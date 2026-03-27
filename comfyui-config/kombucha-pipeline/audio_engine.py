"""Kombucha audio engine — ambient pad, chimes, binaural panning, TTS mix.

Generates a complete scored soundtrack:
  - A-minor drone pad with shimmer LFOs
  - Music-box chimes timed to narration gaps
  - Binaural stereo panning (slow L/R sweeps + depth)
  - ElevenLabs TTS narration mixed on top
  - Loudness normalized for Bluesky

Usage:
    from audio_engine import build_soundtrack
    audio_path = build_soundtrack(monologue, duration=25.0, mood="prowling")
"""

import math
import os
import subprocess
import tempfile
import wave

import numpy as np
import requests
import scipy.signal
from dotenv import load_dotenv

load_dotenv(r"E:\AI\CVS\.env")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "wVOQaU8CfoRJqCWsxoLv")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
SR = 44100

# ── A-minor chord frequencies ─────────────────────────────────────────────

# Root drone
A2 = 110.0
C3 = 130.81
E3 = 164.81
A3 = 220.0

# Shimmer octave
A4 = 440.0
C5 = 523.25
E5 = 659.25

# Chime octave (music box)
A5 = 880.0
C6 = 1046.50
E6 = 1318.51

# Mood color tones
MOOD_TONES = {
    "lingering":  (233.08, 0.008),   # Bb3 — melancholy
    "prowling":   (246.94, 0.006),   # B3 — tension
    "charging":   (329.63, 0.010),   # E4 — energy
    "exploring":  (293.66, 0.008),   # D4 — wonder
    "pressing":   (277.18, 0.007),   # Db4 — urgency
    "reversing":  (233.08, 0.009),   # Bb3 — retreat
    "searching":  (311.13, 0.007),   # Eb4 — longing
    "threading":  (261.63, 0.006),   # C4 — careful
    "curious":    (349.23, 0.008),   # F4 — open
}


