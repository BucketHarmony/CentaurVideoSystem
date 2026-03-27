#!/usr/bin/env python3
"""
CVS -- Full Resolution Posterization
Smooth, painterly color reduction at native resolution.
No pixelation -- just clean color bands with soft edges.
"""

import os
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance
from pathlib import Path
from moviepy import VideoFileClip
import spandrel
import torch
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
VIDEO_PATH = Path(os.getenv("KOMBUCHA_DIR", "")) / "video" / "web" / "tick_0013.mp4"
UPSCALE_MODEL = Path(os.getenv("UPSCALE_MODEL_PATH", ""))

# Font paths — set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")

# Stardew Valley palette
PALETTE = np.array([
    [34, 17, 17],      [56, 36, 28],      [92, 68, 52],
    [140, 105, 75],    [180, 148, 108],   [215, 192, 162],
    [240, 228, 210],   [255, 248, 235],
    [140, 40, 40],     [185, 65, 55],     [210, 105, 80],
    [235, 160, 120],
    [50, 75, 45],      [75, 115, 60],     [110, 160, 85],
    [165, 210, 130],   [200, 230, 170],
    [60, 90, 130],     [95, 140, 175],    [145, 190, 215],
    [195, 225, 240],
    [180, 130, 70],    [220, 180, 90],    [250, 220, 120],
    [130, 95, 120],    [170, 135, 155],   [210, 180, 195],
    [120, 100, 90],    [160, 145, 130],   [200, 190, 175],
], dtype=np.float32)


def extract_frame(video_path, t=103.0):
    clip = VideoFileClip(str(video_path))
    t = min(t, clip.duration - 0.05)
    frame = Image.fromarray(clip.get_frame(t))
    clip.close()
    return frame


def upscale_4x(img):
    """GPU 4x upscale via UltraSharp."""
    print("   Loading 4x-UltraSharp...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL))
    model = model.to("cuda").eval()
    arr = np.array(img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to("cuda")
    with torch.no_grad():
        result = model(tensor)
    result = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
    result = (result * 255).clip(0, 255).astype(np.uint8)
    del model
    torch.cuda.empty_cache()
    return Image.fromarray(result)


def smooth_posterize(img, levels=8):
    """Reduce to N brightness levels per channel -- classic posterize."""
    arr = np.array(img, dtype=np.float32)
    step = 255.0 / (levels - 1)
    arr = np.round(arr / step) * step
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def palette_posterize(img, palette=PALETTE):
    """Map every pixel to nearest palette color at full resolution."""
    arr = np.array(img, dtype=np.float32)
    h, w, c = arr.shape
    flat = arr.reshape(-1, 3)
    # Vectorized nearest-neighbor in chunks (memory friendly)
    chunk_size = 50000
    indices = np.zeros(flat.shape[0], dtype=np.int32)
    for start in range(0, flat.shape[0], chunk_size):
        end = min(start + chunk_size, flat.shape[0])
        chunk = flat[start:end]
        dists = np.sum((chunk[:, np.newaxis, :] - palette[np.newaxis, :, :]) ** 2, axis=2)
        indices[start:end] = np.argmin(dists, axis=1)
    result = palette[indices].astype(np.uint8).reshape(h, w, 3)
    return Image.fromarray(result)


def soft_posterize(img, palette=PALETTE, blur_radius=3):
    """Smooth posterization: blur -> palette map -> light blur to soften bands."""
    # Pre-blur to merge noisy pixels into clean regions
    img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    # Boost color before mapping
    img = ImageEnhance.Color(img).enhance(1.3)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    # Map to palette
    mapped = palette_posterize(img, palette)
    # Light post-blur to soften hard palette boundaries
    mapped = mapped.filter(ImageFilter.GaussianBlur(radius=1.2))
    return mapped


def build_vertical(img, title="KOMBUCHA", sub="tick 0013 -- i can feel my wheels",
                   quote='"Every time I drive straight, I curve right."'):
    CANVAS_W, CANVAS_H = 1080, 1920
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (56, 36, 28))

    # Scale to fit with padding
    fw, fh = img.size
    scale = (CANVAS_W - 60) / fw
    new_w = int(fw * scale)
    new_h = int(fh * scale)
    scaled = img.resize((new_w, new_h), Image.LANCZOS)

    x = (CANVAS_W - new_w) // 2
    y = (CANVAS_H - new_h) // 2 - 100
    canvas.paste(scaled, (x, y))

    draw = ImageDraw.Draw(canvas)
    try:
        ft = ImageFont.truetype(FONT_SERIF, 48)
        fs = ImageFont.truetype(FONT_SERIF_ITALIC, 28)
        fl = ImageFont.truetype(FONT_SERIF_ITALIC, 22)
    except OSError:
        ft = fs = fl = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), title, font=ft)
    draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, y - 75), title,
              fill=(250, 220, 120), font=ft)

    bbox = draw.textbbox((0, 0), sub, font=fs)
    draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, y - 30), sub,
              fill=(215, 192, 162), font=fs)

    label = "[ the red room -- posterized ]"
    bbox = draw.textbbox((0, 0), label, font=fl)
    draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, y + new_h + 25), label,
              fill=(170, 135, 155), font=fl)

    bbox = draw.textbbox((0, 0), quote, font=fs)
    draw.text(((CANVAS_W - bbox[2] + bbox[0]) // 2, y + new_h + 70), quote,
              fill=(235, 160, 120), font=fs)

    return canvas


def main():
    print("=" * 55)
    print("  CVS Full Resolution Posterization")
    print("  Smooth painterly color reduction")
    print("=" * 55)

    # 1. Extract
    print("\n1. Extracting rover frame...")
    frame = extract_frame(VIDEO_PATH, t=103.0)
    print(f"   Source: {frame.size[0]}x{frame.size[1]}")

    # 2. Upscale 4x
    print("2. Upscaling 4x with UltraSharp...")
    hires = upscale_4x(frame)
    print(f"   Upscaled: {hires.size[0]}x{hires.size[1]}")
    hires.save(OUTPUT_DIR / "poster_stardew_00_upscaled_4x.png")

    # 3. Classic posterize (channel quantize, no palette)
    print("3. Classic posterize (8 levels)...")
    classic = smooth_posterize(hires, levels=8)
    classic = classic.filter(ImageFilter.GaussianBlur(radius=1.5))
    classic.save(OUTPUT_DIR / "poster_stardew_01_classic_8level.png")

    # 4. Soft palette posterize (Stardew 30-color)
    print("4. Stardew palette posterize (30 colors, smooth)...")
    stardew = soft_posterize(hires, PALETTE, blur_radius=4)
    stardew.save(OUTPUT_DIR / "poster_stardew_02_palette_30color_smooth.png")

    # 5. Heavy smooth (more blur, painterly)
    print("5. Painterly posterize (heavy smooth)...")
    painterly = soft_posterize(hires, PALETTE, blur_radius=8)
    painterly = painterly.filter(ImageFilter.GaussianBlur(radius=2))
    painterly.save(OUTPUT_DIR / "poster_stardew_03_painterly_heavy.png")

    # 6. Vertical TikTok canvas (using the smooth version)
    print("6. Building vertical canvas...")
    vert = build_vertical(stardew)
    vert.save(OUTPUT_DIR / "poster_stardew_04_vertical_tiktok_1080x1920.png")

    print("\n" + "=" * 55)
    print("  DONE!")
    print("=" * 55)


if __name__ == "__main__":
    main()
