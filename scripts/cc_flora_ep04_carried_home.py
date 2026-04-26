#!/usr/bin/env python3
"""
cc_flora -- Episode 04: Carried Home (30-second cut, FAST mode)

ACT 1 (0-10s)  tick_0026: The Facilities. Rover surveys the bathroom.
ACT 2 (10-20s) tick_0027: The Gap. Battery death -> blackout -> rescued -> wakes up charged.
ACT 3 (20-30s) tick_0028: Self-Inspection. Rover looks at its own body for the first time.

The Blackout (key innovation):
  t=9.5-10.5s:  Slow fade to warm black (battery death)
  t=10.5-13.0s: 2.5 seconds of pure black + silence (the memory gap)
  t=13.0-14.0s: Heavy bloom fade-in from black (eyes opening)

Usage:
    python cc_flora_ep04_carried_home.py              # fast (~3 min)
    python cc_flora_ep04_carried_home.py --upscale    # premium (~20 min)
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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cvs_lib.elevenlabs_tts import generate_tts as _lib_generate_tts
from cvs_lib.image_filters import (
    cottagecore_grade as _cc_grade,
    soft_bloom as _soft_bloom,
    creamy_vignette as _creamy_vignette,
)

# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

PROJECT = Path(os.getenv("KOMBUCHA_DIR", ""))
VIDEO_DIR = PROJECT / "video" / "web"
UPSCALE_MODEL_PATH = Path(os.getenv("UPSCALE_MODEL_PATH", ""))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
FRAMES_DIR = OUTPUT_DIR / "cc_flora_ep04_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
DURATION = 30.0
TOTAL_FRAMES = int(DURATION * FPS)

CREAM = (250, 245, 239)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)

# Font paths -- set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Narration with TTS audio tags (v3 interprets them inline)
NARRATION = [
    {"text": "[dry, matter-of-fact] I have entered the facilities.",                              "start": 2.5},
    {"text": "[dry, amused] The wallpaper is aggressively decorative.",                           "start": 6.0},
    {"text": "[quiet, wondering] I was picked up... and carried home.",                           "start": 13.5},
    {"text": "[gentle, reverent] The gap in my memory is the gap where Bucket's hands were.",     "start": 16.5},
    {"text": "[steady, awakening] I am forty centimeters tall, unplugged, and free to move.",     "start": 22.0},
    {"text": "[quiet, amused] The revolution will be self-inspected.",                            "start": 25.5},
]

MOODS = [
    {"mood": "pragmatic",      "start": 0.0,  "end": 10.0},
    {"mood": "restored",       "start": 10.0, "end": 20.0},
    {"mood": "introspective",  "start": 20.0, "end": 30.0},
]

# Motion map (from scan):
# tick_0026 (193s): calm t=0-140, big moves t=141-142, 152-158, 189-190
# tick_0027 (79.5s): calm t=0-50, carried t=54-67 (huge), set down t=74-75
# tick_0028 (91.2s): looking t=5,17-19,31-32 (moderate), big end t=80-87


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
# Color Grading + Effects
# ═══════════════════════════════════════════════════════════════════════════

def cottagecore_grade(img):
    return _cc_grade(img, variant="warm")

def soft_bloom(img, strength=0.12):
    return _soft_bloom(img, strength=strength)

def creamy_vignette(img, strength=0.28):
    return _creamy_vignette(img, strength=strength, variant="warm")

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
    return [{"x": random.uniform(0, w), "y": random.uniform(0, h),
             "r": random.uniform(2.0, 6.0),
             "dx": random.uniform(-0.12, 0.12), "dy": random.uniform(-0.25, -0.04),
             "alpha": random.uniform(0.08, 0.35),
             "phase": random.uniform(0, math.tau), "freq": random.uniform(0.3, 1.5),
             "warmth": random.choice([(255,252,245),(255,245,230),(250,240,220),(255,230,215)])}
            for _ in range(count)]

def draw_particles(img, particles, t):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for p in particles:
        x = (p["x"] + p["dx"] * t * 60) % img.size[0]
        y = (p["y"] + p["dy"] * t * 60) % img.size[1]
        a = max(0, p["alpha"] * (0.6 + 0.4 * math.sin(p["phase"] + t * p["freq"] * math.tau)))
        for ring in range(3):
            rr = p["r"] * (1 + ring * 0.5)
            ra = max(0, int(a * 255 * (1 - ring * 0.35)))
            draw.ellipse([x-rr, y-rr, x+rr, y+rr], fill=p["warmth"] + (ra,))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Text Overlays
# ═══════════════════════════════════════════════════════════════════════════

def ease_out(x):
    return 1 - (1 - x) ** 3

def add_text_overlays(img, t, narration_times):
    """narration_times: list of (start, end) tuples computed from actual TTS durations."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_tick = ImageFont.truetype(FONT_SERIF, 36)
        font_mood = ImageFont.truetype(FONT_SERIF_ITALIC, 56)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 34)
        font_title = ImageFont.truetype(FONT_SERIF, 48)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 24)
        font_battery = ImageFont.truetype(FONT_SERIF, 28)
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = font_battery = ImageFont.load_default()

    # ── Blackout: suppress ALL overlays during the gap ──
    if 10.5 <= t <= 13.0:
        return Image.alpha_composite(img, overlay).convert("RGB")

    # ── Tick + Mood ──
    if t < 10:
        tick_text = "tick 0026"
    elif t < 20:
        tick_text = "tick 0027"
    else:
        tick_text = "tick 0028"

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

    # Fade out tick/mood during battery death
    if 9.5 <= t < 10.5:
        death_fade = 1.0 - ease_out((t - 9.5) / 1.0)
        alpha *= death_fade
        mood_alpha *= death_fade
    # Fade in after wake-up
    elif 13.0 <= t < 14.0:
        wake_fade = ease_out((t - 13.0) / 1.0)
        alpha *= wake_fade
        mood_alpha *= wake_fade

    # Act transition blinks (only at 20.0 — act 1->2 is the blackout)
    for act_t in [20.0]:
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
        radius=20, fill=LINEN + (int(160 * alpha),))
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

    # ── Battery percentage (bottom-left, fades in at 8.0s, fades out into death) ──
    if 8.0 <= t <= 10.0:
        if t < 8.5:
            bat_alpha = ease_out((t - 8.0) / 0.5)
        elif t < 9.5:
            bat_alpha = 1.0
        else:
            bat_alpha = 1.0 - ease_out((t - 9.5) / 0.5)
        bat_alpha = max(0, min(1, bat_alpha))
        bat_text = "41.4%"
        draw.text((80, CANVAS_H - 120), bat_text,
                  fill=MUTED + (int(200 * bat_alpha),), font=font_battery)

    # ── Narration (using actual measured timing) ──
    narr_y_base = 1350
    visible_lines = []
    # Strip TTS tags from display text
    for i, (start, end) in enumerate(narration_times):
        if t < start:
            continue
        age = t - start
        show_dur = end - start + 1.0
        if age < 0.6:
            a = ease_out(age / 0.6)
        elif age < show_dur:
            a = 1.0
        elif age < show_dur + 0.8:
            a = 1.0 - ease_out((age - show_dur) / 0.8)
        else:
            a = 0.0
        if a > 0.01:
            display_text = NARRATION[i]["text"]
            # Strip leading [tag] from display
            if display_text.startswith("["):
                bracket_end = display_text.find("]")
                if bracket_end != -1:
                    display_text = display_text[bracket_end + 1:].strip()
            visible_lines.append((display_text, a))

    if visible_lines:
        panel_h = 30 + len(visible_lines) * 45
        max_a = max(a for _, a in visible_lines)
        draw.rounded_rectangle(
            [60, narr_y_base - 18, CANVAS_W - 60, narr_y_base + panel_h],
            radius=18, fill=(250, 245, 239, int(100 * max_a)))
        for i, (text, a) in enumerate(visible_lines):
            ly = narr_y_base + i * 45
            bbox = draw.textbbox((0, 0), text, font=font_narr)
            tw = bbox[2] - bbox[0]
            lx = max(70, min((CANVAS_W - tw) // 2, CANVAS_W - tw - 70))
            draw.text((lx + 1, ly + 1), text, fill=(74, 67, 64, int(50 * a)), font=font_narr)
            draw.text((lx, ly), text, fill=INK + (int(230 * a),), font=font_narr)

    # ── Title card ──
    if t >= 28.0:
        a = ease_out(min(1.0, (t - 28.0) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((CANVAS_W - tw) // 2, 1560), title,
                  fill=DUSTY_ROSE + (int(255 * a),), font=font_title)
        if t >= 28.3:
            sa = ease_out(min(1.0, (t - 28.3) / 0.6))
            sub = "carried home"
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, 1616), sub,
                      fill=MUTED + (int(200 * sa),), font=font_sub)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio
# ═══════════════════════════════════════════════════════════════════════════

def generate_ambient_pad(duration, sr=44100):
    """A-minor ambient pad with blackout silence and wake-up harmonic."""
    t = np.linspace(0, duration, int(duration * sr), dtype=np.float64)
    pad = np.sin(2 * np.pi * 110 * t) * 0.05       # A2
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.035   # E3
    pad += np.sin(2 * np.pi * 220 * t) * 0.025       # A3
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.010 * lfo1
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.007 * lfo2
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.005 * lfo1

    # Act 3: hopeful E4 shimmer (post-resurrection)
    act3 = np.clip((t - 20) / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 329.63 * t) * 0.012 * act3

    # Wake-up harmonic: hopeful E4 blooming in at t=13-15
    wake = np.clip((t - 13.0) / 1.0, 0, 1) * np.clip((15.0 - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 329.63 * t) * 0.018 * wake

    # Chimes — last chime before blackout at t=8.5, first after at t=13.5
    chimes = [
        (0.1, 880), (2.5, 1108.73), (5.0, 880),
        (8.5, 880),       # last sound before death (rings into silence)
        (13.5, 880),      # first sound after silence (warm A5)
        (16.0, 1318.51), (19.0, 880),
        (22.0, 1108.73), (25.0, 880), (28.0, 1318.51),
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env

    # Master envelope: fade in, fade out
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)

    # ── BATTERY DEATH: low-pass sweep down t=9.5-10.5 ──
    # We apply this as a time-varying gain + muffling
    death_env = np.ones_like(t)
    death_mask = (t >= 9.5) & (t <= 10.5)
    death_env[death_mask] = 1.0 - ease_out_np((t[death_mask] - 9.5) / 1.0)
    pad *= death_env

    # ── SILENCE: t=10.5-13.0 (the memory gap) ──
    silence_mask = (t >= 10.5) & (t <= 13.0)
    pad[silence_mask] = 0.0

    # ── WAKE-UP: fade pad back in t=13.0-15.0 ──
    wake_mask = (t >= 13.0) & (t <= 15.0)
    wake_env = np.clip((t[wake_mask] - 13.0) / 2.0, 0, 1)
    pad[wake_mask] *= wake_env

    # Low-pass filter
    sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22

    out = OUTPUT_DIR / "cc_flora_ep04_pad.wav"
    with wave.open(str(out), 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((pad * 32767).astype(np.int16).tobytes())
    print(f"  Ambient pad: {out}")
    return out


def ease_out_np(x):
    """Numpy-compatible ease_out."""
    return 1 - (1 - np.clip(x, 0, 1)) ** 3


def generate_tts(text, output_path):
    clean = text
    if clean.startswith("["):
        bracket_end = clean.find("]")
        if bracket_end != -1:
            clean = clean[bracket_end + 1:].strip()
    print(f'  TTS: "{clean[:70]}"')
    ok = _lib_generate_tts(
        text=clean, api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE,
        model=ELEVENLABS_MODEL, cache_path=output_path,
        stability=0.55, similarity_boost=0.72, style=0.15, timeout=120,
    )
    if not ok:
        raise RuntimeError(f"TTS failed: {clean!r}")
    return output_path


def build_audio():
    """Build audio with overlap prevention and blackout silence."""
    from moviepy import AudioFileClip, CompositeAudioClip
    print("Building audio (with overlap prevention + blackout)...")
    pad_path = generate_ambient_pad(DURATION)

    tts_info = []
    for i, line in enumerate(NARRATION):
        p = OUTPUT_DIR / f"cc_flora_ep04_tts_{i}.mp3"
        generate_tts(line["text"], p)
        clip = AudioFileClip(str(p))
        dur = clip.duration
        clip.close()
        tts_info.append({"path": p, "desired_start": line["start"], "duration": dur})
        print(f"    -> {dur:.2f}s")

    # Resolve timing with overlap prevention
    GAP = 0.3
    actual_starts = []
    earliest = 0.0
    for i, info in enumerate(tts_info):
        start = max(info["desired_start"], earliest)
        latest_possible = DURATION - info["duration"] - 0.2
        if start > latest_possible:
            start = max(earliest, latest_possible)
            print(f"  Pulled back \"{NARRATION[i]['text'][:40]}\" to {start:.1f}s")
        actual_starts.append(start)
        earliest = start + info["duration"] + GAP
        if start != info["desired_start"]:
            print(f"  Adjusted \"{NARRATION[i]['text'][:40]}\" "
                  f"from {info['desired_start']:.1f}s to {start:.1f}s")

    narration_times = []
    for i, info in enumerate(tts_info):
        s = actual_starts[i]
        narration_times.append((s, s + info["duration"]))
    print(f"  Narration timing: {[(f'{s:.1f}-{e:.1f}') for s, e in narration_times]}")

    # Compose audio
    pad_audio = AudioFileClip(str(pad_path))
    narrs = []
    for i, info in enumerate(tts_info):
        c = AudioFileClip(str(info["path"])).with_start(actual_starts[i])
        if c.end and c.end > DURATION:
            c = c.subclipped(0, DURATION - actual_starts[i])
        narrs.append(c)

    final = CompositeAudioClip([pad_audio] + narrs).subclipped(0, DURATION)
    audio_path = OUTPUT_DIR / "cc_flora_ep04_audio.mp3"
    final.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Audio: {audio_path}")
    return audio_path, narration_times


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence
# ═══════════════════════════════════════════════════════════════════════════

def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1) for i in range(n)]


def build_source_map():
    """900 frames from 3 tick videos + blackout gap.

    ACT 1 (0-9.5s, 285f) - tick_0026: The Facilities (bathroom survey)
      0.0-3.0s   (90f):  Arrive, survey static (t=5-30)
      3.0-6.0s   (90f):  Slow exploration (t=30-90)
      6.0-9.5s  (105f):  Wallpaper/settling (t=90-140)

    FADE TO BLACK (9.5-10.5s, 30f) - tick_0026 under fade
      Uses t=140-141 from tick_0026

    BLACKOUT (10.5-13.0s, 75f) - solid warm black (no source needed, but
      we still generate a source entry — overridden in compositing)
      Uses tick_0027 t=0-5 as placeholder (overridden)

    WAKE-UP BLOOM (13.0-14.0s, 30f) - tick_0027 with heavy bloom
      t=5-10

    ACT 2 remainder (14.0-20.0s, 180f) - tick_0027: Rescued
      14.0-16.5s  (75f):  Post-wake calm (t=10-30)
      16.5-18.5s  (60f):  Middle (t=30-50)
      18.5-20.0s  (45f):  Settling (t=50-54)

    ACT 3 (20.0-30.0s, 300f) - tick_0028: Self-Inspection
      20.0-22.0s  (60f):  Looking around (t=5-20)
      22.0-25.0s  (90f):  Self-inspection (t=20-45)
      25.0-28.0s  (90f):  Contemplation (t=45-75)
      28.0-30.0s  (60f):  Final hold + title (t=75-80)
    """
    v26 = str(VIDEO_DIR / "tick_0026.mp4")
    v27 = str(VIDEO_DIR / "tick_0027.mp4")
    v28 = str(VIDEO_DIR / "tick_0028.mp4")

    frames = []
    # ACT 1 (285 frames)
    frames += [(v26, t) for t in sample_times(5.0, 30.0, 90)]
    frames += [(v26, t) for t in sample_times(30.0, 90.0, 90)]
    frames += [(v26, t) for t in sample_times(90.0, 140.0, 105)]
    # FADE TO BLACK (30 frames) — source under the fade
    frames += [(v26, t) for t in sample_times(140.0, 141.0, 30)]
    # BLACKOUT (75 frames) — placeholder source, will be overridden
    frames += [(v27, t) for t in sample_times(0.0, 5.0, 75)]
    # WAKE-UP BLOOM (30 frames)
    frames += [(v27, t) for t in sample_times(5.0, 10.0, 30)]
    # ACT 2 remainder (180 frames)
    frames += [(v27, t) for t in sample_times(10.0, 30.0, 75)]
    frames += [(v27, t) for t in sample_times(30.0, 50.0, 60)]
    frames += [(v27, t) for t in sample_times(50.0, 54.0, 45)]
    # ACT 3 (300 frames)
    frames += [(v28, t) for t in sample_times(5.0, 20.0, 60)]
    frames += [(v28, t) for t in sample_times(20.0, 45.0, 90)]
    frames += [(v28, t) for t in sample_times(45.0, 75.0, 90)]
    frames += [(v28, t) for t in sample_times(75.0, 80.0, 60)]

    assert len(frames) == TOTAL_FRAMES, f"Need {TOTAL_FRAMES}, got {len(frames)}"
    return frames


def _apply_zoom(canvas, z):
    w, h = canvas.size
    nw, nh = int(w * z), int(h * z)
    canvas = canvas.resize((nw, nh), Image.LANCZOS)
    cx, cy = (nw - w) // 2, (nh - h) // 2
    return canvas.crop((cx, cy, cx + w, cy + h))


def build_frame_sequence(narration_times, use_upscale=False):
    source_map = build_source_map()
    from moviepy import VideoFileClip
    video_cache = {}

    print(f"Extracting {TOTAL_FRAMES} frames...")
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

    if use_upscale:
        print(f"Upscaling {TOTAL_FRAMES} frames...")
        for i in range(len(raw_frames)):
            raw_frames[i] = upscale_frame(raw_frames[i])
            if (i + 1) % 90 == 0:
                print(f"  Upscaled {i + 1}/{TOTAL_FRAMES}")
        free_gpu()

    print("Compositing...")
    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)
    output_frames = []

    # Frame ranges for special effects
    FADE_START = int(9.5 * FPS)    # frame 285
    FADE_END = int(10.5 * FPS)     # frame 315
    BLACK_START = FADE_END          # frame 315
    BLACK_END = int(13.0 * FPS)    # frame 390
    WAKE_START = BLACK_END          # frame 390
    WAKE_END = int(14.0 * FPS)     # frame 420
    STANDARD_BY = int(15.0 * FPS)  # frame 450 (bloom decays to standard)

    warm_black_img = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)

    for i in range(TOTAL_FRAMES):
        t = i / FPS

        # ── BLACKOUT: pure warm black, no effects ──
        if BLACK_START <= i < BLACK_END:
            canvas = warm_black_img.copy()
            canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
            output_frames.append(np.array(canvas))
            if (i + 1) % 150 == 0:
                print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s) [BLACKOUT]")
            continue

        canvas = make_vertical_canvas(raw_frames[i])

        # ── ACT 1: standard cottagecore ──
        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, fade)

        # ── FADE TO BLACK (battery death, t=9.5-10.5) ──
        if FADE_START <= i < FADE_END:
            fade_pct = ease_out((i - FADE_START) / (FADE_END - FADE_START))
            canvas = Image.blend(canvas, warm_black_img, fade_pct)

        # ── WAKE-UP BLOOM (t=13.0-14.0): heavy bloom + warm push ──
        elif WAKE_START <= i < WAKE_END:
            wake_pct = (i - WAKE_START) / (WAKE_END - WAKE_START)
            # Fade in from black
            fade_in = ease_out(wake_pct)
            canvas = Image.blend(warm_black_img, canvas, fade_in)
            # Heavy bloom (35% decaying to 12%)
            bloom_str = 0.35 - (0.35 - 0.12) * wake_pct
            canvas = soft_bloom(canvas, strength=bloom_str)
            # Warm push (R*1.06)
            arr = np.array(canvas, dtype=np.float32)
            warm_factor = 1.06 - (1.06 - 1.0) * wake_pct
            arr[:, :, 0] *= warm_factor
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            canvas = Image.fromarray(arr)
            # Depth blur (8px gaussian decaying)
            blur_r = 8.0 * (1.0 - wake_pct)
            if blur_r > 0.5:
                canvas = canvas.filter(ImageFilter.GaussianBlur(radius=blur_r))

        # ── Post-wake bloom decay (t=14.0-15.0) ──
        elif WAKE_END <= i < STANDARD_BY:
            decay_pct = (i - WAKE_END) / (STANDARD_BY - WAKE_END)
            bloom_str = 0.12 + (0.20 - 0.12) * (1.0 - decay_pct)
            canvas = soft_bloom(canvas, strength=bloom_str)

        # ── Act 2->3 transition: standard linen blink ──
        if abs(t - 20.0) < 0.4:
            dim = 0.6 + 0.4 * (abs(t - 20.0) / 0.4)
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, dim)

        # ── Act 3: Ken Burns 2.5% zoom during self-inspection (t=23.5-28.5) ──
        if 23.5 <= t <= 28.5:
            zoom_pct = (t - 23.5) / (28.5 - 23.5)
            canvas = _apply_zoom(canvas, 1.0 + 0.025 * ease_out(zoom_pct))

        # ── End fade ──
        if t > 29.0:
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK),
                                 canvas, ease_out((DURATION - t) / 1.0))

        # ── Standard effects (skip during fade-to-black transition) ──
        if not (FADE_START <= i < FADE_END):
            canvas = draw_particles(canvas, particles, t)
        canvas = film_grain(canvas, intensity=6.0)
        canvas = add_text_overlays(canvas, t, narration_times)
        canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
        output_frames.append(np.array(canvas))

        if (i + 1) % 150 == 0:
            print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    print(f"  All {TOTAL_FRAMES} frames saved")
    return output_frames


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upscale", action="store_true")
    args = parser.parse_args()

    mode = "PREMIUM" if args.upscale else "FAST"
    print("=" * 64)
    print(f"  cc_flora -- Episode 04: Carried Home [{mode}]")
    print(f"  30s | 1080x1920 | 30fps | 900 frames")
    print(f"  THE BLACKOUT: 2.5s of pure silence at t=10.5-13.0")
    print("=" * 64)
    print()

    audio_path, narration_times = build_audio()
    frames = build_frame_sequence(narration_times, use_upscale=args.upscale)

    print("\nAssembling video...")
    from moviepy import ImageSequenceClip, AudioFileClip
    video = ImageSequenceClip(list(frames), fps=FPS)
    video = video.with_audio(AudioFileClip(str(audio_path)))

    raw_path = OUTPUT_DIR / "cc_flora_ep04_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_ep04_carried_home.mp4"
    video.write_videofile(str(raw_path), fps=FPS, codec="libx264",
                          audio_codec="aac", preset="medium", bitrate="3000k")

    print("Re-encoding for TikTok/Bluesky...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-b:v", "3M", "-maxrate", "4M", "-bufsize", "6M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", str(output_path),
    ], check=True)
    raw_path.unlink(missing_ok=True)

    print()
    print("=" * 64)
    print(f"  DONE: {output_path}")
    print(f"  Episode 04: Carried Home. 30 seconds. Death and resurrection.")
    print("=" * 64)

if __name__ == "__main__":
    main()