def generate_pad_stereo(duration, mood="exploring"):
    """Generate stereo ambient pad with binaural panning.

    Returns: numpy array shape (N, 2) float64, normalized.
    """
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # ── Base drone (mono) ─────────────────────────────────────────────
    drone = np.zeros(n, dtype=np.float64)
    drone += np.sin(2 * np.pi * A2 * t) * 0.050
    drone += np.sin(2 * np.pi * C3 * t) * 0.030
    drone += np.sin(2 * np.pi * E3 * t) * 0.035
    drone += np.sin(2 * np.pi * A3 * t) * 0.025

    # ── Shimmer with LFOs (creates movement) ──────────────────────────
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    lfo3 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + 2.5)

    shimmer = np.zeros(n, dtype=np.float64)
    shimmer += np.sin(2 * np.pi * A4 * t) * 0.010 * lfo1
    shimmer += np.sin(2 * np.pi * C5 * t) * 0.007 * lfo2
    shimmer += np.sin(2 * np.pi * E5 * t) * 0.005 * lfo3

    # ── Mood color tone ───────────────────────────────────────────────
    mood_freq, mood_amp = MOOD_TONES.get(mood, (293.66, 0.007))
    lfo_mood = 0.5 + 0.5 * np.sin(2 * np.pi * 0.09 * t + 0.7)
    mood_tone = np.sin(2 * np.pi * mood_freq * t) * mood_amp * lfo_mood

    # ── Combine mono pad ──────────────────────────────────────────────
    pad_mono = drone + shimmer + mood_tone

    # ── Envelope: fade in/out, start at 30% ───────────────────────────
    env = np.clip(0.3 + 0.7 * (t / 3.0), 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    pad_mono *= env

    # ── Low-pass filter ───────────────────────────────────────────────
    sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
    pad_mono = scipy.signal.sosfilt(sos, pad_mono)

    # ── Binaural stereo panning ───────────────────────────────────────
    # Slow pan sweeps: drone drifts L/R, shimmer opposite
    pan_drone = 0.5 + 0.3 * np.sin(2 * np.pi * 0.05 * t)        # ~20s cycle
    pan_shimmer = 0.5 + 0.3 * np.sin(2 * np.pi * 0.08 * t + np.pi)  # opposite
    pan_mood = 0.5 + 0.2 * np.sin(2 * np.pi * 0.03 * t + 1.5)   # very slow

    # Binaural depth: slight frequency shift between L/R ears (~1-3Hz)
    # This creates a perceived spatial location inside the head
    binaural_beat = 2.0  # Hz difference between ears
    drone_L = drone * (1 - pan_drone) * env
    drone_R = drone * pan_drone * env
    # Add slight detune to right channel for binaural beat
    drone_R += np.sin(2 * np.pi * (A2 + binaural_beat) * t) * 0.015 * env
    drone_R += np.sin(2 * np.pi * (A3 + binaural_beat * 0.5) * t) * 0.008 * env

    shimmer_L = shimmer * (1 - pan_shimmer) * env
    shimmer_R = shimmer * pan_shimmer * env
    # Binaural shimmer: slightly different LFO phase per ear
    shimmer_R += np.sin(2 * np.pi * (A4 + 1.5) * t) * 0.004 * lfo2 * env

    mood_L = mood_tone * (1 - pan_mood) * env
    mood_R = mood_tone * pan_mood * env

    left = drone_L + shimmer_L + mood_L
    right = drone_R + shimmer_R + mood_R

    # Filter each channel
    left = scipy.signal.sosfilt(sos, left)
    right = scipy.signal.sosfilt(sos, right)

    stereo = np.column_stack([left, right])
    return stereo


def generate_chimes_stereo(duration, narration_times=None):
    """Generate music-box chimes, timed to gaps between narration.

    narration_times: list of (start, end) tuples for TTS segments.
    Chimes are placed in the gaps, plus one at t=0.1s always.

    Returns: numpy array shape (N, 2) float64.
    """
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Find gaps for chime placement
    chime_times = [0.1]  # always start with a chime

    if narration_times:
        # Add chimes in gaps between narration
        for i in range(len(narration_times)):
            gap_start = narration_times[i][1] + 0.3  # after current line ends
            if i + 1 < len(narration_times):
                gap_end = narration_times[i + 1][0] - 0.3  # before next starts
            else:
                gap_end = duration - 1.0

            if gap_end - gap_start > 1.0:
                # Place 1-2 chimes in this gap
                chime_times.append(gap_start + 0.5)
                if gap_end - gap_start > 3.0:
                    chime_times.append(gap_start + (gap_end - gap_start) * 0.6)

        # Also add chimes before first narration
        if narration_times[0][0] > 2.0:
            chime_times.append(narration_times[0][0] - 1.5)
    else:
        # No narration — regular spacing ~2.5s
        ct = 2.5
        while ct < duration - 1.0:
            chime_times.append(ct)
            ct += 2.5

    # Chime note sequence: cycle through A5, C6, E6
    chime_notes = [A5, C6, E6, A5, E6, C6]

    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    for i, ct in enumerate(sorted(chime_times)):
        if ct >= duration - 0.5:
            continue
        freq = chime_notes[i % len(chime_notes)]

        # Chime envelope: sharp attack, exponential decay
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.5) * np.clip(env_t * 20, 0, 1), 0)

        chime_signal = np.sin(2 * np.pi * freq * t) * 0.025 * env
        # Add harmonic overtone
        chime_signal += np.sin(2 * np.pi * freq * 2 * t) * 0.008 * env

        # Pan each chime to a different position (alternating L/R)
        pan = 0.3 + 0.4 * ((i % 3) / 2)  # 0.3, 0.5, 0.7
        left += chime_signal * (1 - pan)
        right += chime_signal * pan

    return np.column_stack([left, right])


def generate_tts(text, output_path):
    """Generate TTS via ElevenLabs API."""
    if not ELEVENLABS_API_KEY:
        raise ValueError("No ELEVENLABS_API_KEY in .env")

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
        json={
            "text": text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.65,
                "similarity_boost": 0.72,
                "style": 0.1,
            },
        },
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        timeout=120,
    )
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


def load_audio_as_stereo(path, sr=SR):
    """Load an audio file and return as stereo float64 numpy array."""
    import torchaudio
    waveform, sample_rate = torchaudio.load(str(path))

    # Resample if needed
    if sample_rate != sr:
        waveform = torchaudio.functional.resample(waveform, sample_rate, sr)

    arr = waveform.numpy().T  # (N, channels)

    # Convert to stereo
    if arr.ndim == 1:
        arr = np.column_stack([arr, arr])
    elif arr.shape[1] == 1:
        arr = np.column_stack([arr[:, 0], arr[:, 0]])

    return arr.astype(np.float64)


