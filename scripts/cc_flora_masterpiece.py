#!/usr/bin/env python3
"""
cc_flora — Episode 01: First Light (Masterpiece Edit)

A small robot opens its eyes for the very first time.
10 seconds. 4x-UltraSharp GPU upscaling. Cottagecore.
Three-part narration. Ambient pad. Film grain. Bokeh dust.

"I have a body.
 The floor is warm beneath me.
 And the first thing I see... is toilet paper."
"""

import os

from dotenv import load_dotenv
load_dotenv(r"E:\AI\CVS\.env")

import math
import random
import struct
import tempfile
import wave
from pathlib import Path

import numpy as np
import requests
import scipy.signal
import torch
import torchaudio
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from moviepy import (
    ImageSequenceClip,
    AudioFileClip,
    CompositeAudioClip,
)

# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

PROJECT = Path("E:/AI/Kombucha")
VIDEO_PATH = PROJECT / "video" / "web" / "tick_0001.mp4"
UPSCALE_MODEL_PATH = Path("E:/AI/ComfyUI/models/upscale_models/4x-UltraSharp.pth")
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output")
FRAMES_DIR = OUTPUT_DIR / "cc_flora_masterpiece_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
DURATION = 10.0
TOTAL_FRAMES = int(DURATION * FPS)  # 300

# Cottagecore palette
ROSE = (232, 180, 184)
SAGE = (181, 197, 163)
CREAM = (250, 245, 239)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)

# Fonts
FONT_SERIF = "C:/Windows/Fonts/georgia.ttf"
FONT_SERIF_ITALIC = "C:/Windows/Fonts/georgiai.ttf"
FONT_SERIF_BOLD = "C:/Windows/Fonts/georgiab.ttf"

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = "wVOQaU8CfoRJqCWsxoLv"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Narration lines and their start times in the output
NARRATION = [
    {"text": "I have a body.",                                "start": 2.5},
    {"text": "The floor is warm beneath me.",                 "start": 4.8},
    {"text": "And the first thing I see... is toilet paper.", "start": 7.2},
]

# Mood (single act for 10s version)
MOODS = [
    {"mood": "curious", "start": 0.0, "end": 10.0},
]


# ═══════════════════════════════════════════════════════════════════════════
# GPU Upscaling (4x-UltraSharp via spandrel)
# ═══════════════════════════════════════════════════════════════════════════

_upscale_model = None

