#!/usr/bin/env python3
"""
Episode 01 — First Light (Cottagecore Edit)

A small robot opens its eyes for the very first time.
5-second vertical TikTok. Soft pastels, warm, disarmed.

Source: tick_0001 — survey left, right, center.
Narration: "I have a body. And a room."
"""

import os

from dotenv import load_dotenv
load_dotenv()

import math
import random
import tempfile
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from moviepy import (
    VideoFileClip,
    ImageClip,
    ImageSequenceClip,
    CompositeVideoClip,
    ColorClip,
    concatenate_videoclips,
    AudioFileClip,
    vfx,
)

# === Paths ===
PROJECT = Path(os.getenv("KOMBUCHA_DIR", ""))
FRAMES_DIR = PROJECT / "media" / "raw"
VIDEO_DIR = PROJECT / "video" / "web"
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
OUTPUT_DIR.mkdir(exist_ok=True)

# Source
VIDEO_PATH = VIDEO_DIR / "tick_0001.mp4"
FRAME_PATHS = [
    FRAMES_DIR / "tick_0001_frame_01.jpg",  # center
    FRAMES_DIR / "tick_0001_frame_02.jpg",  # left pan
    FRAMES_DIR / "tick_0001_frame_03.jpg",  # right pan
]

# === Cottagecore Palette ===
ROSE = (232, 180, 184)
SAGE = (181, 197, 163)
CREAM = (250, 245, 239)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)

# Canvas
CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
DURATION = 5.0
TOTAL_FRAMES = int(DURATION * FPS)  # 150

# Fonts
# Font paths — set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

# ElevenLabs TTS
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"
NARRATION_TEXT = "I have a body. And a room."


def generate_tts(text: str, output_path: Path) -> Path:
    """Generate TTS audio via ElevenLabs API."""
    print(f"Generating TTS: \"{text}\"")
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
            "stability": 0.6,          # slightly more stable for soft delivery
            "similarity_boost": 0.7,
            "style": 0.15,             # gentle style
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    print(f"  TTS saved: {output_path} ({len(resp.content)} bytes)")
    return output_path


def cottagecore_grade(img: Image.Image) -> Image.Image:
    """Apply cottagecore color grading: desaturate reds to dusty rose,
    lift shadows, soften highlights, warm overall."""
    arr = np.array(img, dtype=np.float32)

    # Step 1: Desaturate reds toward dusty rose
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # Detect red-dominant pixels (the red walls)
    red_mask = (r > 100) & (r > g * 1.3) & (r > b * 1.3)
    red_strength = np.clip((r - np.maximum(g, b)) / 100.0, 0, 1)
    red_strength *= red_mask.astype(np.float32)

    # Shift reds toward dusty rose (desaturate + warm pink)
    target_r, target_g, target_b = 210, 175, 175
    arr[:, :, 0] = r * (1 - red_strength * 0.5) + target_r * red_strength * 0.5
    arr[:, :, 1] = g * (1 - red_strength * 0.4) + target_g * red_strength * 0.4
    arr[:, :, 2] = b * (1 - red_strength * 0.3) + target_b * red_strength * 0.3

    # Step 2: Lift shadows (raise blacks toward cream)
    shadow_lift = 25
    arr = arr + shadow_lift
    arr = np.clip(arr, 0, 255)

    # Step 3: Reduce contrast (compress dynamic range)
    midpoint = 128
    arr = midpoint + (arr - midpoint) * 0.82

    # Step 4: Warm shift (slight yellow/cream push)
    arr[:, :, 0] = arr[:, :, 0] * 1.03  # slight red warmth
    arr[:, :, 1] = arr[:, :, 1] * 1.01  # tiny green
    arr[:, :, 2] = arr[:, :, 2] * 0.95  # pull blue down

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    # Step 5: Slight desaturation overall
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(0.75)

    # Step 6: Slight brightness lift
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.06)

    return img


