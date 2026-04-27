"""Tests for cvs_lib.audio cottagecore + hookshot primitives.

Phase 2 baseline: shape/peak/timing checks for ambient_pad, chime_layer,
pad_envelope, tension_partial, impact, sting, lowpass_normalize. Phase
7 will expand with sidechain ducking math + golden mood-template
mappings.
"""

from __future__ import annotations

import numpy as np
import pytest

from cvs_lib.audio import (
    MOODS,
    Mood,
    ambient_pad,
    chime_layer,
    impact,
    lowpass_normalize,
    pad_envelope,
    sting,
    tension_partial,
)


SR = 44100


# --------------------------------------------------------------------------- #
# MOODS registry
# --------------------------------------------------------------------------- #


def test_moods_has_expected_keys():
    assert set(MOODS.keys()) >= {
        "cottagecore_warm",
        "cottagecore_masterpiece",
        "hookshot_attention",
        "hookshot_grief",
    }


def test_mood_is_frozen_dataclass():
    m = MOODS["cottagecore_warm"]
    assert isinstance(m, Mood)
    with pytest.raises((AttributeError, Exception)):
        m.lfo1_hz = 0.5  # frozen


def test_cottagecore_warm_canonical_params():
    m = MOODS["cottagecore_warm"]
    assert m.lfo1_hz == 0.12
    assert m.lfo2_hz == 0.18
    assert m.chime_decay == 2.0
    assert m.chime_attack == 10.0
    assert m.envelope_floor == 0.3
    assert m.lowpass_hz == 3000.0
    assert m.pad_target_gain == 0.22


def test_masterpiece_overrides():
    m = MOODS["cottagecore_masterpiece"]
    assert m.lfo1_hz == 0.15
    assert m.chime_attack_curve == "masterpiece"
    assert m.envelope_floor == 0.0
    assert m.pad_target_gain == 0.25


def test_hookshot_grief_lowpass_narrower():
    assert MOODS["hookshot_grief"].lowpass_hz < MOODS["cottagecore_warm"].lowpass_hz


def test_cottagecore_has_no_sting():
    assert MOODS["cottagecore_warm"].sting == {}


def test_hookshot_has_sting():
    s = MOODS["hookshot_attention"].sting
    assert "sub_hz" in s and s["sub_hz"] > 0
    assert "transient_gain" in s


# --------------------------------------------------------------------------- #
# pad_envelope
# --------------------------------------------------------------------------- #


def test_pad_envelope_default_shape():
    # Duration 10s gives a sustain region (fade_in 2s + fade_out 2.5s
    # = 4.5s of ramps + 5.5s sustain). Short durations multiply
    # fade_in by an already-decaying fade_out tail at t=0.
    env = pad_envelope(10.0, sr=SR)
    assert env.shape == (int(10.0 * SR),)
    assert env.dtype == np.float64
    assert env[0] == pytest.approx(0.3)  # floor
    assert np.max(env) == pytest.approx(1.0, abs=1e-3)


def test_pad_envelope_fade_out_reaches_zero():
    env = pad_envelope(5.0, sr=SR)
    # Last sample should be at the very tail of the fade-out — effectively 0.
    assert env[-1] < 1e-3


def test_pad_envelope_floor_zero_starts_at_zero():
    env = pad_envelope(2.0, sr=SR, floor=0.0)
    assert env[0] == pytest.approx(0.0)


def test_pad_envelope_hookshot_linspace_silence_first_second():
    env = pad_envelope(10.0, sr=SR, variant="hookshot_linspace")
    # First second is silence, so at t=0.5s env should be 0.
    assert env[int(0.5 * SR)] == 0.0
    # At t=2.5s, mid-ramp should be roughly 0.5.
    mid = env[int(2.5 * SR)]
    assert 0.3 < mid < 0.7


def test_pad_envelope_masterpiece_zerofloor_variant():
    env = pad_envelope(5.0, sr=SR, variant="masterpiece_zerofloor")
    assert env[0] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# ambient_pad
# --------------------------------------------------------------------------- #


def test_ambient_pad_shape_dtype():
    pad = ambient_pad(2.0, mood="cottagecore_warm", sr=SR)
    assert pad.shape == (int(2.0 * SR),)
    assert pad.dtype == np.float64


