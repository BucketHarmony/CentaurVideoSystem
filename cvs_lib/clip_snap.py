"""Silence-aware boundary refinement for clip cuts.

Given a candidate `(audio_path, in_t, out_t)` from the word index, snap
each boundary to the nearest "true silence" between words. Three-stage
cascade:

  1. **silero-vad** — neural VAD at 16 kHz returns voice/non-voice
     intervals. Better than RMS-only at distinguishing speech from
     breath/lip-smack/room tone.
  2. **RMS valley** — within a ±`search_ms` window around the
     candidate, find the deepest RMS minimum that lies *outside* a VAD
     voice interval. That's the silence valley between words (or the
     pre-burst silence in front of a plosive — naturally the cleanest
     cut point).
  3. **Zero-crossing snap** — within ±10 ms of the valley, slide to the
     nearest zero-crossing so the cut doesn't introduce a click.

Asymmetric padding because the human ear treats edges differently:
  - Lead: −20 ms before first word's onset (don't clip the burst).
  - Trail: +80 ms after last word's offset (let natural decay breathe).

This module is fully headless. No human in the loop, no UI.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np

PathLike = Union[str, Path]

# silero-vad operates on 16 kHz mono. We resample once and cache.
_VAD_SR = 16000
_RMS_HOP_MS = 5.0           # 5 ms RMS frames — fine enough for the snap
_RMS_FRAME_MS = 20.0        # 20 ms RMS window
_ZX_SEARCH_MS = 10.0        # zero-crossing search radius around valley
_VAD_THRESHOLD = 0.5        # silero default
_VAD_MIN_SILENCE_MS = 50    # collapse silences shorter than this into voice
_PAD_RMS_RISE_DB = -35.0    # RMS above this is "incoming sound" — pad stops
_NO_SILENCE_DB = -25.0      # If best valley is louder than this, the search
                            # window has no real silence (chant/dense crowd
                            # audio). Trust the candidate as-is.

# Reasonable defaults for the asymmetric pads.
DEFAULT_LEAD_PAD_MS = 20.0
DEFAULT_TRAIL_PAD_MS = 80.0
DEFAULT_SEARCH_MS = 300.0


@dataclass
class BoundarySnap:
    """One side's snap result."""
    side: str               # "in" or "out"
    candidate_t: float      # input time before snap
    snapped_t: float        # output time after VAD/RMS/zero-cross
    rms_db: float           # dB at the cut point (lower=cleaner silence)
    in_voice: bool          # True if snapped_t lies inside a VAD voice region
    delta_ms: float         # snapped_t - candidate_t in ms
    pad_ms: float           # asymmetric pad applied (signed)


@dataclass
class SnapResult:
    """Composite result for both ends of a clip."""
    audio_path: str
    in_t: float             # final, snapped + padded
    out_t: float
    candidate_in_t: float   # input before snap
    candidate_out_t: float
    duration: float         # out_t - in_t
    in_snap: BoundarySnap
    out_snap: BoundarySnap

    def quality_summary(self) -> str:
        """One-line human report: cleaner cuts have lower RMS at edges."""
        return (
            f"in={self.in_t:.3f} ({self.in_snap.rms_db:.1f} dB, "
            f"d{self.in_snap.delta_ms:+.0f} ms"
            f"{', VOICE' if self.in_snap.in_voice else ''}) "
            f"out={self.out_t:.3f} ({self.out_snap.rms_db:.1f} dB, "
            f"d{self.out_snap.delta_ms:+.0f} ms"
            f"{', VOICE' if self.out_snap.in_voice else ''})"
        )


