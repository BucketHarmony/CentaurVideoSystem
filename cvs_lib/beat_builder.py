"""One-shot beat builder CLI.

Renders a single MPC-style beat (chip + chrome + caption strip + footage)
to an mp4 in ~60 seconds. Useful for rapid prototyping a beat before
committing it to a full reel script.

Usage:
    python -m cvs_lib.beat_builder \\
        --source "E:/AI/CVS/raw/MPC/Ice Out Romulus/20260425_155313.mp4" \\
        --in-t 13 --out-t 20 \\
        --chip "RELEASED" \\
        --caption "I was released Friday — April 24." \\
        --out E:/AI/CVS/ComfyUI/output/mpc/_beat.mp4

Output is a vertical 1080x1920 mp4 at 30 fps with the standard MPC
chrome (top logo bar, bottom caption strip, side chip). Brand colors
come from `mpc/brand/palette.json`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cvs_lib.captions import render_caption_strip
from cvs_lib.mpc_chrome import ChromeRenderer, Layout, load_palette
from cvs_lib.moviepy_helpers import build_beat_clip


DEFAULT_BRAND = Path("E:/AI/CVS/mpc/brand")
DEFAULT_OUT = Path("E:/AI/CVS/ComfyUI/output/mpc/_beat.mp4")
DEFAULT_ROT_CACHE = Path("E:/AI/CVS/ComfyUI/output/mpc/_rot_cache")


def _build_layout() -> Layout:
    return Layout(
        BANNER_H=140, WELL_TOP=140, WELL_H=1750 - 140,
        CAPTION_BOTTOM=1620, CHIP_Y=168,
        CTA_CHROME_BOTTOM=720, CTA_WELL_TOP=720,
    )


def _composite_caption(beat_clip, caption_text: str, *,
                       width: int, caption_bottom: int, font_path: str):
    """Overlay a caption strip on the beat clip for its full duration."""
    import numpy as np
    from moviepy.editor import CompositeVideoClip, ImageClip

    rgba = render_caption_strip(caption_text, width=width, font_path=font_path)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    dur = beat_clip.duration
    cap = ImageClip(rgb).set_duration(dur)
    cap = cap.set_mask(ImageClip(alpha, ismask=True).set_duration(dur))
    cap = cap.set_position((0, caption_bottom - rgba.shape[0]))
    cap = cap.crossfadein(min(0.12, dur / 4))
    return CompositeVideoClip([beat_clip, cap], size=beat_clip.size).set_duration(dur)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cvs_lib.beat_builder",
                                description="Render one MPC beat to an mp4.")
    p.add_argument("--source", required=True, help="Source video path")
    p.add_argument("--in-t", type=float, required=True, dest="in_t",
                   help="In-point (seconds) in the source")
    p.add_argument("--out-t", type=float, required=True, dest="out_t",
                   help="Out-point (seconds) in the source")
    p.add_argument("--chip", default="", help="Chip label (top-right banner)")
    p.add_argument("--caption", default="", help="Caption strip text")
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help="Output mp4 path (default: %(default)s)")
    p.add_argument("--brand-dir", default=str(DEFAULT_BRAND),
                   help="Brand directory (palette.json + logo). Default: %(default)s")
    p.add_argument("--rotation-cache-dir", default=str(DEFAULT_ROT_CACHE),
                   help="Rotation-bake cache dir. Default: %(default)s")
    p.add_argument("--fps", type=int, default=30)
    args = p.parse_args(argv)

    brand = Path(args.brand_dir)
    palette_path = brand / "palette.json"
    logo_path = str(brand / "logo_wide_alpha.png")
    if not palette_path.exists():
        print(f"[beat_builder] missing palette: {palette_path}", file=sys.stderr)
        return 1

    palette = load_palette(palette_path)
    layout = _build_layout()
    chrome = ChromeRenderer(
        palette=palette,
        font_headline=palette["fonts"]["headline"]["path"],
        font_body=palette["fonts"]["body"]["path"],
        logo_path=logo_path,
        layout=layout,
    )
    chrome_rgba = chrome.render_beat(
        chip_label=args.chip, well_transparent=True,
    )

    duration = float(args.out_t) - float(args.in_t)
    spec = {"path": args.source, "in_t": args.in_t, "out_t": args.out_t}
    rot_cache = Path(args.rotation_cache_dir)
    rot_cache.mkdir(parents=True, exist_ok=True)

    print(f"[beat_builder] source={args.source} t={args.in_t}..{args.out_t} "
          f"({duration:.2f}s) chip={args.chip!r}")
    clip = build_beat_clip(
        chrome_rgba=chrome_rgba,
        footage_spec=spec,
        duration=duration,
        W=layout.W, H=layout.H,
        well_top=layout.WELL_TOP, well_h=layout.WELL_H,
        rotation_cache_dir=rot_cache,
    )
    if args.caption:
        clip = _composite_caption(
            clip, args.caption,
            width=layout.W, caption_bottom=layout.CAPTION_BOTTOM,
            font_path=palette["fonts"]["headline"]["path"],
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[beat_builder] writing {out}")
    clip.write_videofile(
        str(out),
        fps=args.fps,
        codec="libx264",
        preset="medium",
        bitrate="8M",
        audio=False,
        threads=4,
    )
    print(f"[beat_builder] done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
