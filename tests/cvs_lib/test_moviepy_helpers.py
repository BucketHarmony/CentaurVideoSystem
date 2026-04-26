"""Tests for cvs_lib.moviepy_helpers (rotation cache invalidation).

We don't exercise the moviepy pipeline itself — that requires real
mp4 inputs. We do exercise the rotation cache, which is just a
disk-level mtime check around an ffmpeg subprocess.
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

from cvs_lib import moviepy_helpers


def test_rotation_baked_returns_source_when_no_rotation(tmp_path):
    """Rotation 0 (no metadata) → return the original path unchanged."""
    src = tmp_path / "input.mp4"
    src.write_bytes(b"x")
    cache = tmp_path / "rot_cache"
    with patch.object(moviepy_helpers, "get_rotation", return_value=0):
        out = moviepy_helpers.rotation_baked_path(src, cache_dir=cache)
    assert out == src
    # Cache dir is NOT created when no rotation work is needed.
    assert not cache.exists()


def test_rotation_baked_invalidates_when_source_newer(tmp_path):
    """If the source mtime is newer than the cache mtime, ffmpeg runs again."""
    src = tmp_path / "input.mp4"
    src.write_bytes(b"x")
    cache = tmp_path / "rot_cache"
    cache.mkdir()
    cached = cache / "input_rot.mp4"
    cached.write_bytes(b"old-baked")

    # Source is brand-new (now); cached file is OLD by 100 s.
    old = time.time() - 100
    os.utime(cached, (old, old))

    with patch.object(moviepy_helpers, "get_rotation", return_value=90), \
         patch("subprocess.run") as mock_run:
        out = moviepy_helpers.rotation_baked_path(src, cache_dir=cache)
    assert out == cached
    mock_run.assert_called_once()  # rebake happened


def test_rotation_baked_uses_cache_when_fresh(tmp_path):
    """Cached file with mtime ≥ source mtime → no ffmpeg call."""
    src = tmp_path / "input.mp4"
    src.write_bytes(b"x")
    cache = tmp_path / "rot_cache"
    cache.mkdir()
    cached = cache / "input_rot.mp4"
    cached.write_bytes(b"baked")

    # Bump the cached file's mtime past the source's.
    future = time.time() + 100
    os.utime(cached, (future, future))

    with patch.object(moviepy_helpers, "get_rotation", return_value=90), \
         patch("subprocess.run") as mock_run:
        out = moviepy_helpers.rotation_baked_path(src, cache_dir=cache)
    assert out == cached
    mock_run.assert_not_called()


def test_spec_well_falls_back_to_defaults():
    """spec_well returns defaults when keys are absent."""
    assert moviepy_helpers.spec_well({}, default_top=140, default_h=1610) == (140, 1610)


def test_spec_well_reads_per_beat_overrides():
    """spec_well honours well_top/well_h overrides on the spec."""
    spec = {"well_top": 720, "well_h": 1200}
    assert moviepy_helpers.spec_well(spec, default_top=140, default_h=1610) == (720, 1200)


def test_spec_well_reads_first_shot_in_list():
    """spec_well returns the first shot's well dims when given a list."""
    specs = [{"well_top": 100, "well_h": 200}, {"well_top": 999, "well_h": 999}]
    assert moviepy_helpers.spec_well(specs, default_top=140, default_h=1610) == (100, 200)
