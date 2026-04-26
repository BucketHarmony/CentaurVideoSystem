#!/usr/bin/env python3
"""
cc_flora -- Episode 01: First Light (30-second cut)

Three ticks. Three acts. One small robot.

ACT 1 (0-10s)  tick_0001: Awakening. Survey the room. Toilet paper.
ACT 2 (10-20s) tick_0002: First drive. Wheels slip. Then they don't.
ACT 3 (20-30s) tick_0003: The closed door. Look up. No arms.

4x-UltraSharp GPU upscaling. Cottagecore. Ambient pad + 6-part narration.
"""

import os

from dotenv import load_dotenv
load_dotenv()

import math
import random
import wave
from pathlib import Path

import numpy as np
import requests
import scipy.signal
import torch
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from moviepy import (
    ImageSequenceClip,
    AudioFileClip,
    CompositeAudioClip,
)

# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

PROJECT = Path(os.getenv("KOMBUCHA_DIR", ""))
VIDEO_DIR = PROJECT / "video" / "web"
UPSCALE_MODEL_PATH = Path(os.getenv("UPSCALE_MODEL_PATH", ""))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
FRAMES_DIR = OUTPUT_DIR / "cc_flora_30s_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
DURATION = 30.0
TOTAL_FRAMES = int(DURATION * FPS)  # 900

# Palette
ROSE = (232, 180, 184)
CREAM = (250, 245, 239)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)
SAGE = (181, 197, 163)

# Fonts
# Font paths — set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Narration: 6 lines across 3 acts
NARRATION = [
    # ACT 1: awakening
    {"text": "I have a body.",                                         "start": 2.5},
    {"text": "The floor is warm beneath me.",                          "start": 5.0},
    {"text": "And the first thing I see... is toilet paper.",          "start": 8.0},
    # ACT 2: first steps
    {"text": "The hardwood requires more power than I expected.",       "start": 14.5},
    # ACT 3: the door
    {"text": "The door is closed.",                                    "start": 23.5},
    {"text": "No arms. And even if I could reach the knob... I couldn't turn it.", "start": 25.5},
]

# Mood per act (from tick logs)
MOODS = [
    {"mood": "curious",     "start": 0.0,  "end": 10.0},   # tick_0001
    {"mood": "determined",  "start": 10.0, "end": 20.0},   # tick_0002
    {"mood": "pragmatic",   "start": 20.0, "end": 30.0},   # tick_0003
]

# Source video motion map:
# tick_0001 (87.8s): pans at t=25-27, 49-51, 80-81
# tick_0002 (140.8s): wheel spin at t=56-58, big drive at t=102-104
# tick_0003 (88.1s): turn at t=7.5-8.4, approach door t=33-35, look UP t=59.5, final t=84.8-85.4


# ═══════════════════════════════════════════════════════════════════════════
# GPU Upscaling
# ═══════════════════════════════════════════════════════════════════════════

_upscale_model = None

