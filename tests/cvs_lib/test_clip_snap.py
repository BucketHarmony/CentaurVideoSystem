"""Tests for cvs_lib.clip_snap — silence-aware boundary refinement.

Uses real audio in `raw/MPC/Ice Out Romulus/`. Slow-ish (~5s for the
silero model load on first call) but pins the actual snap behavior, not
a mock. Module-scoped audio cache so subsequent tests share the load.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from cvs_lib import clip_snap
from cvs_lib.clip_snap import (
    BoundarySnap, SnapResult,
    _NO_SILENCE_DB, _PAD_RMS_RISE_DB, _VAD_SR,
    _last_rms_rise, _next_rms_rise, _rms_db, _rms_frame_db,
    _snap_to_zero_crossing,
    snap_boundaries,
)

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
SPEECH_PATH = RAW_DIR / "20260425_153128.mp4"   # NBCM coalition speech
CHANT_PATH = RAW_DIR / "20260425_170030.mp4"    # "abolish ICE" repeated


@pytest.fixture(autouse=True, scope="module")
def _share_audio_cache():
    """Don't clear between tests — silero model load is the slow part."""
    yield
    clip_snap.clear_cache()


# --------------------------- low-level helpers --------------------------- #

def test_rms_db_silence_is_floored():
    silent = np.zeros(1000, dtype=np.float32)
    assert _rms_db(silent) == -120.0


def test_rms_db_full_scale_is_zero():
    # Pure +1.0 has RMS = 1.0 = 0 dBFS.
    full = np.ones(1000, dtype=np.float32)
    assert -0.01 < _rms_db(full) < 0.01


def test_rms_frame_db_window_centered_on_t():
    # 16 kHz mono with energy only in [0.4s, 0.6s] should report
    # high RMS at t=0.5 and -120 dB at t=2.0.
    n = 16000 * 2
    a = np.zeros(n, dtype=np.float32)
    a[16000 * 4 // 10 : 16000 * 6 // 10] = 0.5
    assert _rms_frame_db(a, 0.5, 16000) > -10.0
    assert _rms_frame_db(a, 1.5, 16000) == -120.0


def test_snap_to_zero_crossing_finds_nearest_zero():
    # Sine wave; period 1/440s at 16 kHz.
    sr = 16000
    t = np.arange(sr) / sr
    sig = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    snapped = _snap_to_zero_crossing(sig, sr, 0.5)
    # Within 1/(2*440) ≈ 1.1ms of input — far better than a worst-case
    # period away.
    assert abs(snapped - 0.5) < 0.002
    # The function returns the sample *before* the sign flip, so the pair
    # (idx, idx+1) must straddle zero.
    idx = int(snapped * sr)
    assert sig[idx] * sig[idx + 1] <= 0


def test_next_rms_rise_returns_t_when_signal_starts_loud():
    # Silent 0..1s, loud 1..2s. From t=0.5 forward, the rise is at 1.0.
    sr = 16000
    a = np.zeros(sr * 2, dtype=np.float32)
    a[sr:] = 0.5
    rise = _next_rms_rise(a, sr, 0.5, max_advance_ms=2000)
    assert 0.95 < rise < 1.05


def test_next_rms_rise_caps_at_budget_when_no_rise():
    sr = 16000
    silent = np.zeros(sr * 2, dtype=np.float32)
    rise = _next_rms_rise(silent, sr, 0.5, max_advance_ms=200)
    assert abs(rise - 0.7) < 0.01


def test_last_rms_rise_walks_backward():
    sr = 16000
    a = np.zeros(sr * 2, dtype=np.float32)
    a[: sr // 2] = 0.5  # loud 0..0.5s
    rise = _last_rms_rise(a, sr, 1.0, max_advance_ms=600)
    # The boundary between loud and silent should be picked up.
    assert 0.4 < rise < 0.55


# ---------------------------- snap_boundaries ---------------------------- #

@pytest.fixture(scope="module")
def speech_snap():
    """A clean-speech cut: 'to oppose the construction'."""
    return snap_boundaries(SPEECH_PATH, 7.420, 10.380)


@pytest.fixture(scope="module")
def chant_snap():
    """A continuous-chant cut: first 'abolish ICE' repetition.
    The next chant starts at 0.700 — pass it as next_word_start_t so
    the trail pad doesn't bleed into the next "abolish"."""
    return snap_boundaries(CHANT_PATH, 0.0, 0.580, next_word_start_t=0.700)


def test_snap_returns_clean_silences_on_clean_speech(speech_snap):
    # Both edges should land in real silence (deeply below the
    # no-silence threshold).
    assert speech_snap.in_snap.rms_db < _NO_SILENCE_DB
    assert speech_snap.out_snap.rms_db < _NO_SILENCE_DB
    assert not speech_snap.in_snap.in_voice
    assert not speech_snap.out_snap.in_voice


def test_snap_in_side_searches_backward_not_forward(speech_snap):
    # IN snap should land at or before the candidate (silence is *before*
    # the first word). 200ms forward tolerance allowed for plosive cases.
    assert speech_snap.in_snap.delta_ms <= 200.0


def test_snap_out_side_searches_forward_not_backward(speech_snap):
    # OUT snap should land at or after the candidate (silence is *after*
    # the last word).  -200ms tolerance for natural decay snap-back.
    assert speech_snap.out_snap.delta_ms >= -200.0


def test_snap_respects_chant_word_boundary(chant_snap):
    # next_word_start_t=0.700 was passed in; cut must land before it.
    assert chant_snap.out_t < 0.700


def test_snap_flags_in_voice_when_no_silence_available(chant_snap):
    # Out side of a chant cut lands in audible energy.
    assert chant_snap.out_snap.in_voice is True


def test_snap_preserves_clip_polarity():
    # in_t < out_t even when the input is tight against word boundaries.
    res = snap_boundaries(CHANT_PATH, 0.7, 1.72)
    assert res.in_t < res.out_t
    assert res.duration > 0.5


def test_snap_rejects_inverted_input():
    with pytest.raises(ValueError):
        snap_boundaries(CHANT_PATH, 1.0, 0.5)


def test_snap_clamps_in_to_zero_at_file_start():
    # Candidate at 0.0 should never go negative.
    res = snap_boundaries(CHANT_PATH, 0.0, 0.580)
    assert res.in_t >= 0.0


def test_snap_quality_summary_is_human_readable(speech_snap):
    s = speech_snap.quality_summary()
    assert "in=" in s and "out=" in s
    assert "dB" in s


def test_snap_pad_zero_means_no_padding():
    # With both pads zero, snapped edges == valley times (modulo zero-cross).
    res = snap_boundaries(SPEECH_PATH, 7.420, 10.380,
                          lead_pad_ms=0.0, trail_pad_ms=0.0)
    # Confirm IN didn't drift much from the unpadded valley.
    # (Sanity: pads can only widen the cut, never narrow it.)
    padded = snap_boundaries(SPEECH_PATH, 7.420, 10.380,
                             lead_pad_ms=20.0, trail_pad_ms=80.0)
    assert padded.in_t <= res.in_t + 0.01     # padded reaches further back
    assert padded.out_t >= res.out_t - 0.01   # padded reaches further forward
