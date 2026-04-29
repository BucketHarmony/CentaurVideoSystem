"""Markdown renderers for the rally scout dashboard.

Each function is a pure transform from the index-clip JSON into a
markdown string. The driver in `scripts/scout_dashboard.py` composes
them per stem and writes files; tests exercise the pure functions
directly without touching disk.

Schema is documented in `cvs_lib.index` (load_clip_index). Briefly:
meta (path, duration, fps, codec, dims), motion_timeline ({t, motion}),
scenes ({idx, t, path}), transcript ({segments [{start,end,text}],
text}), tags, audio_dominant ({class, fraction}).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def _fmt_t(t: float) -> str:
    """Compact mm:ss for transcript timestamps; sub-minute clips show
    just seconds."""
    if t < 60:
        return f"{t:5.2f}s"
    m, s = divmod(t, 60.0)
    return f"{int(m)}:{s:05.2f}"


def format_meta(data: Dict) -> str:
    """Header block: filename + a one-line summary of the source."""
    meta = data.get("meta", {})
    fname = meta.get("filename", "?")
    dur = float(meta.get("duration_s", 0.0))
    w = meta.get("width", "?")
    h = meta.get("height", "?")
    fps = meta.get("fps", "?")
    codec = meta.get("codec", "?")
    dom = data.get("audio_dominant", {}) or {}
    aud = dom.get("class", "?")
    frac = dom.get("fraction", 0.0)
    aud_summary = f"{aud}" + (f" ({frac:.0%})" if isinstance(frac, (int, float)) else "")
    return (
        f"# {fname}\n\n"
        f"- **Duration**: {dur:.1f}s\n"
        f"- **Resolution**: {w}x{h} @ {fps} fps ({codec})\n"
        f"- **Audio**: {aud_summary}\n"
    )


def format_tags(data: Dict) -> str:
    tags = data.get("tags") or []
    if not tags:
        return ""
    return "- **Tags**: " + ", ".join(f"`{t}`" for t in sorted(tags)) + "\n"


def format_transcript(data: Dict, *, max_chars_per_segment: int = 0) -> str:
    """Markdown-rendered transcript: each segment as `[mm:ss-mm:ss] text`.

    `max_chars_per_segment > 0` truncates long segments with `...`. 0
    (default) keeps full text — editorial reads better with everything.
    """
    t = data.get("transcript") or {}
    segs = t.get("segments") or []
    if not segs:
        text = t.get("text", "")
        if not text:
            return "## Transcript\n\n*(none)*\n"
        return f"## Transcript\n\n> {text.strip()}\n"
    lines = ["## Transcript", ""]
    for s in segs:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", start))
        body = (s.get("text") or "").strip()
        if max_chars_per_segment and len(body) > max_chars_per_segment:
            body = body[:max_chars_per_segment].rstrip() + "..."
        lines.append(f"- `[{_fmt_t(start)} - {_fmt_t(end)}]` {body}")
    lines.append("")
    return "\n".join(lines)


def format_scenes(
    data: Dict, *,
    thumbs_relative_to: Optional[Path] = None,
    limit: int = 12,
) -> str:
    """Scene thumbnails as a markdown gallery. `thumbs_relative_to` is
    the directory the dashboard MD will live in — paths are made
    relative so the rendered file/HTML viewer can resolve them. If
    None, absolute paths are emitted (still openable from a viewer
    that follows file:// links)."""
    scenes = data.get("scenes") or []
    if not scenes:
        return ""
    lines = [f"## Scenes ({len(scenes)})", ""]
    for s in scenes[:limit]:
        t = float(s.get("t", 0.0))
        path = s.get("path", "")
        if thumbs_relative_to is not None and path:
            try:
                path = Path(path).resolve().relative_to(
                    thumbs_relative_to.resolve(),
                ).as_posix()
            except ValueError:
                # Different drive / can't make relative — keep absolute,
                # convert backslashes for cross-renderer compatibility.
                path = Path(path).as_posix()
        lines.append(f"- `[{_fmt_t(t)}]` ![scene]({path})")
    if len(scenes) > limit:
        lines.append(f"- *... {len(scenes) - limit} more scenes*")
    lines.append("")
    return "\n".join(lines)


def format_motion_peaks(
    data: Dict, *, top_n: int = 5,
) -> str:
    """Top-N motion peak timestamps. Useful for finding the high-energy
    moments in a clip without scrubbing."""
    timeline = data.get("motion_timeline") or []
    if not timeline:
        return ""
    sorted_ts = sorted(
        timeline, key=lambda x: -float(x.get("motion", 0)),
    )[:top_n]
    sorted_ts.sort(key=lambda x: float(x.get("t", 0)))
    if not sorted_ts:
        return ""
    lines = [f"## Motion peaks (top {top_n})", ""]
    for entry in sorted_ts:
        t = float(entry.get("t", 0))
        m = float(entry.get("motion", 0))
        lines.append(f"- `[{_fmt_t(t)}]` motion={m:.1f}")
    lines.append("")
    return "\n".join(lines)


def render_stem_page(
    stem: str,
    data: Dict,
    *,
    thumbs_relative_to: Optional[Path] = None,
    scene_limit: int = 12,
    motion_top_n: int = 5,
    max_segment_chars: int = 0,
) -> str:
    """Compose the full per-stem dashboard page."""
    parts = [
        format_meta(data),
        format_tags(data),
    ]
    src = data.get("meta", {}).get("path")
    if src:
        # Source path as a footer link so editorial can open the clip.
        parts.append(f"- **Source**: `{src}`\n")
    parts.append("\n")
    parts.append(format_transcript(data, max_chars_per_segment=max_segment_chars))
    parts.append("\n")
    parts.append(format_motion_peaks(data, top_n=motion_top_n))
    parts.append("\n")
    parts.append(format_scenes(
        data, thumbs_relative_to=thumbs_relative_to, limit=scene_limit,
    ))
    return "".join(parts)


def render_index_page(
    title: str,
    entries: Sequence[Tuple[str, Dict]],
) -> str:
    """Top-level index linking each per-stem page. `entries` is a
    sequence of `(stem, data)` tuples (data is the loaded JSON, used
    for one-line summaries)."""
    lines = [
        f"# {title}",
        "",
        f"{len(entries)} clip(s) indexed.",
        "",
        "| Stem | Duration | Audio | Tags | Transcript preview |",
        "|------|---------:|-------|------|--------------------|",
    ]
    for stem, data in entries:
        meta = data.get("meta", {})
        dur = float(meta.get("duration_s", 0.0))
        dom = (data.get("audio_dominant") or {}).get("class", "?")
        tags = ", ".join((data.get("tags") or [])[:3])
        text = (data.get("transcript", {}) or {}).get("text", "") or ""
        preview = text.strip().replace("|", " ").replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:77] + "..."
        lines.append(
            f"| [`{stem}`]({stem}.md) | {dur:.1f}s | {dom} | "
            f"{tags} | {preview} |"
        )
    lines.append("")
    return "\n".join(lines)
