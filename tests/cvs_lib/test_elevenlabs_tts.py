"""Tests for cvs_lib.elevenlabs_tts.

Covers TTS cache hit/miss (the only behaviour that changes the disk —
HTTP failures and decoding live downstream), and measure_tts_duration
edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cvs_lib import elevenlabs_tts


def test_generate_tts_cache_hit_skips_http(tmp_path):
    """A pre-existing cache file means generate_tts returns True without
    touching requests."""
    cache_path = tmp_path / "x_hook.mp3"
    cache_path.write_bytes(b"already here")
    with patch("requests.post") as mock_post:
        ok = elevenlabs_tts.generate_tts(
            text="hi", api_key="k", voice_id="v",
            cache_path=cache_path,
        )
    assert ok is True
    mock_post.assert_not_called()
    assert cache_path.read_bytes() == b"already here"  # untouched


def test_generate_tts_cache_miss_writes_response_bytes(tmp_path):
    """A cache miss calls the API and writes the response body to disk."""
    cache_path = tmp_path / "x_hook.mp3"
    fake_resp = MagicMock(status_code=200, content=b"\xff\xfb\x90fake-mp3")
    with patch("requests.post", return_value=fake_resp) as mock_post:
        ok = elevenlabs_tts.generate_tts(
            text="hi", api_key="k", voice_id="v",
            cache_path=cache_path,
        )
    assert ok is True
    mock_post.assert_called_once()
    assert cache_path.read_bytes() == b"\xff\xfb\x90fake-mp3"


def test_generate_tts_http_failure_returns_false(tmp_path):
    """A non-200 response leaves no cache file and returns False."""
    cache_path = tmp_path / "x_hook.mp3"
    fake_resp = MagicMock(status_code=429, text="rate limited")
    with patch("requests.post", return_value=fake_resp):
        ok = elevenlabs_tts.generate_tts(
            text="hi", api_key="k", voice_id="v",
            cache_path=cache_path,
        )
    assert ok is False
    assert not cache_path.exists()


def test_measure_tts_duration_missing_file_returns_zero(tmp_path):
    """No cached MP3 → 0.0, not an exception."""
    dur = elevenlabs_tts.measure_tts_duration(
        "missing", cache_dir=tmp_path, cache_prefix="x")
    assert dur == 0.0


def test_synthesize_narration_no_api_key_returns_none(tmp_path):
    """Without an API key the function returns None silently."""
    track = elevenlabs_tts.synthesize_narration(
        env={},
        narration_lines=[{"slug": "a", "start_in_beat": 0.0, "text": "hi"}],
        cache_dir=tmp_path, cache_prefix="x",
        duration=5.0, scene_start=lambda s: 0.0,
    )
    assert track is None
