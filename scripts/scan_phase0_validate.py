"""
Scanner v2 / Phase 0 — validate large-v3 + domain prompt on 5 clips.

Side-by-side: faster-whisper `small` greedy (current default in
`mpc_scan_sources.py`) vs `large-v3` + Detroit/ICE/Romulus
`initial_prompt` + word timestamps.

Output: diff table to stdout AND `mpc/index/_phase0_diff.json` for
later inspection.

Five sample clips:
  170137 — chant verse 1 ("Abolish ICE right now")
  170245 — chant verse 2 ("We are locked inside")
  165207 — Hassan speech ("Our democracy is at test")
  154736 — NDCM organizer speech ("tenth week protesting")
  170030 — pure repetitive chant ("ABOLISH ICE!")

Run:
    python E:/AI/CVS/scripts/scan_phase0_validate.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from pathlib import Path

from faster_whisper import WhisperModel


CLIPS_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
OUT_PATH = Path("E:/AI/CVS/mpc/index/_phase0_diff.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

CLIPS = [
    ("170137", "chant V1 (Abolish ICE right now)"),
    ("170245", "chant V2 (We are locked inside)"),
    ("165207", "Hassan speech (democracy is at test)"),
    ("154736", "NDCM organizer (tenth week protesting)"),
    ("170030", "pure ABOLISH ICE chant"),
]

# Project-specific decoding prompt. Vocabulary-only — first attempt
# quoted exact chant phrases ("Crowd chants: 'Abolish ICE right now'")
# and those phrases LEAKED into transcripts of song clips. Whisper
# treats prompts as continuation context, so quoted strings get echoed.
# Strip to noun list: people, places, key vocab. No verbs, no quotes.
INITIAL_PROMPT = (
    "Detroit. Romulus. Michigan. ICE. Rashida Tlaib. Shri Thanedar. "
    "Naz Hassan. abolish. neighbors. coup. protest. rally."
)


def transcribe(model, path, *, prompt=None, beam=1, word_ts=False,
               vad=True):
    t0 = time.time()
    segments, _info = model.transcribe(
        str(path),
        language="en",
        beam_size=beam,
        vad_filter=vad,
        vad_parameters=dict(min_silence_duration_ms=500) if vad else None,
        word_timestamps=word_ts,
        initial_prompt=prompt,
    )
    out = []
    for s in segments:
        rec = {
            "start": round(float(s.start), 2),
            "end": round(float(s.end), 2),
            "text": s.text.strip(),
        }
        if word_ts and s.words:
            rec["words"] = [
                {"start": round(float(w.start), 2),
                 "end": round(float(w.end), 2),
                 "word": w.word.strip()}
                for w in s.words
            ]
        out.append(rec)
    return out, time.time() - t0


def main():
    print("Loading whisper-small (baseline)...")
    base = WhisperModel("small", device="cuda", compute_type="float16")
    print("Loading whisper-large-v3 (candidate)...")
    cand = WhisperModel("large-v3", device="cuda", compute_type="float16")

    diff = []
    for stem, label in CLIPS:
        path = CLIPS_DIR / f"20260425_{stem}.mp4"
        if not path.exists():
            print(f"  [skip] {path} missing")
            continue
        print(f"\n=== {stem}  ({label}) ===")

        # Baseline mirrors current `mpc_scan_sources.py`: small + greedy + VAD.
        b_segs, b_dt = transcribe(base, path, prompt=None, beam=1,
                                   word_ts=False, vad=True)
        # Candidate: large-v3, beam=5, vocab prompt, VAD OFF (singing
        # gets gated by VAD even on the loud chant clips).
        c_segs, c_dt = transcribe(cand, path, prompt=INITIAL_PROMPT,
                                   beam=5, word_ts=True, vad=False)

        b_text = " ".join(s["text"] for s in b_segs)
        c_text = " ".join(s["text"] for s in c_segs)

        print(f"\n  baseline ({b_dt:.1f}s): {b_text}")
        print(f"\n  candidate ({c_dt:.1f}s): {c_text}")

        diff.append({
            "stem": stem,
            "label": label,
            "baseline": {
                "model": "small", "prompt": None, "beam": 1,
                "elapsed_s": round(b_dt, 2),
                "text": b_text, "segments": b_segs,
            },
            "candidate": {
                "model": "large-v3", "prompt": INITIAL_PROMPT, "beam": 5,
                "word_timestamps": True, "vad": False,
                "elapsed_s": round(c_dt, 2),
                "text": c_text, "segments": c_segs,
            },
        })

    OUT_PATH.write_text(json.dumps(diff, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print(f"\n{'=' * 70}")
    print("PHASE 0 DIFF TABLE")
    print(f"{'=' * 70}")
    for d in diff:
        print(f"\n{d['stem']}  ({d['label']})")
        print(f"  base  ({d['baseline']['elapsed_s']:.1f}s):  "
              f"{d['baseline']['text'][:90]}")
        print(f"  v3    ({d['candidate']['elapsed_s']:.1f}s):  "
              f"{d['candidate']['text'][:90]}")


if __name__ == "__main__":
    main()
