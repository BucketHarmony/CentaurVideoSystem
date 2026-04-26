"""
MPC Romulus Rapid Response — 30s vertical social video.

Composites real source footage from the Ice Out Romulus rally with brand
chrome (text, logo, scene overlays) + audio (harmonic hum chord per scene
+ ElevenLabs narration + Wigella native sync sound on the FIGHT beat).

Scenes:
  0:00-0:04  HOOK    — A minor   — chant footage  — "Hundreds of us marched..."
  0:04-0:13  STAKES  — D minor   — warehouse wide — "DHS bought a warehouse..."
  0:13-0:23  FIGHT   — C major   — Wigella sync  — "stood with Dana Nessel..."
  0:23-0:30  CTA     — A major   — full chrome   — "Chip in. Link below..."

Source footage:
  HOOK:    raw/MPC/Ice Out Romulus/20260425_170030.mp4 t=0.5..4.5 (Abolish ICE chant)
  STAKES:  raw/MPC/Ice Out Romulus/20260425_151118.mp4 t=0.0..9.0 (warehouse + signs)
  FIGHT:   raw/MPC/Ice Out Romulus/20260425_170500.mp4 t=0.0..10.0 (Wigella + native audio)
  CTA:     no footage well — full brand chrome only

Output: E:/AI/CVS/ComfyUI/output/mpc/romulus_rapid_response.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_romulus.py
"""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import butter, lfilter
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

# --------------------------------------------------------------------------- #
# Paths + brand
# --------------------------------------------------------------------------- #

W, H = 1080, 1920
FPS = 30
DURATION = 30.0

ROOT = Path("E:/AI/CVS/mpc")
BRAND = ROOT / "brand"
ENV_PATH = Path("E:/AI/CVS/.env")
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "romulus_rapid_response.mp4"
AUDIO_PATH = OUTPUT_DIR / "romulus_rapid_response_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")
SAFE = PALETTE["safe_zones_1080x1920"]

# Layout zones — video-first: slim banner, well swallows most of the frame.
# Captions overlay on top of the well, anchored to a fixed bottom y so multi-
# line captions grow UPWARD into the video rather than down into TikTok UI.
BANNER_H = 140                  # top white logo bar
WELL_TOP = BANNER_H             # 140
WELL_BOTTOM = 1750              # video now occupies ~84% of frame
WELL_H = WELL_BOTTOM - WELL_TOP # 1610
# Bottom y the caption strip anchors against (top of TikTok UI safe zone).
CAPTION_BOTTOM = 1620

# CTA scene uses a split layout: chrome in top, chant footage in bottom.
# Chrome zone shrunk so footage takes more of the frame on the CTA beat too.
CTA_CHROME_BOTTOM = 720         # chrome ends here; video starts here
CTA_WELL_TOP = 720
CTA_WELL_BOTTOM = 1920
CTA_WELL_H = CTA_WELL_BOTTOM - CTA_WELL_TOP   # 1200

