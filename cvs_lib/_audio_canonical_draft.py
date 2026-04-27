"""Phase 1 SCRATCH — canonical audio primitives draft.

This module is **temporary**. It exists to prove out the API for the
audio overhaul lift before we commit to landing it in
`cvs_lib/audio.py` (Phase 2). DO NOT import from production code.

Canonical decisions per the Phase 0 audit
(`cvs_lib/_audio_drift_audit.md`):

- Drone + shimmer + chimes parameterized by mood.
- Lowpass NOT applied here — caller decides what to filter (pad-only
  for cc_flora, whole-mix for cc_hookshot).
- Master envelope via `pad_envelope()`; default is the cc_flora 0.3-
  floor / 2.0s-in / 2.5s-out shape.
- Per-episode editorial events (act tensions, ep04 battery-death,
  ep05 freeze, ep07/ep08 impacts) live OUTSIDE this primitive — they
  are caller-scheduled inserts via `tension_partial()` + `impact()`.
- masterpiece's 1.20x drone gains handled via `drone_gain_scale=1.20`
  kwarg, not a separate mood.

After Phase 1 sign-off, contents move into `cvs_lib/audio.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple

import numpy as np


SR_DEFAULT = 44100


# --------------------------------------------------------------------------- #
# Mood registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Mood:
    """Frozen mood spec. Drives ambient_pad + chime_layer."""

    drone: Tuple[Tuple[float, float], ...]
    """(freq_hz, gain) per drone partial."""

    shimmer: Tuple[Tuple[float, float, str | None], ...]
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

    # Hookshot extras
    sting: dict = field(default_factory=dict)
    """Optional sting params: sub_hz, sub_gain, sub_decay, dur,
    transient_dur, transient_gain, transient_decay, high_hz,
    high_gain, high_dur. {} for moods without a sting."""


MOODS: dict[str, Mood] = {
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
        # All other fields take cottagecore defaults above.
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
            (220.00, 0.020),   # A3
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
        },
    ),

    # hookshot_collapse (midnight pair) is a TWO-mood cross-fade and
    # doesn't fit the single-Mood schema. Phase 5 will handle it as a
    # caller-side blend between hookshot_attention (pre-crash) and
    # hookshot_grief (post-crash) with a `crash_impact()` event.
    # Documented here so the next reader doesn't go looking.
}


# --------------------------------------------------------------------------- #
# pad_envelope
# --------------------------------------------------------------------------- #

def pad_envelope(
    duration: float,
    *,
    sr: int = SR_DEFAULT,
    fade_in_s: float = 2.0,
    fade_out_s: float = 2.5,
    floor: float = 0.3,
    variant: str | None = None,
) -> np.ndarray:
    """Master pad envelope as 1-D float64 gain curve.

    Default shape (cc_flora canonical): clipped-line fade-in starting
    at `floor` ramping to 1.0 over `fade_in_s`, then sustain, then
    clipped-line fade-out over the last `fade_out_s`.

    variant="hookshot_linspace": cc_hookshot.py shape — silence 0–1s,
    linspace ramp 1→4s, sustain, linspace 3s tail.
    variant="masterpiece_zerofloor": floor=0, fade_out_s=2.0.
    variant="hookshot_short_in": floor=0, fade_in_s=1.0, fade_out=3.0.
    """
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


# --------------------------------------------------------------------------- #
# ambient_pad — drone + shimmer + envelope, NO chimes, NO lowpass
# --------------------------------------------------------------------------- #

def ambient_pad(
    duration: float,
    *,
    mood: str = "cottagecore_warm",
    sr: int = SR_DEFAULT,
    drone_gain_scale: float = 1.0,
    apply_envelope: bool = True,
) -> np.ndarray:
    """Drone + shimmer pad in mono float64.

    Returns UNFILTERED pad — caller decides whether to lowpass and
    whether to lowpass before or after summing chimes/sting/etc.
    Returns the array WITH or WITHOUT the master envelope applied
    (default True; set False when caller wants to apply per-act
    tension partials before envelope).
    """
    m = MOODS[mood]
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)

    pad = np.zeros(n, dtype=np.float64)

    # Drone partials
    for freq, gain in m.drone:
        pad += np.sin(2 * np.pi * freq * t) * gain * drone_gain_scale

    # Shimmer partials with LFO role-based modulation
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * m.lfo1_hz * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * m.lfo2_hz * t + m.lfo2_phase)
    # "lfo" / "anti_lfo" are single-LFO variants used by hookshot_grief
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


# --------------------------------------------------------------------------- #
# chime_layer
# --------------------------------------------------------------------------- #

def chime_layer(
    duration: float,
    schedule: Sequence[Tuple[float, float]],
    *,
    mood: str = "cottagecore_warm",
    sr: int = SR_DEFAULT,
    gain_override: float | None = None,
    octave_gain_override: float | None = None,
) -> np.ndarray:
    """Chimes scheduled at [(t_seconds, freq_hz), ...].

    Decay/attack/gain/octave-gain pulled from the mood. `gain_override`
    + `octave_gain_override` let callers force a specific gain (e.g.
    for a single louder chime within a stack).
    """
    m = MOODS[mood]
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)

    gain = m.chime_gain if gain_override is None else gain_override
    oct_gain = m.chime_octave_gain if octave_gain_override is None else octave_gain_override

    for ct, cf in schedule:
        env_t = t - ct
        if m.chime_attack_curve == "masterpiece":
            # masterpiece formula: env_t * 8 → clip(0,1), then * exp(-env_t * decay)
            env = np.where(
                env_t >= 0,
                np.clip(env_t * m.chime_attack, 0, 1) * np.exp(-env_t * m.chime_decay),
                0,
            )
        else:
            # cc_flora / hookshot canonical: exp(-env_t * decay) * clip(env_t * attack, 0, 1)
            env = np.where(
                env_t >= 0,
                np.exp(-env_t * m.chime_decay) * np.clip(env_t * m.chime_attack, 0, 1),
                0,
            )
        out += np.sin(2 * np.pi * cf * t) * gain * env
        if oct_gain > 0:
            out += np.sin(2 * np.pi * cf * 2 * t) * oct_gain * env

    return out


# --------------------------------------------------------------------------- #
# tension_partial — additive sine over a time window for act-N tensions
# --------------------------------------------------------------------------- #

def tension_partial(
    duration: float,
    *,
    freq_hz: float,
    gain: float,
    fade_in_t: float,
    fade_in_dur: float,
    fade_out_t: float,
    fade_out_dur: float,
    sr: int = SR_DEFAULT,
) -> np.ndarray:
    """Sine partial over a [fade_in_t, fade_out_t] window.

    Replaces inline `np.clip((t - X) / Y, 0, 1) * np.clip((Z - t) / W, 0, 1)`
    + `np.sin(2*pi*freq*t) * gain * env` patterns scattered across
    cc_flora episodes. ep10 uses three of these (drift Bb, hope E4,
    milestone B4); ep08 uses two (tension Bb, uncertainty); etc.
    """
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    env = (
        np.clip((t - fade_in_t) / fade_in_dur, 0, 1)
        * np.clip((fade_out_t - t) / fade_out_dur, 0, 1)
    )
    return np.sin(2 * np.pi * freq_hz * t) * gain * env


# --------------------------------------------------------------------------- #
# impact — percussive thud (ep07 collisions, ep08 wedge)
# --------------------------------------------------------------------------- #

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
    sr: int = SR_DEFAULT,
    rng_seed: int | None = None,
) -> np.ndarray:
    """Percussive thud: low sine + noise burst, both with exp decay.

    ep07 collisions: decay=10, gain=0.04 (Pelican thud) / 0.04 (barrel).
    ep08 wedge: decay=8, gain=0.04.

    `rng_seed` for reproducibility on noise burst.
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


