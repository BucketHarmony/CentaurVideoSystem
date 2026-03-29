"""
CVS Showcase — 8-Bit World Builder

Transforms any image through the Stardew Valley pixel art pipeline,
then produces a 12-second animated vertical video with:

  - Source image → edge detection → pixelation → palette quantization
  - Stardew Valley 30-color earth-tone palette
  - Wooden frame with golden corner gems
  - Side-by-side reveal animation (original → pixel art)
  - Synthesized chiptune-style music (A-minor arpeggios + chimes)
  - TikTok vertical canvas (1080x1920)

No API keys. No ComfyUI. Standalone.

Usage:
    python demo/run_8bit_showcase.py
    python demo/run_8bit_showcase.py path/to/your/image.png
"""

import math
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "demo" / "output"

WIDTH, HEIGHT = 1080, 1920
FPS = 30
DURATION = 12.0
TOTAL_FRAMES = int(FPS * DURATION)
SR = 44100

# ── Stardew Valley Palette (30 colors) ──────────────────────────────────────

PALETTE = [
    (34, 17, 17),      # deep shadow
    (56, 36, 28),      # dark soil
    (92, 68, 52),      # rich wood
    (140, 105, 75),    # oak plank
    (180, 148, 108),   # light wood
    (215, 192, 162),   # birch
    (240, 228, 210),   # cream
    (255, 248, 235),   # warm white
    (140, 40, 40),     # barn red
    (185, 65, 55),     # clay pot
    (210, 105, 80),    # terracotta
    (235, 160, 120),   # peach
    (50, 75, 45),      # forest dark
    (75, 115, 60),     # grass
    (110, 160, 85),    # spring green
    (165, 210, 130),   # meadow
    (200, 230, 170),   # pale green
    (60, 90, 130),     # pond blue
    (95, 140, 175),    # sky
    (145, 190, 215),   # light sky
    (195, 225, 240),   # cloud
    (180, 130, 70),    # honey
    (220, 180, 90),    # golden wheat
    (250, 220, 120),   # sunflower
    (130, 95, 120),    # plum shadow
    (170, 135, 155),   # lavender dusk
    (210, 180, 195),   # pink blossom
    (120, 100, 90),    # stone
    (160, 145, 130),   # cobble
    (200, 190, 175),   # light stone
]

WOOD_DARK = (56, 36, 28)
WOOD_MID = (92, 68, 52)
WOOD_LIGHT = (180, 148, 108)
GOLDEN_WHEAT = (220, 180, 90)
SUNFLOWER = (250, 220, 120)
CREAM = (215, 192, 162)
PEACH = (235, 160, 120)
LAVENDER = (170, 135, 155)


def load_font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Pixel Art Pipeline ──────────────────────────────────────────────────────

def nearest_palette(arr, palette):
    """Vectorized nearest-color palette mapping."""
    h, w, c = arr.shape
    flat = arr.reshape(-1, 3).astype(np.float32)
    pal = np.array(palette, dtype=np.float32)
    # Chunked to avoid memory explosion on large images
    chunk_size = 50000
    result = np.zeros_like(flat, dtype=np.uint8)
    for i in range(0, len(flat), chunk_size):
        chunk = flat[i:i + chunk_size]
        dists = np.sum((chunk[:, np.newaxis, :] - pal[np.newaxis, :, :]) ** 2, axis=2)
        indices = np.argmin(dists, axis=1)
        result[i:i + chunk_size] = pal[indices].astype(np.uint8)
    return result.reshape(h, w, 3)


