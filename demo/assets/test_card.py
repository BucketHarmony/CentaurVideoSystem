"""
CVS Test Card Generator
Generates professional test card images for the Centaur Video System demo kit.
Requires: Pillow (pip install Pillow)
"""

import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# SMPTE-ish color bar palette
BAR_COLORS = [
    "#C0C0C0",  # white/silver
    "#C0C000",  # yellow
    "#00C0C0",  # cyan
    "#00C000",  # green
    "#C000C0",  # magenta
    "#C00000",  # red
    "#0000C0",  # blue
]

# Brand colors
BG_COLOR = "#0e0e1a"
PRIMARY = "#DC143C"
ACCENT = "#f0e68c"
SECONDARY = "#1a1a2e"
GRID_COLOR = "#2a2a3e"


def _best_font(size: int):
    """Try to load a clean sans-serif font, fall back to default."""
    candidates = [
        "arial.ttf",
        "ArialMT.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_test_card(width: int, height: int, output_path: str):
    """Generate a single test card PNG at the given resolution."""
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- subtle grid ---
    grid_step = 60
    for x in range(0, width, grid_step):
        draw.line([(x, 0), (x, height)], fill=GRID_COLOR, width=1)
    for y in range(0, height, grid_step):
        draw.line([(0, y), (width, y)], fill=GRID_COLOR, width=1)

    # --- color bars (top band) ---
    bar_top = int(height * 0.08)
    bar_bottom = int(height * 0.22)
    bar_w = width // len(BAR_COLORS)
    for i, color in enumerate(BAR_COLORS):
        x0 = i * bar_w
        x1 = (i + 1) * bar_w if i < len(BAR_COLORS) - 1 else width
        draw.rectangle([x0, bar_top, x1, bar_bottom], fill=color)

    # Thin accent line under bars
    draw.rectangle([0, bar_bottom, width, bar_bottom + 3], fill=PRIMARY)

    # --- center circle + crosshair ---
    cx, cy = width // 2, height // 2
    r = int(min(width, height) * 0.15)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=2)
    # crosshair
    ch = int(r * 0.6)
    draw.line([(cx - ch, cy), (cx + ch, cy)], fill=ACCENT, width=1)
    draw.line([(cx, cy - ch), (cx, cy + ch)], fill=ACCENT, width=1)

    # --- main title ---
    title_size = int(height * 0.09)
    font_title = _best_font(title_size)
    title = "CVS TEST CARD"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    title_y = int(height * 0.30)
    draw.text(((width - tw) // 2, title_y), title, fill="white", font=font_title)

    # --- resolution label ---
    info_size = int(height * 0.035)
    font_info = _best_font(info_size)
    res_label = f"{width} x {height}"
    bbox = draw.textbbox((0, 0), res_label, font=font_info)
    rw = bbox[2] - bbox[0]
    draw.text(((width - rw) // 2, title_y + th + int(height * 0.03)),
              res_label, fill=ACCENT, font=font_info)

    # --- timestamp ---
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_label = f"Generated: {ts}"
    bbox = draw.textbbox((0, 0), ts_label, font=font_info)
    tsw = bbox[2] - bbox[0]
    draw.text(((width - tsw) // 2, int(height * 0.55)),
              ts_label, fill="#888888", font=font_info)

    # --- bottom band with system info ---
    band_top = int(height * 0.82)
    band_bottom = int(height * 0.92)
    draw.rectangle([0, band_top, width, band_top + 3], fill=PRIMARY)
    draw.rectangle([0, band_top + 3, width, band_bottom], fill=SECONDARY)

    small_size = int(height * 0.025)
    font_small = _best_font(small_size)
    sys_text = "Centaur Video System  |  Demo Media Kit  |  github.com/your-org/cvs"
    bbox = draw.textbbox((0, 0), sys_text, font=font_small)
    sw = bbox[2] - bbox[0]
    text_y = band_top + 3 + (band_bottom - band_top - 3 - (bbox[3] - bbox[1])) // 2
    draw.text(((width - sw) // 2, text_y), sys_text, fill="#aaaaaa", font=font_small)

    # --- corner markers ---
    m = 20
    ml = 40
    for (ox, oy, dx, dy) in [
        (m, m, 1, 1),
        (width - m, m, -1, 1),
        (m, height - m, 1, -1),
        (width - m, height - m, -1, -1),
    ]:
        draw.line([(ox, oy), (ox + ml * dx, oy)], fill=PRIMARY, width=2)
        draw.line([(ox, oy), (ox, oy + ml * dy)], fill=PRIMARY, width=2)

    # --- safe area rectangle (90%) ---
    sx = int(width * 0.05)
    sy = int(height * 0.05)
    draw.rectangle([sx, sy, width - sx, height - sy], outline="#333344", width=1)

    img.save(output_path, "PNG")
    print(f"  Saved: {output_path}  ({width}x{height})")


def main():
    print("CVS Test Card Generator")
    print("=" * 40)

    generate_test_card(1280, 720, os.path.join(SCRIPT_DIR, "test_card_720p.png"))
    generate_test_card(1920, 1080, os.path.join(SCRIPT_DIR, "test_card_1080p.png"))

    print("\nDone. Test cards generated in:", SCRIPT_DIR)


if __name__ == "__main__":
    main()
