"""Tests for cvs_lib.image_filters.

Verifies API contract + variant-kwarg behaviour + reasonable output
ranges. Doesn't test pixel-exact values against a frozen baseline —
the canonical implementation IS the spec, and Phase 1 sign-off
established the visual contract.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from cvs_lib import image_filters as ifx


@pytest.fixture
def src() -> Image.Image:
    """A small RGB image with reds, oranges, and neutrals — enough to
    exercise both red and orange masks in cottagecore_grade."""
    rng = np.random.default_rng(seed=42)
    arr = np.full((128, 128, 3), 100, dtype=np.uint8)
    arr[:64, :64] = (200, 60, 60)      # red square (triggers red mask)
    arr[:64, 64:] = (210, 130, 50)     # orange square (triggers orange mask)
    arr[64:, :] = (100, 110, 130)      # neutral lower half
    # Add tiny noise so the result isn't suspicious flat.
    noise = rng.integers(-5, 5, size=arr.shape, dtype=np.int8)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def test_cottagecore_grade_cool_runs(src):
    out = ifx.cottagecore_grade(src, variant="cool")
    assert out.size == src.size
    assert out.mode == "RGB"


def test_cottagecore_grade_warm_runs(src):
    out = ifx.cottagecore_grade(src, variant="warm")
    assert out.size == src.size
    assert out.mode == "RGB"


def test_cottagecore_grade_default_is_cool(src):
    """Default kwarg must be 'cool' — most cc_flora episodes (5–10) are cool."""
    a = ifx.cottagecore_grade(src)
    b = ifx.cottagecore_grade(src, variant="cool")
    assert np.array_equal(np.array(a), np.array(b))


def test_cottagecore_grade_variants_differ(src):
    """Cool and warm must produce visibly different output."""
    cool = np.array(ifx.cottagecore_grade(src, variant="cool"), dtype=np.float32)
    warm = np.array(ifx.cottagecore_grade(src, variant="warm"), dtype=np.float32)
    mean_diff = float(np.abs(cool - warm).mean())
    assert mean_diff > 5.0, f"cool and warm too similar: mean abs diff = {mean_diff:.2f}"


def test_cottagecore_grade_warm_brighter_than_cool(src):
    """Warm variant lifts shadows + brightness 1.08; cool drops to 0.92.
    Mean luminance must be higher for warm."""
    cool = np.array(ifx.cottagecore_grade(src, variant="cool"), dtype=np.float32).mean()
    warm = np.array(ifx.cottagecore_grade(src, variant="warm"), dtype=np.float32).mean()
    assert warm > cool


def test_cottagecore_grade_rejects_bad_variant(src):
    with pytest.raises(ValueError, match="unknown variant"):
        ifx.cottagecore_grade(src, variant="bogus")


def test_soft_bloom_default_strength_is_subtle(src):
    """Default 0.05 must produce a bloomed-but-recognizable result."""
    out = np.array(ifx.soft_bloom(src), dtype=np.float32)
    src_arr = np.array(src, dtype=np.float32)
    diff = float(np.abs(out - src_arr).mean())
    assert 0.5 < diff < 30.0, f"unexpected bloom magnitude: {diff:.2f}"


def test_soft_bloom_strength_scales_effect(src):
    """Stronger bloom → larger deviation from source."""
    src_arr = np.array(src, dtype=np.float32)
    light = np.array(ifx.soft_bloom(src, strength=0.05), dtype=np.float32)
    heavy = np.array(ifx.soft_bloom(src, strength=0.20), dtype=np.float32)
    light_dev = float(np.abs(light - src_arr).mean())
    heavy_dev = float(np.abs(heavy - src_arr).mean())
    assert heavy_dev > light_dev


def test_creamy_vignette_cool_default_strength(src):
    """When strength=None and variant=cool, default is 0.55."""
    a = ifx.creamy_vignette(src, variant="cool")
    b = ifx.creamy_vignette(src, strength=0.55, variant="cool")
    assert np.array_equal(np.array(a), np.array(b))


def test_creamy_vignette_warm_default_strength(src):
    """When strength=None and variant=warm, default is 0.28."""
    a = ifx.creamy_vignette(src, variant="warm")
    b = ifx.creamy_vignette(src, strength=0.28, variant="warm")
    assert np.array_equal(np.array(a), np.array(b))


def test_creamy_vignette_corners_darker_than_center_cool(src):
    """Cool variant tints toward shadow — corners should be darker."""
    out = np.array(ifx.creamy_vignette(src, variant="cool"))
    h, w = out.shape[:2]
    corners = np.concatenate([
        out[:8, :8].reshape(-1, 3),
        out[:8, -8:].reshape(-1, 3),
        out[-8:, :8].reshape(-1, 3),
        out[-8:, -8:].reshape(-1, 3),
    ]).mean(axis=0).mean()
    center = out[h // 2 - 4:h // 2 + 4, w // 2 - 4:w // 2 + 4].mean()
    assert corners < center


def test_creamy_vignette_corners_lighter_than_center_warm(src):
    """Warm variant tints toward CREAM (250,245,239) — corners
    should be brighter than center for a mid-luminance source."""
    # Use a deliberately darker source so cream tint is unambiguous.
    dark = Image.new("RGB", (128, 128), (60, 70, 80))
    out = np.array(ifx.creamy_vignette(dark, variant="warm"))
    h, w = out.shape[:2]
    corners = np.concatenate([
        out[:8, :8].reshape(-1, 3),
        out[:8, -8:].reshape(-1, 3),
        out[-8:, :8].reshape(-1, 3),
        out[-8:, -8:].reshape(-1, 3),
    ]).mean(axis=0).mean()
    center = out[h // 2 - 4:h // 2 + 4, w // 2 - 4:w // 2 + 4].mean()
    assert corners > center


def test_creamy_vignette_rejects_bad_variant(src):
    with pytest.raises(ValueError, match="unknown variant"):
        ifx.creamy_vignette(src, variant="bogus")


def test_hookshot_cottagecore_grade_runs(src):
    out = ifx.hookshot_cottagecore_grade(src)
    assert out.size == src.size
    assert out.mode == "RGB"


def test_hookshot_grade_differs_from_cool(src):
    """The hookshot grade has no red/orange masking; output must
    differ from the cool cc_flora grade."""
    a = np.array(ifx.cottagecore_grade(src, variant="cool"), dtype=np.float32)
    b = np.array(ifx.hookshot_cottagecore_grade(src), dtype=np.float32)
    assert float(np.abs(a - b).mean()) > 1.0


def test_hookshot_soft_bloom_runs(src):
    out = ifx.hookshot_soft_bloom(src)
    assert out.size == src.size


def test_hookshot_vignette_corners_darker(src):
    out = np.array(ifx.hookshot_vignette(src))
    h, w = out.shape[:2]
    corners = np.concatenate([
        out[:8, :8].reshape(-1, 3),
        out[:8, -8:].reshape(-1, 3),
        out[-8:, :8].reshape(-1, 3),
        out[-8:, -8:].reshape(-1, 3),
    ]).mean(axis=0).mean()
    center = out[h // 2 - 4:h // 2 + 4, w // 2 - 4:w // 2 + 4].mean()
    assert corners < center
