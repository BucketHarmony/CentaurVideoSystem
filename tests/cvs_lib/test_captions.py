"""Phase 2 tests for cvs_lib.captions (data layer only).

Renders are unit-tested elsewhere (require PIL/MoviePy). These tests
exercise `events_from_beats` against the Juan index — auto-fill, manual
override, empty-list suppression, per-segment overrides, and CTA synth.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib.captions import events_from_beats
from cvs_lib import index as idx_mod


JUAN_PATH = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus/20260425_155313.mp4")
INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")


def _beat(slug, dur, **spec):
    return (slug, dur, "minor", slug.upper(), spec)


@pytest.fixture(autouse=True)
def _reset_cache():
    idx_mod.clear_cache()
    yield
    idx_mod.clear_cache()


def test_manual_caption_lines_pass_through():
    """Beats that ship caption_lines bypass the index entirely."""
    beats = [
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0,
              caption_lines=[(0.0, 2.5, "Hello"), (3.0, 6.0, "World")]),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    assert events == [
        {"start": 0.0, "end": 2.5, "text": "Hello"},
        {"start": 3.0, "end": 6.0, "text": "World"},
    ]


def test_empty_caption_lines_suppresses_all():
    """Explicit empty list suppresses captions even when index has segments."""
    beats = [
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0,
              caption_lines=[]),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    assert events == []


def test_autofill_pulls_segments_when_caption_lines_absent():
    """No caption_lines key → auto-fill from the transcript index.

    HOOK beat windows the Juan source at 13.0-20.0. By midpoint test,
    that includes the 12.16-15.52 ('released Friday') and 15.52-19.36
    ('North Lake, 90 days') segments.
    """
    beats = [
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    assert len(events) == 2
    joined = " ".join(e["text"] for e in events)
    assert "released Friday" in joined
    assert "North Lake" in joined


def test_autofill_offsets_relative_to_beat_start():
    """First segment starts at 12.16 in source; with in_t=13.0 the
    offset is -0.84 (segment opens before the cut, common case).
    Scene_t0 for the only beat is 0.0, so start=-0.84."""
    beats = [
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    # First event is the 'released Friday' line.
    e0 = events[0]
    assert e0["start"] == pytest.approx(12.16 - 13.0, abs=1e-6)
    assert e0["end"] == pytest.approx(15.52 - 13.0, abs=1e-6)


def test_autofill_respects_scene_t0():
    """A beat that's not first in the sequence must offset by cumulative t."""
    beats = [
        _beat("intro", 5.0, path=JUAN_PATH, in_t=0.0, out_t=5.0,
              caption_lines=[]),  # suppress so it doesn't pollute
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    # First event is auto-filled in HOOK at scene_t0=5.0.
    e0 = events[0]
    assert e0["start"] == pytest.approx(5.0 + (12.16 - 13.0), abs=1e-6)


def test_caption_overrides_substitute_text_by_segment_start():
    """caption_overrides[seg_start] replaces the segment text."""
    beats = [
        _beat("hook", 7.0, path=JUAN_PATH, in_t=13.0, out_t=20.0,
              caption_overrides={12.16: "I was released Friday."}),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    assert events[0]["text"] == "I was released Friday."
    # Other segments unchanged.
    assert "North Lake" in events[1]["text"]


def test_cta_uses_narration_lines_via_measure_callback():
    """CTA beat reads from narration_lines, sized by measure_tts_duration."""
    beats = [
        _beat("hook", 5.0, path=JUAN_PATH, in_t=13.0, out_t=18.0,
              caption_lines=[]),
        _beat("cta", 5.0, path=JUAN_PATH, in_t=0.0, out_t=5.0),
    ]
    narration = [{"slug": "cta", "start_in_beat": 0.5, "text": "Free them all."}]
    events = events_from_beats(
        beats,
        narration_lines=narration,
        measure_tts_duration=lambda slug: 3.0,
        index_dir=INDEX_DIR,
    )
    assert len(events) == 1
    e = events[0]
    assert e["text"] == "Free them all."
    assert e["start"] == pytest.approx(5.0 + 0.5)
    assert e["end"] == pytest.approx(5.0 + 0.5 + 3.0)


def test_cta_skipped_when_measure_callback_missing():
    beats = [
        _beat("cta", 5.0, path=JUAN_PATH, in_t=0.0, out_t=5.0),
    ]
    narration = [{"slug": "cta", "start_in_beat": 0.5, "text": "Hi"}]
    events = events_from_beats(beats, narration_lines=narration,
                               measure_tts_duration=None,
                               index_dir=INDEX_DIR)
    assert events == []


def test_cta_clipped_to_beat_end():
    """If TTS duration would exceed beat, end clips to beat end."""
    beats = [
        _beat("cta", 5.0, path=JUAN_PATH, in_t=0.0, out_t=5.0),
    ]
    narration = [{"slug": "cta", "start_in_beat": 4.0, "text": "X"}]
    events = events_from_beats(beats, narration_lines=narration,
                               measure_tts_duration=lambda s: 99.0,
                               index_dir=INDEX_DIR)
    assert len(events) == 1
    assert events[0]["end"] == pytest.approx(5.0)


def test_events_are_sorted_by_start():
    beats = [
        _beat("a", 5.0, path=JUAN_PATH, in_t=13.0, out_t=18.0,
              caption_lines=[(2.0, 3.0, "second"), (0.0, 1.0, "first")]),
    ]
    events = events_from_beats(beats, index_dir=INDEX_DIR)
    assert [e["text"] for e in events] == ["first", "second"]
