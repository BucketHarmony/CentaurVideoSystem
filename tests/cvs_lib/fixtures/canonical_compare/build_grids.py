"""Phase 1 sign-off grid builder for cc_flora canonical filters.

Runs current vs canonical filter chains against a shared input image
and saves side-by-side grids. The user reviews these visually to
sign off (or veto) the canonical pick before extraction proceeds.

The "current" filter bodies for ep01, ep02, ep10, and cc_hookshot are
copied verbatim from those scripts as of 2026-04-26. They are NOT
re-imported from the live scripts (which would pull in heavy module
state). If a target script is edited between Phase 0 and Phase 3,
re-run this builder to refresh the grids.

Output:
    tests/cvs_lib/fixtures/canonical_compare/
        grid_ep10_cool.png    (sanity: ep10 current vs canonical-cool)
        grid_ep02_warm.png    (sanity: ep02 current vs canonical-warm)
        grid_ep01_warm.png    (REAL question: ep01 current vs canonical-warm)
        grid_hookshot.png     (cc_hookshot current vs canonical hookshot)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
import draft_filters as canon  # noqa: E402

CREAM = (250, 245, 239)
INPUT_IMAGE = Path(
    "E:/AI/CVS/ComfyUI/output/projects/cc_flora/stills/"
    "cc_flora_ep05_test_frame_v6.png"
)
OUT_DIR = THIS_DIR


# ---------- vendored "current" filter bodies (verbatim from scripts) ----------


def ep10_cottagecore_grade(img):
    """Verbatim from cc_flora_ep10_the_patience_of_rooms.py L123."""
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
    arr[:, :, 0] *= 1.03
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.91
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.75)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    return img


def ep10_soft_bloom(img, strength=0.05):
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def ep10_creamy_vignette(img, strength=0.55):
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


def ep02_cottagecore_grade(img):
    """Verbatim from cc_flora_ep02_bigger_room.py L132."""
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
    arr = np.clip(arr + 20, 0, 255)
    arr = 128 + (arr - 128) * 0.78
    arr[:, :, 0] *= 1.03
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.93
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.70)
    img = ImageEnhance.Brightness(img).enhance(1.08)
    return img


def ep02_soft_bloom(img, strength=0.12):
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def ep02_creamy_vignette(img, strength=0.28):
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vig = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
    vig = vig[:, :, np.newaxis] * strength
    arr = arr * (1 - vig) + np.array(CREAM, dtype=np.float32) * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def ep01_cottagecore_grade(img):
    """Verbatim from cc_flora_ep01_first_light.py L103."""
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    red_mask = (r > 100) & (r > g * 1.3) & (r > b * 1.3)
    red_strength = np.clip((r - np.maximum(g, b)) / 100.0, 0, 1)
    red_strength *= red_mask.astype(np.float32)
    target_r, target_g, target_b = 210, 175, 175
    arr[:, :, 0] = r * (1 - red_strength * 0.5) + target_r * red_strength * 0.5
    arr[:, :, 1] = g * (1 - red_strength * 0.4) + target_g * red_strength * 0.4
    arr[:, :, 2] = b * (1 - red_strength * 0.3) + target_b * red_strength * 0.3
    shadow_lift = 25
    arr = arr + shadow_lift
    arr = np.clip(arr, 0, 255)
    midpoint = 128
    arr = midpoint + (arr - midpoint) * 0.82
    arr[:, :, 0] = arr[:, :, 0] * 1.03
    arr[:, :, 1] = arr[:, :, 1] * 1.01
    arr[:, :, 2] = arr[:, :, 2] * 0.95
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.75)
    img = ImageEnhance.Brightness(img).enhance(1.06)
    return img


def ep01_creamy_vignette(img, strength=0.3):
    """Verbatim from cc_flora_ep01_first_light.py L150."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    normalized = dist / max_dist
    vignette = np.clip((normalized - 0.4) / 0.6, 0, 1) ** 1.5
    vignette = vignette[:, :, np.newaxis] * strength
    cream = np.array(CREAM, dtype=np.float32)
    arr = arr * (1 - vignette) + cream * vignette
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


# ep01 uses ep02-style soft_bloom (verified: same body, strength=0.12)
ep01_soft_bloom = ep02_soft_bloom


def hookshot_cottagecore_grade(img):
    """Verbatim from cc_hookshot.py L183."""
    arr = np.array(img, dtype=np.float32)
    arr = 128 + (arr - 128) * 0.92
    arr[:, :, 0] *= 1.04
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.91
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    return img


def hookshot_soft_bloom(img, radius=15, blend=0.05):
    return Image.blend(img, img.filter(ImageFilter.GaussianBlur(radius)), blend)


