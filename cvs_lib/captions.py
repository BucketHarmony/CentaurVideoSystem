"""Caption-event generation + rendering.

Two layers:

- **Data:** `events_from_beats(...)` builds a list of caption events
  from a BEATS list, with auto-fill from the transcript index when a
  beat omits `caption_lines`. Pure data; no MoviePy.
- **Render:** `render_caption_strip()` (PIL) and `make_caption_clips()`
  (MoviePy) produce the visual strip + ImageClips. MoviePy is imported
  lazily so the data layer can be unit-tested without it.

Auto-fill rule (when `caption_lines` is absent from a beat's spec):
- For every transcript segment whose **midpoint** falls in
  `(beat.in_t, beat.out_t)`, emit a caption event timed at the
  segment's offset within the beat.
- Empty list `caption_lines: []` suppresses captions entirely.
- Per-segment overrides via `caption_overrides={start_t: "sanitized"}`
  on the spec — keys are segment start times in source-clip seconds.

CTA beat is special-cased: captions there come from `narration_lines`
(synth VO), not the source transcript.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from cvs_lib.index import (
    DEFAULT_INDEX_DIR,
    segments_in_window,
    stem_for_path,
)


PathLike = Union[str, Path]
Beat = Tuple[str, float, str, str, dict]


def _beat_specs(beats: Sequence[Beat]) -> Iterable[Tuple[str, float, dict]]:
    for slug, dur, _chord, _label, spec in beats:
        if spec is None:
            continue
        yield slug, float(dur), spec


def _scene_start(beats: Sequence[Beat], target_slug: str) -> float:
    """Cumulative t at which a beat slug begins."""
    t = 0.0
    for slug, dur, *_ in beats:
        if slug == target_slug:
            return t
        t += float(dur)
    raise KeyError(f"unknown beat slug: {target_slug!r}")


def events_from_beats(
    beats: Sequence[Beat],
    *,
    cta_slug: str = "cta",
    narration_lines: Optional[Sequence[Dict]] = None,
    measure_tts_duration=None,
    index_dir: PathLike = DEFAULT_INDEX_DIR,
) -> List[Dict]:
    """Build caption events from BEATS.

    Returns a sorted list of ``{"start": float, "end": float, "text":
    str}`` dicts.

    Per-beat behavior:
    - `caption_lines` present → use as-is (manual override).
    - `caption_lines` absent → auto-fill from transcript index.
    - `caption_lines == []` → suppress all captions for this beat.

    The CTA beat (slug == ``cta_slug``) is sourced from
    ``narration_lines`` instead. Each entry must have ``slug``,
    ``start_in_beat``, ``text``. ``measure_tts_duration(slug) -> float``
    is called to determine end time. If unavailable, the line is skipped.
    """
    events: List[Dict] = []
    for slug, dur, spec in _beat_specs(beats):
        scene_t0 = _scene_start(beats, slug)

        if slug == cta_slug:
            for line in (narration_lines or []):
                if line.get("slug") != cta_slug:
                    continue
                if measure_tts_duration is None:
                    continue
                vo_dur = float(measure_tts_duration(cta_slug))
                if vo_dur <= 0.0:
                    continue
                start = scene_t0 + float(line["start_in_beat"])
                events.append({
                    "start": start,
                    "end": min(scene_t0 + dur, start + vo_dur),
                    "text": str(line["text"]),
                })
            continue

        if "caption_lines" in spec:
            for s_start, s_end, text in (spec.get("caption_lines") or []):
                events.append({
                    "start": scene_t0 + float(s_start),
                    "end":   scene_t0 + float(s_end),
                    "text":  str(text).strip(),
                })
            continue

        # Auto-fill from the index.
        in_t = float(spec.get("in_t", 0.0))
        out_t = float(spec.get("out_t", in_t))
        stem = stem_for_path(spec["path"])
        try:
            segs = segments_in_window(stem, in_t, out_t, index_dir=index_dir)
        except FileNotFoundError:
            segs = []
        overrides = dict(spec.get("caption_overrides") or {})
        for seg in segs:
            seg_t = float(seg["start"])
            offset_in_beat = seg_t - in_t
            seg_end_offset = float(seg["end"]) - in_t
            text_raw = overrides.get(seg_t, seg["text"])
            events.append({
                "start": scene_t0 + offset_in_beat,
                "end":   scene_t0 + seg_end_offset,
                "text":  str(text_raw).strip(),
            })

    events.sort(key=lambda e: e["start"])
    return events


# --------------------------------------------------------------------------- #
# Rendering (lazy imports so data layer is testable without MoviePy/PIL)
# --------------------------------------------------------------------------- #

def render_caption_strip(
    text: str,
    *,
    width: int,
    font_path: str,
    size: int = 64,
    max_w: int = 1000,
    fill=(255, 255, 255, 255),
    stroke_fill=(0, 0, 0, 255),
    stroke_w: int = 5,
    pad_y: int = 16,
):
    """Render a single caption strip as an RGBA numpy array.

    Returns a (H, W, 4) uint8 array sized to fit the wrapped text.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    fnt = ImageFont.truetype(font_path, size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # Word-wrap to max_w pixels.
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        l, t, r, b = measure.textbbox((0, 0), trial, font=fnt)
        if (r - l) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    line_h = int(size * 1.18)
    block_h = line_h * max(1, len(lines))
    strip_h = block_h + 2 * (pad_y + stroke_w)
    img = Image.new("RGBA", (width, strip_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y0 = pad_y + stroke_w
    for i, line in enumerate(lines):
        l, t, r, b = draw.textbbox((0, 0), line, font=fnt)
        draw_x = (width - (r - l)) // 2 - l
        draw_y = y0 + i * line_h - t
        draw.text((draw_x, draw_y), line, font=fnt, fill=fill,
                  stroke_width=stroke_w, stroke_fill=stroke_fill)
    return np.array(img)


def make_caption_clips(
    events: Sequence[Dict],
    *,
    width: int,
    caption_bottom: int,
    font_path: str,
    size: int = 64,
    max_w: int = 1000,
):
    """Build MoviePy ImageClips for caption events.

    Each event ``{"start", "end", "text"}`` becomes an ImageClip
    positioned with its bottom at ``caption_bottom`` and a 0.05–0.12s
    crossfade-in.
    """
    import numpy as np
    from moviepy.editor import ImageClip

    clips = []
    for ev in events:
        rgba = render_caption_strip(
            ev["text"], width=width, font_path=font_path,
            size=size, max_w=max_w,
        )
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3].astype(np.float32) / 255.0
        dur = max(0.05, ev["end"] - ev["start"])
        clip = ImageClip(rgb).set_duration(dur)
        clip = clip.set_mask(ImageClip(alpha, ismask=True).set_duration(dur))
        y_pos = caption_bottom - rgba.shape[0]
        clip = clip.set_start(ev["start"]).set_position((0, y_pos))
        clip = clip.crossfadein(min(0.12, dur / 4))
        clips.append(clip)
    return clips
