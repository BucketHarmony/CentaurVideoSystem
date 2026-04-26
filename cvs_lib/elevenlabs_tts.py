"""ElevenLabs TTS: synth → cache → mix into a track.

Two functions:
- `synthesize_narration(...)` — generate (or load cached) MP3 per
  narration line, decode, place into a float32 track at the right
  scene-relative time.
- `measure_tts_duration(...)` — read a cached MP3's duration without
  rendering. Used by caption layer to time the CTA strip.

Both depend on `requests` (HTTP) and `pydub` (decode). They import
lazily so callers without TTS configured don't pay the cost.

Cache layout:
    {cache_dir}/{cache_prefix}_{slug}.mp3
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Union

import numpy as np


PathLike = Union[str, Path]
DEFAULT_SR = 44100


def measure_tts_duration(
    slug: str, *, cache_dir: PathLike, cache_prefix: str,
) -> float:
    """Duration in seconds of a cached TTS line. Returns 0.0 if the
    file is missing or undecodable."""
    try:
        from pydub import AudioSegment
    except ImportError:
        return 0.0
    p = Path(cache_dir) / f"{cache_prefix}_{slug}.mp3"
    if not p.exists():
        return 0.0
    try:
        return AudioSegment.from_mp3(str(p)).duration_seconds
    except Exception:
        return 0.0


def generate_tts(
    *,
    text: str,
    api_key: str,
    voice_id: str,
    model: str = "eleven_multilingual_v2",
    cache_path: PathLike,
    stability: float = 0.55,
    similarity_boost: float = 0.75,
    style: Optional[float] = None,
    timeout: float = 60.0,
) -> bool:
    """Generate (or load cached) TTS for one line. Returns True on
    success. Writes the MP3 to `cache_path`.

    `style` is optional — only sent to the API when non-None. cc_flora
    scripts use it (0.1 or 0.15); MPC scripts don't.
    """
    cache_path = Path(cache_path)
    if cache_path.exists():
        return True
    try:
        import requests
    except ImportError:
        print("[tts] missing dep: requests")
        return False
    voice_settings: Dict[str, float] = {
        "stability": stability,
        "similarity_boost": similarity_boost,
    }
    if style is not None:
        voice_settings["style"] = style
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": model,
            "voice_settings": voice_settings,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        print(f"[tts] ERROR {r.status_code}: {r.text[:200]}")
        return False
    cache_path.write_bytes(r.content)
    return True


def synthesize_narration(
    env: Dict[str, str],
    narration_lines: Sequence[Dict],
    *,
    cache_dir: PathLike,
    cache_prefix: str,
    duration: float,
    scene_start: Callable[[str], float],
    sr: int = DEFAULT_SR,
    line_gain: float = 0.95,
) -> Optional[np.ndarray]:
    """Synth all narration lines, decode, lay into a float32 track.

    `narration_lines` items must have keys: ``slug`` (matches a beat
    slug), ``start_in_beat`` (seconds offset within the beat),
    ``text``. ``scene_start(slug) -> float`` returns the cumulative t
    where that beat starts in the timeline.

    Returns None if the API key is missing (so callers can fall back
    silently). Returns the track on success — even if some individual
    lines were cached vs. fresh.
    """
    api_key = env.get("ELEVENLABS_API_KEY")
    voice = env.get("ELEVENLABS_VOICE")
    model = env.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
        print("[narration] no API key — skipping")
        return None
    try:
        from pydub import AudioSegment
    except ImportError as e:
        print(f"[narration] missing dep: {e}")
        return None

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    total_n = int(sr * duration)
    track = np.zeros(total_n, dtype=np.float32)
    for line in narration_lines:
        slug = line["slug"]
        cache = cache_dir / f"{cache_prefix}_{slug}.mp3"
        if not cache.exists():
            print(f"[narration] generating {slug}: {line['text']!r}")
            ok = generate_tts(
                text=line["text"],
                api_key=api_key,
                voice_id=voice,
                model=model,
                cache_path=cache,
            )
            if not ok:
                return None
        else:
            print(f"[narration] cached {slug}")
        seg = AudioSegment.from_mp3(cache).set_frame_rate(sr).set_channels(1)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples = samples / float(1 << (8 * seg.sample_width - 1))
        scene_t = scene_start(slug) + float(line["start_in_beat"])
        i0 = int(scene_t * sr)
        i1 = min(total_n, i0 + len(samples))
        if i1 > i0:
            track[i0:i1] += samples[: i1 - i0] * line_gain
    return track
