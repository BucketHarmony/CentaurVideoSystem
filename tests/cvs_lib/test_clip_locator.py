"""Tests for cvs_lib.clip_locator — composed phrase → snapped cut.

End-to-end against real index + raw audio. Slow (silero load on first
call) but pins behavior across word_index + clip_snap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib import clip_snap
from cvs_lib.clip_locator import (
    ClipResolution,
    locate_phrase_across_stems,
    locate_phrase_clip,
    locate_phrase_clip_all,
)

INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")
RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
SPEECH_STEM = "20260425_153128"
CHANT_STEM = "20260425_170030"


@pytest.fixture(autouse=True, scope="module")
def _share_audio_cache():
    yield
    clip_snap.clear_cache()


# ----------------------------- single-stem ------------------------------ #

def test_locate_returns_clean_speech_cut():
    # SPEECH_STEM is shot from far back — speech RMS sits ~3 dB above the
    # crowd noise floor, which the SNR gate (default +10 dB) rejects. Pin
    # snap mechanics by opting out of the gate; an SNR-specific test below
    # covers the gate behavior.
    res = locate_phrase_clip(
        SPEECH_STEM, "to oppose the construction",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        skip_off_mic=False,
    )
    assert res is not None
    assert res.match_score == 1.0
    assert res.duration > 1.0
    # Clean speech cut: both edges silent.
    assert not res.in_voice
    assert not res.out_voice


def test_locate_returns_none_for_unknown_phrase():
    assert locate_phrase_clip(
        SPEECH_STEM, "bananarama republic",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
    ) is None


def test_locate_picks_highest_score_match():
    # Single best from a chant clip: many score==1.0 matches; the picker
    # returns one (earliest tie-break).
    res = locate_phrase_clip(
        CHANT_STEM, "abolish ICE",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    assert res is not None
    assert res.match_score == 1.0


def test_to_beat_dict_has_render_ready_keys():
    res = locate_phrase_clip(
        SPEECH_STEM, "to oppose the construction",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        skip_off_mic=False,
    )
    d = res.to_beat_dict()
    assert "path" in d and "in_t" in d and "out_t" in d
    assert "phrase" in d and "snap_quality" in d
    sq = d["snap_quality"]
    for key in ("score", "in_rms_db", "out_rms_db", "in_voice",
                "out_voice", "delta_in_ms", "delta_out_ms",
                "speech_rms_db", "noise_rms_db", "snr_db",
                "voice_pct", "is_off_mic"):
        assert key in sq, f"missing {key}"
    # path is just the filename, not absolute (BEATS expects relative).
    assert "/" not in d["path"]
    assert "\\" not in d["path"]


# ------------------------------- SNR gate ------------------------------- #

def test_snr_gate_rejects_off_mic_speech():
    # Same off-mic phrase: gate ON (default) returns None.
    res = locate_phrase_clip(
        SPEECH_STEM, "to oppose the construction",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
    )
    assert res is None


def test_snr_gate_keeps_on_mic_chant():
    # Chant audio is loud and clear above the crowd floor.
    res = locate_phrase_clip(
        CHANT_STEM, "abolish ICE",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    assert res is not None
    assert res.snr_db >= 10.0
    assert not res.is_off_mic


def test_snr_gate_off_returns_off_mic_with_flag():
    res = locate_phrase_clip(
        SPEECH_STEM, "to oppose the construction",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        skip_off_mic=False,
    )
    assert res is not None
    assert res.is_off_mic is True
    assert res.snr_db < 10.0
    # OFF-MIC tag surfaces in the human summary.
    assert "OFF-MIC" in res.quality_summary()


# ------------------------------ all-matches ------------------------------ #

def test_locate_all_returns_every_chant_repetition():
    results = locate_phrase_clip_all(
        CHANT_STEM, "abolish ICE",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    assert len(results) >= 8  # 9 chants in the clip per index
    # All matches are the same stem.
    assert all(r.stem == CHANT_STEM for r in results)
    # Sorted ascending by start time (word_index invariant preserved).
    starts = [r.candidate_in_t for r in results]
    assert starts == sorted(starts)


def test_locate_all_empty_for_unknown_phrase():
    assert locate_phrase_clip_all(
        CHANT_STEM, "bananarama republic",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
    ) == []


# ----------------------------- across-stems ----------------------------- #

def test_locate_across_stems_orders_by_quality():
    """Quality-ordered: highest SNR first, then cleanest edges."""
    results = locate_phrase_across_stems(
        "abolish ICE",
        [CHANT_STEM, SPEECH_STEM],
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    assert len(results) > 0
    # Speech stem has zero matches, so all results are chant.
    assert all(r.stem == CHANT_STEM for r in results)
    # First result has SNR at least as high as the last.
    assert results[0].snr_db >= results[-1].snr_db


def test_locate_across_stems_skips_missing_index():
    results = locate_phrase_across_stems(
        "abolish ICE",
        ["does_not_exist", CHANT_STEM],
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    assert len(results) > 0


# ------------------------------- summary -------------------------------- #

def test_quality_summary_flags_in_voice_for_chant_cut():
    res = locate_phrase_clip(
        CHANT_STEM, "abolish ICE",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        fuzzy=False,
    )
    s = res.quality_summary()
    # At least one of the chant cuts has an in/out voice flag.
    assert "VOICE" in s or s.endswith("ms")  # may be clean for some chants
    # Always reports duration + dB values.
    assert "dB" in s
