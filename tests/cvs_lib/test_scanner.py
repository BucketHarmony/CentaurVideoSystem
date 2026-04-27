"""Phase 1 tests for cvs_lib.scanner.

Pure-function tests on tag derivation, scene detection, and prompt
loading — no GPU / whisper / OpenCV required. The whisper transcribe
path is exercised end-to-end via running `scripts/scan.py` against a
real clip in the verification step (see plan: misty-leaping-fiddle.md
… actually diligent-tagging-cartographer.md), not here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvs_lib import scanner


# --------------------------------------------------------------------------- #
# detect_scenes
# --------------------------------------------------------------------------- #

def test_detect_scenes_always_starts_at_zero():
    cuts = scanner.detect_scenes([{"t": 0.5, "motion": 5.0}])
    assert cuts[0] == 0.0


def test_detect_scenes_threshold_filters_low_motion():
    timeline = [
        {"t": 0.5, "motion": 5.0},     # below threshold
        {"t": 2.0, "motion": 20.0},    # above threshold, gap ok
        {"t": 4.0, "motion": 18.0},    # above threshold, gap ok
    ]
    cuts = scanner.detect_scenes(timeline, threshold=14.0, min_gap_s=1.5)
    assert cuts == [0.0, 2.0, 4.0]


def test_detect_scenes_min_gap_suppresses_burst():
    timeline = [
        {"t": 1.0, "motion": 25.0},
        {"t": 1.5, "motion": 30.0},
        {"t": 2.0, "motion": 28.0},
        {"t": 5.0, "motion": 22.0},
    ]
    cuts = scanner.detect_scenes(timeline, threshold=14.0, min_gap_s=1.5)
    # t=1.0 is suppressed (< 1.5 since last cut at 0.0); t=1.5 is the
    # first to satisfy the gap; t=2.0 is suppressed; t=5.0 fires.
    assert cuts == [0.0, 1.5, 5.0]


# --------------------------------------------------------------------------- #
# derive_tags
# --------------------------------------------------------------------------- #

def _meta(duration=30.0, width=1080, height=1920):
    return {"duration_s": duration, "width": width, "height": height}


def test_derive_tags_keyword_match_on_ICE_word_boundary():
    transcript = {"text": "Abolish ICE right now."}
    tags = scanner.derive_tags(_meta(), transcript, [])
    assert "ICE" in tags
    # 'police' must not match the ICE pattern
    transcript = {"text": "the police were watching"}
    tags = scanner.derive_tags(_meta(), transcript, [])
    assert "ICE" not in tags


def test_derive_tags_motion_buckets():
    static_timeline = [{"t": t, "motion": 1.0} for t in (0.5, 1.0, 1.5)]
    tags = scanner.derive_tags(_meta(), {"text": ""}, static_timeline)
    assert "static" in tags

    high_timeline = [{"t": t, "motion": 20.0} for t in (0.5, 1.0, 1.5)]
    tags = scanner.derive_tags(_meta(), {"text": ""}, high_timeline)
    assert "high_motion" in tags

    shake_timeline = [{"t": 0.5, "motion": 50.0}]
    tags = scanner.derive_tags(_meta(), {"text": ""}, shake_timeline)
    assert "camera_shake" in tags


def test_derive_tags_silent_vs_dialogue_vs_ambient():
    assert "silent" in scanner.derive_tags(_meta(), {"text": ""}, [])
    short = scanner.derive_tags(_meta(), {"text": "abolish ICE"}, [])
    assert "ambient" in short
    long_text = "x" * 250
    assert "dialogue" in scanner.derive_tags(_meta(), {"text": long_text}, [])


def test_derive_tags_orientation():
    portrait = scanner.derive_tags(_meta(width=1080, height=1920), {"text": ""}, [])
    assert "vertical" in portrait
    landscape = scanner.derive_tags(_meta(width=1920, height=1080), {"text": ""}, [])
    assert "horizontal" in landscape


def test_derive_tags_duration_buckets():
    assert "short" in scanner.derive_tags(_meta(duration=5.0), {"text": ""}, [])
    assert "long" in scanner.derive_tags(_meta(duration=90.0), {"text": ""}, [])


# --------------------------------------------------------------------------- #
# Prompt registry
# --------------------------------------------------------------------------- #

def test_prompt_for_path_resolves_by_parent_folder(tmp_path: Path):
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps({
        "Ice Out Romulus": "Detroit. ICE.",
        "Other Event": "Foo. Bar.",
    }))
    p = Path("/x/raw/MPC/Ice Out Romulus/20260425_170245.mp4")
    assert scanner.prompt_for_path(p, prompts_path=prompts) == "Detroit. ICE."

    p2 = Path("/x/raw/MPC/Unknown Event/clip.mp4")
    assert scanner.prompt_for_path(p2, prompts_path=prompts) is None


def test_load_prompts_missing_file_returns_empty(tmp_path: Path):
    p = tmp_path / "nope.json"
    assert scanner.load_prompts(p) == {}


# --------------------------------------------------------------------------- #
# Real prompts file structure
# --------------------------------------------------------------------------- #

def test_real_scanner_prompts_has_ice_out_romulus():
    """The MPC prompts file must define the Ice Out Romulus entry —
    Phase 0 validated against this exact vocab string."""
    p = Path("E:/AI/CVS/mpc/scanner_prompts.json")
    prompts = scanner.load_prompts(p)
    assert "Ice Out Romulus" in prompts
    s = prompts["Ice Out Romulus"]
    # No quoted phrases — Phase 0 found that quoted strings leak into output.
    assert "'" not in s and '"' not in s, (
        "scanner_prompts.json entries should be vocabulary only — "
        "no quoted phrases (they leak into transcripts).")
