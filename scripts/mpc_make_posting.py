"""Emit <reel>.posting.md sidecar next to each rendered MPC reel.

Reads `output/mpc/manifest.json` (from `scripts/mpc_render_all.py`)
plus AST-parses each reel's source script for docstring + CTA
constants, then writes a posting markdown to `<reel>.posting.md`
alongside the .mp4. Optionally dry-run to stdout.

Output sidecars contain: file/cover paths + sizes, synopsis, suggested
caption, brand+reel hashtags, accessibility alt-text, and a
per-platform posting checklist (TikTok / Instagram / Bluesky / Facebook).

Run:
    python scripts/mpc_make_posting.py
    python scripts/mpc_make_posting.py --reel north_lake
    python scripts/mpc_make_posting.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cvs_lib.posting import build_meta, render_posting_md


MANIFEST_PATH = REPO / "ComfyUI" / "output" / "mpc" / "manifest.json"
CTA_CONFIG_PATH = REPO / "mpc" / "cta.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mpc_make_posting.py",
        description="Emit posting markdown sidecars for rendered MPC reels.",
    )
    ap.add_argument("--manifest", default=str(MANIFEST_PATH),
                    help="Path to mpc_render_all.py's manifest.json.")
    ap.add_argument("--cta-config", default=str(CTA_CONFIG_PATH))
    ap.add_argument("--reel", action="append", default=None,
                    help="Restrict to these reel slugs (repeatable). "
                         "Slug = the part after `mpc_ep_` in the script "
                         "stem, e.g. `north_lake`.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print to stdout instead of writing sidecars.")
    args = ap.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    cta_config = None
    cta_path = Path(args.cta_config)
    if cta_path.exists():
        cta_config = json.loads(cta_path.read_text(encoding="utf-8"))

    reels = manifest.get("reels", [])
    if not reels:
        print("manifest has no reels")
        return 1

    written = skipped = 0
    for entry in reels:
        if not entry.get("rendered"):
            continue
        script_rel = entry.get("script")
        if not script_rel:
            continue
        script_path = REPO / script_rel
        if not script_path.exists():
            print(f"  ! {script_rel}: source missing, skipping")
            continue
        slug = script_path.stem.replace("mpc_ep_", "")
        if args.reel and slug not in args.reel:
            skipped += 1
            continue

        meta = build_meta(script_path, entry, cta_config=cta_config)
        md = render_posting_md(meta)

        if args.dry_run:
            print(f"\n===== {slug} =====")
            print(md)
            written += 1
            continue

        output_rel = entry.get("output")
        if not output_rel:
            print(f"  ! {slug}: no output path in manifest, skipping")
            continue
        output_path = REPO / output_rel
        sidecar = output_path.with_suffix(".posting.md")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(md, encoding="utf-8")
        size_kb = sidecar.stat().st_size // 1024
        print(f"  -> {sidecar.relative_to(REPO).as_posix()}  ({size_kb} KB)")
        written += 1

    print()
    if args.dry_run:
        print(f"Dry run: {written} sidecar(s) would be written, {skipped} skipped.")
    else:
        print(f"Wrote {written} sidecar(s); {skipped} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
