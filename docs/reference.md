# Reference

Details that most people never need. The [README](../README.md) covers getting started.

## Command line

Everything the app does is also a command:

```bash
.venv/bin/clipper run ~/Downloads/episode-12.mov --campaign auto --creator @examplepod
.venv/bin/clipper preview <job-id>          # optional: check the crop before rendering
.venv/bin/clipper approve <job-id> 1 3
.venv/bin/clipper render <job-id>
```

`run` prints the ranked moments with the reason each was picked. Moments flagged
`[check framing]` are ones where the crop fell back to a safe layout.

| Command | Does |
|---|---|
| `clipper serve` | starts the app (what `./start` runs) |
| `clipper app` | makes Clipper.app in `~/Applications`; its log is `~/Library/Logs/Clipper.log` |
| `clipper doctor` | lists every setup check with its fix |
| `clipper setup` | downloads anything missing (ffmpeg, the face model), then checks |
| `clipper clean` | deletes working files from jobs older than `retention_days`; finished clips are kept |

To re-pick moments on a job you already transcribed (after changing the prompt or campaign):
`clipper run <file> --campaign <slug> --from pick`.

`./start --port 9000` and `./start --no-browser` pass their options on to `clipper serve`.

## What `./start` installs

Everything goes into the project folder:

| Folder | Holds |
|---|---|
| `.tools/` | uv, Python, Node.js (only if you have none), and the downloaded ffmpeg |
| `.venv/` | the Python packages |
| `assets/` | the caption font and the face-detection model |
| `jobs/` | your jobs and finished clips |

The app downloads ffmpeg and the face model itself on first start; each is a fixed version
checked against a SHA-256.

## Optional settings

Clipper needs no configuration file. To change where jobs and finished clips are kept, or how
long working files stay, copy `config.yaml.example` to `config.yaml` and edit it. Every key
is optional.

To use your own ffmpeg, set `CLIPPER_FFMPEG`. It must be built with libass.

## AI providers

**Settings** (the gear) is where you choose the one provider that picks the moments:
Anthropic, OpenAI, Google Gemini, OpenRouter, Mistral, DeepSeek, or Ollama running on this
computer. Only one is in use at a time; the others keep their keys.

Keys are saved in `settings.json` in the project folder, readable only by you and ignored by
git. A key already in your shell (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, …)
is picked up without typing anything.

Anthropic is the provider Clipper was built and tuned with. The others go through their
OpenAI-compatible APIs.

## Videos you drop in

A video you pick through Finder is read where it is. A dropped video is copied into
`jobs/uploads/`, because a browser never says where a dropped file lives. That copy is
deleted with the job's other working files after `retention_days`.

## Campaign options

```yaml
name: Example Podcast
credit: { enabled: true, handle: "@examplepod", position: below_headline }
clip_length: { min: 20, max: 60 }
required_hashtags: ["#examplepod"]
vocabulary: ["Jane Doe", "Acme"]
headline: { enabled: true }
music: { allowed: true, folder: music/example-podcast, volume_db: -22 }
captions: { accent_color: "#FFE500", uppercase: false }
pacing: { cut_pauses: true, max_pause: 0.3, speed: 1.1 }
```

`pacing` tightens the rhythm: silences longer than `max_pause` seconds are cut to a short
breath, then the clip plays at `speed` with the pitch preserved. Set `cut_pauses: false` and
`speed: 1.0` for creators who don't want their audio altered. `clip_length` applies to the
finished clip, after cuts and speed-up.

With the **Any video** campaign, the credit and creator hashtag come from the **Creator** box
in New (or `--creator`).

## How a job is stored

Each video gets `jobs/<job-id>/`, and every step writes one file:

| File | Written by | Holds |
|---|---|---|
| `status.json` | all | current step, progress, any error |
| `meta.json` | fetch | title, creator, duration, resolution |
| `proxy.mp4` | fetch | 720p working copy (never the final output) |
| `transcript.json` | transcribe | every word with its timing |
| `candidates.json` | pick | the moments and your edits |
| `crop_plan.json` | reframe | where the 9:16 crop goes |
| `out/` | render | finished clips and their captions |
| `clips.json` | the app | which moment each clip came from, and when you marked it posted |

Any step can be re-run without redoing the ones before it, and every file is plain JSON.

## Setting it up by hand

`./start` is a short shell script, and you can do what it does yourself:

```bash
uv sync
cd frontend && npm ci && npm run build && cd ..
.venv/bin/clipper serve
```

On Apple Silicon the Python must be an arm64 one (`mediapipe` and `mlx-whisper` have no Intel
macOS builds), which is why `./start` brings its own uv and Python.

## Other systems

Clipper is built and tested on Apple Silicon Macs.

- **Linux** (x86-64 and arm64): `./start` runs, and transcription switches to
  `faster-whisper` by itself. This path has had far less use, so expect rough edges.
- **Windows**: no launcher yet. Under WSL, use the Linux steps. Natively, install uv, Node.js
  and an ffmpeg with libass yourself, then follow "Setting it up by hand". **Show in Finder**
  is Mac-only.

## Checking speaker detection

`scripts/validate_speaker.md` is a short procedure for checking who-is-talking detection
against real episodes. It is the least certain part of the design, and the file lists which
knobs to turn if it does not hold up.