def write_wav_stereo(path, data, sr=SR):
    """Write stereo float64 array to WAV."""
    data = np.clip(data, -1, 1)
    samples = (data * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())


def build_soundtrack(monologue, duration, mood="exploring", output_dir=None):
    """Build complete scored soundtrack with ambient pad, chimes, binaural panning, and TTS.

    Args:
        monologue: Full text for TTS narration
        duration: Video duration in seconds
        mood: Mood string for color tone selection
        output_dir: Where to save files (default: ComfyUI/output)

    Returns:
        path to final mixed WAV file, actual_duration
    """
    if output_dir is None:
        output_dir = r"E:\AI\CVS\ComfyUI\output"

    print("  [audio] Generating TTS...")
    tts_path = os.path.join(output_dir, "kombucha_tts_temp.mp3")
    generate_tts(monologue, tts_path)

    # Load TTS and measure duration
    tts_stereo = load_audio_as_stereo(tts_path)
    tts_duration = len(tts_stereo) / SR
    print(f"  [audio] TTS duration: {tts_duration:.1f}s")

    # Total audio duration: max of video duration or TTS + buffer
    total_duration = max(duration, tts_duration + 3.0)

    # Narration timing: starts at 1.5s to let pad establish
    narr_start = 1.5
    narration_times = [(narr_start, narr_start + tts_duration)]

    # ── Generate layers ───────────────────────────────────────────────
    n_total = int(total_duration * SR)

    print(f"  [audio] Generating ambient pad ({mood})...")
    pad = generate_pad_stereo(total_duration, mood=mood)

    print("  [audio] Generating chimes...")
    chimes = generate_chimes_stereo(total_duration, narration_times)

    # ── Place TTS in stereo mix ───────────────────────────────────────
    tts_layer = np.zeros((n_total, 2), dtype=np.float64)
    start_sample = int(narr_start * SR)
    end_sample = min(start_sample + len(tts_stereo), n_total)
    tts_len = end_sample - start_sample

    # Center the voice with slight binaural width
    # Tiny L/R delay difference (~0.3ms) for subtle spatial presence
    delay_samples = int(0.0003 * SR)  # ~13 samples
    tts_layer[start_sample:start_sample + tts_len, 0] = tts_stereo[:tts_len, 0]
    delayed_start = start_sample + delay_samples
    delayed_end = min(delayed_start + tts_len, n_total)
    delayed_len = delayed_end - delayed_start
    tts_layer[delayed_start:delayed_end, 1] = tts_stereo[:delayed_len, 1]

    # ── Duck pad during narration ─────────────────────────────────────
    # Reduce pad volume when voice is speaking
    duck_env = np.ones(n_total, dtype=np.float64)
    for ns, ne in narration_times:
        s = int(ns * SR)
        e = min(int(ne * SR), n_total)
        # Smooth duck: 0.3s attack/release
        attack = int(0.3 * SR)
        for j in range(max(0, s - attack), s):
            duck_env[j] = min(duck_env[j], 0.4 + 0.6 * (s - j) / attack)
        duck_env[s:e] = 0.4  # duck to 40%
        for j in range(e, min(e + attack, n_total)):
            duck_env[j] = min(duck_env[j], 0.4 + 0.6 * (j - e) / attack)

    pad[:, 0] *= duck_env
    pad[:, 1] *= duck_env
    chimes[:, 0] *= duck_env
    chimes[:, 1] *= duck_env

    # ── Mix ───────────────────────────────────────────────────────────
    mix = np.zeros((n_total, 2), dtype=np.float64)
    mix += pad[:n_total]
    mix += chimes[:n_total]
    mix += tts_layer * 1.2  # voice slightly louder than music

    # Normalize
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.85

    # Write raw mix
    raw_path = os.path.join(output_dir, "kombucha_soundtrack_raw.wav")
    write_wav_stereo(raw_path, mix)

    # Loudness normalize with ffmpeg
    final_path = os.path.join(output_dir, "kombucha_soundtrack.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-ar", str(SR), "-ac", "2",
        final_path,
    ], capture_output=True)

    os.unlink(raw_path)

    # Clean up temp TTS
    if os.path.exists(tts_path):
        os.unlink(tts_path)

    actual_duration = total_duration
    print(f"  [audio] Soundtrack: {final_path} ({actual_duration:.1f}s)")
    return final_path, actual_duration
