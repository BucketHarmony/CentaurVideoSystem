"""Single-clip scanner CLI — primary entry for `cvs_lib.scanner`.

Defaults reflect Phase 0 findings: large-v3, vad off, vocab prompt
auto-resolved from `mpc/scanner_prompts.json` by source folder name,
word timestamps on.

Usage:
    python scripts/scan.py "E:/AI/CVS/raw/MPC/Ice Out Romulus/20260425_170245.mp4"
    python scripts/scan.py <video> --out E:/AI/CVS/mpc/index/clips
    python scripts/scan.py <video> --whisper-model medium --vad
    python scripts/scan.py <video> --prompt "Detroit. Romulus. ICE."
    python scripts/scan.py <video> --no-thumbnails

The script writes:
    <out>/<stem>.json
    <out>/../thumbnails/<stem>_s<idx>_t<t>.jpg   (unless --no-thumbnails)

For batch + DB indexing of an entire source folder, use
`scripts/mpc_scan_sources.py` which calls into `cvs_lib.scanner`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cvs_lib import scanner


DEFAULT_OUT_DIR = Path("E:/AI/CVS/mpc/index/clips")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="Path to a video file")
    ap.add_argument("--out", default=str(DEFAULT_OUT_DIR),
                    help="Directory for the per-clip JSON")
    ap.add_argument("--no-thumbnails", action="store_true",
                    help="Skip JPG extraction (faster; index records scene t only)")
    ap.add_argument("--whisper-model", default="large-v3",
                    help="tiny | base | small | medium | large-v3 (default: large-v3)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16",
                    help="float16 | int8_float16 | int8 (use int8 on cpu)")
    ap.add_argument("--vad", action="store_true",
                    help="Enable VAD filter (default off — VAD drops sung content)")
    ap.add_argument("--prompt",
                    help="Explicit initial_prompt override. If absent, the "
                         "prompt is auto-resolved from the video's parent "
                         "folder via mpc/scanner_prompts.json.")
    ap.add_argument("--prompts-path", default=str(scanner.DEFAULT_PROMPTS_PATH),
                    help="Path to scanner_prompts.json")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"ERROR: {video} does not exist", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir = None if args.no_thumbnails else out_dir.parent / "thumbnails"

    print(f"Scanning {video.name}...")
    print(f"  whisper: {args.whisper_model} on {args.device}/{args.compute_type}")
    model = scanner.load_whisper(args.whisper_model, args.device, args.compute_type)

    record = scanner.scan_clip(
        video, model,
        thumbnails_dir=thumbs_dir,
        initial_prompt=args.prompt,
        vad=args.vad,
        prompts_path=args.prompts_path,
        verbose=True,
    )

    out_path = out_dir / f"{video.stem}.json"
    out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    text = record["transcript"]["text"]
    preview = text[:90] + (" …" if len(text) > 90 else "")
    print(f"\n  text:    {preview!r}")
    print(f"  tags:    {', '.join(record['tags']) or '—'}")
    print(f"  scenes:  {len(record['scenes'])}")
    print(f"  wrote:   {out_path}")


if __name__ == "__main__":
    main()
