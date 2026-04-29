"""Demo: 5 tight clips cut by phrase via clip_locator + ffmpeg.

Demonstrates the new word_index -> clip_snap -> clip_locator pipeline
end-to-end. Each entry below names a phrase + stem; the script
resolves the phrase to a snap-refined cut, then ffmpegs the actual
mp4 with frame-accurate seek.

Output: output/mpc/_demo_clips/<NN_slug>.mp4 + demo_manifest.json
listing duration, RMS quality, deltas.

Run:
    python scripts/mpc_demo_clips.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cvs_lib.clip_cut import cut_clip
from cvs_lib.clip_locator import locate_phrase_clip

OUT_DIR = REPO / "ComfyUI" / "output" / "mpc" / "_demo_clips"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUT_DIR / "demo_manifest.json"

# Editorially distinct: testimony / coalition fact / community call /
# personal stake / dollar figure. Five different speakers; five different
# emotional registers.
DEMOS = [
    {
        "n": 1,
        "stem": "20260425_155313",
        "phrase": "I was detained for three months at North Lake",
        "slug": "north_lake_testimony",
        "register": "testimony - primary source",
    },
    {
        "n": 2,
        "stem": "20260425_153128",
        "phrase": "to oppose the construction",
        "slug": "nbcm_origin",
        "register": "coalition origin - context",
    },
    {
        "n": 3,
        "stem": "20260425_154736",
        "phrase": "the community of Romulus is engaged",
        "slug": "community_engaged",
        "register": "rally call - organizing",
    },
    {
        "n": 4,
        "stem": "20260425_165207",
        "phrase": "I am very fearful",
        "slug": "naz_fearful",
        "register": "personal stake - emotion",
    },
    {
        "n": 5,
        "stem": "20260425_170328",
        "phrase": "254 million",
        "slug": "geogroup_254m",
        "register": "dollar figure - receipts",
    },
]


def main():
    print(f"Resolving {len(DEMOS)} demo clips -> {OUT_DIR}")
    print(f"SNR gate: reject when speech RMS - noise RMS < +10 dB")
    print()
    manifest = []
    cut_count = 0
    rejected_count = 0
    for spec in DEMOS:
        print(f"[{spec['n']}/{len(DEMOS)}] {spec['register']}")
        print(f"  stem={spec['stem']}  phrase={spec['phrase']!r}")
        # Resolve with the gate disabled so we can report on rejections;
        # we apply the gate ourselves below to decide whether to ffmpeg.
        res = locate_phrase_clip(
            spec["stem"], spec["phrase"], skip_off_mic=False,
        )
        if res is None:
            print(f"  SKIP: no match found")
            continue
        print(f"  cand: in={res.candidate_in_t:.3f}  "
              f"out={res.candidate_out_t:.3f}")
        print(f"  snap: in={res.in_t:.3f}  out={res.out_t:.3f}  "
              f"dur={res.duration:.3f}s")
        print(f"  qual: SNR{res.snr_db:+.1f} dB  "
              f"speech={res.speech_rms_db:+.1f}  "
              f"noise={res.noise_rms_db:+.1f}  "
              f"voice={res.voice_pct:.0f}%")
        print(f"  edge: {res.in_rms_db:+.1f}/{res.out_rms_db:+.1f} dB  "
              f"d{res.in_delta_ms:+.0f}/{res.out_delta_ms:+.0f}ms"
              f"{' [IN_VOICE]' if res.in_voice else ''}"
              f"{' [OUT_VOICE]' if res.out_voice else ''}")

        entry = {
            "n": spec["n"],
            "register": spec["register"],
            "phrase": spec["phrase"],
            "matched_text": res.matched_text,
            "stem": spec["stem"],
            "source_path": res.path,
            "in_t": round(res.in_t, 3),
            "out_t": round(res.out_t, 3),
            "duration_s": round(res.duration, 3),
            "candidate_in_t": round(res.candidate_in_t, 3),
            "candidate_out_t": round(res.candidate_out_t, 3),
            "in_rms_db": round(res.in_rms_db, 1),
            "out_rms_db": round(res.out_rms_db, 1),
            "in_voice": res.in_voice,
            "out_voice": res.out_voice,
            "delta_in_ms": round(res.in_delta_ms),
            "delta_out_ms": round(res.out_delta_ms),
            "match_score": round(res.match_score, 2),
            "speech_rms_db": round(res.speech_rms_db, 1),
            "noise_rms_db": round(res.noise_rms_db, 1),
            "snr_db": round(res.snr_db, 1),
            "voice_pct": round(res.voice_pct, 1),
            "is_off_mic": res.is_off_mic,
        }

        if res.is_off_mic:
            print(f"  REJECTED: OFF-MIC (SNR{res.snr_db:+.1f} dB below +10)")
            print()
            entry["status"] = "rejected_off_mic"
            entry["output"] = None
            entry["size_kb"] = 0
            manifest.append(entry)
            rejected_count += 1
            continue

        out_name = f"{spec['n']:02d}_{spec['slug']}.mp4"
        out_path = OUT_DIR / out_name
        elapsed = cut_clip(Path(res.path), res.in_t, res.out_t, out_path)
        size_kb = out_path.stat().st_size // 1024
        print(f"  -> {out_name}  ({size_kb} KB, {elapsed:.1f}s)")
        print()
        entry["status"] = "cut"
        entry["output"] = out_name
        entry["size_kb"] = size_kb
        manifest.append(entry)
        cut_count += 1

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2), encoding="utf-8",
    )
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Cut: {cut_count}/{len(DEMOS)}.  "
          f"Rejected off-mic: {rejected_count}.")


if __name__ == "__main__":
    main()
