"""Pre-render validation for MPC reel scripts.

Two tiers:
- ERROR  — hard fail (missing source, beat-sum mismatch). Exits 1.
- WARN   — soft (in_t may land mid-word per the index). Print + continue.
           Promoted to ERROR when `strict=True`.

Each validator is a pure function returning a list of `Issue`s. The
`run()` orchestrator collects, prints, and decides exit.

Beat tuple shape (from scripts/mpc_ep_*.py):
    (slug, dur, chord_key, chip_label, spec)
where spec is a dict with at least {"path", "in_t", "out_t"}.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


ERROR = "ERROR"
WARN = "WARN"


@dataclass(frozen=True)
class Issue:
    severity: str  # ERROR or WARN
    code: str
    message: str

    def format(self) -> str:
        return f"[preflight {self.severity}] {self.code}: {self.message}"


Beat = Tuple[str, float, str, str, dict]


def _spec_path(spec: dict) -> Path:
    return Path(spec["path"])


def assert_sources_exist(beats: Sequence[Beat]) -> List[Issue]:
    """Every beat's source file must exist on disk."""
    issues: List[Issue] = []
    seen = set()
    for slug, _dur, _chord, _label, spec in beats:
        if spec is None:
            continue
        path = _spec_path(spec)
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            issues.append(Issue(
                ERROR, "source_missing",
                f"beat '{slug}': source file does not exist: {path}"
            ))
    return issues


def assert_beats_sum_to_duration(
    beats: Sequence[Beat], target_duration: float, tol: float = 1e-6,
) -> List[Issue]:
    """Sum of beat durations must equal target (within tol)."""
    s = sum(float(b[1]) for b in beats)
    if not math.isclose(s, target_duration, abs_tol=tol):
        return [Issue(
            ERROR, "duration_mismatch",
            f"sum(beat durations)={s:.3f} != DURATION={target_duration:.3f} "
            f"(delta={s - target_duration:+.3f}s)"
        )]
    return []


def assert_in_out_ordering(beats: Sequence[Beat]) -> List[Issue]:
    """For every beat, in_t < out_t and both are non-negative."""
    issues: List[Issue] = []
    for slug, _dur, _chord, _label, spec in beats:
        if spec is None:
            continue
        in_t = float(spec.get("in_t", 0.0))
        out_t = float(spec.get("out_t", 0.0))
        if in_t < 0 or out_t < 0:
            issues.append(Issue(
                ERROR, "negative_time",
                f"beat '{slug}': in_t={in_t} out_t={out_t} cannot be negative"
            ))
        if not in_t < out_t:
            issues.append(Issue(
                ERROR, "in_out_ordering",
                f"beat '{slug}': in_t={in_t} >= out_t={out_t}"
            ))
    return issues


def assert_rotation_cache_writable(
    beats: Sequence[Beat], cache_dir: Path,
) -> List[Issue]:
    """The rotation-cache directory must exist or be creatable."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return [Issue(
            ERROR, "rotation_cache_unwritable",
            f"cannot create/write rotation cache dir {cache_dir}: {e}"
        )]
    if not os.access(cache_dir, os.W_OK):
        return [Issue(
            ERROR, "rotation_cache_unwritable",
            f"rotation cache dir not writable: {cache_dir}"
        )]
    return []


def assert_caption_windows_in_beat(beats: Sequence[Beat]) -> List[Issue]:
    """Caption start/end times must fall within the beat duration."""
    issues: List[Issue] = []
    for slug, dur, _chord, _label, spec in beats:
        if spec is None:
            continue
        for line in spec.get("caption_lines") or []:
            try:
                s, e, _txt = line
            except (TypeError, ValueError):
                continue
            if s < 0 or e > float(dur) + 1e-6 or s >= e:
                issues.append(Issue(
                    WARN, "caption_window",
                    f"beat '{slug}' (dur={dur}): caption window "
                    f"({s:.2f}, {e:.2f}) is outside beat or invalid"
                ))
    return issues


def run(
    beats: Sequence[Beat],
    target_duration: float,
    rotation_cache_dir: Path = Path("E:/AI/CVS/ComfyUI/output/mpc/_rot_cache"),
    strict: bool = False,
) -> int:
    """Run all validators and return an exit code (0 OK, 1 fatal).

    Hard errors exit 1. Warnings exit 1 only when strict=True.
    Prints all issues regardless.
    """
    issues: List[Issue] = []
    issues += assert_sources_exist(beats)
    issues += assert_beats_sum_to_duration(beats, target_duration)
    issues += assert_in_out_ordering(beats)
    issues += assert_rotation_cache_writable(beats, rotation_cache_dir)
    issues += assert_caption_windows_in_beat(beats)

    for i in issues:
        print(i.format())

    has_error = any(i.severity == ERROR for i in issues)
    has_warn = any(i.severity == WARN for i in issues)

    if has_error or (strict and has_warn):
        return 1
    return 0


def run_or_exit(
    beats: Sequence[Beat],
    target_duration: float,
    rotation_cache_dir: Path = Path("E:/AI/CVS/ComfyUI/output/mpc/_rot_cache"),
    strict: bool = False,
) -> None:
    """Convenience wrapper for scripts: exits process on failure."""
    code = run(beats, target_duration, rotation_cache_dir, strict)
    if code != 0:
        sys.exit(code)