def creamy_vignette(img: Image.Image, strength: float = 0.3) -> Image.Image:
    """Apply a soft, creamy vignette (edges fade to warm cream, not black)."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32)

    # Create radial gradient
    Y, X = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    normalized = dist / max_dist

    # Smooth falloff starting from 0.5 radius
    vignette = np.clip((normalized - 0.4) / 0.6, 0, 1) ** 1.5
    vignette = vignette[:, :, np.newaxis] * strength

    # Blend toward cream color
    cream = np.array(CREAM, dtype=np.float32)
    arr = arr * (1 - vignette) + cream * vignette
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    return Image.fromarray(arr)


def generate_dust_motes(w: int, h: int, num_motes: int = 40) -> list:
    """Generate floating dust mote particles with random properties."""
    motes = []
    for _ in range(num_motes):
        motes.append({
            "x": random.uniform(0, w),
            "y": random.uniform(0, h),
            "size": random.uniform(1.5, 4.0),
            "speed_x": random.uniform(-0.15, 0.15),
            "speed_y": random.uniform(-0.3, -0.05),  # float upward
            "alpha_base": random.uniform(0.15, 0.5),
            "phase": random.uniform(0, math.pi * 2),
            "freq": random.uniform(0.5, 2.0),
        })
    return motes


def draw_dust_motes(img: Image.Image, motes: list, t: float) -> Image.Image:
    """Draw floating dust motes at time t."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for m in motes:
        x = (m["x"] + m["speed_x"] * t * 60) % img.size[0]
        y = (m["y"] + m["speed_y"] * t * 60) % img.size[1]

        # Gentle pulsing alpha
        alpha = m["alpha_base"] * (0.7 + 0.3 * math.sin(m["phase"] + t * m["freq"] * math.pi * 2))
        alpha_int = int(alpha * 255)

        # Warm white mote
        color = (255, 250, 240, alpha_int)
        r = m["size"]
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def make_vertical_canvas(frame: Image.Image, grade: bool = True) -> Image.Image:
    """Place a graded frame into a vertical canvas with blurred background."""
    if grade:
        frame = cottagecore_grade(frame)

    # Scale frame to canvas width
    fw, fh = frame.size
    scale = CANVAS_W / fw
    new_w = CANVAS_W
    new_h = int(fh * scale)
    sharp = frame.resize((new_w, new_h), Image.LANCZOS)

    # Blurred background: scale to fill canvas height, blur heavily
    bg_scale = CANVAS_H / fh
    bg_w = int(fw * bg_scale)
    bg = frame.resize((bg_w, CANVAS_H), Image.LANCZOS)
    # Center crop
    if bg_w > CANVAS_W:
        crop_x = (bg_w - CANVAS_W) // 2
        bg = bg.crop((crop_x, 0, crop_x + CANVAS_W, CANVAS_H))
    else:
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))

    # Lighten & desaturate the blurred background (cottagecore: creamy, not dark)
    bg_arr = np.array(bg, dtype=np.float32)
    bg_arr = bg_arr * 0.35 + np.array(LINEN, dtype=np.float32) * 0.65
    bg = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))

    # Paste sharp video centered vertically (shifted slightly up)
    canvas = bg.copy()
    y_offset = (CANVAS_H - new_h) // 2 - 60
    canvas.paste(sharp, (0, max(0, y_offset)))

    # Apply creamy vignette
    canvas = creamy_vignette(canvas, strength=0.25)

    return canvas