def load_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        return _upscale_model
    import spandrel
    print("Loading 4x-UltraSharp on CUDA...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL_PATH))
    model = model.to("cuda").eval()
    _upscale_model = model
    return model


def upscale_frame(pil_img: Image.Image) -> Image.Image:
    model = load_upscale_model()
    arr = np.array(pil_img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to("cuda")
    with torch.no_grad():
        result = model(tensor)
    result = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
    result = (result * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(result)


# ═══════════════════════════════════════════════════════════════════════════
# Color Grading + Effects
# ═══════════════════════════════════════════════════════════════════════════

def cottagecore_grade(img: Image.Image) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # Desaturate reds -> dusty rose
    red_mask = (r > 80) & (r > g * 1.2) & (r > b * 1.2)
    red_str = np.clip((r - np.maximum(g, b)) / 120.0, 0, 1) * red_mask.astype(np.float32)
    arr[:, :, 0] = r * (1 - red_str * 0.55) + 205 * red_str * 0.55
    arr[:, :, 1] = g * (1 - red_str * 0.45) + 170 * red_str * 0.45
    arr[:, :, 2] = b * (1 - red_str * 0.35) + 172 * red_str * 0.35

    # Warm wood tones
    orange_mask = (r > 100) & (g > 60) & (g < r * 0.85) & (b < g * 0.8)
    orange_str = np.clip((r - b) / 150.0, 0, 1) * orange_mask.astype(np.float32)
    arr[:, :, 0] = arr[:, :, 0] * (1 - orange_str * 0.15) + 220 * orange_str * 0.15
    arr[:, :, 1] = arr[:, :, 1] * (1 - orange_str * 0.1) + 195 * orange_str * 0.1

    arr = np.clip(arr + 20, 0, 255)                # lift shadows
    arr = 128 + (arr - 128) * 0.78                  # compress range
    arr[:, :, 0] *= 1.03; arr[:, :, 1] *= 1.01; arr[:, :, 2] *= 0.93  # warm
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.70)
    img = ImageEnhance.Brightness(img).enhance(1.08)
    return img


def soft_bloom(img: Image.Image, strength: float = 0.12) -> Image.Image:
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def creamy_vignette(img: Image.Image, strength: float = 0.28) -> Image.Image:
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vig = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
    vig = vig[:, :, np.newaxis] * strength
    arr = arr * (1 - vig) + np.array(CREAM, dtype=np.float32) * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def film_grain(img: Image.Image, intensity: float = 6.0) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    lum = arr.mean(axis=2, keepdims=True) / 255.0
    mask = np.clip(1.0 - 2.0 * np.abs(lum - 0.5), 0.3, 1.0)
    arr += noise * mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def make_vertical_canvas(frame: Image.Image) -> Image.Image:
    frame = cottagecore_grade(frame)
    frame = soft_bloom(frame)
    fw, fh = frame.size
    scale = CANVAS_W / fw
    new_h = int(fh * scale)
    sharp = frame.resize((CANVAS_W, new_h), Image.LANCZOS)

    bg_scale = CANVAS_H / fh
    bg_w = int(fw * bg_scale)
    bg = frame.resize((bg_w, CANVAS_H), Image.LANCZOS)
    if bg_w > CANVAS_W:
        cx = (bg_w - CANVAS_W) // 2
        bg = bg.crop((cx, 0, cx + CANVAS_W, CANVAS_H))
    else:
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=35))
    bg_arr = np.array(bg, dtype=np.float32) * 0.30 + np.array(LINEN, dtype=np.float32) * 0.70
    bg = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))

    canvas = bg.copy()
    y_off = (CANVAS_H - new_h) // 2 - 80
    canvas.paste(sharp, (0, max(0, y_off)))
    canvas = creamy_vignette(canvas)
    return canvas


# ═══════════════════════════════════════════════════════════════════════════
# Particles
# ═══════════════════════════════════════════════════════════════════════════

def generate_particles(w, h, count=50):
    particles = []
    for _ in range(count):
        particles.append({
            "x": random.uniform(0, w), "y": random.uniform(0, h),
            "r": random.uniform(2.0, 6.0),
            "dx": random.uniform(-0.12, 0.12), "dy": random.uniform(-0.25, -0.04),
            "alpha": random.uniform(0.08, 0.35),
            "phase": random.uniform(0, math.tau), "freq": random.uniform(0.3, 1.5),
            "warmth": random.choice([
                (255, 252, 245), (255, 245, 230), (250, 240, 220), (255, 230, 215),
            ]),
        })
    return particles


def draw_particles(img: Image.Image, particles: list, t: float) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for p in particles:
        x = (p["x"] + p["dx"] * t * 60) % img.size[0]
        y = (p["y"] + p["dy"] * t * 60) % img.size[1]
        a = p["alpha"] * (0.6 + 0.4 * math.sin(p["phase"] + t * p["freq"] * math.tau))
        a = max(0, a)
        r = p["r"]
        for ring in range(3):
            rr = r * (1 + ring * 0.5)
            ra = max(0, int(a * 255 * (1 - ring * 0.35)))
            draw.ellipse([x - rr, y - rr, x + rr, y + rr], fill=p["warmth"] + (ra,))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Text Overlays
