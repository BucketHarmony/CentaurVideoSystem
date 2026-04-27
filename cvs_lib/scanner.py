"""Source-clip scanner — turn a video file into a structured index entry.

Pure-function library extracted from `scripts/mpc_scan_sources.py`. The
script orchestrates batches and persists to SQLite; this module owns the
per-clip work: probe → motion → scenes → thumbnails → transcript → tags.

Schema produced:

    {
      "meta": {path, filename, duration_s, size_bytes,
               width, height, fps, codec},
      "motion_timeline": [{t, motion}, ...],
      "scenes": [{idx, t, path}, ...],
      "transcript": {
        "language", "language_probability", "duration_s",
        "text", "segments": [{start, end, text, words?}, ...],
        "model", "vad", "initial_prompt"
      },
      "tags": [str, ...]
    }

This matches v1 schema additively — `words` and `model`/`vad`/
`initial_prompt` fields are new but old readers ignore them.

## Phase 0 findings baked in (2026-04-27)

- **Default model: `large-v3`** (was `small`). Recovered "Romulus
  engaged…cannot ignore" where small heard "Romulus and Gates…cannot go
  on", and "love and protect all our neighbors" where small hallucinated
  "love you girls".
- **Default `vad_filter=False`** (was True). VAD silently dropped sung
  content even on loud chant clips. Toggle on via `vad=True` for
  speech-only clips with crowd noise floor.
- **`initial_prompt` is vocabulary-only**, not phrase-bearing. First
  attempt quoted exact chant strings and those leaked verbatim into
  output transcripts. Pass nouns/names; let whisper figure out the
  syntax.
- **`word_timestamps=True`** by default — needed for karaoke (built one
  reel today that had to hand-run word-level transcription) and for
  Phase 3 clean-cut boundaries.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

PathLike = Union[str, Path]

SCANNER_VERSION = 2  # bump when schema changes

# Heuristic transcript-keyword → tag mapping. Word-boundary regexes keep
# "ice" out of "police" and "march" out of "marchioness".
TAG_PATTERNS: Dict[str, List[str]] = {
    "march":      [r"\bmarch(ing|ed|es)?\b", r"\brally\b", r"\bdemonstration\b"],
    "chant":      [r"\bchant", r"\bshout"],
    "warehouse":  [r"\bwarehouse"],
    "DHS":        [r"\bDHS\b", r"\bhomeland security\b"],
    "ICE":        [r"\bICE\b", r"\bimmigration enforcement\b"],
    "Romulus":    [r"\bromulus\b", r"\bcogswell\b"],
    "Nessel":     [r"\bnessel\b", r"\battorney general\b"],
    "immigrant":  [r"\bimmigra(nt|tion)\b", r"\basylum\b", r"\bdetention\b"],
    "press":      [r"\bpresser\b", r"\bpress conference\b"],
    "speech":     [r"\bfellow\b", r"\bneighbors?\b", r"\bcommunity\b"],
    "court":      [r"\bcourt\b", r"\binjunction\b", r"\bsuing\b", r"\blawsuit\b"],
}


# --------------------------------------------------------------------------- #
# ffprobe / OpenCV: metadata + motion timeline
# --------------------------------------------------------------------------- #

def probe_video(path: PathLike) -> Dict:
    """Read container/stream metadata via ffprobe.

    Returns the v1 meta dict shape (path, filename, duration_s, size_bytes,
    width, height, fps, codec). On parse failure, fps defaults to 30.0.
    """
    path = Path(path)
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    info = json.loads(out.stdout) if out.stdout else {}
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    fps_str = vstream.get("r_frame_rate", "30/1")
    try:
        num, den = map(int, fps_str.split("/"))
        fps = num / den if den else 30.0
    except Exception:
        fps = 30.0
    return {
        "path": str(path),
        "filename": path.name,
        "duration_s": float(fmt.get("duration", 0)),
        "size_bytes": int(fmt.get("size", 0)),
        "width": int(vstream.get("width", 0)),
        "height": int(vstream.get("height", 0)),
        "fps": fps,
        "codec": vstream.get("codec_name", "unknown"),
    }


def motion_timeline(path: PathLike, sample_rate_hz: float = 2.0) -> List[Dict]:
    """Sample frame-diff motion at ~`sample_rate_hz` Hz.

    Frames are downsampled to 320x180 grayscale before diffing — fast
    and insensitive to compression noise at the original res.
    """
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps / sample_rate_hz)))
    timeline: List[Dict] = []
    prev = None
    f = 0
    while f < n:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            motion = float(np.abs(gray.astype(int) - prev.astype(int)).mean())
            timeline.append({"t": round(f / fps, 3), "motion": round(motion, 3)})
        prev = gray
        f += step
    cap.release()
    return timeline


def detect_scenes(timeline: Sequence[Dict],
                  threshold: float = 14.0,
                  min_gap_s: float = 1.5) -> List[float]:
    """Treat motion spikes above `threshold` as scene boundaries.

    `min_gap_s` prevents a sustained spike from registering as N
    back-to-back cuts. Always includes 0.0 as the first scene start.
    """
    cuts: List[float] = [0.0]
    last_t = 0.0
    for entry in timeline:
        if entry["motion"] > threshold and entry["t"] - last_t >= min_gap_s:
            cuts.append(entry["t"])
            last_t = entry["t"]
    return cuts


def extract_thumbnails(path: PathLike, scene_starts: Sequence[float],
                       out_dir: PathLike, prefix: str) -> List[Dict]:
    """One JPG per scene start, downscaled to 640w."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    out: List[Dict] = []
    for i, t in enumerate(scene_starts):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        new_w = 640
        new_h = max(1, int(h * (new_w / w)))
        small = cv2.resize(frame, (new_w, new_h))
        out_path = out_dir / f"{prefix}_s{i:02d}_t{int(t):04d}.jpg"
        cv2.imwrite(str(out_path), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        out.append({"idx": i, "t": float(t), "path": str(out_path)})
    cap.release()
    return out


# --------------------------------------------------------------------------- #
# Whisper: transcription
# --------------------------------------------------------------------------- #

def load_whisper(model_size: str = "large-v3",
                 device: str = "cuda",
                 compute_type: str = "float16"):
    """Return a faster-whisper WhisperModel; fall back to CPU/int8 on CUDA failure.

    Stashes `_cvs_model_size` on the returned object so `transcribe()`
    can record which model produced a transcript (faster-whisper's
    WhisperModel doesn't expose the size string itself).
    """
    from faster_whisper import WhisperModel
    try:
        m = WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as e:
        print(f"  [whisper] {device}/{compute_type} failed ({e}); "
              f"falling back to cpu/int8")
        m = WhisperModel(model_size, device="cpu", compute_type="int8")
    m._cvs_model_size = model_size
    return m


def transcribe(path: PathLike, model, *,
               initial_prompt: Optional[str] = None,
               vad: bool = False,
               beam_size: int = 5,
               word_timestamps: bool = True,
               language: str = "en") -> Dict:
    """Run whisper on `path`. Returns the v1 transcript schema with
    additive fields for `words`, `model`, `vad`, `initial_prompt`.

    Defaults reflect Phase 0 findings: VAD off, beam=5, word_ts on.
    """
    segments_iter, info = model.transcribe(
        str(path),
        language=language,
        beam_size=beam_size,
        vad_filter=vad,
        vad_parameters=dict(min_silence_duration_ms=500) if vad else None,
        word_timestamps=word_timestamps,
        initial_prompt=initial_prompt,
    )
    segments: List[Dict] = []
    parts: List[str] = []
    for seg in segments_iter:
        text = seg.text.strip()
        rec: Dict = {
            "start": round(float(seg.start), 3),
            "end":   round(float(seg.end), 3),
            "text":  text,
        }
        if word_timestamps and seg.words:
            rec["words"] = [
                {"start": round(float(w.start), 3),
                 "end":   round(float(w.end), 3),
                 "word":  w.word.strip()}
                for w in seg.words
            ]
        segments.append(rec)
        if text:
            parts.append(text)

    model_id = getattr(model, "_cvs_model_size", None) or "unknown"

    return {
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "duration_s": float(info.duration),
        "text": " ".join(parts).strip(),
        "segments": segments,
        "model": model_id,
        "vad": vad,
        "initial_prompt": initial_prompt,
    }


# --------------------------------------------------------------------------- #
# Prompt registry (per source folder)
# --------------------------------------------------------------------------- #

DEFAULT_PROMPTS_PATH = Path("E:/AI/CVS/mpc/scanner_prompts.json")


def load_prompts(path: PathLike = DEFAULT_PROMPTS_PATH) -> Dict[str, str]:
    """Load the per-source vocabulary prompt registry."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def prompt_for_path(video_path: PathLike,
                    prompts_path: PathLike = DEFAULT_PROMPTS_PATH
                    ) -> Optional[str]:
    """Resolve the initial_prompt for a video by its parent folder name.

    `raw/MPC/Ice Out Romulus/20260425_170245.mp4` looks up the
    "Ice Out Romulus" entry in `mpc/scanner_prompts.json`. Returns
    None if no entry exists.
    """
    prompts = load_prompts(prompts_path)
    parent = Path(video_path).parent.name
    return prompts.get(parent)


# --------------------------------------------------------------------------- #
# Tag derivation
# --------------------------------------------------------------------------- #

def derive_tags(meta: Dict, transcript: Dict, timeline: Sequence[Dict]) -> List[str]:
    """Heuristic tag set from transcript text, motion stats, duration, orientation."""
    tags = set()
    text = transcript.get("text", "")

    for tag, patterns in TAG_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            tags.add(tag)

    if timeline:
        motions = [e["motion"] for e in timeline]
        avg_m = sum(motions) / len(motions)
        max_m = max(motions)
        if avg_m < 3.0:
            tags.add("static")
        elif avg_m > 14.0:
            tags.add("high_motion")
        if max_m > 30.0:
            tags.add("camera_shake")

    text_strip = text.strip()
    if not text_strip:
        tags.add("silent")
    elif len(text_strip) > 200:
        tags.add("dialogue")
    else:
        tags.add("ambient")

    if meta["duration_s"] < 8:
        tags.add("short")
    elif meta["duration_s"] > 60:
        tags.add("long")

    if meta.get("height", 0) > meta.get("width", 0):
        tags.add("vertical")
    else:
        tags.add("horizontal")

    return sorted(tags)


# --------------------------------------------------------------------------- #
# Per-clip orchestration
# --------------------------------------------------------------------------- #

def scan_clip(path: PathLike, model, *,
              thumbnails_dir: Optional[PathLike] = None,
              initial_prompt: Optional[str] = None,
              vad: bool = False,
              motion_hz: float = 2.0,
              scene_threshold: float = 14.0,
              scene_min_gap_s: float = 1.5,
              prompts_path: PathLike = DEFAULT_PROMPTS_PATH,
              audio_classify: bool = True,
              audio_class_model=None,
              verbose: bool = False) -> Dict:
    """Scan one clip end-to-end and return the v2 schema dict.

    `model` is a faster-whisper WhisperModel from `load_whisper`. The
    function does NOT persist anything; the caller chooses where to
    write the JSON / DB row.

    `initial_prompt`: explicit override. If None, resolved via
    `prompt_for_path` (parent folder lookup in `scanner_prompts.json`).

    `audio_classify=True` (Phase 2 default) runs the PANNs CNN14
    classifier and adds:
        record["audio_segments"]: [{t0, t1, class, confidence}, ...]
        record["audio_dominant"]: {"class": str, "fraction": float}
        record["tags"] gets the dominant class appended (e.g. "song").
    Pass False to skip (no PANNs / GPU memory; useful for tests).
    """
    path = Path(path)
    if initial_prompt is None:
        initial_prompt = prompt_for_path(path, prompts_path)

    if verbose:
        print(f"  probe...")
    meta = probe_video(path)

    if verbose:
        print(f"  motion timeline ({motion_hz} Hz)...")
    timeline = motion_timeline(path, sample_rate_hz=motion_hz)

    cuts = detect_scenes(timeline, threshold=scene_threshold,
                         min_gap_s=scene_min_gap_s)
    if verbose:
        print(f"  scenes: {len(cuts)}")

    scenes: List[Dict] = []
    if thumbnails_dir is not None:
        scenes = extract_thumbnails(path, cuts, thumbnails_dir, path.stem)
    else:
        scenes = [{"idx": i, "t": float(t), "path": ""} for i, t in enumerate(cuts)]

    if verbose:
        print(f"  whisper transcribe (prompt={'yes' if initial_prompt else 'no'}, "
              f"vad={'on' if vad else 'off'})...")
    transcript = transcribe(path, model,
                            initial_prompt=initial_prompt, vad=vad)

    audio_segments: List[Dict] = []
    audio_dominant: Optional[Dict] = None
    salient: List[str] = []
    if audio_classify:
        if verbose:
            print(f"  audio classify (PANNs CNN14)...")
        from cvs_lib import audio_class
        audio_segments = audio_class.classify_clip(
            path, model=audio_class_model)
        cls, frac = audio_class.dominant_class(audio_segments)
        audio_dominant = {"class": cls, "fraction": round(frac, 3)}
        salient = audio_class.salient_classes(audio_segments)

    tags = derive_tags(meta, transcript, timeline)
    if salient:
        tags = sorted(set(tags) | set(salient))

    record: Dict = {
        "meta": meta,
        "motion_timeline": timeline,
        "scenes": scenes,
        "transcript": transcript,
        "tags": tags,
        "scanner_version": SCANNER_VERSION,
    }
    if audio_classify:
        record["audio_segments"] = audio_segments
        record["audio_dominant"] = audio_dominant
    return record
