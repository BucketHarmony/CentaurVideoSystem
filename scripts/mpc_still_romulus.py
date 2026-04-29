"""
MPC Romulus stills — 5 vertical 1080x1920 still posts from the rally.

Applies the same color grade as the video reels (curves+sat+warm-highlight)
and the still-image rules from feedback_progressive_still_posts.md:
  - Subject eyes on upper third (~y=640 in 1920)
  - Headline 110-140pt stencil all-caps, sub 56-72pt mixed case
  - One thumb-stop per frame (face OR number OR color block)
  - 90/10 saturation pairing (pastel + one magenta accent)
  - WCAG-safe text overlays (magenta stroke or solid scrim)
  - Rapid-response gets timestamp burn + minimal chrome
  - Evergreen quote/stat cards get full brand chrome

Output: E:/AI/CVS/ComfyUI/output/mpc/stills_romulus/*.png
Run:    python E:/AI/CVS/scripts/mpc_still_romulus.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# --------------------------------------------------------------------------- #
# Paths + brand
# --------------------------------------------------------------------------- #

W, H = 1080, 1920

ROOT = Path("E:/AI/CVS/mpc")
BRAND = ROOT / "brand"
RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
OUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc/stills_romulus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
LOGO_PATH = BRAND / "logo_wide_alpha.png"
STENCIL_FONT = "C:/Windows/Fonts/STENCIL.TTF"

BANNER_H = 140
EVENT_DATE = "APR 25, 2026"
EVENT_TIME = "ROMULUS, MI"


# --------------------------------------------------------------------------- #
# Image grade — match the video pipeline (PIL impl, no ffmpeg dependency)
# --------------------------------------------------------------------------- #

def apply_grade(im: Image.Image) -> Image.Image:
    """Approximate the ffmpeg recipe used by the reels:
        curves=preset=medium_contrast, sat 1.20, gamma 0.96, contrast 1.03,
        colorbalance rh=0.04 gh=0.01 bh=-0.03  (warm highlights only)
    Implemented in PIL/numpy — close enough for stills, no ffmpeg roundtrip.
    """
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0

    # gamma 0.96 (slight midtone lift)
    arr = np.power(arr, 0.96)

    # contrast 1.03 around 0.5
    arr = (arr - 0.5) * 1.03 + 0.5

    # mild S-curve (medium_contrast preset analogue)
    arr = arr + 0.06 * np.sin(np.pi * arr) * (0.5 - arr) * -2.0  # subtle

    # warm highlights only — colorbalance rh=+0.04 bh=-0.03 (highlights mask)
    hi = np.clip((arr.mean(axis=2, keepdims=True) - 0.5) * 2.0, 0.0, 1.0)
    arr[..., 0] += 0.04 * hi[..., 0]    # +R in highlights
    arr[..., 1] += 0.01 * hi[..., 0]    # tiny +G
    arr[..., 2] -= 0.03 * hi[..., 0]    # -B in highlights

    arr = np.clip(arr, 0.0, 1.0)

    # saturation 1.20 (HSV-style boost in RGB)
    luma = (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])
    luma3 = luma[..., None]
    arr = luma3 + (arr - luma3) * 1.20
    arr = np.clip(arr, 0.0, 1.0)

    return Image.fromarray((arr * 255.0).astype(np.uint8), "RGB")


# --------------------------------------------------------------------------- #
# Subject framing — load + EXIF-transpose + crop to 9:16 with subject anchor
# --------------------------------------------------------------------------- #

def load_upright(path: Path) -> Image.Image:
    """Load JPEG and apply EXIF orientation transpose (most phone shots
    are stored landscape with rotation=6)."""
    im = Image.open(path).convert("RGB")
    return ImageOps.exif_transpose(im)


def fit_to_well(im: Image.Image, target_w: int, target_h: int,
                *, anchor_y_frac: float = 0.40,
                anchor_x_frac: float = 0.50) -> Image.Image:
    """Scale + crop `im` to exactly (target_w, target_h).

    `anchor_y_frac`: where in the source image the visual anchor (face) is
    located (0=top, 1=bottom). After scaling so that the shorter axis fits,
    the larger axis gets cropped centered on the anchor.

    Default 0.40 puts the face slightly above center in the source — which
    after fit-to-9:16 lands near the upper-third line of the output (rule
    from feedback_progressive_still_posts.md).
    """
    src_w, src_h = im.size
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h
    if src_aspect > target_aspect:
        # source wider than target — fit height, crop width
        new_h = target_h
        new_w = int(round(src_w * (new_h / src_h)))
        im_r = im.resize((new_w, new_h), Image.LANCZOS)
        x_anchor = int(anchor_x_frac * new_w)
        x_left = max(0, min(new_w - target_w, x_anchor - target_w // 2))
        return im_r.crop((x_left, 0, x_left + target_w, target_h))
    else:
        # source taller than target — fit width, crop height
        new_w = target_w
        new_h = int(round(src_h * (new_w / src_w)))
        im_r = im.resize((new_w, new_h), Image.LANCZOS)
        y_anchor = int(anchor_y_frac * new_h)
        y_top = max(0, min(new_h - target_h, y_anchor - target_h // 2))
        return im_r.crop((0, y_top, target_w, y_top + target_h))


# --------------------------------------------------------------------------- #
# Drawing primitives
# --------------------------------------------------------------------------- #

def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def fit_font(path: str, text: str, *, max_w: int, max_size: int,
             min_size: int = 60, draw: ImageDraw.ImageDraw | None = None
             ) -> ImageFont.FreeTypeFont:
    """Largest font in [min_size, max_size] that fits `text` within `max_w`."""
    probe_img = Image.new("RGB", (8, 8))
    d = draw or ImageDraw.Draw(probe_img)
    size = max_size
    while size > min_size:
        fnt = ImageFont.truetype(path, size)
        l, t, r, b = d.textbbox((0, 0), text, font=fnt)
        if (r - l) <= max_w:
            return fnt
        size -= 4
    return ImageFont.truetype(path, min_size)


def text_metrics(draw, txt, fnt):
    l, t, r, b = draw.textbbox((0, 0), txt, font=fnt)
    return r - l, b - t, l, t


def draw_text_centered(draw, text, fnt, x_center, top, fill,
                       stroke_w=0, stroke_fill=None, shadow=None):
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    x = x_center - w // 2 - l
    y = top - t
    if shadow:
        sx, sy, sc = shadow
        draw.text((x + sx, y + sy), text, font=fnt, fill=sc)
    if stroke_w > 0 and stroke_fill is not None:
        draw.text((x, y), text, font=fnt, fill=fill,
                  stroke_width=stroke_w, stroke_fill=stroke_fill)
    else:
        draw.text((x, y), text, font=fnt, fill=fill)
    return (x + l, y + t, x + r, y + b)


def draw_logo_bar(img: Image.Image, *, banner_h: int = BANNER_H,
                  logo_w: int = 560) -> tuple:
    """White logo bar across the top. Returns the bar bbox."""
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, W, banner_h), fill=(*C["white"], 255))
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = logo_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((logo_w, new_h), Image.LANCZOS)
    img.paste(logo, ((W - logo_w) // 2, (banner_h - new_h) // 2), logo)
    return (0, 0, W, banner_h)


def draw_scrim(img: Image.Image, top: int, bot: int, *,
               opacity: int = 180, color=(0, 0, 0)):
    """Draw a horizontal solid scrim band over [top, bot]. Helps text
    legibility over photo content."""
    band = Image.new("RGBA", (W, bot - top), (*color, opacity))
    img.paste(band, (0, top), band)


def draw_gradient_scrim(img: Image.Image, top: int, bot: int, *,
                        top_alpha: int = 0, bot_alpha: int = 220,
                        color=(0, 0, 0)):
    """Vertical gradient scrim — fades from `top_alpha` at `top` to
    `bot_alpha` at `bot`. Used for darkening the lower third without a
    visible band edge."""
    h = bot - top
    band = np.zeros((h, W, 4), dtype=np.uint8)
    band[..., 0] = color[0]
    band[..., 1] = color[1]
    band[..., 2] = color[2]
    alpha_ramp = np.linspace(top_alpha, bot_alpha, h, dtype=np.uint8)
    band[..., 3] = alpha_ramp[:, None]
    img.paste(Image.fromarray(band, "RGBA"), (0, top), Image.fromarray(band, "RGBA"))


def draw_timestamp_burn(img: Image.Image, text: str, *,
                        x: int = 28, y: int = H - 60, size: int = 32):
    """ISO-style timestamp burn for rapid-response stills."""
    draw = ImageDraw.Draw(img, "RGBA")
    fnt = font(FONT_BODY, size)
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    pad = 12
    box = (x - pad, y - pad - t, x + (r - l) + pad - l, y + (b - t) + pad - t)
    bg = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 200))
    img.paste(bg, (box[0], box[1]), bg)
    draw.text((x - l, y - t), text, font=fnt, fill=(*C["white"], 255))


def draw_pill(img: Image.Image, label: str, *, y: int, fnt, color, fill_text):
    draw = ImageDraw.Draw(img, "RGBA")
    l, t, r, b = draw.textbbox((0, 0), label, font=fnt)
    tw, th = r - l, b - t
    pad_x, pad_y = 36, 18
    pill_w, pill_h = tw + pad_x * 2, th + pad_y * 2
    x = (W - pill_w) // 2
    draw.rounded_rectangle((x, y, x + pill_w, y + pill_h),
                           radius=pill_h // 2, fill=(*color, 240))
    draw.text((x + pad_x - l, y + pad_y - t), label, font=fnt, fill=fill_text)
    return (x, y, x + pill_w, y + pill_h)


# --------------------------------------------------------------------------- #
# Card layouts
# --------------------------------------------------------------------------- #

def card_portrait_rapid(src_path: Path, *,
                        anchor_y_frac: float = 0.42,
                        anchor_x_frac: float = 0.50,
                        place_label: str,
                        timestamp: str) -> Image.Image:
    """Rapid-response portrait. Photo full-bleed + subtle bottom gradient
    scrim + place label centered + timestamp burn lower-left. Logo bar top.
    """
    photo = apply_grade(load_upright(src_path))
    canvas = fit_to_well(photo, W, H, anchor_y_frac=anchor_y_frac,
                         anchor_x_frac=anchor_x_frac).convert("RGBA")

    draw_logo_bar(canvas)
    draw_gradient_scrim(canvas, H - 480, H, bot_alpha=200)

    draw = ImageDraw.Draw(canvas, "RGBA")
    fnt_head = fit_font(STENCIL_FONT, place_label, max_w=W - 80,
                        max_size=130, min_size=70, draw=draw)
    draw_text_centered(draw, place_label, fnt_head, W // 2, H - 320,
                       fill=(*C["white"], 255),
                       stroke_w=8, stroke_fill=(*C["deep_magenta"], 255))

    draw_timestamp_burn(canvas, timestamp, x=40, y=H - 50, size=34)
    return canvas.convert("RGB")


def card_stat(src_path: Path, *,
              anchor_y_frac: float = 0.40,
              anchor_x_frac: float = 0.50,
              big_text: str,
              sub_text: str,
              chip_label: str | None = None) -> Image.Image:
    """Stat card. Photo full-bleed but darker scrim + headline + subhead
    in lower third + optional pill chip up top under logo bar.
    """
    photo = apply_grade(load_upright(src_path))
    canvas = fit_to_well(photo, W, H, anchor_y_frac=anchor_y_frac,
                         anchor_x_frac=anchor_x_frac).convert("RGBA")

    draw_logo_bar(canvas)

    # Lower-third heavier scrim for the headline+sub
    draw_gradient_scrim(canvas, H - 600, H, bot_alpha=235)

    draw = ImageDraw.Draw(canvas, "RGBA")
    fnt_head = fit_font(STENCIL_FONT, big_text, max_w=W - 80,
                        max_size=110, min_size=70, draw=ImageDraw.Draw(canvas))
    fnt_sub = fit_font(FONT_HEADLINE, sub_text, max_w=W - 80,
                       max_size=58, min_size=36, draw=ImageDraw.Draw(canvas))

    # Headline near top of scrim
    head_top = H - 470
    head_bbox = draw_text_centered(draw, big_text, fnt_head, W // 2, head_top,
                                   fill=(*C["white"], 255),
                                   stroke_w=6, stroke_fill=(*C["deep_magenta"], 255))
    sub_top = head_bbox[3] + 30
    draw_text_centered(draw, sub_text, fnt_sub, W // 2, sub_top,
                       fill=(*C["soft_pink"], 255),
                       shadow=(3, 3, (0, 0, 0, 220)))

    if chip_label:
        chip_fnt = font(FONT_HEADLINE, 38)
        draw_pill(canvas, chip_label, y=BANNER_H + 28, fnt=chip_fnt,
                  color=C["deep_magenta"], fill_text=(*C["white"], 255))

    return canvas.convert("RGB")


def card_chant(src_path: Path, *,
               anchor_y_frac: float = 0.42,
               anchor_x_frac: float = 0.50,
               line1: str,
               line2: str | None = None) -> Image.Image:
    """Chant card. Photo full-bleed + giant stencil callout overlay near
    lower third (per chant_callout pattern). Used for portrait + slogan.
    """
    photo = apply_grade(load_upright(src_path))
    canvas = fit_to_well(photo, W, H, anchor_y_frac=anchor_y_frac,
                         anchor_x_frac=anchor_x_frac).convert("RGBA")

    draw_logo_bar(canvas)
    draw_gradient_scrim(canvas, H - 540, H, bot_alpha=210)

    draw = ImageDraw.Draw(canvas, "RGBA")
    max_w = W - 80           # 40px side margin minimum
    longest = line1 if not line2 else max([line1, line2], key=len)
    fnt_head = fit_font(STENCIL_FONT, longest, max_w=max_w,
                        max_size=150, min_size=70, draw=draw)
    head_top = H - 420
    bbox = draw_text_centered(draw, line1, fnt_head, W // 2, head_top,
                              fill=(*C["white"], 255),
                              stroke_w=10, stroke_fill=(*C["deep_magenta"], 255))
    if line2:
        bbox2_top = bbox[3] + 20
        draw_text_centered(draw, line2, fnt_head, W // 2, bbox2_top,
                           fill=(*C["soft_pink"], 255),
                           stroke_w=10, stroke_fill=(*C["deep_magenta"], 255))
    return canvas.convert("RGB")


def card_chalk_rapid(src_path: Path, *, timestamp: str) -> Image.Image:
    """Rapid-response chalk close-up. No big headline — just the chalk and
    a timestamp burn. Minimal chrome (no logo bar, just a small mark) per
    rapid-response convention."""
    photo = apply_grade(load_upright(src_path))
    canvas = fit_to_well(photo, W, H, anchor_y_frac=0.50,
                         anchor_x_frac=0.50).convert("RGBA")

    # Tiny logo mark in upper-right (not full bar — rapid-response feel)
    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_w = 280
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    pad = 24
    # White rounded plate behind so the logo reads on any background
    plate_w, plate_h = target_w + 2 * pad, new_h + 2 * pad
    plate = Image.new("RGBA", (plate_w, plate_h), (255, 255, 255, 235))
    canvas.paste(plate, (W - plate_w - 24, 24), plate)
    canvas.paste(logo, (W - target_w - 24 - pad, 24 + pad), logo)

    draw_timestamp_burn(canvas, timestamp, x=40, y=H - 50, size=36)
    return canvas.convert("RGB")


# --------------------------------------------------------------------------- #
# 5 picks
# --------------------------------------------------------------------------- #

STILLS = [
    {
        "out": "01_we_were_there.png",
        "type": "portrait_rapid",
        "src": RAW_DIR / "20260425_160015.jpg",        # Detroit Caucus crew
        "anchor_y": 0.38, "anchor_x": 0.50,
        "place_label": "ROMULUS, MI",
        "timestamp": "APR 25, 2026  |  4:00 PM",
    },
    {
        "out": "02_dhs_warehouse.png",
        "type": "stat",
        "src": RAW_DIR / "20260425_162056.jpg",        # speaker + warehouse
        "anchor_y": 0.32, "anchor_x": 0.50,
        "big_text": "DHS WAREHOUSE",
        "sub_text": "7525 Cogswell Rd  -  Romulus",
        "chip_label": "INJUNCTION HEARING - MAY 18",
    },
    {
        "out": "03_for_our_neighbors.png",
        "type": "chant",
        "src": RAW_DIR / "20260425_153513.jpg",        # 3 women portrait
        "anchor_y": 0.36, "anchor_x": 0.50,
        "line1": "WE MARCH",
        "line2": "FOR OUR NEIGHBORS",
    },
    {
        "out": "04_dont_back_down.png",
        "type": "chant",
        "src": RAW_DIR / "20260425_160807.jpg",        # couple raised fist
        "anchor_y": 0.42, "anchor_x": 0.45,
        "line1": "WE DON'T",
        "line2": "BACK DOWN",
    },
    {
        "out": "05_chalk.png",
        "type": "chalk_rapid",
        "src": RAW_DIR / "20260425_171312.jpg",        # sidewalk chalk
        "timestamp": "ROMULUS  |  APR 25  |  5:13 PM",
    },
]


def render_one(spec: dict) -> Path:
    out = OUT_DIR / spec["out"]
    print(f"[still] {spec['type']:14s} {spec['src'].name} -> {out.name}")
    if spec["type"] == "portrait_rapid":
        im = card_portrait_rapid(
            spec["src"],
            anchor_y_frac=spec["anchor_y"], anchor_x_frac=spec["anchor_x"],
            place_label=spec["place_label"], timestamp=spec["timestamp"])
    elif spec["type"] == "stat":
        im = card_stat(
            spec["src"],
            anchor_y_frac=spec["anchor_y"], anchor_x_frac=spec["anchor_x"],
            big_text=spec["big_text"], sub_text=spec["sub_text"],
            chip_label=spec.get("chip_label"))
    elif spec["type"] == "chant":
        im = card_chant(
            spec["src"],
            anchor_y_frac=spec["anchor_y"], anchor_x_frac=spec["anchor_x"],
            line1=spec["line1"], line2=spec.get("line2"))
    elif spec["type"] == "chalk_rapid":
        im = card_chalk_rapid(spec["src"], timestamp=spec["timestamp"])
    else:
        raise ValueError(f"unknown type: {spec['type']}")
    im.save(out, format="PNG", optimize=True)
    return out


def main():
    print(f"Building {len(STILLS)} MPC Romulus stills -> {OUT_DIR}")
    paths = [render_one(s) for s in STILLS]
    print("\nDone:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
