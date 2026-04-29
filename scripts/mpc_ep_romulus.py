"""
MPC Romulus Rapid Response — 30s vertical social video.

Composites real source footage from the Ice Out Romulus rally with brand
chrome (text, logo, scene overlays) + audio (harmonic hum chord per scene
+ ElevenLabs narration + Wigella native sync sound on the FIGHT beat).

Migrated to import shared infrastructure from `cvs_lib`. Romulus is the
most divergent reel: 4-scene structure (hook/stakes/fight/cta) with
SCENE_CHORDS keyed by slug, narration timed by absolute scene-timeline
"start" (not "start_in_beat"), Wigella native-audio FIGHT beat instead
of synth VO, and per-scene custom chrome that doesn't fit the
ChromeRenderer mold. Those pieces stay local; everything else (synth,
ducking, footage prep, caption strip render, TTS HTTP, rotation cache,
.env loader) delegates to `cvs_lib`.

Scenes:
  0:00-0:04    HOOK   — A minor — chant footage  — "Hundreds of us marched..."
  0:04-0:14.5  STAKES — D minor — warehouse + chant — "DHS bought a warehouse..."
  0:14.5-0:23.5 FIGHT — C major — Wigella sync   — "stood with Dana Nessel..."
  0:23.5-0:30  CTA    — A major — split chrome   — "Chip in. Link below..."

Output: E:/AI/CVS/ComfyUI/output/mpc/romulus_rapid_response.mp4
Run:    python E:/AI/CVS/scripts/mpc_ep_romulus.py
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

# Make `import cvs_lib` work when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from cvs_lib import audio as cvs_audio
from cvs_lib import captions as cvs_captions
from cvs_lib import elevenlabs_tts as cvs_tts
from cvs_lib import moviepy_helpers as cvs_movie
from cvs_lib.env import load_env
from cvs_lib.preflight import run_or_exit as _preflight
from cvs_lib.preview import render_beat_stills as _render_beat_stills

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
TTS_PREFIX = "romulus"

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")

BANNER_H = 140
WELL_TOP = BANNER_H
WELL_BOTTOM = 1750
WELL_H = WELL_BOTTOM - WELL_TOP
CAPTION_BOTTOM = 1620

CTA_CHROME_BOTTOM = 720
CTA_WELL_TOP = 720
CTA_WELL_BOTTOM = 1920
CTA_WELL_H = CTA_WELL_BOTTOM - CTA_WELL_TOP

FOOTAGE = {
    "hook":   {"path": RAW_DIR / "20260425_170030.mp4", "in_t": 0.5,  "out_t": 4.5,
               "audio_gain": 1.0},
    "stakes": [
        {"path": RAW_DIR / "20260425_151118.mp4", "in_t": 0.0,  "out_t": 4.5,
         "crop_x_frac": 0.62, "audio_gain": 1.0},
        {"path": RAW_DIR / "20260425_170030.mp4", "in_t": 10.0, "out_t": 16.0,
         "audio_gain": 1.0},
    ],
    "fight":  {"path": RAW_DIR / "20260425_170500.mp4", "in_t": 0.0, "out_t": 9.0,
               "audio_in": 0.0, "audio_out": 9.0, "audio_gain": 1.4},
    "cta":    {"path": RAW_DIR / "20260425_170245.mp4", "in_t": 8.0, "out_t": 14.5,
               "audio_gain": 0.7,
               "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H},
}

# --------------------------------------------------------------------------- #
# Color grade (rainy-day footage + pastel chrome was reading washed-out and
# low-energy). Recipe: punchier S-curve, +40% saturation, +0.08 gamma lift,
# warm shadows/highlights, slightly cool blacks. Applied once per source via
# ffmpeg, cached by mtime + recipe hash. Only the well content is graded —
# brand chrome (logos, gradients, text) is untouched.
# --------------------------------------------------------------------------- #

GRADE_VF = (
    "curves=preset=medium_contrast,"
    "eq=saturation=1.20:gamma=0.96:contrast=1.03,"
    "colorbalance=rh=0.04:gh=0.01:bh=-0.03"
)
_GRADE_CACHE_DIR = OUTPUT_DIR / "_grade_cache"


def grade_baked_path(path: Path, *, vf: str = GRADE_VF,
                     cache_dir: Path = _GRADE_CACHE_DIR) -> Path:
    """Return a graded copy of `path` in `cache_dir`, baking once via ffmpeg.
    Cache key = recipe hash + source mtime."""
    path = Path(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(vf.encode("utf-8")).hexdigest()[:8]
    out = cache_dir / f"{path.stem}_g{key}.mp4"
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    print(f"[grade] baking {path.name} -> {out.name}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", str(path),
           "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-c:a", "copy",
           str(out)]
    subprocess.run(cmd, check=True)
    return out


def _apply_grade_to_footage():
    """Remap every FOOTAGE spec's `path` to its graded copy."""
    for slug, spec in FOOTAGE.items():
        shots = spec if isinstance(spec, list) else [spec]
        for s in shots:
            s["path"] = grade_baked_path(s["path"])


