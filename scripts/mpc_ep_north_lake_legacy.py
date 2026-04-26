"""
MPC "North Lake" — 30s vertical reel, the testimony angle.

Different lever from the other reels in the suite: not receipts (Follow
the Money), not identity (Detroit Knows), not authority (Abolish ICE
Congress), not duration (Ten Weeks), not energy (People Power). This
one names *who's inside*: a translated message from Juan, released
April 24 after 90 days at the North Lake detention center.

Every other reel in the suite features MPC organizers, legislators,
or activists speaking on behalf of those locked up. This reel hands
the mic — through a translator — to someone who was actually in.

Beats (30s):
  0:00-0:07  HOOK     — Dm — "I was released Friday — April 24."
                        (155313 13.0-20.0)
  0:07-0:15  INSIDE   — Am — "The conditions right now are very upsetting"
                        (155313 20.0-28.0)
  0:15-0:25  THE LAW  — Dm — "Federal judges issuing very high bond awards
                        ... denials of bond in asylum cases."
                        (155313 30.4-40.4)
  0:25-0:30  CTA      — A  — chrome + chant b-roll + synth VO
                        "Free them all. Stand with Juan. Chip in. Link in bio."

Output: E:/AI/CVS/ComfyUI/output/mpc/north_lake.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_north_lake.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

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
from cvs_lib.elevenlabs_tts import (
    measure_tts_duration as _lib_measure_tts_duration,
    synthesize_narration as _lib_synthesize_narration,
)
from cvs_lib.env import load_env as _lib_load_env

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
OUTPUT_PATH = OUTPUT_DIR / "north_lake.mp4"
AUDIO_PATH = OUTPUT_DIR / "north_lake_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
TTS_PREFIX = "nlk"
_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")

# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

BANNER_H = 140
WELL_TOP = BANNER_H
WELL_BOTTOM = 1750
WELL_H = WELL_BOTTOM - WELL_TOP
CAPTION_BOTTOM = 1620
CHIP_Y = 168

CTA_CHROME_BOTTOM = 720
CTA_WELL_TOP = 720
CTA_WELL_H = H - CTA_WELL_TOP

# --------------------------------------------------------------------------- #
# Beats
# --------------------------------------------------------------------------- #

JUAN = RAW_DIR / "20260425_155313.mp4"
CHANT = RAW_DIR / "20260425_170030.mp4"

BEATS = [
    # HOOK: who Juan is, when he got out. The date specificity ("Friday,
    # April 24") matters — it makes him a real person, not a case study.
    # Source 13.0-20.0 catches "So this is from Juan, good morning. I was
    # released Friday the 24th of April. I was detained for three months
    # at North Lake, 90 days." — the establishing line + setup.
    ("hook", 7.0, "grief", "RELEASED  •  APRIL 24",
     {"path": JUAN, "in_t": 13.0, "out_t": 20.0,
      "audio_gain": 1.25,
      "caption_lines": [
          (0.0, 2.5, "So this is from Juan."),
          (2.7, 6.7, "I was released Friday — April 24."),
      ]}),
    # INSIDE: the conditions. Source 20.0-28.0 captures the conditions line
    # cleanly. Speech ends ~27.5; 0.5s post-roll for the line to land.
    ("inside", 8.0, "minor", "90 DAYS AT NORTH LAKE",
     {"path": JUAN, "in_t": 20.0, "out_t": 28.0,
      "audio_gain": 1.25,
      "caption_lines": [
          (0.0, 7.7,
           "The conditions right now are very upsetting — ICE is not following the law."),
      ]}),
    # THE LAW: the structural claim — judges denying bond, gaming asylum
    # cases. Source 30.4-40.4 captures the full federal-judges sequence.
    ("law", 10.0, "grief", "JUDGES IGNORING THE LAW",
     {"path": JUAN, "in_t": 30.4, "out_t": 40.4,
      "audio_gain": 1.25,
      "caption_lines": [
          (0.0, 3.0, "Federal judges decide on their own terms."),
          (3.2, 9.5,
           "Very high bond awards — denials of bond in asylum cases."),
      ]}),
    # CTA: brand chrome top + chant b-roll bottom. Synth VO closes.
    ("cta", 5.0, "resolve", "FREE THEM ALL",
     {"path": CHANT, "in_t": 8.0, "out_t": 13.0,
      "audio_gain": 0.5,
      "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H}),
]
# Sanity: 7+8+10+5 = 30 ✓

def _build_scenes():
    out, t = [], 0.0
    for slug, dur, *_ in BEATS:
        out.append((t, t + dur, slug))
        t += dur
    return out

SCENES = _build_scenes()

# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #

SR = 44100
N = int(SR * DURATION)

SCENE_CHORDS = {
    "minor":   [110.00, 164.81, 220.00],
    "grief":   [73.42,  110.00, 146.83, 174.61],
    "build":   [130.81, 196.00, 261.63],
    "resolve": [110.00, 164.81, 220.00, 277.18],
}

NARRATION_LINES = [
    {"slug": "cta", "start_in_beat": 0.4,
     "text": "Free them all. Stand with Juan. Chip in. Link in bio."},
]

CTA_URL = "secure.actblue.com/donate/michigan-progressive-caucus-1"
CTA_HEADLINE = "FREE THEM ALL"
CTA_SUBHEAD = "STAND WITH JUAN"

# --------------------------------------------------------------------------- #
# PIL helpers
# --------------------------------------------------------------------------- #

def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_HEADLINE if bold else FONT_BODY, size)


def text_size(draw, txt, fnt):
    l, t, r, b = draw.textbbox((0, 0), txt, font=fnt)
    return r - l, b - t


def wrap(draw, text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if text_size(draw, trial, fnt)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
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
    return (draw_x + l, draw_y + t, draw_x + r, draw_y + b), draw_x, draw_y


def draw_centered_text(draw, text, fnt, x_center, top, fill,
                       shadow_offset=None, shadow_color=(0, 0, 0, 200)):
    bbox, dx, dy = measure_text_bbox(draw, text, fnt, x_center, top)
    if shadow_offset:
        sx, sy = shadow_offset
        draw.text((dx + sx, dy + sy), text, font=fnt, fill=shadow_color)
        bbox = (bbox[0], bbox[1], bbox[2] + max(sx, 0), bbox[3] + max(sy, 0))
    draw.text((dx, dy), text, font=fnt, fill=fill)
    return bbox


# --------------------------------------------------------------------------- #
# Brand chrome
# --------------------------------------------------------------------------- #

def draw_top_banner(img, banner_h=BANNER_H, target_w=560):
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, W, banner_h), fill=(*C["white"], 255))
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    img.paste(logo, ((W - target_w) // 2, (banner_h - new_h) // 2), logo)


def draw_proof_chip(img, label, chip_color=None):
    if chip_color is None:
        chip_color = C["deep_magenta"]
    draw = ImageDraw.Draw(img, "RGBA")
    fnt = font(38, bold=True)
    l, t, r, b = draw.textbbox((0, 0), label, font=fnt)
    tw, th = r - l, b - t
    pad_x, pad_y = 32, 16
    pill_w, pill_h = tw + pad_x * 2, th + pad_y * 2
    x = (W - pill_w) // 2
    y = CHIP_Y
    draw.rounded_rectangle((x, y, x + pill_w, y + pill_h),
                           radius=pill_h // 2, fill=(*chip_color, 240))
    draw.text((x + pad_x - l, y + pad_y - t),
              label, font=fnt, fill=(*C["white"], 255))


def draw_well(img, well_top=WELL_TOP, well_h=WELL_H, transparent=True,
              c_top=(40, 30, 50), c_bot=(15, 10, 20)):
    if transparent:
        well = np.zeros((well_h, W, 4), dtype=np.uint8)
        img.paste(Image.fromarray(well, "RGBA"), (0, well_top))
        return
    well = np.zeros((well_h, W, 4), dtype=np.uint8)
    for i in range(well_h):
        t = i / max(1, well_h - 1)
        well[i, :, 0] = int(c_top[0] * (1 - t) + c_bot[0] * t)
        well[i, :, 1] = int(c_top[1] * (1 - t) + c_bot[1] * t)
        well[i, :, 2] = int(c_top[2] * (1 - t) + c_bot[2] * t)
        well[i, :, 3] = 255
    img.paste(Image.fromarray(well, "RGBA"), (0, well_top))


# Testimony reel: magenta on the human (release date — Juan as person),
# magenta on the lived condition, sky on the structural claim (judges
# acting outside the law — institutional accountability), magenta on CTA.
CHIP_COLORS = {
    "hook":   C["deep_magenta"],
    "inside": C["deep_magenta"],
    "law":    C["sky_blue"],
    "cta":    C["deep_magenta"],
}


def render_beat_chrome(slug, chip_label, well_transparent=True):
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    draw_well(img, transparent=well_transparent)
    draw_top_banner(img)
    if chip_label:
        draw_proof_chip(img, chip_label, chip_color=CHIP_COLORS.get(slug))
    return np.array(img)


def render_cta_chrome(well_transparent=True):
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

    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_w = 720
    ratio = target_w / logo.width
    new_h = int(logo.height * ratio)
    logo = logo.resize((target_w, new_h), Image.LANCZOS)
    bar_y = 60
    pad = 36
    bar_top = bar_y - pad
    bar_bot = bar_y + new_h + pad
    bar = Image.new("RGBA", (W, new_h + pad * 2), (*C["white"], 255))
    img.paste(bar, (0, bar_top), bar)
    img.paste(logo, ((W - target_w) // 2, bar_y), logo)

    tag_top = bar_bot + 22
    tag_bbox = draw_centered_text(
        draw, CTA_HEADLINE, font(96, bold=True), W // 2, tag_top,
        fill=(*C["white"], 255),
        shadow_offset=(4, 4),
        shadow_color=(*C["deep_magenta"], 240))

    sub_top = tag_bbox[3] + 16
    sub_bbox = draw_centered_text(
        draw, CTA_SUBHEAD, font(44, bold=True), W // 2, sub_top,
        fill=(*C["white"], 255))

    url_fnt = font(28, bold=True)
    ul, ut, ur, ub = draw.textbbox((0, 0), CTA_URL, font=url_fnt)
    url_tw, url_th = ur - ul, ub - ut
    plate_w = url_tw + 70
    plate_h = url_th + 40
    plate_x = (W - plate_w) // 2
    plate_y = sub_bbox[3] + 18
    draw.rounded_rectangle((plate_x, plate_y, plate_x + plate_w, plate_y + plate_h),
                           radius=20, fill=(*C["white"], 250))
    draw.text((plate_x + 35 - ul, plate_y + 20 - ut),
              CTA_URL, font=url_fnt, fill=(*C["deep_magenta"], 255))

    handle_top = plate_y + plate_h + 18
    draw_centered_text(
        draw, "Link in bio  •  @michiganprogressive",
        font(32, bold=False), W // 2, handle_top,
        fill=(*C["white"], 255))

    return np.array(img)


# --------------------------------------------------------------------------- #
# Audio synthesis (delegates to cvs_lib.audio + cvs_lib.elevenlabs_tts)
# --------------------------------------------------------------------------- #

def _scene_start(slug):
    return next(s[0] for s in SCENES if s[2] == slug)


def load_env(path=ENV_PATH):
    return _lib_load_env(path)


def harmonic_hum():
    return cvs_audio.harmonic_hum(
        SCENES, BEATS, SCENE_CHORDS,
        duration=DURATION, sr=SR,
    )


def synthesize_narration(env):
    return _lib_synthesize_narration(
        env, NARRATION_LINES,
        cache_dir=TTS_CACHE, cache_prefix=TTS_PREFIX,
        duration=DURATION, scene_start=_scene_start, sr=SR,
    )


def measure_tts_duration(slug):
    return _lib_measure_tts_duration(
        slug, cache_dir=TTS_CACHE, cache_prefix=TTS_PREFIX)


def sidechain_duck(bed, voice, threshold=0.025, ratio=0.30,
                   attack_ms=20.0, release_ms=180.0):
    return cvs_audio.sidechain_duck(
        bed, voice, sr=SR, threshold=threshold, ratio=ratio,
        attack_ms=attack_ms, release_ms=release_ms,
    )


def vo_duck_envelope(voice, threshold=0.02, low_gain=0.5,
                     attack_ms=10.0, release_ms=200.0):
    return cvs_audio.vo_duck_envelope(
        voice, total_n=N, sr=SR, threshold=threshold, low_gain=low_gain,
        attack_ms=attack_ms, release_ms=release_ms,
    )


def to_int16_stereo(mono):
    return cvs_audio.to_int16_stereo(mono)


# --------------------------------------------------------------------------- #
# Footage compositor
# --------------------------------------------------------------------------- #

def _get_rotation(path):
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
    s = spec[0] if isinstance(spec, list) else spec
    return int(s.get("well_top", WELL_TOP)), int(s.get("well_h", WELL_H))


def prepare_footage(spec, duration):
    specs = spec if isinstance(spec, list) else [spec]
    _, well_h = _spec_well(spec)
    sub_clips = [prepare_one_clip(s, well_h) for s in specs]
    out = sub_clips[0] if len(sub_clips) == 1 else concatenate_videoclips(
        sub_clips, method="compose")
    return out.set_duration(duration)


def make_chrome_clip(rgba, duration):
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    chrome = ImageClip(rgb).set_duration(duration)
    mask = ImageClip(alpha, ismask=True).set_duration(duration)
    return chrome.set_mask(mask)


def build_beat_clip(slug, chip_label, footage_spec, duration,
                    is_cta, fadein=0.0, fadeout=0.0):
    if is_cta:
        chrome_rgba = render_cta_chrome(well_transparent=True)
    else:
        chrome_rgba = render_beat_chrome(slug, chip_label, well_transparent=True)
    chrome = make_chrome_clip(chrome_rgba, duration)
    well_top, _ = _spec_well(footage_spec)
    footage = prepare_footage(footage_spec, duration).set_position((0, well_top))
    bg = ColorClip(size=(W, H), color=(0, 0, 0)).set_duration(duration)
    clip = CompositeVideoClip([bg, footage, chrome], size=(W, H)).set_duration(duration)
    if fadein > 0:
        clip = clip.crossfadein(fadein)
    if fadeout > 0:
        clip = clip.crossfadeout(fadeout)
    return clip


# --------------------------------------------------------------------------- #
# Audio mix
# --------------------------------------------------------------------------- #

def _shot_audio_range(shot):
    return float(shot.get("audio_in", shot["in_t"])), \
           float(shot.get("audio_out", shot["out_t"]))


def extract_audio_segment(path, t0, t1):
    return cvs_audio.extract_audio_segment(path, t0, t1, sr=SR)


def build_source_audio_track():
    track = np.zeros(N, dtype=np.float32)
    fade_n = int(0.05 * SR)
    for slug, _dur, _chord, _label, spec in BEATS:
        if spec is None:
            continue
        a0, a1 = _shot_audio_range(spec)
        seg = extract_audio_segment(_rotation_baked_path(spec["path"]), a0, a1)
        if seg is None:
            continue
        gain = float(spec.get("audio_gain", 1.0))
        if len(seg) > 2 * fade_n:
            seg[:fade_n] *= np.linspace(0, 1, fade_n)
            seg[-fade_n:] *= np.linspace(1, 0, fade_n)
        place_t = _scene_start(slug)
        i0 = int(place_t * SR)
        i1 = min(N, i0 + len(seg))
        track[i0:i1] += seg[: i1 - i0] * gain
        print(f"[audio/{slug}] +{Path(spec['path']).name} a={a0:.2f}..{a1:.2f}s "
              f"@ t={place_t:.2f}s gain={gain}")
    return track


def build_audio():
    print("[audio] harmonic hum...")
    bed = harmonic_hum()
    print("[audio] synth VO (CTA only)...")
    voice = synthesize_narration(load_env())
    if voice is None:
        voice = np.zeros(N, dtype=np.float32)
    print("[audio] source-audio track...")
    source = build_source_audio_track()

    source = source * vo_duck_envelope(voice, low_gain=0.45)

    speech = voice + source
    if float(np.max(np.abs(speech))) > 1e-4:
        bed = sidechain_duck(bed, speech)

    mix = bed * 0.5 + voice * 1.0 + source * 1.0
    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.9
    return mix


def write_wav(mono, path=AUDIO_PATH):
    cvs_audio.write_wav(mono, path, sr=SR)
    print(f"[audio] wrote {path}")


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

def build_caption_events():
    events = []
    for slug, dur, _chord, _label, spec in BEATS:
        if spec is None:
            continue
        scene_t0 = _scene_start(slug)
        if slug == "cta":
            for line in NARRATION_LINES:
                if line["slug"] != "cta":
                    continue
                vo_dur = measure_tts_duration("cta")
                if vo_dur > 0.0:
                    start = scene_t0 + line["start_in_beat"]
                    events.append({"start": start,
                                   "end":   min(scene_t0 + dur, start + vo_dur),
                                   "text":  line["text"]})
            continue
        if "caption_lines" in spec:
            for s_start, s_end, text in (spec.get("caption_lines") or []):
                events.append({"start": scene_t0 + float(s_start),
                               "end":   scene_t0 + float(s_end),
                               "text":  text.strip()})
    events.sort(key=lambda e: e["start"])
    return events


def render_caption_strip(text, size=64, max_w=1000,
                         fill=(255, 255, 255, 255),
                         stroke_fill=(0, 0, 0, 255), stroke_w=5,
                         pad_y=16):
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


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print("Building MPC North Lake (30s testimony reel)...")

    print("\n[pre-warm] generating any missing TTS...")
    synthesize_narration(load_env())

    clips = []
    for idx, (slug, dur, chord, chip_label, spec) in enumerate(BEATS):
        is_first = idx == 0
        is_last = idx == len(BEATS) - 1
        is_cta = slug == "cta"
        fadein = 0.0 if is_first else 0.25
        fadeout = 0.4 if is_last else 0.0
        print(f"[video/{slug}] {Path(spec['path']).name} "
              f"t={spec['in_t']}..{spec['out_t']}  chip={chip_label!r}")
        clips.append(build_beat_clip(slug, chip_label, spec, dur, is_cta,
                                     fadein=fadein, fadeout=fadeout))
    video = concatenate_videoclips(clips, method="compose").set_duration(DURATION)

    print("\n[captions] building events...")
    events = build_caption_events()
    for ev in events:
        print(f"  {ev['start']:5.2f}-{ev['end']:5.2f}  {ev['text'][:80]}")
    cc = make_caption_clips(events)
    if cc:
        video = CompositeVideoClip([video, *cc], size=(W, H)).set_duration(DURATION)

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
