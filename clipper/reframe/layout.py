"""Crop rectangles for each layout, in normalized coordinates.

Every crop stays inside the source frame, so the same plan applies to the 720p
proxy and to a 4K section without ever asking for pixels that don't exist.
"""

from __future__ import annotations

from clipper.models import Rect

TARGET_ASPECT = 9 / 16      # the finished clip
STACK_ASPECT = 9 / 8        # one half of a stacked clip


def _crop_for_aspect(face: Rect, src_w: int, src_h: int, aspect: float) -> Rect:
    src_aspect = src_w / src_h
    if aspect <= src_aspect:                     # limited by height
        h_norm = 1.0
        w_norm = min(1.0, aspect / src_aspect)
    else:                                        # limited by width
        w_norm = 1.0
        h_norm = min(1.0, src_aspect / aspect)

    cx = face.x + face.w / 2
    cy = face.y + face.h / 2
    x = min(max(cx - w_norm / 2, 0.0), 1.0 - w_norm)
    y = min(max(cy - h_norm / 2, 0.0), 1.0 - h_norm)
    return Rect(x=x, y=y, w=w_norm, h=h_norm)


def single_crop(face: Rect, src_w: int, src_h: int) -> Rect:
    return _crop_for_aspect(face, src_w, src_h, TARGET_ASPECT)


def stack_crops(faces: list[Rect], src_w: int, src_h: int) -> list[Rect]:
    ordered = sorted(faces, key=lambda f: f.x)[:2]
    return [_crop_for_aspect(f, src_w, src_h, STACK_ASPECT) for f in ordered]


def fit_rect() -> Rect:
    return Rect(0.0, 0.0, 1.0, 1.0)


def choose_layout(n_faces: int, speaker_confident: bool) -> str:
    if n_faces == 1:
        return "single"
    if n_faces == 2:
        return "speaker" if speaker_confident else "stack"
    return "fit"
