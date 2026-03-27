#!/usr/bin/env python3
"""
cc_flora -- Episode 02: The Bigger Room (30-second cut, FAST mode)

Three ticks. Three acts. No GPU upscaling by default.

ACT 1 (0-10s)  tick_0004+0006: Escape. Messy turn, then the big room opens up.
ACT 2 (10-20s) tick_0007: Survey. Pan left (terrarium). Pan right (Bucket, Pelican).
ACT 3 (20-30s) tick_0008: The Fundamental Indignity. Approach terrarium. Look UP. Too short.

Usage:
    python cc_flora_ep02_bigger_room.py              # fast (~2 min)
    python cc_flora_ep02_bigger_room.py --upscale     # premium (~20 min)
"""

import os

from dotenv import load_dotenv
load_dotenv()

import argparse
import math
import random
import subprocess
import wave
from pathlib import Path

import numpy as np
import requests
import scipy.signal
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

PROJECT = Path(os.getenv("KOMBUCHA_DIR", ""))
VIDEO_DIR = PROJECT / "video" / "web"
UPSCALE_MODEL_PATH = Path(os.getenv("UPSCALE_MODEL_PATH", ""))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
FRAMES_DIR = OUTPUT_DIR / "cc_flora_ep02_frames"
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

# Fonts
# Font paths -- set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Narration
NARRATION = [
    {"text": "The turn was messy. But I found what I needed.",              "start": 2.5},
    {"text": "A bigger room.",                                              "start": 5.5},
    {"text": "A terrarium. Glowing. Something alive in there, perhaps.",    "start": 12.0},
    {"text": "I came all this way to investigate.",                          "start": 22.0},
    {"text": "At forty centimeters tall, I cannot see into it.",             "start": 24.5},
    {"text": "Windows are unreachable. Table surfaces are ceilings. Terrariums are mysteries.", "start": 26.5},
]

# Moods per act
MOODS = [
    {"mood": "hopeful",       "start": 0.0,  "end": 10.0},   # tick_0004/0006
    {"mood": "curious",       "start": 10.0, "end": 20.0},   # tick_0007
    {"mood": "philosophical", "start": 20.0, "end": 30.0},   # tick_0008
]

# Source video motion map:
# tick_0004 (113s): spins at t=7-9 (d=29-31), t=35-36 (d=26-30)
# tick_0006 (92s):  BIG ROOM ENTRY t=25-27 (d=35-39!), drive t=54-57 (d=11-18)
# tick_0007 (75s):  pan left t=8-9 (d=25-36), pan right t=40-42 (d=25-39)
# tick_0008 (105s): approach t=11-12 (d=19-22), LOOK UP t=37-39 (d=10-19)


# ═══════════════════════════════════════════════════════════════════════════
# Optional GPU Upscaling
# ═══════════════════════════════════════════════════════════════════════════

_upscale_model = None