def load_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        return _upscale_model
    import spandrel
    print(f"Loading 4x-UltraSharp on CUDA...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL_PATH))
    model = model.to("cuda").eval()
    _upscale_model = model
    print(f"  Model loaded.")
    return model


def upscale_frame(pil_img: Image.Image) -> Image.Image:
    """Upscale a PIL image 4x using UltraSharp on GPU."""
    model = load_upscale_model()

    # PIL → tensor (B, C, H, W) float32 0-1
    arr = np.array(pil_img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to("cuda")

    with torch.no_grad():
        result = model(tensor)

    # tensor → PIL
    result = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
    result = (result * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(result)


# ═══════════════════════════════════════════════════════════════════════════
# Cottagecore Color Grading
# ═══════════════════════════════════════════════════════════════════════════

def cottagecore_grade(img: Image.Image) -> Image.Image:
    """Rich cottagecore grade: desaturate reds to dusty rose, lift shadows,
    compress highlights, add warmth. More nuanced than v1."""
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # ── Desaturate reds toward dusty rose/mauve ──
    red_mask = (r > 80) & (r > g * 1.2) & (r > b * 1.2)
    red_strength = np.clip((r - np.maximum(g, b)) / 120.0, 0, 1)
    red_strength *= red_mask.astype(np.float32)

    # Target: dusty rose with slight mauve lean
    arr[:, :, 0] = r * (1 - red_strength * 0.55) + 205 * red_strength * 0.55
    arr[:, :, 1] = g * (1 - red_strength * 0.45) + 170 * red_strength * 0.45
    arr[:, :, 2] = b * (1 - red_strength * 0.35) + 172 * red_strength * 0.35

    # ── Warm the wood tones (orange/brown → honey) ──
    orange_mask = (r > 100) & (g > 60) & (g < r * 0.85) & (b < g * 0.8)
    orange_str = np.clip((r - b) / 150.0, 0, 1) * orange_mask.astype(np.float32)
    arr[:, :, 0] = arr[:, :, 0] * (1 - orange_str * 0.15) + 220 * orange_str * 0.15
    arr[:, :, 1] = arr[:, :, 1] * (1 - orange_str * 0.1) + 195 * orange_str * 0.1

    # ── Lift shadows ──
    arr = arr + 20
    arr = np.clip(arr, 0, 255)

    # ── Compress dynamic range (soften) ──
    arr = 128 + (arr - 128) * 0.78

    # ── Warm shift ──
    arr[:, :, 0] *= 1.03
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.93

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    # ── Desaturation ──
    img = ImageEnhance.Color(img).enhance(0.70)

    # ── Brightness lift ──
    img = ImageEnhance.Brightness(img).enhance(1.08)

    return img


def soft_bloom(img: Image.Image, strength: float = 0.12) -> Image.Image:
    """Add soft bloom/glow to highlights — the cottagecore light-leak feel."""
    # Create a heavily blurred bright version
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))

    # Blend bloom onto original (screen-like)
    arr = np.array(img, dtype=np.float32)
    bloom_arr = np.array(bloom, dtype=np.float32)

    # Screen blend: 1 - (1-a)(1-b), but we use additive with strength control
    result = arr + bloom_arr * strength
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def creamy_vignette(img: Image.Image, strength: float = 0.28) -> Image.Image:
    """Soft vignette fading to cream, not black."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vignette = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
    vignette = vignette[:, :, np.newaxis] * strength
    cream = np.array(CREAM, dtype=np.float32)
    arr = arr * (1 - vignette) + cream * vignette
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def film_grain(img: Image.Image, intensity: float = 8.0) -> Image.Image:
    """Add subtle organic film grain."""
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    # Grain is stronger in midtones, weaker in shadows/highlights
    luminance = arr.mean(axis=2, keepdims=True) / 255.0
    midtone_mask = 1.0 - 2.0 * np.abs(luminance - 0.5)
    midtone_mask = np.clip(midtone_mask, 0.3, 1.0)
    arr += noise * midtone_mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ═══════════════════════════════════════════════════════════════════════════
# Vertical Canvas
# ═══════════════════════════════════════════════════════════════════════════

def make_vertical_canvas(frame: Image.Image, upscaled: bool = True) -> Image.Image:
    """Place a frame into vertical canvas with creamy blurred background."""
    frame = cottagecore_grade(frame)
    frame = soft_bloom(frame)

    fw, fh = frame.size

    # Scale to canvas width
    scale = CANVAS_W / fw
    new_w = CANVAS_W
    new_h = int(fh * scale)
    sharp = frame.resize((new_w, new_h), Image.LANCZOS)

    # Blurred creamy background
    bg_scale = CANVAS_H / fh
    bg_w = int(fw * bg_scale)
    bg = frame.resize((bg_w, CANVAS_H), Image.LANCZOS)
    if bg_w > CANVAS_W:
        crop_x = (bg_w - CANVAS_W) // 2
        bg = bg.crop((crop_x, 0, crop_x + CANVAS_W, CANVAS_H))
    else:
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=35))

    # Blend background toward linen (lighter, creamier)
    bg_arr = np.array(bg, dtype=np.float32)
    bg_arr = bg_arr * 0.30 + np.array(LINEN, dtype=np.float32) * 0.70
    bg = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))

    # Paste sharp video (centered, slightly above middle)
    canvas = bg.copy()
    y_offset = (CANVAS_H - new_h) // 2 - 80
    canvas.paste(sharp, (0, max(0, y_offset)))

    canvas = creamy_vignette(canvas)
    return canvas


# ═══════════════════════════════════════════════════════════════════════════
# Particle System (bokeh dust motes)
# ═══════════════════════════════════════════════════════════════════════════

def generate_particles(w, h, count=50):
    """Generate bokeh-style floating dust particles."""
    particles = []
    for _ in range(count):
        particles.append({
            "x": random.uniform(0, w),
            "y": random.uniform(0, h),
            "r": random.uniform(2.0, 6.0),       # larger = more bokeh
            "dx": random.uniform(-0.12, 0.12),
            "dy": random.uniform(-0.25, -0.04),   # float upward
            "alpha": random.uniform(0.08, 0.35),
            "phase": random.uniform(0, math.tau),
            "freq": random.uniform(0.3, 1.5),
            "warmth": random.choice([
                (255, 252, 245),   # warm white
                (255, 245, 230),   # cream
                (250, 240, 220),   # linen
                (255, 230, 215),   # peach
            ]),
        })
    return particles


def draw_particles(img: Image.Image, particles: list, t: float) -> Image.Image:
    """Draw bokeh dust motes with soft edges."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for p in particles:
        x = (p["x"] + p["dx"] * t * 60) % img.size[0]
        y = (p["y"] + p["dy"] * t * 60) % img.size[1]
        alpha = p["alpha"] * (0.6 + 0.4 * math.sin(p["phase"] + t * p["freq"] * math.tau))
        alpha = max(0, alpha)

        r = p["r"]
        color = p["warmth"] + (int(alpha * 255),)

        # Soft bokeh: draw concentric circles with decreasing alpha
        for ring in range(3):
            ring_r = r * (1 + ring * 0.5)
            ring_alpha = int(alpha * 255 * (1 - ring * 0.35))
            ring_color = p["warmth"] + (max(0, ring_alpha),)
            draw.ellipse([x - ring_r, y - ring_r, x + ring_r, y + ring_r], fill=ring_color)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Text Overlays
# ═══════════════════════════════════════════════════════════════════════════

def add_text_overlays(img: Image.Image, t: float) -> Image.Image:
    """Add all text overlays with timing and fades."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_tick = ImageFont.truetype(FONT_SERIF, 36)
        font_mood = ImageFont.truetype(FONT_SERIF_ITALIC, 56)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 36)
        font_title = ImageFont.truetype(FONT_SERIF, 48)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 24)
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = ImageFont.load_default()

    # ── Tick number + Mood (top of frame, large) ──
    if t >= 0.0:
        tick_text = "tick 0001"

        # Get current mood
        current_mood = ""
        for m in MOODS:
            if m["start"] <= t < m["end"]:
                current_mood = m["mood"]
                break

        if t < 0.5:
            alpha = ease_out(t / 0.5)
        elif t > 8.5:
            alpha = ease_out(max(0, (9.5 - t)))
        else:
            alpha = 1.0
        alpha = max(0, min(1, alpha))

        # Tick number (large pill)
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

        # Mood (large, below tick pill)
        if current_mood:
            mood_y = py + th + pad_y + 20
            bbox = draw.textbbox((0, 0), current_mood, font=font_mood)
            mw = bbox[2] - bbox[0]
            mx = (CANVAS_W - mw) // 2
            draw.text((mx + 2, mood_y + 2), current_mood,
                      fill=(74, 67, 64, int(40 * alpha)), font=font_mood)
            draw.text((mx, mood_y), current_mood,
                      fill=DUSTY_ROSE + (int(220 * alpha),), font=font_mood)

    # ── Narration lines ──
    narr_y_base = 1350
    for i, line in enumerate(NARRATION):
        line_start = line["start"]
        if t < line_start:
            continue

        fade_in = ease_out(min(1.0, (t - line_start) / 0.6))
        # Lines stack
        ly = narr_y_base + i * 48
        text = line["text"]
        bbox = draw.textbbox((0, 0), text, font=font_narr)
        tw = bbox[2] - bbox[0]
        lx = (CANVAS_W - tw) // 2

        # Backing panel (only draw once for all visible lines)
        if i == 0 and fade_in > 0:
            # Count how many lines are visible
            visible = sum(1 for l in NARRATION if t >= l["start"])
            panel_h = 40 + visible * 48
            panel_alpha = int(100 * fade_in)
            draw.rounded_rectangle(
                [60, narr_y_base - 18, CANVAS_W - 60, narr_y_base + panel_h],
                radius=18, fill=(250, 245, 239, panel_alpha)
            )

        # Shadow
        draw.text((lx + 1, ly + 1), text,
                  fill=(74, 67, 64, int(50 * fade_in)), font=font_narr)
        # Text
        draw.text((lx, ly), text,
                  fill=INK + (int(230 * fade_in),), font=font_narr)

    # ── Title card: "kombucha" / "tick one" (t=8.5s) ──
    if t >= 8.5:
        alpha = ease_out(min(1.0, (t - 8.5) / 0.8))

        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        tx = (CANVAS_W - tw) // 2
        ty = 1580
        draw.text((tx, ty), title, fill=DUSTY_ROSE + (int(255 * alpha),), font=font_title)

        sub = "tick one"
        bbox = draw.textbbox((0, 0), sub, font=font_sub)
        sw = bbox[2] - bbox[0]
        sx = (CANVAS_W - sw) // 2
        sy = ty + 56
        # Delayed slightly
        sub_alpha = ease_out(min(1.0, (t - 8.8) / 0.6)) if t >= 8.8 else 0
        draw.text((sx, sy), sub, fill=MUTED + (int(200 * sub_alpha),), font=font_sub)

    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


def ease_out(x):
    """Cubic ease-out for smooth fades."""
    return 1 - (1 - x) ** 3


# ═══════════════════════════════════════════════════════════════════════════
# Audio: Ambient Pad + TTS
# ═══════════════════════════════════════════════════════════════════════════

def generate_ambient_pad(duration: float, sample_rate: int = 44100) -> Path:
    """Generate a soft ambient pad using layered sine waves with filtering.
    Warm, cottagecore, like a music box dissolving into air."""
    t = np.linspace(0, duration, int(duration * sample_rate), dtype=np.float64)

    # Base drone: very low, warm
    pad = np.sin(2 * np.pi * 110 * t) * 0.06        # A2
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.04    # E3
    pad += np.sin(2 * np.pi * 220 * t) * 0.03       # A3

    # Shimmer: high harmonics with slow LFO
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.22 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.012 * lfo1    # A4
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.008 * lfo2  # C#5
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.006 * lfo1  # E5

    # Music box notes: sparse chime hits
    chime_times = [0.5, 2.0, 4.0, 6.5, 8.0]
    chime_freqs = [880, 1108.73, 880, 1318.51, 880]  # A5, C#6, A5, E6, A5
    for ct, cf in zip(chime_times, chime_freqs):
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.5) * env_t * 8, 0)
        env = np.clip(env, 0, 1)
        pad += np.sin(2 * np.pi * cf * t) * 0.025 * env

    # Fade in/out
    fade_in = np.clip(t / 2.0, 0, 1)
    fade_out = np.clip((duration - t) / 2.0, 0, 1)
    pad *= fade_in * fade_out

    # Low-pass filter for warmth
    sos = scipy.signal.butter(4, 3000, 'low', fs=sample_rate, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)

    # Normalize
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.25

    # Save as WAV
    out_path = OUTPUT_DIR / "cc_flora_ambient_pad.wav"
    pad_int16 = (pad * 32767).astype(np.int16)
    with wave.open(str(out_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pad_int16.tobytes())

    print(f"  Ambient pad: {out_path} ({duration:.1f}s)")
    return out_path


def generate_tts(text: str, output_path: Path) -> Path:
    """Generate TTS via ElevenLabs."""
    print(f"  TTS: \"{text}\"")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.65,
            "similarity_boost": 0.72,
            "style": 0.1,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


def build_audio() -> Path:
    """Build the full audio track: ambient pad + three narration clips."""
    print("Building audio...")

    # Generate ambient pad
    pad_path = generate_ambient_pad(DURATION)

    # Generate TTS for each narration line
    tts_clips = []
    for i, line in enumerate(NARRATION):
        tts_path = OUTPUT_DIR / f"cc_flora_tts_{i}.mp3"
        generate_tts(line["text"], tts_path)
        tts_clips.append((tts_path, line["start"]))

    # Compose: pad + narration clips at their start times
    pad_audio = AudioFileClip(str(pad_path))

    narr_audios = []
    for tts_path, start_t in tts_clips:
        clip = AudioFileClip(str(tts_path)).with_start(start_t)
        # Ensure it doesn't run past video end
        if clip.end and clip.end > DURATION:
            clip = clip.subclipped(0, DURATION - start_t)
        narr_audios.append(clip)

    # Mix all audio
    final_audio = CompositeAudioClip([pad_audio] + narr_audios)
    final_audio = final_audio.subclipped(0, DURATION)

    audio_path = OUTPUT_DIR / "cc_flora_masterpiece_audio.mp3"
    final_audio.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Final audio: {audio_path}")
    return audio_path


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence Builder
# ═══════════════════════════════════════════════════════════════════════════

def build_frame_sequence():
    """Build 300 frames from real video, 4x upscaled, cottagecore graded.

    Source video motion map:
      Pan 1 (center→left):  t=25.0–27.0s
      Pan 2 (left→right):   t=49.0–51.0s
      Pan 3 (right→center): t=80.0–81.0s

    Output timeline (10s @ 30fps = 300 frames):
      0.0–1.5s   (f 0–44):    Fade from black, center hold (breathing)
      1.5–3.2s   (f 45–95):   Real pan left (slowed ~0.4x, dreamy)
      3.2–4.5s   (f 96–134):  Hold left, settle
      4.5–6.5s   (f 135–194): Real pan right (slowed ~0.35x)
      6.5–7.5s   (f 195–224): Real pan back to center (slowed ~0.4x)
      7.5–10.0s  (f 225–299): Hold center, gentle zoom, title
    """
    from moviepy import VideoFileClip

    print("Loading source video...")
    clip = VideoFileClip(str(VIDEO_PATH))

    def sample_times(src_start, src_end, n):
        return [src_start + (src_end - src_start) * i / max(n - 1, 1)
                for i in range(n)]

    source_times = []
    # Beat 1: fade in on static center (45 frames)
    source_times += sample_times(21.0, 24.8, 45)
    # Beat 2: real pan left (51 frames from 2s of pan = 0.4x)
    source_times += sample_times(25.0, 27.0, 51)
    # Beat 3: hold left view (39 frames)
    source_times += sample_times(28.0, 32.0, 39)
    # Beat 4: real pan right (60 frames from 2s = 0.33x, extra dreamy)
    source_times += sample_times(49.0, 51.0, 60)
    # Beat 5: real pan back to center (30 frames from 1.2s)
    source_times += sample_times(79.8, 81.0, 30)
    # Beat 6: hold center for narration + title (75 frames)
    source_times += sample_times(82.0, 87.0, 75)

    assert len(source_times) == TOTAL_FRAMES, f"Need {TOTAL_FRAMES}, got {len(source_times)}"

    # ── Extract raw frames ──
    print(f"Extracting {TOTAL_FRAMES} raw frames from source video...")
    raw_frames = []
    for i, src_t in enumerate(source_times):
        src_t = min(src_t, clip.duration - 0.05)
        frame_np = clip.get_frame(src_t)
        raw_frames.append(Image.fromarray(frame_np))
        if (i + 1) % 60 == 0:
            print(f"  Extracted {i + 1}/{TOTAL_FRAMES}")
    clip.close()

    # ── Upscale all frames on GPU ──
    print(f"Upscaling {TOTAL_FRAMES} frames with 4x-UltraSharp on GPU...")
    upscaled_frames = []
    for i, frame in enumerate(raw_frames):
        up = upscale_frame(frame)
        upscaled_frames.append(up)
        if (i + 1) % 30 == 0:
            print(f"  Upscaled {i + 1}/{TOTAL_FRAMES} ({up.size[0]}x{up.size[1]})")

    # Free GPU memory
    global _upscale_model
    del _upscale_model
    _upscale_model = None
    torch.cuda.empty_cache()

    # ── Process: grade + canvas + effects ──
    print("Compositing frames (grade + canvas + particles + grain + text)...")
    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)  # deterministic grain

    output_frames = []
    for i in range(TOTAL_FRAMES):
        t = i / FPS

        # Build vertical canvas from upscaled frame
        canvas = make_vertical_canvas(upscaled_frames[i])

        # Beat 1: fade from black
        if t < 1.5:
            fade = ease_out(t / 1.5)
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)
            canvas = Image.blend(black, canvas, fade)

        # Beat 6: gentle slow zoom
        if t > 7.5:
            zoom_t = (t - 7.5) / (DURATION - 7.5)
            zoom = 1.0 + 0.025 * ease_out(zoom_t)
            w, h = canvas.size
            nw, nh = int(w * zoom), int(h * zoom)
            canvas = canvas.resize((nw, nh), Image.LANCZOS)
            cx, cy = (nw - w) // 2, (nh - h) // 2
            canvas = canvas.crop((cx, cy, cx + w, cy + h))

        # Particles
        canvas = draw_particles(canvas, particles, t)

        # Film grain
        canvas = film_grain(canvas, intensity=6.0)

        # Text overlays
        canvas = add_text_overlays(canvas, t)

        # Save
        canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
        output_frames.append(np.array(canvas))

        if (i + 1) % 30 == 0:
            print(f"  Frame {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    print(f"  All {TOTAL_FRAMES} frames saved to {FRAMES_DIR}")
    return output_frames


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("  cc_flora — Episode 01: First Light (Masterpiece)")
    print("  10 seconds | 1080x1920 | 30fps | 4x-UltraSharp | RTX 4090")
    print("=" * 64)
    print()

    # Build audio first (TTS API calls)
    audio_path = build_audio()

    # Build video frames
    frames = build_frame_sequence()

    # Assemble final video
    print("\nAssembling final video...")
    video = ImageSequenceClip(list(frames), fps=FPS)
    audio = AudioFileClip(str(audio_path))
    video = video.with_audio(audio)

    raw_path = OUTPUT_DIR / "cc_flora_masterpiece_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_masterpiece.mp4"
    print(f"Exporting raw...")
    video.write_videofile(
        str(raw_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="slow",
        bitrate="3000k",
    )

    # Re-encode for Bluesky
    print("Re-encoding for Bluesky (yuv420p, faststart, main profile)...")
    import subprocess
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
    print(f"  Bluesky-optimized: yuv420p, 3Mbps, faststart")
    print("=" * 64)


if __name__ == "__main__":
    main()
