"""MoviePy compositing helpers.

Footage prep (rotation bake + crop), chrome→ImageClip mask building, and
single-beat composition. MoviePy is imported lazily so importing this
module doesn't drag MoviePy into preflight/test contexts.

Rotation cache: phone footage with rotation metadata gets pre-baked to
an upright mp4 because MoviePy 1.0.3 ignores the rotation tag. Cache
key is mtime; cache invalidates when source mp4 is re-encoded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np


PathLike = Union[str, Path]


# --------------------------------------------------------------------------- #
# Rotation cache
# --------------------------------------------------------------------------- #

def get_rotation(path: PathLike) -> int:
    """Return rotation degrees in source video metadata, or 0 if absent.

    Uses ffprobe; any failure → 0 (pass through).
    """
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream_side_data=rotation",
             "-of", "default=nw=1:nk=1", str(path)],
            stderr=subprocess.STDOUT,
        ).decode().strip()
        return int(float(out)) if out else 0
    except Exception:
        return 0


def rotation_baked_path(path: PathLike, *, cache_dir: PathLike) -> Path:
    """If `path` has rotation metadata, return a baked upright copy in
    `cache_dir`. Otherwise return the original path. Cache hits via
    mtime check.
    """
    path = Path(path)
    if get_rotation(path) == 0:
        return path
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{path.stem}_rot.mp4"
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", str(path),
           "-metadata:s:v", "rotate=0",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k",
           str(out)]
    print(f"[rotate] baking {path.name} -> {out.name}")
    subprocess.run(cmd, check=True)
    return out


# --------------------------------------------------------------------------- #
# Footage prep
# --------------------------------------------------------------------------- #

def prepare_one_clip(spec: dict, *, target_w: int, well_h: int,
                     rotation_cache_dir: PathLike):
    """Subclip + scale + crop one source to (target_w, well_h).

    `spec` keys:
        path        — source mp4 (required)
        in_t, out_t — subclip range (required)
        crop_x_frac — horizontal center as fraction of full scaled width
                      (0.5 default — middle of the frame)
    """
    from moviepy.editor import VideoFileClip
    src = rotation_baked_path(spec["path"], cache_dir=rotation_cache_dir)
    clip = VideoFileClip(str(src)).subclip(spec["in_t"], spec["out_t"])
    clip = clip.without_audio()
    scaled = clip.resize(height=well_h)
    crop_frac = float(spec.get("crop_x_frac", 0.5))
    if scaled.w > target_w:
        x_center = scaled.w * crop_frac
        x_center = max(target_w / 2, min(scaled.w - target_w / 2, x_center))
        return scaled.crop(x_center=x_center, width=target_w, height=well_h)
    if scaled.w < target_w:
        widened = clip.resize(width=target_w)
        if widened.h > well_h:
            return widened.crop(y_center=widened.h / 2, width=target_w, height=well_h)
        return widened
    return scaled


def prepare_footage(spec, *, target_w: int, well_h: int,
                    duration: float, rotation_cache_dir: PathLike):
    """Build a footage clip from a spec or a list of specs (concatenated)."""
    from moviepy.editor import concatenate_videoclips
    specs = spec if isinstance(spec, list) else [spec]
    sub_clips = [
        prepare_one_clip(s, target_w=target_w, well_h=well_h,
                         rotation_cache_dir=rotation_cache_dir)
        for s in specs
    ]
    out = sub_clips[0] if len(sub_clips) == 1 else concatenate_videoclips(
        sub_clips, method="compose")
    return out.set_duration(duration)


def spec_well(spec, *, default_top: int, default_h: int) -> Tuple[int, int]:
    """Return (well_top, well_h) for a beat spec, falling back to defaults."""
    s = spec[0] if isinstance(spec, list) else spec
    return int(s.get("well_top", default_top)), int(s.get("well_h", default_h))


# --------------------------------------------------------------------------- #
# Chrome → ImageClip
# --------------------------------------------------------------------------- #

def make_chrome_clip(rgba: np.ndarray, duration: float):
    """RGBA chrome array → MoviePy ImageClip with alpha mask."""
    from moviepy.editor import ImageClip
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    chrome = ImageClip(rgb).set_duration(duration)
    mask = ImageClip(alpha, ismask=True).set_duration(duration)
    return chrome.set_mask(mask)


# --------------------------------------------------------------------------- #
# Single-beat composer
# --------------------------------------------------------------------------- #

def build_beat_clip(*, chrome_rgba: np.ndarray,
                    footage_spec, duration: float,
                    W: int, H: int,
                    well_top: int, well_h: int,
                    rotation_cache_dir: PathLike,
                    fadein: float = 0.0, fadeout: float = 0.0):
    """Compose one beat: black BG + footage in well + RGBA chrome on top.

    `footage_spec` may be a single spec dict or a list (concatenated).
    `well_top`/`well_h` come from `spec_well(...)`.
    """
    from moviepy.editor import ColorClip, CompositeVideoClip
    chrome = make_chrome_clip(chrome_rgba, duration)
    footage = prepare_footage(
        footage_spec, target_w=W, well_h=well_h,
        duration=duration, rotation_cache_dir=rotation_cache_dir,
    ).set_position((0, well_top))
    bg = ColorClip(size=(W, H), color=(0, 0, 0)).set_duration(duration)
    clip = CompositeVideoClip([bg, footage, chrome], size=(W, H)).set_duration(duration)
    if fadein > 0:
        clip = clip.crossfadein(fadein)
    if fadeout > 0:
        clip = clip.crossfadeout(fadeout)
    return clip
