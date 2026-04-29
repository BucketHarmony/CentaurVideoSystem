"""Rally scout dashboard: browse an indexed pipeline as markdown.

Reads `<pipeline>/index/clips/*.json` and emits one `<stem>.md` per
clip plus an `_index.md` linking them all. Pairs with
`scripts/find_phrase.py`: that's "search for X", this is "browse
everything". Output lives at
`output/<pipeline>/_scout/<rally_slug>/`.

Pure rendering lives in `cvs_lib/scout.py` — this file is just the
walk + write driver.

Examples:
    python scripts/scout_dashboard.py
    python scripts/scout_dashboard.py --pipeline mpc --rally "Ice Out Romulus"
    python scripts/scout_dashboard.py --stem 20260425_155313  # one clip only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cvs_lib.index import load_clip_index
from cvs_lib.scout import render_index_page, render_stem_page


PIPELINE_DEFAULTS = {
    "mpc": {
        "index_dir": REPO / "mpc" / "index" / "clips",
        "out_root": REPO / "ComfyUI" / "output" / "mpc",
        "default_rally": "Ice Out Romulus",
    },
    "cc_flora": {
        "index_dir": REPO / "cc_flora" / "index" / "clips",
        "out_root": REPO / "ComfyUI" / "output" / "cc_flora",
        "default_rally": "season",
    },
    "cc_hookshot": {
        "index_dir": REPO / "cc_hookshot" / "index" / "clips",
        "out_root": REPO / "ComfyUI" / "output" / "cc_hookshot",
        "default_rally": "default",
    },
}


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "rally"


def discover_stems(index_dir: Path) -> list:
    return sorted(
        p.stem for p in index_dir.glob("*.json")
        if not p.stem.startswith("_")
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="scout_dashboard.py",
        description="Markdown dashboard for an indexed pipeline.",
    )
    ap.add_argument("--pipeline", default="mpc",
                    choices=sorted(PIPELINE_DEFAULTS.keys()))
    ap.add_argument("--rally", default=None,
                    help="Rally name (drives the output folder; "
                         "default: pipeline default).")
    ap.add_argument("--index-dir", default=None,
                    help="Override the pipeline's default index dir.")
    ap.add_argument("--out-dir", default=None,
                    help="Override the output directory.")
    ap.add_argument("--stem", action="append", default=None,
                    help="Restrict to these stems (repeatable). Default: all.")
    ap.add_argument("--scene-limit", type=int, default=12)
    ap.add_argument("--motion-top-n", type=int, default=5)
    ap.add_argument("--max-segment-chars", type=int, default=0,
                    help="Truncate transcript segments at N chars "
                         "(0 = no truncation).")
    args = ap.parse_args(argv)

    defaults = PIPELINE_DEFAULTS[args.pipeline]
    index_dir = Path(args.index_dir) if args.index_dir else defaults["index_dir"]
    rally = args.rally or defaults["default_rally"]
    out_dir = (
        Path(args.out_dir) if args.out_dir
        else defaults["out_root"] / "_scout" / slugify(rally)
    )

    if not index_dir.exists():
        print(f"index dir not found: {index_dir}")
        return 1

    stems = args.stem if args.stem else discover_stems(index_dir)
    if not stems:
        print(f"no stems in {index_dir}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Rendering {len(stems)} stem(s) -> {out_dir}")

    entries = []
    for stem in stems:
        try:
            data = load_clip_index(stem, index_dir)
        except FileNotFoundError:
            print(f"  ! {stem}: index entry missing, skipping")
            continue
        page = render_stem_page(
            stem, data,
            thumbs_relative_to=out_dir,
            scene_limit=args.scene_limit,
            motion_top_n=args.motion_top_n,
            max_segment_chars=args.max_segment_chars,
        )
        page_path = out_dir / f"{stem}.md"
        page_path.write_text(page, encoding="utf-8")
        entries.append((stem, data))

    if entries:
        index_md = render_index_page(
            f"{rally} — scout dashboard",
            entries,
        )
        (out_dir / "_index.md").write_text(index_md, encoding="utf-8")
        print(f"  wrote {len(entries)} stem pages + _index.md")
    else:
        print("  no pages written")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
