"""Cross-rally phrase search: find every utterance, snap-cut it, audition.

Editorial accelerator. Given a phrase and a pipeline (mpc / cc_flora /
cc_hookshot — anywhere a `<pipeline>/index/clips/*.json` lives), walk
every indexed stem, locate the phrase via word_index + clip_snap, and
print an SNR-sorted table showing where every utterance lives. With
`--audition`, ffmpeg-cut each result into
`output/<pipeline>/_audition/<phrase_slug>/NN_<stem>.mp4` so the
editorial review is "open the folder, listen / look".

Reuses the WordIndex cache inside `cvs_lib.clip_locator` so a 30-stem
search runs in roughly the time of one silero load (~5s) plus a
quick per-stem snap pass.

Examples:
    python scripts/find_phrase.py "abolish ICE"
    python scripts/find_phrase.py "abolish ICE" --audition
    python scripts/find_phrase.py "two hundred million" --keep-off-mic
    python scripts/find_phrase.py "$254 million" --pipeline mpc \\
        --raw-dir "E:/AI/CVS/raw/MPC/Ice Out Romulus" --audition
    python scripts/find_phrase.py "abolish ICE" --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cvs_lib.clip_cut import cut_clip
from cvs_lib.clip_locator import (
    DEFAULT_RAW_DIR,
    locate_phrase_across_stems,
)
from cvs_lib.clip_snap import (
    DEFAULT_LEAD_PAD_MS,
    DEFAULT_MIN_SNR_DB,
    DEFAULT_SEARCH_MS,
    DEFAULT_TRAIL_PAD_MS,
)


# Default raw-dir per pipeline. Override with --raw-dir when the rally
# lives elsewhere; the index-dir is `<pipeline>/index/clips/` by
# convention.
PIPELINE_DEFAULTS = {
    "mpc": {
        "index_dir": REPO / "mpc" / "index" / "clips",
        "raw_dir": DEFAULT_RAW_DIR,  # current rally — override per-rally
        "out_root": REPO / "ComfyUI" / "output" / "mpc",
    },
    "cc_flora": {
        "index_dir": REPO / "cc_flora" / "index" / "clips",
        "raw_dir": REPO / "raw" / "cc_flora",
        "out_root": REPO / "ComfyUI" / "output" / "cc_flora",
    },
    "cc_hookshot": {
        "index_dir": REPO / "cc_hookshot" / "index" / "clips",
        "raw_dir": REPO / "raw" / "cc_hookshot",
        "out_root": REPO / "ComfyUI" / "output" / "cc_hookshot",
    },
}


def slugify(s: str) -> str:
    """Filesystem-safe phrase slug: lowercase, alnums + underscores."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s[:60] or "phrase"


def discover_stems(index_dir: Path) -> list:
    """Every `<stem>.json` in the index dir, leading-underscore files
    excluded (those are auxiliaries: `_song_*`, etc.)."""
    if not index_dir.exists():
        raise SystemExit(f"index dir not found: {index_dir}")
    return sorted(
        p.stem for p in index_dir.glob("*.json")
        if not p.stem.startswith("_")
    )


def print_table(results: list) -> None:
    if not results:
        print("  (no matches)")
        return
    print(f"  {'#':>2}  {'stem':<18}  {'in_t':>7}  {'dur':>5}  "
          f"{'SNR':>6}  {'score':>5}  flag       text")
    for i, r in enumerate(results, 1):
        flag = ""
        if r.is_off_mic:
            flag = "OFF-MIC"
        elif r.in_voice or r.out_voice:
            flag = "VOICE-EDGE"
        text = r.matched_text[:60] + ("..." if len(r.matched_text) > 60 else "")
        print(
            f"  {i:>2}  {r.stem:<18}  {r.in_t:>7.3f}  "
            f"{r.duration:>5.2f}  {r.snr_db:>+6.1f}  "
            f"{r.match_score:>5.2f}  {flag:<10} {text!r}"
        )


