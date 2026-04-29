"""Build contact sheets of all stills, split into halves for legibility."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SRC = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
OUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc/_still_picks")
OUT_DIR.mkdir(parents=True, exist_ok=True)

stills = sorted(SRC.glob("*.jpg"))
print(f"{len(stills)} stills")

cols = 5
cell_w, cell_h = 480, 360
label_h = 30
half = (len(stills) + 1) // 2

try:
    fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
except OSError:
    fnt = ImageFont.load_default()

for half_idx, group in enumerate([stills[:half], stills[half:]]):
    rows = (len(group) + cols - 1) // cols
    sheet_w = cols * cell_w
    sheet_h = rows * (cell_h + label_h)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    base_idx = half_idx * half
    for j, p in enumerate(group):
        i = base_idx + j
        r, c = divmod(j, cols)
        x, y = c * cell_w, r * (cell_h + label_h)
        try:
            im = Image.open(p).convert("RGB")
        except Exception as e:
            print(f"skip {p.name}: {e}")
            continue
        im.thumbnail((cell_w - 6, cell_h - 6), Image.LANCZOS)
        ox = x + (cell_w - im.width) // 2
        oy = y + (cell_h - im.height) // 2
        sheet.paste(im, (ox, oy))
        label = f"#{i:02d}  {p.stem.split('_')[-1]}"
        draw.text((x + 8, y + cell_h + 4), label, font=fnt, fill=(230, 230, 230))
    out = OUT_DIR / f"contact_{'A' if half_idx == 0 else 'B'}.jpg"
    sheet.save(out, quality=88)
    print(f"wrote {out} ({sheet.size})")
