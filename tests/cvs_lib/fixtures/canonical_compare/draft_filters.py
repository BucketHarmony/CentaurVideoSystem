"""Phase 1 draft of cvs_lib/image_filters.py.

This is NOT yet the production module — it lives here for sign-off
review only. The production module lands in Phase 3 at
cvs_lib/image_filters.py with the same API.

Design (from cvs_lib/_drift_audit.md):
- cottagecore_grade(img, variant="cool"|"warm")
  - "cool" (default) = ep10 body, used by ep05–ep10
  - "warm" = ep02 body, used by ep02–ep04 + cc_flora_30s + cc_flora_masterpiece + dream_sequence
  - ep01 deliberately migrates to "warm" (drops its outlier params)
- soft_bloom(img, strength=0.05) — single body; warm callers pass 0.12
- creamy_vignette(img, strength=None, variant="cool"|"warm")
  - strength defaults to 0.55 (cool) or 0.28 (warm) when None
- hookshot_cottagecore_grade(img) — sibling for cc_hookshot family
- hookshot_soft_bloom(img, radius=15, blend=0.05) — Image.blend variant
- hookshot_vignette(img, strength=0.55) — normalized-distance variant
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


CREAM = (250, 245, 239)
SHADOW_TINT = (55, 48, 42)


def cottagecore_grade(img: Image.Image, variant: str = "cool") -> Image.Image:
    """cc_flora cottagecore color grade.

    "cool" (ep10): no shadow lift, 0.92 compression, slight blue pull,
    saturation 0.75, brightness 0.92, contrast 1.12. Cooler/cleaner.

    "warm" (ep02): +20 shadow lift, 0.78 compression, blue pull 0.93,
    saturation 0.70, brightness 1.08, no contrast call. Warmer/softer.
    """
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
    arr[:, :, 1] = arr[:, :, 1] * (1 - orange_str * 0.10) + 195 * orange_str * 0.10

    if variant == "warm":
        arr = np.clip(arr + 20, 0, 255)
        arr = 128 + (arr - 128) * 0.78
        arr[:, :, 0] *= 1.03
        arr[:, :, 1] *= 1.01
        arr[:, :, 2] *= 0.93
    elif variant == "cool":
        arr = 128 + (arr - 128) * 0.92
        arr[:, :, 0] *= 1.03
        arr[:, :, 1] *= 1.01
        arr[:, :, 2] *= 0.91
    else:
        raise ValueError(f"unknown variant: {variant!r}")

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr)

    if variant == "warm":
        out = ImageEnhance.Color(out).enhance(0.70)
        out = ImageEnhance.Brightness(out).enhance(1.08)
    else:
        out = ImageEnhance.Color(out).enhance(0.75)
        out = ImageEnhance.Brightness(out).enhance(0.92)
        out = ImageEnhance.Contrast(out).enhance(1.12)
    return out


def soft_bloom(img: Image.Image, strength: float = 0.05) -> Image.Image:
    """cc_flora soft bloom (numpy additive).

    Defaults to ep10's strength=0.05 (cool/light bloom). Warm callers
    pass strength=0.12.
    """
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32) + np.array(bloom, dtype=np.float32) * strength
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def creamy_vignette(
    img: Image.Image,
    strength: float | None = None,
    variant: str = "cool",
) -> Image.Image:
    """Radial vignette toward shadow ("cool") or cream ("warm").

    "cool" (ep10): shadow tint (55,48,42), gradient 0.25/0.55, exp 1.4,
    default strength 0.55.

    "warm" (ep02): CREAM (250,245,239), gradient 0.35/0.65, exp 1.8,
    default strength 0.28.
    """
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)

    if variant == "warm":
        if strength is None:
            strength = 0.28
        vig = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
        tint = np.array(CREAM, dtype=np.float32)
    elif variant == "cool":
        if strength is None:
            strength = 0.55
        vig = np.clip((dist / max_dist - 0.25) / 0.55, 0, 1) ** 1.4
        tint = np.array(SHADOW_TINT, dtype=np.float32)
    else:
        raise ValueError(f"unknown variant: {variant!r}")

    vig = vig[:, :, np.newaxis] * strength
    arr = arr * (1 - vig) + tint * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def hookshot_cottagecore_grade(img: Image.Image) -> Image.Image:
    """Minimalist grade used by cc_hookshot family (and minimalist
    midnight variants). Just range compression + warm/blue shift +
    contrast/brightness. No red/orange masking."""
    arr = np.array(img, dtype=np.float32)
    arr = 128 + (arr - 128) * 0.92
    arr[:, :, 0] *= 1.04
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.91
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr)
    out = ImageEnhance.Contrast(out).enhance(1.12)
    out = ImageEnhance.Brightness(out).enhance(0.92)
    return out


def hookshot_soft_bloom(
    img: Image.Image, radius: int = 15, blend: float = 0.05,
) -> Image.Image:
    """Image.blend bloom used by cc_hookshot family."""
    return Image.blend(img, img.filter(ImageFilter.GaussianBlur(radius)), blend)


def hookshot_vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    """Normalized-distance vignette used by cc_hookshot family.

    Different formula from creamy_vignette: works in 0–1 float space,
    gradient 0.25/0.75, exponent 2, shadow tint."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32) / 255.0
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2) / math.sqrt(
        (w / 2) ** 2 + (h / 2) ** 2
    )
    mask = (np.clip((dist - 0.25) / 0.75, 0, 1) ** 2 * strength)[:, :, np.newaxis]
    tint = np.array(SHADOW_TINT, dtype=np.float32) / 255.0
    arr = arr * (1 - mask) + tint * mask
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