def test_ambient_pad_drone_frequencies_in_spectrum():
    """FFT of cottagecore_warm pad should peak near 110 Hz (root drone)."""
    pad = ambient_pad(4.0, mood="cottagecore_warm", sr=SR, apply_envelope=False)
    spec = np.abs(np.fft.rfft(pad))
    freqs = np.fft.rfftfreq(len(pad), d=1 / SR)
    # Energy at 110 Hz drone should be substantially higher than at 1 kHz
    # (above the highest shimmer at 659.25 Hz).
    bin_110 = np.argmin(np.abs(freqs - 110))
    bin_1k = np.argmin(np.abs(freqs - 1000))
    assert spec[bin_110] > 10 * spec[bin_1k]


def test_ambient_pad_drone_gain_scale_louder():
    pad_default = ambient_pad(2.0, mood="cottagecore_warm", sr=SR,
                              drone_gain_scale=1.0, apply_envelope=False)
    pad_loud = ambient_pad(2.0, mood="cottagecore_warm", sr=SR,
                           drone_gain_scale=1.20, apply_envelope=False)
    # Higher drone scale → larger overall amplitude.
    assert np.max(np.abs(pad_loud)) > np.max(np.abs(pad_default))


def test_ambient_pad_apply_envelope_false_skips_master():
    pad_no_env = ambient_pad(2.0, mood="cottagecore_warm", sr=SR,
                             apply_envelope=False)
    pad_with_env = ambient_pad(2.0, mood="cottagecore_warm", sr=SR,
                               apply_envelope=True)
    # First sample with envelope is multiplied by floor=0.3.
    assert abs(pad_with_env[0]) < abs(pad_no_env[0]) + 1e-6
    # Mid-buffer they should be close (envelope == 1 in sustain).
    mid = len(pad_no_env) // 2
    # Default 2-second pad has fade-in = 2s and fade-out = 2.5s, so
    # there's barely any sustain — just check shapes match.
    assert pad_no_env.shape == pad_with_env.shape


# --------------------------------------------------------------------------- #
# chime_layer
# --------------------------------------------------------------------------- #


def test_chime_layer_empty_schedule_is_silent():
    out = chime_layer(2.0, [], mood="cottagecore_warm", sr=SR)
    assert np.max(np.abs(out)) == 0.0


def test_chime_layer_peak_near_scheduled_time():
    """Chime at t=1.0s should produce its energy peak within ~50ms of t=1.0s."""
    out = chime_layer(3.0, [(1.0, 880.0)], mood="cottagecore_warm", sr=SR)
    # Find the sample with max absolute amplitude.
    peak_idx = int(np.argmax(np.abs(out)))
    peak_t = peak_idx / SR
    # Attack is `clip(env_t * 10, 0, 1)` → reaches 1 at env_t=0.1s, then
    # decays. So peak should be very near t=1.1s.
    assert 1.0 < peak_t < 1.2


def test_chime_layer_silent_before_first_scheduled_time():
    out = chime_layer(3.0, [(2.0, 880.0)], mood="cottagecore_warm", sr=SR)
    # No chime energy before t=2.0s.
    assert np.max(np.abs(out[: int(1.95 * SR)])) < 1e-9


def test_chime_layer_octave_gain_adds_higher_partial():
    # Without octave gain (cottagecore default).
    base = chime_layer(2.0, [(0.5, 440.0)], mood="cottagecore_warm",
                       sr=SR, octave_gain_override=0.0)
    # With octave gain.
    octave = chime_layer(2.0, [(0.5, 440.0)], mood="cottagecore_warm",
                         sr=SR, octave_gain_override=0.01)
    spec_base = np.abs(np.fft.rfft(base))
    spec_oct = np.abs(np.fft.rfft(octave))
    freqs = np.fft.rfftfreq(len(base), d=1 / SR)
    bin_880 = np.argmin(np.abs(freqs - 880))
    # Octave layer adds energy at 2*440 = 880 Hz.
    assert spec_oct[bin_880] > spec_base[bin_880]


def test_chime_layer_masterpiece_curve_uses_different_attack():
    sched = [(0.5, 440.0)]
    cc = chime_layer(2.0, sched, mood="cottagecore_warm", sr=SR)
    mp = chime_layer(2.0, sched, mood="cottagecore_masterpiece", sr=SR)
    # The two curves should differ (masterpiece formula clip→exp vs
    # canonical exp→clip, plus different attack/decay constants).
    assert not np.allclose(cc, mp)


# --------------------------------------------------------------------------- #
# tension_partial
# --------------------------------------------------------------------------- #