_apply_grade_to_footage()

# --------------------------------------------------------------------------- #
# Audio config
# --------------------------------------------------------------------------- #

SR = 44100
N = int(SR * DURATION)

SCENES = [
    (0.0,  4.0,  "hook",   "OPEN"),
    (4.0,  14.5, "stakes", "STAKES"),
    (14.5, 23.5, "fight",  "THE FIGHT"),
    (23.5, 30.0, "cta",    "CTA"),
]

# SCENE_CHORDS keyed by slug directly (vs the other 7 reels which key by
# minor/grief/build/resolve). cvs_audio.harmonic_hum tolerates any keying as
# long as every beat's chord_key (BEATS[i][2]) is a key of scene_chords. We
# build a synthetic BEATS list where slug == chord_key so the lib resolves
# `chord_for_slug[slug]` to slug, then `scene_chords[slug]` to the notes.
SCENE_CHORDS = {
    "hook":   [110.00, 164.81, 220.00],
    "stakes": [73.42,  110.00, 146.83, 174.61],
    "fight":  [130.81, 196.00, 261.63, 329.63],
    "cta":    [110.00, 164.81, 220.00, 277.18],
}

NARRATION_LINES = [
    {"slug": "hook",   "start": 0.30,
     "text": "Today, hundreds of us marched in Romulus."},
    {"slug": "stakes", "start": 4.30,
     "text": "DHS bought a warehouse near Metro Airport. We march for our neighbors."},
    {"slug": "cta",    "start": 23.90,
     "text": "Chip in to the Michigan Progressive Caucus. Link below. We don't back down."},
]

CTA_URL = "secure.actblue.com/donate/michigan-progressive-caucus-1"

# --------------------------------------------------------------------------- #
# PIL helpers (kept local — romulus chrome is too bespoke for ChromeRenderer)
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


def measure_text_bbox(draw, text, fnt, x_center, top):
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    draw_x = x_center - w // 2 - l
    draw_y = top - t
    bbox = (draw_x + l, draw_y + t, draw_x + r, draw_y + b)
    return bbox, draw_x, draw_y


def draw_centered_text(draw, text, fnt, x_center, top, fill,
                       shadow_offset=None, shadow_color=(0, 0, 0, 200)):
    bbox, dx, dy = measure_text_bbox(draw, text, fnt, x_center, top)
    if shadow_offset:
        sx, sy = shadow_offset
        draw.text((dx + sx, dy + sy), text, font=fnt, fill=shadow_color)
        bbox = (bbox[0], bbox[1], bbox[2] + max(sx, 0), bbox[3] + max(sy, 0))
    draw.text((dx, dy), text, font=fnt, fill=fill)
    return bbox


def check_overlaps(scene_name, elements, padding=4, fail_on_overlap=False):
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


def draw_top_banner(img, banner_h=BANNER_H, target_w=560):
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


def draw_lower_third_pill(img, label, y=1140, color=None):
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
    draw_x = x + pad_x - l
    draw_y = y + pad_y - t
    draw.text((draw_x, draw_y), label, font=fnt, fill=(*C["white"], 255))
    return (x, y, x + pill_w, y + pill_h)


def draw_giant_callout(img, label, top_y, size=240, color=None,
                       sub=None, sub_size=50, sub_gap=None):
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
            sub_gap = max(28, int(size * 0.18))
        sub_top = label_bbox[3] + sub_gap
        sub_bbox = draw_centered_text(draw, sub, sub_fnt, W // 2, sub_top,
                                      fill=(*C["white"], 255),
                                      shadow_offset=(3, 3),
                                      shadow_color=(0, 0, 0, 200))
    return label_bbox, sub_bbox