def build_edges(img):
    """Multi-scale edge detection."""
    gray = img.convert("L")
    e1 = np.array(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    e2_raw = gray.filter(ImageFilter.Kernel(
        size=(3, 3), kernel=[-1, -1, -1, -1, 8, -1, -1, -1, -1],
        scale=1, offset=128
    ))
    e2 = np.abs(np.array(e2_raw, dtype=np.float32) - 128) * 2
    combined = np.clip(e1 * 0.6 + e2 * 0.4, 0, 255)
    binary = np.where(combined > 40, 255, 0).astype(np.uint8)
    edge_img = Image.fromarray(binary).filter(ImageFilter.MaxFilter(size=3))
    return edge_img


def pixelate(img, pixel_size=6):
    """Downscale → palette quantize → NEAREST upscale."""
    w, h = img.size
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    small = img.resize((w // pixel_size, h // pixel_size), Image.BILINEAR)
    small = ImageEnhance.Color(small).enhance(1.5)
    small = ImageEnhance.Contrast(small).enhance(1.3)
    quantized = nearest_palette(np.array(small), PALETTE)
    pixel_art = Image.fromarray(quantized)
    return pixel_art.resize((w, h), Image.NEAREST)


def add_edges(pixel_art, edges):
    """Burn dark outlines onto pixel art."""
    edges = edges.resize(pixel_art.size, Image.NEAREST)
    arr = np.array(pixel_art)
    arr[np.array(edges) > 128] = (20, 18, 16)
    return Image.fromarray(arr)


def add_wooden_frame(img):
    """Stardew Valley wooden UI frame with corner gems."""
    w, h = img.size
    b = 18
    framed = Image.new("RGB", (w + b * 2, h + b * 2), WOOD_MID)
    draw = ImageDraw.Draw(framed)
    draw.rectangle([0, 0, w + b*2 - 1, h + b*2 - 1], outline=WOOD_DARK, width=4)
    draw.rectangle([b-3, b-3, w+b+2, h+b+2], outline=WOOD_LIGHT, width=2)
    draw.rectangle([b-1, b-1, w+b, h+b], outline=(140, 105, 75), width=1)
    framed.paste(img, (b, b))
    for cx, cy in [(7, 7), (w+b*2-8, 7), (7, h+b*2-8), (w+b*2-8, h+b*2-8)]:
        draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill=GOLDEN_WHEAT, outline=(180, 130, 70))
    return framed


# ── Audio: Chiptune A-minor ─────────────────────────────────────────────────

def generate_chiptune(duration):
    """Generate chiptune-style A-minor arpeggios + bass + chimes."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Square wave approximation (fundamental + odd harmonics)
    def square_wave(freq, t, harmonics=5):
        w = np.zeros_like(t)
        for k in range(1, harmonics * 2, 2):
            w += np.sin(2 * np.pi * freq * k * t) / k
        return w * (4 / np.pi) * 0.3

    # Triangle wave
    def tri_wave(freq, t):
        phase = (t * freq) % 1.0
        return (4 * np.abs(phase - 0.5) - 1) * 0.4

    # ── Bass line: A2 pulse with rhythm ──
    bass_notes = [110.0, 110.0, 130.81, 164.81]  # A2, A2, C3, E3
    beat_len = SR // 4  # 16th note at 120 BPM
    bass = np.zeros(n, dtype=np.float64)
    for i in range(n):
        note_idx = (i // (beat_len * 4)) % len(bass_notes)
        freq = bass_notes[note_idx]
        # Gate: on for 75% of beat
        if (i % (beat_len * 4)) < (beat_len * 3):
            bass[i] = tri_wave(freq, t[i:i+1])[0] * 0.15
    # Low-pass the bass
    try:
        import scipy.signal
        sos = scipy.signal.butter(2, 400, 'low', fs=SR, output='sos')
        bass = scipy.signal.sosfilt(sos, bass)
    except ImportError:
        pass

    # ── Arpeggio: A-minor broken chord ──
    arp_notes = [440.0, 523.25, 659.25, 880.0, 659.25, 523.25]  # A4 C5 E5 A5 E5 C5
    arp_beat = SR // 6  # Faster arpeggios
    arp = np.zeros(n, dtype=np.float64)
    for i in range(n):
        note_idx = (i // arp_beat) % len(arp_notes)
        freq = arp_notes[note_idx]
        # Short envelope per note
        pos_in_beat = (i % arp_beat) / arp_beat
        env = max(0, 1.0 - pos_in_beat * 3.0)  # Quick decay
        arp[i] = square_wave(freq, t[i:i+1], harmonics=3)[0] * 0.06 * env

    # ── Ambient pad (sine, gentle) ──
    pad = (
        np.sin(2 * np.pi * 220.0 * t) * 0.03 +
        np.sin(2 * np.pi * 329.63 * t) * 0.02 +
        np.sin(2 * np.pi * 440.0 * t) * 0.015
    )
    # LFO tremolo
    pad *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t)

    # ── Chimes at key moments ──
    chime_times = [0.1, 2.0, 4.0, 6.5, 8.5, 10.5]
    chime_notes = [880.0, 1046.5, 1318.5, 880.0, 1318.5, 1046.5]
    chimes = np.zeros(n, dtype=np.float64)
    for ct, freq in zip(chime_times, chime_notes):
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 4.0) * np.clip(env_t * 30, 0, 1), 0)
        chimes += np.sin(2 * np.pi * freq * t) * 0.04 * env
        chimes += np.sin(2 * np.pi * freq * 2 * t) * 0.015 * env

    # ── Mix ──
    mix = bass + arp + pad + chimes

    # ── Master envelope ──
    env = np.clip(t / 2.0, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    mix *= env

    # ── Stereo (slight spread) ──
    left = mix + arp * 0.3
    right = mix - arp * 0.3 + chimes * 0.2

    stereo = np.column_stack([left, right])
    peak = np.abs(stereo).max()
    if peak > 0:
        stereo = stereo / peak * 0.75
    return stereo


def write_wav(path, stereo):
    samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(samples.tobytes())


# ── Frame Generation ────────────────────────────────────────────────────────

def render_frame(frame_idx, source_img, pixel_art, framed_art, edges_img):
    """Render a single frame of the showcase animation."""
    progress = frame_idx / max(TOTAL_FRAMES - 1, 1)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), WOOD_DARK)
    draw = ImageDraw.Draw(canvas)

    font_title = load_font(44, bold=True)
    font_label = load_font(24)
    font_small = load_font(20)
    font_tag = load_font(18)

    # ── Header ──
    title_alpha = min(progress * 4, 1.0)
    if title_alpha > 0:
        title = "8-BIT WORLD BUILDER"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        color = tuple(int(c * title_alpha) for c in SUNFLOWER)
        draw.text(((WIDTH - tw) // 2, 100), title, fill=color, font=font_title)

        sub = "stardew valley palette  //  30 colors"
        bbox2 = draw.textbbox((0, 0), sub, font=font_label)
        sw = bbox2[2] - bbox2[0]
        sub_color = tuple(int(c * title_alpha) for c in CREAM)
        draw.text(((WIDTH - sw) // 2, 155), sub, fill=sub_color, font=font_label)

    # ── Scene layout based on time ──
    # 0-3s: Source image appears
    # 3-5s: Edge detection reveal
    # 5-8s: Pixel art transformation (wipe reveal)
    # 8-10s: Framed version with labels
    # 10-12s: Full showcase + palette strip

    art_region_y = 240
    art_region_h = 1100
    art_region_w = WIDTH - 80
    art_x = 40

    if progress < 0.25:
        # Scene 1: Source image
        local_p = progress / 0.25
        alpha = min(local_p * 3, 1.0)
        label = "SOURCE"

        scaled = source_img.copy()
        s = art_region_w / max(scaled.size)
        new_size = (int(scaled.width * s), int(scaled.height * s))
        scaled = scaled.resize(new_size, Image.LANCZOS)
        px = art_x + (art_region_w - new_size[0]) // 2
        py = art_region_y + (art_region_h - new_size[1]) // 2
        canvas.paste(scaled, (px, py))

        draw.text((art_x, art_region_y - 30), f"[ {label} ]", fill=LAVENDER, font=font_label)

    elif progress < 0.42:
        # Scene 2: Edge detection (cross-dissolve from source)
        local_p = (progress - 0.25) / 0.17
        label = "EDGE DETECTION"

        # Blend source and edges
        s = art_region_w / max(source_img.size)
        new_size = (int(source_img.width * s), int(source_img.height * s))
        src_scaled = source_img.resize(new_size, Image.LANCZOS)

        edge_rgb = Image.new("RGB", source_img.size, (240, 225, 200))
        e_arr = np.array(edge_rgb)
        e_arr[np.array(edges_img.resize(source_img.size, Image.NEAREST)) > 128] = (20, 18, 16)
        edge_vis = Image.fromarray(e_arr).resize(new_size, Image.LANCZOS)

        blended = Image.blend(src_scaled, edge_vis, min(local_p * 1.5, 1.0))
        px = art_x + (art_region_w - new_size[0]) // 2
        py = art_region_y + (art_region_h - new_size[1]) // 2
        canvas.paste(blended, (px, py))

        draw.text((art_x, art_region_y - 30), f"[ {label} ]", fill=LAVENDER, font=font_label)

    elif progress < 0.67:
        # Scene 3: Pixel art wipe reveal (left to right)
        local_p = (progress - 0.42) / 0.25
        label = "PIXELATE + QUANTIZE"

        s = art_region_w / max(source_img.size)
        new_size = (int(source_img.width * s), int(source_img.height * s))
        src_scaled = source_img.resize(new_size, Image.LANCZOS)
        pix_scaled = pixel_art.resize(new_size, Image.NEAREST)

        # Wipe: left side is pixel art, right is source
        wipe_x = int(new_size[0] * min(local_p * 1.3, 1.0))
        composite = src_scaled.copy()
        if wipe_x > 0:
            left_strip = pix_scaled.crop((0, 0, wipe_x, new_size[1]))
            composite.paste(left_strip, (0, 0))

        # Draw wipe line
        comp_draw = ImageDraw.Draw(composite)
        if 0 < wipe_x < new_size[0]:
            comp_draw.line([(wipe_x, 0), (wipe_x, new_size[1])], fill=SUNFLOWER, width=3)

        px = art_x + (art_region_w - new_size[0]) // 2
        py = art_region_y + (art_region_h - new_size[1]) // 2
        canvas.paste(composite, (px, py))

        draw.text((art_x, art_region_y - 30), f"[ {label} ]", fill=LAVENDER, font=font_label)

    elif progress < 0.83:
        # Scene 4: Framed pixel art
        local_p = (progress - 0.67) / 0.16
        label = "STARDEW FRAME"

        s = (art_region_w - 40) / max(framed_art.size)
        new_size = (int(framed_art.width * s), int(framed_art.height * s))
        framed_scaled = framed_art.resize(new_size, Image.NEAREST)
        px = art_x + (art_region_w - new_size[0]) // 2
        py = art_region_y + (art_region_h - new_size[1]) // 2
        canvas.paste(framed_scaled, (px, py))

        draw.text((art_x, art_region_y - 30), f"[ {label} ]", fill=LAVENDER, font=font_label)

    else:
        # Scene 5: Full showcase with palette
        local_p = (progress - 0.83) / 0.17
        label = "COMPLETE"

        s = (art_region_w - 40) / max(framed_art.size)
        new_size = (int(framed_art.width * s), int(framed_art.height * s))
        framed_scaled = framed_art.resize(new_size, Image.NEAREST)
        px = art_x + (art_region_w - new_size[0]) // 2
        py = art_region_y + (art_region_h - new_size[1]) // 2 - 40
        canvas.paste(framed_scaled, (px, py))

        draw.text((art_x, art_region_y - 30), f"[ {label} ]", fill=LAVENDER, font=font_label)

        # Draw palette strip
        palette_y = py + new_size[1] + 30
        swatch_size = 28
        cols = 15
        px_start = (WIDTH - cols * (swatch_size + 4)) // 2
        for i, color in enumerate(PALETTE):
            row = i // cols
            col = i % cols
            x = px_start + col * (swatch_size + 4)
            y = palette_y + row * (swatch_size + 4)
            reveal = min((local_p - i * 0.02) * 5, 1.0)
            if reveal > 0:
                draw.rectangle([x, y, x + swatch_size, y + swatch_size],
                             fill=color, outline=WOOD_DARK)

        draw.text((px_start, palette_y + (swatch_size + 4) * 2 + 10),
                  "30-color Stardew Valley earth-tone palette",
                  fill=CREAM, font=font_small)

    # ── Footer ──
    footer_alpha = min(progress * 3, 1.0)
    if footer_alpha > 0:
        footer = "centaur video system  //  8bit_world.py"
        bbox = draw.textbbox((0, 0), footer, font=font_tag)
        fw = bbox[2] - bbox[0]
        f_color = tuple(int(c * footer_alpha * 0.5) for c in (200, 200, 200))
        draw.text(((WIDTH - fw) // 2, HEIGHT - 120), footer, fill=f_color, font=font_tag)

    return canvas


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Showcase — 8-Bit World Builder")
    print("  Stardew Valley pixel art pipeline")
    print("=" * 60)

    # Load source image
    if len(sys.argv) > 1:
        source_path = Path(sys.argv[1])
    else:
        source_path = ROOT / "demo" / "assets" / "test_card_1080p.png"

    if not source_path.exists():
        print(f"  Error: {source_path} not found")
        sys.exit(1)

    print(f"\n  Source: {source_path.name}")
    source_img = Image.open(source_path).convert("RGB")
    print(f"  Size: {source_img.size[0]}x{source_img.size[1]}")

    # ── Run pixel art pipeline ──
    print("\n  Running pixel art pipeline...")
    print("    1. Edge detection (multi-scale, threshold >40)")
    edges = build_edges(source_img)

    print("    2. Pixelate (6px blocks, blur pre-filter)")
    pixel_art = pixelate(source_img, pixel_size=6)

    print("    3. Burn edge outlines")
    pixel_art = add_edges(pixel_art, edges)

    print("    4. Add wooden frame + corner gems")
    framed = add_wooden_frame(pixel_art)

    # Save stills
    OUTPUT.mkdir(exist_ok=True)
    pixel_art.save(OUTPUT / "8bit_pixel_art.png")
    framed.save(OUTPUT / "8bit_framed.png")
    print(f"    Saved stills to {OUTPUT}")

    # ── Render frames ──
    print(f"\n  Rendering {TOTAL_FRAMES} frames...")
    frame_dir = OUTPUT / "8bit_frames"
    frame_dir.mkdir(exist_ok=True)

    for i in range(TOTAL_FRAMES):
        frame = render_frame(i, source_img, pixel_art, framed, edges)
        frame.save(frame_dir / f"frame_{i:05d}.png")
        if (i + 1) % 30 == 0:
            pct = (i + 1) / TOTAL_FRAMES * 100
            print(f"    [{pct:5.1f}%] Frame {i+1}/{TOTAL_FRAMES}")

    # ── Generate audio ──
    print("\n  Synthesizing chiptune soundtrack...")
    audio = generate_chiptune(DURATION)
    audio_path = OUTPUT / "8bit_soundtrack.wav"
    write_wav(audio_path, audio)

    # ── Encode ──
    print("  Encoding video...")
    video_path = OUTPUT / "cvs_8bit_showcase.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-crf", "18",
        "-shortest", str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ffmpeg error: {result.stderr[-300:]}")
        sys.exit(1)

    # Cleanup frames
    import shutil
    shutil.rmtree(frame_dir)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"\n  Output: {video_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Pipeline: source -> edges -> pixelate -> palette -> frame -> animate")
    print(f"  Audio: chiptune A-minor (square wave bass + arpeggios + chimes)")
    print("\n" + "=" * 60)
    print("  Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
