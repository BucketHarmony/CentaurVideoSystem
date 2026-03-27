#!/usr/bin/env python
import sys, io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""Kombucha full-episode production via ComfyUI pipeline nodes.

3-act, 30-second episodes from multiple ticks. Uses CosyMotes effects,
MotionClip, 4x upscale, multi-line narration, per-act text overlays.

Usage:
    python produce_episode.py episode.json
    python produce_episode.py episode.json --no-upscale
    python produce_episode.py episode.json --dry-run

Episode JSON format:
{
    "number": 11,
    "title": "The Patience of Rooms",
    "acts": [
        {"tick": 46, "mood": "recalculating",
         "motion_range": [56.0, 58.0],
         "narration": [
             {"text": "Left drift introduces you to furniture.", "start": 2.5},
             {"text": "The bright room waits.", "start": 7.0}
         ]},
        {"tick": 48, "mood": "liminal", ...},
        {"tick": 49, "mood": "threshold", ...}
    ]
}
"""

import argparse
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
import wave

import cv2
import numpy as np
import scipy.signal
import torch
import torchaudio
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

# ── paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI_DIR = os.path.join(SCRIPT_DIR, "..", "..")
KOMBUCHA_DIR = r"E:\AI\Kombucha"
OUTPUT_DIR = os.path.join(COMFYUI_DIR, "output")
ENV_FILE = r"E:\AI\CVS\.env"
UPSCALE_MODEL = os.path.join(COMFYUI_DIR, "models", "upscale_models", "4x-UltraSharp.pth")

CANVAS_W, CANVAS_H = 1080, 1080  # Square output
FPS = 30
DURATION = 30.0
TOTAL_FRAMES = int(DURATION * FPS)  # 900
ACT_FRAMES = 300  # 10s per act
SR = 44100

FONT_SERIF = "C:/Windows/Fonts/georgia.ttf"
FONT_SERIF_ITALIC = "C:/Windows/Fonts/georgiai.ttf"

# Palette (matching Flora cottagecore)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)
PILL_BG = (245, 238, 228)

load_dotenv(ENV_FILE)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "wVOQaU8CfoRJqCWsxoLv")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# ── load pipeline nodes ───────────────────────────────────────────────
_spec = importlib.util.spec_from_file_location(
    "kombucha_nodes", os.path.join(SCRIPT_DIR, "nodes.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
CosyMotes = _mod.CosyMotes


# ══════════════════════════════════════════════════════════════════════
# Video frame extraction
# ══════════════════════════════════════════════════════════════════════

def find_video(tick_num):
    for d in [os.path.join(KOMBUCHA_DIR, "video", "web"),
              os.path.join(KOMBUCHA_DIR, "video")]:
        path = os.path.join(d, f"tick_{tick_num:04d}.mp4")
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No video for tick {tick_num}")


def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1)
            for i in range(n)]


def extract_frames_for_act(act_config):
    """Extract 300 frames for one act from a tick video.

    act_config has: tick, motion_range [start, end], and optional
    pre_motion_range, post_motion_range for static segments.
    """
    tick = act_config["tick"]
    video_path = find_video(tick)
    cap = cv2.VideoCapture(video_path)
    total_dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    try:
        from moviepy import VideoFileClip
    except ImportError:
        from moviepy.editor import VideoFileClip
    clip = VideoFileClip(video_path)

    motion_start, motion_end = act_config["motion_range"]
    # Default: static before motion, motion slowed, static after
    pre_start = act_config.get("pre_start", 2.0)
    pre_end = act_config.get("pre_end", motion_start - 1.0)
    post_start = act_config.get("post_start", motion_end + 0.5)
    post_end = act_config.get("post_end", min(total_dur - 0.5, motion_end + 15.0))

    # Frame allocation: heavy slow-mo on motion
    # 60 pre (2s), 180 motion (6s from ~2s source = 0.33x), 60 post (2s)
    pre_frames = 60
    motion_frames = 180
    post_frames = ACT_FRAMES - pre_frames - motion_frames  # 60

    source_times = []
    source_times += sample_times(pre_start, pre_end, pre_frames)
    source_times += sample_times(motion_start, motion_end, motion_frames)
    source_times += sample_times(post_start, post_end, post_frames)

    frames = []
    for t in source_times:
        t = min(t, clip.duration - 0.05)
        frames.append(Image.fromarray(clip.get_frame(t)))
    clip.close()

    assert len(frames) == ACT_FRAMES, f"Act needs {ACT_FRAMES}, got {len(frames)}"
    return frames


# ══════════════════════════════════════════════════════════════════════
# CosyMotes effects via pipeline node
# ══════════════════════════════════════════════════════════════════════

def apply_cosymotes(frames_pil):
    """Apply CosyMotes ethereal effects to a list of PIL images."""
    # Convert to tensor (B, H, W, C) float32 [0, 1]
    arrays = [np.array(f).astype(np.float32) / 255.0 for f in frames_pil]
    tensor = torch.from_numpy(np.stack(arrays)).float()

    cm = CosyMotes()
    result = cm.apply(
        images=tensor,
        tiltshift_strength=0.8,
        focus_near=0.75,
        focus_far=0.15,
        bloom_strength=0.25,
        ray_strength=80.0,
        vignette_strength=0.3,
        haze_strength=0.10,
        shadow_lift=0.05,
        warmth=1.04,
        seed=42,
    )
    effected = result[0]  # (B, H, W, C) tensor

    # Convert back to PIL
    out = []
    for i in range(effected.shape[0]):
        arr = (effected[i].numpy() * 255).clip(0, 255).astype(np.uint8)
        out.append(Image.fromarray(arr))
    return out


# ══════════════════════════════════════════════════════════════════════
# 4x GPU Upscale
# ══════════════════════════════════════════════════════════════════════

_upscale_model = None

def load_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        return _upscale_model
    import spandrel
    print("  Loading 4x-UltraSharp on CUDA...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL))
    model = model.to("cuda").eval()
    _upscale_model = model
    return model

def upscale_frame(pil_img):
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
        del _upscale_model
        _upscale_model = None
        torch.cuda.empty_cache()


# ══════════════════════════════════════════════════════════════════════
# Vertical canvas compositing (from Flora pipeline)
# ══════════════════════════════════════════════════════════════════════

def soft_bloom(img, strength=0.05):
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def creamy_vignette(img, strength=0.55):
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vig = np.clip((dist / max_dist - 0.25) / 0.55, 0, 1) ** 1.4
    vig = vig[:, :, np.newaxis] * strength
    shadow = np.array((55, 48, 42), dtype=np.float32)
    arr = arr * (1 - vig) + shadow * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def film_grain(img, intensity=5.0):
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    lum = arr.mean(axis=2, keepdims=True) / 255.0
    mask = np.clip(1.0 - 2.0 * np.abs(lum - 0.5), 0.3, 1.0)
    arr += noise * mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def make_square_canvas(frame):
    """Place frame into 1080x1080 square with blurred fill in letterbox areas.

    The trick: scale the frame up to fill the full square, blur it heavily,
    darken it, then paste the sharp original centered on top.
    """
    frame = soft_bloom(frame)
    fw, fh = frame.size

    # Sharp video: scale to fill width, centered vertically
    scale = CANVAS_W / fw
    new_w = CANVAS_W
    new_h = int(fh * scale)
    sharp = frame.resize((new_w, new_h), Image.LANCZOS)

    # Blurred fill: scale to fill the entire square (crop to fit)
    bg_scale = max(CANVAS_W / fw, CANVAS_H / fh)
    bg_w = int(fw * bg_scale)
    bg_h = int(fh * bg_scale)
    bg = frame.resize((bg_w, bg_h), Image.LANCZOS)
    # Center crop to 1080x1080
    cx = (bg_w - CANVAS_W) // 2
    cy = (bg_h - CANVAS_H) // 2
    bg = bg.crop((max(0, cx), max(0, cy),
                  max(0, cx) + CANVAS_W, max(0, cy) + CANVAS_H))
    if bg.size != (CANVAS_W, CANVAS_H):
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

    # Heavy blur + darken the background
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    bg_arr = np.array(bg, dtype=np.float32) * 0.35  # darken to 35%
    bg = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))

    # Paste sharp video centered
    canvas = bg.copy()
    y_off = (CANVAS_H - new_h) // 2
    canvas.paste(sharp, (0, y_off))

    canvas = creamy_vignette(canvas, strength=0.4)
    return canvas


# ══════════════════════════════════════════════════════════════════════
# Particles
# ══════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════
# Text overlays (per-act tick pill, mood, narration, title card)
# ══════════════════════════════════════════════════════════════════════

def ease_out(x):
    return 1 - (1 - x) ** 3

MAX_TEXT_W = CANVAS_W - 140

def wrap_text(text, font, max_w, draw):
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = f"{current} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_w and current:
            lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def add_text_overlays(img, t, episode_config, narration_lines, narration_times):
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_tick = ImageFont.truetype(FONT_SERIF, 40)
        font_mood = ImageFont.truetype(FONT_SERIF_ITALIC, 60)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 36)
        font_title = ImageFont.truetype(FONT_SERIF, 48)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 26)
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = ImageFont.load_default()

    acts = episode_config["acts"]
    act_idx = min(int(t / 10.0), 2)
    act = acts[act_idx]
    tick_text = f"tick {act['tick']:04d}"
    current_mood = act["mood"]

    # Global alpha
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

    # Tick pill — positioned for square canvas
    bbox = draw.textbbox((0, 0), tick_text, font=font_tick)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    px = (CANVAS_W - tw) // 2
    py = 60  # higher for square
    pad_x, pad_y = 30, 16
    draw.rounded_rectangle(
        [px - pad_x, py - pad_y, px + tw + pad_x, py + th + pad_y],
        radius=22, fill=PILL_BG + (int(210 * alpha),))
    draw.text((px, py), tick_text, fill=(100, 90, 82, int(255 * alpha)), font=font_tick)

    # Mood pill
    if current_mood:
        mood_y = py + th + pad_y + 18
        bbox = draw.textbbox((0, 0), current_mood, font=font_mood)
        mw, mh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        mx = (CANVAS_W - mw) // 2
        mpx, mpy = 36, 14
        draw.rounded_rectangle(
            [mx - mpx, mood_y - mpy, mx + mw + mpx, mood_y + mh + mpy],
            radius=26, fill=PILL_BG + (int(190 * mood_alpha),))
        draw.text((mx + 2, mood_y + 2), current_mood,
                  fill=(74, 67, 64, int(60 * mood_alpha)), font=font_mood)
        draw.text((mx, mood_y), current_mood,
                  fill=(190, 140, 145, int(255 * mood_alpha)), font=font_mood)

    # Narration — lower third of square
    narr_y_base = 860
    visible_lines = []
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
            wrapped = wrap_text(narration_lines[i], font_narr, MAX_TEXT_W, draw)
            visible_lines.append((wrapped, a))

    if visible_lines:
        total_lines = sum(len(wl) for wl, _ in visible_lines)
        line_h = 48
        panel_h = total_lines * line_h + 30
        max_a = max(a for _, a in visible_lines)
        draw.rounded_rectangle(
            [50, narr_y_base - 18, CANVAS_W - 50, narr_y_base + panel_h],
            radius=20, fill=PILL_BG + (int(180 * max_a),))
        y_cursor = narr_y_base
        for wrapped, a in visible_lines:
            for line in wrapped:
                bbox = draw.textbbox((0, 0), line, font=font_narr)
                lw = bbox[2] - bbox[0]
                lx = (CANVAS_W - lw) // 2
                draw.text((lx + 1, y_cursor + 1), line,
                          fill=(74, 67, 64, int(80 * a)), font=font_narr)
                draw.text((lx, y_cursor), line,
                          fill=(58, 52, 48, int(240 * a)), font=font_narr)
                y_cursor += line_h

    # Title card — positioned for square
    if t >= 28.0:
        a = ease_out(min(1.0, (t - 28.0) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((CANVAS_W - tw) // 2, 920), title,
                  fill=DUSTY_ROSE + (int(255 * a),), font=font_title)
        if t >= 28.3:
            sa = ease_out(min(1.0, (t - 28.3) / 0.6))
            sub = episode_config["title"].lower()
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, 976), sub,
                      fill=MUTED + (int(200 * sa),), font=font_sub)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ══════════════════════════════════════════════════════════════════════
# Audio: ambient pad + chimes + multi-line TTS
# ══════════════════════════════════════════════════════════════════════

MOOD_TONES = {
    "recalculating": (233.08, 0.006),
    "liminal":       (293.66, 0.008),
    "threshold":     (329.63, 0.010),
    "humbled":       (233.08, 0.007),
    "curious":       (349.23, 0.008),
    "wistful":       (277.18, 0.006),
    "resolute":      (329.63, 0.009),
    "frustrated":    (233.08, 0.009),
}

def generate_ambient_pad(duration, moods):
    """Generate stereo ambient pad with per-act mood color tones."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

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

    # Per-act mood tones with crossfade
    for i, mood_name in enumerate(moods):
        freq, amp = MOOD_TONES.get(mood_name, (293.66, 0.007))
        act_start = i * 10.0
        act_end = (i + 1) * 10.0
        env = np.clip((t - act_start) / 2.0, 0, 1) * np.clip((act_end - t) / 2.0, 0, 1)
        pad += np.sin(2 * np.pi * freq * t) * amp * env

    # Chimes
    chimes = [
        (0.1, 880), (3.0, 1108.73), (5.5, 880), (8.0, 1318.51),
        (10.5, 880), (13.5, 1108.73), (16.0, 1318.51), (19.0, 880),
        (22.0, 1108.73), (25.5, 880), (28.0, 1318.51),
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env

    # Master envelope
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)

    # Filter
    sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22

    # Make stereo with binaural panning
    pan = 0.5 + 0.3 * np.sin(2 * np.pi * 0.05 * t)
    left = pad * (1 - pan)
    right = pad * pan
    # Binaural beat on right channel
    right += np.sin(2 * np.pi * 112.0 * t) * 0.015 * np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)

    return np.column_stack([left, right])


