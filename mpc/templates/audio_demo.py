"""
Audio bed for the MPC 30s brand demo.

Synthesizes:
  - Ambient pad (additive sines, A-minor harmonic family)
  - Scene-transition stings (sub-bass thumps + filtered noise bursts)
  - Optional ElevenLabs narration (if API key available in .env)

Mixes everything to a single 30s WAV at 44.1k stereo. Runs standalone for
preview, or imported by template_30s_demo.py.

Output: ComfyUI/output/mpc/template_30s_demo_audio.wav
"""

from __future__ import annotations

import os
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = Path("E:/AI/CVS/.env")
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_WAV = OUTPUT_DIR / "template_30s_demo_audio.wav"

SR = 44100
DURATION = 30.0
N = int(SR * DURATION)
T = np.linspace(0.0, DURATION, N, endpoint=False)

# Scene boundaries (seconds) — must match template_30s_demo.py
SCENES = [0.0, 3.0, 8.0, 18.0, 25.0, 30.0]

NARRATION_LINES = [
    {"text": "Here's what they actually voted for.",        "start": 0.4, "scene": "hook"},
    {"text": "On April 15, the Michigan House voted on HB twelve thirty-four — the school lunch funding bill.",
                                                            "start": 3.6, "scene": "setup"},
    # No narration over the quote scene (8-18) — let the pull-quote breathe
    {"text": "Meanwhile, the same legislator voted for corporate tax breaks and to defund school safety.",
                                                            "start": 18.5, "scene": "receipts"},
    {"text": "Follow the fight at miprogressivecaucus.com.","start": 25.7, "scene": "endcard"},
]


# --------------------------------------------------------------------------- #
# .env loader (keep dependency-free)
# --------------------------------------------------------------------------- #

def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# --------------------------------------------------------------------------- #
# Energy curve — climbs from sparse to anthemic across the 30s
# --------------------------------------------------------------------------- #

# Per-scene energy targets (0..1). Music GROWS instead of holding flat or fading.
ENERGY_KEYFRAMES = [
    (0.0,  0.55),   # Hook — already present, not a fade-in
    (3.0,  0.70),   # Setup — building
    (8.0,  0.80),   # Quote — confident
    (18.0, 0.88),   # Receipts — driving
    (25.0, 1.00),   # Endcard — peak
    (29.5, 1.00),   # Hold the peak
    (30.0, 0.85),   # Tiny tail (avoid harsh cut)
]


def energy_curve() -> np.ndarray:
    """Linear interpolation between keyframes, sample-rate resolution."""
    keys_t = np.array([k[0] for k in ENERGY_KEYFRAMES])
    keys_v = np.array([k[1] for k in ENERGY_KEYFRAMES])
    return np.interp(T, keys_t, keys_v).astype(np.float32)


# --------------------------------------------------------------------------- #
# Anthem pad — A MAJOR additive synth (uplifting, not contemplative)
# --------------------------------------------------------------------------- #

def anthem_pad(energy: np.ndarray) -> np.ndarray:
    """
    Mono pad in A major — root, major 3rd, perfect 5th establish bright tonality.
    Amplitude is modulated by the energy curve so the pad GROWS through the
    video instead of holding flat.
    """
    pad = np.zeros(N, dtype=np.float32)

    # Foundation (rooted, always present from the start)
    foundation = [
        (110.00, 0.045),   # A2  — root
        (138.59, 0.030),   # C#3 — MAJOR third (the big tonality switch)
        (164.81, 0.038),   # E3  — perfect 5th
        (220.00, 0.028),   # A3  — octave
        (277.18, 0.020),   # C#4 — major 3rd above
        (329.63, 0.022),   # E4  — uplifting upper voice
    ]
    # Shimmer (anthemic upper register, energy-gated so they swell as we climb)
    shimmer = [
        (440.00, 0.014, 0.10),   # A4
        (554.37, 0.012, 0.14),   # C#5
        (659.25, 0.010, 0.18),   # E5
        (880.00, 0.008, 0.22),   # A5 — that "anthem sparkle" register
    ]

    for f, a in foundation:
        pad += a * np.sin(2 * np.pi * f * T)

    for f, a, lfo_hz in shimmer:
        # Shimmer voices follow energy curve — quiet at start, blazing at end
        gate = 0.4 + 0.6 * energy
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * lfo_hz * T)
        pad += a * gate * lfo * np.sin(2 * np.pi * f * T)

    # Apply global energy envelope to the foundation as well (gentler swing)
    pad *= 0.55 + 0.45 * energy

    # NO fadeout. Anthems don't fade — they land. Tiny tail handled by keyframes.
    fadein_n = int(SR * 0.6)
    pad[:fadein_n] *= np.linspace(0.6, 1.0, fadein_n)

    # Slight lowpass for warmth, but brighter than the cottagecore version
    b, a = butter(4, 5500 / (SR / 2), btype="low")
    pad = lfilter(b, a, pad).astype(np.float32)
    return pad


