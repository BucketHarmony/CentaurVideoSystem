"""Generate posting covers for every rendered MPC reel.

Each reel gets a 1080x1920 PNG in `output/mpc/covers/<reel>.png`. Per-reel
config picks the best frame (`t`) and an optional overlay headline + sub
that punches up the in-feed thumbnail. Reels without explicit config get
a default frame extracted at 25% of duration with no overlay.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cvs_lib.cover import make_cover

OUT_BASE = Path("E:/AI/CVS/ComfyUI/output/mpc")
COVER_DIR = OUT_BASE / "covers"
COVER_DIR.mkdir(parents=True, exist_ok=True)

# Per-reel cover config. `t` = seek time in seconds (frame extracted from
# this point — pick a peak editorial moment, often mid-CTA or mid-FIGHT).
# `headline`/`sub` override the in-frame chrome with a punchier hook just
# for the thumbnail. Set to None to use the raw frame as the cover.
COVERS = [
    # HOOK at t=2: in-video chrome is already a strong hook ("ROMULUS /
    # TODAY · APRIL 25, 2026"); adding an overlay headline competes with
    # whatever beat's chrome we land on. Use raw frame for this one.
    {"reel": "romulus_rapid_response.mp4", "t": 2.0,
     "headline": None, "sub": None},
    {"reel": "romulus_march.mp4", "t": 7.5,
     "headline": "WE MARCH",
     "sub": "FOR OUR NEIGHBORS"},
    {"reel": "ten_weeks.mp4", "t": 4.0,
     "headline": "10 WEEKS",
     "sub": "OF AGGRESSION"},
    {"reel": "north_lake.mp4", "t": 5.0,
     "headline": "NORTH LAKE",
     "sub": "THIS IS WHO THEY ARE"},
    {"reel": "follow_the_money.mp4", "t": 14.0,
     "headline": "$254M",
     "sub": "FOLLOW THE MONEY"},
    {"reel": "we_dont_back_down.mp4", "t": 22.0,
     "headline": "WE DON'T",
     "sub": "BACK DOWN"},
    # t=24 was on the fade-to-black at scene end; t=14 is mid-FIGHT.
    {"reel": "abolish_ice_congress.mp4", "t": 14.0,
     "headline": "ABOLISH ICE",
     "sub": "ACT OF CONGRESS"},
    {"reel": "detroit_knows.mp4", "t": 6.0,
     "headline": "DETROIT KNOWS",
     "sub": None},
    {"reel": "people_power.mp4", "t": 22.0,
     "headline": "PEOPLE POWER",
     "sub": None},
    {"reel": "locked_inside.mp4", "t": 4.0,
     "headline": "LOCKED INSIDE",
     "sub": None},
    # template_30s_demo is the dead template reel; cover with no overlay
    # (kept for parity, can be ignored at posting time).
    {"reel": "template_30s_demo.mp4", "t": 7.5,
     "headline": None, "sub": None},
]


def _probe_duration(p: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(p)],
        stderr=subprocess.STDOUT,
    ).decode().strip()
    return float(out)


def main():
    print(f"Generating MPC covers -> {COVER_DIR}")
    written = []
    for spec in COVERS:
        reel = OUT_BASE / spec["reel"]
        if not reel.exists():
            print(f"  SKIP missing: {spec['reel']}")
            continue
        out = COVER_DIR / (reel.stem + ".png")
        t = float(spec["t"])
        # Clamp to duration just in case
        try:
            dur = _probe_duration(reel)
            t = min(t, max(0.0, dur - 0.05))
        except Exception:
            pass
        head = spec.get("headline")
        sub = spec.get("sub")
        tag = "(raw)" if head is None else f"(\"{head}\"" + (f" / \"{sub}\"" if sub else "") + ")"
        print(f"  {reel.name}  t={t:.2f}s  {tag}")
        make_cover(reel, out, t_seek=t, headline=head, sub=sub)
        written.append(out)

    print("\nDone:")
    for p in written:
        print(f"  {p}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
