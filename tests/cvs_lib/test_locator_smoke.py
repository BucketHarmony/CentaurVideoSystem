"""End-to-end smoke test: locate the 5 canonical demo phrases.

These are the same five phrases driven by `scripts/mpc_demo_clips.py`
— hand-graded against the rally audio. This test pins their snap +
SNR + match-score against the 2026-04-29 baseline so a regression
in any of word_index, clip_snap, clip_locator, or the SNR analysis
will surface here without needing audio playback.

Tolerance: ±0.25s on duration, ±2 dB on SNR, exact match on the
off-mic flag. Loose enough to absorb fixture audio re-encodes; tight
enough to catch a meaningful misbehavior (a dropped pad, a silero
threshold change, a wrong noise-floor formula).

Slow first run (~5s for silero load + per-stem WordIndex/audio loads).
Subsequent runs in the same pytest invocation share the audio cache
via the module-scoped fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib import clip_snap
from cvs_lib.clip_locator import locate_phrase_clip

INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")
RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

# Baseline values captured 2026-04-29 from a clean run of
# `scripts/mpc_demo_clips.py` against the Ice Out Romulus rally
# (see ComfyUI/output/mpc/_demo_clips/demo_manifest.json). Each entry
# is one demo: stem + phrase + the snap_quality fields the test
# asserts against.
BASELINES = [
    {
        "name": "north_lake_testimony",
        "stem": "20260425_155313",
        "phrase": "I was detained for three months at North Lake",
        "duration": 3.05,
        "snr_db": 11.3,
        "is_off_mic": False,
    },
    {
        "name": "nbcm_origin",
        "stem": "20260425_153128",
        "phrase": "to oppose the construction",
        "duration": 3.375,
        "snr_db": 5.2,
        "is_off_mic": True,
    },
    {
        "name": "community_engaged",
        "stem": "20260425_154736",
        "phrase": "the community of Romulus is engaged",
        "duration": 1.855,
        "snr_db": 4.1,
        "is_off_mic": True,
    },
    {
        "name": "naz_fearful",
        "stem": "20260425_165207",
        "phrase": "I am very fearful",
        "duration": 2.369,
        "snr_db": 15.8,
        "is_off_mic": False,
    },
    {
        "name": "geogroup_254m",
        "stem": "20260425_170328",
        "phrase": "254 million",
        "duration": 1.935,
        "snr_db": 23.5,
        "is_off_mic": False,
    },
]


@pytest.fixture(autouse=True, scope="module")
def _share_audio_cache():
    yield
    clip_snap.clear_cache()


@pytest.mark.parametrize("baseline", BASELINES, ids=lambda b: b["name"])
def test_demo_phrase_resolves_to_baseline(baseline):
    """Every demo phrase must resolve, score 1.0, and land within
    tolerance of its 2026-04-29 baseline duration + SNR. The off-mic
    flag is asserted exactly — it's the editorial gate."""
    res = locate_phrase_clip(
        baseline["stem"], baseline["phrase"],
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
        skip_off_mic=False,
    )
    assert res is not None, f"{baseline['name']}: phrase not found"
    assert res.match_score == 1.0, (
        f"{baseline['name']}: expected exact match, got "
        f"score={res.match_score:.2f}"
    )
    assert abs(res.duration - baseline["duration"]) < 0.25, (
        f"{baseline['name']}: duration drift "
        f"{res.duration:.3f} vs baseline {baseline['duration']:.3f}"
    )
    assert abs(res.snr_db - baseline["snr_db"]) < 2.0, (
        f"{baseline['name']}: SNR drift "
        f"{res.snr_db:+.1f} vs baseline {baseline['snr_db']:+.1f}"
    )
    assert res.is_off_mic == baseline["is_off_mic"], (
        f"{baseline['name']}: off-mic flag flipped "
        f"({res.is_off_mic} vs baseline {baseline['is_off_mic']}; "
        f"SNR={res.snr_db:+.1f})"
    )


def test_geogroup_254m_captures_two_via_vad_extension():
    """Regression-pin the 2026-04-29 VAD-interval extension fix.

    Whisper places `$254` at 21.280 but the spoken "two" lives in
    unscored audio at 20.70-21.20 inside the same VAD voice interval.
    The clip_snap fix walks back to the VAD interval onset (~20.6)
    when the candidate sits inside a longer voice region. If that
    behaviour breaks, this test catches it before the demo cuts ship.
    """
    res = locate_phrase_clip(
        "20260425_170328", "254 million",
        raw_dir=RAW_DIR, index_dir=INDEX_DIR,
    )
    assert res is not None
    # candidate_in_t is whisper's word boundary (21.28); snapped in_t
    # MUST land before that to capture the spoken "two".
    assert res.in_t < 21.0, (
        f"VAD-interval extension regressed: in_t={res.in_t:.3f} "
        f"(must be < 21.0 to capture 'two')"
    )
    # Lead delta should be substantial (>500ms back).
    assert res.in_delta_ms < -500.0
