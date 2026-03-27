"""
CVS Demo — Centaur Video System showcase

Produces a 15-second branded video with:
  - Ken Burns animated title card
  - Synthesized A-minor ambient pad + music-box chimes
  - Text overlays with brand colors
  - Crossfade transitions between scenes
  - Cottagecore color grading
  - Film grain + vignette

No API keys needed. No ComfyUI needed. Runs standalone.

Usage:
    python demo/run_demo.py
"""

import math
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── Config ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"
OUTPUT = DEMO_DIR / "output"

WIDTH, HEIGHT = 1080, 1920   # Vertical TikTok
FPS = 30
DURATION = 15.0              # seconds
TOTAL_FRAMES = int(FPS * DURATION)
SR = 44100

# Brand colors from demo brand kit
PRIMARY = "#DC143C"          # Crimson
SECONDARY = "#1a1a2e"        # Dark navy
ACCENT = "#f0e68c"           # Khaki gold

# Narration lines (timed)
NARRATION = [
    (1.0, "The Centaur Video System"),
    (4.5, "Human-directed."),
    (6.5, "AI-executed."),
    (9.0, "The graph is the boundary."),
    (12.0, "Design once. Render everywhere."),
]

# Fonts (Windows defaults, with fallback)
def load_font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Audio Synthesis ─────────────────────────────────────────────────────────

A2, C3, E3, A3 = 110.0, 130.81, 164.81, 220.0
A4, C5, E5 = 440.0, 523.25, 659.25
A5, C6, E6 = 880.0, 1046.50, 1318.51


def generate_soundtrack(duration):
    """Generate ambient pad + chimes as stereo WAV."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # ── Ambient pad: A-minor drone ──
    drone = np.zeros(n, dtype=np.float64)
    drone += np.sin(2 * np.pi * A2 * t) * 0.050
    drone += np.sin(2 * np.pi * C3 * t) * 0.030
    drone += np.sin(2 * np.pi * E3 * t) * 0.035
    drone += np.sin(2 * np.pi * A3 * t) * 0.025

    # ── Shimmer with LFOs ──
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    lfo3 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + 2.5)
    shimmer = (
        np.sin(2 * np.pi * A4 * t) * 0.012 * lfo1 +
        np.sin(2 * np.pi * C5 * t) * 0.008 * lfo2 +
        np.sin(2 * np.pi * E5 * t) * 0.006 * lfo3
    )

    # ── Mood tone (curious = F4) ──
    mood = np.sin(2 * np.pi * 349.23 * t) * 0.008 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.09 * t))

    pad = drone + shimmer + mood

    # ── Envelope: 3s fade in, 3s fade out ──
    env = np.clip(t / 3.0, 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    pad *= env

    # ── Low-pass filter ──
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
        pad = scipy.signal.sosfilt(sos, pad)
    except ImportError:
        pass  # Skip filter if scipy unavailable

    # ── Stereo panning ──
    pan = 0.5 + 0.3 * np.sin(2 * np.pi * 0.05 * t)
    left = pad * (1 - pan)
    right = pad * pan
    # Binaural beat on right channel
    right += np.sin(2 * np.pi * (A2 + 2.0) * t) * 0.012 * env

    # ── Chimes ──
    chime_times = [0.1, 3.5, 6.0, 8.5, 11.5, 14.0]
    chime_notes = [A5, C6, E6, A5, E6, C6]
    for i, ct in enumerate(chime_times):
        if ct >= duration - 0.5:
            continue
        freq = chime_notes[i % len(chime_notes)]
        env_c = np.where(t - ct >= 0, np.exp(-(t - ct) * 2.5) * np.clip((t - ct) * 20, 0, 1), 0)
        chime = np.sin(2 * np.pi * freq * t) * 0.030 * env_c
        chime += np.sin(2 * np.pi * freq * 2 * t) * 0.010 * env_c
        cpan = 0.3 + 0.4 * ((i % 3) / 2)
        left += chime * (1 - cpan)
        right += chime * cpan

    stereo = np.column_stack([left, right])
    stereo = np.clip(stereo / max(np.abs(stereo).max(), 1e-6) * 0.8, -1, 1)
    return stereo


def write_wav(path, stereo):
    """Write stereo float64 array to WAV."""
    samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(samples.tobytes())


# ── Visual Pipeline ─────────────────────────────────────────────────────────

def hex_to_rgb(h):
    return tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))


def cottagecore_grade(img):
    """Apply cottagecore color grading: warm shadows, desaturated reds."""
    arr = np.array(img, dtype=np.float32) / 255.0
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]

    # Desaturate reds slightly
    red_mask = (r > 0.5) & (r > g * 1.3) & (r > b * 1.3)
    arr[:,:,0] = np.where(red_mask, r * 0.85 + g * 0.1 + b * 0.05, r)

    # Warm shadow lift
    shadow_mask = (r + g + b) / 3 < 0.3
    arr[:,:,0] += np.where(shadow_mask, 0.03, 0)
    arr[:,:,1] += np.where(shadow_mask, 0.01, 0)

    # Range compression (reduce contrast slightly)
    arr = arr * 0.92 + 0.04

    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


def soft_bloom(img, radius=21, blend=0.25):
    """Soft bloom on highlights."""
    blurred = img.filter(ImageFilter.GaussianBlur(radius))
    return Image.blend(img, blurred, blend)


def film_grain(img, intensity=0.03):
    """Add subtle film grain."""
    arr = np.array(img, dtype=np.float32) / 255.0
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    arr = np.clip(arr + noise, 0, 1)
    return Image.fromarray((arr * 255).astype(np.uint8))


def vignette(img, strength=0.4):
    """Cream-tinted radial vignette."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32) / 255.0
    cy, cx = h / 2, w / 2
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx)**2 + (Y - cy)**2) / math.sqrt(cx**2 + cy**2)
    mask = 1.0 - np.clip(dist * strength, 0, 0.6)
    # Cream tint in vignette region
    tint = 1.0 - mask
    arr[:,:,0] = arr[:,:,0] * mask + 0.95 * tint  # warm
    arr[:,:,1] = arr[:,:,1] * mask + 0.90 * tint
    arr[:,:,2] = arr[:,:,2] * mask + 0.82 * tint
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