# --------------------------------------------------------------------------- #
# Per-scene renderers (custom chrome — kept local)
# --------------------------------------------------------------------------- #

def render_hook(well_transparent=False):
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    elems = []
    elems.append(("well", draw_well_placeholder(
        img,
        well_color_top=(60, 50, 70),
        well_color_bottom=(25, 20, 35),
        footage_hint="protest crowd, signs, marchers on Cogswell",
        transparent=well_transparent)))

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
    bg_full = gradient_bg(C["sky_blue"], C["soft_pink"], angle_deg=300)
    bg_full[CTA_CHROME_BOTTOM:, :, :] = 0
    img = Image.fromarray(bg_full).convert("RGBA")
    if well_transparent:
        bot = np.zeros((CTA_WELL_H, W, 4), dtype=np.uint8)
        img.paste(Image.fromarray(bot, "RGBA"), (0, CTA_WELL_TOP))
    else:
        tint = np.zeros((CTA_WELL_H, W, 4), dtype=np.uint8)
        tint[..., :3] = (40, 30, 50)
        tint[..., 3] = 255
        img.paste(Image.fromarray(tint, "RGBA"), (0, CTA_WELL_TOP))

    draw = ImageDraw.Draw(img, "RGBA")
    elems = []

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

    tag_top = bar_bot + 30
    tag_bbox = draw_centered_text(
        draw, "WE DON'T BACK DOWN", font(70, bold=True), W // 2, tag_top,
        fill=(*C["white"], 255),
        shadow_offset=(4, 4),
        shadow_color=(*C["deep_magenta"], 230))
    elems.append(("tagline", tag_bbox))

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
# Audio: harmonic hum + narration + source-audio + ducking
# --------------------------------------------------------------------------- #

def harmonic_hum():
    """Build the full hum track. Romulus uses overlap=0.5 (vs lib default
    0.35) — the synthetic BEATS list (slug == chord_key) lets the lib
    resolve every scene's slug straight back to SCENE_CHORDS.
    """
    scenes_3tup = [(t0, t1, slug) for t0, t1, slug, _ in SCENES]
    beats_for_hum = [
        (slug, t1 - t0, slug, "", {})
        for t0, t1, slug, _ in SCENES
    ]
    return cvs_audio.harmonic_hum(
        scenes_3tup, beats_for_hum, SCENE_CHORDS,
        duration=DURATION, sr=SR, overlap=0.5,
    )


def synthesize_narration(env):
    # AI VO disabled 2026-04-26 per editorial call. NARRATION_LINES kept
    # in source for caption alignment but is not voiced. Source audio +
    # harmonic bed remain.
    return None


def build_voice_track():
    env = load_env(ENV_PATH)
    voice = synthesize_narration(env)
    return voice if voice is not None else np.zeros(N, dtype=np.float32)


def _shot_audio_range(shot):
    return float(shot.get("audio_in", shot["in_t"])), \
           float(shot.get("audio_out", shot["out_t"]))


def build_source_audio_track():
    """Per-clip native audio aligned to scene timelines. For multi-shot
    scenes, each shot's audio is placed back-to-back at the scene's start.
    """
    track = np.zeros(N, dtype=np.float32)
    scene_starts = {s[2]: s[0] for s in SCENES}
    fade_n = int(0.05 * SR)
    for slug, spec in FOOTAGE.items():
        if spec is None:
            continue
        shots = spec if isinstance(spec, list) else [spec]
        offset_s = 0.0
        for shot in shots:
            video_dur = float(shot["out_t"]) - float(shot["in_t"])
            a0, a1 = _shot_audio_range(shot)
            src = cvs_movie.rotation_baked_path(shot["path"], cache_dir=_ROT_CACHE_DIR)
            seg = cvs_audio.extract_audio_segment(src, a0, a1, sr=SR)
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