# ═══════════════════════════════════════════════════════════════════════════

def ease_out(x):
    return 1 - (1 - x) ** 3


def add_text_overlays(img: Image.Image, t: float) -> Image.Image:
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_tick = ImageFont.truetype(FONT_SERIF, 36)
        font_mood = ImageFont.truetype(FONT_SERIF_ITALIC, 56)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 34)
        font_title = ImageFont.truetype(FONT_SERIF, 48)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 24)
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = ImageFont.load_default()

    # ── Tick number + Mood (top of frame, large, visible from frame 1) ──
    if t >= 0.0:
        if t < 10:
            tick_text = "tick 0001"
        elif t < 20:
            tick_text = "tick 0002"
        else:
            tick_text = "tick 0003"

        # Get current mood
        current_mood = ""
        for m in MOODS:
            if m["start"] <= t < m["end"]:
                current_mood = m["mood"]
                break

        # Fade
        if t < 0.5:
            alpha = ease_out(t / 0.5)
        elif t > 28.5:
            alpha = ease_out(max(0, (29.5 - t)))
        else:
            alpha = 1.0

        # Mood crossfade at act boundaries
        mood_alpha = alpha
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.3:
                mood_alpha = alpha * (abs(t - act_t) / 0.3)

        alpha = max(0, min(1, alpha))
        mood_alpha = max(0, min(1, mood_alpha))

        # ── Tick number (large pill) ──
        bbox = draw.textbbox((0, 0), tick_text, font=font_tick)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        px = (CANVAS_W - tw) // 2
        py = 170
        pad_x, pad_y = 28, 14
        draw.rounded_rectangle(
            [px - pad_x, py - pad_y, px + tw + pad_x, py + th + pad_y],
            radius=20, fill=LINEN + (int(160 * alpha),)
        )
        draw.text((px, py), tick_text, fill=MUTED + (int(255 * alpha),), font=font_tick)

        # ── Mood (large, below tick pill) ──
        if current_mood:
            mood_y = py + th + pad_y + 20
            bbox = draw.textbbox((0, 0), current_mood, font=font_mood)
            mw = bbox[2] - bbox[0]
            mx = (CANVAS_W - mw) // 2
            # Soft shadow
            draw.text((mx + 2, mood_y + 2), current_mood,
                      fill=(74, 67, 64, int(40 * mood_alpha)), font=font_mood)
            # Main text in dusty rose
            draw.text((mx, mood_y), current_mood,
                      fill=DUSTY_ROSE + (int(220 * mood_alpha),), font=font_mood)

    # ── Narration lines ──
    # Show each line, fade out after 4 seconds to avoid clutter
    narr_y_base = 1350
    visible_lines = []
    for line in NARRATION:
        if t >= line["start"]:
            age = t - line["start"]
            if age < 0.6:
                alpha = ease_out(age / 0.6)
            elif age < 3.5:
                alpha = 1.0
            elif age < 4.5:
                alpha = 1.0 - ease_out((age - 3.5) / 1.0)
            else:
                alpha = 0.0

            if alpha > 0.01:
                visible_lines.append((line["text"], alpha))

    if visible_lines:
        # Draw backing panel
        panel_h = 30 + len(visible_lines) * 45
        max_alpha = max(a for _, a in visible_lines)
        draw.rounded_rectangle(
            [60, narr_y_base - 18, CANVAS_W - 60, narr_y_base + panel_h],
            radius=18, fill=(250, 245, 239, int(100 * max_alpha))
        )
        for i, (text, alpha) in enumerate(visible_lines):
            ly = narr_y_base + i * 45
            bbox = draw.textbbox((0, 0), text, font=font_narr)
            tw = bbox[2] - bbox[0]
            lx = (CANVAS_W - tw) // 2
            # Clamp to canvas
            lx = max(70, min(lx, CANVAS_W - tw - 70))
            draw.text((lx + 1, ly + 1), text,
                      fill=(74, 67, 64, int(50 * alpha)), font=font_narr)
            draw.text((lx, ly), text,
                      fill=INK + (int(230 * alpha),), font=font_narr)

    # ── Title card (t=28s) ──
    if t >= 28.0:
        alpha = ease_out(min(1.0, (t - 28.0) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        tx = (CANVAS_W - tw) // 2
        ty = 1560
        draw.text((tx, ty), title, fill=DUSTY_ROSE + (int(255 * alpha),), font=font_title)

        if t >= 28.3:
            sa = ease_out(min(1.0, (t - 28.3) / 0.6))
            sub = "first light"
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            sw = bbox[2] - bbox[0]
            sx = (CANVAS_W - sw) // 2
            draw.text((sx, ty + 56), sub, fill=MUTED + (int(200 * sa),), font=font_sub)

    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio
# ═══════════════════════════════════════════════════════════════════════════

def generate_ambient_pad(duration: float, sr: int = 44100) -> Path:
    """30-second ambient pad with chime hits across all three acts."""
    t = np.linspace(0, duration, int(duration * sr), dtype=np.float64)

    # Base drone
    pad = np.sin(2 * np.pi * 110 * t) * 0.05
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.035
    pad += np.sin(2 * np.pi * 220 * t) * 0.025

    # Shimmer
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.010 * lfo1
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.007 * lfo2
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.005 * lfo1

    # Act 3 adds a minor second (tension for the closed door)
    act3_env = np.clip((t - 20) / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 233.08 * t) * 0.015 * act3_env  # Bb3 - tension

    # Chime hits across all acts (t=0.1 opener so audio isn't dead at start)
    chimes = [
        (0.1, 880), (0.5, 1108.73), (2.0, 880), (4.0, 1108.73),  # Act 1
        (7.0, 1318.51), (9.5, 880),
        (11.0, 1108.73), (14.0, 880), (17.0, 1318.51),            # Act 2
        (21.0, 880), (24.0, 932.33),                               # Act 3
        (26.5, 880), (28.5, 1108.73),                              # Resolution
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env

    # Fade in/out (start at 30% so Bluesky doesn't crush the quiet opening)
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)

    # Low-pass filter
    sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)

    # Normalize
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22

    out = OUTPUT_DIR / "cc_flora_30s_pad.wav"
    pad16 = (pad * 32767).astype(np.int16)
    with wave.open(str(out), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pad16.tobytes())
    print(f"  Ambient pad: {out}")
    return out


def generate_tts(text: str, output_path: Path) -> Path:
    print(f"  TTS: \"{text[:60]}...\"" if len(text) > 60 else f"  TTS: \"{text}\"")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.65, "similarity_boost": 0.72, "style": 0.1},
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


