"""Step 6: cut, crop, caption and encode the approved clips.

One ffmpeg pass per clip: trim to the clip, apply the crop timeline (a shot can
contain several segments when the speaker changes), burn in captions, mix music
if it was toggled on, and normalize loudness to what social platforms play at.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from clipper import align, captions, fetch, jobs, pacing, shell
from clipper.campaigns import Campaign, music_tracks
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Candidate, CropPlan, CropSegment, Meta, Transcript

OUT_W, OUT_H = 1080, 1920
LOUDNESS = "I=-14:TP=-1:LRA=11"



class RenderError(Exception):
    pass


def caption_layout(
    plan_segments: list[CropSegment], clip_start: float, clip_end: float
) -> str:
    """The layout of the first segment the clip actually shows.

    The crop plan covers candidate +/-10s, so its first segment may belong to
    footage the viewer never sees — and it decides where captions sit.
    """
    for segment in plan_segments:
        if segment.end > clip_start and segment.start < clip_end:
            return segment.layout
    return "single"


def parse_loudnorm_json(stderr: str) -> dict:
    """Pull the measurement block out of ffmpeg's loudnorm pass."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        return json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return {}


MEASURED_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def _usable(measured: dict | None) -> bool:
    """Silence measures as -inf, which loudnorm rejects; fall back to one pass."""
    if not measured or any(k not in measured for k in MEASURED_KEYS):
        return False
    try:
        values = [float(measured[k]) for k in MEASURED_KEYS]
    except (TypeError, ValueError):
        return False
    return all(v == v and abs(v) != float("inf") for v in values)


def _is_silent(measured: dict | None) -> bool:
    return bool(measured) and str(measured.get("input_i", "")).strip() == "-inf"


def _loudnorm_filter(measured: dict | None, measure: bool) -> str:
    if measure:
        return f"loudnorm={LOUDNESS}:print_format=json"
    if _is_silent(measured):
        # Nothing to normalize; loudnorm on digital silence emits NaN samples.
        return "anull"
    if _usable(measured):
        return (
            f"loudnorm={LOUDNESS}"
            f":measured_I={measured['input_i']}"
            f":measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}"
            f":measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}"
            ":linear=true"
        )
    return f"loudnorm={LOUDNESS}"


def _pace_audio(source: str, keep: list[tuple[float, float]] | None,
                speed: float) -> tuple[list[str], str]:
    """Cut pauses (sample-accurate) and speed up. Returns (graph parts, output label)."""
    parts: list[str] = []
    if keep:
        n = len(keep)
        pieces = []
        if n > 1:
            parts.append(f"{source}asplit={n}" + "".join(f"[p{i}]" for i in range(n)))
        for i, (a, b) in enumerate(keep):
            length = b - a
            fade = min(0.005, length / 4)
            src = f"[p{i}]" if n > 1 else source
            parts.append(
                f"{src}atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={fade:.4f},afade=t=out:st={length - fade:.4f}:d={fade:.4f}[q{i}]"
            )
            pieces.append(f"[q{i}]")
        parts.append(f"{''.join(pieces)}concat=n={n}:v=0:a=1[cut]")
        source = "[cut]"
    if speed != 1.0:
        parts.append(f"{source}atempo={speed:.3f}[fast]")
        source = "[fast]"
    return parts, source


def build_audio_graph(
    clip_start: float,
    clip_end: float,
    music: Path | None,
    music_db: float,
    measured: dict | None = None,
    measure: bool = False,
    keep: list[tuple[float, float]] | None = None,
    speed: float = 1.0,
) -> str:
    """The audio half of the graph, shared by the measure and render passes."""
    parts = [
        f"[0:a]atrim=start={clip_start:.3f}:end={clip_end:.3f},asetpts=PTS-STARTPTS[raw]"
    ]
    paced, source = _pace_audio("[raw]", keep, speed)
    parts += paced
    parts.append(f"{source}anull[speech]")

    kept_length = sum(b - a for a, b in keep) if keep else clip_end - clip_start
    finished = kept_length / speed
    if music is not None:
        parts.append(
            f"[1:a]volume={music_db:.0f}dB,afade=t=in:st=0:d=0.5,"
            f"afade=t=out:st={max(0.0, finished - 1.0):.3f}:d=1.0[bed]"
        )
        parts.append(
            "[bed][speech]sidechaincompress=threshold=0.03:ratio=8:attack=20:"
            "release=400[ducked]"
        )
        parts.append("[ducked][speech]amix=inputs=2:duration=shortest:normalize=0[mixed]")
        source = "[mixed]"
    else:
        source = "[speech]"
    # loudnorm outputs 192kHz; AAC will not take it, so pin the rate here
    # rather than at every call site.
    parts.append(f"{source}{_loudnorm_filter(measured, measure)},aresample=48000[aout]")
    return ";".join(parts)