def generate_tts(text, output_path):
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
        json={"text": text, "model_id": ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.55, "similarity_boost": 0.72, "style": 0.15}},
        headers={"xi-api-key": ELEVENLABS_API_KEY,
                 "Content-Type": "application/json", "Accept": "audio/mpeg"},
        timeout=120)
    resp.raise_for_status()
    Path(output_path).write_bytes(resp.content)
    return output_path

import requests

def build_audio(episode_config, ep_num):
    """Build multi-line narration audio with ambient pad."""
    try:
        from moviepy import AudioFileClip, CompositeAudioClip
    except ImportError:
        from moviepy.editor import AudioFileClip, CompositeAudioClip

    print("[Audio] Building scored soundtrack...")
    moods = [act["mood"] for act in episode_config["acts"]]
    pad_stereo = generate_ambient_pad(DURATION, moods)

    # Write pad
    pad_path = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_pad.wav")
    pad_samples = (np.clip(pad_stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(pad_path, 'w') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(pad_samples.tobytes())
    print(f"  Pad: {pad_path}")

    # Collect all narration lines across acts
    all_narration = []
    for act in episode_config["acts"]:
        for line in act.get("narration", []):
            all_narration.append(line)

    # Generate TTS per line
    tts_info = []
    for i, line in enumerate(all_narration):
        p = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_tts_{i}.mp3")
        print(f'  TTS: "{line["text"][:70]}"')
        generate_tts(line["text"], p)
        clip = AudioFileClip(str(p))
        dur = clip.duration
        clip.close()
        tts_info.append({"path": p, "desired_start": line["start"], "duration": dur})
        print(f"    -> {dur:.2f}s")

    # Overlap prevention
    GAP = 0.3
    actual_starts = []
    earliest = 0.0
    for i, info in enumerate(tts_info):
        start = max(info["desired_start"], earliest)
        latest = DURATION - info["duration"] - 0.2
        if start > latest:
            start = max(earliest, latest)
            print(f"  Pulled back line {i} to {start:.1f}s")
        actual_starts.append(start)
        earliest = start + info["duration"] + GAP
        if start != info["desired_start"]:
            print(f"  Adjusted line {i} from {info['desired_start']:.1f}s to {start:.1f}s")

    narration_times = [(actual_starts[i], actual_starts[i] + tts_info[i]["duration"])
                       for i in range(len(tts_info))]
    narration_lines = [n["text"] for n in all_narration]
    print(f"  Timing: {[(f'{s:.1f}-{e:.1f}') for s, e in narration_times]}")

    # Mix
    pad_audio = AudioFileClip(str(pad_path))
    narrs = []
    for i, info in enumerate(tts_info):
        c = AudioFileClip(str(info["path"]))
        try:
            c = c.with_start(actual_starts[i])
        except AttributeError:
            c = c.set_start(actual_starts[i])
        if c.end and c.end > DURATION:
            try:
                c = c.subclipped(0, DURATION - actual_starts[i])
            except AttributeError:
                c = c.subclip(0, DURATION - actual_starts[i])
        narrs.append(c)

    try:
        final = CompositeAudioClip([pad_audio] + narrs).subclipped(0, DURATION)
    except AttributeError:
        final = CompositeAudioClip([pad_audio] + narrs).subclip(0, DURATION)
    audio_path = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_audio.mp3")
    final.write_audiofile(str(audio_path), fps=SR, codec="libmp3lame")
    print(f"  Audio: {audio_path}")

    return audio_path, narration_lines, narration_times


# ══════════════════════════════════════════════════════════════════════
# Frame compositing
# ══════════════════════════════════════════════════════════════════════

def _apply_zoom(canvas, z):
    w, h = canvas.size
    nw, nh = int(w * z), int(h * z)
    canvas = canvas.resize((nw, nh), Image.LANCZOS)
    cx, cy = (nw - w) // 2, (nh - h) // 2
    return canvas.crop((cx, cy, cx + w, cy + h))


def composite_frames(all_frames, episode_config, narration_lines, narration_times, use_upscale=False):
    """Composite 900 frames with effects, particles, text overlays."""
    assert len(all_frames) == TOTAL_FRAMES

    if use_upscale:
        print(f"[Upscale] Upscaling {TOTAL_FRAMES} frames...")
        for i in range(len(all_frames)):
            all_frames[i] = upscale_frame(all_frames[i])
            if (i + 1) % 90 == 0:
                print(f"  {i + 1}/{TOTAL_FRAMES}")
        free_gpu()

    print("[Composite] Building final frames...")
    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)
    output_frames = []

    for i in range(TOTAL_FRAMES):
        t = i / FPS
        canvas = make_square_canvas(all_frames[i])

        # Fade in
        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (55, 48, 42))
            canvas = Image.blend(bg, canvas, fade)

        # Act transitions
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.4:
                dim = 0.6 + 0.4 * (abs(t - act_t) / 0.4)
                canvas = Image.blend(
                    Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, dim)

        # End fade
        if t > 29.0:
            canvas = Image.blend(
                Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK),
                canvas, ease_out((DURATION - t) / 1.0))

        canvas = draw_particles(canvas, particles, t)
        canvas = film_grain(canvas, intensity=5.0)
        canvas = add_text_overlays(canvas, t, episode_config, narration_lines, narration_times)
        output_frames.append(np.array(canvas))

        if (i + 1) % 150 == 0:
            print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    print(f"  All {TOTAL_FRAMES} frames done")
    return output_frames