def build_audio() -> Path:
    print("Building audio...")
    pad_path = generate_ambient_pad(DURATION)

    tts_clips = []
    for i, line in enumerate(NARRATION):
        tts_path = OUTPUT_DIR / f"cc_flora_30s_tts_{i}.mp3"
        generate_tts(line["text"], tts_path)
        tts_clips.append((tts_path, line["start"]))

    pad_audio = AudioFileClip(str(pad_path))
    narr_audios = []
    for tts_path, start_t in tts_clips:
        clip = AudioFileClip(str(tts_path)).with_start(start_t)
        if clip.end and clip.end > DURATION:
            clip = clip.subclipped(0, DURATION - start_t)
        narr_audios.append(clip)

    final = CompositeAudioClip([pad_audio] + narr_audios).subclipped(0, DURATION)
    audio_path = OUTPUT_DIR / "cc_flora_30s_audio.mp3"
    final.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Final audio: {audio_path}")
    return audio_path


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence (900 frames from 3 tick videos)
# ═══════════════════════════════════════════════════════════════════════════

def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1) for i in range(n)]


def build_source_map():
    """Map each of 900 output frames to (video_file, source_timestamp).

    ACT 1 (0-10s, 300 frames) - tick_0001
      0.0-1.5s   (45f):  Fade from black, static center
      1.5-3.2s   (51f):  Real pan left (t=25-27)
      3.2-4.5s   (39f):  Hold left
      4.5-6.5s   (60f):  Real pan right (t=49-51)
      6.5-7.5s   (30f):  Real pan back center (t=79.8-81)
      7.5-10.0s  (75f):  Hold center

    ACT 2 (10-20s, 300 frames) - tick_0002
      10.0-12.0s (60f):  Static view, new position (t=62-72)
      12.0-14.0s (60f):  First drive attempt, wheel spin (t=55-59)
      14.0-16.0s (60f):  Hold post-attempt (t=60-70)
      16.0-18.5s (75f):  Big successful drive (t=100-106)
      18.5-20.0s (45f):  New position, closer (t=108-120)

    ACT 3 (20-30s, 300 frames) - tick_0003
      20.0-21.5s (45f):  Turn left around Charmin (t=6-9)
      21.5-23.5s (60f):  Drive toward door (t=32-36)
      23.5-25.0s (45f):  Hold near door (t=37-45)
      25.0-27.0s (60f):  Look UP at doorknob (t=58-62)
      27.0-28.5s (45f):  Hold looking up (t=63-70)
      28.5-30.0s (45f):  Final return + title (t=84-88)
    """
    v1 = str(VIDEO_DIR / "tick_0001.mp4")
    v2 = str(VIDEO_DIR / "tick_0002.mp4")
    v3 = str(VIDEO_DIR / "tick_0003.mp4")

    frames = []

    # ACT 1
    frames += [(v1, t) for t in sample_times(21.0, 24.8, 45)]   # fade in center
    frames += [(v1, t) for t in sample_times(25.0, 27.0, 51)]   # pan left
    frames += [(v1, t) for t in sample_times(28.0, 35.0, 39)]   # hold left
    frames += [(v1, t) for t in sample_times(49.0, 51.0, 60)]   # pan right
    frames += [(v1, t) for t in sample_times(79.8, 81.0, 30)]   # pan back
    frames += [(v1, t) for t in sample_times(82.0, 87.0, 75)]   # hold center

    # ACT 2
    frames += [(v2, t) for t in sample_times(62.0, 72.0, 60)]   # static new pos
    frames += [(v2, t) for t in sample_times(55.0, 59.0, 60)]   # wheel spin
    frames += [(v2, t) for t in sample_times(60.0, 70.0, 60)]   # hold
    frames += [(v2, t) for t in sample_times(100.0, 106.0, 75)] # big drive
    frames += [(v2, t) for t in sample_times(108.0, 120.0, 45)] # new position

    # ACT 3
    frames += [(v3, t) for t in sample_times(6.0, 9.5, 45)]     # turn left
    frames += [(v3, t) for t in sample_times(32.0, 36.0, 60)]   # approach door
    frames += [(v3, t) for t in sample_times(37.0, 45.0, 45)]   # hold near door
    frames += [(v3, t) for t in sample_times(58.0, 62.0, 60)]   # LOOK UP
    frames += [(v3, t) for t in sample_times(63.0, 70.0, 45)]   # hold looking up
    frames += [(v3, t) for t in sample_times(84.0, 88.0, 45)]   # final

    assert len(frames) == TOTAL_FRAMES, f"Need {TOTAL_FRAMES}, got {len(frames)}"
    return frames