def _even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def _crop(rect, src_w: int, src_h: int) -> str:
    return (
        f"crop={_even(rect.w * src_w)}:{_even(rect.h * src_h)}:"
        f"{_even(rect.x * src_w)}:{_even(rect.y * src_h)}"
    )


def build_filtergraph(
    plan_segments: list[CropSegment],
    clip_start: float,
    clip_end: float,
    src_w: int,
    src_h: int,
    ass_path: Path | None,
    music: Path | None,
    music_db: float,
    measured: dict | None = None,
    keep: list[tuple[float, float]] | None = None,
    speed: float = 1.0,
    fps: float = 30.0,
) -> str:
    parts: list[str] = []
    labels: list[str] = []

    for idx, segment in enumerate(plan_segments):
        start = max(segment.start, clip_start)
        end = min(segment.end, clip_end)
        if end <= start:
            continue
        label = f"v{idx}"
        trim = f"trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS"

        if segment.layout == "stack":
            top, bottom = segment.crops[0], segment.crops[1]
            parts.append(
                f"[0:v]{trim},{_crop(top, src_w, src_h)},scale={OUT_W}:{OUT_H // 2},"
                f"setsar=1[{label}a]"
            )
            parts.append(
                f"[0:v]{trim},{_crop(bottom, src_w, src_h)},scale={OUT_W}:{OUT_H // 2},"
                f"setsar=1[{label}b]"
            )
            parts.append(f"[{label}a][{label}b]vstack=inputs=2,setsar=1[{label}]")
        elif segment.layout == "fit":
            parts.append(f"[0:v]{trim},scale={OUT_W}:-2,setsar=1[{label}f]")
            parts.append(
                f"[0:v]{trim},scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
                f"crop={OUT_W}:{OUT_H},gblur=sigma=30,eq=brightness=-0.15[{label}bg]"
            )
            parts.append(
                f"[{label}bg][{label}f]overlay=(W-w)/2:(H-h)/2,setsar=1[{label}]"
            )
        else:
            parts.append(
                f"[0:v]{trim},{_crop(segment.crops[0], src_w, src_h)},"
                f"scale={OUT_W}:{OUT_H},setsar=1[{label}]"
            )
        labels.append(f"[{label}]")

    if not labels:
        raise RenderError(
            f"no crop segments cover {clip_start:.1f}-{clip_end:.1f}s. "
            "Re-run reframe for this candidate, or widen the trim."
        )
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[vcat]")

    # Order matters: drop the paused frames, burn captions timed to the cut clip,
    # then speed everything up together so captions stay locked to the words.
    video: list[str] = []
    if keep:
        half = 0.5 / fps
        expr = "+".join(f"gte(t\\,{a - half:.4f})*lt(t\\,{b - half:.4f})" for a, b in keep)
        video += [f"select='{expr}'", f"setpts=N/({fps}*TB)"]
    if ass_path:
        fonts = shell.project_home() / "assets" / "fonts"
        video.append(f"ass={shell.filter_path(ass_path)}:fontsdir={shell.filter_path(fonts)}")
    if speed != 1.0:
        # Convert back to a standard rate here, not with the output -r flag: -r
        # kept extra frames and left video ~0.07 s longer than the audio.
        video += [f"setpts=PTS/{speed:.3f}", f"fps={min(60.0, fps):g}"]
    parts.append(f"[vcat]{','.join(video) or 'null'}[vout]")

    parts.append(build_audio_graph(clip_start, clip_end, music, music_db, measured,
                                   keep=keep, speed=speed))

    return ";".join(parts)


def write_sidecar(path: Path, candidate: Candidate) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{candidate.post_caption}\n\n{' '.join(candidate.hashtags)}\n")
    return path


def section_path(paths: JobPaths, candidate: Candidate) -> Path:
    """Where a candidate's high-quality download lives, keyed by its time range.

    Keyed by range, not candidate number: re-picking renumbers candidates, and
    yt-dlp skips files that already exist, so a number-keyed file would quietly
    serve an old candidate's footage.
    """
    return paths.sections / f"{candidate.start:.2f}-{candidate.end:.2f}.mp4"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "clip"


