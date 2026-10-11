"""Data types shared by every pipeline step.

All of them serialize to plain JSON so each step's output can be read on disk.
Crop coordinates are normalized (0-1) against the source frame, so a plan built
from the 720p proxy applies unchanged to a 4K section.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Word:
    i: int
    text: str
    start: float
    end: float
    prob: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Word:
        return cls(**d)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    first_word: int
    last_word: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Segment:
        return cls(**d)


@dataclass
class Transcript:
    words: list[Word]
    segments: list[Segment]
    duration: float

    def to_dict(self) -> dict:
        return {
            "words": [w.to_dict() for w in self.words],
            "segments": [s.to_dict() for s in self.segments],
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Transcript:
        return cls(
            [Word.from_dict(w) for w in d["words"]],
            [Segment.from_dict(s) for s in d["segments"]],
            float(d["duration"]),
        )


@dataclass
class Meta:
    job_id: str
    source_kind: str          # "youtube" | "local"
    source: str               # URL, or absolute path for local files
    title: str
    description: str
    channel: str
    duration: float
    width: int                # proxy dimensions
    height: int
    fps: float
    max_height: int           # best height available from the source
    channel_handle: str = ""  # the creator's @handle (YouTube uploader_id); "" when unknown

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Meta:
        return cls(**d)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Rect:
        return cls(**d)


@dataclass
class CropSegment:
    start: float
    end: float
    layout: str               # "single" | "stack" | "fit"
    crops: list[Rect]

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "layout": self.layout,
            "crops": [c.to_dict() for c in self.crops],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CropSegment:
        return cls(
            float(d["start"]),
            float(d["end"]),
            str(d["layout"]),
            [Rect.from_dict(c) for c in d["crops"]],
        )


@dataclass
class CropPlan:
    candidate_n: int
    analyzed_start: float
    analyzed_end: float
    segments: list[CropSegment]

    def to_dict(self) -> dict:
        return {
            "candidate_n": self.candidate_n,
            "analyzed_start": self.analyzed_start,
            "analyzed_end": self.analyzed_end,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CropPlan:
        return cls(
            int(d["candidate_n"]),
            float(d["analyzed_start"]),
            float(d["analyzed_end"]),
            [CropSegment.from_dict(s) for s in d["segments"]],
        )


@dataclass
class Candidate:
    n: int
    start: float
    end: float
    orig_start: float
    orig_end: float
    headline: str
    hook: str
    reason: str
    score: int
    post_caption: str
    hashtags: list[str] = field(default_factory=list)
    layout: str = "auto"      # "auto" | "stack" | "fit"
    music_on: bool = False
    music_track: str | None = None
    approved: bool = False
    needs_check: bool = False
    edited: bool = False       # changed in review; guards "Pick again"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Candidate:
        return cls(**d)
