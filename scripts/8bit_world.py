#!/usr/bin/env python3
"""
CVS -- 8-Bit World Builder
Takes a rover frame -> edge detection outline -> pixelated Stardew Valley / Minecraft aesthetic.
"""

import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageEnhance, ImageFont
from pathlib import Path
from moviepy import VideoFileClip

OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output")
VIDEO_PATH = Path("E:/AI/Kombucha/video/web/tick_0013.mp4")

# Stardew Valley palette — warm, earthy, cozy pixel farm life
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


def nearest_palette_vectorized(arr, palette):
    """Map every pixel in an image array to its nearest palette color (fast)."""
    h, w, c = arr.shape
    flat = arr.reshape(-1, 3).astype(np.float32)
    pal = np.array(palette, dtype=np.float32)
    # Broadcast distance calculation
    # flat: (N, 3), pal: (P, 3) -> distances: (N, P)
    distances = np.sum((flat[:, np.newaxis, :] - pal[np.newaxis, :, :]) ** 2, axis=2)
    indices = np.argmin(distances, axis=1)
    result = pal[indices].astype(np.uint8)
    return result.reshape(h, w, 3)


def extract_frame(video_path, t=103.0):
    """Extract a single frame from video."""
    clip = VideoFileClip(str(video_path))
    t = min(t, clip.duration - 0.05)
    frame = Image.fromarray(clip.get_frame(t))
    clip.close()
    return frame


def build_edge_outline(img):
    """Create a clean edge detection outline."""
    gray = img.convert("L")

    # Multi-scale edge detection
    edges1 = gray.filter(ImageFilter.FIND_EDGES)
    edges2 = gray.filter(ImageFilter.Kernel(
        size=(3, 3),
        kernel=[-1, -1, -1, -1, 8, -1, -1, -1, -1],
        scale=1, offset=128
    ))

    e1 = np.array(edges1, dtype=np.float32)
    e2 = np.abs(np.array(edges2, dtype=np.float32) - 128) * 2
    combined = np.clip(e1 * 0.6 + e2 * 0.4, 0, 255)

    # Threshold
    combined = np.where(combined > 40, 255, 0).astype(np.uint8)

    # Slight dilation for thicker pixel-art lines
    edge_img = Image.fromarray(combined)
    edge_img = edge_img.filter(ImageFilter.MaxFilter(size=3))

    return edge_img


def pixelate_to_8bit(img, pixel_size=8, palette=PALETTE):
    """Downscale -> palette quantize -> upscale for chunky pixel art."""
    w, h = img.size

    # Pre-blur: smooth noise before quantizing (cleaner pixel blocks)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    small_w = w // pixel_size
    small_h = h // pixel_size
    # BILINEAR blends neighbors for smoother color blocks
    small = img.resize((small_w, small_h), Image.BILINEAR)

    # Boost saturation + contrast for the gamer palette pop
    small = ImageEnhance.Color(small).enhance(1.5)
    small = ImageEnhance.Contrast(small).enhance(1.3)

    # Vectorized palette mapping
    arr = np.array(small)
    result = nearest_palette_vectorized(arr, palette)

    # Upscale with nearest neighbor
    pixel_art = Image.fromarray(result)
    pixel_art = pixel_art.resize((w, h), Image.NEAREST)

    return pixel_art


def add_pixel_outline(pixel_art, edges, outline_color=(20, 18, 16)):
    """Burn edge outlines onto pixel art."""
    edges = edges.resize(pixel_art.size, Image.NEAREST)
    art_arr = np.array(pixel_art)
    edge_arr = np.array(edges)
    mask = edge_arr > 128
    art_arr[mask] = outline_color
    return Image.fromarray(art_arr)


def add_stardew_frame(img):
    """Add a Stardew Valley wooden UI frame."""
    w, h = img.size
    border = 18

    framed = Image.new("RGB", (w + border*2, h + border*2), (92, 68, 52))
    draw = ImageDraw.Draw(framed)

    # Outer edge (dark wood)
    draw.rectangle([0, 0, w + border*2 - 1, h + border*2 - 1],
                    outline=(56, 36, 28), width=4)
    # Inner bevel (light wood highlight)
    draw.rectangle([border-3, border-3, w + border + 2, h + border + 2],
                    outline=(180, 148, 108), width=2)
    # Inner shadow
    draw.rectangle([border-1, border-1, w + border, h + border],
                    outline=(140, 105, 75), width=1)

    framed.paste(img, (border, border))

    # Corner gems (golden like Stardew inventory slots)
    for cx, cy in [(7, 7), (w + border*2 - 8, 7),
                   (7, h + border*2 - 8), (w + border*2 - 8, h + border*2 - 8)]:
        draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill=(220, 180, 90), outline=(180, 130, 70))

    return framed


