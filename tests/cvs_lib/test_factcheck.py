"""Tests for cvs_lib.factcheck.

Covers:
- Roster loading + _schema sentinel stripping
- Name extraction regex behavior + deny list
- Exact / close / unknown name match paths
- Non-progressive WARN
- Content hash stability + signoff staleness
- Integration via preflight.run() with factcheck_roster set
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvs_lib import factcheck, preflight


# ───────────────────────────── fixtures ─────────────────────────────

ROSTER = {
    "_schema": {"description": "test"},
    "donovan_mckinney": {
        "name": "Donovan McKinney",
        "role": "MI State Rep",
        "progressive": True,
        "aliases": ["McKinney", "Rep. McKinney"],
    },
    "kristi_noem": {
        "name": "Kristi Noem",
        "role": "Sec DHS",
        "progressive": False,
        "aliases": ["Noem"],
        "notes": "needs critical framing",
    },
    "juan": {
        "name": "Juan",
        "role": "detainee",
        "progressive": None,
        "aliases": [],
    },
}


@pytest.fixture
def roster_file(tmp_path: Path) -> Path:
    p = tmp_path / "roster.json"
    p.write_text(json.dumps(ROSTER), encoding="utf-8")
    return p


def _beat(slug, dur, chip, spec):
    return (slug, dur, "minor", chip, spec)


def _spec_with_captions(lines):
    """Build a spec dict whose caption_lines is a list of (s,e,txt)."""
    return {
        "path": Path("does/not/exist.mp4"),
        "in_t": 0.0,
        "out_t": 1.0,
        "caption_lines": [(0.0, 1.0, t) for t in lines],
    }


# ───────────────────────────── roster loading ─────────────────────────────

def test_load_roster_strips_schema(roster_file):
    r = factcheck.load_roster(roster_file)
    assert "_schema" not in r
    assert "donovan_mckinney" in r
    assert "kristi_noem" in r


def test_load_roster_missing_returns_empty(tmp_path):
    assert factcheck.load_roster(tmp_path / "nope.json") == {}


# ───────────────────────────── name extraction ─────────────────────────────

def test_extract_name_candidates_basic():
    cands = factcheck._extract_name_candidates(
        "Donovan McKinney spoke at the rally."
    )
    assert "Donovan McKinney" in cands


def test_extract_name_candidates_filters_function_words():
    """Single capitalized words at sentence start that are function words
    (The, We, I) should be filtered out."""
    cands = factcheck._extract_name_candidates(
        "The plan was clear. We went home."
    )
    assert "The" not in cands
    assert "We" not in cands


def test_extract_name_candidates_keeps_multiword():
    cands = factcheck._extract_name_candidates("Rashida Tlaib stood up.")
    assert "Rashida Tlaib" in cands


# ───────────────────────────── name validation ─────────────────────────────

def test_exact_match_silent(roster_file):
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Donovan McKinney is a state rep.", "test", roster, lookup
    )
    assert issues == []


def test_alias_match_silent(roster_file):
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Rep. McKinney spoke today.", "test", roster, lookup
    )
    assert issues == []


def test_misspelling_caught_as_error(roster_file):
    """'Donavan Mckinney' is one edit + casing drift from canonical."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Donavan Mckinney spoke today.", "test", roster, lookup
    )
    assert any(i.severity == "ERROR" and i.code == "name_misspelled"
               for i in issues)


def test_non_progressive_warn(roster_file):
    """Mentioning a progressive=false figure must WARN for sign-off."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Kristi Noem ordered the raid.", "test", roster, lookup
    )
    assert any(i.severity == "WARN" and i.code == "non_progressive_mention"
               for i in issues)


def test_unknown_multiword_name_warn(roster_file):
    """'Bernie Sanders' is not in this fixture roster — should WARN."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Bernie Sanders endorsed it.", "test", roster, lookup
    )
    assert any(i.severity == "WARN" and i.code == "name_not_in_roster"
               for i in issues)


