"""Where a downloaded section really starts.

yt-dlp cuts sections at keyframes, so a section can begin several seconds
earlier than asked — a 5-10s GOP is ordinary. The section's opening audio is
searched for inside a wider window of the proxy, and the match is scored only
over the samples that actually overlap, so a large but correct offset scores as
highly as a small one. A weak match fails the clip rather than rendering it
misaligned.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from clipper import shell

MIN_CONFIDENCE = 0.4
PROBE_SECONDS = 8.0
SEARCH_BACK = 15.0        # how far before the requested start a section may begin
SEARCH_FORWARD = 3.0


class AlignmentError(Exception):
    pass


def load_audio(path: Path, start: float, duration: float, rate: int = 8000) -> np.ndarray:
    out = shell.run_binary([
        shell.ffmpeg(), "-v", "error", "-ss", str(max(0.0, start)), "-t", str(duration),
        "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(rate), "-",
    ])
    return np.frombuffer(out, dtype=np.float32)


def measure_offset_arrays(
    section: np.ndarray, proxy: np.ndarray, rate: int = 8000
) -> tuple[float, float]:
    """Seconds the section leads the proxy window, and how sure we are (0-1).

    Correlation is normalized per lag by the energy of the overlapping samples,
    so the score reflects how well the two actually match rather than how much
    they overlap.
    """
    if section.size == 0 or proxy.size == 0:
        return 0.0, 0.0
    a = (section - section.mean()).astype(np.float64)
    b = (proxy - proxy.mean()).astype(np.float64)

    corr = np.correlate(b, a, mode="full")
    # Energy of the overlapping part of each signal, per lag.
    energy_a = np.correlate(np.ones_like(b), a * a, mode="full")
    energy_b = np.correlate(b * b, np.ones_like(a), mode="full")
    norm = np.sqrt(energy_a * energy_b)
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(norm > 0, corr / norm, 0.0)

    # Ignore lags with too little overlap to mean anything.
    overlap = np.minimum.reduce([
        np.arange(1, corr.size + 1),
        np.full(corr.size, min(a.size, b.size)),
        np.arange(corr.size, 0, -1),
    ])
    scores[overlap < min(a.size, b.size) // 4] = 0.0

    peak = int(np.argmax(np.abs(scores)))
    lag = peak - (a.size - 1)
    confidence = float(np.abs(scores[peak]))
    # np.correlate's lag is how far the section must shift right to match the
    # proxy; a section that starts earlier needs a left shift, so negate it to
    # report "seconds the section leads".
    return -lag / rate, confidence


def measure_offset(
    section: Path, proxy: Path, expected_start: float, probe_seconds: float = PROBE_SECONDS
) -> tuple[float, float]:
    """Returns the proxy-relative time that corresponds to section time 0."""
    section_audio = load_audio(section, 0.0, probe_seconds)

    # Search a window wide enough to contain the section's opening, however far
    # back the keyframe was.
    window_start = max(0.0, expected_start - SEARCH_BACK)
    window_len = (expected_start - window_start) + probe_seconds + SEARCH_FORWARD
    proxy_audio = load_audio(proxy, window_start, window_len)

    lead, confidence = measure_offset_arrays(section_audio, proxy_audio)
    if confidence < MIN_CONFIDENCE:
        raise AlignmentError(
            f"Could not align the downloaded section with the proxy "
            f"(confidence {confidence:.2f}). Retry this clip."
        )
    return window_start - lead, confidence