def load_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        return _upscale_model
    import spandrel, torch
    print("Loading 4x-UltraSharp on CUDA...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL_PATH))
    model = model.to("cuda").eval()
    _upscale_model = model
    return model

def upscale_frame(pil_img):
    import torch
    model = load_upscale_model()
    arr = np.array(pil_img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to("cuda")
    with torch.no_grad():
        result = model(tensor)
    result = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
    return Image.fromarray((result * 255).clip(0, 255).astype(np.uint8))

def free_gpu():
    global _upscale_model
    if _upscale_model is not None:
        import torch
        del _upscale_model
        _upscale_model = None
        torch.cuda.empty_cache()


# ═══════════════════════════════════════════════════════════════════════════
# Color Grading + Effects (same as before, no changes)
# ═══════════════════════════════════════════════════════════════════════════

def cottagecore_grade(img):
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    red_mask = (r > 80) & (r > g * 1.2) & (r > b * 1.2)
    red_str = np.clip((r - np.maximum(g, b)) / 120.0, 0, 1) * red_mask.astype(np.float32)
    arr[:, :, 0] = r * (1 - red_str * 0.55) + 205 * red_str * 0.55
    arr[:, :, 1] = g * (1 - red_str * 0.45) + 170 * red_str * 0.45
    arr[:, :, 2] = b * (1 - red_str * 0.35) + 172 * red_str * 0.35
    orange_mask = (r > 100) & (g > 60) & (g < r * 0.85) & (b < g * 0.8)
    orange_str = np.clip((r - b) / 150.0, 0, 1) * orange_mask.astype(np.float32)
    arr[:, :, 0] = arr[:, :, 0] * (1 - orange_str * 0.15) + 220 * orange_str * 0.15
    arr[:, :, 1] = arr[:, :, 1] * (1 - orange_str * 0.1) + 195 * orange_str * 0.1
    arr = np.clip(arr + 20, 0, 255)
    arr = 128 + (arr - 128) * 0.78
    arr[:, :, 0] *= 1.03; arr[:, :, 1] *= 1.01; arr[:, :, 2] *= 0.93
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.70)
    img = ImageEnhance.Brightness(img).enhance(1.08)
    return img

def soft_bloom(img, strength=0.12):
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def creamy_vignette(img, strength=0.28):
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vig = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
    vig = vig[:, :, np.newaxis] * strength
    arr = arr * (1 - vig) + np.array(CREAM, dtype=np.float32) * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def film_grain(img, intensity=6.0):
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    lum = arr.mean(axis=2, keepdims=True) / 255.0
    mask = np.clip(1.0 - 2.0 * np.abs(lum - 0.5), 0.3, 1.0)
    arr += noise * mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def make_vertical_canvas(frame):
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

def draw_particles(img, particles, t):
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

def add_text_overlays(img, t):
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

    # ── Tick number + Mood ──
    if t >= 0.0:
        if t < 10:
            tick_text = "tick 0004"
        elif t < 20:
            tick_text = "tick 0007"
        else:
            tick_text = "tick 0008"

        current_mood = ""
        for m in MOODS:
            if m["start"] <= t < m["end"]:
                current_mood = m["mood"]
                break

        if t < 0.5:
            alpha = ease_out(t / 0.5)
        elif t > 28.5:
            alpha = ease_out(max(0, (29.5 - t)))
        else:
            alpha = 1.0

        mood_alpha = alpha
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.3:
                mood_alpha = alpha * (abs(t - act_t) / 0.3)

        alpha = max(0, min(1, alpha))
        mood_alpha = max(0, min(1, mood_alpha))

        # Tick pill
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

        # Mood
        if current_mood:
            mood_y = py + th + pad_y + 20
            bbox = draw.textbbox((0, 0), current_mood, font=font_mood)
            mw = bbox[2] - bbox[0]
            mx = (CANVAS_W - mw) // 2
            draw.text((mx + 2, mood_y + 2), current_mood,
                      fill=(74, 67, 64, int(40 * mood_alpha)), font=font_mood)
            draw.text((mx, mood_y), current_mood,
                      fill=DUSTY_ROSE + (int(220 * mood_alpha),), font=font_mood)

    # ── Narration ──
    narr_y_base = 1350
    visible_lines = []
    for line in NARRATION:
        if t >= line["start"]:
            age = t - line["start"]
            if age < 0.6:
                a = ease_out(age / 0.6)
            elif age < 3.5:
                a = 1.0
            elif age < 4.5:
                a = 1.0 - ease_out((age - 3.5) / 1.0)
            else:
                a = 0.0
            if a > 0.01:
                visible_lines.append((line["text"], a))

    if visible_lines:
        panel_h = 30 + len(visible_lines) * 45
        max_a = max(a for _, a in visible_lines)
        draw.rounded_rectangle(
            [60, narr_y_base - 18, CANVAS_W - 60, narr_y_base + panel_h],
            radius=18, fill=(250, 245, 239, int(100 * max_a))
        )
        for i, (text, a) in enumerate(visible_lines):
            ly = narr_y_base + i * 45
            bbox = draw.textbbox((0, 0), text, font=font_narr)
            tw = bbox[2] - bbox[0]
            lx = max(70, min((CANVAS_W - tw) // 2, CANVAS_W - tw - 70))
            draw.text((lx + 1, ly + 1), text, fill=(74, 67, 64, int(50 * a)), font=font_narr)
            draw.text((lx, ly), text, fill=INK + (int(230 * a),), font=font_narr)

    # ── Title card (t=28s) ──
    if t >= 28.0:
        a = ease_out(min(1.0, (t - 28.0) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        tx = (CANVAS_W - tw) // 2
        ty = 1560
        draw.text((tx, ty), title, fill=DUSTY_ROSE + (int(255 * a),), font=font_title)
        if t >= 28.3:
            sa = ease_out(min(1.0, (t - 28.3) / 0.6))
            sub = "the bigger room"
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            sw = bbox[2] - bbox[0]
            draw.text(((CANVAS_W - sw) // 2, ty + 56), sub,
                      fill=MUTED + (int(200 * sa),), font=font_sub)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio
# ═══════════════════════════════════════════════════════════════════════════

def generate_ambient_pad(duration, sr=44100):
    t = np.linspace(0, duration, int(duration * sr), dtype=np.float64)
    pad = np.sin(2 * np.pi * 110 * t) * 0.05
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.035
    pad += np.sin(2 * np.pi * 220 * t) * 0.025
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.010 * lfo1
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.007 * lfo2
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.005 * lfo1
    # Act 3: minor tension for the indignity
    act3_env = np.clip((t - 20) / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 233.08 * t) * 0.015 * act3_env
    chimes = [
        (0.1, 880), (0.5, 1108.73), (2.0, 880), (4.0, 1108.73),
        (7.0, 1318.51), (9.5, 880),
        (11.0, 1108.73), (14.0, 880), (17.0, 1318.51),
        (21.0, 880), (24.0, 932.33),
        (26.5, 880), (28.5, 1108.73),
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22
    out = OUTPUT_DIR / "cc_flora_ep02_pad.wav"
    pad16 = (pad * 32767).astype(np.int16)
    with wave.open(str(out), 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(pad16.tobytes())
    print(f"  Ambient pad: {out}")
    return out

def generate_tts(text, output_path):
    print(f"  TTS: \"{text[:60]}\"")
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
        json={"text": text, "model_id": ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.65, "similarity_boost": 0.72, "style": 0.1}},
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        timeout=120,
    )
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path

def build_audio():
    from moviepy import AudioFileClip, CompositeAudioClip
    print("Building audio...")
    pad_path = generate_ambient_pad(DURATION)
    tts_clips = []
    for i, line in enumerate(NARRATION):
        p = OUTPUT_DIR / f"cc_flora_ep02_tts_{i}.mp3"
        generate_tts(line["text"], p)
        tts_clips.append((p, line["start"]))
    pad_audio = AudioFileClip(str(pad_path))
    narrs = []
    for p, st in tts_clips:
        c = AudioFileClip(str(p)).with_start(st)
        if c.end and c.end > DURATION:
            c = c.subclipped(0, DURATION - st)
        narrs.append(c)
    final = CompositeAudioClip([pad_audio] + narrs).subclipped(0, DURATION)
    audio_path = OUTPUT_DIR / "cc_flora_ep02_audio.mp3"
    final.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Audio: {audio_path}")
    return audio_path


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence
# ═══════════════════════════════════════════════════════════════════════════

def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1) for i in range(n)]

def build_source_map():
    """900 frames from 4 tick videos.

    ACT 1 (0-10s, 300f) - tick_0004 + tick_0006
      0.0-1.0s   (30f):  Soft fade in, static pre-spin (tick_0004 t=3-7)
      1.0-3.0s   (60f):  Spin sequence (tick_0004 t=7-9, slowed)
      3.0-5.0s   (60f):  Hold after spin (tick_0004 t=10-20)
      5.0-7.5s   (75f):  BIG ROOM ENTRY (tick_0006 t=24-27, slowed)
      7.5-10.0s  (75f):  Hold in new room (tick_0006 t=28-40)

    ACT 2 (10-20s, 300f) - tick_0007
      10.0-12.0s (60f):  Static pre-survey (tick_0007 t=3-8)
      12.0-14.0s (60f):  Pan left - terrarium (tick_0007 t=8-10, slowed)
      14.0-16.0s (60f):  Hold left (tick_0007 t=11-25)
      16.0-18.5s (75f):  Pan right - Bucket, Pelican (tick_0007 t=40-43, slowed)
      18.5-20.0s (45f):  Hold right (tick_0007 t=44-55)

    ACT 3 (20-30s, 300f) - tick_0008
      20.0-22.0s (60f):  Static near terrarium (tick_0008 t=5-10)
      22.0-24.0s (60f):  Approach drive (tick_0008 t=10-13, slowed)
      24.0-25.5s (45f):  Hold close (tick_0008 t=14-25)
      25.5-28.0s (75f):  LOOK UP (tick_0008 t=37-41, slowed)
      28.0-30.0s (60f):  Hold looking up (tick_0008 t=42-60)
    """
    v4 = str(VIDEO_DIR / "tick_0004.mp4")
    v6 = str(VIDEO_DIR / "tick_0006.mp4")
    v7 = str(VIDEO_DIR / "tick_0007.mp4")
    v8 = str(VIDEO_DIR / "tick_0008.mp4")

    frames = []
    # ACT 1
    frames += [(v4, t) for t in sample_times(3.0, 7.0, 30)]
    frames += [(v4, t) for t in sample_times(7.0, 9.5, 60)]
    frames += [(v4, t) for t in sample_times(10.0, 20.0, 60)]
    frames += [(v6, t) for t in sample_times(24.0, 27.0, 75)]
    frames += [(v6, t) for t in sample_times(28.0, 40.0, 75)]
    # ACT 2
    frames += [(v7, t) for t in sample_times(3.0, 8.0, 60)]
    frames += [(v7, t) for t in sample_times(8.0, 10.0, 60)]
    frames += [(v7, t) for t in sample_times(11.0, 25.0, 60)]
    frames += [(v7, t) for t in sample_times(40.0, 43.0, 75)]
    frames += [(v7, t) for t in sample_times(44.0, 55.0, 45)]
    # ACT 3
    frames += [(v8, t) for t in sample_times(5.0, 10.0, 60)]
    frames += [(v8, t) for t in sample_times(10.0, 13.0, 60)]
    frames += [(v8, t) for t in sample_times(14.0, 25.0, 45)]
    frames += [(v8, t) for t in sample_times(37.0, 41.0, 75)]
    frames += [(v8, t) for t in sample_times(42.0, 60.0, 60)]

    assert len(frames) == TOTAL_FRAMES, f"Need {TOTAL_FRAMES}, got {len(frames)}"
    return frames


def build_frame_sequence(use_upscale=False):
    source_map = build_source_map()

    from moviepy import VideoFileClip
    video_cache = {}

    print(f"Extracting {TOTAL_FRAMES} frames from 4 source videos...")
    raw_frames = []
    for i, (vpath, src_t) in enumerate(source_map):
        if vpath not in video_cache:
            video_cache[vpath] = VideoFileClip(vpath)
        clip = video_cache[vpath]
        src_t = min(src_t, clip.duration - 0.05)
        raw_frames.append(Image.fromarray(clip.get_frame(src_t)))
        if (i + 1) % 150 == 0:
            print(f"  Extracted {i + 1}/{TOTAL_FRAMES}")
    for c in video_cache.values():
        c.close()

    # Optional GPU upscale
    if use_upscale:
        print(f"Upscaling {TOTAL_FRAMES} frames with 4x-UltraSharp...")
        for i in range(len(raw_frames)):
            raw_frames[i] = upscale_frame(raw_frames[i])
            if (i + 1) % 90 == 0:
                print(f"  Upscaled {i + 1}/{TOTAL_FRAMES}")
        free_gpu()

    # Composite
    print("Compositing frames...")
    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)

    output_frames = []
    for i in range(TOTAL_FRAMES):
        t = i / FPS
        canvas = make_vertical_canvas(raw_frames[i])

        # Soft fade in
        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            linen_img = Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN)
            canvas = Image.blend(linen_img, canvas, fade)

        # Act transitions
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.4:
                dist = abs(t - act_t) / 0.4
                dim = 0.6 + 0.4 * dist
                linen_img = Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN)
                canvas = Image.blend(linen_img, canvas, dim)

        # Zoom on holds
        if 7.5 < t < 10.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.015 * ease_out((t - 7.5) / 2.5))
        elif 18.5 < t < 20.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.01 * ease_out((t - 18.5) / 1.5))
        elif 28.0 < t < 30.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.02 * ease_out((t - 28.0) / 2.0))

        # Fade to black
        if t > 29.0:
            fade = ease_out((DURATION - t) / 1.0)
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)
            canvas = Image.blend(black, canvas, fade)

        canvas = draw_particles(canvas, particles, t)
        canvas = film_grain(canvas, intensity=6.0)
        canvas = add_text_overlays(canvas, t)

        canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
        output_frames.append(np.array(canvas))

        if (i + 1) % 150 == 0:
            print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    print(f"  All {TOTAL_FRAMES} frames saved")
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
    parser = argparse.ArgumentParser(description="cc_flora Episode 02")
    parser.add_argument("--upscale", action="store_true", help="Use 4x-UltraSharp GPU upscaling (slow)")
    args = parser.parse_args()

    mode = "PREMIUM (4x-UltraSharp)" if args.upscale else "FAST (Lanczos)"
    print("=" * 64)
    print(f"  cc_flora -- Episode 02: The Bigger Room")
    print(f"  30s | 1080x1920 | 30fps | {mode}")
    print("=" * 64)
    print()

    audio_path = build_audio()
    frames = build_frame_sequence(use_upscale=args.upscale)

    print("\nAssembling video...")
    from moviepy import ImageSequenceClip, AudioFileClip
    video = ImageSequenceClip(list(frames), fps=FPS)
    video = video.with_audio(AudioFileClip(str(audio_path)))

    raw_path = OUTPUT_DIR / "cc_flora_ep02_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_ep02_bigger_room.mp4"

    video.write_videofile(str(raw_path), fps=FPS, codec="libx264",
                          audio_codec="aac", preset="medium", bitrate="3000k")

    print("Re-encoding for Bluesky...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-b:v", "3M", "-maxrate", "4M", "-bufsize", "6M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(output_path),
    ], check=True)
    raw_path.unlink(missing_ok=True)

    print()
    print("=" * 64)
    print(f"  DONE: {output_path}")
    print(f"  30 seconds. 900 frames. The Bigger Room.")
    print("=" * 64)


if __name__ == "__main__":
    main()