# --------------------------------------------------------------------------- #
# sting — hookshot opener
# --------------------------------------------------------------------------- #

def sting(
    duration: float,
    *,
    mood: str = "hookshot_attention",
    t_start: float = 0.0,
    sr: int = SR_DEFAULT,
) -> np.ndarray:
    """Hookshot sting: sub thump + transient noise + optional high tone.

    Returns mono float64 sized to `duration` with the sting starting
    at `t_start`. Mood pulls all params; for hookshot moods without a
    `sting` dict (or non-hookshot moods), returns silence.
    """
    m = MOODS[mood]
    if not m.sting:
        return np.zeros(int(duration * sr), dtype=np.float64)
    s = m.sting

    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)

    st = t - t_start

    # Sub thump
    sub_env = np.where(
        (st >= 0) & (st < s["dur"]),
        np.exp(-st * s["sub_decay"]),
        0,
    )
    out += np.sin(2 * np.pi * s["sub_hz"] * t) * s["sub_gain"] * sub_env

    # Transient noise burst
    rng = np.random.RandomState(42)  # deterministic
    transient_env = np.where(
        (st >= 0) & (st < s["transient_dur"]),
        np.exp(-st * s["transient_decay"]),
        0,
    )
    out += rng.randn(n) * s["transient_gain"] * transient_env

    # High tone (optional per mood)
    if "high_hz" in s and s.get("high_gain", 0) > 0:
        high_env = np.where(
            (st >= 0) & (st < s["high_dur"]),
            np.clip(st * 4.0, 0, 1) * np.exp(-st * 3.0),
            0,
        )
        out += np.sin(2 * np.pi * s["high_hz"] * t) * s["high_gain"] * high_env

    return out


# --------------------------------------------------------------------------- #
# Convenience: full cc_flora pad assembler (canonical-only — no events)
# --------------------------------------------------------------------------- #

def cottagecore_pad_canonical(
    duration: float,
    chime_schedule: Sequence[Tuple[float, float]],
    *,
    mood: str = "cottagecore_warm",
    sr: int = SR_DEFAULT,
    drone_gain_scale: float = 1.0,
    apply_lowpass: bool = True,
) -> np.ndarray:
    """Reproduce the canonical cc_flora `generate_ambient_pad` shape
    using primitives, MINUS per-episode editorial events.

    Useful for Phase 1 sign-off: render this against the existing
    inline output to validate the primitive's base behavior.
    """
    import scipy.signal

    pad = ambient_pad(
        duration, mood=mood, sr=sr,
        drone_gain_scale=drone_gain_scale,
        apply_envelope=False,
    )
    pad += chime_layer(duration, chime_schedule, mood=mood, sr=sr)
    pad *= pad_envelope(
        duration, sr=sr,
        fade_in_s=MOODS[mood].envelope_fade_in_s,
        fade_out_s=MOODS[mood].envelope_fade_out_s,
        floor=MOODS[mood].envelope_floor,
    )
    if apply_lowpass:
        sos = scipy.signal.butter(
            MOODS[mood].lowpass_order, MOODS[mood].lowpass_hz,
            "low", fs=sr, output="sos",
        )
        pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * MOODS[mood].pad_target_gain
    return pad
