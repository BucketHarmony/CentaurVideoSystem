"""
MPC "We Don't Back Down" — 30s vertical reel, Juan + chant + tagline.

Three beats: a survivor's voice, the chant that names who we're for, and
the tagline as conclusion. No politicians, no opening card — the released
detainee leads, the crowd echoes, MPC closes the loop.

Beats (30s):
  0:00-0:17  JUAN          — Dm — released after 90 days at North Lake .........
                             "I was released Friday the 24th of April. Detained
                              three months at North Lake, 90 days..."
  0:17-0:24  FOR OUR       — Am — chant: locked-inside ........................
                             "This is for our neighbors who are locked inside,
                              together we'll abolish ICE."
  0:24-0:30  WE DON'T      — A  — chant b-roll + tagline + synth VO ............
                             "We don't back down. Chip in. Link in bio."

Output: E:/AI/CVS/ComfyUI/output/mpc/we_dont_back_down.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_we_dont_back_down.py
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
OUTPUT_PATH = OUTPUT_DIR / "we_dont_back_down.mp4"
AUDIO_PATH = OUTPUT_DIR / "we_dont_back_down_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

PALETTE = json.loads((BRAND / "palette.json").read_text(encoding="utf-8"))
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]
FONT_BODY = PALETTE["fonts"]["body"]["path"]
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")

# --------------------------------------------------------------------------- #
# Layout (matches mpc_ep_romulus.py production conventions)
# --------------------------------------------------------------------------- #

BANNER_H = 140
WELL_TOP = BANNER_H
WELL_BOTTOM = 1750
WELL_H = WELL_BOTTOM - WELL_TOP
CAPTION_BOTTOM = 1620

# Proof chip: pill below the top banner that names what kind of evidence
# this beat is contributing to the "we don't back down" argument.
CHIP_Y = 168

# CTA split layout
CTA_CHROME_BOTTOM = 720
CTA_WELL_TOP = 720
CTA_WELL_H = H - CTA_WELL_TOP

# --------------------------------------------------------------------------- #
# Beats. Each entry is one cut: (slug, label_for_chip, chord_key, duration,
# footage spec). chord_key indexes SCENE_CHORDS below.
# --------------------------------------------------------------------------- #

BEATS = [
    # JUAN — released after 90 days at North Lake. Source starts at 11.0 to
    # catch the tail of "So this is from Juan." into his actual testimony.
    # 17s holds through the regulatory critique without going past it.
    ("juan",    17.0, "grief",  "JUAN  •  RELEASED 4/24",
     {"path": RAW_DIR / "20260425_155313.mp4", "in_t": 11.0, "out_t": 28.0,
      "audio_gain": 1.2}),
    # FOR OUR NEIGHBORS — the chant that says who Juan IS to the rally.
    # Bridges from one survivor's voice to the collective answer.
    ("neighbors", 7.0, "minor",  "FOR OUR NEIGHBORS",
     {"path": RAW_DIR / "20260425_170245.mp4", "in_t": 7.5, "out_t": 14.5,
      "audio_gain": 1.0}),
    # CTA — chant b-roll bottom half, brand chrome top, synth VO closes.
    ("cta",     6.0, "resolve", "WE DON'T BACK DOWN",
     {"path": RAW_DIR / "20260425_170137.mp4", "in_t": 12.0, "out_t": 18.0,
      "audio_gain": 0.55,
      "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H}),
]
# Sanity: 17+7+6 = 30 ✓

# Build SCENES from BEATS (start, end, slug).
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

# Chord families used across BEATS — tied to emotional arc.
SCENE_CHORDS = {
    "minor":   [110.00, 164.81, 220.00],            # A minor — urgent
    "grief":   [73.42,  110.00, 146.83, 174.61],    # D minor — testimony
    "build":   [130.81, 196.00, 261.63],            # C major — institution
    "resolve": [110.00, 164.81, 220.00, 277.18],    # A major — triumph
}

# Synth VO used only on the CTA beat. Native sync sound carries every
# preceding beat; the synth voice is reserved for the final brand line so
# the closing tagline reads as MPC speaking, not the rally speaking.
NARRATION_LINES = [
    {"slug": "cta", "start_in_beat": 0.6,
     "text": "We don't back down. Chip in. Link in bio."},
]

CTA_URL = "secure.actblue.com/donate/michigan-progressive-caucus-1"

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
    """Pill-shaped proof tag below the banner naming the kind of evidence
    this beat contributes. Chip pulses subtly with the beat by varying
    chip_color across beats."""
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


# Per-beat chip color. Both survivor beats stay in the same warm magenta
# so the visual register reads "same KIND of evidence" — no chip-color cut
# distracts from the testimony.
CHIP_COLORS = {
    "juan":      C["deep_magenta"],
    "neighbors": C["deep_magenta"],
    "cta":       C["deep_magenta"],
}


def render_beat_chrome(slug, chip_label, well_transparent=True):
    """Generic chrome for the 6 proof beats: banner + proof chip on top of
    a transparent well that the footage layer composites under."""
    img = Image.new("RGBA", (W, H), (*C["near_black"], 255))
    draw_well(img, transparent=well_transparent)
    draw_top_banner(img)
    draw_proof_chip(img, chip_label, chip_color=CHIP_COLORS.get(slug))
    return np.array(img)


def render_cta_chrome(well_transparent=True):
    """CTA: split layout — gradient chrome top half, footage bottom half.
    Tagline + ActBlue plate + handle.
    """
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
        draw, "WE DON'T BACK DOWN", font(72, bold=True), W // 2, tag_top,
        fill=(*C["white"], 255),
        shadow_offset=(4, 4),
        shadow_color=(*C["deep_magenta"], 240))

    # Sub-tagline immediately under the headline so the chrome reads as
    # one block — the proof stack already sold the line; this just labels
    # the destination.
    sub_top = tag_bbox[3] + 16
    sub_bbox = draw_centered_text(
        draw, "CHIP IN", font(48, bold=True), W // 2, sub_top,
        fill=(*C["white"], 255))

    # ActBlue URL plate
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

    # Handle line
    handle_top = plate_y + plate_h + 18
    draw_centered_text(
        draw, "Link in bio  •  @michiganprogressive",
        font(32, bold=False), W // 2, handle_top,
        fill=(*C["white"], 255))

    return np.array(img)


# --------------------------------------------------------------------------- #
# Audio synthesis (chord per beat) + synth VO + native sync sound mix
# --------------------------------------------------------------------------- #

def render_chord_window(notes_hz, t_start, t_end, fade_in=0.4, fade_out=0.4):
    out = np.zeros(N, dtype=np.float32)
    i0 = int(t_start * SR)
    i1 = min(N, int(t_end * SR))
    if i0 >= N or i1 <= i0:
        return out
    n = i1 - i0
    t_local = np.linspace(0, n / SR, n, endpoint=False)
    chord = np.zeros(n, dtype=np.float32)
    vib = 0.004 * np.sin(2 * np.pi * 5.5 * t_local)
    breath = 1.0 - 0.18 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.3 * t_local))
    for k, f in enumerate(notes_hz):
        amp = max(0.04, 0.13 - 0.025 * k)
        ph1 = 2 * np.pi * np.cumsum(f * (1 + vib)) / SR
        chord += amp * np.sin(ph1)
        ph2 = 2 * np.pi * np.cumsum(2 * f * (1 + vib * 0.6)) / SR
        chord += amp * 0.30 * np.sin(ph2)
        ph3 = 2 * np.pi * np.cumsum(3 * f * (1 + vib * 0.3)) / SR
        chord += amp * 0.12 * np.sin(ph3)
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
    """Bed: render the chord assigned to each beat, with crossfade overlap
    between adjacent same-chord beats and a clean change between different
    chords."""
    bed = np.zeros(N, dtype=np.float32)
    overlap = 0.35
    for idx, (t0, t1, slug) in enumerate(SCENES):
        chord_key = next(b[2] for b in BEATS if b[0] == slug)
        notes = SCENE_CHORDS[chord_key]
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


def _scene_start(slug):
    return next(s[0] for s in SCENES if s[2] == slug)


def synthesize_narration(env):
    """One synth line for the CTA. Cache key = `wdbd_<slug>.mp3` so we don't
    collide with the romulus pipeline cache."""
    api_key = env.get("ELEVENLABS_API_KEY")
    voice = env.get("ELEVENLABS_VOICE")
    model = env.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
        print("[narration] no API key — skipping")
        return None
    try:
        import requests
        from pydub import AudioSegment
    except ImportError as e:
        print(f"[narration] missing dep: {e}")
        return None

    track = np.zeros(N, dtype=np.float32)
    for line in NARRATION_LINES:
        cache = TTS_CACHE / f"wdbd_{line['slug']}.mp3"
        if not cache.exists():
            print(f"[narration] generating {line['slug']}: {line['text']!r}")
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
            cache.write_bytes(r.content)
        else:
            print(f"[narration] cached {line['slug']}")
        seg = AudioSegment.from_mp3(cache).set_frame_rate(SR).set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples = samples / float(1 << (8 * seg.sample_width - 1))
        scene_t = _scene_start(line["slug"]) + line["start_in_beat"]
        i0 = int(scene_t * SR)
        i1 = min(N, i0 + len(samples))
        track[i0:i1] += samples[: i1 - i0] * 0.95
    return track


def measure_tts_duration(slug):
    try:
        from pydub import AudioSegment
    except ImportError:
        return 0.0
    p = TTS_CACHE / f"wdbd_{slug}.mp3"
    if not p.exists():
        return 0.0
    try:
        return AudioSegment.from_mp3(str(p)).duration_seconds
    except Exception:
        return 0.0


def sidechain_duck(bed, voice, threshold=0.025, ratio=0.30,
                   attack_ms=20.0, release_ms=180.0):
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


def vo_duck_envelope(voice, threshold=0.02, low_gain=0.5,
                     attack_ms=10.0, release_ms=200.0):
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


def to_int16_stereo(mono):
    mono = np.clip(mono, -1.0, 1.0)
    L = (mono * 32767).astype(np.int16)
    return np.column_stack([L, L.copy()]).flatten()


# --------------------------------------------------------------------------- #
# Footage compositor — rotation-safe loader + scene composer
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
    """MoviePy 1.0.3 silently ignores rotation metadata and ships aspect-
    distorted frames. Bake the rotation into pixels with ffmpeg autorotate
    so subjects appear at correct portrait aspect.

    See E:/AI/CVS/mpc/brand/BRAND_KIT.md → Production Notes for the why.
    Cache lives under OUTPUT_DIR/_rot_cache/.
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
# Audio mix (native source per beat + synth CTA VO)
# --------------------------------------------------------------------------- #