# --------------------------------------------------------------------------- #
# Heartbeat pulse — steady forward motion (replaces ambient hold)
# --------------------------------------------------------------------------- #

BPM = 108  # anthemic walking tempo — "All You Need Is Love" energy
BEAT = 60.0 / BPM


def heartbeat(start_t: float, end_t: float, energy: np.ndarray,
              accent_pattern: tuple = (1.0, 0.6, 0.85, 0.6)) -> np.ndarray:
    """
    Kick-drum-like pulses on every beat between start_t and end_t.
    Volume tracks the energy curve. Accent pattern emphasizes downbeats.
    """
    out = np.zeros(N, dtype=np.float32)
    t = start_t
    beat_idx = 0
    while t < end_t and t < DURATION:
        i0 = int(t * SR)
        if i0 >= N:
            break
        # Pulse: sub-sine with sharp attack, fast decay
        dur = 0.18
        n = min(N - i0, int(dur * SR))
        t_local = np.linspace(0, dur, n, endpoint=False)
        # 90Hz → 55Hz pitched-down sweep — tight kick character
        sweep = 90 * np.exp(-12 * t_local) + 55 * (1 - np.exp(-12 * t_local))
        phase = 2 * np.pi * np.cumsum(sweep) / SR
        env = np.exp(-9 * t_local)
        accent = accent_pattern[beat_idx % len(accent_pattern)]
        # Energy modulation at the pulse's start time
        e_here = float(energy[i0]) if i0 < N else 1.0
        amp = 0.30 * accent * (0.4 + 0.6 * e_here)
        out[i0:i0 + n] += amp * env * np.sin(phase)
        t += BEAT
        beat_idx += 1
    return out


# --------------------------------------------------------------------------- #
# Hand claps — the "people power" element. Enters in the back half.
# --------------------------------------------------------------------------- #

def hand_clap(t_start: float, amp: float = 0.18) -> np.ndarray:
    """Single hand-clap: bandpass-filtered noise burst around 1.5kHz."""
    out = np.zeros(N, dtype=np.float32)
    i0 = int(t_start * SR)
    if i0 >= N:
        return out
    dur = 0.10
    n = min(N - i0, int(dur * SR))
    rng = np.random.RandomState(int(t_start * 1000) % (2**31))
    burst = rng.randn(n).astype(np.float32)
    # Bandpass 1k-3k for clap "snap"
    b, a = butter(4, [1000 / (SR / 2), 3000 / (SR / 2)], btype="band")
    burst = lfilter(b, a, burst).astype(np.float32)
    # Sharp attack, exponential decay
    env = np.exp(-30 * np.linspace(0, dur, n, endpoint=False))
    out[i0:i0 + n] = amp * env * burst
    return out


def clap_pattern(start_t: float, end_t: float, beats_on: tuple = (1, 3),
                 amp: float = 0.18) -> np.ndarray:
    """
    Hand claps on specified beats of every 4-beat bar (0-indexed).
    Default (1, 3) = backbeat (beats 2 and 4 in 1-indexed counting).
    """
    out = np.zeros(N, dtype=np.float32)
    t = start_t
    beat_idx = 0
    while t < end_t and t < DURATION:
        if (beat_idx % 4) in beats_on:
            out += hand_clap(t, amp=amp)
        t += BEAT
        beat_idx += 1
    return out


# --------------------------------------------------------------------------- #
# Rising swells — replace the descending thumps. These LIFT instead of HIT.
# --------------------------------------------------------------------------- #