def audition_cuts(results: list, out_dir: Path) -> Path:
    """ffmpeg-cut each result into `out_dir/NN_<stem>.mp4` (HDR-aware
    via cvs_lib.clip_cut). Writes a manifest alongside."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, r in enumerate(results, 1):
        name = f"{i:02d}_{r.stem}.mp4"
        dst = out_dir / name
        try:
            elapsed = cut_clip(r.path, r.in_t, r.out_t, dst)
            size_kb = dst.stat().st_size // 1024
            print(f"  -> {name}  ({size_kb} KB, {elapsed:.1f}s)")
            manifest.append({
                "n": i,
                "stem": r.stem,
                "matched_text": r.matched_text,
                "in_t": round(r.in_t, 3),
                "out_t": round(r.out_t, 3),
                "duration": round(r.duration, 3),
                "snr_db": round(r.snr_db, 1),
                "match_score": round(r.match_score, 2),
                "is_off_mic": r.is_off_mic,
                "output": name,
                "size_kb": size_kb,
            })
        except Exception as e:
            print(f"  !! {name}  ffmpeg failed: {e}")
            manifest.append({
                "n": i, "stem": r.stem, "output": None, "error": str(e),
            })
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="find_phrase.py",
        description="Find every utterance of a phrase across an indexed pipeline.",
    )
    ap.add_argument("phrase", help="Phrase to locate (case-insensitive).")
    ap.add_argument("--pipeline", default="mpc",
                    choices=sorted(PIPELINE_DEFAULTS.keys()))
    ap.add_argument("--index-dir", default=None,
                    help="Override the pipeline's default index dir.")
    ap.add_argument("--raw-dir", default=None,
                    help="Override where the source videos live.")
    ap.add_argument("--stem", action="append", default=None,
                    help="Restrict search to these stems (repeatable).")
    ap.add_argument("--exact", action="store_true",
                    help="Disable fuzzy matching.")
    ap.add_argument("--min-score", type=float, default=0.6)
    ap.add_argument("--lead-pad-ms", type=float, default=DEFAULT_LEAD_PAD_MS)
    ap.add_argument("--trail-pad-ms", type=float, default=DEFAULT_TRAIL_PAD_MS)
    ap.add_argument("--search-ms", type=float, default=DEFAULT_SEARCH_MS)
    ap.add_argument("--min-snr-db", type=float, default=DEFAULT_MIN_SNR_DB)
    ap.add_argument("--keep-off-mic", action="store_true",
                    help="Show off-mic matches in the table (still cut "
                         "during --audition unless --skip-off-mic).")
    ap.add_argument("--skip-off-mic", action="store_true",
                    help="Filter off-mic matches out of results.")
    ap.add_argument("--top", type=int, default=0,
                    help="Limit to top N results (0 = all).")
    ap.add_argument("--audition", action="store_true",
                    help="ffmpeg-cut every match into "
                         "output/<pipeline>/_audition/<phrase_slug>/.")
    ap.add_argument("--json", action="store_true",
                    help="Emit beat-ready dicts as JSON instead of a table.")
    args = ap.parse_args(argv)

    defaults = PIPELINE_DEFAULTS[args.pipeline]
    index_dir = Path(args.index_dir) if args.index_dir else defaults["index_dir"]
    raw_dir = Path(args.raw_dir) if args.raw_dir else defaults["raw_dir"]
    out_root = defaults["out_root"]

    stems = args.stem if args.stem else discover_stems(index_dir)
    if not stems:
        print(f"  no stems found in {index_dir}")
        return 1

    print(f"Searching {len(stems)} stem(s) for {args.phrase!r}  "
          f"(pipeline={args.pipeline}, index={index_dir})")

    results = locate_phrase_across_stems(
        args.phrase, stems,
        raw_dir=raw_dir, index_dir=index_dir,
        fuzzy=not args.exact,
        min_score=args.min_score,
        lead_pad_ms=args.lead_pad_ms,
        trail_pad_ms=args.trail_pad_ms,
        search_ms=args.search_ms,
        min_snr_db=args.min_snr_db,
        skip_off_mic=args.skip_off_mic,
    )

    if not args.keep_off_mic and not args.skip_off_mic:
        # Default view: keep off-mic in the table but flag them; sorted
        # so they sink. The CLI passes skip_off_mic=False and the sort
        # already puts off-mic last by SNR.
        pass

    if args.top > 0:
        results = results[:args.top]

    if args.json:
        print(json.dumps(
            [r.to_beat_dict() for r in results], indent=2,
        ))
    else:
        print_table(results)

    if args.audition and results:
        audition_dir = out_root / "_audition" / slugify(args.phrase)
        print()
        print(f"Auditioning {len(results)} cut(s) -> {audition_dir}")
        manifest_path = audition_cuts(results, audition_dir)
        print(f"Manifest: {manifest_path}")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
