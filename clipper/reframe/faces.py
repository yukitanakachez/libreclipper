"""Where the faces are, and how much each mouth is moving.

Detections are sampled at 10 fps and grouped into per-person tracks by position.
`mouth` is the inner-lip gap divided by face height, which is what the speaker
timeline turns into "who is talking".
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

from clipper import shell
from clipper.models import Rect

MODEL_FILE = "face_landmarker.task"
UPPER_LIP, LOWER_LIP = 13, 14      # MediaPipe face-mesh inner lip landmarks


@dataclass(frozen=True)
class FaceSample:
    t: float
    box: Rect
    mouth: float


@dataclass
class FaceTrack:
    id: int
    samples: list[FaceSample] = field(default_factory=list)

    def median_box(self) -> Rect:
        return Rect(
            x=statistics.median(s.box.x for s in self.samples),
            y=statistics.median(s.box.y for s in self.samples),
            w=statistics.median(s.box.w for s in self.samples),
            h=statistics.median(s.box.h for s in self.samples),
        )

    def mouth_series(self) -> list[tuple[float, float]]:
        return [(s.t, s.mouth) for s in sorted(self.samples, key=lambda s: s.t)]


def _iou(a: Rect, b: Rect) -> float:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def group_into_tracks(
    detections: list[tuple[float, Rect, float]], iou_threshold: float = 0.3
) -> list[FaceTrack]:
    tracks: list[FaceTrack] = []
    for t, box, mouth in sorted(detections, key=lambda d: d[0]):
        best, best_iou = None, iou_threshold
        for track in tracks:
            score = _iou(track.samples[-1].box, box)
            if score >= best_iou:
                best, best_iou = track, score
        if best is None:
            best = FaceTrack(id=len(tracks))
            tracks.append(best)
        best.samples.append(FaceSample(t=t, box=box, mouth=mouth))
    return tracks


def _model_path() -> Path:
    path = shell.project_home() / "assets" / MODEL_FILE
    if not path.exists():
        from clipper import provision  # imported here: provision imports this module
        provision.ensure(("model",))            # downloads it, once
    if not path.exists():
        raise FileNotFoundError(
            f"MediaPipe model missing: {path}. Run clipper setup to download it."
        )
    return path


class Sampler:
    """Picks roughly `fps` frames per second out of a source played in order.

    Keeps the first frame at or after each tick, so a 29.97 or 60 fps source both
    come out at ~10 fps without seeking to exact timestamps.
    """

    EPS = 0.001

    def __init__(self, start: float, end: float, fps: float = 10.0) -> None:
        self.next_due = start
        self.end = end
        self.step = 1.0 / fps

    def take(self, t: float) -> bool:
        if t >= self.end or t < self.next_due - self.EPS:
            return False
        while self.next_due <= t + self.EPS:
            self.next_due += self.step
        return True


def _open_video(path: Path):
    import cv2

    return cv2.VideoCapture(str(path))


def iter_sampled_frames(video: Path, start: float, end: float, fps: float = 10.0):
    """Yields (seconds, RGB frame) for ~fps frames per second across [start, end).

    One seek to the start, then sequential reads. Seeking per sample cost ~38 ms
    a frame on AV1 proxies; reading forward costs ~1 ms, and frames that are not
    kept are only grabbed, never decoded to pixels.
    """
    import cv2

    cap = _open_video(video)
    sampler = Sampler(start, end, fps)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        while cap.grab():
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t >= end:
                break
            if not sampler.take(t):
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            yield t, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()


def _make_landmarker():
    import mediapipe as mp
    from mediapipe.tasks.python import vision

    return vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_model_path())),
            num_faces=4,
            running_mode=vision.RunningMode.VIDEO,
        )
    )


def detect_faces(
    video: Path, start: float, end: float, fps: float = 10.0
) -> list[tuple[float, Rect, float]]:
    """Every face in [start, end) as (seconds, box, mouth openness).

    One landmarker for the whole range. Its video mode needs rising timestamps,
    so callers make one call per candidate rather than sharing one across a job.
    """
    import mediapipe as mp

    landmarker = _make_landmarker()
    detections: list[tuple[float, Rect, float]] = []
    last_ms = -1
    try:
        for t, rgb in iter_sampled_frames(video, start, end, fps):
            ms = max(int(round(t * 1000)), last_ms + 1)
            last_ms = ms
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(image, ms)
            for marks in result.face_landmarks:
                xs = [m.x for m in marks]
                ys = [m.y for m in marks]
                box = Rect(x=min(xs), y=min(ys), w=max(xs) - min(xs), h=max(ys) - min(ys))
                mouth = abs(marks[LOWER_LIP].y - marks[UPPER_LIP].y) / box.h if box.h else 0.0
                detections.append((t, box, mouth))
    finally:
        landmarker.close()
    return detections


def tracks_in(
    detections: list[tuple[float, Rect, float]], start: float, end: float
) -> list[FaceTrack]:
    """The face tracks for one shot, from detections made across a whole range."""
    return group_into_tracks([d for d in detections if start <= d[0] < end])
