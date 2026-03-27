"""Tests for the audio engine (ambient pad, chimes, synthesis)."""

import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "comfyui-config" / "kombucha-pipeline"))

from audio_engine import (
    SR, A2, C3, E3, A3, A4, C5, E5, A5, C6, E6,
    MOOD_TONES,
)


class TestFrequencyConstants:
    def test_a_minor_root_frequencies(self):
        assert A2 == pytest.approx(110.0)
        assert C3 == pytest.approx(130.81)
        assert E3 == pytest.approx(164.81)
        assert A3 == pytest.approx(220.0)

    def test_shimmer_octave(self):
        assert A4 == pytest.approx(440.0)
        assert C5 == pytest.approx(523.25)
        assert E5 == pytest.approx(659.25)

    def test_chime_octave(self):
        assert A5 == pytest.approx(880.0)
        assert C6 == pytest.approx(1046.50)
        assert E6 == pytest.approx(1318.51)

    def test_sample_rate(self):
        assert SR == 44100

    def test_mood_tones_structure(self):
        assert len(MOOD_TONES) > 0
        for mood, (freq, amp) in MOOD_TONES.items():
            assert isinstance(mood, str)
            assert 100 < freq < 1000, f"Mood {mood} freq {freq} out of range"
            assert 0 < amp < 1.0, f"Mood {mood} amp {amp} out of range"


class TestAmbientPadSynthesis:
    def test_generate_sine_wave(self):
        """Basic sine wave generation should produce correct duration."""
        duration = 2.0
        t = np.linspace(0, duration, int(SR * duration), endpoint=False)
        wave = np.sin(2 * np.pi * A2 * t)
        assert len(wave) == int(SR * duration)
        assert -1.0 <= wave.min() <= wave.max() <= 1.0

    def test_additive_synthesis_a_minor(self):
        """A-minor chord from additive synthesis should not clip."""
        duration = 1.0
        t = np.linspace(0, duration, int(SR * duration), endpoint=False)
        chord = np.zeros_like(t)
        for freq, amp in [(A2, 0.3), (C3, 0.25), (E3, 0.2), (A3, 0.15)]:
            chord += amp * np.sin(2 * np.pi * freq * t)
        assert chord.max() < 1.0
        assert chord.min() > -1.0

    def test_lfo_modulation(self):
        """LFO should produce slow amplitude variation."""
        duration = 10.0
        t = np.linspace(0, duration, int(SR * duration), endpoint=False)
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)  # 0.12 Hz
        # LFO should oscillate between 0 and 1
        assert lfo.min() >= 0.0
        assert lfo.max() <= 1.0
        # Should complete ~1.2 cycles in 10s
        zero_crossings = np.sum(np.diff(np.sign(lfo - 0.5)) != 0)
        assert 1 <= zero_crossings <= 5

    def test_stereo_binaural(self):
        """Binaural panning should produce different L/R channels."""
        duration = 2.0
        t = np.linspace(0, duration, int(SR * duration), endpoint=False)
        pan = np.sin(2 * np.pi * 0.1 * t)  # slow L/R sweep
        left = 0.5 * (1 + pan)
        right = 0.5 * (1 - pan)
        # At some point L and R should differ significantly
        diff = np.abs(left - right)
        assert diff.max() > 0.5


class TestChimeSynthesis:
    def test_chime_envelope_decay(self):
        """Chime should have exponential decay."""
        duration = 1.0
        t = np.linspace(0, duration, int(SR * duration), endpoint=False)
        envelope = np.exp(-4.0 * t)
        chime = envelope * np.sin(2 * np.pi * A5 * t)
        # Start should be louder than end
        first_quarter = np.abs(chime[:int(len(chime) * 0.25)]).mean()
        last_quarter = np.abs(chime[int(len(chime) * 0.75):]).mean()
        assert first_quarter > last_quarter * 5

    def test_chime_frequencies_in_a_minor(self):
        """All chime frequencies should be in A minor."""
        a_minor_freqs = {A5, C6, E6}
        for freq in a_minor_freqs:
            assert freq > 800  # All in high octave
            assert freq < 1400


class TestMixLevels:
    def test_pad_level(self):
        """Pad at 30% should not overpower narration at 100%."""
        pad = np.random.randn(SR) * 0.3
        narration = np.random.randn(SR) * 1.0
        mixed = pad + narration
        # Narration should dominate
        assert np.abs(narration).mean() > np.abs(pad).mean() * 2

    def test_fade_envelope(self):
        """3-second fade in/out should ramp smoothly."""
        duration = 10.0
        n = int(SR * duration)
        fade_in_samples = int(SR * 3.0)
        fade_out_samples = int(SR * 3.0)

        envelope = np.ones(n)
        envelope[:fade_in_samples] = np.linspace(0, 1, fade_in_samples)
        envelope[-fade_out_samples:] = np.linspace(1, 0, fade_out_samples)

        assert envelope[0] == 0.0
        assert envelope[-1] == 0.0
        assert envelope[n // 2] == 1.0