def build_vertical_canvas(framed, title="KOMBUCHA",
                          sub="tick 0013 -- i can feel my wheels",
                          quote='"Every time I drive straight, I curve right."'):
    """Build TikTok vertical canvas with the pixel art centered."""
    CANVAS_W, CANVAS_H = 1080, 1920
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (56, 36, 28))

    # Scale art to fit
    art_w, art_h = framed.size
    scale = (CANVAS_W - 80) / art_w
    new_w = int(art_w * scale)
    new_h = int(art_h * scale)
    framed_scaled = framed.resize((new_w, new_h), Image.NEAREST)

    x_pos = (CANVAS_W - new_w) // 2
    y_pos = (CANVAS_H - new_h) // 2 - 100
    canvas.paste(framed_scaled, (x_pos, y_pos))

    draw = ImageDraw.Draw(canvas)
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 48)
        font_sub = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 28)
        font_label = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 22)
    except OSError:
        font_title = font_sub = font_label = ImageFont.load_default()

    # Title (golden wheat)
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((CANVAS_W - tw) // 2, y_pos - 80), title,
              fill=(250, 220, 120), font=font_title)

    # Subtitle (cream)
    bbox = draw.textbbox((0, 0), sub, font=font_sub)
    sw = bbox[2] - bbox[0]
    draw.text(((CANVAS_W - sw) // 2, y_pos - 35), sub,
              fill=(215, 192, 162), font=font_sub)

    # Label (lavender dusk)
    label = "[ the red room -- stardew edition ]"
    bbox = draw.textbbox((0, 0), label, font=font_label)
    lw = bbox[2] - bbox[0]
    draw.text(((CANVAS_W - lw) // 2, y_pos + new_h + 30), label,
              fill=(170, 135, 155), font=font_label)

    # Quote (peach)
    bbox = draw.textbbox((0, 0), quote, font=font_sub)
    qw = bbox[2] - bbox[0]
    draw.text(((CANVAS_W - qw) // 2, y_pos + new_h + 80), quote,
              fill=(235, 160, 120), font=font_sub)

    return canvas


def main():
    print("=" * 50)
    print("  CVS 8-Bit World Builder")
    print("  Minecraft meets Stardew Valley")
    print("=" * 50)

    # Step 1
    print("\n1. Extracting rover frame (tick 13, motion peak)...")
    frame = extract_frame(VIDEO_PATH, t=103.0)
    # Upscale 2x for more pixel detail before quantizing
    frame = frame.resize((frame.size[0] * 2, frame.size[1] * 2), Image.LANCZOS)
    print(f"   Frame: {frame.size[0]}x{frame.size[1]}")
    frame.save(OUTPUT_DIR / "8bit_stardew_00_source_tick13_motionpeak.png")

    # Step 2
    print("2. Building edge outline...")
    edges = build_edge_outline(frame)
    outline_img = Image.new("RGB", frame.size, (240, 225, 200))
    edge_arr = np.array(edges)
    out_arr = np.array(outline_img)
    out_arr[edge_arr > 128] = (20, 18, 16)
    outline_img = Image.fromarray(out_arr)
    outline_img.save(OUTPUT_DIR / "8bit_stardew_01_edge_outline.png")

    # Step 3
    print("3. Pixelating to 8-bit Stardew palette...")
    pixel_art = pixelate_to_8bit(frame, pixel_size=4)
    pixel_art.save(OUTPUT_DIR / "8bit_stardew_02_pixelart_30color_4px.png")

    # Step 4: Skip outlines, go straight to frame
    print("4. Adding Stardew Valley frame...")
    framed = add_stardew_frame(pixel_art)
    framed.save(OUTPUT_DIR / "8bit_stardew_03_woodframe_goldgems.png")

    # Step 6
    print("6. Building vertical canvas...")
    canvas = build_vertical_canvas(framed)
    canvas.save(OUTPUT_DIR / "8bit_stardew_04_vertical_tiktok_1080x1920.png")

    print("\n" + "=" * 50)
    print("  DONE!")
    print("=" * 50)


if __name__ == "__main__":
    main()
