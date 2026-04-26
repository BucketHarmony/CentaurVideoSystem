"""Read-only access to the source-clip index at mpc/index/clips/<stem>.json.

The index is produced by scripts/mpc_scan_sources.py — this module never
writes it. Each clip JSON has the schema:

    {
      "meta":            {...},        # path, duration_s, width, height, fps, codec
      "motion_timeline": [{t, motion}, ...],
      "scenes":          [{idx, t, path}, ...],
      "transcript": {
        "language": "en",
        "duration_s": float,
        "text": str,                   # full transcript
        "segments": [{start, end, text}, ...],
      },
      "tags": [str, ...]
    }
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

PathLike = Union[str, Path]

DEFAULT_INDEX_DIR = Path("E:/AI/CVS/mpc/index/clips")


def _resolve_path(stem: str, index_dir: PathLike) -> Path:
    """Resolve a clip stem (e.g. '20260425_155313') to its JSON path."""
    return Path(index_dir) / f"{stem}.json"


@lru_cache(maxsize=128)
def _load(stem: str, index_dir: str) -> dict:
    """Load and cache a clip's JSON. Internal — callers use load_clip_index."""
    p = _resolve_path(stem, index_dir)
    if not p.exists():
        raise FileNotFoundError(f"index entry not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_clip_index(
    stem: str, index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> dict:
    """Load a clip's JSON index entry by file stem.

    Cached per (stem, index_dir) — the index is read-only at runtime.
    """
    return _load(stem, str(index_dir))


def stem_for_path(path: PathLike) -> str:
    """Get the stem we'd use to look up the index for a video file path."""
    return Path(path).stem


def segments_in_window(
    stem: str, t0: float, t1: float,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> List[Dict]:
    """Return transcript segments whose **midpoint** lands in [t0, t1).

    Midpoint test handles boundary segments gracefully — a segment that
    spans 19..23s with t0=20 is included if its midpoint (21) falls
    inside the window.
    """
    if t1 <= t0:
        return []
    data = load_clip_index(stem, index_dir)
    segs = data.get("transcript", {}).get("segments", [])
    out: List[Dict] = []
    for s in segs:
        mid = 0.5 * (float(s["start"]) + float(s["end"]))
        if t0 <= mid < t1:
            out.append(dict(s))
    return out


def scenes_in_window(
    stem: str, t0: float, t1: float,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> List[Dict]:
    """Return scene-boundary entries whose `t` falls in [t0, t1)."""
    if t1 <= t0:
        return []
    data = load_clip_index(stem, index_dir)
    scenes = data.get("scenes", [])
    return [dict(s) for s in scenes if t0 <= float(s["t"]) < t1]


def motion_at(
    stem: str, t: float,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> Optional[float]:
    """Linearly interpolate motion at time t. Returns None if no data
    or t is out of bounds.

    The motion_timeline samples every ~0.5s; we interpolate between
    bracketing samples.
    """
    data = load_clip_index(stem, index_dir)
    timeline = data.get("motion_timeline", [])
    if not timeline:
        return None
    ts = [float(p["t"]) for p in timeline]
    ms = [float(p["motion"]) for p in timeline]
    if t < ts[0] or t > ts[-1]:
        return None
    # Find bracketing index — timeline is monotonic in t.
    for i in range(1, len(ts)):
        if ts[i] >= t:
            t0, t1 = ts[i - 1], ts[i]
            m0, m1 = ms[i - 1], ms[i]
            if t1 == t0:
                return m0
            frac = (t - t0) / (t1 - t0)
            return m0 + (m1 - m0) * frac
    return ms[-1]


def transcript_text(
    stem: str, index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> str:
    """Full transcript text for a clip."""
    return load_clip_index(stem, index_dir).get("transcript", {}).get("text", "")


def tags(
    stem: str, index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> List[str]:
    """Return the tag list for a clip."""
    return list(load_clip_index(stem, index_dir).get("tags", []))


def clear_cache() -> None:
    """Reset the load cache (for tests that mutate fixtures)."""
    _load.cache_clear()
