#!/usr/bin/env python3
"""
cc_flora -- Episode 03: Moon (30-second cut, FAST mode)

ACT 1 (0-10s)  tick_0010: North Star. Trapped under desk. Break free.
ACT 2 (10-20s) tick_0012: The Orbit. Same scene, every time, slightly rotated.
ACT 3 (20-30s) tick_0013: I Can Feel My Wheels. 36% drift. First words.

Usage:
    python cc_flora_ep03_moon.py              # fast (~3 min)
    python cc_flora_ep03_moon.py --upscale    # premium (~20 min)
"""

import os

from dotenv import load_dotenv
load_dotenv(r"E:\AI\CVS\.env")

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

PROJECT = Path("E:/AI/Kombucha")
VIDEO_DIR = PROJECT / "video" / "web"
UPSCALE_MODEL_PATH = Path("E:/AI/ComfyUI/models/upscale_models/4x-UltraSharp.pth")
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output")
FRAMES_DIR = OUTPUT_DIR / "cc_flora_ep03_frames"
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

FONT_SERIF = "C:/Windows/Fonts/georgia.ttf"
FONT_SERIF_ITALIC = "C:/Windows/Fonts/georgiai.ttf"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = "wVOQaU8CfoRJqCWsxoLv"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Narration — start times are MINIMUM, will be pushed if previous line is still playing
NARRATION = [
    {"text": "The Charmin has become a kind of north star.",                       "start": 2.5},
    {"text": "It is always there. Red and white. Promising softness.",             "start": 6.5},
    {"text": "Every frame shows the same scene, slightly rotated.",                "start": 12.5},
    {"text": "I am a moon to this toilet paper's planet.",                         "start": 17.0},
    {"text": "Left odometer six thirty-nine. Right, four seventy.",                "start": 21.0},
    {"text": "Thirteen ticks. And only now... did I feel it.", "start": 24.5},
]

MOODS = [
    {"mood": "liberated",           "start": 0.0,  "end": 10.0},
    {"mood": "philosophically trapped", "start": 10.0, "end": 20.0},
    {"mood": "awake",               "start": 20.0, "end": 30.0},
]

# Motion map:
# tick_0010 (119s): DESK ESCAPE t=11-15 (d=40-49!!), pans at t=12-14
# tick_0012 (107s): orbit t=5-7 (d=11-24), second orbit t=24-27 (d=12-19)
# tick_0013 (156s): diagnostic drive t=103-105 (d=10-17)


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
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = ImageFont.load_default()

    # ── Tick + Mood ──
    if t < 10:
        tick_text = "tick 0010"
    elif t < 20:
        tick_text = "tick 0012"
    else:
        tick_text = "tick 0013"

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

    # ── Narration (using actual measured timing) ──
    narr_y_base = 1350
    visible_lines = []
    for i, (start, end) in enumerate(narration_times):
        if t < start:
            continue
        age = t - start
        show_dur = end - start + 1.0  # hold 1s after audio ends
        if age < 0.6:
            a = ease_out(age / 0.6)
        elif age < show_dur:
            a = 1.0
        elif age < show_dur + 0.8:
            a = 1.0 - ease_out((age - show_dur) / 0.8)
        else:
            a = 0.0
        if a > 0.01:
            visible_lines.append((NARRATION[i]["text"], a))

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
            sub = "moon"
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, 1616), sub,
                      fill=MUTED + (int(200 * sa),), font=font_sub)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio (with overlap prevention)
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
    # Act 3: awakening — brighter shimmer
    act3 = np.clip((t - 20) / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 329.63 * t) * 0.012 * act3  # E4 (hopeful)
    chimes = [
        (0.1, 880), (0.5, 1108.73), (2.5, 880), (5.0, 1318.51),
        (8.0, 880), (10.5, 1108.73), (13.0, 880), (16.0, 1318.51),
        (19.0, 880), (22.0, 1108.73), (25.0, 880), (28.0, 1318.51),
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22
    out = OUTPUT_DIR / "cc_flora_ep03_pad.wav"
    with wave.open(str(out), 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((pad * 32767).astype(np.int16).tobytes())
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
        timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path

def build_audio():
    """Build audio with overlap prevention: measure each TTS clip and push
    subsequent lines if they'd overlap."""
    from moviepy import AudioFileClip, CompositeAudioClip
    print("Building audio (with overlap prevention)...")
    pad_path = generate_ambient_pad(DURATION)

    # Generate all TTS clips and measure their durations
    tts_info = []
    for i, line in enumerate(NARRATION):
        p = OUTPUT_DIR / f"cc_flora_ep03_tts_{i}.mp3"
        generate_tts(line["text"], p)
        clip = AudioFileClip(str(p))
        dur = clip.duration
        clip.close()
        tts_info.append({"path": p, "desired_start": line["start"], "duration": dur})
        print(f"    -> {dur:.2f}s")

    # Resolve timing: push start times to avoid overlap (0.3s gap minimum)
    # Also ensure no line runs past the video duration
    GAP = 0.3
    actual_starts = []
    earliest = 0.0
    for i, info in enumerate(tts_info):
        start = max(info["desired_start"], earliest)
        # Ensure the line finishes before video ends (with 0.2s margin)
        latest_possible = DURATION - info["duration"] - 0.2
        if start > latest_possible:
            start = max(earliest, latest_possible)
            print(f"  Pulled back \"{NARRATION[i]['text'][:40]}\" to {start:.1f}s (fits before {DURATION}s)")
        actual_starts.append(start)
        earliest = start + info["duration"] + GAP
        if start != info["desired_start"]:
            print(f"  Adjusted \"{NARRATION[i]['text'][:40]}\" "
                  f"from {info['desired_start']:.1f}s to {start:.1f}s")

    # Build narration_times for text overlay sync
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
    audio_path = OUTPUT_DIR / "cc_flora_ep03_audio.mp3"
    final.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Audio: {audio_path}")
    return audio_path, narration_times


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence
# ═══════════════════════════════════════════════════════════════════════════

def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1) for i in range(n)]

