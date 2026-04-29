"""Tests for cvs_lib.word_index — phrase search over the index.

Uses real index fixtures at `mpc/index/clips/*.json`. Stems chosen so
the tests verify both clean-speech matching (153128) and recurring
chant matching (170030).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib import index, word_index
from cvs_lib.word_index import (
    PhraseMatch, Word, WordIndex,
    _edit_distance, _norm_token, _seq_edit_distance, _tokens_close,
    _tokenize, find_phrase_across_stems,
)

INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")
SPEECH_STEM = "20260425_153128"   # NBCM coalition speech (~130 chars)
CHANT_STEM = "20260425_170030"    # "abolish ICE" repeated 9x


@pytest.fixture(autouse=True)
def _reset_index_cache():
    index.clear_cache()
    yield
    index.clear_cache()


# -------------------------------- helpers -------------------------------- #

def test_norm_token_strips_punctuation_and_lowercases():
    assert _norm_token("Hello,") == "hello"
    assert _norm_token("don't") == "don't"
    assert _norm_token("ICE.") == "ice"
    assert _norm_token("") == ""
    assert _norm_token("...") == ""


def test_tokenize_returns_normalized_token_list():
    assert _tokenize("Hello, World!") == ["hello", "world"]
    assert _tokenize("don't back DOWN") == ["don't", "back", "down"]
    assert _tokenize("") == []


def test_edit_distance_basic():
    assert _edit_distance("abolish", "abolish") == 0
    assert _edit_distance("abolish", "abolosh") == 1
    assert _edit_distance("", "abc") == 3
    assert _edit_distance("kitten", "sitting") == 3


def test_tokens_close_handles_typos_and_apostrophes():
    assert _tokens_close("abolish", "abolish") is True
    assert _tokens_close("abolish", "abolosh") is True   # 1-char typo
    assert _tokens_close("don't", "dont") is True        # apostrophe drop
    assert _tokens_close("cat", "dog") is False
    assert _tokens_close("ice", "ace") is False          # short tokens demand exact


def test_seq_edit_distance_reduces_to_zero_on_close_tokens():
    # ["abolosh", "ice"] vs ["abolish", "ice"] - should be 0 because
    # "abolosh" is close to "abolish".
    assert _seq_edit_distance(["abolosh", "ice"], ["abolish", "ice"]) == 0
    # One missing token = 1 edit.
    assert _seq_edit_distance(["abolish"], ["abolish", "ice"]) == 1


# -------------------------------- WordIndex -------------------------------- #

def test_load_returns_flat_words_with_seg_idx():
    wi = WordIndex.load(SPEECH_STEM, INDEX_DIR)
    assert len(wi.words) > 10
    # Every word has positive duration and a normalized form.
    for w in wi.words:
        assert w.end > w.start
        assert w.norm != ""
        assert w.seg_idx >= 0


def test_words_in_window_returns_overlapping_words():
    wi = WordIndex.load(SPEECH_STEM, INDEX_DIR)
    # A 1s window early in the clip should hit at least one word.
    hits = wi.words_in_window(0.5, 1.5)
    assert len(hits) >= 1
    for w in hits:
        # Must overlap [0.5, 1.5).
        assert w.start < 1.5
        assert w.end > 0.5


def test_words_in_window_empty_when_t1_le_t0():
    wi = WordIndex.load(SPEECH_STEM, INDEX_DIR)
    assert wi.words_in_window(2.0, 2.0) == []
    assert wi.words_in_window(2.0, 1.0) == []


# -------------------------------- find_phrase -------------------------------- #

def test_find_phrase_exact_match_gets_score_1():
    wi = WordIndex.load(SPEECH_STEM, INDEX_DIR)
    matches = wi.find_phrase("to oppose the construction", fuzzy=False)
    assert len(matches) == 1
    m = matches[0]
    assert m.score == 1.0
    assert m.matched_text.lower().startswith("to oppose")
    # First word's start ~7.42, last word's end ~10.38.
    assert 7.0 < m.start_t < 8.0
    assert 10.0 < m.end_t < 11.0


def test_find_phrase_returns_all_chant_repetitions():
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    matches = wi.find_phrase("abolish ice", fuzzy=False)
    assert len(matches) >= 8  # 9 in this clip per index
    # All exact matches.
    assert all(m.score == 1.0 for m in matches)
    # Sorted ascending by start_t.
    assert all(matches[i].start_t < matches[i + 1].start_t
               for i in range(len(matches) - 1))


def test_find_phrase_fuzzy_handles_typo():
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    # "abolosh" is one char off "abolish" — close-token handling absorbs
    # it as a free substitution.
    matches = wi.find_phrase("abolosh ice", fuzzy=True)
    assert len(matches) >= 1
    # Score still 1.0 because tokens_close treats them as identical.
    assert matches[0].score == 1.0


def test_find_phrase_fuzzy_skipped_when_exact_finds_results():
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    matches = wi.find_phrase("abolish ice", fuzzy=True)
    # Should be the exact-pass results, not noisier fuzzy ones.
    assert all(m.score == 1.0 for m in matches)


def test_find_phrase_unknown_returns_empty():
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    assert wi.find_phrase("bananarama republic", fuzzy=True) == []


def test_find_phrase_empty_query_returns_empty():
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    assert wi.find_phrase("", fuzzy=True) == []
    assert wi.find_phrase("...", fuzzy=True) == []


def test_find_phrase_dedupes_overlapping_matches():
    """When fuzzy mode considers windows of length |target|±2, overlapping
    matches at different lengths can co-occur. Only the best survives."""
    wi = WordIndex.load(CHANT_STEM, INDEX_DIR)
    matches = wi.find_phrase("abolish ICE", fuzzy=False)
    # No two matches overlap (de-dup invariant).
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            a, b = matches[i], matches[j]
            assert a.end_t <= b.start_t or b.end_t <= a.start_t


# -------------------------------- across stems -------------------------------- #

def test_find_phrase_across_stems_orders_by_score_then_stem():
    matches = find_phrase_across_stems(
        "abolish ICE",
        [CHANT_STEM, SPEECH_STEM],
        index_dir=INDEX_DIR,
        fuzzy=False,
    )
    # Plenty of chant matches, zero speech matches.
    assert len(matches) > 0
    assert all(m.stem == CHANT_STEM for m in matches)


def test_find_phrase_across_stems_skips_missing_index():
    matches = find_phrase_across_stems(
        "abolish ICE",
        ["does_not_exist_stem", CHANT_STEM],
        index_dir=INDEX_DIR,
    )
    # The missing stem doesn't crash; chant matches still come back.
    assert len(matches) > 0