def build_audio():
    print("[audio] rendering harmonic hum (chord per scene)...")
    bed = harmonic_hum()
    print("[audio] building voice track (synth TTS)...")
    voice = build_voice_track()
    print("[audio] building source-audio track from clips...")
    source = build_source_audio_track()

    print("[audio] ducking source audio under VO (50% during VO, 100% otherwise)...")
    source = source * cvs_audio.vo_duck_envelope(voice, total_n=N, sr=SR, low_gain=0.5)

    speech = voice + source
    has_speech = float(np.max(np.abs(speech))) > 1e-4
    if has_speech:
        print("[audio] sidechain ducking hum under voice + source...")
        bed = cvs_audio.sidechain_duck(bed, speech, sr=SR)

    mix = bed * 0.5 + voice * 1.0 + source * 1.0
    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.9
    return mix


def write_wav(mono, path=AUDIO_PATH):
    cvs_audio.write_wav(mono, path, sr=SR)
    print(f"[audio] wrote {path}")
    return path


# --------------------------------------------------------------------------- #
# Footage compositor
# --------------------------------------------------------------------------- #

_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"


def _spec_well(spec):
    s = spec[0] if isinstance(spec, list) else spec
    return int(s.get("well_top", WELL_TOP)), int(s.get("well_h", WELL_H))


def prepare_footage(spec, duration):
    _, well_h = _spec_well(spec)
    return cvs_movie.prepare_footage(
        spec, target_w=W, well_h=well_h, duration=duration,
        rotation_cache_dir=_ROT_CACHE_DIR,
    )


def build_scene_clip(render_fn, footage_spec, duration, fadein=0.0, fadeout=0.0):
    """Scene = [black bg] + [footage in well, if any] + [chrome on top].
    None footage → chrome-only full-frame.
    """
    if footage_spec is None:
        rgba = render_fn(well_transparent=False)
        clip = ImageClip(rgba[:, :, :3]).set_duration(duration)
    else:
        chrome_rgba = render_fn(well_transparent=True)
        chrome = cvs_movie.make_chrome_clip(chrome_rgba, duration)

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


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

# Wigella's Whisper-segmented quote, offset by FIGHT scene start at runtime.
WIGELLA_SEGMENTS = [
    (0.00, 2.48, "Legislation that would take masks off ICE."),
    (2.48, 9.04, "We've stood with Dana Nessel, suing the federal government."),
]


def measure_tts_duration(slug):
    return cvs_tts.measure_tts_duration(
        slug, cache_dir=TTS_CACHE, cache_prefix=TTS_PREFIX,
    )


def build_caption_events():
    """Synth-VO captions from NARRATION_LINES (absolute t) +
    Wigella native-segment captions offset by FIGHT scene start.
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


def make_caption_clips(events):
    return cvs_captions.make_caption_clips(
        events, width=W, caption_bottom=CAPTION_BOTTOM,
        font_path=FONT_HEADLINE, size=66, max_w=1000,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def _preview_beats():
    """Synthesize a BEATS-shaped list from SCENES + FOOTAGE so the
    preview helper can iterate it like the other reels."""
    chip_for_slug = {"hook": "ROMULUS", "stakes": "DHS WAREHOUSE",
                     "fight": "MAY 18", "cta": "CHIP IN"}
    out = []
    for t0, t1, slug, _ in SCENES:
        spec = FOOTAGE.get(slug)
        out.append((slug, t1 - t0, slug, chip_for_slug.get(slug, ""), spec))
    return out


def _chrome_for_preview(slug, chip_label, spec):
    return {
        "hook": render_hook,
        "stakes": render_stakes,
        "fight": render_fight,
        "cta": render_cta,
    }[slug](well_transparent=True)


def _spec_well_for_preview(spec):
    return _spec_well(spec) if spec is not None else (WELL_TOP, WELL_H)


def main():
    print("Building MPC Romulus Rapid Response (30s)...")

    if "--preview" in sys.argv:
        out = OUTPUT_DIR / "_preview" / "romulus"
        _render_beat_stills(
            beats=_preview_beats(), out_dir=out,
            chrome_for=_chrome_for_preview, spec_well=_spec_well_for_preview,
            W=W, H=H, rotation_cache_dir=_ROT_CACHE_DIR,
        )
        return

    # Preflight: validate sources + scene-sum, on a synthetic BEATS list.
    _preflight(_preview_beats(), DURATION, rotation_cache_dir=_ROT_CACHE_DIR,
               reel_slug="romulus")

    print("\n[pre-warm] generating any missing TTS now...")
    synthesize_narration(load_env(ENV_PATH))

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
