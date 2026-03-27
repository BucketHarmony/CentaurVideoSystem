#!/usr/bin/env python3
"""
cc_flora -- Episode 07: Ping-Pong (30-second cut, FAST mode)

ACT 1 (0-10s)  tick_0036: The Bold Drive. 12cm, broke 3m, doorway 20cm ahead.
ACT 2 (10-20s) tick_0037: The Gap. Squeezing between Pelican case and barrel. Hits the case.
ACT 3 (20-30s) tick_0037: Bounce. Reverses, hits barrel. Fails. Learns.

Usage:
    python cc_flora_ep07_ping_pong.py              # fast (~3 min)
    python cc_flora_ep07_ping_pong.py --upscale    # premium (~20 min)
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
FRAMES_DIR = OUTPUT_DIR / "cc_flora_ep07_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
DURATION = 30.0
TOTAL_FRAMES = int(DURATION * FPS)

LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)
PILL_BG = (245, 238, 228)

# Font paths -- set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

NARRATION = [
    {"text": "Twelve centimeters in one drive. I broke three meters.",                  "start": 2.5},
    {"text": "The doorway is right there. Between a Pelican case and a barrel.",        "start": 6.5},
    {"text": "I went left. I hit the case.",                                            "start": 12.5},
    {"text": "I reversed. I went right. I hit the barrel.",                             "start": 16.5},
    {"text": "The gap is fifteen centimeters. I am forty centimeters wide.",             "start": 22.0},
    {"text": "The bathroom does not move. I am learning that I do.",                    "start": 26.0},
]

MOODS = [
    {"mood": "resolute",   "start": 0.0,  "end": 10.0},
    {"mood": "frustrated", "start": 10.0, "end": 20.0},
    {"mood": "humbled",    "start": 20.0, "end": 30.0},
]

# Motion map:
# tick_0036 (100s): bursts t=54-56 (d=33), t=91-94 (d=48-75)
# tick_0037 (199.8s): active t=61-180, spikes t=94(58), t=139(57), t=174(51), t=179(59)


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
# Color Grading + Effects (v6)
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
    arr = 128 + (arr - 128) * 0.92
    arr[:, :, 0] *= 1.03; arr[:, :, 1] *= 1.01; arr[:, :, 2] *= 0.91
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.75)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    return img

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
    warm_bg = np.array((175, 162, 148), dtype=np.float32)
    bg_arr = np.array(bg, dtype=np.float32) * 0.60 + warm_bg * 0.40
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
# Text Overlays (v6)
# ═══════════════════════════════════════════════════════════════════════════

def ease_out(x):
    return 1 - (1 - x) ** 3

MAX_TEXT_W = CANVAS_W - 140

def wrap_text(text, font, max_w, draw):
    words = text.split()
    lines = []
    current = ""
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

def add_text_overlays(img, t, narration_times):
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_tick = ImageFont.truetype(FONT_SERIF, 40)
        font_mood = ImageFont.truetype(FONT_SERIF_ITALIC, 60)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 36)
        font_title = ImageFont.truetype(FONT_SERIF, 48)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 26)
        font_bat = ImageFont.truetype(FONT_SERIF, 30)
    except OSError:
        font_tick = font_mood = font_narr = font_title = font_sub = font_bat = ImageFont.load_default()

    if t < 10:
        tick_text = "tick 0036"
    elif t < 20:
        tick_text = "tick 0037"
    else:
        tick_text = "tick 0037"

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
        mood_pad_x, mood_pad_y = 36, 14
        draw.rounded_rectangle(
            [mx - mood_pad_x, mood_y - mood_pad_y, mx + mw + mood_pad_x, mood_y + mh + mood_pad_y],
            radius=26, fill=PILL_BG + (int(190 * mood_alpha),))
        draw.text((mx + 2, mood_y + 2), current_mood,
                  fill=(74, 67, 64, int(60 * mood_alpha)), font=font_mood)
        draw.text((mx, mood_y), current_mood,
                  fill=(190, 140, 145, int(255 * mood_alpha)), font=font_mood)

    # Battery
    bat_entries = [(1.0, 3.0, "96.9%")]
    for bat_start, bat_end, bat_text in bat_entries:
        if bat_start <= t <= bat_end + 1.0:
            if t < bat_start + 0.5:
                ba = ease_out((t - bat_start) / 0.5)
            elif t < bat_end:
                ba = 1.0
            else:
                ba = 1.0 - ease_out((t - bat_end) / 1.0)
            ba = max(0, min(1, ba))
            draw.text((80, CANVAS_H - 120), bat_text,
                      fill=(170, 155, 145, int(200 * ba)), font=font_bat)

    # Narration
    narr_y_base = 1320
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
            wrapped = wrap_text(NARRATION[i]["text"], font_narr, MAX_TEXT_W, draw)
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

    # Title card
    if t >= 28.0:
        a = ease_out(min(1.0, (t - 28.0) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((CANVAS_W - tw) // 2, 1560), title,
                  fill=DUSTY_ROSE + (int(255 * a),), font=font_title)
        if t >= 28.3:
            sa = ease_out(min(1.0, (t - 28.3) / 0.6))
            sub = "ping-pong"
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, 1616), sub,
                      fill=MUTED + (int(200 * sa),), font=font_sub)

    return Image.alpha_composite(img, overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio
# ═══════════════════════════════════════════════════════════════════════════

def ease_out_np(x):
    return 1 - (1 - np.clip(x, 0, 1)) ** 3

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

    # Act 2-3: frustration — minor second dissonance builds
    frustration = np.clip((t - 10) / 5.0, 0, 1) * np.clip((25.0 - t) / 5.0, 0, 1)
    pad += np.sin(2 * np.pi * 233.08 * t) * 0.010 * frustration  # Bb3

    # Act 3 resolution: humbled acceptance — E4 returns
    act3 = np.clip((t - 24) / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 329.63 * t) * 0.012 * act3

    # Impact sounds at collisions
    # t=13.0: hits Pelican case (thud)
    # t=17.5: hits barrel (thud)
    for impact_t in [13.0, 17.5]:
        imp_env = np.where(
            (t >= impact_t) & (t < impact_t + 0.15),
            np.exp(-(t - impact_t) * 25) * 0.08,
            0.0
        )
        pad += np.random.RandomState(int(impact_t * 100)).randn(len(t)) * imp_env
        # Low thud
        thud_env = np.where(
            (t >= impact_t) & (t < impact_t + 0.3),
            np.exp(-(t - impact_t) * 10) * 0.04,
            0.0
        )
        pad += np.sin(2 * np.pi * 55 * t) * thud_env  # Low A1 thud

    # Chimes
    chimes = [
        (0.1, 880), (2.5, 1108.73), (5.0, 880), (8.0, 1318.51),
        (10.5, 880), (15.0, 1108.73), (19.0, 880),
        (22.0, 1108.73), (25.0, 880), (28.0, 1318.51),
    ]
    for ct, cf in chimes:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.022 * env

    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((duration - t) / 2.5, 0, 1)

    sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22

    out = OUTPUT_DIR / "cc_flora_ep07_pad.wav"
    with wave.open(str(out), 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((pad * 32767).astype(np.int16).tobytes())
    print(f"  Ambient pad: {out}")
    return out

def generate_tts(text, output_path):
    clean = text
    if clean.startswith("["):
        bracket_end = clean.find("]")
        if bracket_end != -1:
            clean = clean[bracket_end + 1:].strip()
    print(f'  TTS: "{clean[:70]}"')
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
        json={"text": clean, "model_id": ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.55, "similarity_boost": 0.72, "style": 0.15}},
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path

def build_audio():
    from moviepy import AudioFileClip, CompositeAudioClip
    print("Building audio (with overlap prevention)...")
    pad_path = generate_ambient_pad(DURATION)

    tts_info = []
    for i, line in enumerate(NARRATION):
        p = OUTPUT_DIR / f"cc_flora_ep07_tts_{i}.mp3"
        generate_tts(line["text"], p)
        clip = AudioFileClip(str(p))
        dur = clip.duration
        clip.close()
        tts_info.append({"path": p, "desired_start": line["start"], "duration": dur})
        print(f"    -> {dur:.2f}s")

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

    pad_audio = AudioFileClip(str(pad_path))
    narrs = []
    for i, info in enumerate(tts_info):
        c = AudioFileClip(str(info["path"])).with_start(actual_starts[i])
        if c.end and c.end > DURATION:
            c = c.subclipped(0, DURATION - actual_starts[i])
        narrs.append(c)

    final = CompositeAudioClip([pad_audio] + narrs).subclipped(0, DURATION)
    audio_path = OUTPUT_DIR / "cc_flora_ep07_audio.mp3"
    final.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Audio: {audio_path}")
    return audio_path, narration_times


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence
# ═══════════════════════════════════════════════════════════════════════════

def sample_times(src_start, src_end, n):
    return [src_start + (src_end - src_start) * i / max(n - 1, 1) for i in range(n)]

def build_source_map():
    """900 frames from tick_0036 + tick_0037.

    ACT 1 (0-10s, 300f) - tick_0036: Bold drive
      0-3s    (90f):  Static opening (t=0-20)
      3-6s    (90f):  Pre-drive buildup (t=20-50)
      6-8.5s  (75f):  Drive motion (t=50-60, includes burst)
      8.5-10s (45f):  Post-drive, broke 3m (t=88-95, big burst)

    ACT 2 (10-20s, 300f) - tick_0037: Pelican case hit
      10-13s  (90f):  Approach (t=0-60)
      13-15s  (60f):  First collision — left into case (t=60-100, spike t=94)
      15-17.5s(75f):  Reverse attempt (t=100-130)
      17.5-20s(75f):  Right into barrel (t=130-145, spike t=139)

    ACT 3 (20-30s, 300f) - tick_0037: Aftermath, learning
      20-23s  (90f):  Post-collision assessment (t=145-170)
      23-26s  (90f):  Final attempts (t=170-185, spikes t=174,179)
      26-28.5s(75f):  Acceptance, holding position (t=185-195)
      28.5-30s(45f):  Final hold + title (t=195-199)
    """
    v36 = str(VIDEO_DIR / "tick_0036.mp4")
    v37 = str(VIDEO_DIR / "tick_0037.mp4")

    frames = []
    # ACT 1 (300 frames)
    frames += [(v36, t) for t in sample_times(0.0, 20.0, 90)]
    frames += [(v36, t) for t in sample_times(20.0, 50.0, 90)]
    frames += [(v36, t) for t in sample_times(50.0, 60.0, 75)]
    frames += [(v36, t) for t in sample_times(88.0, 95.0, 45)]
    # ACT 2 (300 frames)
    frames += [(v37, t) for t in sample_times(0.0, 60.0, 90)]
    frames += [(v37, t) for t in sample_times(60.0, 100.0, 60)]
    frames += [(v37, t) for t in sample_times(100.0, 130.0, 75)]
    frames += [(v37, t) for t in sample_times(130.0, 145.0, 75)]
    # ACT 3 (300 frames)
    frames += [(v37, t) for t in sample_times(145.0, 170.0, 90)]
    frames += [(v37, t) for t in sample_times(170.0, 185.0, 90)]
    frames += [(v37, t) for t in sample_times(185.0, 195.0, 75)]
    frames += [(v37, t) for t in sample_times(195.0, 199.0, 45)]

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

    # Impact shake frames
    IMPACT1_FRAME = int(13.0 * FPS)  # hits case
    IMPACT2_FRAME = int(17.5 * FPS)  # hits barrel

    for i in range(TOTAL_FRAMES):
        t = i / FPS
        canvas = make_vertical_canvas(raw_frames[i])

        # Fade in
        if t < 1.0:
            fade = 0.4 + 0.6 * ease_out(t / 1.0)
            bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (55, 48, 42))
            canvas = Image.blend(bg, canvas, fade)

        # Act transitions
        for act_t in [10.0, 20.0]:
            if abs(t - act_t) < 0.4:
                dim = 0.6 + 0.4 * (abs(t - act_t) / 0.4)
                canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), LINEN), canvas, dim)

        # Impact shakes (5 frames of jitter at each collision)
        for impact_frame in [IMPACT1_FRAME, IMPACT2_FRAME]:
            if impact_frame <= i <= impact_frame + 5:
                decay = 1.0 - (i - impact_frame) / 5.0
                jx = int(random.uniform(-5, 5) * decay)
                jy = int(random.uniform(-4, 4) * decay)
                arr = np.array(canvas)
                arr = np.roll(arr, jy, axis=0)
                arr = np.roll(arr, jx, axis=1)
                canvas = Image.fromarray(arr)

        # Act 1: Ken Burns push-in (approaching the gap)
        if 5.0 <= t <= 10.0:
            zoom_pct = (t - 5.0) / 5.0
            canvas = _apply_zoom(canvas, 1.0 + 0.015 * ease_out(zoom_pct))

        # End fade
        if t > 29.0:
            canvas = Image.blend(Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK),
                                 canvas, ease_out((DURATION - t) / 1.0))

        canvas = draw_particles(canvas, particles, t)
        canvas = film_grain(canvas, intensity=5.0)
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
    print(f"  cc_flora -- Episode 07: Ping-Pong [{mode}]")
    print(f"  30s | 1080x1920 | 30fps | 900 frames")
    print(f"  PING-PONG: case, barrel, case, barrel, bathroom")
    print("=" * 64)
    print()

    audio_path, narration_times = build_audio()
    frames = build_frame_sequence(narration_times, use_upscale=args.upscale)

    print("\nAssembling video...")
    from moviepy import ImageSequenceClip, AudioFileClip
    video = ImageSequenceClip(list(frames), fps=FPS)
    video = video.with_audio(AudioFileClip(str(audio_path)))

    raw_path = OUTPUT_DIR / "cc_flora_ep07_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_ep07_ping_pong.mp4"
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
    print(f"  Episode 07: Ping-Pong. 30 seconds. Bouncing.")
    print("=" * 64)

if __name__ == "__main__":
    main()
