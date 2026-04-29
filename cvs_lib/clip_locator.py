"""End-to-end clip resolver: phrase + stem -> beat-ready dict.

Composes `cvs_lib.word_index` (coarse word boundaries from whisper) and
`cvs_lib.clip_snap` (silence-aware refinement). The result is a dict
that drops directly into a reel script's BEATS list with `path`,
`in_t`, `out_t`, plus a `snap_quality` block that reports how clean
the cut is (RMS at the edges, deltas from the word-index seed, whether
either edge landed in audible energy).

Headless. No human in the loop. Use it from a reel script's pre-render
pass to resolve `phrase=` keys into `in_t`/`out_t` automatically.

CLI:
    python -m cvs_lib.clip_locator <stem> "we don't back down"
    python -m cvs_lib.clip_locator --all-stems "abolish ICE"
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from cvs_lib.clip_snap import (
    DEFAULT_LEAD_PAD_MS,
    DEFAULT_MIN_SNR_DB,
    DEFAULT_SEARCH_MS,
    DEFAULT_TRAIL_PAD_MS,
    SnapResult,
    snap_boundaries,
)
from cvs_lib.index import DEFAULT_INDEX_DIR, load_clip_index
from cvs_lib.word_index import PhraseMatch, WordIndex, find_phrase_across_stems

PathLike = Union[str, Path]

DEFAULT_RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")


@dataclass
class ClipResolution:
    """One phrase → one cut, refined."""
    stem: str
    phrase: str
    matched_text: str
    match_score: float           # word-index match confidence (1.0 = exact)
    path: str                    # absolute path to the source video/audio
    in_t: float                  # snap-refined cut-in
    out_t: float                 # snap-refined cut-out
    duration: float              # out_t - in_t
    candidate_in_t: float        # word-index seed before snap
    candidate_out_t: float
    in_rms_db: float             # RMS at the cut-in (lower = cleaner)
    out_rms_db: float
    in_voice: bool               # cut lands in audible energy (warning)
    out_voice: bool
    in_delta_ms: float           # snap motion: snapped - candidate
    out_delta_ms: float
    speech_rms_db: float         # median RMS during voiced cut frames
    noise_rms_db: float          # median RMS of non-voiced source frames
    snr_db: float                # speech_rms_db - noise_rms_db
    voice_pct: float             # % of cut frames flagged voice by VAD
    is_off_mic: bool             # snr_db < min_snr_db threshold

    def to_beat_dict(self) -> Dict:
        """Reduce to the keys a reel BEATS entry typically uses."""
        return {
            "path": Path(self.path).name,
            "in_t": round(self.in_t, 3),
            "out_t": round(self.out_t, 3),
            "phrase": self.phrase,
            "snap_quality": {
                "score": round(self.match_score, 2),
                "in_rms_db": round(self.in_rms_db, 1),
                "out_rms_db": round(self.out_rms_db, 1),
                "in_voice": self.in_voice,
                "out_voice": self.out_voice,
                "delta_in_ms": round(self.in_delta_ms),
                "delta_out_ms": round(self.out_delta_ms),
                "speech_rms_db": round(self.speech_rms_db, 1),
                "noise_rms_db": round(self.noise_rms_db, 1),
                "snr_db": round(self.snr_db, 1),
                "voice_pct": round(self.voice_pct, 1),
                "is_off_mic": self.is_off_mic,
            },
        }

    def quality_summary(self) -> str:
        flags = []
        if self.is_off_mic:
            flags.append(f"OFF-MIC({self.snr_db:+.1f}dB)")
        if self.in_voice:
            flags.append("IN_VOICE")
        if self.out_voice:
            flags.append("OUT_VOICE")
        if self.match_score < 1.0:
            flags.append(f"FUZZY({self.match_score:.2f})")
        flag_str = f"  [{' '.join(flags)}]" if flags else ""
        return (
            f"{self.stem}  {self.in_t:.3f}-{self.out_t:.3f} "
            f"({self.duration:.3f}s)  "
            f"SNR{self.snr_db:+.1f}  "
            f"{self.in_rms_db:+.1f}/{self.out_rms_db:+.1f} dB  "
            f"d{self.in_delta_ms:+.0f}/{self.out_delta_ms:+.0f}ms"
            f"{flag_str}"
        )


def _resolve_audio_path(stem: str,
                        raw_dir: PathLike,
                        index_dir: PathLike) -> Path:
    """Try to find the source video for a stem — index meta first,
    then raw_dir/<stem>.{mp4,mov}. Raise if neither resolves."""
    try:
        data = load_clip_index(stem, index_dir)
        meta_path = data.get("meta", {}).get("path")
        if meta_path and Path(meta_path).exists():
            return Path(meta_path)
    except FileNotFoundError:
        pass
    raw_dir = Path(raw_dir)
    for ext in (".mp4", ".MP4", ".mov", ".MOV"):
        p = raw_dir / f"{stem}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(
        f"could not resolve source video for stem {stem!r}; "
        f"checked index meta + {raw_dir}"
    )


def locate_phrase_clip(
    stem: str,
    phrase: str,
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    fuzzy: bool = True,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_score: float = 0.6,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    skip_off_mic: bool = True,
) -> Optional[ClipResolution]:
    """Locate `phrase` in `stem`'s word index, snap the cut, return one
    `ClipResolution` (the highest-scoring match) or None if no match.

    `min_snr_db` defines the speech-vs-noise floor; matches below it are
    flagged `is_off_mic=True`. With `skip_off_mic=True` (default), the
    function walks matches in score order and returns the first that
    passes; if all fail, returns None. With `skip_off_mic=False`, returns
    the best match regardless and the caller can read `is_off_mic`.
    """
    wi = WordIndex.load(stem, index_dir)
    matches = wi.find_phrase(phrase, fuzzy=fuzzy, min_score=min_score)
    if not matches:
        return None
    audio_path = _resolve_audio_path(stem, raw_dir, index_dir)
    # Walk in score order, earliest tie-break.
    ordered = sorted(matches, key=lambda m: (-m.score, m.start_t))
    first: Optional[ClipResolution] = None
    for m in ordered:
        res = _resolve_match(
            m, audio_path,
            lead_pad_ms=lead_pad_ms,
            trail_pad_ms=trail_pad_ms,
            search_ms=search_ms,
            min_snr_db=min_snr_db,
            word_index=wi,
        )
        if first is None:
            first = res
        if not res.is_off_mic:
            return res
    return None if skip_off_mic else first


def locate_phrase_clip_all(
    stem: str,
    phrase: str,
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    fuzzy: bool = True,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_score: float = 0.6,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    skip_off_mic: bool = False,
) -> List[ClipResolution]:
    """Resolve every match of `phrase` in `stem`. Useful when the same
    line is repeated (chants) and you want to pick one to use.

    `skip_off_mic` defaults False here — callers asking for "all" usually
    want to see the off-mic matches too (and decide for themselves)."""
    wi = WordIndex.load(stem, index_dir)
    matches = wi.find_phrase(phrase, fuzzy=fuzzy, min_score=min_score)
    if not matches:
        return []
    audio_path = _resolve_audio_path(stem, raw_dir, index_dir)
    out = [
        _resolve_match(
            m, audio_path,
            lead_pad_ms=lead_pad_ms,
            trail_pad_ms=trail_pad_ms,
            search_ms=search_ms,
            min_snr_db=min_snr_db,
            word_index=wi,
        )
        for m in matches
    ]
    if skip_off_mic:
        out = [r for r in out if not r.is_off_mic]
    return out


def locate_phrase_across_stems(
    phrase: str,
    stems: Sequence[str],
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    fuzzy: bool = True,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_score: float = 0.6,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    skip_off_mic: bool = False,
) -> List[ClipResolution]:
    """Search a phrase across many stems; return all matches (any
    confidence ≥ min_score) snap-refined and sorted by quality.

    Sort key: highest SNR first (off-mic clips sink), then lowest mean
    edge RMS, then highest match score, then earliest stem/start.
    """
    matches = find_phrase_across_stems(
        phrase, stems,
        index_dir=index_dir,
        fuzzy=fuzzy,
        min_score=min_score,
    )
    out: List[ClipResolution] = []
    wi_cache: Dict[str, WordIndex] = {}
    for m in matches:
        try:
            audio_path = _resolve_audio_path(m.stem, raw_dir, index_dir)
        except FileNotFoundError:
            continue
        wi = wi_cache.get(m.stem)
        if wi is None:
            try:
                wi = WordIndex.load(m.stem, index_dir)
                wi_cache[m.stem] = wi
            except FileNotFoundError:
                pass
        out.append(_resolve_match(
            m, audio_path,
            lead_pad_ms=lead_pad_ms,
            trail_pad_ms=trail_pad_ms,
            search_ms=search_ms,
            min_snr_db=min_snr_db,
            word_index=wi,
        ))
    if skip_off_mic:
        out = [r for r in out if not r.is_off_mic]
    # Quality sort: best SNR first (so off-mic sinks even if RMS is low),
    # then cleanest edges, then highest match score, then earliest.
    out.sort(key=lambda r: (
        -r.snr_db,
        0.5 * (r.in_rms_db + r.out_rms_db),
        -r.match_score,
        r.stem,
        r.in_t,
    ))
    return out


def _adjacent_word_bounds(
    wi: WordIndex, in_t: float, out_t: float,
) -> tuple:
    """Return `(prev_word_end_t, next_word_start_t)` — the boundaries
    of the words immediately before/after the matched phrase in the
    index. Either may be None if the phrase sits at a file edge.

    Used to clamp lead/trail extension when whisper reports a real
    inter-word gap (e.g., a 1.3-second pause before "$254 million").
    """
    prev_end = None
    next_start = None
    for w in wi.words:
        if w.end <= in_t:
            prev_end = w.end
        elif w.start >= out_t and next_start is None:
            next_start = w.start
            break
    return prev_end, next_start


def _resolve_match(
    match: PhraseMatch,
    audio_path: Path,
    *,
    lead_pad_ms: float,
    trail_pad_ms: float,
    search_ms: float,
    min_snr_db: float,
    word_index: Optional[WordIndex] = None,
) -> ClipResolution:
    prev_end_t = next_start_t = None
    if word_index is not None:
        prev_end_t, next_start_t = _adjacent_word_bounds(
            word_index, match.start_t, match.end_t,
        )
    snap = snap_boundaries(
        audio_path,
        match.start_t,
        match.end_t,
        lead_pad_ms=lead_pad_ms,
        trail_pad_ms=trail_pad_ms,
        search_ms=search_ms,
        min_snr_db=min_snr_db,
        prev_word_end_t=prev_end_t,
        next_word_start_t=next_start_t,
    )
    q = snap.quality
    return ClipResolution(
        stem=match.stem,
        phrase=match.matched_text,  # original text, not the input
        matched_text=match.matched_text,
        match_score=match.score,
        path=str(audio_path),
        in_t=snap.in_t,
        out_t=snap.out_t,
        duration=snap.duration,
        candidate_in_t=match.start_t,
        candidate_out_t=match.end_t,
        in_rms_db=snap.in_snap.rms_db,
        out_rms_db=snap.out_snap.rms_db,
        in_voice=snap.in_snap.in_voice,
        out_voice=snap.out_snap.in_voice,
        in_delta_ms=snap.in_snap.delta_ms,
        out_delta_ms=snap.out_snap.delta_ms,
        speech_rms_db=q.speech_rms_db,
        noise_rms_db=q.noise_rms_db,
        snr_db=q.snr_db,
        voice_pct=q.voice_pct,
        is_off_mic=q.is_off_mic,
    )


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m cvs_lib.clip_locator",
        description="Resolve a phrase to a snap-refined cut.",
    )
    ap.add_argument("phrase", help="The phrase to locate.")
    ap.add_argument("--stem", action="append", default=None,
                    help="Restrict to these stems (repeatable). "
                         "Default: all stems in --index-dir.")
    ap.add_argument("--all", action="store_true",
                    help="Return every match in the chosen stem(s), not "
                         "just the best one.")
    ap.add_argument("--exact", action="store_true",
                    help="Disable fuzzy matching.")
    ap.add_argument("--min-score", type=float, default=0.6)
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    ap.add_argument("--lead-pad-ms", type=float, default=DEFAULT_LEAD_PAD_MS)
    ap.add_argument("--trail-pad-ms", type=float, default=DEFAULT_TRAIL_PAD_MS)
    ap.add_argument("--search-ms", type=float, default=DEFAULT_SEARCH_MS)
    ap.add_argument("--min-snr-db", type=float, default=DEFAULT_MIN_SNR_DB,
                    help="Reject cuts where speech RMS minus noise RMS "
                         "is below this. Default 10 dB.")
    ap.add_argument("--keep-off-mic", action="store_true",
                    help="Don't filter off-mic matches; flag them instead.")
    ap.add_argument("--json", action="store_true",
                    help="Emit beat-ready dicts as JSON instead of "
                         "human-readable summary.")
    args = ap.parse_args()

    if args.stem:
        stems = args.stem
    else:
        stems = sorted(
            p.stem for p in Path(args.index_dir).glob("*.json")
            if not p.stem.startswith("_")
        )

    common = dict(
        raw_dir=args.raw_dir,
        index_dir=args.index_dir,
        fuzzy=not args.exact,
        min_score=args.min_score,
        lead_pad_ms=args.lead_pad_ms,
        trail_pad_ms=args.trail_pad_ms,
        search_ms=args.search_ms,
        min_snr_db=args.min_snr_db,
        skip_off_mic=not args.keep_off_mic,
    )

    if args.all:
        results: List[ClipResolution] = []
        for stem in stems:
            results.extend(locate_phrase_clip_all(stem, args.phrase, **common))
    else:
        results = locate_phrase_across_stems(args.phrase, stems, **common)

    if not results:
        print(f"no matches for {args.phrase!r}")
        return 1

    if args.json:
        print(json.dumps([r.to_beat_dict() for r in results], indent=2))
    else:
        for r in results:
            print(f"  {r.quality_summary()}  {r.matched_text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