def test_unknown_single_capitalized_word_no_warn(roster_file):
    """Single capitalized words at sentence start (not honorific-prefixed)
    should not produce a name-not-in-roster warning."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Yesterday everything changed.", "test", roster, lookup
    )
    assert not any(i.code == "name_not_in_roster" for i in issues)


def test_extended_form_with_honorific_silent(roster_file):
    """'Rep. Donovan McKinney' contains the canonical 'Donovan McKinney'
    as a multi-word substring — should pass silently as an extension,
    not get flagged as a misspelling."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Rep. Donovan McKinney spoke today.", "test", roster, lookup
    )
    assert issues == []


def test_misspelling_with_alias_word_still_flagged(roster_file):
    """'Donavan Mckinney' contains the alias 'McKinney' as substring,
    but the rest of the phrase is misspelled — must not silently bypass."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Donavan Mckinney spoke today.", "test", roster, lookup
    )
    assert any(i.code == "name_misspelled" for i in issues)


def test_all_caps_chip_phrase_silent(roster_file):
    """Slogan-style ALL-CAPS chip text ('FREE THEM ALL', 'JUDGES IGNORING
    THE LAW') should not produce name-not-in-roster warnings."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    for chip in [
        "FREE THEM ALL",
        "JUDGES IGNORING THE LAW",
        "DEFUND THE CAGES",
        "PEOPLE POWER",
        "ABOLISH ICE",
    ]:
        issues = factcheck.check_name_in_text(chip, "chip", roster, lookup)
        assert not any(i.code == "name_not_in_roster" for i in issues), \
            f"all-caps chip {chip!r} should pass silently, got {issues}"