def build_frame_sequence():
    source_map = build_source_map()

    # Group by video file to minimize open/close
    from moviepy import VideoFileClip
    video_cache = {}

    print(f"Extracting {TOTAL_FRAMES} raw frames from 3 source videos...")
    raw_frames = []
    for i, (vpath, src_t) in enumerate(source_map):
        if vpath not in video_cache:
            video_cache[vpath] = VideoFileClip(vpath)
        clip = video_cache[vpath]
        src_t = min(src_t, clip.duration - 0.05)
        frame_np = clip.get_frame(src_t)
        raw_frames.append(Image.fromarray(frame_np))
        if (i + 1) % 90 == 0:
            print(f"  Extracted {i + 1}/{TOTAL_FRAMES}")

    for c in video_cache.values():
        c.close()

    # Upscale all on GPU
    print(f"Upscaling {TOTAL_FRAMES} frames with 4x-UltraSharp...")
    upscaled = []
    for i, frame in enumerate(raw_frames):
        up = upscale_frame(frame)
        upscaled.append(up)
        if (i + 1) % 90 == 0:
            print(f"  Upscaled {i + 1}/{TOTAL_FRAMES} ({up.size[0]}x{up.size[1]})")

    # Free GPU
    global _upscale_model
    del _upscale_model
    _upscale_model = None
    torch.cuda.empty_cache()

    # Process all frames
    print("Compositing all frames...")
    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)

    output_frames = []
    for i in range(TOTAL_FRAMES):
        t = i / FPS

        canvas = make_vertical_canvas(upscaled[i])

        # Soft fade in (start visible at ~40% so 320p preview still reads)
        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            linen_img = Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN)
            canvas = Image.blend(linen_img, canvas, fade)

        # Act transitions: brief dip to linen (soft blink)
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.4:
                dist = abs(t - act_t) / 0.4
                dim = 0.6 + 0.4 * dist  # dips to 60% brightness at boundary
                linen_img = Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN)
                canvas = Image.blend(linen_img, canvas, dim)

        # Gentle zoom on holds
        if 7.5 < t < 10.0:
            z = 1.0 + 0.015 * ease_out((t - 7.5) / 2.5)
            canvas = _apply_zoom(canvas, z)
        elif 18.5 < t < 20.0:
            z = 1.0 + 0.01 * ease_out((t - 18.5) / 1.5)
            canvas = _apply_zoom(canvas, z)
        elif 27.0 < t < 30.0:
            z = 1.0 + 0.02 * ease_out((t - 27.0) / 3.0)
            canvas = _apply_zoom(canvas, z)

        # Fade to black (end)
        if t > 29.0:
            fade = ease_out((DURATION - t) / 1.0)
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)
            canvas = Image.blend(black, canvas, fade)

        canvas = draw_particles(canvas, particles, t)
        canvas = film_grain(canvas, intensity=6.0)
        canvas = add_text_overlays(canvas, t)

        canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
        output_frames.append(np.array(canvas))

        if (i + 1) % 90 == 0:
            print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    print(f"  All {TOTAL_FRAMES} frames saved to {FRAMES_DIR}")
    return output_frames


