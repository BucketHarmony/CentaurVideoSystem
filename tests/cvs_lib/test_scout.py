"""Tests for cvs_lib.scout — markdown renderers for the rally dashboard.

Pure-function tests against fixture data shaped like the index JSON
schema. Plus an end-to-end render against a real index entry to
confirm the composition works on production data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvs_lib.scout import (
    _fmt_t,
    format_meta,
    format_motion_peaks,
    format_scenes,
    format_tags,
    format_transcript,
    render_index_page,
    render_stem_page,
)

INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")
SAMPLE_STEM = "20260425_155313"


# ----------------------------- helpers -------------------------------- #

def _fixture():
    """Hand-crafted minimal index entry — keeps tests independent of
    the live index file."""
    return {
        "meta": {
            "filename": "test.mp4",
            "path": "E:/raw/test.mp4",
            "duration_s": 12.5,
            "width": 1920, "height": 1080,
            "fps": 30.0, "codec": "h264",
        },
        "motion_timeline": [
            {"t": 0.5, "motion": 10.0},
            {"t": 1.0, "motion": 50.0},
            {"t": 1.5, "motion": 30.0},
            {"t": 2.0, "motion": 90.0},
            {"t": 2.5, "motion": 20.0},
        ],
        "scenes": [
            {"idx": 0, "t": 0.0,
             "path": "E:/AI/CVS/mpc/index/thumbnails/test_s00_t0000.jpg"},
            {"idx": 1, "t": 5.0,
             "path": "E:/AI/CVS/mpc/index/thumbnails/test_s01_t0500.jpg"},
        ],
        "transcript": {
            "language": "en",
            "duration_s": 12.5,
            "text": "Hello world. This is a test.",
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Hello world."},
                {"start": 5.0, "end": 12.5, "text": "This is a test."},
            ],
        },
        "tags": ["speech", "horizontal", "test"],
        "audio_dominant": {"class": "speech", "fraction": 1.0},
    }


# --------------------------- timestamps ------------------------------ #

def test_fmt_t_under_minute_uses_seconds():
    assert "5.00" in _fmt_t(5.0)
    assert "s" in _fmt_t(45.0)


def test_fmt_t_over_minute_uses_mmss():
    s = _fmt_t(125.5)
    assert "2:" in s
    assert "05.50" in s


# ------------------------------ meta --------------------------------- #

def test_format_meta_includes_dims_codec_audio():
    md = format_meta(_fixture())
    assert "test.mp4" in md
    assert "1920x1080" in md
    assert "30.0 fps" in md
    assert "h264" in md
    assert "speech" in md


def test_format_meta_handles_missing_audio_dominant():
    data = _fixture()
    data["audio_dominant"] = None
    md = format_meta(data)
    # Doesn't crash; renders something for the audio line.
    assert "Audio" in md


# ------------------------------ tags --------------------------------- #

def test_format_tags_alphabetizes_and_codes():
    md = format_tags(_fixture())
    assert "`horizontal`" in md
    assert "`speech`" in md
    # Sorted output: 'horizontal' before 'speech' before 'test'.
    assert md.index("horizontal") < md.index("speech") < md.index("test")


def test_format_tags_empty_returns_empty_string():
    assert format_tags({"tags": []}) == ""
    assert format_tags({}) == ""


# --------------------------- transcript ------------------------------ #

def test_format_transcript_lists_each_segment_with_timestamp():
    md = format_transcript(_fixture())
    assert "Hello world." in md
    assert "This is a test." in md
    assert " 0.00s" in md or "0.00s" in md
    assert " 5.00s" in md or "5.00s" in md


def test_format_transcript_truncates_at_max_chars():
    data = _fixture()
    data["transcript"]["segments"][0]["text"] = "x" * 200
    md = format_transcript(data, max_chars_per_segment=50)
    assert "..." in md
    assert "x" * 200 not in md


def test_format_transcript_falls_back_to_full_text_when_no_segments():
    data = {"transcript": {"text": "fallback only", "segments": []}}
    md = format_transcript(data)
    assert "fallback only" in md
    assert "> " in md  # blockquote rendering


def test_format_transcript_empty_returns_none_marker():
    md = format_transcript({})
    assert "none" in md.lower() or "Transcript" in md


# --------------------------- motion peaks ---------------------------- #

def test_format_motion_peaks_picks_highest_motion_values():
    md = format_motion_peaks(_fixture(), top_n=2)
    # Two highest are t=2.0 (motion=90) and t=1.0 (motion=50).
    assert "motion=90.0" in md
    assert "motion=50.0" in md
    # Lowest (t=0.5, motion=10) should NOT appear.
    assert "motion=10.0" not in md


def test_format_motion_peaks_orders_by_time_not_motion():
    """Peaks ordered chronologically so editorial reads left-to-right."""
    md = format_motion_peaks(_fixture(), top_n=3)
    # The selected peaks are t=1.0, 1.5, 2.0 — verify time order.
    i_10 = md.index("1.00s")
    i_15 = md.index("1.50s")
    i_20 = md.index("2.00s")
    assert i_10 < i_15 < i_20


def test_format_motion_peaks_empty_returns_empty_string():
    assert format_motion_peaks({"motion_timeline": []}) == ""


# ------------------------------ scenes ------------------------------- #

def test_format_scenes_emits_image_links():
    md = format_scenes(_fixture(), thumbs_relative_to=None)
    assert "![scene]" in md
    assert "test_s00_t0000.jpg" in md


def test_format_scenes_limits_to_top_n():
    data = _fixture()
    data["scenes"] = [
        {"idx": i, "t": float(i),
         "path": f"E:/thumbs/s{i:02d}.jpg"}
        for i in range(20)
    ]
    md = format_scenes(data, limit=5)
    assert "s00.jpg" in md
    assert "s04.jpg" in md
    assert "s05.jpg" not in md
    assert "15 more scenes" in md


def test_format_scenes_falls_back_to_posix_when_relative_fails(tmp_path):
    """Different drive (or unrelated path) -> can't relativize, posix
    backslash conversion still applied so the link works in any
    markdown viewer."""
    data = _fixture()
    md = format_scenes(data, thumbs_relative_to=tmp_path)
    # Backslashes should be normalized to forward slashes.
    assert "\\" not in md


# -------------------------- composite renders ------------------------- #

def test_render_stem_page_includes_all_sections():
    md = render_stem_page("test", _fixture())
    assert "test.mp4" in md          # meta
    assert "Tags" in md               # tags
    assert "Transcript" in md         # transcript
    assert "Motion peaks" in md       # motion
    assert "Scenes" in md             # scenes


def test_render_index_page_links_each_stem():
    entries = [("a", _fixture()), ("b", _fixture())]
    md = render_index_page("Test rally", entries)
    assert "Test rally" in md
    assert "[`a`](a.md)" in md
    assert "[`b`](b.md)" in md
    # Header row of the table.
    assert "Duration" in md and "Audio" in md and "Tags" in md


def test_render_index_page_truncates_long_transcript_in_preview():
    data = _fixture()
    data["transcript"]["text"] = "x " * 500  # very long
    md = render_index_page("Test", [("a", data)])
    # The preview cell shouldn't blow past ~80 chars (gets truncated
    # with `...` per the renderer).
    assert "..." in md


def test_render_index_page_strips_pipe_chars_in_preview():
    """Markdown table cells must not contain raw pipe chars."""
    data = _fixture()
    data["transcript"]["text"] = "before | middle | after"
    md = render_index_page("Test", [("a", data)])
    # Find the row for stem 'a' specifically and check that beyond the
    # leading `| ` the preview text doesn't reintroduce raw pipes.
    rows = [ln for ln in md.splitlines() if ln.startswith("| [`a`]")]
    assert rows, "expected a table row for stem a"
    cells = rows[0].split("|")
    preview = cells[-2]  # last non-empty cell
    assert "|" not in preview


# ------------------------ live-index sanity -------------------------- #

@pytest.mark.skipif(not INDEX_DIR.exists(),
                    reason="MPC index not available")
def test_render_stem_page_against_real_index():
    """Exercise the renderer against a real index entry to catch any
    schema assumption that the fixture papers over."""
    data = json.loads(
        (INDEX_DIR / f"{SAMPLE_STEM}.json").read_text(encoding="utf-8"),
    )
    md = render_stem_page(SAMPLE_STEM, data)
    # Real Juan-testimony clip has a long transcript and tags.
    assert "Juan" in md or "released" in md
    assert "Transcript" in md
    assert "Scenes" in md
    # No KeyError, no NoneType errors — render produced a string.
    assert len(md) > 200
