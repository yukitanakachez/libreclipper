"""Generates tests/fixtures/shots.mp4: three 2s shots of flat colours.

Run once: .venv/bin/python tests/fixtures/make_fixtures.py
"""

import subprocess
from pathlib import Path

from clipper import shell

OUT = Path(__file__).parent / "shots.mp4"


def main() -> None:
    parts = []
    for colour in ("red", "green", "blue"):
        part = OUT.parent / f"_{colour}.mp4"
        subprocess.run([
            shell.ffmpeg(), "-y", "-f", "lavfi",
            "-i", f"color=c={colour}:s=1280x720:d=2:r=30",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(part),
        ], check=True)
        parts.append(part)

    listing = OUT.parent / "_list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run([
        shell.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", str(OUT),
    ], check=True, cwd=OUT.parent)

    for p in parts + [listing]:
        p.unlink()


if __name__ == "__main__":
    main()
