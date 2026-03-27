#!/usr/bin/env python
"""Render a Kombucha tick video with ethereal effects for Bluesky (1080x1080).

Usage:
    python render_bsky.py <tick_number>
    python render_bsky.py 188
    python render_bsky.py 188 --max-seconds 15 --fps 15 --crf 18
"""

import argparse
import importlib
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
import torch
from dotenv import load_dotenv

load_dotenv()

# Ensure pipeline modules are importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI_DIR = os.path.join(SCRIPT_DIR, "..", "..")
sys.path.insert(0, COMFYUI_DIR)

# Import from this package's nodes.py directly to avoid collision with ComfyUI's nodes.py
import importlib.util
_spec = importlib.util.spec_from_file_location("kombucha_nodes", os.path.join(SCRIPT_DIR, "nodes.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
CosyMotes = _mod.CosyMotes
MotionClip = _mod.MotionClip
VerticalFrameComposite = _mod.VerticalFrameComposite


def find_video(tick_num):
    """Locate the video file for a given tick number."""
    tick_str = f"tick_{tick_num:04d}"
    kombucha_dir = os.getenv("KOMBUCHA_DIR", "")
    search_dirs = [
        os.path.join(kombucha_dir, "video", "web"),
        os.path.join(kombucha_dir, "video"),
    ]
    for d in search_dirs:
        path = os.path.join(d, f"{tick_str}.mp4")
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No video found for tick {tick_num}")


def load_frames(video_path, target_fps=15):
    """Load video, dedup to target fps."""
    cap = cv2.VideoCapture(video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    skip = max(1, round(src_fps / target_fps))
    frames = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % skip == 0:
            frames.append(
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            )
        idx += 1
    cap.release()
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    print(f"Source: {int(total)} frames @ {src_fps:.0f}fps, loaded {len(frames)} @ {target_fps}fps")
    return frames


def render(tick_num, max_seconds=10, fps=15, crf=18):
    video_path = find_video(tick_num)
    print(f"Video: {video_path}")

    max_frames = int(fps * max_seconds)

    # Load
    frames = load_frames(video_path, target_fps=fps)
    images = torch.from_numpy(np.stack(frames)).float()

    # Strip stills
    print("Stripping still frames...")
    mc = MotionClip()
    clipped, count = mc.clip_motion(
        images=images, sensitivity=1.5, min_segment_frames=3,
        merge_gap_frames=8, pad_frames=4, max_output_frames=max_frames,
    )
    clipped = clipped[:max_frames]
    count = clipped.shape[0]
    print(f"Motion clipped: {count} frames = {count/fps:.1f}s")

    # Apply ethereal effects at native res
    print("Applying CosyMotes effects...")
    cm = CosyMotes()
    result = cm.apply(
        images=clipped,
        tiltshift_strength=1.0,
        focus_near=0.75,
        focus_far=0.15,
        bloom_strength=0.3,
        ray_strength=120.0,
        vignette_strength=0.35,
        haze_strength=0.12,
        shadow_lift=0.06,
        warmth=1.05,
        seed=42,
    )
    effected = result[0]

    # Scale to 1080 wide
    B, H, W, C = effected.shape
    scale = 1080 / W
    new_h = int(H * scale)
    frames_chw = effected.permute(0, 3, 1, 2)
    scaled = torch.nn.functional.interpolate(
        frames_chw, size=(new_h, 1080), mode="bilinear", align_corners=False
    )
    scaled_bhwc = scaled.permute(0, 2, 3, 1)

    # Square composite: 1080x1080
    print("Compositing 1080x1080 square...")
    vfc = VerticalFrameComposite()
    square, _, _ = vfc.composite(
        scaled_bhwc, canvas_width=1080, canvas_height=1080,
        blur_radius=25, blur_darken=0.4, video_y_offset=0,
    )

    # Write lossless intermediate
    tmp = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
    tmp.close()
    writer = cv2.VideoWriter(
        tmp.name, cv2.VideoWriter_fourcc(*"HFYU"), fps, (1080, 1080)
    )
    for i in range(square.shape[0]):
        frame_np = (square[i].numpy() * 255).clip(0, 255).astype(np.uint8)
        writer.write(cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR))
    writer.release()

    # Encode with ffmpeg
    out_dir = os.getenv("COMFYUI_OUTPUT_DIR", os.path.join(COMFYUI_DIR, "output"))
    out_path = os.path.join(out_dir, f"kombucha_bsky_tick{tick_num:04d}.mp4")
    print(f"Encoding H.264 CRF {crf}...")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", tmp.name,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "slow",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-profile:v", "high",
            "-level", "4.0",
            out_path,
        ],
        capture_output=True,
    )
    os.unlink(tmp.name)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Done! {out_path}")
    print(f"  {square.shape[0]} frames @ {fps}fps = {square.shape[0]/fps:.1f}s")
    print(f"  1080x1080, H.264 CRF {crf}, {size_mb:.1f}MB")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render Kombucha tick for Bluesky")
    parser.add_argument("tick", type=int, help="Tick number (e.g. 188)")
    parser.add_argument("--max-seconds", type=int, default=10)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    render(args.tick, max_seconds=args.max_seconds, fps=args.fps, crf=args.crf)
