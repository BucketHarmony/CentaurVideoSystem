#!/usr/bin/env python3
"""
CVS -- Video Scout
Fast frame-by-frame analysis tool for finding key moments in tick videos.

Modes:
  motion   - Find biggest motion spikes (collisions, falls, fast moves)
  bright   - Find brightness changes (lights, flips, overexposure)
  tilt     - Detect camera rotation (falls, flips) via edge angle analysis
  extract  - Save frames at specific timestamps as JPGs
  scan     - Full scan: motion + brightness + tilt combined

Usage:
    python scripts/video_scout.py motion E:/AI/Kombucha/video/web/tick_0277.mp4
    python scripts/video_scout.py motion tick_0277.mp4 --start 90 --end 130 --resolution 0.1
    python scripts/video_scout.py extract tick_0277.mp4 --times 116.5,116.7,117.0,118.0
    python scripts/video_scout.py scan tick_0277.mp4 --top 10
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load_clip(video_path):
    from moviepy.editor import VideoFileClip
    # Try multiple paths
    p = Path(video_path)
    if not p.exists():
        # Try Kombucha paths
        import os
        kombucha = Path(os.getenv("KOMBUCHA_DIR", "E:/AI/Kombucha"))
        for subdir in ["video/web", "video"]:
            alt = kombucha / subdir / p.name
            if alt.exists():
                p = alt
                break
    if not p.exists():
        print(f"  ERROR: {video_path} not found")
        sys.exit(1)
    return VideoFileClip(str(p))


def get_frame(clip, t):
    """Safe frame extraction."""
    t = max(0, min(t, clip.duration - 0.05))
    return clip.get_frame(t)


def analyze_motion(clip, start, end, resolution):
    """Find frame-to-frame motion spikes."""
    results = []
    prev = None
    for t in np.arange(start, end, resolution):
        frame = get_frame(clip, t)
        if prev is not None:
            change = np.abs(frame.astype(float) - prev.astype(float)).mean()
            results.append((t, change))
        prev = frame.copy()
    return sorted(results, key=lambda x: x[1], reverse=True)


def analyze_brightness(clip, start, end, resolution):
    """Find brightness changes and inversions (top vs bottom)."""
    results = []
    prev_bright = None
    for t in np.arange(start, end, resolution):
        frame = get_frame(clip, t)
        h = frame.shape[0]
        brightness = frame.mean()
        top = frame[:h//2].mean()
        bottom = frame[h//2:].mean()
        delta = abs(brightness - prev_bright) if prev_bright is not None else 0
        inversion = bottom - top  # positive = brighter bottom (normal), negative = flipped
        results.append((t, brightness, delta, top, bottom, inversion))
        prev_bright = brightness
    return results


def analyze_tilt(clip, start, end, resolution):
    """Detect camera rotation by comparing horizontal vs vertical edge energy."""
    results = []
    for t in np.arange(start, end, resolution):
        frame = get_frame(clip, t)
        gray = np.mean(frame, axis=2)
        # Horizontal edges (camera tilting = horizontal edges become vertical)
        horiz = np.abs(np.diff(gray, axis=0)).mean()
        vert = np.abs(np.diff(gray, axis=1)).mean()
        ratio = vert / max(horiz, 0.001)  # >1 means more vertical edges than normal
        results.append((t, ratio, horiz, vert))
    return results


def cmd_motion(args):
    clip = load_clip(args.video)
    start = args.start if args.start is not None else 0
    end = args.end if args.end is not None else clip.duration
    res = args.resolution

    print(f"  Scanning {Path(args.video).name} for motion ({start:.1f}s - {end:.1f}s, {res}s resolution)")
    results = analyze_motion(clip, start, end, res)
    clip.close()

    top = args.top
    print(f"\n  Top {top} motion spikes:")
    print(f"  {'Time':>8s}  {'Change':>8s}  {'Bar'}")
    print(f"  {'----':>8s}  {'------':>8s}  {'---'}")
    max_change = results[0][1] if results else 1
    for t, change in results[:top]:
        bar_len = int(40 * change / max_change)
        bar = '#' * bar_len
        print(f"  {t:8.2f}s  {change:8.1f}  {bar}")

    print(f"\n  Recommended hook start: t={results[0][0] - 0.25:.2f}s (0.25s before biggest spike)")


def cmd_brightness(args):
    clip = load_clip(args.video)
    start = args.start if args.start is not None else 0
    end = args.end if args.end is not None else clip.duration
    res = args.resolution

    print(f"  Scanning {Path(args.video).name} for brightness ({start:.1f}s - {end:.1f}s)")
    results = analyze_brightness(clip, start, end, res)
    clip.close()

    # Find biggest brightness deltas
    by_delta = sorted(results, key=lambda x: x[2], reverse=True)
    print(f"\n  Top {args.top} brightness changes:")
    print(f"  {'Time':>8s}  {'Bright':>7s}  {'Delta':>7s}  {'Top':>7s}  {'Bottom':>7s}  {'Inv':>7s}")
    for t, bright, delta, top, bottom, inv in by_delta[:args.top]:
        flag = " FLIP?" if inv < -10 else ""
        print(f"  {t:8.2f}s  {bright:7.1f}  {delta:7.1f}  {top:7.1f}  {bottom:7.1f}  {inv:7.1f}{flag}")


def cmd_tilt(args):
    clip = load_clip(args.video)
    start = args.start if args.start is not None else 0
    end = args.end if args.end is not None else clip.duration
    res = args.resolution

    print(f"  Scanning {Path(args.video).name} for camera tilt ({start:.1f}s - {end:.1f}s)")
    results = analyze_tilt(clip, start, end, res)
    clip.close()

    by_ratio = sorted(results, key=lambda x: abs(x[1] - 1.0), reverse=True)
    print(f"\n  Top {args.top} tilt anomalies (ratio != 1.0 = camera rotated):")
    print(f"  {'Time':>8s}  {'Ratio':>7s}  {'Horiz':>7s}  {'Vert':>7s}")
    for t, ratio, h, v in by_ratio[:args.top]:
        print(f"  {t:8.2f}s  {ratio:7.2f}  {h:7.1f}  {v:7.1f}")


def cmd_extract(args):
    clip = load_clip(args.video)
    times = [float(t.strip()) for t in args.times.split(",")]
    out_dir = Path(args.output) if args.output else Path(".")

    print(f"  Extracting {len(times)} frames from {Path(args.video).name}")
    for t in times:
        frame = Image.fromarray(get_frame(clip, t))
        name = f"{Path(args.video).stem}_t{t:.2f}s.jpg"
        path = out_dir / name
        frame.save(path)
        print(f"    t={t:.2f}s -> {path}")
    clip.close()


def cmd_scan(args):
    """Combined scan: motion + brightness + tilt. Finds THE moment."""
    clip = load_clip(args.video)
    start = args.start if args.start is not None else 0
    end = args.end if args.end is not None else clip.duration
    res = args.resolution

    print(f"  Full scan of {Path(args.video).name} ({start:.1f}s - {end:.1f}s, {res}s)")
    print(f"  Duration: {clip.duration:.1f}s, Size: {clip.size}")

    # Collect all metrics
    prev = None
    prev_bright = None
    events = []

    for t in np.arange(start, end, res):
        frame = get_frame(clip, t)
        h_px = frame.shape[0]

        brightness = frame.mean()
        top = frame[:h_px//2].mean()
        bottom = frame[h_px//2:].mean()

        motion = 0
        if prev is not None:
            motion = np.abs(frame.astype(float) - prev.astype(float)).mean()

        bright_delta = abs(brightness - prev_bright) if prev_bright is not None else 0

        gray = np.mean(frame, axis=2)
        horiz_e = np.abs(np.diff(gray, axis=0)).mean()
        vert_e = np.abs(np.diff(gray, axis=1)).mean()
        tilt_ratio = vert_e / max(horiz_e, 0.001)

        # Combined score: weight motion highest, then brightness change, then tilt anomaly
        score = motion * 1.0 + bright_delta * 0.5 + abs(tilt_ratio - 1.0) * 10
        events.append({
            "t": t, "score": score, "motion": motion,
            "bright": brightness, "bright_delta": bright_delta,
            "top": top, "bottom": bottom,
            "tilt": tilt_ratio,
        })

        prev = frame.copy()
        prev_bright = brightness

    clip.close()

    # Sort by score
    events.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n  Top {args.top} events (combined score):")
    print(f"  {'Time':>8s}  {'Score':>7s}  {'Motion':>7s}  {'BrDelta':>7s}  {'Tilt':>6s}  {'Notes'}")
    print(f"  {'----':>8s}  {'-----':>7s}  {'------':>7s}  {'-------':>7s}  {'----':>6s}  {'-----'}")

    for ev in events[:args.top]:
        notes = []
        if ev["motion"] > 30:
            notes.append("BIG MOTION")
        if ev["bright_delta"] > 20:
            notes.append("FLASH")
        if ev["bottom"] - ev["top"] < -10:
            notes.append("FLIPPED")
        if abs(ev["tilt"] - 1.0) > 0.3:
            notes.append("TILTED")
        note_str = " | ".join(notes) if notes else ""
        print(f"  {ev['t']:8.2f}s  {ev['score']:7.1f}  {ev['motion']:7.1f}  {ev['bright_delta']:7.1f}  {ev['tilt']:6.2f}  {note_str}")

    best = events[0]
    print(f"\n  RECOMMENDED HOOK START: t={best['t'] - 0.25:.2f}s")
    print(f"  (0.25s before the biggest event at t={best['t']:.2f}s)")


def main():
    parser = argparse.ArgumentParser(description="CVS Video Scout — find key moments in tick videos")
    sub = parser.add_subparsers(dest="command")

    for cmd_name in ["motion", "bright", "tilt", "scan"]:
        p = sub.add_parser(cmd_name)
        p.add_argument("video", help="Video file path")
        p.add_argument("--start", type=float, default=None, help="Start time (seconds)")
        p.add_argument("--end", type=float, default=None, help="End time (seconds)")
        p.add_argument("--resolution", type=float, default=0.1, help="Scan interval (seconds)")
        p.add_argument("--top", type=int, default=15, help="Number of top results")

    p_extract = sub.add_parser("extract")
    p_extract.add_argument("video", help="Video file path")
    p_extract.add_argument("--times", required=True, help="Comma-separated timestamps")
    p_extract.add_argument("--output", default=None, help="Output directory")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    print("=" * 60)
    print(f"  CVS Video Scout — {args.command}")
    print("=" * 60)

    {"motion": cmd_motion, "bright": cmd_brightness, "tilt": cmd_tilt,
     "scan": cmd_scan, "extract": cmd_extract}[args.command](args)


if __name__ == "__main__":
    main()