def ken_burns(img, frame_idx, total_frames, zoom_start=1.0, zoom_end=1.15):
    """Apply Ken Burns zoom + slight pan."""
    w, h = img.size
    progress = frame_idx / max(total_frames - 1, 1)
    # Ease in-out
    progress = 0.5 - 0.5 * math.cos(math.pi * progress)

    zoom = zoom_start + (zoom_end - zoom_start) * progress
    crop_w = int(w / zoom)
    crop_h = int(h / zoom)

    # Slight pan right and down
    cx = w // 2 + int(20 * progress)
    cy = h // 2 + int(10 * progress)

    left = max(0, cx - crop_w // 2)
    top = max(0, cy - crop_h // 2)
    right = min(w, left + crop_w)
    bottom = min(h, top + crop_h)

    cropped = img.crop((left, top, right, bottom))
    return cropped.resize((w, h), Image.LANCZOS)


def make_scene_title(frame_idx, total_scene_frames):
    """Scene 1: Animated title card with brand colors."""
    bg = hex_to_rgb(SECONDARY)
    accent = hex_to_rgb(ACCENT)
    primary = hex_to_rgb(PRIMARY)

    img = Image.new('RGB', (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)

    progress = frame_idx / max(total_scene_frames - 1, 1)

    # Animated accent line (grows from center)
    line_y = HEIGHT // 2 - 120
    line_width = int(WIDTH * 0.6 * min(progress * 3, 1.0))
    line_x = (WIDTH - line_width) // 2
    if line_width > 0:
        draw.rectangle([line_x, line_y, line_x + line_width, line_y + 3], fill=primary)

    # Title text (fades in)
    alpha = min(progress * 2.5, 1.0)
    if alpha > 0.1:
        font_large = load_font(72, bold=True)
        font_small = load_font(36)
        font_tag = load_font(28)

        title = "CENTAUR"
        subtitle = "VIDEO SYSTEM"
        tagline = "human-directed  //  AI-executed"

        # Title
        bbox = draw.textbbox((0, 0), title, font=font_large)
        tw = bbox[2] - bbox[0]
        tx = (WIDTH - tw) // 2
        ty = HEIGHT // 2 - 80
        color_t = tuple(int(c * alpha) for c in (255, 255, 255))
        draw.text((tx, ty), title, fill=color_t, font=font_large)

        # Subtitle
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
        tw2 = bbox2[2] - bbox2[0]
        tx2 = (WIDTH - tw2) // 2
        color_a = tuple(int(c * alpha) for c in accent)
        draw.text((tx2, ty + 90), subtitle, fill=color_a, font=font_small)

        # Tagline (delayed fade)
        tag_alpha = max(0, min((progress - 0.4) * 2.5, 1.0))
        if tag_alpha > 0:
            bbox3 = draw.textbbox((0, 0), tagline, font=font_tag)
            tw3 = bbox3[2] - bbox3[0]
            color_tag = tuple(int(c * tag_alpha) for c in (180, 180, 180))
            draw.text(((WIDTH - tw3) // 2, ty + 150), tagline, fill=color_tag, font=font_tag)

    # Bottom accent line
    line2_width = int(WIDTH * 0.6 * min(progress * 3, 1.0))
    line2_x = (WIDTH - line2_width) // 2
    line2_y = HEIGHT // 2 + 120
    if line2_width > 0:
        draw.rectangle([line2_x, line2_y, line2_x + line2_width, line2_y + 3], fill=primary)

    return img


def make_scene_showcase(frame_idx, total_scene_frames, test_card):
    """Scene 2: Ken Burns on test card with overlays."""
    # Scale test card to fill vertical canvas (blurred bg + sharp center)
    card_w, card_h = test_card.size
    scale = WIDTH / card_w
    new_h = int(card_h * scale)

    # Apply Ken Burns to test card
    zoomed = ken_burns(test_card, frame_idx, total_scene_frames, 1.0, 1.2)

    # Create blurred background fill
    bg_scale = HEIGHT / card_h
    bg = test_card.resize((int(card_w * bg_scale), HEIGHT), Image.LANCZOS)
    # Center crop
    if bg.width > WIDTH:
        left = (bg.width - WIDTH) // 2
        bg = bg.crop((left, 0, left + WIDTH, HEIGHT))
    else:
        bg = bg.resize((WIDTH, HEIGHT), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(25))
    from PIL import ImageEnhance
    bg = ImageEnhance.Brightness(bg).enhance(0.35)

    # Paste sharp video centered
    sharp = zoomed.resize((WIDTH, new_h), Image.LANCZOS)
    y_pos = (HEIGHT - new_h) // 2 - 60
    bg.paste(sharp, (0, max(0, y_pos)))

    # Apply grading
    bg = cottagecore_grade(bg)
    bg = soft_bloom(bg, radius=15, blend=0.2)

    return bg


def make_scene_principles(frame_idx, total_scene_frames):
    """Scene 3: Design principles with animated reveals."""
    bg_color = hex_to_rgb(SECONDARY)
    accent = hex_to_rgb(ACCENT)
    primary = hex_to_rgb(PRIMARY)

    img = Image.new('RGB', (WIDTH, HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    progress = frame_idx / max(total_scene_frames - 1, 1)
    font_heading = load_font(48, bold=True)
    font_body = load_font(30)
    font_small = load_font(24)

    principles = [
        ("THE GRAPH", "is the directive"),
        ("THE BRAND KIT", "is the identity"),
        ("THE RULE GATE", "is the guardrail"),
    ]

    y_start = HEIGHT // 2 - 250
    for i, (heading, body) in enumerate(principles):
        reveal_progress = max(0, min((progress - i * 0.25) * 3.0, 1.0))
        if reveal_progress <= 0:
            continue

        y = y_start + i * 180
        alpha = reveal_progress

        # Accent dot
        dot_color = tuple(int(c * alpha) for c in primary)
        draw.ellipse([80, y + 8, 100, y + 28], fill=dot_color)

        # Heading
        h_color = tuple(int(c * alpha) for c in (255, 255, 255))
        draw.text((120, y), heading, fill=h_color, font=font_heading)

        # Body (slightly delayed)
        body_alpha = max(0, min((reveal_progress - 0.3) * 2.0, 1.0))
        b_color = tuple(int(c * body_alpha) for c in accent)
        draw.text((120, y + 55), body, fill=b_color, font=font_body)

    # Bottom URL
    url_alpha = max(0, min((progress - 0.6) * 3.0, 1.0))
    if url_alpha > 0:
        url = "github.com/BucketHarmony/CentaurVideoSystem"
        bbox = draw.textbbox((0, 0), url, font=font_small)
        tw = bbox[2] - bbox[0]
        url_color = tuple(int(c * url_alpha) for c in (120, 120, 120))
        draw.text(((WIDTH - tw) // 2, HEIGHT - 200), url, fill=url_color, font=font_small)

    return img


def add_narration_overlay(img, frame_idx):
    """Add narration text overlay based on timing."""
    current_time = frame_idx / FPS

    # Find active narration line
    active_text = None
    for i, (start, text) in enumerate(NARRATION):
        end = NARRATION[i + 1][0] - 0.3 if i + 1 < len(NARRATION) else start + 2.5
        if start <= current_time < end:
            # Fade in/out
            fade_in = min((current_time - start) * 4, 1.0)
            fade_out = min((end - current_time) * 4, 1.0)
            alpha = min(fade_in, fade_out)
            active_text = (text, alpha)
            break

    if not active_text:
        return img

    text, alpha = active_text
    draw = ImageDraw.Draw(img)
    font = load_font(38, bold=True)

    # Text position (safe zone: above bottom 480px)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (WIDTH - tw) // 2
    ty = HEIGHT - 560

    # Semi-transparent background pill
    pad = 16
    pill_alpha = int(160 * alpha)
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [tx - pad, ty - pad, tx + tw + pad, ty + th + pad],
        radius=12,
        fill=(26, 26, 46, pill_alpha)
    )

    # Text with alpha
    text_color = tuple(int(c * alpha) for c in hex_to_rgb(ACCENT))
    overlay_draw.text((tx, ty), text, fill=text_color + (int(255 * alpha),), font=font)

    img = img.convert('RGBA')
    img = Image.alpha_composite(img, overlay)
    return img.convert('RGB')


# ── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Demo — Centaur Video System Showcase")
    print("=" * 60)

    OUTPUT.mkdir(exist_ok=True)

    # Load test card for scene 2
    test_card_path = DEMO_DIR / "assets" / "test_card_1080p.png"
    if not test_card_path.exists():
        print("  Generating test cards...")
        subprocess.run([sys.executable, str(DEMO_DIR / "assets" / "test_card.py")],
                      check=True, capture_output=True)
    test_card = Image.open(test_card_path)

    # ── Generate frames ──
    print(f"\n  Rendering {TOTAL_FRAMES} frames at {WIDTH}x{HEIGHT}...")

    # Scene breakdown: title (5s) + showcase (5s) + principles (5s)
    scene_frames = [int(5 * FPS), int(5 * FPS), int(5 * FPS)]
    frame_dir = OUTPUT / "frames"
    frame_dir.mkdir(exist_ok=True)

    frame_idx_global = 0
    for scene_num, num_frames in enumerate(scene_frames):
        for local_idx in range(num_frames):
            if scene_num == 0:
                img = make_scene_title(local_idx, num_frames)
            elif scene_num == 1:
                img = make_scene_showcase(local_idx, num_frames, test_card)
            else:
                img = make_scene_principles(local_idx, num_frames)

            # Crossfade between scenes (15 frames overlap)
            overlap = 15
            if scene_num > 0 and local_idx < overlap:
                # Get last frame of previous scene
                prev_path = frame_dir / f"frame_{frame_idx_global - 1:05d}.png"
                if prev_path.exists():
                    prev = Image.open(prev_path)
                    blend = local_idx / overlap
                    img = Image.blend(prev, img, blend)

            # Apply global effects
            img = film_grain(img, 0.02)
            img = vignette(img, 0.35)
            img = add_narration_overlay(img, frame_idx_global)

            # Save frame
            img.save(frame_dir / f"frame_{frame_idx_global:05d}.png")
            frame_idx_global += 1

            if frame_idx_global % 30 == 0:
                pct = frame_idx_global / TOTAL_FRAMES * 100
                print(f"    [{pct:5.1f}%] Frame {frame_idx_global}/{TOTAL_FRAMES}")

    # ── Generate audio ──
    print("\n  Synthesizing A-minor ambient pad + chimes...")
    audio = generate_soundtrack(DURATION)
    audio_path = OUTPUT / "demo_soundtrack.wav"
    write_wav(audio_path, audio)
    print(f"    Saved: {audio_path}")

    # ── Encode video ──
    print("\n  Encoding video with ffmpeg...")
    video_path = OUTPUT / "cvs_demo.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-crf", "18",
        "-shortest",
        str(video_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ffmpeg error: {result.stderr[-500:]}")
        sys.exit(1)

    # ── Cleanup frames ──
    import shutil
    shutil.rmtree(frame_dir)

    # ── Report ──
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"\n  Output: {video_path}")
    print(f"  Size:   {size_mb:.1f} MB")
    print(f"  Format: H.264 yuv420p {WIDTH}x{HEIGHT} @ {FPS}fps")
    print(f"  Audio:  A-minor pad + chimes, 44.1kHz stereo")
    print(f"  Duration: {DURATION}s")
    print("\n" + "=" * 60)
    print("  Done! Open the video to see the CVS demo.")
    print("=" * 60)


if __name__ == "__main__":
    main()