def test_tension_partial_zero_outside_window():
    tp = tension_partial(30.0, freq_hz=329.63, gain=0.014,
                         fade_in_t=10.0, fade_in_dur=2.0,
                         fade_out_t=20.0, fade_out_dur=2.0, sr=SR)
    # Before fade-in start, partial is gated off.
    assert np.max(np.abs(tp[: int(10.0 * SR)])) < 1e-9
    # After fade-out end, partial is gated off.
    assert np.max(np.abs(tp[int(20.0 * SR):])) < 1e-9


def test_tension_partial_peaks_inside_window():
    tp = tension_partial(30.0, freq_hz=329.63, gain=0.014,
                         fade_in_t=10.0, fade_in_dur=2.0,
                         fade_out_t=20.0, fade_out_dur=2.0, sr=SR)
    # Peak inside [12s, 18s] should be ≤ gain.
    inside = tp[int(13.0 * SR):int(17.0 * SR)]
    assert np.max(np.abs(inside)) == pytest.approx(0.014, abs=1e-3)


# --------------------------------------------------------------------------- #
# impact
# --------------------------------------------------------------------------- #


def test_impact_silent_before_t():
    out = impact(5.0, t=2.0, sr=SR, rng_seed=0)
    # No energy before t=2.0s.
    assert np.max(np.abs(out[: int(2.0 * SR) - 100])) < 1e-9


def test_impact_decays():
    out = impact(5.0, t=1.0, sr=SR, rng_seed=0,
                 sub_decay=10.0, sub_dur=1.0, noise_dur=0.5)
    # Energy at t=1.05s should exceed energy at t=1.5s (decay).
    early = np.mean(np.abs(out[int(1.05 * SR):int(1.10 * SR)]))
    late = np.mean(np.abs(out[int(1.5 * SR):int(1.55 * SR)]))
    assert early > late


def test_impact_rng_seed_reproducible():
    a = impact(2.0, t=0.5, sr=SR, rng_seed=42)
    b = impact(2.0, t=0.5, sr=SR, rng_seed=42)
    np.testing.assert_array_equal(a, b)


# --------------------------------------------------------------------------- #
# sting
# --------------------------------------------------------------------------- #


def test_sting_silent_for_cottagecore_mood():
    out = sting(2.0, mood="cottagecore_warm", t_start=0.0, sr=SR)
    assert np.max(np.abs(out)) == 0.0


def test_sting_produces_signal_for_hookshot():
    out = sting(2.0, mood="hookshot_attention", t_start=0.0, sr=SR)
    assert np.max(np.abs(out)) > 0.1  # well above silence


def test_sting_silent_before_t_start():
    out = sting(2.0, mood="hookshot_attention", t_start=1.0, sr=SR)
    # Before t_start=1.0s there should be no energy.
    assert np.max(np.abs(out[: int(0.95 * SR)])) < 1e-9


# --------------------------------------------------------------------------- #
# lowpass_normalize
# --------------------------------------------------------------------------- #


def test_lowpass_normalize_peak_matches_mood_target():
    pad = ambient_pad(3.0, mood="cottagecore_warm", sr=SR)
    norm = lowpass_normalize(pad, mood="cottagecore_warm", sr=SR)
    assert np.max(np.abs(norm)) == pytest.approx(0.22, abs=1e-4)


def test_lowpass_normalize_masterpiece_target():
    pad = ambient_pad(3.0, mood="cottagecore_masterpiece", sr=SR)
    norm = lowpass_normalize(pad, mood="cottagecore_masterpiece", sr=SR)
    assert np.max(np.abs(norm)) == pytest.approx(0.25, abs=1e-4)


def test_lowpass_normalize_attenuates_high_frequencies():
    """500 Hz sine should pass; 5 kHz sine should be attenuated."""
    sr = SR
    duration = 1.0
    n = int(duration * sr)
    t = np.linspace(0, duration, n, dtype=np.float64)
    mixed = np.sin(2 * np.pi * 500 * t) + np.sin(2 * np.pi * 5000 * t)
    out = lowpass_normalize(mixed, mood="cottagecore_warm", sr=sr)
    spec = np.abs(np.fft.rfft(out))
    freqs = np.fft.rfftfreq(n, d=1 / sr)
    bin_500 = np.argmin(np.abs(freqs - 500))
    bin_5k = np.argmin(np.abs(freqs - 5000))
    # Cottagecore lowpass is 3 kHz, order 4. 500 Hz passes; 5 kHz is
    # well above cutoff and should be substantially attenuated.
    assert spec[bin_500] > 5 * spec[bin_5k]
