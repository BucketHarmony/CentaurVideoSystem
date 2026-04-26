"""Audio synthesis + mixing for MPC reels.

Pure NumPy/SciPy. No MoviePy or PIL dependency. Functions are
parameter-driven so any caller (north_lake's `minor/grief/build/resolve`
SCENE_CHORDS or romulus's `hook/stakes/fight/cta`) can pass its own
mapping.

API surface:
- `render_chord_window(...)` — additive synth + envelope shaping
- `harmonic_hum(...)`        — overlapping chord beds across scenes
- `sidechain_duck(...)`      — duck the bed under any speech-like signal
- `vo_duck_envelope(...)`    — return a gain curve to lower source under VO
- `extract_audio_segment(...)` — pcm float32 from a video file via ffmpeg
- `to_int16_stereo(...)`     — final mono → interleaved int16 stereo
- `write_wav(...)`           — bytes-to-disk
- `audio_sha256_from_wav(...)` — for byte-identity regression tests

Conventions:
- `sr` (sample rate) defaults to 44100 everywhere. Pass through.
- Functions that allocate a full-track array take `total_n` (samples)
  rather than `duration` to avoid float-rounding drift across calls.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple, Union

import numpy as np
from scipy.signal import butter, lfilter


PathLike = Union[str, Path]
DEFAULT_SR = 44100

Scene = Tuple[float, float, str]      # (t0, t1, slug)
Beat = Tuple[str, float, str, str, dict]


# --------------------------------------------------------------------------- #
# Synth
# --------------------------------------------------------------------------- #

def render_chord_window(
    notes_hz: Sequence[float],
    t_start: float,
    t_end: float,
    *,
    total_n: int,
    sr: int = DEFAULT_SR,
    fade_in: float = 0.4,
    fade_out: float = 0.4,
) -> np.ndarray:
    """Render an additive-synth chord into a track of length `total_n`.

    Three harmonics per note (fundamental, octave, fifth-octave) with
    light vibrato (5.5 Hz, 0.4%) and a slow breath envelope. Final
    lowpass at 3.5 kHz to keep it pad-soft.
    """
    out = np.zeros(total_n, dtype=np.float32)
    i0 = int(t_start * sr)
    i1 = min(total_n, int(t_end * sr))
    if i0 >= total_n or i1 <= i0:
        return out
    n = i1 - i0
    t_local = np.linspace(0, n / sr, n, endpoint=False)
    chord = np.zeros(n, dtype=np.float32)
    vib = 0.004 * np.sin(2 * np.pi * 5.5 * t_local)
    breath = 1.0 - 0.18 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.3 * t_local))
    for k, f in enumerate(notes_hz):
        amp = max(0.04, 0.13 - 0.025 * k)
        ph1 = 2 * np.pi * np.cumsum(f * (1 + vib)) / sr
        chord += amp * np.sin(ph1)
        ph2 = 2 * np.pi * np.cumsum(2 * f * (1 + vib * 0.6)) / sr
        chord += amp * 0.30 * np.sin(ph2)
        ph3 = 2 * np.pi * np.cumsum(3 * f * (1 + vib * 0.3)) / sr
        chord += amp * 0.12 * np.sin(ph3)
    chord *= breath
    fi_n = min(int(fade_in * sr), n // 2)
    fo_n = min(int(fade_out * sr), n // 2)
    if fi_n > 0:
        chord[:fi_n] *= np.linspace(0, 1, fi_n) ** 2
    if fo_n > 0:
        chord[-fo_n:] *= np.linspace(1, 0, fo_n) ** 2
    b, a = butter(4, 3500 / (sr / 2), btype="low")
    chord = lfilter(b, a, chord).astype(np.float32)
    out[i0:i1] = chord
    return out


def harmonic_hum(
    scenes: Sequence[Scene],
    beats: Sequence[Beat],
    scene_chords: dict,
    *,
    duration: float,
    sr: int = DEFAULT_SR,
    overlap: float = 0.35,
) -> np.ndarray:
    """Render overlapping chord beds across all scenes.

    `scene_chords` maps the chord_key (BEATS[i][2]) to a list of
    fundamental frequencies. romulus uses `hook/stakes/fight/cta`; the
    other 7 reels use `minor/grief/build/resolve`. Either works — the
    only requirement is that every BEAT's chord_key is a key in this
    dict.
    """
    total_n = int(sr * duration)
    bed = np.zeros(total_n, dtype=np.float32)
    chord_for_slug = {b[0]: b[2] for b in beats}
    for idx, (t0, t1, slug) in enumerate(scenes):
        chord_key = chord_for_slug[slug]
        notes = scene_chords[chord_key]
        is_first = idx == 0
        is_last = idx == len(scenes) - 1
        ws = max(0.0, t0 - (0 if is_first else overlap))
        we = min(duration, t1 + (0 if is_last else overlap))
        fi = 0.25 if is_first else overlap
        fo = 0.6 if is_last else overlap
        bed += render_chord_window(
            notes, ws, we,
            total_n=total_n, sr=sr,
            fade_in=fi, fade_out=fo,
        )
    return bed


# --------------------------------------------------------------------------- #
# Ducking
# --------------------------------------------------------------------------- #

def _envelope_follower(
    sig: np.ndarray, *, sr: int, attack_ms: float, release_ms: float,
) -> np.ndarray:
    """One-pole envelope follower with separate attack/release time
    constants. Returns a smoothed |signal| curve, same shape as input.
    """
    env = np.abs(sig)
    a_atk = math.exp(-1 / (sr * attack_ms / 1000))
    a_rel = math.exp(-1 / (sr * release_ms / 1000))
    smoothed = np.zeros_like(env)
    s = 0.0
    for i in range(len(env)):
        coef = a_atk if env[i] > s else a_rel
        s = coef * s + (1 - coef) * env[i]
        smoothed[i] = s
    return smoothed


def sidechain_duck(
    bed: np.ndarray,
    voice: Optional[np.ndarray],
    *,
    sr: int = DEFAULT_SR,
    threshold: float = 0.025,
    ratio: float = 0.30,
    attack_ms: float = 20.0,
    release_ms: float = 180.0,
) -> np.ndarray:
    """Duck `bed` under `voice` (compressor-style). voice=None → bed
    unchanged."""
    if voice is None:
        return bed
    smoothed = _envelope_follower(
        voice, sr=sr, attack_ms=attack_ms, release_ms=release_ms)
    duck = 1.0 - np.clip((smoothed - threshold) / threshold, 0, 1) * (1 - ratio)
    return bed * duck.astype(np.float32)


def vo_duck_envelope(
    voice: Optional[np.ndarray],
    *,
    total_n: int,
    sr: int = DEFAULT_SR,
    threshold: float = 0.02,
    low_gain: float = 0.5,
    attack_ms: float = 10.0,
    release_ms: float = 200.0,
) -> np.ndarray:
    """Return a gain curve in [low_gain, 1.0] that drops while VO is
    active. Used to multiply the source-audio track so on-camera speech
    yields under synth narration.

    voice=None or near-silent → returns ones (no ducking)."""
    if voice is None or float(np.max(np.abs(voice))) < 1e-5:
        return np.ones(total_n, dtype=np.float32)
    smoothed = _envelope_follower(
        voice, sr=sr, attack_ms=attack_ms, release_ms=release_ms)
    duck = 1.0 - np.clip((smoothed - threshold) / threshold, 0, 1) * (1.0 - low_gain)
    return duck.astype(np.float32)


# --------------------------------------------------------------------------- #
# Source extraction
# --------------------------------------------------------------------------- #

def extract_audio_segment(
    path: PathLike, t0: float, t1: float, *, sr: int = DEFAULT_SR,
) -> Optional[np.ndarray]:
    """Decode a [t0, t1) span of a video file to mono float32 PCM at
    `sr`. Uses ffmpeg via a temp .wav. Returns None on failure or
    zero-length input."""
    dur = float(t1 - t0)
    if dur <= 0:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    try:
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-ss", f"{float(t0):.3f}", "-t", f"{dur:.3f}",
               "-i", str(path),
               "-vn", "-ac", "1", "-ar", str(sr),
               "-acodec", "pcm_s16le", tmp]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            return None
        with wave.open(tmp, "rb") as w:
            n = w.getnframes()
            if n == 0:
                return None
            raw = w.readframes(n)
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass
    return arr


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def to_int16_stereo(mono: np.ndarray) -> np.ndarray:
    """Mono float32 in [-1, 1] → interleaved int16 stereo."""
    mono = np.clip(mono, -1.0, 1.0)
    L = (mono * 32767).astype(np.int16)
    return np.column_stack([L, L.copy()]).flatten()


def write_wav(
    mono: np.ndarray, path: PathLike, *, sr: int = DEFAULT_SR,
) -> None:
    """Write a mono float32 array to `path` as int16 stereo WAV at
    `sr`."""
    stereo = to_int16_stereo(mono)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