def hookshot_vignette(img, strength=0.55):
    w, h = img.size
    arr = np.array(img, dtype=np.float32) / 255.0
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2) / math.sqrt(
        (w / 2) ** 2 + (h / 2) ** 2
    )
    mask = (np.clip((dist - 0.25) / 0.75, 0, 1) ** 2 * strength)[:, :, np.newaxis]
    tint = np.array([55, 48, 42], dtype=np.float32) / 255.0
    arr = arr * (1 - mask) + tint * mask
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


# ---------- grid builder ----------


def _try_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _abs_diff(a: Image.Image, b: Image.Image) -> Image.Image:
    """Visualize per-pixel absolute difference, scaled to be visible."""
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    diff = np.abs(arr_a - arr_b)
    # Amplify so subtle drifts show up
    diff = np.clip(diff * 4, 0, 255).astype(np.uint8)
    return Image.fromarray(diff)


def make_grid(
    title: str,
    input_img: Image.Image,
    current_chain,
    canonical_chain,
    out_path: Path,
    thumb_w: int = 540,
):
    cur = current_chain(input_img)
    can = canonical_chain(input_img)
    diff = _abs_diff(cur, can)

    # Resize each panel to thumb_w preserving aspect.
    def _thumb(im: Image.Image) -> Image.Image:
        w, h = im.size
        new_h = int(h * thumb_w / w)
        return im.resize((thumb_w, new_h), Image.LANCZOS)

    panels = {
        "input": _thumb(input_img),
        "current": _thumb(cur),
        "canonical": _thumb(can),
        "abs_diff (×4)": _thumb(diff),
    }
    panel_h = panels["input"].height
    pad = 16
    label_h = 36
    title_h = 56
    grid_w = thumb_w * 4 + pad * 5
    grid_h = title_h + label_h + panel_h + pad * 3

    grid = Image.new("RGB", (grid_w, grid_h), (240, 240, 240))
    draw = ImageDraw.Draw(grid)
    title_font = _try_font(28)
    label_font = _try_font(20)
    draw.text((pad, pad), title, fill=(20, 20, 20), font=title_font)

    x = pad
    y_panel = title_h + label_h + pad
    for name, panel in panels.items():
        draw.text((x, title_h + pad), name, fill=(60, 60, 60), font=label_font)
        grid.paste(panel, (x, y_panel))
        x += thumb_w + pad

    grid.save(out_path)
    print(f"wrote {out_path.name}  ({cur.size[0]}x{cur.size[1]} per panel)")


def chain(*fns):
    def _run(img):
        for fn in fns:
            img = fn(img)
        return img
    return _run


def main():
    if not INPUT_IMAGE.exists():
        sys.exit(f"input image not found: {INPUT_IMAGE}")
    src = Image.open(INPUT_IMAGE).convert("RGB")
    print(f"input: {INPUT_IMAGE.name}  {src.size}")

    make_grid(
        "ep10 current  vs  canonical(variant=cool)  — should be IDENTICAL",
        src,
        chain(ep10_cottagecore_grade, ep10_soft_bloom, ep10_creamy_vignette),
        chain(
            lambda im: canon.cottagecore_grade(im, variant="cool"),
            lambda im: canon.soft_bloom(im, strength=0.05),
            lambda im: canon.creamy_vignette(im, variant="cool"),
        ),
        OUT_DIR / "grid_ep10_cool.png",
    )

    make_grid(
        "ep02 current  vs  canonical(variant=warm)  — should be IDENTICAL",
        src,
        chain(ep02_cottagecore_grade, ep02_soft_bloom, ep02_creamy_vignette),
        chain(
            lambda im: canon.cottagecore_grade(im, variant="warm"),
            lambda im: canon.soft_bloom(im, strength=0.12),
            lambda im: canon.creamy_vignette(im, variant="warm"),
        ),
        OUT_DIR / "grid_ep02_warm.png",
    )

    make_grid(
        "ep01 current  vs  canonical(variant=warm)  — REAL DECISION",
        src,
        chain(ep01_cottagecore_grade, ep01_soft_bloom, ep01_creamy_vignette),
        chain(
            lambda im: canon.cottagecore_grade(im, variant="warm"),
            lambda im: canon.soft_bloom(im, strength=0.12),
            lambda im: canon.creamy_vignette(im, variant="warm"),
        ),
        OUT_DIR / "grid_ep01_warm.png",
    )

    make_grid(
        "cc_hookshot current  vs  canonical hookshot family",
        src,
        chain(hookshot_cottagecore_grade, hookshot_soft_bloom, hookshot_vignette),
        chain(
            canon.hookshot_cottagecore_grade,
            canon.hookshot_soft_bloom,
            canon.hookshot_vignette,
        ),
        OUT_DIR / "grid_hookshot.png",
    )


if __name__ == "__main__":
    main()
