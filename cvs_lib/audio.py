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
from dataclasses import dataclass, field
from scipy.signal import butter, lfilter, sosfilt


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


def render_chord_window_stereo(
    notes_hz: Sequence[float],
    t_start: float,
    t_end: float,
    *,
    total_n: int,
    sr: int = DEFAULT_SR,
    fade_in: float = 0.4,
    fade_out: float = 0.4,
    width_cents: float = 3.0,
    haas_ms: float = 7.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Stereo version of render_chord_window with binaural width.

    Each note is rendered twice — left channel detuned -width_cents/2,
    right channel detuned +width_cents/2. Right channel is then delayed
    by `haas_ms` (Haas precedence effect: brain reads it as ambience,
    not echo). No HRTF; just the two cues that produce most of the
    "around-your-head" feel.
    """
    cents = width_cents / 2.0
    detune_l = 2.0 ** (-cents / 1200.0)
    detune_r = 2.0 ** (cents / 1200.0)
    notes_l = [f * detune_l for f in notes_hz]
    notes_r = [f * detune_r for f in notes_hz]
    L = render_chord_window(
        notes_l, t_start, t_end,
        total_n=total_n, sr=sr,
        fade_in=fade_in, fade_out=fade_out,
    )
    R = render_chord_window(
        notes_r, t_start, t_end,
        total_n=total_n, sr=sr,
        fade_in=fade_in, fade_out=fade_out,
    )
    haas_n = int(haas_ms * sr / 1000)
    if haas_n > 0:
        R = np.concatenate([np.zeros(haas_n, dtype=np.float32), R[:-haas_n]])
    return L, R


def binaural_pulse(
    t_start: float,
    t_end: float,
    *,
    total_n: int,
    sr: int = DEFAULT_SR,
    carrier_hz: float,
    beat_hz: float,
    gain: float = 0.04,
) -> Tuple[np.ndarray, np.ndarray]:
    """Sub-audible binaural-beat carrier pair (L, R).

    L plays a pure sine at `carrier_hz`; R plays at `carrier_hz +
    beat_hz`. The brain perceives a pulse at `beat_hz` inside the head.
    Used as a felt-not-heard emotional carrier under the pad — theta
    (4-8Hz) for grief/contemplation, alpha (8-12Hz) for focus, low beta
    (12-15Hz) for alert determination.

    Headphones strongly recommended on playback (binaural beats fall
    apart on speakers — the L/R signals just sum).
    """
    out_l = np.zeros(total_n, dtype=np.float32)
    out_r = np.zeros(total_n, dtype=np.float32)
    i0 = int(t_start * sr)
    i1 = min(total_n, int(t_end * sr))
    if i0 >= total_n or i1 <= i0:
        return out_l, out_r
    n = i1 - i0
    t = np.arange(n, dtype=np.float32) / sr
    atk = min(int(1.0 * sr), n // 4)
    rel = min(int(1.0 * sr), n // 4)
    env = np.ones(n, dtype=np.float32)
    if atk > 0:
        env[:atk] = np.linspace(0, 1, atk) ** 2
    if rel > 0:
        env[-rel:] = np.linspace(1, 0, rel) ** 2
    out_l[i0:i1] = (
        gain * np.sin(2 * np.pi * carrier_hz * t).astype(np.float32) * env
    )
    out_r[i0:i1] = (
        gain * np.sin(2 * np.pi * (carrier_hz + beat_hz) * t).astype(np.float32) * env
    )
    return out_l, out_r


def spatial_bed(
    scenes: Sequence[Scene],
    beats: Sequence[Beat],
    scene_chords: dict,
    *,
    duration: float,
    sr: int = DEFAULT_SR,
    bpm: float = 96.0,
    beats_per_scene: int = 16,
    pad_gain: float = 0.30,
    sub_gain: float = 0.18,
    kick_gain: float = 0.20,
    width_cents: float = 3.0,
    haas_ms: float = 7.0,
    binaural_carriers: Optional[dict] = None,
    binaural_gain: float = 0.04,
) -> Tuple[np.ndarray, np.ndarray]:
    """Stereo "binaural-width" bed — subtler sibling of `song_bed`.

    Returns `(L, R)` mono float32 arrays of length `total_n`.

    Layers, per scene:
    - Stereo pad via `render_chord_window_stereo` (detune + Haas).
    - Mono sub-bass at root/2 (sub frequencies don't localize; mono
      keeps the low end tight).
    - Mono soft kick on every 4th beat (downbeats), shorter decay than
      `song_bed`'s kick — felt-not-heard.
    - Optional binaural-beat carrier per scene if `binaural_carriers`
      is provided as `{chord_key: (carrier_hz, beat_hz)}`.

    Default gains are roughly half of `song_bed` so the bed reads as a
    presence rather than a foreground element.
    """
    total_n = int(sr * duration)
    L = np.zeros(total_n, dtype=np.float32)
    R = np.zeros(total_n, dtype=np.float32)
    chord_for_slug = {b[0]: b[2] for b in beats}
    spb = 60.0 / bpm

    for idx, (t0, t1, slug) in enumerate(scenes):
        chord_key = chord_for_slug[slug]
        notes = scene_chords[chord_key]
        is_first = idx == 0
        is_last = idx == len(scenes) - 1
        ws = max(0.0, t0 - (0 if is_first else 0.35))
        we = min(duration, t1 + (0 if is_last else 0.35))
        fi = 0.25 if is_first else 0.35
        fo = 0.6 if is_last else 0.35
        pl, pr = render_chord_window_stereo(
            notes, ws, we,
            total_n=total_n, sr=sr,
            fade_in=fi, fade_out=fo,
            width_cents=width_cents, haas_ms=haas_ms,
        )
        L += pad_gain * pl
        R += pad_gain * pr

    for (t0, t1, slug) in scenes:
        chord_key = chord_for_slug[slug]
        notes = scene_chords[chord_key]
        i0 = int(t0 * sr)
        i1 = min(total_n, int(t1 * sr))
        n = i1 - i0
        if n <= 0:
            continue

        # Sub-bass: mono center.
        root = notes[0] / 2.0
        t_local = np.arange(n, dtype=np.float32) / sr
        sub = np.sin(2 * np.pi * root * t_local).astype(np.float32)
        atk = min(int(0.4 * sr), n // 3)
        rel = min(int(0.4 * sr), n // 3)
        env = np.ones(n, dtype=np.float32)
        if atk > 0:
            env[:atk] = np.linspace(0, 1, atk) ** 2
        if rel > 0:
            env[-rel:] = np.linspace(1, 0, rel) ** 2
        sub_layer = sub_gain * sub * env
        L[i0:i1] += sub_layer
        R[i0:i1] += sub_layer

        # Kick: mono center, shorter decay than song_bed.
        kn = int(0.08 * sr)
        tk = np.arange(kn, dtype=np.float32) / sr
        pitch = 80.0 - 30.0 * np.clip(tk / 0.04, 0, 1)
        burst = np.sin(2 * np.pi * np.cumsum(pitch) / sr).astype(np.float32)
        burst *= np.exp(-tk * 28.0).astype(np.float32)
        for beat_idx in range(0, beats_per_scene, 4):
            k_t = beat_idx * spb
            ki = i0 + int(k_t * sr)
            if ki >= total_n:
                break
            ke = min(total_n, ki + kn)
            kick_layer = kick_gain * burst[: ke - ki]
            L[ki:ke] += kick_layer
            R[ki:ke] += kick_layer

    if binaural_carriers:
        for (t0, t1, slug) in scenes:
            chord_key = chord_for_slug[slug]
            if chord_key not in binaural_carriers:
                continue
            carrier_hz, beat_hz = binaural_carriers[chord_key]
            bl, br = binaural_pulse(
                t0, t1, total_n=total_n, sr=sr,
                carrier_hz=carrier_hz, beat_hz=beat_hz,
                gain=binaural_gain,
            )
            L += bl
            R += br

    return L, R


def song_bed(
    scenes: Sequence[Scene],
    beats: Sequence[Beat],
    scene_chords: dict,
    *,
    duration: float,
    sr: int = DEFAULT_SR,
    bpm: float = 96.0,
    beats_per_scene: int = 16,
    pad_gain: float = 0.55,
    sub_gain: float = 0.30,
    kick_gain: float = 0.45,
) -> np.ndarray:
    """Tempo-aware bed: chord pad + sub-bass + soft kick on downbeats.

    Same chord drone as `harmonic_hum`, but adds rhythmic structure so
    each scene reads as a complete musical phrase. Defaults assume
    `beats_per_scene` beats fit exactly inside each scene
    (i.e. scene_dur == beats_per_scene * 60 / bpm). Caller is
    responsible for matching scene durations to the tempo.

    Kick lands on beat 1 of each 4/4 measure (so 4 hits per 16-beat
    scene). Sub-bass plays the chord root one octave below the pad,
    sustained across the scene with a 0.4s attack/release.
    """
    total_n = int(sr * duration)
    out = np.zeros(total_n, dtype=np.float32)
    chord_for_slug = {b[0]: b[2] for b in beats}
    spb = 60.0 / bpm

    # Pad: same overlapping-chord call as harmonic_hum, identical timbre.
    for idx, (t0, t1, slug) in enumerate(scenes):
        chord_key = chord_for_slug[slug]
        notes = scene_chords[chord_key]
        is_first = idx == 0
        is_last = idx == len(scenes) - 1
        ws = max(0.0, t0 - (0 if is_first else 0.35))
        we = min(duration, t1 + (0 if is_last else 0.35))
        fi = 0.25 if is_first else 0.35
        fo = 0.6 if is_last else 0.35
        out += pad_gain * render_chord_window(
            notes, ws, we,
            total_n=total_n, sr=sr,
            fade_in=fi, fade_out=fo,
        )

    # Sub-bass + kick, scene by scene. Kept inside this loop so each
    # scene's tonic is taken from its own chord.
    for (t0, t1, slug) in scenes:
        chord_key = chord_for_slug[slug]
        notes = scene_chords[chord_key]
        i0 = int(t0 * sr)
        i1 = min(total_n, int(t1 * sr))
        n = i1 - i0
        if n <= 0:
            continue

        # Sub-bass: octave-down root, sustained, slow attack/release.
        root = notes[0] / 2.0
        t_local = np.arange(n, dtype=np.float32) / sr
        sub = np.sin(2 * np.pi * root * t_local).astype(np.float32)
        atk = min(int(0.4 * sr), n // 3)
        rel = min(int(0.4 * sr), n // 3)
        env = np.ones(n, dtype=np.float32)
        if atk > 0:
            env[:atk] = np.linspace(0, 1, atk) ** 2
        if rel > 0:
            env[-rel:] = np.linspace(1, 0, rel) ** 2
        out[i0:i1] += sub_gain * sub * env

        # Kick: soft sine thump at beat 1 of each measure.
        kn = int(0.12 * sr)
        tk = np.arange(kn, dtype=np.float32) / sr
        # Pitch falls from 80Hz to 50Hz over the burst — subby thump.
        pitch = 80.0 - 30.0 * np.clip(tk / 0.06, 0, 1)
        burst = np.sin(2 * np.pi * np.cumsum(pitch) / sr).astype(np.float32)
        burst *= np.exp(-tk * 18.0).astype(np.float32)
        for beat_idx in range(0, beats_per_scene, 4):
            k_t = beat_idx * spb
            ki = i0 + int(k_t * sr)
            if ki >= total_n:
                break
            ke = min(total_n, ki + kn)
            out[ki:ke] += kick_gain * burst[: ke - ki]

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


def write_wav_stereo(
    left: np.ndarray, right: np.ndarray, path: PathLike,
    *, sr: int = DEFAULT_SR,
) -> None:
    """Write separate L/R float32 arrays to `path` as int16 stereo WAV.

    Sibling of `write_wav` for callers that built a true stereo signal
    (e.g. `spatial_bed` returns L != R for binaural width).
    """
    L = np.clip(left, -1.0, 1.0)
    R = np.clip(right, -1.0, 1.0)
    Li = (L * 32767).astype(np.int16)
    Ri = (R * 32767).astype(np.int16)
    interleaved = np.column_stack([Li, Ri]).flatten()
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(interleaved.tobytes())


# --------------------------------------------------------------------------- #
# Cottagecore + Hookshot primitives — mood-driven additive synth
# --------------------------------------------------------------------------- #
# These primitives consolidate ~18 inline `generate_ambient_pad` /
# `generate_bed_audio` copies from cc_flora (12 episodes) and cc_hookshot
# (5 distinct scripts) into one parameterized API. Per the audio overhaul
# lift design (`C:/Users/kenne/.claude/plans/bouncing-velvet-tympani.md`):
#
# Editorial philosophies (PRESERVED — sharing primitives, not the pipeline):
# - MPC ducks (sidechain compressor in `sidechain_duck`).
# - cc_flora does NOT duck (narration sits proud on pad).
# - cc_hookshot ducks aggressively (60% reduction inline in mix_tts).
# Don't try to "fix" this by unifying — the split is editorial.
#
# Primitives are LOWPASS-AGNOSTIC. cc_flora lowpasses the pad alone;
# cc_hookshot lowpasses the whole mix downstream. Caller decides.
#
# Per-episode editorial events (act-N tensions, ep04 battery-death,
# ep07/ep08 impacts) live OUTSIDE these primitives — caller composes via
# `tension_partial()` + `impact()` between `ambient_pad()` and
# `pad_envelope()`. This was Phase 0's audit finding.


@dataclass(frozen=True)
class Mood:
    """Frozen mood spec. Drives ambient_pad + chime_layer."""

    drone: Tuple[Tuple[float, float], ...]
    """(freq_hz, gain) per drone partial."""

    shimmer: Tuple[Tuple[float, float, Optional[str]], ...]
    """(freq_hz, gain, lfo_role) per shimmer partial.
    lfo_role ∈ {"lfo1", "lfo2", "lfo", "anti_lfo", None}."""

    lfo1_hz: float = 0.12
    lfo2_hz: float = 0.18
    lfo2_phase: float = 1.0  # rad

    chime_decay: float = 2.0
    chime_attack: float = 10.0
    chime_gain: float = 0.022
    chime_octave_gain: float = 0.0
    chime_attack_curve: str = "linear"  # "linear" or "masterpiece"

    envelope_floor: float = 0.3
    envelope_fade_in_s: float = 2.0
    envelope_fade_out_s: float = 2.5

    lowpass_hz: float = 3000.0
    lowpass_order: int = 4
    pad_target_gain: float = 0.22

    sting: dict = field(default_factory=dict)
    """Optional sting params (hookshot moods). {} for non-hookshot."""


MOODS: dict = {
    "cottagecore_warm": Mood(
        drone=(
            (110.0, 0.050),
            (164.81, 0.035),
            (220.0, 0.025),
        ),
        shimmer=(
            (440.0, 0.010, "lfo1"),
            (554.37, 0.007, "lfo2"),
            (659.25, 0.005, "lfo1"),
        ),
    ),

    "cottagecore_masterpiece": Mood(
        drone=(
            (110.0, 0.060),
            (164.81, 0.040),
            (220.0, 0.030),
        ),
        shimmer=(
            (440.0, 0.012, "lfo1"),
            (554.37, 0.008, "lfo2"),
            (659.25, 0.006, "lfo1"),
        ),
        lfo1_hz=0.15,
        lfo2_hz=0.22,
        chime_decay=2.5,
        chime_attack=8.0,
        chime_attack_curve="masterpiece",
        chime_gain=0.025,
        envelope_floor=0.0,
        envelope_fade_out_s=2.0,
        pad_target_gain=0.25,
    ),

    "hookshot_attention": Mood(
        drone=(
            (110.00, 0.040),
            (130.81, 0.025),
            (164.81, 0.030),
            (220.00, 0.020),
        ),
        shimmer=(
            (440.00, 0.010, "lfo1"),
            (523.25, 0.007, "lfo2"),
            (659.25, 0.005, None),
        ),
        chime_decay=2.5,
        chime_attack=20.0,
        chime_gain=0.025,
        chime_octave_gain=0.008,
        sting={
            "sub_hz": 60.0, "sub_gain": 0.35, "sub_decay": 8.0, "dur": 0.5,
            "transient_dur": 0.02, "transient_gain": 0.25, "transient_decay": 10.0,
            "high_hz": 880.0, "high_gain": 0.08, "high_dur": 0.5,
        },
    ),

    "hookshot_grief": Mood(  # faith — D minor
        drone=(
            (73.42, 0.045),    # D2
            (87.31, 0.025),    # F2
            (110.00, 0.035),   # A2
            (146.83, 0.020),   # D3
        ),
        shimmer=(
            (293.66, 0.008, "lfo"),       # D4
            (349.23, 0.006, "anti_lfo"),  # F4
        ),
        lfo1_hz=0.08,
        chime_decay=3.0,
        chime_attack=20.0,
        chime_gain=0.020,
        chime_octave_gain=0.006,
        lowpass_hz=2800.0,
        sting={
            "sub_hz": 50.0, "sub_gain": 0.50, "sub_decay": 6.0, "dur": 0.6,
            "transient_dur": 0.03, "transient_gain": 0.35, "transient_decay": 8.0,
            "high_hz": 440.0, "high_gain": 0.06, "high_dur": 0.6,
            "high_attack": 3.0, "high_decay": 4.0,
        },
    ),

    "hookshot_toast": Mood(  # toast — A minor, no high tone, single-lfo shimmer
        drone=(
            (110.00, 0.040),
            (130.81, 0.025),
            (164.81, 0.030),
            (220.00, 0.020),
        ),
        shimmer=(
            (440.00, 0.010, "lfo"),
            (523.25, 0.007, "anti_lfo"),
        ),
        chime_decay=2.5,
        chime_attack=20.0,
        chime_gain=0.025,
        chime_octave_gain=0.0,
        envelope_floor=0.0,
        envelope_fade_in_s=2.5,
        envelope_fade_out_s=3.0,
        sting={
            "sub_hz": 55.0, "sub_gain": 0.4, "sub_decay": 7.0, "dur": 0.5,
            "transient_dur": 0.025, "transient_gain": 0.3, "transient_decay": 9.0,
        },
    ),

    # hookshot_collapse (midnight pair) is a TWO-mood cross-fade and
    # doesn't fit the single-Mood schema. Phase 5 handles it as a
    # caller-side blend between hookshot_attention (pre-crash) and
    # hookshot_grief (post-crash) with a `crash_impact()` event.
}


def pad_envelope(
    duration: float,
    *,
    sr: int = DEFAULT_SR,
    fade_in_s: float = 2.0,
    fade_out_s: float = 2.5,
    floor: float = 0.3,
    variant: Optional[str] = None,
    mood: Optional[str] = None,
) -> np.ndarray:
    """Master pad envelope as 1-D float64 gain curve.

    Default (cc_flora canonical): clipped-line fade-in starting at
    `floor` ramping to 1.0 over `fade_in_s`, then sustain, then
    clipped-line fade-out over the last `fade_out_s`.

    `mood=` overrides fade_in_s / fade_out_s / floor with the values
    from MOODS[mood], so callers don't have to repeat the triplet.

    Variants (override mood):
      "hookshot_linspace"     — silence 0–1s, linspace ramp 1→4s,
                                sustain, linspace 3s tail (cc_hookshot).
      "masterpiece_zerofloor" — floor=0, fade_out_s=2.0.
      "hookshot_short_in"     — floor=0, fade_in=1s, fade_out=3s.
    """
    if mood is not None:
        m = MOODS[mood]
        fade_in_s = m.envelope_fade_in_s
        fade_out_s = m.envelope_fade_out_s
        floor = m.envelope_floor

    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)

    if variant == "hookshot_linspace":
        env = np.zeros(n, dtype=np.float64)
        ramp_start = int(1.0 * sr)
        ramp_end = int(4.0 * sr)
        tail_start = max(ramp_end, n - int(3.0 * sr))
        env[ramp_start:ramp_end] = np.linspace(0, 1, ramp_end - ramp_start)
        env[ramp_end:tail_start] = 1.0
        env[tail_start:] = np.linspace(1, 0, n - tail_start)
        return env

    if variant == "masterpiece_zerofloor":
        floor = 0.0
        fade_out_s = 2.0
    elif variant == "hookshot_short_in":
        floor = 0.0
        fade_in_s = 1.0
        fade_out_s = 3.0

    fade_in = np.clip(floor + (1.0 - floor) * (t / fade_in_s), 0, 1)
    fade_out = np.clip((duration - t) / fade_out_s, 0, 1)
    return fade_in * fade_out


def ambient_pad(
    duration: float,
    *,
    mood: str = "cottagecore_warm",
    sr: int = DEFAULT_SR,
    drone_gain_scale: float = 1.0,
    apply_envelope: bool = True,
) -> np.ndarray:
    """Drone + shimmer pad, mono float64.

    Returns UNFILTERED pad — caller decides whether to lowpass and
    when (cc_flora lowpasses pad-only; cc_hookshot lowpasses whole
    mix). Master envelope optional — set `apply_envelope=False` when
    inserting per-act tension partials before the envelope.
    """
    m = MOODS[mood]
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)

    pad = np.zeros(n, dtype=np.float64)

    for freq, gain in m.drone:
        pad += np.sin(2 * np.pi * freq * t) * gain * drone_gain_scale

    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * m.lfo1_hz * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * m.lfo2_hz * t + m.lfo2_phase)
    lfo_single = 0.5 + 0.5 * np.sin(2 * np.pi * m.lfo1_hz * t)
    anti_lfo = 1.0 - lfo_single
    role_to_curve = {
        "lfo1": lfo1, "lfo2": lfo2,
        "lfo": lfo_single, "anti_lfo": anti_lfo,
        None: np.ones_like(t),
    }
    for freq, gain, role in m.shimmer:
        pad += np.sin(2 * np.pi * freq * t) * gain * role_to_curve[role]

    if apply_envelope:
        pad *= pad_envelope(
            duration, sr=sr,
            fade_in_s=m.envelope_fade_in_s,
            fade_out_s=m.envelope_fade_out_s,
            floor=m.envelope_floor,
        )

    return pad


def chime_layer(
    duration: float,
    schedule: Sequence[Tuple[float, float]],
    *,
    mood: str = "cottagecore_warm",
    sr: int = DEFAULT_SR,
    gain_override: Optional[float] = None,
    octave_gain_override: Optional[float] = None,
) -> np.ndarray:
    """Chimes scheduled at [(t_seconds, freq_hz), ...].

    Decay/attack/gain/octave-gain pulled from the mood. Overrides let
    callers force a specific gain (e.g. for a single louder chime
    inside a stack of canonical-gain ones).
    """
    m = MOODS[mood]
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)

    gain = m.chime_gain if gain_override is None else gain_override
    oct_gain = (
        m.chime_octave_gain if octave_gain_override is None
        else octave_gain_override
    )

    for ct, cf in schedule:
        env_t = t - ct
        if m.chime_attack_curve == "masterpiece":
            # masterpiece: clip(exp(-decay) * env_t * attack, 0, 1).
            # Peak shifts later vs the canonical curve (~0.21s vs 0.13s
            # for decay=2.5/attack=8) and reaches 1.0 instead of ~0.73.
            env = np.where(
                env_t >= 0,
                np.clip(np.exp(-env_t * m.chime_decay) * env_t * m.chime_attack, 0, 1),
                0,
            )
        else:
            # cc_flora / hookshot canonical: exp(-decay) * clip(attack, 0, 1).
            env = np.where(
                env_t >= 0,
                np.exp(-env_t * m.chime_decay) * np.clip(env_t * m.chime_attack, 0, 1),
                0,
            )
        out += np.sin(2 * np.pi * cf * t) * gain * env
        if oct_gain > 0:
            out += np.sin(2 * np.pi * cf * 2 * t) * oct_gain * env

    return out


def tension_partial(
    duration: float,
    *,
    freq_hz: float,
    gain: float,
    fade_in_t: float,
    fade_in_dur: float,
    fade_out_t: float,
    fade_out_dur: float,
    sr: int = DEFAULT_SR,
) -> np.ndarray:
    """Sine partial gated by a [fade_in_t, fade_out_t] window.

    Replaces the inline pattern
        env = clip((t - X) / Y, 0, 1) * clip((Z - t) / W, 0, 1)
        pad += sin(2*pi*freq*t) * gain * env
    that scattered across cc_flora episodes for act-N tensions.
    ep10 uses three (drift Bb / hope E4 / milestone B4); ep08 uses
    two (tension Bb / uncertainty); etc.
    """
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    env = (
        np.clip((t - fade_in_t) / fade_in_dur, 0, 1)
        * np.clip((fade_out_t - t) / fade_out_dur, 0, 1)
    )
    return np.sin(2 * np.pi * freq_hz * t) * gain * env


def impact(
    duration: float,
    *,
    t: float,
    sub_hz: float = 55.0,
    sub_gain: float = 0.04,
    sub_decay: float = 8.0,
    sub_dur: float = 0.4,
    noise_gain: float = 0.06,
    noise_decay: float = 20.0,
    noise_dur: float = 0.2,
    sr: int = DEFAULT_SR,
    rng_seed: Optional[int] = None,
) -> np.ndarray:
    """Percussive thud at time `t`: low sine + noise burst, both
    exponentially decaying. ep07 collisions, ep08 wedge.

    `rng_seed` makes the noise burst reproducible.
    """
    n = int(duration * sr)
    t_arr = np.linspace(0, duration, n, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)

    rng = np.random.RandomState(rng_seed) if rng_seed is not None else np.random

    sub_t = t_arr - t
    sub_env = np.where(
        (sub_t >= 0) & (sub_t < sub_dur),
        np.exp(-sub_t * sub_decay),
        0,
    )
    out += np.sin(2 * np.pi * sub_hz * t_arr) * sub_gain * sub_env

    noise_t = t_arr - t
    noise_env = np.where(
        (noise_t >= 0) & (noise_t < noise_dur),
        np.exp(-noise_t * noise_decay),
        0,
    )
    out += rng.randn(n) * noise_gain * noise_env

    return out


def sting(
    duration: float,
    *,
    mood: str = "hookshot_attention",
    t_start: float = 0.0,
    sr: int = DEFAULT_SR,
    rng_seed: int = 42,
) -> np.ndarray:
    """Hookshot opener: sub thump + transient noise + optional high tone.

    Returns mono float64 of length `duration*sr` with the sting starting
    at `t_start`. Mood pulls all params; for moods without a `sting`
    dict (e.g. cottagecore_warm), returns silence.
    """
    m = MOODS[mood]
    n = int(duration * sr)
    if not m.sting:
        return np.zeros(n, dtype=np.float64)
    s = m.sting

    t = np.linspace(0, duration, n, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)
    st = t - t_start

    sub_env = np.where(
        (st >= 0) & (st < s["dur"]),
        np.exp(-st * s["sub_decay"]),
        0,
    )
    out += np.sin(2 * np.pi * s["sub_hz"] * t) * s["sub_gain"] * sub_env

    rng = np.random.RandomState(rng_seed)
    # Transient envelope: e-folds-over-window. Matches the legacy
    # `np.exp(-np.linspace(0, 1, trans_n) * transient_decay)` shape, where
    # `transient_decay` is the exponent reached at the end of the window
    # (not a per-second rate). Index-based progress so the env is bit-
    # identical to the legacy linspace when t_start=0 and trans_n samples
    # fit inside the output.
    transient_env = np.zeros(n, dtype=np.float64)
    trans_n = int(s["transient_dur"] * sr)
    i_start = int(t_start * sr)
    i_end = min(i_start + trans_n, n)
    n_active = i_end - i_start
    if n_active > 0 and trans_n > 0:
        progress = np.linspace(0, 1, trans_n)[:n_active]
        transient_env[i_start:i_end] = np.exp(-progress * s["transient_decay"])
    out += rng.randn(n) * s["transient_gain"] * transient_env

    if "high_hz" in s and s.get("high_gain", 0) > 0:
        high_attack = s.get("high_attack", 4.0)
        high_decay = s.get("high_decay", 3.0)
        high_env = np.where(
            (st >= 0) & (st < s["high_dur"]),
            np.clip(st * high_attack, 0, 1) * np.exp(-st * high_decay),
            0,
        )
        out += np.sin(2 * np.pi * s["high_hz"] * t) * s["high_gain"] * high_env

    return out


def lowpass_normalize(
    pad: np.ndarray,
    *,
    mood: str = "cottagecore_warm",
    sr: int = DEFAULT_SR,
) -> np.ndarray:
    """Apply mood's butterworth lowpass + normalize to mood's
    `pad_target_gain`. Convenience wrapper for the cc_flora canonical
    finishing pattern: sosfilt → divide by peak → multiply by target.
    """
    m = MOODS[mood]
    sos = butter(m.lowpass_order, m.lowpass_hz, "low", fs=sr, output="sos")
    pad = sosfilt(sos, pad)
    return pad / (np.max(np.abs(pad)) + 1e-8) * m.pad_target_gain