# --------------------------------------------------------------------------- #
# Audio loading
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=8)
def _load_audio_16k(path_str: str) -> np.ndarray:
    """Load `path` as mono float32 at 16 kHz. ffmpeg via subprocess so we
    handle MOV/MP4/whatever uniformly."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", path_str,
        "-f", "f32le", "-ac", "1", "-ar", str(_VAD_SR),
        "-",
    ]
    raw = subprocess.check_output(cmd)
    if not raw:
        raise RuntimeError(f"ffmpeg returned no audio for {path_str}")
    return np.frombuffer(raw, dtype=np.float32).copy()


def clear_cache() -> None:
    """Reset the audio cache (for tests / long-running processes)."""
    _load_audio_16k.cache_clear()


# --------------------------------------------------------------------------- #
# silero-vad
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _silero_model():
    from silero_vad import load_silero_vad
    return load_silero_vad()


def _vad_voice_intervals(audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
    """Return list of (start_s, end_s) speech intervals via silero-vad."""
    from silero_vad import get_speech_timestamps
    import torch

    model = _silero_model()
    tensor = torch.from_numpy(audio)
    ts = get_speech_timestamps(
        tensor, model,
        sampling_rate=sr,
        threshold=_VAD_THRESHOLD,
        min_silence_duration_ms=_VAD_MIN_SILENCE_MS,
        return_seconds=True,
    )
    return [(float(t["start"]), float(t["end"])) for t in ts]


def _is_in_voice(t: float, voice: List[Tuple[float, float]]) -> bool:
    for s, e in voice:
        if s <= t < e:
            return True
        if s > t:
            return False
    return False


def _next_voice_start_after(t: float, voice: List[Tuple[float, float]]) -> Optional[float]:
    """First voice onset strictly after `t`, or None if none."""
    for s, _e in voice:
        if s > t:
            return s
    return None


def _last_voice_end_before(t: float, voice: List[Tuple[float, float]]) -> Optional[float]:
    """Last voice offset strictly before `t`, or None if none."""
    last: Optional[float] = None
    for _s, e in voice:
        if e < t:
            last = e
        else:
            break
    return last


# --------------------------------------------------------------------------- #
# RMS + zero-crossing
# --------------------------------------------------------------------------- #

def _rms_db(samples: np.ndarray) -> float:
    """RMS in dBFS. Empty/silent → -120 dB clip."""
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    if rms <= 1e-7:
        return -120.0
    return 20.0 * math.log10(rms)


def _rms_frame_db(audio: np.ndarray, t: float, sr: int,
                  frame_ms: float = _RMS_FRAME_MS) -> float:
    """RMS dB centered on time `t` over a `frame_ms` window."""
    half = int(0.5 * frame_ms * 1e-3 * sr)
    i = int(t * sr)
    lo = max(0, i - half)
    hi = min(len(audio), i + half)
    return _rms_db(audio[lo:hi])


def _find_silence_valley(
    audio: np.ndarray,
    sr: int,
    candidate_t: float,
    voice: List[Tuple[float, float]],
    *,
    search_back_ms: float,
    search_fwd_ms: float,
) -> Tuple[float, float]:
    """Return `(valley_t, valley_db)` — the deepest non-voice RMS minimum
    in `[candidate_t - search_back_ms, candidate_t + search_fwd_ms]`.

    Asymmetric window so callers can bias the search: IN-side cuts want
    silence *before* the first word (search_back >> search_fwd); OUT-side
    cuts want silence *after* the last word (search_fwd >> search_back).
    A symmetric search drifts the cut into the wrong region (e.g., past
    the first word's consonant onset).

    If every frame in the window is voice, falls back to the absolute
    quietest frame; if even that is louder than `_NO_SILENCE_DB`, the
    function returns the input candidate's actual RMS so the caller can
    see the search produced no useful silence.
    """
    t_lo = max(0.0, candidate_t - search_back_ms * 1e-3)
    t_hi = min(len(audio) / sr, candidate_t + search_fwd_ms * 1e-3)
    if t_hi <= t_lo:
        return candidate_t, _rms_frame_db(audio, candidate_t, sr)

    hop_s = _RMS_HOP_MS * 1e-3
    n_frames = max(1, int(round((t_hi - t_lo) / hop_s)) + 1)
    times = np.linspace(t_lo, t_hi, n_frames)

    best_t = candidate_t
    best_db = math.inf
    best_t_voice = candidate_t
    best_db_voice = math.inf
    for t in times:
        db = _rms_frame_db(audio, float(t), sr)
        in_voice = _is_in_voice(float(t), voice)
        if not in_voice and db < best_db:
            best_db = db
            best_t = float(t)
        if db < best_db_voice:
            best_db_voice = db
            best_t_voice = float(t)
    if best_db == math.inf:
        # Whole window was voice per VAD — use global quietest within the
        # window (RMS sees sub-VAD micro-silences silero misses).
        best_t, best_db = best_t_voice, best_db_voice
    if best_db > _NO_SILENCE_DB:
        # No real silence in the window (continuous chant, dense crowd).
        # Trust the input candidate; report its actual RMS so the caller
        # can see the cut is in voice.
        return candidate_t, _rms_frame_db(audio, candidate_t, sr)
    return best_t, best_db


def _next_rms_rise(
    audio: np.ndarray,
    sr: int,
    t_start: float,
    *,
    max_advance_ms: float,
    threshold_db: float = _PAD_RMS_RISE_DB,
) -> float:
    """Walk forward from `t_start` looking for the first frame with RMS
    above `threshold_db`. Used to clamp trail-pad — silero's ~100ms frame
    size misses sub-VAD inter-word gaps, but RMS sees them clearly.

    Returns the first violating time, or `t_start + max_advance_ms` if no
    rise is found within the budget.
    """
    audio_dur = len(audio) / sr
    end_s = min(audio_dur, t_start + max_advance_ms * 1e-3)
    hop_s = _RMS_HOP_MS * 1e-3
    t = t_start
    while t < end_s:
        if _rms_frame_db(audio, t, sr) > threshold_db:
            return t
        t += hop_s
    return end_s


def _last_rms_rise(
    audio: np.ndarray,
    sr: int,
    t_end: float,
    *,
    max_advance_ms: float,
    threshold_db: float = _PAD_RMS_RISE_DB,
) -> float:
    """Walk backward from `t_end` looking for the last frame with RMS
    above `threshold_db`. Used to clamp lead-pad — never reach back into
    the prior word's tail.
    """
    start_s = max(0.0, t_end - max_advance_ms * 1e-3)
    hop_s = _RMS_HOP_MS * 1e-3
    t = t_end
    while t > start_s:
        if _rms_frame_db(audio, t, sr) > threshold_db:
            return t
        t -= hop_s
    return start_s


def _snap_to_zero_crossing(audio: np.ndarray, sr: int, t: float) -> float:
    """Slide `t` to the nearest zero-crossing within ±_ZX_SEARCH_MS.
    Avoids click artifacts from cutting mid-cycle."""
    half = int(_ZX_SEARCH_MS * 1e-3 * sr)
    i = int(t * sr)
    lo = max(1, i - half)
    hi = min(len(audio) - 1, i + half)
    if hi <= lo:
        return t
    seg = audio[lo:hi + 1]
    # Sign-change indices.
    signs = np.sign(seg)
    # Treat exact 0 as already a crossing.
    zx_idx = np.where(np.diff(signs) != 0)[0]
    zero_idx = np.where(seg == 0)[0]
    candidates = np.concatenate([zx_idx + lo, zero_idx + lo])
    if candidates.size == 0:
        return t
    target_i = i
    best = int(candidates[np.argmin(np.abs(candidates - target_i))])
    return best / sr


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def snap_boundaries(
    audio_path: PathLike,
    in_t: float,
    out_t: float,
    *,
    lead_pad_ms: float = DEFAULT_LEAD_PAD_MS,
    trail_pad_ms: float = DEFAULT_TRAIL_PAD_MS,
    search_ms: float = DEFAULT_SEARCH_MS,
) -> SnapResult:
    """Refine `(in_t, out_t)` by snapping to the nearest silence + zero
    crossing, then apply asymmetric pad.

    Pad convention:
      - Lead pad widens the cut backwards (in_t = snapped - lead_pad).
      - Trail pad widens the cut forwards (out_t = snapped + trail_pad).
    Both default positive — the cut grows slightly so leading bursts
    aren't clipped and trailing decays aren't chopped. Pass 0 to opt
    out, or negative values to tighten.
    """
    if out_t <= in_t:
        raise ValueError(f"out_t ({out_t}) must be > in_t ({in_t})")

    audio_path = str(audio_path)
    audio = _load_audio_16k(audio_path)
    voice = _vad_voice_intervals(audio, _VAD_SR)

    audio_dur = len(audio) / _VAD_SR
    # Buffer so the clamped boundary lands just outside voice, not on its edge.
    _BUF_S = 0.005

    # IN side: snap to silence valley, zero-cross, then back-pad — but never
    # back past the prior word's tail (RMS rise detection, sub-VAD).
    # Asymmetric search: mostly look backward (silence before first word).
    valley_t_in, valley_db_in = _find_silence_valley(
        audio, _VAD_SR, in_t, voice,
        search_back_ms=search_ms,
        search_fwd_ms=search_ms * 0.2,
    )
    snapped_in_pre_pad = _snap_to_zero_crossing(audio, _VAD_SR, valley_t_in)
    rms_floor_in = _last_rms_rise(
        audio, _VAD_SR, snapped_in_pre_pad, max_advance_ms=lead_pad_ms,
    )
    target_in = max(
        snapped_in_pre_pad - lead_pad_ms * 1e-3,
        rms_floor_in + _BUF_S,
    )
    snapped_in = max(0.0, target_in)

    # OUT side: snap to silence valley, zero-cross, then forward-pad — but
    # never forward past the next word's onset (RMS rise detection).
    # Asymmetric search: mostly look forward (silence after last word).
    valley_t_out, valley_db_out = _find_silence_valley(
        audio, _VAD_SR, out_t, voice,
        search_back_ms=search_ms * 0.2,
        search_fwd_ms=search_ms,
    )
    snapped_out_pre_pad = _snap_to_zero_crossing(audio, _VAD_SR, valley_t_out)
    rms_ceiling_out = _next_rms_rise(
        audio, _VAD_SR, snapped_out_pre_pad, max_advance_ms=trail_pad_ms,
    )
    target_out = min(
        snapped_out_pre_pad + trail_pad_ms * 1e-3,
        rms_ceiling_out - _BUF_S,
    )
    snapped_out = min(audio_dur, target_out)

    in_snap = BoundarySnap(
        side="in",
        candidate_t=in_t,
        snapped_t=snapped_in,
        rms_db=valley_db_in,
        # `in_voice` reflects what the EAR will hear at the cut: an RMS
        # above _NO_SILENCE_DB means audible energy, regardless of what
        # silero's coarse voice/non-voice block labelling says.
        in_voice=valley_db_in > _NO_SILENCE_DB,
        delta_ms=(snapped_in - in_t) * 1000.0,
        pad_ms=-lead_pad_ms,
    )
    out_snap = BoundarySnap(
        side="out",
        candidate_t=out_t,
        snapped_t=snapped_out,
        rms_db=valley_db_out,
        in_voice=valley_db_out > _NO_SILENCE_DB,
        delta_ms=(snapped_out - out_t) * 1000.0,
        pad_ms=+trail_pad_ms,
    )

    if snapped_out <= snapped_in:
        # Pathological: pads collapsed the clip. Fall back to the
        # un-padded snapped values.
        snapped_in = max(0.0, snapped_in_pre_pad)
        snapped_out = min(audio_dur, snapped_out_pre_pad)
        if snapped_out <= snapped_in:
            # Still bad — bail back to the inputs; caller can decide.
            snapped_in, snapped_out = in_t, out_t

    return SnapResult(
        audio_path=audio_path,
        in_t=snapped_in,
        out_t=snapped_out,
        candidate_in_t=in_t,
        candidate_out_t=out_t,
        duration=snapped_out - snapped_in,
        in_snap=in_snap,
        out_snap=out_snap,
    )


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m cvs_lib.clip_snap",
        description="Snap a clip's boundaries to true silence + zero crossing.",
    )
    ap.add_argument("audio_path")
    ap.add_argument("in_t", type=float)
    ap.add_argument("out_t", type=float)
    ap.add_argument("--lead-pad-ms", type=float, default=DEFAULT_LEAD_PAD_MS)
    ap.add_argument("--trail-pad-ms", type=float, default=DEFAULT_TRAIL_PAD_MS)
    ap.add_argument("--search-ms", type=float, default=DEFAULT_SEARCH_MS)
    args = ap.parse_args()

    res = snap_boundaries(
        args.audio_path, args.in_t, args.out_t,
        lead_pad_ms=args.lead_pad_ms,
        trail_pad_ms=args.trail_pad_ms,
        search_ms=args.search_ms,
    )
    print(f"  candidate: in={args.in_t:.3f}  out={args.out_t:.3f}  "
          f"dur={args.out_t - args.in_t:.3f}")
    print(f"  snapped:   in={res.in_t:.3f}  out={res.out_t:.3f}  "
          f"dur={res.duration:.3f}")
    print(f"  {res.quality_summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
