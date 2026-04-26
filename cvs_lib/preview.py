"""Beat preview: render PNG stills of each beat without audio/encoding.

Drops the iteration loop from a ~4-minute full render to ~10 seconds.
Each beat becomes one PNG: footage frame at the middle of the beat's
in/out window with the beat's chrome composited on top.

Usage from a script's main():

    if "--preview" in sys.argv:
        from cvs_lib.preview import render_beat_stills
        render_beat_stills(
            beats=BEATS,
            out_dir=PREVIEW_DIR,
            chrome_for=chrome_for,
            spec_well=_spec_well,
            W=W, H=H,
            rotation_cache_dir=_ROT_CACHE_DIR,
        )
        sys.exit(0)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Sequence, Tuple, Union

import numpy as np


PathLike = Union[str, Path]


def _composite(frame: np.ndarray, chrome_rgba: np.ndarray,
               well_top: int, well_h: int, W: int, H: int) -> np.ndarray:
    """Place `frame` in the well; blend `chrome_rgba` on top. Returns RGB."""
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    if frame is not None:
        fh, fw = frame.shape[:2]
        if fw == W and fh == well_h:
            canvas[well_top:well_top + well_h] = frame
    rgb = chrome_rgba[..., :3].astype(np.float32)
    alpha = chrome_rgba[..., 3:4].astype(np.float32) / 255.0
    canvas = (canvas.astype(np.float32) * (1 - alpha) + rgb * alpha).astype(np.uint8)
    return canvas


def render_beat_stills(
    beats: Sequence,
    *,
    out_dir: PathLike,
    chrome_for: Callable,
    spec_well: Callable,
    W: int,
    H: int,
    rotation_cache_dir: PathLike,
) -> List[Path]:
    """Render one PNG per beat.

    Args:
        beats: BEATS list, each entry ``(slug, dur, chord, chip_label, spec)``.
            ``spec`` may be a dict, a list of dicts, or None.
        out_dir: directory to write PNGs into (created).
        chrome_for: ``chrome_for(slug, chip_label, spec) -> rgba (H,W,4)``.
            Called once per beat. Should return well-transparent chrome.
        spec_well: ``spec_well(spec) -> (well_top, well_h)``. Receives the
            beat's spec (dict / list / None). For None specs, return
            sensible defaults — the well will be black behind a fully
            opaque chrome.
        W, H: frame dimensions.
        rotation_cache_dir: dir for ffmpeg rotation cache.

    Returns:
        List of written PNG paths.
    """
    from PIL import Image
    from cvs_lib.moviepy_helpers import prepare_one_clip

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    for slug, dur, _chord, chip_label, spec in beats:
        chrome = chrome_for(slug, chip_label, spec)
        well_top, well_h = spec_well(spec)
        frame = None
        if spec is not None:
            shot = spec[0] if isinstance(spec, list) else spec
            try:
                clip = prepare_one_clip(
                    shot, target_w=W, well_h=well_h,
                    rotation_cache_dir=rotation_cache_dir,
                )
                mid_t = max(0.0, min(clip.duration - 0.01, clip.duration / 2))
                frame = clip.get_frame(mid_t)
                clip.close()
            except Exception as e:
                print(f"[preview/{slug}] frame grab failed: {e}")
                frame = None
        canvas = _composite(frame, chrome, well_top, well_h, W, H)
        out = out_dir / f"{slug}.png"
        Image.fromarray(canvas, "RGB").save(out)
        print(f"[preview/{slug}] -> {out}")
        written.append(out)
    return written
