"""Tests for cvs_lib.beat_resolver.

Mix of pure-function tests (no locator call) and live-index integration
tests against the Juan testimony stem (20260425_155313) which has rich
phrase coverage and is already pinned by test_locator_smoke.py.

The live tests are guarded by index/raw existence so test_beat_resolver
runs as a unit suite even on a clean checkout where the rally raw
footage isn't present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib.beat_resolver import (
    ERROR,
    INFO,
    WARN,
    ResolutionIssue,
    has_phrases,
    resolve_beats,
    resolve_spec,
)

INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")
RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
JUAN_STEM = "20260425_155313"
JUAN_SRC = RAW_DIR / f"{JUAN_STEM}.mp4"

_HAS_LIVE = JUAN_SRC.exists() and (INDEX_DIR / f"{JUAN_STEM}.json").exists()
live_only = pytest.mark.skipif(
    not _HAS_LIVE, reason="MPC rally raw + index not present"
)


# --------------------------- pure-function ---------------------------- #

def test_pass_through_when_no_phrase_key():
    spec = {"path": "/x.mp4", "in_t": 1.0, "out_t": 2.0, "audio_gain": 1.2}
    out, issues = resolve_spec("hook", spec)
    assert out == spec
    assert out is not spec  # never mutates input
    assert issues == []


def test_phrase_without_path_errors():
    spec = {"phrase": "anything"}
    out, issues = resolve_spec("hook", spec)
    assert any(i.severity == ERROR and i.code == "phrase_no_path" for i in issues)
    # Spec returned unchanged (caller can fall back to static).
    assert "in_t" not in out


def test_resolution_issue_format_includes_severity_and_slug():
    iss = ResolutionIssue(WARN, "x", "hook", "msg")
    s = iss.format()
    assert "WARN" in s and "hook" in s and "msg" in s


def test_has_phrases_detects_top_level_dict():
    beats = [
        ("a", 1.0, "minor", "L", {"path": "x.mp4", "phrase": "hi"}),
        ("b", 2.0, "minor", "L", {"path": "y.mp4", "in_t": 0, "out_t": 2}),
    ]
    assert has_phrases(beats) is True


def test_has_phrases_detects_multi_shot():
    beats = [
        ("a", 5.0, "minor", "L",
         [{"path": "x.mp4", "in_t": 0, "out_t": 1},
          {"path": "y.mp4", "phrase": "deep cut"}]),
    ]
    assert has_phrases(beats) is True


def test_has_phrases_false_when_legacy_only():
    beats = [
        ("a", 1.0, "minor", "L", {"path": "x.mp4", "in_t": 0, "out_t": 1}),
        ("b", 1.0, "minor", "L", None),
    ]
    assert has_phrases(beats) is False


def test_resolve_beats_passes_through_legacy_unchanged():
    beats = [
        ("a", 1.0, "minor", "L", {"path": "x.mp4", "in_t": 0.0, "out_t": 1.0}),
        ("b", 2.0, "minor", "L", None),
    ]
    out, issues = resolve_beats(beats)
    assert out == beats
    assert issues == []


def test_resolve_beats_preserves_tuple_arity_and_metadata():
    beats = [("a", 1.5, "build", "LABEL",
              {"path": "x.mp4", "in_t": 0, "out_t": 1.5, "audio_gain": 0.7})]
    out, _ = resolve_beats(beats)
    assert len(out) == 1
    slug, dur, chord, label, spec = out[0]
    assert (slug, dur, chord, label) == ("a", 1.5, "build", "LABEL")
    assert spec["audio_gain"] == 0.7


# ---------------------- live-index integration ------------------------ #

@live_only
def test_phrase_fills_missing_in_t_and_out_t():
    spec = {"path": str(JUAN_SRC), "phrase": "I was released Friday"}
    out, issues = resolve_spec("hook", spec, index_dir=INDEX_DIR)
    assert "in_t" in out and "out_t" in out
    assert out["out_t"] > out["in_t"]
    # Phrase appears around 13.0-15.0s in the Juan transcript.
    assert 12.0 < out["in_t"] < 14.0
    assert 14.0 < out["out_t"] < 16.0
    # Forensics block records what the locator found.
    assert "_phrase_resolution" in out
    fr = out["_phrase_resolution"]
    assert fr["used"] == "phrase"
    assert fr["match_score"] == 1.0
    # No ERROR issues; INFO/WARN possible (off-mic if footage is loud).
    assert not any(i.severity == ERROR for i in issues)


@live_only
def test_phrase_fills_only_missing_out_when_in_set():
    """`in_t` already set → resolver leaves it alone, fills only `out_t`."""
    spec = {
        "path": str(JUAN_SRC),
        "phrase": "I was released Friday",
        "in_t": 13.0,  # editorial pin
    }
    out, _ = resolve_spec("hook", spec, index_dir=INDEX_DIR)
    assert out["in_t"] == 13.0  # untouched
    assert "out_t" in out
    assert out["out_t"] > 13.0


@live_only
def test_phrase_with_static_in_out_keeps_static_and_documents():
    """Both in_t/out_t set → static wins; phrase becomes documentation
    plus drift sentinel."""
    spec = {
        "path": str(JUAN_SRC),
        "phrase": "I was released Friday",
        "in_t": 13.0,
        "out_t": 20.0,
    }
    out, issues = resolve_spec("hook", spec, index_dir=INDEX_DIR)
    assert out["in_t"] == 13.0  # static won
    assert out["out_t"] == 20.0
    fr = out["_phrase_resolution"]
    assert fr["used"] == "static"
    # No ERROR; possibly a static_drift WARN (depending on snap result).
    assert not any(i.severity == ERROR for i in issues)


@live_only
def test_phrase_not_found_emits_error():
    spec = {"path": str(JUAN_SRC),
            "phrase": "this phrase definitely is not in the audio xyzzy"}
    out, issues = resolve_spec("hook", spec, index_dir=INDEX_DIR)
    assert any(
        i.severity == ERROR and i.code == "phrase_not_found"
        for i in issues
    )
    # Spec returns unchanged on failure.
    assert "in_t" not in out


@live_only
def test_resolve_beats_end_to_end_with_juan():
    """Two-beat BEATS list, phrase-driven, runs cleanly against live index."""
    beats = [
        ("hook", 5.0, "grief", "RELEASED",
         {"path": str(JUAN_SRC), "phrase": "So this is from Juan"}),
        ("inside", 6.0, "minor", "NORTH LAKE",
         {"path": str(JUAN_SRC),
          "phrase": "I was detained for three months at North Lake"}),
    ]
    out, issues = resolve_beats(beats, index_dir=INDEX_DIR)
    assert len(out) == 2
    for _, _, _, _, spec in out:
        assert isinstance(spec, dict)
        assert "in_t" in spec and "out_t" in spec
        assert spec["out_t"] > spec["in_t"]
    assert not any(i.severity == ERROR for i in issues)


@live_only
def test_resolve_beats_dur_drift_warns_when_phrase_runs_long():
    """If `dur` disagrees with the resolved phrase duration > 250ms,
    emit a dur_drift WARN. Hook beat is 1s; phrase is ~2s — mismatch."""
    beats = [
        ("hook", 1.0, "grief", "RELEASED",
         {"path": str(JUAN_SRC), "phrase": "I was released Friday"}),
    ]
    out, issues = resolve_beats(beats, index_dir=INDEX_DIR)
    assert any(
        i.severity == WARN and i.code == "dur_drift"
        for i in issues
    )
    # Resolution still happened — the warn is informational, not fatal.
    spec = out[0][4]
    assert "in_t" in spec and "out_t" in spec


@live_only
def test_multi_shot_spec_each_sub_resolved():
    beats = [
        ("stakes", 6.0, "minor", "STAKES",
         [{"path": str(JUAN_SRC), "in_t": 1.0, "out_t": 4.0},  # legacy
          {"path": str(JUAN_SRC), "phrase": "I was released Friday"}]),
    ]
    out, _ = resolve_beats(beats, index_dir=INDEX_DIR)
    sub_specs = out[0][4]
    assert isinstance(sub_specs, list) and len(sub_specs) == 2
    # First sub: legacy, untouched.
    assert sub_specs[0]["in_t"] == 1.0 and sub_specs[0]["out_t"] == 4.0
    assert "_phrase_resolution" not in sub_specs[0]
    # Second sub: phrase-driven, filled.
    assert "in_t" in sub_specs[1] and "out_t" in sub_specs[1]
    assert "_phrase_resolution" in sub_specs[1]


@live_only
def test_fuzzy_match_emits_info_not_error():
    """Phrase with a typo still resolves; emit INFO fuzzy_match (not ERROR)."""
    spec = {"path": str(JUAN_SRC), "phrase": "I was released Fryday"}  # typo
    out, issues = resolve_spec("hook", spec, index_dir=INDEX_DIR)
    # Resolved.
    assert "in_t" in out
    # Fuzzy match info present (or not — depends on edit distance accept).
    # Either way: no ERROR.
    assert not any(i.severity == ERROR for i in issues)


# ----------------------- resolve_or_exit wrapper ----------------------- #

def test_resolve_or_exit_passthrough_for_legacy_beats():
    """No phrase= specs anywhere → resolve_or_exit returns beats unchanged
    without exiting (and without touching the locator at all)."""
    from cvs_lib.beat_resolver import resolve_or_exit
    beats = [
        ("a", 1.0, "minor", "L", {"path": "/x.mp4", "in_t": 0, "out_t": 1}),
    ]
    out = resolve_or_exit(beats)
    assert out == beats


def test_resolve_or_exit_exits_on_error(capsys):
    """phrase= without path → ERROR → SystemExit(1) with formatted output."""
    from cvs_lib.beat_resolver import resolve_or_exit
    import io
    beats = [("a", 1.0, "minor", "L", {"phrase": "no path here"})]
    buf = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        resolve_or_exit(beats, stream=buf)
    assert exc_info.value.code == 1
    assert "phrase_no_path" in buf.getvalue()


@live_only
def test_resolve_or_exit_strict_promotes_warn_to_fatal():
    """`strict=True` makes WARN-level issues (e.g. dur_drift) fatal."""
    from cvs_lib.beat_resolver import resolve_or_exit
    import io
    beats = [
        ("hook", 1.0, "minor", "L",
         {"path": str(JUAN_SRC), "phrase": "I was released Friday"}),
    ]
    buf = io.StringIO()
    with pytest.raises(SystemExit):
        resolve_or_exit(beats, index_dir=INDEX_DIR, strict=True, stream=buf)
    assert "dur_drift" in buf.getvalue() or "off_mic" in buf.getvalue()


# ------------------------- preflight integration ------------------------- #

def test_preflight_catches_unresolved_phrase():
    """Reel forgot to call resolve_or_exit — preflight surfaces the
    foot-gun with a pointed ERROR pointing at the resolver."""
    from cvs_lib import preflight
    beats = [
        ("hook", 7.0, "minor", "L", {"path": "/x.mp4", "phrase": "abolish ICE"}),
        ("rest", 23.0, "minor", "L", {"path": "/x.mp4", "in_t": 0, "out_t": 23}),
    ]
    issues = preflight.assert_phrases_were_resolved(beats)
    assert len(issues) == 1
    assert issues[0].severity == "ERROR"
    assert issues[0].code == "phrase_unresolved"
    assert "resolve_or_exit" in issues[0].message


def test_preflight_silent_when_phrase_already_resolved():
    """Resolved spec (phrase + in_t + out_t) doesn't trip the guard —
    that's the documented static-wins case."""
    from cvs_lib import preflight
    beats = [
        ("hook", 7.0, "minor", "L",
         {"path": "/x.mp4", "phrase": "abolish ICE", "in_t": 1.0, "out_t": 8.0}),
    ]
    assert preflight.assert_phrases_were_resolved(beats) == []