def add_text_overlays(img: Image.Image, t: float, duration: float) -> Image.Image:
    """Add cottagecore text overlays with timing."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── "tick 0001" pill (appears at t=0.8s, gentle fade) ──
    if t >= 0.8:
        pill_alpha = min(1.0, (t - 0.8) / 0.6)
        try:
            font_pill = ImageFont.truetype(FONT_SERIF, 22)
        except OSError:
            font_pill = ImageFont.load_default()

        pill_text = "tick 0001"
        bbox = draw.textbbox((0, 0), pill_text, font=font_pill)
        pw = bbox[2] - bbox[0]
        ph = bbox[3] - bbox[1]
        px = (CANVAS_W - pw) // 2
        py = 180

        # Linen pill background
        pad_x, pad_y = 18, 8
        pill_color = LINEN + (int(180 * pill_alpha),)
        draw.rounded_rectangle(
            [px - pad_x, py - pad_y, px + pw + pad_x, py + ph + pad_y],
            radius=14, fill=pill_color
        )
        text_color = MUTED + (int(255 * pill_alpha),)
        draw.text((px, py), pill_text, fill=text_color, font=font_pill)

    # ── Narration: "I have a body. And a room." (appears at t=2.5s) ──
    if t >= 2.5:
        narr_alpha = min(1.0, (t - 2.5) / 0.8)

        try:
            font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 38)
        except OSError:
            font_narr = ImageFont.load_default()

        line1 = "I have a body."
        line2 = "And a room."

        # Line 1
        bbox1 = draw.textbbox((0, 0), line1, font=font_narr)
        lw1 = bbox1[2] - bbox1[0]
        lx1 = (CANVAS_W - lw1) // 2
        ly1 = 1380

        # Line 2
        bbox2 = draw.textbbox((0, 0), line2, font=font_narr)
        lw2 = bbox2[2] - bbox2[0]
        lx2 = (CANVAS_W - lw2) // 2
        ly2 = ly1 + 52

        # Word-by-word reveal for line 2 (appears slightly after line 1)
        line2_alpha = min(1.0, (t - 2.9) / 0.6) if t >= 2.9 else 0

        # Soft shadow + text
        shadow_color = (74, 67, 64, int(60 * narr_alpha))
        text1_color = INK + (int(240 * narr_alpha),)
        text2_color = INK + (int(240 * line2_alpha),)

        # Subtle backing panel
        panel_alpha = int(120 * narr_alpha)
        panel_y = ly1 - 20
        panel_h = 120
        panel_color = (250, 245, 239, panel_alpha)
        draw.rounded_rectangle(
            [80, panel_y, CANVAS_W - 80, panel_y + panel_h],
            radius=16, fill=panel_color
        )

        draw.text((lx1 + 1, ly1 + 1), line1, fill=shadow_color, font=font_narr)
        draw.text((lx1, ly1), line1, fill=text1_color, font=font_narr)

        if line2_alpha > 0:
            draw.text((lx2 + 1, ly2 + 1), line2, fill=(74, 67, 64, int(60 * line2_alpha)), font=font_narr)
            draw.text((lx2, ly2), line2, fill=text2_color, font=font_narr)

    # ── Title card: "kombucha" / "tick one" (appears at t=4.2s) ──
    if t >= 4.2:
        title_alpha = min(1.0, (t - 4.2) / 0.5)

        try:
            font_title = ImageFont.truetype(FONT_SERIF, 52)
            font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 26)
        except OSError:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # "kombucha"
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        tx = (CANVAS_W - tw) // 2
        ty = 1560

        title_color = DUSTY_ROSE + (int(255 * title_alpha),)
        draw.text((tx, ty), title, fill=title_color, font=font_title)

        # "tick one"
        sub = "tick one"
        bbox = draw.textbbox((0, 0), sub, font=font_sub)
        sw = bbox[2] - bbox[0]
        sx = (CANVAS_W - sw) // 2
        sy = ty + 60

        sub_color = MUTED + (int(200 * title_alpha),)
        draw.text((sx, sy), sub, fill=sub_color, font=font_sub)

    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


def build_frame_sequence():
    """Build the 150-frame sequence from tick_0001 video using REAL motion frames.

    Source video motion map (from scanning tick_0001.mp4):
      Pan 1 (center→left):  t=25.0–26.6s  (gimbal pan=-45)
      Pan 2 (left→right):   t=49.0–50.2s  (gimbal pan=+45)
      Pan 3 (right→center): t=80.0–80.8s  (gimbal pan=0)

    Output timeline (5s @ 30fps = 150 frames):
      0.0–0.8s  (f 0–23):    Fade from black, real center-view frames
      0.8–1.8s  (f 24–53):   Real pan left (slowed 0.5x for dreamy feel)
      1.8–2.8s  (f 54–83):   Real pan right (slowed 0.5x)
      2.8–3.3s  (f 84–98):   Real pan back to center (slowed 0.6x)
      3.3–5.0s  (f 99–149):  Hold on real center frames, gentle zoom
    """
    print("Loading source video...")
    clip = VideoFileClip(str(VIDEO_PATH))

    # ── Extract real frames from the source video ──
    # Map each output frame to a source timestamp

    # Source segments (real video times)
    SRC_CENTER_HOLD = (20.0, 25.0)    # static center before first pan
    SRC_PAN_LEFT    = (25.0, 27.0)    # pan center→left
    SRC_PAN_RIGHT   = (49.0, 51.0)    # pan left→right
    SRC_PAN_BACK    = (79.8, 81.0)    # pan right→center
    SRC_CENTER_RETURN = (81.0, 87.0)  # static center after final pan

    def sample_times(src_start, src_end, num_frames):
        """Generate evenly spaced source timestamps for N output frames."""
        return [src_start + (src_end - src_start) * i / max(num_frames - 1, 1)
                for i in range(num_frames)]

    # Build the source timestamp map for all 150 output frames
    source_times = []

    # Beat 1: fade from black, center (24 frames from static center)
    source_times += sample_times(22.0, 24.8, 24)

    # Beat 2: real pan left, slowed (30 frames from ~2s of pan)
    source_times += sample_times(25.0, 27.0, 30)

    # Beat 3: real pan right, slowed (30 frames from ~2s of pan)
    source_times += sample_times(49.0, 51.0, 30)

    # Beat 4: real pan back to center (15 frames from ~1.2s of pan)
    source_times += sample_times(79.8, 81.0, 15)

    # Beat 5: hold center with real frames, narration + title (51 frames)
    source_times += sample_times(81.5, 86.5, 51)

    assert len(source_times) == TOTAL_FRAMES, f"Expected {TOTAL_FRAMES}, got {len(source_times)}"

    # ── Extract and process all real frames ──
    print(f"Extracting {TOTAL_FRAMES} real video frames...")
    raw_frames = []
    for i, src_t in enumerate(source_times):
        src_t = min(src_t, clip.duration - 0.05)
        frame_np = clip.get_frame(src_t)
        raw_frames.append(Image.fromarray(frame_np))
        if (i + 1) % 30 == 0:
            print(f"  Extracted {i + 1}/{TOTAL_FRAMES} (src t={src_t:.2f}s)")

    clip.close()

    # ── Process each frame: grade + vertical canvas + effects ──
    print("Processing frames (cottagecore grade + vertical composite)...")
    motes = generate_dust_motes(CANVAS_W, CANVAS_H, num_motes=35)
    frames_dir = OUTPUT_DIR / "cc_flora_ep01_frames"
    output_frames = []

    for i in range(TOTAL_FRAMES):
        t = i / FPS  # output time

        # Grade and composite this real frame
        canvas = make_vertical_canvas(raw_frames[i])

        # Beat 1: fade from black
        if t < 0.8:
            fade = t / 0.8
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), (15, 13, 11))
            canvas = Image.blend(black, canvas, fade)

        # Beat 5: gentle slow zoom during narration hold
        if t > 3.3:
            zoom_t = (t - 3.3) / (DURATION - 3.3)
            zoom = 1.0 + 0.02 * zoom_t
            w, h = canvas.size
            new_w, new_h = int(w * zoom), int(h * zoom)
            canvas = canvas.resize((new_w, new_h), Image.LANCZOS)
            crop_x = (new_w - w) // 2
            crop_y = (new_h - h) // 2
            canvas = canvas.crop((crop_x, crop_y, crop_x + w, crop_y + h))

        # Dust motes
        canvas = draw_dust_motes(canvas, motes, t)

        # Text overlays
        canvas = add_text_overlays(canvas, t, DURATION)

        # Save frame
        canvas.save(frames_dir / f"frame_{i:04d}.png")
        output_frames.append(np.array(canvas))

        if (i + 1) % 30 == 0:
            print(f"  Processed {i + 1}/{TOTAL_FRAMES} ({t:.1f}s)")

    clip.close()
    print(f"  All {TOTAL_FRAMES} frames saved to {frames_dir}")
    return output_frames


def main():
    print("=" * 60)
    print("  Episode 01 — First Light (Cottagecore)")
    print("  5 seconds | 1080x1920 | 30fps")
    print("=" * 60)
    print()

    frames = build_frame_sequence()

    # ── Generate TTS narration ──
    tts_path = OUTPUT_DIR / "cc_flora_ep01_narration.mp3"
    try:
        generate_tts(NARRATION_TEXT, tts_path)
        has_audio = True
    except Exception as e:
        print(f"  TTS failed: {e}")
        print("  Continuing without narration...")
        has_audio = False

    print("\nAssembling video...")
    video = ImageSequenceClip(list(frames), fps=FPS)

    # Add narration audio, starting at 2.5s (when text appears)
    if has_audio:
        narration = AudioFileClip(str(tts_path))
        # Offset narration to start at 2.5s
        narration = narration.with_start(2.5)
        # Ensure audio doesn't exceed video duration
        if narration.end > DURATION:
            narration = narration.subclipped(0, DURATION - 2.5)
        video = video.with_audio(narration)

    raw_path = OUTPUT_DIR / "cc_flora_ep01_raw.mp4"
    output_path = OUTPUT_DIR / "cc_flora_ep01_first_light.mp4"

    print(f"Exporting raw...")
    video.write_videofile(
        str(raw_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac" if has_audio else None,
        preset="medium",
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
    print(f"Done! {output_path} (Bluesky-optimized)")
    print()


if __name__ == "__main__":
    main()