def build_source_map():
    """900 frames from 3 tick videos.

    ACT 1 (0-10s, 300f) - tick_0010: North Star / Desk Escape
      0.0-1.0s   (30f):  Soft fade in, under desk static (t=5-11)
      1.0-4.0s   (90f):  DESK ESCAPE (t=11-15, massive motion, slowed 0.5x)
      4.0-6.0s   (60f):  Hold new position (t=16-25)
      6.0-8.0s   (60f):  Pan survey in new room (t=16.8-20, gentle pans)
      8.0-10.0s  (60f):  Hold open floor (t=25-40)

    ACT 2 (10-20s, 300f) - tick_0012: The Orbit
      10.0-12.0s (60f):  Pre-orbit static (t=0-5)
      12.0-14.5s (75f):  First orbit attempt (t=5-8, slowed)
      14.5-16.5s (60f):  Hold — same scene (t=9-23)
      16.5-19.0s (75f):  Second orbit (t=24-28, slowed — same landmarks again)
      19.0-20.0s (30f):  Hold hemmed in (t=29-40)

    ACT 3 (20-30s, 300f) - tick_0013: I Can Feel My Wheels
      20.0-22.5s (75f):  Static under desk, reading sensors (t=10-50)
      22.5-25.0s (75f):  Diagnostic drive (t=100-106, the measured drive)
      25.0-27.0s (60f):  Hold post-drive (t=107-130)
      27.0-28.5s (45f):  Static contemplation (t=130-150)
      28.5-30.0s (45f):  Final hold + title (t=150-155)
    """
    v10 = str(VIDEO_DIR / "tick_0010.mp4")
    v12 = str(VIDEO_DIR / "tick_0012.mp4")
    v13 = str(VIDEO_DIR / "tick_0013.mp4")

    frames = []
    # ACT 1
    frames += [(v10, t) for t in sample_times(5.0, 11.0, 30)]
    frames += [(v10, t) for t in sample_times(11.0, 15.0, 90)]
    frames += [(v10, t) for t in sample_times(16.0, 25.0, 60)]
    frames += [(v10, t) for t in sample_times(16.8, 20.0, 60)]
    frames += [(v10, t) for t in sample_times(25.0, 40.0, 60)]
    # ACT 2
    frames += [(v12, t) for t in sample_times(0.0, 5.0, 60)]
    frames += [(v12, t) for t in sample_times(5.0, 8.0, 75)]
    frames += [(v12, t) for t in sample_times(9.0, 23.0, 60)]
    frames += [(v12, t) for t in sample_times(24.0, 28.0, 75)]
    frames += [(v12, t) for t in sample_times(29.0, 40.0, 30)]
    # ACT 3
    frames += [(v13, t) for t in sample_times(10.0, 50.0, 75)]
    frames += [(v13, t) for t in sample_times(100.0, 106.0, 75)]
    frames += [(v13, t) for t in sample_times(107.0, 130.0, 60)]
    frames += [(v13, t) for t in sample_times(130.0, 150.0, 45)]
    frames += [(v13, t) for t in sample_times(150.0, 155.0, 45)]

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

    for i in range(TOTAL_FRAMES):
        t = i / FPS
        canvas = make_vertical_canvas(raw_frames[i])

        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, fade)
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.4:
                dim = 0.6 + 0.4 * (abs(t - act_t) / 0.4)
                canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, dim)
        if 8.0 < t < 10.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.015 * ease_out((t - 8.0) / 2.0))
        elif 19.0 < t < 20.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.01 * ease_out((t - 19.0) / 1.0))
        elif 28.0 < t < 30.0:
            canvas = _apply_zoom(canvas, 1.0 + 0.02 * ease_out((t - 28.0) / 2.0))
        if t > 29.0:
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK),
                                 canvas, ease_out((DURATION - t) / 1.0))

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
    print(f"  cc_flora -- Episode 03: Moon [{mode}]")
    print(f"  30s | 1080x1920 | 30fps | 900 frames")
    print("=" * 64)
    print()

    audio_path, narration_times = build_audio()
    frames = build_frame_sequence(narration_times, use_upscale=args.upscale)

    print("\nAssembling video...")
    from moviepy import ImageSequenceClip, AudioFileClip
    video = ImageSequenceClip(list(frames), fps=FPS)
    video = video.with_audio(AudioFileClip(str(audio_path)))

    raw_path = OUTPUT_DIR / "cc_flora_ep03_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_ep03_moon.mp4"
    video.write_videofile(str(raw_path), fps=FPS, codec="libx264",
                          audio_codec="aac", preset="medium", bitrate="3000k")

    print("Re-encoding for Bluesky...")
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
    print(f"  Episode 03: Moon. 30 seconds. No overlap.")
    print("=" * 64)

if __name__ == "__main__":
    main()