def retire_older_renders(out_dir: Path, n: int) -> None:
    """Move earlier renders of clip n into previous/, so the clips folder (and the
    phone) shows only the current one, and nothing you may have posted is lost."""
    older = [p for p in Path(out_dir).glob(f"{n:02d}-*")
             if p.is_file() and not p.name.endswith(".partial.mp4")]
    if not older:
        return
    previous = Path(out_dir) / "previous"
    previous.mkdir(exist_ok=True)
    for path in older:
        target, k = previous / path.name, 2
        while target.exists():                           # keep every earlier version
            target, k = previous / f"{path.stem}-{k}{path.suffix}", k + 1
        os.replace(path, target)


def _pick_music(candidate: Candidate, campaign: Campaign) -> Path | None:
    if not (candidate.music_on and campaign.music_allowed and campaign.music_folder):
        return None
    if candidate.music_track:
        return Path(candidate.music_track)
    tracks = music_tracks(campaign)
    return Path(tracks[0]) if tracks else None


def render_clip(
    paths: JobPaths,
    meta: Meta,
    campaign: Campaign,
    candidate: Candidate,
    plan: CropPlan,
    transcript: Transcript,
    cfg: AppConfig,
) -> Path:
    section = fetch.download_section(
        meta, candidate.start, candidate.end, section_path(paths, candidate), cfg,
    )
    src_w, src_h, src_fps = fetch.probe_video(section)

    if meta.source_kind == "local":
        offset = 0.0
    else:
        offset, _ = align.measure_offset(
            section, paths.proxy, max(0.0, candidate.start - 5.0)
        )

    clip_start = candidate.start - offset
    clip_end = candidate.end - offset
    segments = [
        CropSegment(s.start - offset, s.end - offset, s.layout, s.crops)
        for s in plan.segments
    ]

    fixes = jobs.read_json(paths.word_fixes) if paths.word_fixes.exists() else {}
    words = captions.apply_word_fixes(
        [w for w in transcript.words
         if w.end > candidate.start and w.start < candidate.end],
        fixes,
    )
    # Pacing works in clip-relative time, so the section offset cancels out.
    keep = pacing.keep_intervals(words, candidate.start, candidate.end,
                                 campaign.pacing, fps=src_fps)
    time_map = pacing.TimeMap(keep)
    cut = keep if campaign.pacing.cut_pauses else None
    speed = campaign.pacing.speed

    chunks = captions.retime_chunks(captions.chunk_words(words), time_map,
                                    clip_start=candidate.start)
    ass_path = captions.write_ass(
        paths.work / f"clip_{candidate.n:02d}.ass",
        chunks,
        campaign,
        caption_layout(segments, clip_start, clip_end),
        0.0,
        candidate.headline,
        campaign.credit_handle,
        duration=time_map.duration,
    )

    music = _pick_music(candidate, campaign)

    def inputs() -> list[str]:
        cmd = [shell.ffmpeg(), "-y", "-i", str(section)]
        if music is not None:
            cmd += ["-stream_loop", "-1", "-i", str(music)]
        return cmd

    # Pass 1: measure this clip's loudness (audio only, so it is cheap).
    measure_graph = build_audio_graph(
        clip_start, clip_end, music, campaign.music_volume_db, measure=True,
        keep=cut, speed=speed,
    )
    measured = parse_loudnorm_json(
        shell.run_capture_stderr(
            inputs() + ["-filter_complex", measure_graph, "-map", "[aout]",
                        "-f", "null", "-"]
        )
    )

    # Pass 2: render with those measurements applied.
    graph = build_filtergraph(
        segments, clip_start, clip_end, src_w, src_h, ass_path, music,
        campaign.music_volume_db, measured=measured,
        keep=cut, speed=speed, fps=src_fps,
    )

    out_path = paths.out / f"{candidate.n:02d}-{_slug(candidate.headline)}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # The Output page and iCloud see the clips folder: publish only complete files.
    partial = out_path.with_name(out_path.stem + ".partial.mp4")

    try:
        shell.run(inputs() + [
            "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-r", str(min(60.0, src_fps)),
            "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
            "-movflags", "+faststart", str(partial),
        ])
        retire_older_renders(paths.out, candidate.n)
        os.replace(partial, out_path)
    finally:
        partial.unlink(missing_ok=True)

    write_sidecar(out_path.with_suffix(".txt"), candidate)
    return out_path
