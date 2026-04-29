"""Word-level phrase search over the source-clip index.

The existing index at `mpc/index/clips/<stem>.json` already carries
word-level timestamps from `mpc_scan_sources.py` (whisper large-v3
+ word_timestamps=True). This module is a thin reader on top of it:
exposes `WordIndex.words_in_window()` for time-based lookups and
`find_phrase()` for "where in this clip does the speaker say X?"
queries.

The `start`/`end` per word lands within ~50-100ms of true onset
and is the *coarse* boundary that `cvs_lib.clip_snap` then refines
to a silence-aligned, zero-cross-snapped cut.

Read-only — re-indexing is `mpc_scan_sources.py`'s job.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Union

from cvs_lib.index import DEFAULT_INDEX_DIR, load_clip_index

PathLike = Union[str, Path]

_TOKEN_RX = re.compile(r"[\w']+", re.UNICODE)


def _norm_token(s: str) -> str:
    """Lowercase + strip punctuation + drop diacritics. Used for matching."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    m = _TOKEN_RX.search(s.lower())
    return m.group(0) if m else ""


def _tokenize(text: str) -> List[str]:
    return [t for t in (_norm_token(x) for x in _TOKEN_RX.findall(text)) if t]


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _tokens_close(a: str, b: str) -> bool:
    """True if `a` and `b` are the same token modulo a small char-level
    edit distance — handles whisper mistranscriptions ("abolosh"/"abolish")
    and apostrophe drops ("don't"/"dont")."""
    if a == b:
        return True
    a2, b2 = a.replace("'", ""), b.replace("'", "")
    if a2 == b2:
        return True
    L = max(len(a2), len(b2))
    if L < 4:
        # Too short — demand exact match. Single-char typos in 3-letter
        # words are too easily "and"/"any"/"add" — false-positive risk.
        return False
    return _edit_distance(a2, b2) <= max(1, L // 4)


def _seq_edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Token-level Levenshtein with char-aware substitution cost.

    Two tokens that are within ~1 char edit per 4 chars cost 0 to swap;
    otherwise cost 1. Lets fuzzy phrase search ride through whisper
    mistranscriptions without inflating the edit total.
    """
    if list(a) == list(b):
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ta in enumerate(a, 1):
        curr = [i]
        for j, tb in enumerate(b, 1):
            cost = 0 if _tokens_close(ta, tb) else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    word: str          # raw text (may carry punctuation)
    norm: str          # normalized form used for matching
    seg_idx: int       # which transcript segment this word came from

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class PhraseMatch:
    stem: str
    start_t: float       # first word's start
    end_t: float         # last word's end
    words: List[Word]
    matched_text: str    # joined original `word` text
    score: float         # 1.0 = exact; <1.0 = fuzzy

    @property
    def duration(self) -> float:
        return self.end_t - self.start_t


@dataclass
class WordIndex:
    """Flat list of timestamped words for one source clip."""
    stem: str
    words: List[Word]

    @classmethod
    def load(cls, stem: str, index_dir: PathLike = DEFAULT_INDEX_DIR) -> "WordIndex":
        data = load_clip_index(stem, index_dir)
        segments = data.get("transcript", {}).get("segments", [])
        flat: List[Word] = []
        for i, seg in enumerate(segments):
            for w in seg.get("words", []):
                raw = (w.get("word") or "").strip()
                norm = _norm_token(raw)
                if not norm:
                    continue
                flat.append(Word(
                    start=float(w["start"]),
                    end=float(w["end"]),
                    word=raw,
                    norm=norm,
                    seg_idx=i,
                ))
        return cls(stem=stem, words=flat)

    def words_in_window(self, t0: float, t1: float) -> List[Word]:
        """Words whose interval overlaps [t0, t1)."""
        if t1 <= t0:
            return []
        return [w for w in self.words if w.start < t1 and w.end > t0]

    def find_phrase(
        self,
        text: str,
        *,
        fuzzy: bool = True,
        max_edits: int = 2,
        min_score: float = 0.6,
    ) -> List[PhraseMatch]:
        """Locate `text` in the word stream.

        Two-pass:
          1. Exact contiguous match (no edits).
          2. If `fuzzy`, sliding window of length |target|±2 with token-
             level edit distance ≤ `max_edits`.

        Score = 1 − edits/max(|target|, |window|). Overlapping matches
        collapse to highest-score wins. Returned matches are sorted by
        `start_t` ascending.
        """
        target = _tokenize(text)
        if not target:
            return []
        n_target = len(target)

        # Pass 1: exact contiguous match.
        exact: List[PhraseMatch] = []
        for i in range(len(self.words) - n_target + 1):
            window = self.words[i:i + n_target]
            if [w.norm for w in window] == target:
                exact.append(PhraseMatch(
                    stem=self.stem,
                    start_t=window[0].start,
                    end_t=window[-1].end,
                    words=list(window),
                    matched_text=" ".join(w.word for w in window),
                    score=1.0,
                ))
        if exact or not fuzzy:
            return _dedup_overlapping(exact)

        # Pass 2: fuzzy sliding window.
        fuzzy_matches: List[PhraseMatch] = []
        max_window = n_target + 2
        min_window = max(1, n_target - 2)
        for i in range(len(self.words)):
            for L in range(min_window, max_window + 1):
                end = i + L
                if end > len(self.words):
                    break
                window = self.words[i:end]
                edits = _seq_edit_distance([w.norm for w in window], target)
                if edits > max_edits:
                    continue
                score = 1.0 - edits / max(n_target, L)
                if score < min_score:
                    continue
                fuzzy_matches.append(PhraseMatch(
                    stem=self.stem,
                    start_t=window[0].start,
                    end_t=window[-1].end,
                    words=list(window),
                    matched_text=" ".join(w.word for w in window),
                    score=score,
                ))
        return _dedup_overlapping(fuzzy_matches)

    def text(self) -> str:
        """Joined raw-word text for the whole clip — useful for grep."""
        return " ".join(w.word for w in self.words)


def _dedup_overlapping(matches: List[PhraseMatch]) -> List[PhraseMatch]:
    """Keep highest-scoring per overlap region; tie-break on earlier start."""
    if not matches:
        return []
    matches = sorted(matches, key=lambda m: (-m.score, m.start_t))
    kept: List[PhraseMatch] = []
    for m in matches:
        if not any(_overlaps(m, k) for k in kept):
            kept.append(m)
    kept.sort(key=lambda m: m.start_t)
    return kept


def _overlaps(a: PhraseMatch, b: PhraseMatch) -> bool:
    return a.start_t < b.end_t and a.end_t > b.start_t


def find_phrase_across_stems(
    phrase: str,
    stems: Sequence[str],
    *,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    fuzzy: bool = True,
    max_edits: int = 2,
    min_score: float = 0.6,
) -> List[PhraseMatch]:
    """Search a phrase across many stems. Returns matches sorted by score
    descending, then stem, then start_t — most-confident-first.
    """
    out: List[PhraseMatch] = []
    for stem in stems:
        try:
            wi = WordIndex.load(stem, index_dir)
        except FileNotFoundError:
            continue
        out.extend(wi.find_phrase(
            phrase, fuzzy=fuzzy, max_edits=max_edits, min_score=min_score,
        ))
    out.sort(key=lambda m: (-m.score, m.stem, m.start_t))
    return out


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m cvs_lib.word_index",
        description="Search a phrase in the MPC word index.",
    )
    ap.add_argument("phrase", help="The phrase to find.")
    ap.add_argument("--stem", action="append", default=None,
                    help="Restrict to these stems (repeatable). "
                         "Default: all stems in --index-dir.")
    ap.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    ap.add_argument("--exact", action="store_true",
                    help="Disable fuzzy matching.")
    ap.add_argument("--max-edits", type=int, default=2)
    ap.add_argument("--min-score", type=float, default=0.6)
    args = ap.parse_args()

    if args.stem:
        stems = args.stem
    else:
        stems = sorted(
            p.stem for p in Path(args.index_dir).glob("*.json")
            if not p.stem.startswith("_")
        )

    matches = find_phrase_across_stems(
        args.phrase, stems,
        index_dir=args.index_dir,
        fuzzy=not args.exact,
        max_edits=args.max_edits,
        min_score=args.min_score,
    )
    if not matches:
        print(f"no matches for {args.phrase!r} across {len(stems)} stems")
        return 1
    for m in matches:
        print(f"  {m.stem}  {m.start_t:7.3f}-{m.end_t:7.3f}  "
              f"score={m.score:.2f}  {m.matched_text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
