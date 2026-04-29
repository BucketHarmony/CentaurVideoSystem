"""Cover thumbnail extraction + overlay for posted reels.

A cover is a single 1080x1920 PNG extracted from a rendered reel,
optionally with an overlay headline that doesn't appear in the video
itself. TikTok/IG default a video's first frame as the thumbnail; a
custom cover at the strongest editorial moment with a punched-up
hook headline lifts feed-grid stop-rate.

Two primitives:
  extract_frame(video, t, out)  — ffmpeg seek+extract, no overlay
  make_cover(video, ..., headline=...)  — extract + optional overlay

The overlay primitives mirror `mpc_still_romulus.py` so cover styling
stays consistent with the still-image card pattern (stencil headline,
magenta stroke, gradient scrim).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def extract_frame(video_path: Path, t_seek: float, out_path: Path) -> Path:
    """ffmpeg seek+extract one frame to PNG. Uses fast input-seek (-ss before
    -i) which is frame-imprecise but ~10x faster than output-seek; for a
    cover thumbnail, ±1 frame is fine.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{t_seek:.3f}", "-i", str(video_path),
        "-frames:v", "1",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _fit_font(font_path: str, text: str, *, max_w: int,
              max_size: int, min_size: int = 60) -> ImageFont.FreeTypeFont:
    probe_img = Image.new("RGB", (8, 8))
    d = ImageDraw.Draw(probe_img)
    size = max_size
    while size > min_size:
        fnt = ImageFont.truetype(font_path, size)
        l, _, r, _ = d.textbbox((0, 0), text, font=fnt)
        if (r - l) <= max_w:
            return fnt
        size -= 4
    return ImageFont.truetype(font_path, min_size)


def _draw_text_centered(draw, text, fnt, x_center, top, fill,
                        stroke_w=0, stroke_fill=None):
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w = r - l
    x = x_center - w // 2 - l
    y = top - t
    if stroke_w > 0 and stroke_fill is not None:
        draw.text((x, y), text, font=fnt, fill=fill,
                  stroke_width=stroke_w, stroke_fill=stroke_fill)
    else:
        draw.text((x, y), text, font=fnt, fill=fill)
    return (x + l, y + t, x + r, y + b)


def _draw_gradient_scrim(img: Image.Image, top: int, bot: int, *,
                         top_alpha: int = 0, bot_alpha: int = 220,
                         color: Tuple[int, int, int] = (0, 0, 0)):
    h = bot - top
    w = img.width
    band = np.zeros((h, w, 4), dtype=np.uint8)
    band[..., 0] = color[0]
    band[..., 1] = color[1]
    band[..., 2] = color[2]
    band[..., 3] = np.linspace(top_alpha, bot_alpha, h, dtype=np.uint8)[:, None]
    band_im = Image.fromarray(band, "RGBA")
    img.paste(band_im, (0, top), band_im)


def make_cover(
    video_path: Path,
    out_path: Path,
    *,
    t_seek: float,
    headline: Optional[str] = None,
    sub: Optional[str] = None,
    stencil_font: str = "C:/Windows/Fonts/STENCIL.TTF",
    sub_font: str = "C:/Windows/Fonts/arialbd.ttf",
    headline_y_frac: float = 0.62,
    headline_color: Tuple[int, int, int] = (255, 255, 255),
    stroke_color: Tuple[int, int, int] = (139, 58, 82),  # MPC deep_magenta
    sub_color: Tuple[int, int, int] = (250, 197, 213),   # MPC soft_pink
    headline_max_size: int = 160,
    sub_max_size: int = 64,
    scrim: bool = True,
) -> Path:
    """Extract `video_path` at `t_seek` and write a cover PNG to `out_path`.

    If `headline` is provided, an additional stencil overlay is drawn near
    `headline_y_frac` (0..1, fraction of frame height for the headline's
    vertical center). A bottom gradient scrim is drawn first so any
    headline lands on legible darkness regardless of underlying photo.

    `out_path` is the final PNG path. A temp `*_raw.png` is written
    alongside and removed after composition.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out_path.with_name(out_path.stem + "_raw.png")
    extract_frame(video_path, t_seek, raw_path)

    im = Image.open(raw_path).convert("RGBA")
    W = im.width

    if headline:
        if scrim:
            scrim_top = int(im.height * (headline_y_frac - 0.18))
            _draw_gradient_scrim(im, scrim_top, im.height,
                                 top_alpha=0, bot_alpha=215)
        draw = ImageDraw.Draw(im, "RGBA")
        fnt_head = _fit_font(stencil_font, headline,
                             max_w=W - 100, max_size=headline_max_size,
                             min_size=80)
        head_y_center = int(im.height * headline_y_frac)
        # textbbox top corresponds to roughly y_center - h/2; pick top such
        # that the visual centerline lands near head_y_center.
        l, t, r, b = draw.textbbox((0, 0), headline, font=fnt_head)
        head_top = head_y_center - (b - t) // 2
        head_bbox = _draw_text_centered(
            draw, headline, fnt_head, W // 2, head_top,
            fill=(*headline_color, 255),
            stroke_w=10, stroke_fill=(*stroke_color, 255),
        )
        if sub:
            fnt_sub = _fit_font(sub_font, sub,
                                max_w=W - 120, max_size=sub_max_size,
                                min_size=32)
            sub_top = head_bbox[3] + 24
            _draw_text_centered(
                draw, sub, fnt_sub, W // 2, sub_top,
                fill=(*sub_color, 255),
                stroke_w=4, stroke_fill=(*stroke_color, 255),
            )

    im.convert("RGB").save(out_path, format="PNG", optimize=True)
    raw_path.unlink(missing_ok=True)
    return out_path