# ══════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════

def produce_episode(config_path, no_upscale=False, dry_run=False, skip_effects=False):
    t_start = time.time()

    with open(config_path) as f:
        config = json.load(f)

    ep_num = config["number"]
    title = config["title"]
    acts = config["acts"]

    print("=" * 64)
    print(f"  Kombucha Episode {ep_num}: {title}")
    print(f"  30s | 1080x1080 | 30fps | 900 frames")
    print(f"  Ticks: {', '.join(str(a['tick']) for a in acts)}")
    print(f"  CosyMotes: {'yes' if not skip_effects else 'skip'}")
    print(f"  Upscale: {'yes' if not no_upscale else 'skip'}")
    print("=" * 64)
    print()

    # ── 1. Extract frames per act ─────────────────────────────────────
    print("[1] Extracting frames...")
    all_frames = []
    for i, act in enumerate(acts):
        print(f"  Act {i+1}: tick {act['tick']}, motion {act['motion_range']}")
        frames = extract_frames_for_act(act)
        all_frames.extend(frames)
        print(f"    {len(frames)} frames extracted")
    print(f"  Total: {len(all_frames)} frames")
    print()

    if dry_run:
        print("-- DRY RUN -- stopping here")
        return None

    # ── 2. CosyMotes effects (per act for memory efficiency) ─────────
    if not skip_effects:
        print("[2] Applying CosyMotes effects...")
        effected = []
        for i in range(3):
            start = i * ACT_FRAMES
            end = start + ACT_FRAMES
            print(f"  Act {i+1} ({ACT_FRAMES} frames)...")
            act_effected = apply_cosymotes(all_frames[start:end])
            effected.extend(act_effected)
        all_frames = effected
        print()
    else:
        print("[2] Skipping CosyMotes")
        print()

    # ── 3. Audio ──────────────────────────────────────────────────────
    print("[3] Building audio...")
    audio_path, narration_lines, narration_times = build_audio(config, ep_num)
    print()

    # ── 4. Composite + encode ─────────────────────────────────────────
    print("[4] Compositing...")
    output_frames = composite_frames(
        all_frames, config, narration_lines, narration_times,
        use_upscale=not no_upscale)
    print()

    # ── 5. Encode ─────────────────────────────────────────────────────
    print("[5] Encoding...")
    try:
        from moviepy import ImageSequenceClip, AudioFileClip
    except ImportError:
        from moviepy.editor import ImageSequenceClip, AudioFileClip
    video = ImageSequenceClip(list(output_frames), fps=FPS)
    try:
        video = video.with_audio(AudioFileClip(str(audio_path)))
    except AttributeError:
        video = video.set_audio(AudioFileClip(str(audio_path)))

    raw_path = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_raw.mp4")
    output_path = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_{title.lower().replace(' ', '_')}.mp4")

    video.write_videofile(str(raw_path), fps=FPS, codec="libx264",
                          audio_codec="aac", preset="medium", bitrate="3000k")

    print("  Re-encoding for platform...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-b:v", "3M", "-maxrate", "4M", "-bufsize", "6M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", str(output_path),
    ], check=True)

    if os.path.exists(raw_path):
        os.unlink(raw_path)

    # Loudnorm
    bsky_path = os.path.join(OUTPUT_DIR, f"kombucha_ep{ep_num:02d}_bsky.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(output_path),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-c:a", "aac", "-b:a", "192k",
        str(bsky_path),
    ], check=True)

    elapsed = time.time() - t_start
    size_mb = os.path.getsize(output_path) / (1024 * 1024)

    print()
    print("=" * 64)
    print(f"  DONE: {output_path}")
    print(f"  Bluesky: {bsky_path}")
    print(f"  Size: {size_mb:.1f}MB | Time: {elapsed:.0f}s")
    print(f"  Episode {ep_num}: {title}")
    print("=" * 64)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kombucha full-episode pipeline")
    parser.add_argument("config", help="Episode JSON config file")
    parser.add_argument("--no-upscale", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-effects", action="store_true", help="Skip CosyMotes (faster dev)")
    args = parser.parse_args()

    produce_episode(args.config, no_upscale=args.no_upscale,
                    dry_run=args.dry_run, skip_effects=args.skip_effects)
