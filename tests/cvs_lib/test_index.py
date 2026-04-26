"""Phase 2 tests for cvs_lib.index.

Exercises the read-only loader against the real Juan transcript at
mpc/index/clips/20260425_155313.json — the canonical fixture for the
North Lake reel. If that file moves, these tests should be updated, not
copied to a tmp fixture: the index file is the source of truth.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib import index


JUAN_STEM = "20260425_155313"
INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")


@pytest.fixture(autouse=True)
def _reset_cache():
    index.clear_cache()
    yield
    index.clear_cache()


def test_load_clip_index_has_expected_top_level_keys():
    data = index.load_clip_index(JUAN_STEM, INDEX_DIR)
    assert {"meta", "motion_timeline", "scenes", "transcript", "tags"} <= set(data)
    assert data["meta"]["filename"] == "20260425_155313.mp4"


def test_load_clip_index_missing_stem_raises():
    with pytest.raises(FileNotFoundError):
        index.load_clip_index("does_not_exist_stem", INDEX_DIR)


def test_segments_in_window_returns_released_friday():
    """The North Lake HOOK beat (13.0-20.0) must include the
    'released Friday' segment by midpoint test."""
    segs = index.segments_in_window(JUAN_STEM, 13.0, 20.0, INDEX_DIR)
    assert len(segs) >= 1
    joined = " ".join(s["text"] for s in segs)
    assert "released Friday" in joined


def test_segments_in_window_empty_when_t1_le_t0():
    assert index.segments_in_window(JUAN_STEM, 5.0, 5.0, INDEX_DIR) == []
    assert index.segments_in_window(JUAN_STEM, 5.0, 4.0, INDEX_DIR) == []


def test_segments_in_window_uses_midpoint_not_overlap():
    """A segment that overlaps the window but whose midpoint is outside
    must NOT be returned. Segment 19.36-22.84 has midpoint 21.10 — it
    overlaps a (13.0, 20.0) window but should not be included."""
    segs = index.segments_in_window(JUAN_STEM, 13.0, 20.0, INDEX_DIR)
    starts = [s["start"] for s in segs]
    assert 19.36 not in starts


def test_stem_for_path_strips_extension_and_dirs():
    p = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus/20260425_155313.mp4")
    assert index.stem_for_path(p) == "20260425_155313"


def test_motion_at_interpolates_between_samples():
    """Motion timeline starts at t=0.5; t=0.75 should be between
    sample[0]=44.456 and sample[1]=42.414."""
    m = index.motion_at(JUAN_STEM, 0.75, INDEX_DIR)
    assert m is not None
    assert 42.0 <= m <= 45.0


def test_motion_at_out_of_bounds_returns_none():
    assert index.motion_at(JUAN_STEM, -1.0, INDEX_DIR) is None
    assert index.motion_at(JUAN_STEM, 9999.0, INDEX_DIR) is None


def test_transcript_text_nonempty():
    txt = index.transcript_text(JUAN_STEM, INDEX_DIR)
    assert "released Friday" in txt
    assert "North Lake" in txt


def test_tags_returns_list():
    t = index.tags(JUAN_STEM, INDEX_DIR)
    assert isinstance(t, list)
    assert "ICE" in t