def rising_swell(land_t: float, build_dur: float = 1.2, amp: float = 0.18) -> np.ndarray:
    """
    Ascending pitch + noise sweep that LANDS at land_t (build phase precedes it).
    Combines a pitched-up sine sweep with a filtered noise riser. Communicates
    "something good is coming" rather than "impact."
    """
    out = np.zeros(N, dtype=np.float32)
    start_t = max(0.0, land_t - build_dur)
    i0 = int(start_t * SR)
    i1 = min(N, int(land_t * SR))
    if i0 >= N or i1 <= i0:
        return out
    n = i1 - i0
    t_local = np.linspace(0, build_dur, n, endpoint=False)

    # Pitched-UP sine sweep (220Hz → 660Hz, A3 → E5)
    sweep = 220 * (1 + 2 * (t_local / build_dur) ** 1.6)
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    env = (t_local / build_dur) ** 1.5  # ramp up
    out[i0:i1] += 0.08 * env * np.sin(phase)

    # Filtered noise riser
    rng = np.random.RandomState(int(start_t * 1000) % (2**31))
    burst = rng.randn(n).astype(np.float32)
    b, a = butter(4, 4000 / (SR / 2), btype="high")
    burst = lfilter(b, a, burst).astype(np.float32)
    out[i0:i1] += amp * env * burst * 0.5
    return out


def downbeat_landing(t: float, amp: float = 0.32) -> np.ndarray:
    """A satisfying landing hit — sub thump + bright transient — for scene starts."""
    out = np.zeros(N, dtype=np.float32)
    i0 = int(t * SR)
    if i0 >= N:
        return out
    # Sub component (short, doesn't sustain)
    dur = 0.30
    n = min(N - i0, int(dur * SR))
    t_local = np.linspace(0, dur, n, endpoint=False)
    sub = 0.25 * np.exp(-7 * t_local) * np.sin(2 * np.pi * 65 * t_local)
    out[i0:i0 + n] += amp * sub
    # Bright "snap" on top
    rng = np.random.RandomState(int(t * 1000) % (2**31))
    n2 = min(N - i0, int(0.06 * SR))
    snap = rng.randn(n2).astype(np.float32)
    b, a = butter(4, 5000 / (SR / 2), btype="high")
    snap = lfilter(b, a, snap).astype(np.float32)
    snap_env = np.exp(-50 * np.linspace(0, 0.06, n2, endpoint=False))
    out[i0:i0 + n2] += amp * 0.4 * snap_env * snap
    return out


# --------------------------------------------------------------------------- #
# Build the full mix
# --------------------------------------------------------------------------- #

def music_bed() -> np.ndarray:
    """Compose all the musical elements into one mono track."""
    energy = energy_curve()
    bed = np.zeros(N, dtype=np.float32)

    # Pad: continuous, climbing
    bed += anthem_pad(energy)

    # Heartbeat: starts mid-setup (4.0s), drives through to endcard
    bed += heartbeat(start_t=4.0, end_t=29.5, energy=energy)

    # Claps: "people power" — enter at receipts (18s), peak through endcard
    # First with backbeat (2 & 4), then quarter notes for last bar
    bed += clap_pattern(start_t=18.0, end_t=25.0, beats_on=(1, 3), amp=0.16)
    bed += clap_pattern(start_t=25.0, end_t=29.5, beats_on=(0, 1, 2, 3), amp=0.20)

    # Rising swells — land at scene boundaries (transitions LIFT, not hit)
    for t in [3.0, 8.0, 18.0, 25.0]:
        bed += rising_swell(land_t=t, build_dur=1.2, amp=0.14)

    # Landing hits at the openers we want to feel decisive
    bed += downbeat_landing(0.0, amp=0.30)        # Hook entrance
    bed += downbeat_landing(8.0, amp=0.22)        # Quote entrance
    bed += downbeat_landing(25.0, amp=0.30)       # Endcard entrance

    return bed


# --------------------------------------------------------------------------- #
# ElevenLabs TTS (optional)
# --------------------------------------------------------------------------- #