# Per-scene source footage. Each entry is a dict (single shot) or list (chained).
# Optional keys: crop_x_frac, audio_gain, audio_in/audio_out (for trimming a
# mid-sentence tail), well_top/well_h (for non-default wells like CTA's split).
FOOTAGE = {
    "hook":   {"path": RAW_DIR / "20260425_170030.mp4", "in_t": 0.5,  "out_t": 4.5,
               "audio_gain": 1.0},                                                      # 4.0s
    "stakes": [
        # 4.5s warehouse establishing (crop shifted right to keep the building in frame)
        {"path": RAW_DIR / "20260425_151118.mp4", "in_t": 0.0,  "out_t": 4.5,
         "crop_x_frac": 0.62, "audio_gain": 1.0},
        # 6.0s chant footage extended past 14.5 → 16.0 to land cleanly on
        # an "Abolish ICE!" beat instead of cutting mid-chant.
        {"path": RAW_DIR / "20260425_170030.mp4", "in_t": 10.0, "out_t": 16.0,
         "audio_gain": 1.0},
    ],                                                                                  # 10.5s total
    # Wigella speaking — native sync sound IS the FIGHT narration. Audio
    # range trimmed to 0..9.0 to land on the end of "...suing the federal
    # government." Scene shrunk 10s → 9s to make room for extended chant.
    "fight":  {"path": RAW_DIR / "20260425_170500.mp4", "in_t": 0.0, "out_t": 9.0,
               "audio_in": 0.0, "audio_out": 9.0, "audio_gain": 1.4},                   # 9.0s
    # CTA bottom-half: chant + signs. Trimmed 7s → 6.5s to balance.
    "cta":    {"path": RAW_DIR / "20260425_170245.mp4", "in_t": 8.0, "out_t": 14.5,
               "audio_gain": 0.7,                                                       # 6.5s
               "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H},
}

# --------------------------------------------------------------------------- #
# Audio config
# --------------------------------------------------------------------------- #

SR = 44100
N = int(SR * DURATION)
T = np.linspace(0, DURATION, N, endpoint=False)

# Scene boundaries (start, end, slug, label) — extended STAKES to capture
# a clean "Abolish ICE!" beat; FIGHT and CTA shrink to keep total = 30s.
SCENES = [
    (0.0,  4.0,  "hook",   "OPEN"),
    (4.0,  14.5, "stakes", "STAKES"),
    (14.5, 23.5, "fight",  "THE FIGHT"),
    (23.5, 30.0, "cta",    "CTA"),
]

# Harmonic hum: chord per scene (Hz), one root + a few colour tones.
# The progression Am -> Dm -> C -> A traces the emotional arc of the words:
# protest urgency -> grief over injustice -> rising hope -> triumphant resolve.
SCENE_CHORDS = {
    "hook":   [110.00, 164.81, 220.00],            # A minor (A2 + E3 + A3)
    "stakes": [73.42,  110.00, 146.83, 174.61],    # D minor (D2 + A2 + D3 + F3)
    "fight":  [130.81, 196.00, 261.63, 329.63],    # C major (C3 + G3 + C4 + E4)
    "cta":    [110.00, 164.81, 220.00, 277.18],    # A major (A2 + E3 + A3 + C#4)
}

NARRATION_LINES = [
    {"slug": "hook",   "start": 0.30,
     "text": "Today, hundreds of us marched in Romulus."},
    {"slug": "stakes", "start": 4.30,
     "text": "DHS bought a warehouse near Metro Airport. We march for our neighbors."},
    # FIGHT VO replaced by Wigella native sync sound from FOOTAGE["fight"].
    {"slug": "cta",    "start": 23.90,
     "text": "Chip in to the Michigan Progressive Caucus. Link below. We don't back down."},
]

CTA_URL = "secure.actblue.com/donate/michigan-progressive-caucus-1"

# --------------------------------------------------------------------------- #
# PIL helpers
# --------------------------------------------------------------------------- #

def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_HEADLINE if bold else FONT_BODY
    return ImageFont.truetype(path, size)


def text_size(draw, txt, fnt):
    l, t, r, b = draw.textbbox((0, 0), txt, font=fnt)
    return r - l, b - t


def wrap(draw, text, fnt, max_w):
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


def gradient_bg(c1, c2, angle_deg=135.0):
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    proj = xx * dx + yy * dy
    proj = (proj - proj.min()) / (proj.max() - proj.min())
    img = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(3):
        img[..., i] = (c1[i] * (1 - proj) + c2[i] * proj).astype(np.uint8)
    return img

# --------------------------------------------------------------------------- #
# Layout safety: bbox-aware text helpers + per-scene overlap guard
# --------------------------------------------------------------------------- #
#
# Every `draw_*` helper returns the bounding box of the element it placed.
# Each `render_*` scene collects those bboxes into `elems` and calls
# `check_overlaps()` at the end. If any two registered elements overlap (with
# a small padding tolerance), the build prints a clear warning per scene so
# layout regressions are caught before export instead of after eyeballing
# the rendered video.

def measure_text_bbox(draw, text, fnt, x_center, top):
    """
    Compute (bbox, draw_x, draw_y) so that drawing `text` at (draw_x, draw_y)
    with `fnt` lands the ink horizontally centered on `x_center` and starting
    at y=`top`. The returned bbox reflects the actual ink extent (from
    Pillow's textbbox) — accounting for font ascender/descender offsets.
    """
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    draw_x = x_center - w // 2 - l
    draw_y = top - t
    bbox = (draw_x + l, draw_y + t, draw_x + r, draw_y + b)
    return bbox, draw_x, draw_y


def draw_centered_text(draw, text, fnt, x_center, top, fill,
                       shadow_offset=None, shadow_color=(0, 0, 0, 200)):
    """
    Draw `text` horizontally centered on `x_center` with the top of the ink
    at y=`top`. Returns the actual ink bbox (extended to include shadow if
    `shadow_offset` is given).
    """
    bbox, dx, dy = measure_text_bbox(draw, text, fnt, x_center, top)
    if shadow_offset:
        sx, sy = shadow_offset
        draw.text((dx + sx, dy + sy), text, font=fnt, fill=shadow_color)
        bbox = (bbox[0], bbox[1], bbox[2] + max(sx, 0), bbox[3] + max(sy, 0))
    draw.text((dx, dy), text, font=fnt, fill=fill)
    return bbox


def check_overlaps(scene_name, elements, padding=4, fail_on_overlap=False):
    """
    Walk every pair of bboxes in `elements` (list of (label, (x0,y0,x1,y1)))
    and print any pair that overlaps by more than `padding` px on both axes.
    Used at the end of every scene render to catch silent layout regressions.

    Set `fail_on_overlap=True` to raise instead of warn — useful in CI.
    """
    issues = []
    for i, (la, ba) in enumerate(elements):
        for lb, bb in elements[i + 1:]:
            if (ba[0] < bb[2] - padding and ba[2] > bb[0] + padding and
                    ba[1] < bb[3] - padding and ba[3] > bb[1] + padding):
                issues.append((la, ba, lb, bb))
    if not issues:
        print(f"[layout/{scene_name}] OK — {len(elements)} elements, no overlaps")
        return
    print(f"[layout/{scene_name}] {len(issues)} OVERLAP(S) in {len(elements)} elements:")
    for la, ba, lb, bb in issues:
        print(f"  '{la}' {ba}  <->  '{lb}' {bb}")
    if fail_on_overlap:
        raise RuntimeError(f"[layout/{scene_name}] layout overlap detected")


# --------------------------------------------------------------------------- #
# Scene chrome — top banner, video-well placeholder, bottom caption
# --------------------------------------------------------------------------- #

def draw_top_banner(img, banner_h=BANNER_H, target_w=560):
    """White bar with centered MPC logo. `target_w` shrinks for the slim banner."""
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, W, banner_h), fill=(*C["white"], 255))
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    img.paste(logo, ((W - target_w) // 2, (banner_h - new_h) // 2), logo)
    return (0, 0, W, banner_h)


def draw_well_placeholder(img, well_color_top, well_color_bottom, footage_hint,
                          transparent=False, well_top=WELL_TOP, well_h=WELL_H):
    """
    Backdrop for the video well. `well_top`/`well_h` allow non-default wells
    (CTA's bottom-half split, etc).
    """
    if transparent:
        well = np.zeros((well_h, W, 4), dtype=np.uint8)
        img.paste(Image.fromarray(well, "RGBA"), (0, well_top))
        return (0, well_top, W, well_top + well_h)

    well = np.zeros((well_h, W, 4), dtype=np.uint8)
    for i in range(well_h):
        t = i / max(1, well_h - 1)
        well[i, :, 0] = int(well_color_top[0] * (1 - t) + well_color_bottom[0] * t)
        well[i, :, 1] = int(well_color_top[1] * (1 - t) + well_color_bottom[1] * t)
        well[i, :, 2] = int(well_color_top[2] * (1 - t) + well_color_bottom[2] * t)
        well[i, :, 3] = 255
    img.paste(Image.fromarray(well, "RGBA"), (0, well_top))

    draw = ImageDraw.Draw(img, "RGBA")
    hint_fnt = font(28, bold=False)
    label = f"[ FOOTAGE: {footage_hint} ]"
    return draw_centered_text(draw, label, hint_fnt, W // 2, well_top + 24,
                              fill=(255, 255, 255, 90))


def draw_caption(img, text, size=58, y_top=1240, plate_alpha=200, color=None):
    """
    Bottom caption: bold white text on a translucent dark plate. Returns the
    plate bbox (which fully encloses the text) — that's the box to register
    with the overlap guard.
    """
    if color is None:
        color = C["white"]
    draw = ImageDraw.Draw(img, "RGBA")
    fnt = font(size, bold=True)
    lines = wrap(draw, text, fnt, max_w=940)
    line_h = int(size * 1.18)
    block_h = line_h * len(lines) + 56
    plate_top = y_top
    plate_bot = min(WELL_BOTTOM, plate_top + block_h)
    draw.rectangle((0, plate_top, W, plate_bot), fill=(*C["near_black"], plate_alpha))

    for i, line in enumerate(lines):
        line_top = plate_top + 28 + i * line_h
        draw_centered_text(draw, line, fnt, W // 2, line_top,
                           fill=(*color, 255),
                           shadow_offset=(3, 3),
                           shadow_color=(0, 0, 0, 220))
    return (0, plate_top, W, plate_bot)


def draw_lower_third_pill(img, label, y=1140, color=None):
    """Pill-shaped chip for an address/location callout. Returns the pill bbox."""
    if color is None:
        color = C["deep_magenta"]
    draw = ImageDraw.Draw(img, "RGBA")
    fnt = font(46, bold=True)
    l, t, r, b = draw.textbbox((0, 0), label, font=fnt)
    tw, th = r - l, b - t
    pad_x, pad_y = 36, 20
    pill_w, pill_h = tw + pad_x * 2, th + pad_y * 2
    x = (W - pill_w) // 2
    draw.rounded_rectangle((x, y, x + pill_w, y + pill_h),
                           radius=pill_h // 2, fill=(*color, 240))
    # Center text inside pill using bbox-correct coords (no font baseline slop)
    draw_x = x + pad_x - l
    draw_y = y + pad_y - t
    draw.text((draw_x, draw_y), label, font=fnt, fill=(*C["white"], 255))
    return (x, y, x + pill_w, y + pill_h)


def draw_giant_callout(img, label, top_y, size=240, color=None,
                       sub=None, sub_size=50, sub_gap=None):
    """
    Big centered callout (e.g. 'MAY 18') with optional subtitle below.
    `top_y` is the y of the top of the label ink. The sub flows AFTER the
    label's actual ink-bbox bottom + `sub_gap` (default scales with `size`,
    so a 240pt headline gets a meaningful breathing pad rather than a fixed
    24px gap that disappears at large sizes).
    Returns (label_bbox, sub_bbox) — sub_bbox is None when no subtitle.
    """
    if color is None:
        color = C["soft_pink"]
    draw = ImageDraw.Draw(img, "RGBA")
    fnt = font(size, bold=True)
    label_bbox = draw_centered_text(draw, label, fnt, W // 2, top_y,
                                    fill=(*color, 255),
                                    shadow_offset=(6, 6),
                                    shadow_color=(0, 0, 0, 200))
    sub_bbox = None
    if sub:
        sub_fnt = font(sub_size, bold=True)
        if sub_gap is None:
            # Proportional to label size so big headlines get visible space
            sub_gap = max(28, int(size * 0.18))
        sub_top = label_bbox[3] + sub_gap
        sub_bbox = draw_centered_text(draw, sub, sub_fnt, W // 2, sub_top,
                                      fill=(*C["white"], 255),
                                      shadow_offset=(3, 3),
                                      shadow_color=(0, 0, 0, 200))
    return label_bbox, sub_bbox


# --------------------------------------------------------------------------- #
# Per-scene renderers
# --------------------------------------------------------------------------- #

def render_hook(well_transparent=False):
    """0-4s: HOOK — protest crowd footage, headline. Transcript via overlay layer."""
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    elems = []

    elems.append(("well", draw_well_placeholder(
        img,
        well_color_top=(60, 50, 70),
        well_color_bottom=(25, 20, 35),
        footage_hint="protest crowd, signs, marchers on Cogswell",
        transparent=well_transparent)))

    # Big in-well headline (flows from a top y; date strip flows after it)
    draw = ImageDraw.Draw(img, "RGBA")
    head_bbox = draw_centered_text(draw, "ROMULUS", font(108, bold=True),
                                   W // 2, 220, fill=(*C["soft_pink"], 255),
                                   shadow_offset=(5, 5),
                                   shadow_color=(0, 0, 0, 230))
    elems.append(("ROMULUS", head_bbox))

    date_top = head_bbox[3] + 24
    date_bbox = draw_centered_text(draw, "TODAY  •  APRIL 25, 2026",
                                   font(54, bold=True), W // 2, date_top,
                                   fill=(*C["white"], 255),
                                   shadow_offset=(3, 3),
                                   shadow_color=(0, 0, 0, 230))
    elems.append(("date_strip", date_bbox))

    elems.append(("top_banner", draw_top_banner(img)))

    elems_for_check = [e for e in elems if e[0] != "well"] if well_transparent else elems
    check_overlaps("HOOK", elems_for_check)
    return np.array(img)


def render_stakes(well_transparent=False):
    """4-13s: STAKES — warehouse footage + headline + address pill.

    Subtitle reframed from "to cage immigrant neighbors" (dark/grim) to
    "FOR OUR NEIGHBORS" — answers "what are we fighting for", echoes a real
    line from the rally ("This is for our neighbors who are locked inside",
    chanted in clip 170245). Stays warm/protective rather than fear-driven.
    """
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    elems = []

    elems.append(("well", draw_well_placeholder(
        img,
        well_color_top=(80, 30, 50),
        well_color_bottom=(25, 12, 22),
        footage_hint="warehouse exterior, DHS site",
        transparent=well_transparent)))

    draw = ImageDraw.Draw(img, "RGBA")
    head_bbox = draw_centered_text(draw, "DHS WAREHOUSE", font(74, bold=True),
                                   W // 2, 200, fill=(*C["white"], 255),
                                   shadow_offset=(4, 4),
                                   shadow_color=(0, 0, 0, 220))
    elems.append(("DHS WAREHOUSE", head_bbox))

    sub_top = head_bbox[3] + 22
    sub_bbox = draw_centered_text(draw, "FOR OUR NEIGHBORS",
                                  font(56, bold=True), W // 2, sub_top,
                                  fill=(*C["soft_pink"], 255),
                                  shadow_offset=(3, 3),
                                  shadow_color=(0, 0, 0, 230))
    elems.append(("for_our_neighbors", sub_bbox))

    elems.append(("top_banner", draw_top_banner(img)))
    elems.append(("address_pill",
                  draw_lower_third_pill(img, "7525 COGSWELL RD  •  ROMULUS", y=1180)))

    elems_for_check = [e for e in elems if e[0] != "well"] if well_transparent else elems
    check_overlaps("STAKES", elems_for_check)
    return np.array(img)


def render_fight(well_transparent=False):
    """13-23s: FIGHT — Wigella sync footage + MAY 18 over the speaker's legs.

    The callout sits at top_y=1060 over the speaker's legs/grass, leaving
    his head & mic visible. Sized so MAY 18 + INJUNCTION HEARING + AG NESSEL
    strip ends above the transcript caption strip (anchored to CAPTION_BOTTOM).
    """
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    elems = []

    elems.append(("well", draw_well_placeholder(
        img,
        well_color_top=(40, 70, 110),
        well_color_bottom=(15, 30, 60),
        footage_hint="Wigella speaking — warehouse behind",
        transparent=well_transparent)))

    label_bbox, sub_bbox = draw_giant_callout(
        img, "MAY 18", top_y=1060, size=160, color=C["soft_pink"],
        sub="INJUNCTION HEARING", sub_size=42, sub_gap=12)
    elems.append(("MAY 18", label_bbox))
    elems.append(("INJUNCTION HEARING", sub_bbox))

    draw = ImageDraw.Draw(img, "RGBA")
    nessel_top = sub_bbox[3] + 18
    nessel_bbox = draw_centered_text(
        draw, "AG NESSEL  •  CITY OF ROMULUS  •  SUING",
        font(34, bold=True), W // 2, nessel_top,
        fill=(*C["white"], 255),
        shadow_offset=(3, 3),
        shadow_color=(0, 0, 0, 220))
    elems.append(("ag_nessel_strip", nessel_bbox))

    elems.append(("top_banner", draw_top_banner(img)))

    elems_for_check = [e for e in elems if e[0] != "well"] if well_transparent else elems
    check_overlaps("FIGHT", elems_for_check)
    return np.array(img)


def render_cta(well_transparent=False):
    """23-30s: split layout — brand chrome in TOP HALF (0..960), chant + signs
    footage in BOTTOM HALF (960..1920). Bottom half is punched transparent
    when `well_transparent=True` so the FOOTAGE['cta'] clip composites in.
    """
    # Top-half background gradient (chrome zone only)
    bg_full = gradient_bg(C["sky_blue"], C["soft_pink"], angle_deg=300)
    bg_full[CTA_CHROME_BOTTOM:, :, :] = 0  # zero the bottom half
    img = Image.fromarray(bg_full).convert("RGBA")
    if well_transparent:
        # Punch bottom half fully transparent (alpha=0)
        bot = np.zeros((CTA_WELL_H, W, 4), dtype=np.uint8)
        img.paste(Image.fromarray(bot, "RGBA"), (0, CTA_WELL_TOP))
    else:
        # Preview-mode: tint the bottom half so it's visible without footage
        tint = np.zeros((CTA_WELL_H, W, 4), dtype=np.uint8)
        tint[..., :3] = (40, 30, 50)
        tint[..., 3] = 255
        img.paste(Image.fromarray(tint, "RGBA"), (0, CTA_WELL_TOP))

    draw = ImageDraw.Draw(img, "RGBA")
    elems = []

    # Logo on white bar (BRAND RULE)
    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_w = 720
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    bar_y = 90
    pad = 40
    bar_top = bar_y - pad
    bar_bot = bar_y + new_h + pad
    bar = Image.new("RGBA", (W, new_h + pad * 2), (*C["white"], 255))
    img.paste(bar, (0, bar_top), bar)
    img.paste(logo, ((W - target_w) // 2, bar_y), logo)
    elems.append(("logo_bar", (0, bar_top, W, bar_bot)))

    # Tagline
    tag_top = bar_bot + 30
    tag_bbox = draw_centered_text(
        draw, "WE DON'T BACK DOWN", font(70, bold=True), W // 2, tag_top,
        fill=(*C["white"], 255),
        shadow_offset=(4, 4),
        shadow_color=(*C["deep_magenta"], 230))
    elems.append(("tagline", tag_bbox))

    # CHIP IN + polygon down-arrow (Montserrat lacks U+2193)
    chip_top = tag_bbox[3] + 24
    chip_bbox = draw_centered_text(
        draw, "CHIP IN", font(48, bold=True), W // 2, chip_top,
        fill=(*C["white"], 255))
    arrow_h = chip_bbox[3] - chip_bbox[1]
    arrow_w = int(arrow_h * 0.8)
    arrow_x = chip_bbox[2] + 22
    arrow_top = chip_bbox[1]
    stem_w = max(6, arrow_w // 4)
    stem_top = arrow_top + arrow_h // 6
    stem_bot = arrow_top + int(arrow_h * 0.55)
    cx = arrow_x + arrow_w // 2
    draw.rectangle((cx - stem_w // 2, stem_top, cx + stem_w // 2, stem_bot),
                   fill=(*C["white"], 255))
    draw.polygon([
        (arrow_x, stem_bot),
        (arrow_x + arrow_w, stem_bot),
        (cx, arrow_top + arrow_h),
    ], fill=(*C["white"], 255))
    chip_bbox = (chip_bbox[0], chip_bbox[1],
                 arrow_x + arrow_w, max(chip_bbox[3], arrow_top + arrow_h))
    elems.append(("chip_in", chip_bbox))

    # ActBlue URL plate
    url_fnt = font(30, bold=True)
    ul, ut, ur, ub = draw.textbbox((0, 0), CTA_URL, font=url_fnt)
    url_tw, url_th = ur - ul, ub - ut
    plate_w = url_tw + 70
    plate_h = url_th + 44
    plate_x = (W - plate_w) // 2
    plate_y = chip_bbox[3] + 20
    draw.rounded_rectangle((plate_x, plate_y, plate_x + plate_w, plate_y + plate_h),
                           radius=20, fill=(*C["white"], 250))
    draw.text((plate_x + 35 - ul, plate_y + 22 - ut),
              CTA_URL, font=url_fnt, fill=(*C["deep_magenta"], 255))
    elems.append(("actblue_plate", (plate_x, plate_y, plate_x + plate_w, plate_y + plate_h)))

    # Handle / link-in-bio
    cap_top = plate_y + plate_h + 24
    cap_bbox = draw_centered_text(
        draw, "Link in bio  •  @michiganprogressive",
        font(34, bold=False), W // 2, cap_top,
        fill=(*C["white"], 255))
    elems.append(("link_in_bio", cap_bbox))

    elems_for_check = [e for e in elems if e[0] != "well"] if well_transparent else elems
    check_overlaps("CTA", elems_for_check)
    return np.array(img)


# --------------------------------------------------------------------------- #
# Audio: harmonic hum chord per scene (crossfaded) + ElevenLabs narration
# --------------------------------------------------------------------------- #

def render_chord_window(notes_hz, t_start, t_end, fade_in=0.5, fade_out=0.5):
    """
    Sustained harmonic hum from t_start..t_end. Each voice is a sine
    fundamental + softer 2nd/3rd harmonics, with subtle vibrato + slow
    tremolo for breath. Lowpassed for warmth.
    """
    out = np.zeros(N, dtype=np.float32)
    i0 = int(t_start * SR)
    i1 = min(N, int(t_end * SR))
    if i0 >= N or i1 <= i0:
        return out
    n = i1 - i0
    t_local = np.linspace(0, n / SR, n, endpoint=False)

    chord = np.zeros(n, dtype=np.float32)
    # Vibrato (5.5Hz, 0.4% pitch wobble) and slow breath (0.3Hz tremolo, 18%)
    vib = 0.004 * np.sin(2 * np.pi * 5.5 * t_local)
    breath = 1.0 - 0.18 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.3 * t_local))

    for k, f in enumerate(notes_hz):
        amp = max(0.04, 0.13 - 0.025 * k)
        # Fundamental with vibrato — phase = 2*pi * cumsum(f_inst)/SR
        phase1 = 2 * np.pi * np.cumsum(f * (1 + vib)) / SR
        chord += amp * np.sin(phase1)
        # 2nd harmonic (octave) at 30% — adds body
        phase2 = 2 * np.pi * np.cumsum(2 * f * (1 + vib * 0.6)) / SR
        chord += amp * 0.30 * np.sin(phase2)
        # 3rd harmonic at 12% — colour
        phase3 = 2 * np.pi * np.cumsum(3 * f * (1 + vib * 0.3)) / SR
        chord += amp * 0.12 * np.sin(phase3)

    chord *= breath

    fi_n = min(int(fade_in * SR), n // 2)
    fo_n = min(int(fade_out * SR), n // 2)
    if fi_n > 0:
        chord[:fi_n] *= np.linspace(0, 1, fi_n) ** 2
    if fo_n > 0:
        chord[-fo_n:] *= np.linspace(1, 0, fo_n) ** 2

    b, a = butter(4, 3500 / (SR / 2), btype="low")
    chord = lfilter(b, a, chord).astype(np.float32)

    out[i0:i1] = chord
    return out


def harmonic_hum():
    """Build the full hum track. Adjacent scenes overlap by `overlap` for a smooth chord change."""
    bed = np.zeros(N, dtype=np.float32)
    overlap = 0.5
    for idx, (t0, t1, slug, _) in enumerate(SCENES):
        notes = SCENE_CHORDS[slug]
        is_first = idx == 0
        is_last = idx == len(SCENES) - 1
        ws = max(0.0, t0 - (0 if is_first else overlap))
        we = min(DURATION, t1 + (0 if is_last else overlap))
        fi = 0.25 if is_first else overlap
        fo = 0.6 if is_last else overlap
        bed += render_chord_window(notes, ws, we, fade_in=fi, fade_out=fo)
    return bed


def load_env(path=ENV_PATH):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def synthesize_narration(env):
    api_key = env.get("ELEVENLABS_API_KEY")
    voice = env.get("ELEVENLABS_VOICE")
    model = env.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
        print("[narration] no ELEVENLABS_API_KEY — skipping TTS")
        return None
    try:
        import requests
        from pydub import AudioSegment
    except ImportError as e:
        print(f"[narration] missing dep: {e}")
        return None

    track = np.zeros(N, dtype=np.float32)
    for i, line in enumerate(NARRATION_LINES):
        # Cache key by slug so dropping/reordering NARRATION_LINES doesn't
        # invalidate cached MP3s for the lines that didn't change.
        cache_path = TTS_CACHE / f"romulus_{line['slug']}.mp3"
        if not cache_path.exists():
            print(f"[narration] generating line {i}: {line['text'][:60]!r}")
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": api_key,
                         "Content-Type": "application/json",
                         "Accept": "audio/mpeg"},
                json={"text": line["text"], "model_id": model,
                      "voice_settings": {"stability": 0.55, "similarity_boost": 0.75}},
                timeout=60,
            )
            if r.status_code != 200:
                print(f"  ERROR {r.status_code}: {r.text[:200]}")
                return None
            cache_path.write_bytes(r.content)
        else:
            print(f"[narration] cached line {i}")
        seg = AudioSegment.from_mp3(cache_path).set_frame_rate(SR).set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples = samples / float(1 << (8 * seg.sample_width - 1))
        i0 = int(line["start"] * SR)
        i1 = min(N, i0 + len(samples))
        track[i0:i1] += samples[: i1 - i0] * 0.95
    return track


def sidechain_duck(bed, voice, threshold=0.025, ratio=0.30,
                   attack_ms=20.0, release_ms=180.0):
    """Drop the hum where voice is loud so VO sits cleanly on top."""
    if voice is None:
        return bed
    env = np.abs(voice)
    a_atk = math.exp(-1 / (SR * attack_ms / 1000))
    a_rel = math.exp(-1 / (SR * release_ms / 1000))
    smoothed = np.zeros_like(env)
    s = 0.0
    for i in range(len(env)):
        coef = a_atk if env[i] > s else a_rel
        s = coef * s + (1 - coef) * env[i]
        smoothed[i] = s
    duck = 1.0 - np.clip((smoothed - threshold) / threshold, 0, 1) * (1 - ratio)
    return bed * duck.astype(np.float32)


def to_int16_stereo(mono):
    mono = np.clip(mono, -1.0, 1.0)
    L = (mono * 32767).astype(np.int16)
    R = L.copy()
    return np.column_stack([L, R]).flatten()


def build_voice_track():
    """Synth TTS narration only, aligned to the master timeline."""
    env = load_env()
    voice = synthesize_narration(env)
    return voice if voice is not None else np.zeros(N, dtype=np.float32)


def _shot_audio_range(shot):
    """Audio in/out for a shot — defaults to video in_t/out_t."""
    return float(shot.get("audio_in", shot["in_t"])), \
           float(shot.get("audio_out", shot["out_t"]))


def build_source_audio_track():
    """
    Per-clip native audio aligned to scene timelines. For multi-shot scenes,
    each shot's audio is placed back-to-back at the scene's start. A small
    fade-in/out at every shot boundary kills click/pop.
    """
    track = np.zeros(N, dtype=np.float32)
    scene_starts = {s[2]: s[0] for s in SCENES}
    fade_n = int(0.05 * SR)  # 50ms edge fade
    for slug, spec in FOOTAGE.items():
        if spec is None:
            continue
        shots = spec if isinstance(spec, list) else [spec]
        offset_s = 0.0
        for shot in shots:
            video_dur = float(shot["out_t"]) - float(shot["in_t"])
            a0, a1 = _shot_audio_range(shot)
            seg = extract_audio_segment(_rotation_baked_path(shot["path"]), a0, a1)
            if seg is None:
                offset_s += video_dur
                continue
            gain = float(shot.get("audio_gain", 1.0))
            if len(seg) > 2 * fade_n:
                seg[:fade_n] *= np.linspace(0, 1, fade_n)
                seg[-fade_n:] *= np.linspace(1, 0, fade_n)
            place_t = scene_starts[slug] + offset_s
            i0 = int(place_t * SR)
            i1 = min(N, i0 + len(seg))
            track[i0:i1] += seg[: i1 - i0] * gain
            print(f"[audio/{slug}] +{Path(shot['path']).name} a={a0:.2f}..{a1:.2f}s "
                  f"@ t={place_t:.2f}s gain={gain}")
            offset_s += video_dur
    return track


def vo_duck_envelope(voice, threshold=0.02, low_gain=0.5,
                     attack_ms=10.0, release_ms=200.0):
    """
    Returns an N-length curve in [low_gain, 1.0]: drops to `low_gain` where
    `voice` is loud, returns to 1.0 where voice is quiet. Used to duck the
    source-audio track to 50% under synth VO without affecting parts of the
    timeline where there's no VO at all.
    """
    if voice is None or float(np.max(np.abs(voice))) < 1e-5:
        return np.ones(N, dtype=np.float32)
    env = np.abs(voice)
    a_atk = math.exp(-1 / (SR * attack_ms / 1000))
    a_rel = math.exp(-1 / (SR * release_ms / 1000))
    smoothed = np.zeros_like(env)
    s = 0.0
    for i in range(len(env)):
        coef = a_atk if env[i] > s else a_rel
        s = coef * s + (1 - coef) * env[i]
        smoothed[i] = s
    duck = 1.0 - np.clip((smoothed - threshold) / threshold, 0, 1) * (1.0 - low_gain)
    return duck.astype(np.float32)


def build_audio():
    print("[audio] rendering harmonic hum (chord per scene)...")
    bed = harmonic_hum()
    print("[audio] building voice track (synth TTS)...")
    voice = build_voice_track()
    print("[audio] building source-audio track from clips...")
    source = build_source_audio_track()

    # Duck source audio to 50% only where synth VO is active
    print("[audio] ducking source audio under VO (50% during VO, 100% otherwise)...")
    source = source * vo_duck_envelope(voice, low_gain=0.5)

    # Sidechain bed under voice + source so the chord retreats during any speech
    speech = voice + source
    has_speech = float(np.max(np.abs(speech))) > 1e-4
    if has_speech:
        print("[audio] sidechain ducking hum under voice + source...")
        bed = sidechain_duck(bed, speech)

    # Chord bed at 50% of previous level (user request)
    mix = bed * 0.5 + voice * 1.0 + source * 1.0
    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.9
    return mix


def write_wav(mono, path=AUDIO_PATH):
    stereo = to_int16_stereo(mono)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"[audio] wrote {path}")
    return path


# --------------------------------------------------------------------------- #
# Footage compositor — load source MP4s, scale-and-crop into the well, then
# overlay the chrome (RGBA with the well rectangle punched out).
# --------------------------------------------------------------------------- #

_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"


def _get_rotation(path):
    """Read display-rotation metadata (degrees, signed) from a video file.
    Returns 0 when no rotation tag is present."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream_side_data=rotation",
             "-of", "default=nw=1:nk=1", str(path)],
            stderr=subprocess.STDOUT,
        ).decode().strip()
        return int(float(out)) if out else 0
    except Exception:
        return 0


def _rotation_baked_path(path):
    """If `path` has rotation metadata, return a cached re-encoded copy with
    rotation baked into pixels (and cleared from metadata) so MoviePy 1.0.3,
    which silently ignores rotation, sees the correct aspect.

    MoviePy 1.0.3 distorts rotated phone videos: it applies rotation to the
    frame contents but keeps the original (un-rotated) buffer dimensions,
    visibly squashing portrait clips into landscape. Pre-baking with ffmpeg's
    default autorotate sidesteps the bug entirely.
    """
    if _get_rotation(path) == 0:
        return Path(path)
    _ROT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = _ROT_CACHE_DIR / f"{Path(path).stem}_rot.mp4"
    if out.exists() and out.stat().st_mtime >= Path(path).stat().st_mtime:
        return out
    import subprocess
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", str(path),
           "-metadata:s:v", "rotate=0",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k",
           str(out)]
    print(f"[rotate] baking {Path(path).name} -> {out.name}")
    subprocess.run(cmd, check=True)
    return out


def prepare_one_clip(spec, well_h):
    """
    Load `spec["path"]` from in_t..out_t, scale to fill `well_h`, crop to W.
    `spec["crop_x_frac"]` (default 0.5) shifts the horizontal crop center.
    """
    src = _rotation_baked_path(spec["path"])
    clip = VideoFileClip(str(src)).subclip(spec["in_t"], spec["out_t"])
    clip = clip.without_audio()
    scaled = clip.resize(height=well_h)
    crop_frac = float(spec.get("crop_x_frac", 0.5))
    if scaled.w > W:
        x_center = scaled.w * crop_frac
        x_center = max(W / 2, min(scaled.w - W / 2, x_center))
        return scaled.crop(x_center=x_center, width=W, height=well_h)
    if scaled.w < W:
        widened = clip.resize(width=W)
        if widened.h > well_h:
            return widened.crop(y_center=widened.h / 2, width=W, height=well_h)
        return widened
    return scaled


def _spec_well(spec):
    """Returns (well_top, well_h) for a spec, defaulting to scene's well."""
    s = spec[0] if isinstance(spec, list) else spec
    return int(s.get("well_top", WELL_TOP)), int(s.get("well_h", WELL_H))


def prepare_footage(spec, duration):
    """
    Build the well-sized footage clip. `spec` may be a single dict or a list.
    Per-shot well dimensions (well_top, well_h) come from the first shot.
    """
    specs = spec if isinstance(spec, list) else [spec]
    _, well_h = _spec_well(spec)
    sub_clips = [prepare_one_clip(s, well_h) for s in specs]
    if len(sub_clips) == 1:
        out = sub_clips[0]
    else:
        out = concatenate_videoclips(sub_clips, method="compose")
    return out.set_duration(duration)


def split_chrome_alpha(rgba):
    """Split an HxWx4 RGBA numpy array into (rgb, alpha_float)."""
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    return rgb, alpha


def make_chrome_clip(rgba, duration):
    """Build an ImageClip with mask from a 4-channel RGBA numpy array."""
    rgb, alpha = split_chrome_alpha(rgba)
    chrome = ImageClip(rgb).set_duration(duration)
    mask = ImageClip(alpha, ismask=True).set_duration(duration)
    return chrome.set_mask(mask)


def build_scene_clip(render_fn, footage_spec, duration, fadein=0.0, fadeout=0.0):
    """
    Build a scene as: [black bg] + [footage in well, if any] + [chrome on top].
    If footage_spec is None, skip the footage layer (chrome covers full frame).
    """
    if footage_spec is None:
        rgba = render_fn(well_transparent=False)
        clip = ImageClip(rgba[:, :, :3]).set_duration(duration)
    else:
        chrome_rgba = render_fn(well_transparent=True)
        chrome = make_chrome_clip(chrome_rgba, duration)

        well_top, _ = _spec_well(footage_spec)
        footage = prepare_footage(footage_spec, duration)
        footage = footage.set_position((0, well_top))

        bg = ColorClip(size=(W, H), color=(0, 0, 0)).set_duration(duration)
        clip = CompositeVideoClip([bg, footage, chrome], size=(W, H))
        clip = clip.set_duration(duration)

    if fadein > 0:
        clip = clip.crossfadein(fadein)
    if fadeout > 0:
        clip = clip.crossfadeout(fadeout)
    return clip


def measure_tts_duration(slug):
    """Read the cached TTS mp3's duration so caption events match audio length."""
    try:
        from pydub import AudioSegment
    except ImportError:
        return 0.0
    p = TTS_CACHE / f"romulus_{slug}.mp3"
    if not p.exists():
        return 0.0
    try:
        return AudioSegment.from_mp3(str(p)).duration_seconds
    except Exception:
        return 0.0


# Wigella's Whisper-segmented quote, offset by FIGHT scene start at runtime.
# Lifted from E:/AI/CVS/mpc/index/clips/20260425_170500.json (large-v3 model).
WIGELLA_SEGMENTS = [
    (0.00, 2.48, "Legislation that would take masks off ICE."),
    (2.48, 9.04, "We've stood with Dana Nessel, suing the federal government."),
]


def build_caption_events():
    """
    Build (start, end, text) events for the transcript layer.
    - HOOK / STAKES / CTA: synth-VO line, duration = cached TTS file length.
    - FIGHT: Wigella's Whisper segments, offset to FIGHT scene start.
    """
    events = []
    fight_start = next(s[0] for s in SCENES if s[2] == "fight")

    for line in NARRATION_LINES:
        dur = measure_tts_duration(line["slug"])
        if dur > 0.0:
            events.append({"start": line["start"],
                           "end":   line["start"] + dur,
                           "text":  line["text"]})

    for t0, t1, txt in WIGELLA_SEGMENTS:
        events.append({"start": fight_start + t0,
                       "end":   fight_start + t1,
                       "text":  txt})

    events.sort(key=lambda e: e["start"])
    return events


def render_caption_strip(text, size=66, max_w=1000,
                         fill=(255, 255, 255, 255),
                         stroke_fill=(0, 0, 0, 255), stroke_w=5,
                         pad_y=16):
    """
    TikTok-style transcript strip — stroked white text on transparent bg.
    Strip height is sized dynamically to fit the wrapped text plus padding,
    so multi-line captions don't clip at the top edge.
    """
    # Pre-measure to determine line count
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    fnt = font(size, bold=True)
    lines = wrap(measure, text, fnt, max_w)
    line_h = int(size * 1.18)
    block_h = line_h * len(lines)
    strip_h = block_h + 2 * (pad_y + stroke_w)

    img = Image.new("RGBA", (W, strip_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y0 = pad_y + stroke_w
    for i, line in enumerate(lines):
        l, t, r, b = draw.textbbox((0, 0), line, font=fnt)
        draw_x = (W - (r - l)) // 2 - l
        draw_y = y0 + i * line_h - t
        draw.text((draw_x, draw_y), line, font=fnt, fill=fill,
                  stroke_width=stroke_w, stroke_fill=stroke_fill)
    return np.array(img)


def make_caption_clips(events):
    """
    Timeline-positioned caption ImageClips composited as the top layer.
    Strips are anchored to CAPTION_BOTTOM so multi-line captions push UPWARD
    into the video well rather than clipping at the top of a fixed strip.
    """
    clips = []
    for ev in events:
        rgba = render_caption_strip(ev["text"])
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3].astype(np.float32) / 255.0
        dur = max(0.05, ev["end"] - ev["start"])
        clip = ImageClip(rgb).set_duration(dur)
        clip = clip.set_mask(ImageClip(alpha, ismask=True).set_duration(dur))
        y_pos = CAPTION_BOTTOM - rgba.shape[0]
        clip = clip.set_start(ev["start"]).set_position((0, y_pos))
        clip = clip.crossfadein(min(0.12, dur / 4))
        clips.append(clip)
    return clips


def extract_audio_segment(path, t0, t1):
    """
    Extract `t0..t1` seconds of audio from `path`, downmix to mono at SR,
    return float32 numpy array. Returns None if the file has no audio or
    the range is empty.

    Uses ffmpeg directly because MoviePy 1.0.3's `audio.to_soundarray()`
    breaks against modern NumPy (the generator/sequence stack TypeError).
    """
    import subprocess
    import tempfile

    dur = float(t1 - t0)
    if dur <= 0:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{float(t0):.3f}", "-t", f"{dur:.3f}",
            "-i", str(path),
            "-vn", "-ac", "1", "-ar", str(SR),
            "-acodec", "pcm_s16le",
            tmp,
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            return None
        with wave.open(tmp, "rb") as w:
            n = w.getnframes()
            if n == 0:
                return None
            raw = w.readframes(n)
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass
    return arr


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main():
    print("Building MPC Romulus Rapid Response (30s)...")

    # Pre-warm the TTS cache so caption durations can be read from disk.
    # build_caption_events() reads each cached mp3 to size each caption to its
    # actual VO length, so the synth must run before captions are built.
    print("\n[pre-warm] generating any missing TTS now...")
    synthesize_narration(load_env())

    # (slug, render_fn, duration, fadein, fadeout)
    scene_specs = [
        ("hook",   render_hook,   4.0,  0.0, 0.0),
        ("stakes", render_stakes, 10.5, 0.4, 0.0),
        ("fight",  render_fight,   9.0, 0.4, 0.0),
        ("cta",    render_cta,     6.5, 0.5, 0.4),
    ]
    clips = []
    for slug, fn, dur, fadein, fadeout in scene_specs:
        spec = FOOTAGE.get(slug)
        if spec is None:
            print(f"[video/{slug}] no footage well — full chrome")
        else:
            shots = spec if isinstance(spec, list) else [spec]
            for k, s in enumerate(shots):
                tag = f"[video/{slug}]" if len(shots) == 1 else f"[video/{slug}#{k}]"
                print(f"{tag} {Path(s['path']).name} "
                      f"t={s['in_t']}..{s['out_t']}"
                      f"{' crop_x=%.2f' % s['crop_x_frac'] if 'crop_x_frac' in s else ''}")
        clips.append(build_scene_clip(fn, spec, dur, fadein=fadein, fadeout=fadeout))
    video = concatenate_videoclips(clips, method="compose").set_duration(DURATION)

    # Transcript caption layer composited over the entire timeline
    print("\n[captions] building transcript events...")
    events = build_caption_events()
    for ev in events:
        print(f"  {ev['start']:5.2f}-{ev['end']:5.2f}  {ev['text']}")
    caption_clips = make_caption_clips(events)
    if caption_clips:
        video = CompositeVideoClip([video, *caption_clips],
                                   size=(W, H)).set_duration(DURATION)

    mix = build_audio()
    write_wav(mix)
    audio_clip = AudioFileClip(str(AUDIO_PATH)).set_duration(DURATION)
    video = video.set_audio(audio_clip)

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