def _shot_audio_range(shot):
    return float(shot.get("audio_in", shot["in_t"])), \
           float(shot.get("audio_out", shot["out_t"]))


def extract_audio_segment(path, t0, t1):
    """ffmpeg subprocess audio extractor (mono, SR). MoviePy 1.0.3's
    to_soundarray() breaks against modern numpy."""
    import subprocess
    import tempfile
    dur = float(t1 - t0)
    if dur <= 0:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    try:
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-ss", f"{float(t0):.3f}", "-t", f"{dur:.3f}",
               "-i", str(path),
               "-vn", "-ac", "1", "-ar", str(SR),
               "-acodec", "pcm_s16le", tmp]
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

    # Duck native source under synth VO (only matters in CTA window)
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
    stereo = to_int16_stereo(mono)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"[audio] wrote {path}")


# --------------------------------------------------------------------------- #
# Captions — Whisper segments per beat + synth VO timing for CTA
# --------------------------------------------------------------------------- #

def _load_whisper_segments(path):
    """Load segments from `mpc/index/clips/<stem>.json` produced by the
    asset scan. Returns list of (start, end, text) in CLIP-LOCAL time."""
    stem = Path(path).stem
    p = ROOT / "index" / "clips" / f"{stem}.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return [(s["start"], s["end"], s["text"]) for s in
                d.get("transcript", {}).get("segments", [])]
    except Exception:
        return []


def build_caption_events():
    """For each non-CTA beat, take its source clip's Whisper segments, clip
    them to in_t..out_t, offset to scene-timeline. CTA caption uses the
    synth-VO line at its measured TTS duration."""
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
        in_t = float(spec["in_t"])
        out_t = float(spec["out_t"])
        for s_start, s_end, text in _load_whisper_segments(spec["path"]):
            # Intersect segment with the clip's in_t..out_t window
            seg_start = max(s_start, in_t)
            seg_end = min(s_end, out_t)
            if seg_end - seg_start < 0.25:
                continue
            events.append({"start": scene_t0 + (seg_start - in_t),
                           "end":   scene_t0 + (seg_end - in_t),
                           "text":  text.strip()})
    events.sort(key=lambda e: e["start"])
    return events


def render_caption_strip(text, size=64, max_w=1000,
                         fill=(255, 255, 255, 255),
                         stroke_fill=(0, 0, 0, 255), stroke_w=5,
                         pad_y=16):
    """Dynamic-height stroked caption strip (see feedback_caption_strip_sizing)."""
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
    print("Building MPC We Don't Back Down (45s reel)...")

    # Pre-warm TTS so caption sizing reads its real duration.
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
