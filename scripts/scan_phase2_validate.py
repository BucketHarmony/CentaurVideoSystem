"""Scanner v2 / Phase 2 — validate PANNs audio classifier on 5 clips.

Verifies the editorial 5-class mapping (speech | chant | song | ambient
| silence) on the same clips Phase 0 used for transcript validation.

Acceptance per the plan:
    - 170245 (We are locked inside song)  → song
    - 170137 (Abolish ICE chant verse 1)  → chant or song (mixed)
    - 165207 (Hassan speech)              → speech
    - 154736 (NDCM organizer speech)      → speech
    - 170030 (pure ABOLISH ICE chant)     → chant

Run:
    python E:/AI/CVS/scripts/scan_phase2_validate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cvs_lib import audio_class

CLIPS_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
OUT_PATH = Path("E:/AI/CVS/mpc/index/_phase2_audio_class.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

CLIPS = [
    ("170137", "chant V1 (Abolish ICE right now)",   {"chant", "song"}),
    ("170245", "song V2 (We are locked inside)",      {"song"}),
    ("165207", "Hassan speech",                       {"speech"}),
    ("154736", "NDCM organizer speech",               {"speech"}),
    ("170030", "pure ABOLISH ICE chant",              {"chant"}),
]


def main():
    print("Loading PANNs CNN14...")
    model = audio_class.load_model()

    results = []
    for stem, label, expected in CLIPS:
        path = CLIPS_DIR / f"20260425_{stem}.mp4"
        if not path.exists():
            print(f"  [skip] {path} missing")
            continue
        print(f"\n=== {stem}  ({label}) ===")
        segs = audio_class.classify_clip(path, model=model)
        cls, frac = audio_class.dominant_class(segs)
        ok = cls in expected
        marker = "OK " if ok else "MISS"
        print(f"  [{marker}] dominant: {cls}  ({frac*100:.0f}% of clip)  "
              f"expected: {sorted(expected)}")
        for s in segs:
            print(f"    {s['t0']:5.2f}-{s['t1']:5.2f}  "
                  f"{s['class']:8s} ({s['confidence']:.2f})")
        results.append({
            "stem": stem, "label": label,
            "expected": sorted(expected),
            "dominant_class": cls,
            "dominant_fraction": round(frac, 3),
            "pass": ok,
            "segments": segs,
        })

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")

    n_pass = sum(1 for r in results if r["pass"])
    print(f"\nResult: {n_pass}/{len(results)} clips classified correctly.")


if __name__ == "__main__":
    main()