def synthesize_narration(env: dict[str, str]) -> np.ndarray | None:
    """Returns mono float32 narration track, or None if TTS unavailable."""
    api_key = env.get("ELEVENLABS_API_KEY")
    voice = env.get("ELEVENLABS_VOICE", "pNInz6obpgDQGcFmaJgB")
    model = env.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
        print("[narration] no ELEVENLABS_API_KEY — skipping TTS")
        return None

    try:
        import requests
    except ImportError:
        print("[narration] requests not installed — skipping TTS")
        return None

    try:
        from pydub import AudioSegment
        from io import BytesIO
    except ImportError:
        print("[narration] pydub not available — skipping TTS")
        return None

    track = np.zeros(N, dtype=np.float32)
    cache_dir = OUTPUT_DIR / "tts_cache"
    cache_dir.mkdir(exist_ok=True)

    for i, line in enumerate(NARRATION_LINES):
        cache_path = cache_dir / f"demo_line_{i}.mp3"
        if not cache_path.exists():
            print(f"[narration] generating line {i}: {line['text'][:50]!r}")
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": line["text"],
                    "model_id": model,
                    "voice_settings": {"stability": 0.55, "similarity_boost": 0.75},
                },
                timeout=60,
            )
            if r.status_code != 200:
                print(f"  ERROR {r.status_code}: {r.text[:200]}")
                return None
            cache_path.write_bytes(r.content)
        else:
            print(f"[narration] cached line {i}")

        seg = AudioSegment.from_mp3(cache_path).set_frame_rate(SR).set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        # Normalize int16 → float32
        samples = samples / float(1 << (8 * seg.sample_width - 1))
        # Place at start time
        i0 = int(line["start"] * SR)
        i1 = min(N, i0 + len(samples))
        track[i0:i1] += samples[: i1 - i0] * 0.85

    return track


# --------------------------------------------------------------------------- #
# Mix & write
# --------------------------------------------------------------------------- #

def to_int16_stereo(mono: np.ndarray) -> np.ndarray:
    """Convert mono float32 in [-1, 1] to int16 stereo interleaved."""
    mono = np.clip(mono, -1.0, 1.0)
    # Light stereo widening: dry/wet difference between L/R
    delay_n = int(SR * 0.012)
    delayed = np.concatenate([np.zeros(delay_n, dtype=np.float32), mono[:-delay_n]])
    L = mono * 0.95 + delayed * 0.10
    R = mono * 0.95 - delayed * 0.10 * 0.6
    L = np.clip(L, -1.0, 1.0)
    R = np.clip(R, -1.0, 1.0)
    L_i = (L * 32767).astype(np.int16)
    R_i = (R * 32767).astype(np.int16)
    return np.column_stack([L_i, R_i]).flatten()


def sidechain_duck(bed: np.ndarray, voice: np.ndarray,
                   threshold: float = 0.02, ratio: float = 0.45,
                   attack_ms: float = 30, release_ms: float = 200) -> np.ndarray:
    """Quick & dirty sidechain ducking — drop bed where voice is loud."""
    if voice is None:
        return bed
    # Voice envelope (rectified + smoothed)
    env = np.abs(voice)
    # IIR smoothing (one-pole)
    a_atk = np.exp(-1 / (SR * attack_ms / 1000))
    a_rel = np.exp(-1 / (SR * release_ms / 1000))
    smoothed = np.zeros_like(env)
    s = 0.0
    for i in range(len(env)):
        coef = a_atk if env[i] > s else a_rel
        s = coef * s + (1 - coef) * env[i]
        smoothed[i] = s
    # Map env → gain reduction
    duck = 1.0 - np.clip((smoothed - threshold) / threshold, 0, 1) * (1 - ratio)
    return bed * duck.astype(np.float32)


def build() -> np.ndarray:
    print("[audio] building anthem music bed (major key, climbing energy)...")
    bed = music_bed()

    env = load_env()
    print("[audio] synthesizing narration...")
    voice = synthesize_narration(env)

    print("[audio] mixing with sidechain ducking...")
    # Duck the bed where voice is present so narration sits on top cleanly.
    # Lighter duck than before — anthemic mix shouldn't drop out as much.
    if voice is not None:
        bed = sidechain_duck(bed, voice, threshold=0.03, ratio=0.55)
        mix = bed * 0.80 + voice * 1.0
    else:
        mix = bed * 0.95

    # Normalize to peak ~0.9 (loudnorm later if posting to platforms)
    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.9

    return mix


def write_wav(mono: np.ndarray, path: Path = OUT_WAV) -> Path:
    stereo = to_int16_stereo(mono)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"[audio] wrote {path}")
    return path


def main() -> None:
    mix = build()
    write_wav(mix)


if __name__ == "__main__":
    main()