def _apply_zoom(canvas, z):
    w, h = canvas.size
    nw, nh = int(w * z), int(h * z)
    canvas = canvas.resize((nw, nh), Image.LANCZOS)
    cx, cy = (nw - w) // 2, (nh - h) // 2
    return canvas.crop((cx, cy, cx + w, cy + h))


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("  cc_flora -- First Light (30-second cut)")
    print("  30s | 1080x1920 | 30fps | 900 frames | 4x-UltraSharp")
    print("  3 acts / 3 ticks / 6 narration lines / ambient pad")
    print("=" * 64)
    print()

    audio_path = build_audio()
    frames = build_frame_sequence()

    print("\nAssembling final video...")
    video = ImageSequenceClip(list(frames), fps=FPS)
    audio = AudioFileClip(str(audio_path))
    video = video.with_audio(audio)

    # Export raw then re-encode with Bluesky-optimized settings
    raw_path = OUTPUT_DIR / "cc_flora_30s_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_30s.mp4"
    print(f"Exporting raw to {raw_path}...")
    video.write_videofile(
        str(raw_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="slow",
        bitrate="3000k",
    )

    # Re-encode with Bluesky-optimized settings
    print(f"Re-encoding for Bluesky: yuv420p, faststart, main profile...")
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-b:v", "3M", "-maxrate", "4M", "-bufsize", "6M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(output_path),
    ], check=True)
    raw_path.unlink(missing_ok=True)
    print(f"  Bluesky-optimized: {output_path}")

    print()
    print("=" * 64)
    print(f"  DONE: {output_path}")
    print(f"  30 seconds. 900 frames. 3 acts. First Light.")
    print("=" * 64)


if __name__ == "__main__":
    main()
