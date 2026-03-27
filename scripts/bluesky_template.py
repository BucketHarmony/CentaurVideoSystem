#!/usr/bin/env python3
"""
CVS -- Bluesky Square Template
1024x1024 cottagecore with dark accent.
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
FONT_CONSOLA = os.getenv("FONT_CONSOLA", "C:/Windows/Fonts/consola.ttf")

SQ = 1024

# Dark cottagecore palette
BG_DARK = (18, 14, 12)          # near-black warm
BORDER_DARK = (32, 26, 22)      # dark walnut
BORDER_MID = (58, 48, 40)       # espresso
ACCENT_DARK = (42, 32, 28)      # dark roast
CREAM = (240, 228, 210)
LINEN = (225, 215, 198)
MUTED = (165, 148, 130)
DUSTY_ROSE = (185, 140, 135)
HONEY = (200, 165, 90)
SAGE = (120, 140, 110)


def extract_frame(video_path, t=103.0):
    clip = VideoFileClip(str(video_path))
    t = min(t, clip.duration - 0.05)
    frame = Image.fromarray(clip.get_frame(t))
    clip.close()
    return frame


def upscale_4x(img):
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


def cottagecore_grade(img):
    """Warm cottagecore color grade."""
    arr = np.array(img, dtype=np.float32)
    # Lift shadows
    arr = arr + 12
    # Compress range (softer)
    arr = 128 + (arr - 128) * 0.82
    # Warm shift
    arr[:, :, 0] *= 1.04
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.92
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.75)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    return img


def build_template(frame_img, tick_num=13, mood="awake",
                   quote='"Every time I drive straight, I curve right."',
                   episode_title="i can feel my wheels"):

    canvas = Image.new("RGB", (SQ, SQ), BG_DARK)
    draw = ImageDraw.Draw(canvas)

    # -- Outer border line (thin, dark walnut) --
    margin = 24
    draw.rectangle([margin, margin, SQ - margin - 1, SQ - margin - 1],
                   outline=BORDER_MID, width=1)

    # -- Inner content area --
    inner_margin = 40

    # -- Image area: top portion --
    img_top = 85
    img_bottom = 660
    img_left = inner_margin
    img_right = SQ - inner_margin
    img_w = img_right - img_left
    img_h = img_bottom - img_top

    # Grade and fit the frame
    graded = cottagecore_grade(frame_img)
    fw, fh = graded.size
    scale = max(img_w / fw, img_h / fh)
    new_w = int(fw * scale)
    new_h = int(fh * scale)
    graded = graded.resize((new_w, new_h), Image.LANCZOS)
    # Center crop to fit
    cx = (new_w - img_w) // 2
    cy = (new_h - img_h) // 2
    cropped = graded.crop((cx, cy, cx + img_w, cy + img_h))

    # Soft bloom on the image
    bloom = cropped.filter(ImageFilter.GaussianBlur(radius=30))
    c_arr = np.array(cropped, dtype=np.float32)
    b_arr = np.array(bloom, dtype=np.float32)
    c_arr = c_arr + b_arr * 0.08
    cropped = Image.fromarray(np.clip(c_arr, 0, 255).astype(np.uint8))

    # Vignette on image
    varr = np.array(cropped, dtype=np.float32)
    Y, X = np.ogrid[:img_h, :img_w]
    dist = np.sqrt((X - img_w/2)**2 + (Y - img_h/2)**2)
    max_dist = np.sqrt((img_w/2)**2 + (img_h/2)**2)
    vig = np.clip((dist / max_dist - 0.4) / 0.6, 0, 1) ** 2
    vig = vig[:, :, np.newaxis] * 0.5
    dark = np.array(BG_DARK, dtype=np.float32)
    varr = varr * (1 - vig) + dark * vig
    cropped = Image.fromarray(np.clip(varr, 0, 255).astype(np.uint8))

    canvas.paste(cropped, (img_left, img_top))

    # -- Thin line under image --
    line_y = img_bottom + 16
    draw.line([(inner_margin + 60, line_y), (SQ - inner_margin - 60, line_y)],
              fill=BORDER_MID, width=1)

    # -- Fonts --
    try:
        font_title = ImageFont.truetype(FONT_SERIF, 38)
        font_episode = ImageFont.truetype(FONT_SERIF_ITALIC, 30)
        font_quote = ImageFont.truetype(FONT_SERIF_ITALIC, 30)
        font_tick = ImageFont.truetype(FONT_CONSOLA, 28)
        font_mood = ImageFont.truetype(FONT_CONSOLA, 29)
    except OSError:
        font_title = font_episode = font_quote = font_tick = font_mood = ImageFont.load_default()

    # -- Title: "kombucha" top center --
    title = "kombucha"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((SQ - tw) // 2, 38), title, fill=CREAM, font=font_title)

    # -- Tick badge: top left corner --
    tick_text = f"tick {tick_num:04d}"
    draw.text((inner_margin + 8, img_top + 12), tick_text,
              fill=MUTED, font=font_tick)

    # -- Mood badge: top right --
    mood_text = mood.upper()
    bbox = draw.textbbox((0, 0), mood_text, font=font_mood)
    mw = bbox[2] - bbox[0]
    mx = SQ - inner_margin - mw - 16
    my = img_top + 12
    pad = 12
    draw.rounded_rectangle([mx - pad, my - pad//2, mx + mw + pad, my + (bbox[3]-bbox[1]) + pad//2],
                           radius=4, fill=ACCENT_DARK + (180,))
    draw.text((mx, my), mood_text, fill=DUSTY_ROSE, font=font_mood)

    # -- Episode title --
    bbox = draw.textbbox((0, 0), episode_title, font=font_episode)
    ew = bbox[2] - bbox[0]
    draw.text(((SQ - ew) // 2, line_y + 40), episode_title,
              fill=DUSTY_ROSE, font=font_episode)

    # -- Quote --
    bbox = draw.textbbox((0, 0), quote, font=font_quote)
    qw = bbox[2] - bbox[0]
    # Wrap if needed
    if qw > SQ - inner_margin * 2 - 40:
        words = quote.split()
        lines = []
        current = ""
        for w in words:
            test = f"{current} {w}" if current else w
            tb = draw.textbbox((0, 0), test, font=font_quote)
            if tb[2] - tb[0] > SQ - inner_margin * 2 - 40:
                lines.append(current)
                current = w
            else:
                current = test
        if current:
            lines.append(current)
    else:
        lines = [quote]

    quote_y = line_y + 100
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_quote)
        lw = bbox[2] - bbox[0]
        draw.text(((SQ - lw) // 2, quote_y), line, fill=MUTED, font=font_quote)
        quote_y += 50

    # -- Decorative dots (sage green, subtle) --
    dot_y = SQ - margin - 12
    center_x = SQ // 2
    for dx in [-28, 0, 28]:
        draw.ellipse([center_x + dx - 4, dot_y - 4, center_x + dx + 4, dot_y + 4],
                     fill=SAGE)

    return canvas


def main():
    print("=" * 50)
    print("  CVS Bluesky Template")
    print("  1024x1024 dark cottagecore")
    print("=" * 50)

    print("\n1. Extracting frame...")
    frame = extract_frame(VIDEO_PATH, t=103.0)

    print("2. Upscaling 4x...")
    hires = upscale_4x(frame)
    print(f"   {hires.size[0]}x{hires.size[1]}")

    print("3. Building template...")
    result = build_template(
        hires,
        tick_num=13,
        mood="awake",
        quote='"Every time I drive straight, I curve right."',
        episode_title="i can feel my wheels",
    )
    out = OUTPUT_DIR / "bluesky_dark_cottagecore_tick0013_1024sq.png"
    result.save(out)
    print(f"   Saved: {out}")

    # Also do tick 10 for variety
    print("\n4. Building tick 10 variant...")
    frame10 = extract_frame(Path(os.getenv("KOMBUCHA_DIR", "")) / "video" / "web" / "tick_0010.mp4", t=50.0)
    hires10 = upscale_4x(frame10)
    result10 = build_template(
        hires10,
        tick_num=10,
        mood="liberated",
        quote='"The Charmin package has become a kind of north star."',
        episode_title="north star",
    )
    out10 = OUTPUT_DIR / "bluesky_dark_cottagecore_tick0010_1024sq.png"
    result10.save(out10)
    print(f"   Saved: {out10}")

    print("\n" + "=" * 50)
    print("  DONE!")
    print("=" * 50)


if __name__ == "__main__":
    main()
