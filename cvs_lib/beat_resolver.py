"""Phrase-driven beat resolution for MPC reel scripts.

Today MPC scripts hard-code `(in_t, out_t)` per beat from the transcript
index. Editorial picks live in code as magic numbers; if whisper re-runs
and timestamps shift, every reel breaks silently.

This module lets a beat spec say `phrase="So this is from Juan"` and
have `in_t` / `out_t` resolved at render time via
`cvs_lib.clip_locator.locate_phrase_clip`. Cuts become self-healing
against re-transcription, edits read like editorial ("the 254 million
line") not arithmetic ("21.28 to 22.18"), and off-mic / fuzzy-match
warnings surface in the existing preflight fail-fast path.

## Resolution semantics

For each beat spec dict:

- `phrase` absent → pass-through, no changes.
- `phrase` set, `in_t`/`out_t` both also set → static values WIN. Phrase
  treated as documentation only; resolver still runs the locator and
  warns if the static cut and the phrase resolution disagree by > 100ms
  (signals: index drift after re-transcription).
- `phrase` set, `in_t` and/or `out_t` missing → those keys are filled
  in from the locator. Off-mic / fuzzy-match → WARN.
- `phrase` set, no `path` → ERROR (resolver requires an explicit stem
  anchor; cross-stem search lives in `find_phrase.py`, not here).

Beat tuple shape (unchanged): `(slug, dur, chord_key, chip_label, spec)`.
A multi-shot spec (`spec` is a list of dicts) gets each sub-spec
resolved independently.

The reel script's `dur` is *not* touched. If the resolved cut duration
disagrees with `dur`, the resolver emits a WARN — editorial chooses
whether to retune `dur` or accept whisper's idea of how long the line is.

## API

    from cvs_lib.beat_resolver import resolve_beats

    resolved, issues = resolve_beats(BEATS, raw_dir=RAW_DIR)
    for i in issues:
        print(i.format())
    BEATS = resolved  # use these for render

Pure: no stdout, no sys.exit. Caller owns reporting + flow control.
Preflight wires this in via `assert_phrases_resolve()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from cvs_lib.clip_locator import (
    DEFAULT_RAW_DIR,
    ClipResolution,
    locate_phrase_clip,
)
from cvs_lib.clip_snap import (
    DEFAULT_LEAD_PAD_MS,
    DEFAULT_MIN_SNR_DB,
    DEFAULT_SEARCH_MS,
    DEFAULT_TRAIL_PAD_MS,
)
from cvs_lib.index import DEFAULT_INDEX_DIR


ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

# A static (in_t, out_t) cut that disagrees with the phrase resolution
# by more than this is flagged. Tighter than the snap's own search
# window so it catches real drift, not microscopic rounding.
_STATIC_DRIFT_TOL_MS = 100.0

# When phrase fully drives in_t + out_t, complain if the resulting clip
# duration drifts from the beat's editorial `dur` by more than this.
_DUR_DRIFT_TOL_MS = 250.0


PathLike = Union[str, Path]
Beat = Tuple[str, float, str, Optional[str], object]


@dataclass(frozen=True)
class ResolutionIssue:
    """Pure data — caller decides whether to print or promote."""
    severity: str   # ERROR | WARN | INFO
    code: str
    beat_slug: str
    message: str

    def format(self) -> str:
        return (
            f"[beat-resolver {self.severity}] {self.code} "
            f"({self.beat_slug}): {self.message}"
        )


# --------------------------------------------------------------------------- #
# Per-spec resolution
# --------------------------------------------------------------------------- #

def resolve_spec(
    slug: str,
    spec: dict,
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    beat_dur: Optional[float] = None,
) -> Tuple[dict, List[ResolutionIssue]]:
    """Resolve one beat spec dict.

    Returns a copy of `spec` with `in_t`/`out_t` filled (when applicable)
    and a list of resolution issues. The original spec is never mutated.
    """
    if "phrase" not in spec:
        return dict(spec), []

    phrase: str = spec["phrase"]
    new = dict(spec)
    issues: List[ResolutionIssue] = []

    if "path" not in spec:
        issues.append(ResolutionIssue(
            ERROR, "phrase_no_path", slug,
            f"phrase={phrase!r} but spec has no 'path' to anchor the stem."
        ))
        return new, issues

    src_path = Path(spec["path"])
    stem = src_path.stem
    # The locator's _resolve_audio_path tries the index meta first then
    # falls back to <raw_dir>/<stem>.{mp4,mov}. Pass the actual parent
    # of `path` as raw_dir so the fallback works even when our beat's
    # source isn't in the locator's default rally directory.
    res = locate_phrase_clip(
        stem,
        phrase,
        raw_dir=src_path.parent,
        index_dir=index_dir,
        lead_pad_ms=lead_pad_ms,
        trail_pad_ms=trail_pad_ms,
        search_ms=search_ms,
        min_snr_db=min_snr_db,
        skip_off_mic=False,  # we want the result + the off_mic flag
    )
    if res is None:
        issues.append(ResolutionIssue(
            ERROR, "phrase_not_found", slug,
            f"phrase={phrase!r} did not match in stem {stem!r}."
        ))
        return new, issues

    has_in = "in_t" in spec
    has_out = "out_t" in spec

    if has_in and has_out:
        # Static cut wins; phrase is documentation. Still flag if the
        # static and resolved cuts disagree — that's index drift the
        # editor probably wants to know about.
        static_in = float(spec["in_t"])
        static_out = float(spec["out_t"])
        in_drift = abs((res.in_t - static_in) * 1000.0)
        out_drift = abs((res.out_t - static_out) * 1000.0)
        if in_drift > _STATIC_DRIFT_TOL_MS or out_drift > _STATIC_DRIFT_TOL_MS:
            issues.append(ResolutionIssue(
                WARN, "static_drift", slug,
                f"phrase={phrase!r} resolves to "
                f"{res.in_t:.3f}-{res.out_t:.3f} but spec is fixed at "
                f"{static_in:.3f}-{static_out:.3f} "
                f"(d_in={res.in_t - static_in:+.3f}s, "
                f"d_out={res.out_t - static_out:+.3f}s)."
            ))
        # Carry the resolution forensics regardless.
        new["_phrase_resolution"] = _forensics(res, used="static")
        return new, issues

    # Phrase fills the missing edges.
    if not has_in:
        new["in_t"] = round(res.in_t, 3)
    if not has_out:
        new["out_t"] = round(res.out_t, 3)
    new["_phrase_resolution"] = _forensics(res, used="phrase")

    if res.is_off_mic:
        issues.append(ResolutionIssue(
            WARN, "off_mic", slug,
            f"phrase={phrase!r} resolved at "
            f"SNR{res.snr_db:+.1f}dB (< floor {min_snr_db:+.1f}dB) — "
            f"clip will sound off-mic. Consider a different stem or rescue."
        ))
    if res.match_score < 1.0:
        issues.append(ResolutionIssue(
            INFO, "fuzzy_match", slug,
            f"phrase={phrase!r} fuzzy-matched (score={res.match_score:.2f}, "
            f"text={res.matched_text!r})."
        ))

    if beat_dur is not None and not has_in and not has_out:
        resolved_dur = res.out_t - res.in_t
        if abs(resolved_dur - float(beat_dur)) * 1000.0 > _DUR_DRIFT_TOL_MS:
            issues.append(ResolutionIssue(
                WARN, "dur_drift", slug,
                f"phrase={phrase!r} resolved to {resolved_dur:.3f}s but "
                f"beat dur is {float(beat_dur):.3f}s "
                f"(d={resolved_dur - float(beat_dur):+.3f}s). "
                f"Either retune `dur=` or hard-pin in_t/out_t."
            ))

    return new, issues


def _forensics(res: ClipResolution, *, used: str) -> dict:
    """Compact resolution metadata for downstream debug + posting markdown."""
    return {
        "phrase": res.phrase,
        "matched_text": res.matched_text,
        "match_score": round(res.match_score, 2),
        "resolved_in_t": round(res.in_t, 3),
        "resolved_out_t": round(res.out_t, 3),
        "snr_db": round(res.snr_db, 1),
        "is_off_mic": res.is_off_mic,
        "in_voice": res.in_voice,
        "out_voice": res.out_voice,
        "used": used,  # "phrase" | "static"
    }


# --------------------------------------------------------------------------- #
# Whole-BEATS resolution
# --------------------------------------------------------------------------- #

def resolve_beats(
    beats: Sequence[Beat],
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
) -> Tuple[List[Beat], List[ResolutionIssue]]:
    """Resolve every phrase= spec in a BEATS list.

    Returns `(resolved_beats, issues)`. Multi-shot specs (spec is a list
    of dicts) get each sub-spec resolved independently. Tuples without a
    dict spec (e.g. `(slug, dur, chord, label, None)`) pass through.
    """
    out: List[Beat] = []
    issues: List[ResolutionIssue] = []
    for beat in beats:
        slug, dur, chord, label, spec = beat
        if isinstance(spec, list):
            new_subs = []
            for sub in spec:
                if isinstance(sub, dict):
                    ns, sub_issues = resolve_spec(
                        slug, sub,
                        raw_dir=raw_dir,
                        index_dir=index_dir,
                        lead_pad_ms=lead_pad_ms,
                        trail_pad_ms=trail_pad_ms,
                        search_ms=search_ms,
                        min_snr_db=min_snr_db,
                        beat_dur=None,  # multi-shot: dur is the SUM, not per-shot
                    )
                    new_subs.append(ns)
                    issues.extend(sub_issues)
                else:
                    new_subs.append(sub)
            out.append((slug, dur, chord, label, new_subs))
        elif isinstance(spec, dict):
            ns, sub_issues = resolve_spec(
                slug, spec,
                raw_dir=raw_dir,
                index_dir=index_dir,
                lead_pad_ms=lead_pad_ms,
                trail_pad_ms=trail_pad_ms,
                search_ms=search_ms,
                min_snr_db=min_snr_db,
                beat_dur=float(dur) if dur is not None else None,
            )
            out.append((slug, dur, chord, label, ns))
            issues.extend(sub_issues)
        else:
            out.append(beat)
    return out, issues


def has_phrases(beats: Sequence[Beat]) -> bool:
    """True if any beat in the list uses `phrase=` resolution. Cheap
    helper for callers that want to short-circuit when no resolution
    is needed (e.g. legacy pre-migration reels)."""
    for _, _, _, _, spec in beats:
        if isinstance(spec, dict) and "phrase" in spec:
            return True
        if isinstance(spec, list):
            for sub in spec:
                if isinstance(sub, dict) and "phrase" in sub:
                    return True
    return False


# --------------------------------------------------------------------------- #
# Convenience wrapper for reel scripts
# --------------------------------------------------------------------------- #

def resolve_or_exit(
    beats: Sequence[Beat],
    *,
    raw_dir: PathLike = DEFAULT_RAW_DIR,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
    min_snr_db: float = DEFAULT_MIN_SNR_DB,
    strict: bool = False,
    stream=None,
) -> List[Beat]:
    """Resolve all phrase= specs, print issues, exit on ERROR.

    Reel-script ergonomic wrapper. Returns the resolved BEATS list ready
    for preflight + render. Pass-through fast-path when no spec uses
    `phrase=` (legacy reels stay unchanged).

    `strict=True` promotes WARN to fatal (helpful in CI / batch render).
    `stream` defaults to stderr; pass a StringIO in tests.
    """
    if not has_phrases(beats):
        return list(beats)

    import sys
    out_stream = stream if stream is not None else sys.stderr

    resolved, issues = resolve_beats(
        beats,
        raw_dir=raw_dir,
        index_dir=index_dir,
        lead_pad_ms=lead_pad_ms,
        trail_pad_ms=trail_pad_ms,
        search_ms=search_ms,
        min_snr_db=min_snr_db,
    )
    for i in issues:
        print(i.format(), file=out_stream)

    fatal = any(i.severity == ERROR for i in issues) or (
        strict and any(i.severity == WARN for i in issues)
    )
    if fatal:
        sys.exit(1)
    return resolved
