"""
MPC 30s brand-fit demo template (v2).

Renders a 30-second 1080x1920 vertical video that exercises the Michigan
Progressive Caucus brand kit: palette, fonts, logo placement, lower-thirds,
captions, and safe-zone respect. Uses no source footage — pure synthesis —
so we can validate brand styling before the full pipeline lands.

v2 changes:
  - Vertical text auto-flow (no more hardcoded-y collisions)
  - Bullet vertical-center alignment fix
  - Transparent (knocked-out) logo — no white box
  - Audio bed: ambient pad + transition stings + ElevenLabs narration

Output: E:/AI/CVS/ComfyUI/output/mpc/template_30s_demo.mp4

Run:
    python E:/AI/CVS/mpc/templates/template_30s_demo.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)

# Allow `import audio_demo` even when run from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_demo  # noqa: E402

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

W, H = 1080, 1920
FPS = 30
DURATION = 30.0

ROOT = Path(__file__).resolve().parent.parent          # mpc/
BRAND = ROOT / "brand"
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "template_30s_demo.mp4"

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
# Use the alpha-knockout version (no white box around the bird)
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")
SAFE = PALETTE["safe_zones_1080x1920"]

# --------------------------------------------------------------------------- #
# PIL helpers
# --------------------------------------------------------------------------- #

def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_HEADLINE if bold else FONT_BODY
    return ImageFont.truetype(path, size)


def text_size(draw: ImageDraw.ImageDraw, txt: str, fnt) -> tuple[int, int]:
    l, t, r, b = draw.textbbox((0, 0), txt, font=fnt)
    return r - l, b - t


def wrap(draw, text: str, fnt, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_size(draw, trial, fnt)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def gradient_bg(c1: tuple, c2: tuple, angle_deg: float = 135.0) -> np.ndarray:
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    proj = xx * dx + yy * dy
    proj = (proj - proj.min()) / (proj.max() - proj.min())
    img = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(3):
        img[..., i] = (c1[i] * (1 - proj) + c2[i] * proj).astype(np.uint8)
    return img


def solid_bg(color: tuple) -> np.ndarray:
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = color
    return img


# --------------------------------------------------------------------------- #
# Layout engine
# --------------------------------------------------------------------------- #
#
# Blocks render sequentially. Each block can specify:
#   y       : absolute pixel y (resets cursor)
#   y       : None / omitted → auto-flow (place at cursor + gap_before)
#   gap_before, gap_after : extra vertical spacing
#
# Block kinds:
#   { "kind": "text", "text", "size", "color", "bold"?, "align"?, "shadow"?,
#     "max_w"?, "y"?, "gap_before"?, "gap_after"? }
#   { "kind": "rect", "xywh", "color", "radius"?, "alpha"? }
#   { "kind": "underline", "w", "h", "color", "y"?, "gap_before"?, "gap_after"? }
#   { "kind": "spacer", "h" }
#   { "kind": "logo", "w", "y"?, "gap_before"?, "gap_after"? }
#   { "kind": "lower_third", "name", "subtitle", "y"?, "h"?, "color"? }
#
# --------------------------------------------------------------------------- #

def _draw_text_block(draw, b, cursor_y: int, content_box) -> int:
    """Returns new cursor_y after rendering the text block."""
    cx0, _, cx1, _ = content_box
    content_w = cx1 - cx0
    fnt = font(b["size"], bold=b.get("bold", True))
    color = (*b["color"], 255)
    shadow = b.get("shadow")
    align = b.get("align", "center")
    max_w = b.get("max_w", content_w)
    lines = wrap(draw, b["text"], fnt, max_w)
    line_h = int(b["size"] * 1.15)

    y = b["y"] if b.get("y") is not None else cursor_y + b.get("gap_before", 0)

    for i, line in enumerate(lines):
        tw, _ = text_size(draw, line, fnt)
        if align == "center":
            x = (W - tw) // 2
        else:
            x = b.get("x", cx0)
        yy = y + i * line_h
        if shadow:
            sx, sy, sc = shadow
            draw.text((x + sx, yy + sy), line, font=fnt, fill=(*sc, 200))
        draw.text((x, yy), line, font=fnt, fill=color)

    bottom = y + line_h * len(lines)
    return bottom + b.get("gap_after", 0)


def _draw_underline(draw, b, cursor_y: int) -> int:
    w = b["w"]
    h = b.get("h", 10)
    color = (*b["color"], b.get("alpha", 255))
    y = b["y"] if b.get("y") is not None else cursor_y + b.get("gap_before", 0)
    x = (W - w) // 2
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=color)
    return y + h + b.get("gap_after", 0)


def _draw_logo(img, b, cursor_y: int) -> int:
    target_w = b.get("w", 700)
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    y = b["y"] if b.get("y") is not None else cursor_y + b.get("gap_before", 0)

    # BRAND RULE: when the logo sits over any non-white background (solid color
    # OR gradient), pass bar_color=C["white"] with bar_padding=40. The MPC
    # wordmark was designed against white; without the bar, the alpha-knockout
    # edges fringe visibly against pink/blue/magenta. Future templates should
    # default to using this bar when the underlying bg is anything but pure
    # white. See BRAND_KIT.md → "Logo placement rule".
    bar_color = b.get("bar_color")
    if bar_color is not None:
        pad = b.get("bar_padding", 30)
        bar = Image.new("RGBA", (W, new_h + pad * 2), (*bar_color, 255))
        img.paste(bar, (0, y - pad), bar)

    img.paste(logo, ((W - target_w) // 2, y), logo)
    return y + new_h + b.get("gap_after", 0)


def _draw_lower_third(draw, b) -> None:
    h = b.get("h", 180)
    y = b["y"] if b.get("y") is not None else H - 640
    bg = (*b.get("color", C["deep_magenta"]), 255)
    draw.rectangle((0, y, W, y + h), fill=bg)

    # Name
    name_fnt = font(56, bold=True)
    name_color = (*C["white"], 255)
    nw, nh = text_size(draw, b["name"], name_fnt)
    draw.text(((W - nw) // 2, y + 28), b["name"], font=name_fnt, fill=name_color)

    # Subtitle (citation)
    sub_fnt = font(32, bold=False)
    sub_color = (*C["soft_pink"], 255)
    sw, sh = text_size(draw, b["subtitle"], sub_fnt)
    draw.text(((W - sw) // 2, y + 28 + nh + 18),
              b["subtitle"], font=sub_fnt, fill=sub_color)


def _draw_bullet_row(draw, b, cursor_y: int) -> int:
    """Bullet (centered colored dot) + text on one line, vertically aligned."""
    text_size_px = b["size"]
    fnt = font(text_size_px, bold=True)
    line_h = int(text_size_px * 1.15)
    color = (*b["color"], 255)
    bullet_color = (*b.get("bullet_color", C["sky_blue"]), 255)
    bullet_d = b.get("bullet_d", 28)

    y = b["y"] if b.get("y") is not None else cursor_y + b.get("gap_before", 0)
    x_text = b.get("x", 200)
    x_bullet = x_text - 60
    # Vertically center bullet against text cap-height (~70% of nominal)
    cap_h = int(text_size_px * 0.7)
    bullet_y = y + (cap_h - bullet_d) // 2 + 4

    draw.ellipse((x_bullet, bullet_y, x_bullet + bullet_d, bullet_y + bullet_d),
                 fill=bullet_color)
    draw.text((x_text, y), b["text"], font=fnt, fill=color)

    return y + line_h + b.get("gap_after", 0)


def render_card(bg: np.ndarray, blocks: list[dict]) -> np.ndarray:
    """Compose a frame from background + ordered blocks (auto-flow layout)."""
    img = Image.fromarray(bg.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    content_box = SAFE["content_box"]
    cursor_y = content_box[1]

    for b in blocks:
        kind = b["kind"]
        if kind == "text":
            cursor_y = _draw_text_block(draw, b, cursor_y, content_box)
        elif kind == "underline":
            cursor_y = _draw_underline(draw, b, cursor_y)
        elif kind == "rect":
            x, y, w, h = b["xywh"]
            r = b.get("radius", 0)
            color = (*b["color"], b.get("alpha", 255))
            if r > 0:
                draw.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=color)
            else:
                draw.rectangle((x, y, x + w, y + h), fill=color)
        elif kind == "spacer":
            cursor_y += b["h"]
        elif kind == "logo":
            cursor_y = _draw_logo(img, b, cursor_y)
        elif kind == "lower_third":
            _draw_lower_third(draw, b)
        elif kind == "bullet":
            cursor_y = _draw_bullet_row(draw, b, cursor_y)
        else:
            raise ValueError(f"unknown block kind: {kind}")

    return np.array(img.convert("RGB"))


def make_clip(frame: np.ndarray, duration: float, fadein: float = 0.0,
              fadeout: float = 0.0) -> ImageClip:
    clip = ImageClip(frame).set_duration(duration)
    if fadein > 0:
        clip = clip.crossfadein(fadein)
    if fadeout > 0:
        clip = clip.crossfadeout(fadeout)
    return clip


# --------------------------------------------------------------------------- #
# Scenes
# --------------------------------------------------------------------------- #

def scene_hook() -> ImageClip:
    """0-3s: pattern interrupt. Pink/blue gradient + scream-text headline."""
    bg = gradient_bg(C["soft_pink"], C["sky_blue"], angle_deg=120)
    blocks = [
        {"kind": "spacer", "h": 500},
        {
            "kind": "text",
            "text": "WHAT THEY ACTUALLY VOTED FOR",
            "size": 96,
            "color": C["white"],
            "shadow": (4, 4, C["deep_magenta"]),
            "gap_after": 32,
        },
        {"kind": "underline", "w": 600, "h": 14, "color": C["white"], "gap_after": 28},
        {
            "kind": "text",
            "text": "(not what they said in the press release)",
            "size": 38,
            "color": C["white"],
            "bold": False,
        },
    ]
    return make_clip(render_card(bg, blocks), 3.0)


def scene_setup() -> ImageClip:
    """3-8s: soft pink bg, logo bird perched, situation setup."""
    bg = solid_bg(C["soft_pink"])
    blocks = [
        {"kind": "spacer", "h": 80},
        {"kind": "logo", "w": 800, "bar_color": C["white"], "bar_padding": 40,
         "gap_after": 80},
        {
            "kind": "text",
            "text": "On April 15,",
            "size": 72,
            "color": C["deep_magenta"],
            "bold": False,
            "gap_after": 18,
        },
        {
            "kind": "text",
            "text": "the Michigan House voted on HB-1234",
            "size": 60,
            "color": C["near_black"],
            "gap_after": 22,
        },
        {
            "kind": "text",
            "text": "(the school lunch funding bill)",
            "size": 44,
            "color": C["near_black"],
            "bold": False,
        },
    ]
    return make_clip(render_card(bg, blocks), 5.0, fadein=0.3)


def scene_quote() -> ImageClip:
    """8-18s: blue bg, big pull-quote with citation lower-third."""
    bg = solid_bg(C["sky_blue"])
    blocks = [
        {"kind": "spacer", "h": 200},
        {
            "kind": "text",
            "text": "“",  # left double quotation mark
            "size": 240,
            "color": C["white"],
            "gap_after": 0,
        },
        {
            "kind": "text",
            "text": "We simply cannot afford to feed every child in Michigan.",
            "size": 64,
            "color": C["white"],
            "gap_before": 20,
            "gap_after": 60,
        },
        {"kind": "underline", "w": 400, "h": 10, "color": C["soft_pink"]},
        {
            "kind": "lower_third",
            "name": "REP. EXAMPLE NAME",
            "subtitle": "Floor speech  •  April 15, 2026  •  House Journal p. 412",
            "y": 1280,
            "h": 180,
            "color": C["deep_magenta"],
        },
    ]
    return make_clip(render_card(bg, blocks), 10.0, fadein=0.4)


def scene_receipts() -> ImageClip:
    """18-25s: white bg, MEANWHILE header, three voting receipts."""
    bg = solid_bg(C["white"])
    blocks = [
        {"kind": "spacer", "h": 120},
        {
            "kind": "text",
            "text": "MEANWHILE,",
            "size": 56,
            "color": C["deep_magenta"],
            "gap_after": 12,
        },
        {
            "kind": "text",
            "text": "the same legislator voted to:",
            "size": 44,
            "color": C["near_black"],
            "bold": False,
            "gap_after": 80,
        },
        {
            "kind": "bullet",
            "text": "Approve $2.3M corporate tax break",
            "size": 44,
            "color": C["near_black"],
            "x": 200,
            "gap_after": 40,
        },
        {
            "kind": "bullet",
            "text": "Raise own legislative budget by 18%",
            "size": 44,
            "color": C["near_black"],
            "x": 200,
            "gap_after": 40,
        },
        {
            "kind": "bullet",
            "text": "Defund the Office of School Safety",
            "size": 44,
            "color": C["near_black"],
            "x": 200,
            "gap_after": 100,
        },
        {
            "kind": "text",
            "text": "Sources: HJ p.412, p.508, p.601",
            "size": 28,
            "color": C["deep_magenta"],
            "bold": False,
        },
    ]
    return make_clip(render_card(bg, blocks), 7.0, fadein=0.3)


def scene_endcard() -> ImageClip:
    """25-30s: gradient endcard with logo + handle + CTA."""
    bg = gradient_bg(C["sky_blue"], C["soft_pink"], angle_deg=300)
    blocks = [
        {"kind": "spacer", "h": 380},
        {"kind": "logo", "w": 900, "bar_color": C["white"], "bar_padding": 40,
         "gap_after": 220},
        {
            "kind": "text",
            "text": "FOLLOW THE FIGHT",
            "size": 64,
            "color": C["white"],
            "shadow": (3, 3, C["deep_magenta"]),
            "gap_after": 24,
        },
        {
            "kind": "text",
            "text": "@michiganprogressive",
            "size": 56,
            "color": C["white"],
            "gap_after": 16,
        },
        {
            "kind": "text",
            "text": "miprogressivecaucus.com",
            "size": 38,
            "color": C["white"],
            "bold": False,
        },
    ]
    return make_clip(render_card(bg, blocks), 5.0, fadein=0.4, fadeout=0.5)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    print("Building MPC 30s brand-fit demo (v2)...")

    scenes = [
        scene_hook(),
        scene_setup(),
        scene_quote(),
        scene_receipts(),
        scene_endcard(),
    ]

    video = concatenate_videoclips(scenes, method="compose").set_duration(DURATION)

    # --- Audio -------------------------------------------------------------- #
    print("\n[main] building audio bed...")
    mix_mono = audio_demo.build()
    audio_path = audio_demo.write_wav(mix_mono)
    audio_clip = AudioFileClip(str(audio_path)).set_duration(DURATION)
    video = video.set_audio(audio_clip)

    # --- Render ------------------------------------------------------------- #
    print("\n[main] rendering final video...")
    video.write_videofile(
        str(OUTPUT_PATH),
        fps=FPS,
        codec="libx264",
        preset="medium",
        bitrate="8M",
        audio_codec="aac",
        audio_bitrate="192k",
        threads=4,
    )
    print(f"\nDone. Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