def test_all_caps_chip_with_roster_name_still_flags_non_progressive(roster_file):
    """An all-caps chip that contains a non-progressive figure's name
    (e.g. 'KRISTI NOEM ORDERED') should still WARN."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "KRISTI NOEM ORDERED THE RAID", "chip", roster, lookup
    )
    assert any(i.code == "non_progressive_mention" for i in issues)


def test_phrase_of_only_deny_words_silent(roster_file):
    """'House District' — both tokens are in the deny list. Should not WARN
    as a name-shaped unknown."""
    roster = factcheck.load_roster(roster_file)
    lookup = factcheck._build_lookup(roster)
    issues = factcheck.check_name_in_text(
        "Michigan House District 14.", "test", roster, lookup
    )
    assert not any(i.code == "name_not_in_roster" and "House District" in i.message
                   for i in issues)


# ───────────────────────────── beats traversal ─────────────────────────────

def test_check_beats_against_roster_walks_chips_and_captions(roster_file):
    beats = [
        _beat("intro", 1.0, "DONAVAN MCKINNEY",
              _spec_with_captions(["Donavan Mckinney spoke."])),
    ]
    issues = factcheck.check_beats_against_roster(beats, roster_file)
    # Misspelling shows up in BOTH chip and caption text — at least one error.
    assert any(i.code == "name_misspelled" for i in issues)


def test_check_beats_handles_multi_shot_list_specs(roster_file):
    """Multi-shot specs (list-of-dicts) must still be walked."""
    beats = [
        _beat("multi", 1.0, "CHIP", [
            _spec_with_captions(["Donovan McKinney is here."]),
            _spec_with_captions(["Bernie Sanders too."]),
        ]),
    ]
    issues = factcheck.check_beats_against_roster(beats, roster_file)
    # Bernie should produce a warn (not in roster); Donovan should be silent.
    assert any(i.code == "name_not_in_roster" and "Bernie" in i.message
               for i in issues)


def test_missing_roster_is_error(tmp_path):
    beats = [_beat("intro", 1.0, "X", _spec_with_captions(["hello"]))]
    issues = factcheck.check_beats_against_roster(beats, tmp_path / "nope.json")
    assert any(i.code == "roster_missing" for i in issues)


# ───────────────────────────── claims sign-off ─────────────────────────────

def test_content_hash_is_stable(roster_file):
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hello world"]))]
    h1 = factcheck._content_hash(beats)
    h2 = factcheck._content_hash(beats)
    assert h1 == h2


def test_content_hash_changes_on_caption_edit():
    b1 = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hello"]))]
    b2 = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hello!"]))]
    assert factcheck._content_hash(b1) != factcheck._content_hash(b2)


def test_content_hash_changes_on_chip_edit():
    b1 = [_beat("a", 1.0, "CHIP A", _spec_with_captions(["x"]))]
    b2 = [_beat("a", 1.0, "CHIP B", _spec_with_captions(["x"]))]
    assert factcheck._content_hash(b1) != factcheck._content_hash(b2)


def test_missing_claims_file_is_error(tmp_path):
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hi"]))]
    issues = factcheck.check_claims_signoff(beats, "myreel", tmp_path)
    assert any(i.code == "claims_unverified" for i in issues)


def test_verified_claims_file_passes(tmp_path):
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hi"]))]
    h = factcheck._content_hash(beats)
    claims = tmp_path / "myreel.json"
    claims.write_text(json.dumps({
        "content_hash": h,
        "verified_by": "claude-sonnet-4-6",
        "verified_at": "2026-04-26",
    }), encoding="utf-8")
    assert factcheck.check_claims_signoff(beats, "myreel", tmp_path) == []


def test_legacy_signed_off_by_is_no_longer_accepted(tmp_path):
    """Human signoff field has been removed; only verified_by counts."""
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hi"]))]
    h = factcheck._content_hash(beats)
    claims = tmp_path / "myreel.json"
    claims.write_text(json.dumps({
        "content_hash": h,
        "signed_off_by": "Ken",
        "signed_off_at": "2026-04-26",
    }), encoding="utf-8")
    issues = factcheck.check_claims_signoff(beats, "myreel", tmp_path)
    assert any(i.code == "claims_no_verifier" for i in issues)


def test_stale_signoff_is_error(tmp_path):
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hi"]))]
    claims = tmp_path / "myreel.json"
    claims.write_text(json.dumps({
        "content_hash": "stale_hash_12345",
        "verified_by": "claude-sonnet-4-6",
        "verified_at": "2026-04-25",
    }), encoding="utf-8")
    issues = factcheck.check_claims_signoff(beats, "myreel", tmp_path)
    assert any(i.code == "claims_stale" for i in issues)


def test_missing_verifier_is_error(tmp_path):
    beats = [_beat("a", 1.0, "CHIP", _spec_with_captions(["hi"]))]
    h = factcheck._content_hash(beats)
    claims = tmp_path / "myreel.json"
    claims.write_text(json.dumps({"content_hash": h}), encoding="utf-8")
    issues = factcheck.check_claims_signoff(beats, "myreel", tmp_path)
    assert any(i.code == "claims_no_verifier" for i in issues)


# ───────────────────────────── preflight integration ─────────────────────────────

def test_preflight_runs_factcheck_when_roster_set(
    tmp_path: Path, roster_file: Path, capsys
):
    """When factcheck_roster is provided, preflight.run() should surface
    factcheck issues alongside its own."""
    src = tmp_path / "x.mp4"
    src.write_bytes(b"x")
    spec = {
        "path": src,
        "in_t": 0.0,
        "out_t": 1.0,
        "caption_lines": [(0.0, 1.0, "Donavan Mckinney spoke.")],
    }
    beats = [_beat("a", 30.0, "INTRO", spec)]

    code = preflight.run(
        beats, 30.0,
        rotation_cache_dir=tmp_path / "rot",
        factcheck_roster=roster_file,
        factcheck_require_claims=False,  # no claims dir for this test
    )
    out = capsys.readouterr().out
    assert code == 1  # ERROR from misspelling
    assert "name_misspelled" in out


def test_preflight_no_factcheck_when_roster_unset(tmp_path: Path, capsys):
    """Without factcheck_roster, behavior is unchanged from baseline."""
    src = tmp_path / "x.mp4"
    src.write_bytes(b"x")
    spec = {
        "path": src,
        "in_t": 0.0,
        "out_t": 1.0,
        "caption_lines": [(0.0, 1.0, "Bernie Sanders said.")],
    }
    beats = [_beat("a", 30.0, "INTRO", spec)]

    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 0
    assert "factcheck" not in out
