#!/usr/bin/env python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""Full Kombucha video production pipeline for Bluesky.

Content curation -> tick log parsing -> video staging -> motion clip ->
ethereal filters -> 4x upscale -> square composite -> ElevenLabs TTS ->
text overlay -> audio sync -> H.264 encode.

Usage:
    python produce_bsky.py 188
    python produce_bsky.py 188 --dry-run          # preview without TTS/encode
    python produce_bsky.py 188 --max-seconds 15
    python produce_bsky.py 188 --skip-tts          # no voiceover
    python produce_bsky.py 188 --no-upscale        # skip 4x (faster dev)
    python produce_bsky.py 188 --crf 22            # smaller file
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np
import torch
import torchaudio
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image

# ── paths ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI_DIR = os.path.join(SCRIPT_DIR, "..", "..")
KOMBUCHA_DIR = os.getenv("KOMBUCHA_DIR", "")
OUTPUT_DIR = os.path.join(COMFYUI_DIR, "output")
UPSCALE_MODEL = os.path.join(COMFYUI_DIR, "models", "upscale_models", "RealESRGAN_x4plus.pth")

# Series bible voice
VOICE_ID = os.getenv("ELEVENLABS_VOICE", "")

# ── load pipeline nodes ───────────────────────────────────────────────────

sys.path.insert(0, COMFYUI_DIR)
_spec = importlib.util.spec_from_file_location("kombucha_nodes", os.path.join(SCRIPT_DIR, "nodes.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ParseTickLog = _mod.ParseTickLog
ElevenLabsTTS = _mod.ElevenLabsTTS
MotionClip = _mod.MotionClip
CosyMotes = _mod.CosyMotes
VerticalFrameComposite = _mod.VerticalFrameComposite
TextOverlay = _mod.TextOverlay
PadToAudio = _mod.PadToAudio


# ── helpers ───────────────────────────────────────────────────────────────

def load_env():
    """Load .env and return ElevenLabs key."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    key = os.getenv("ELEVENLABS_API_KEY", "")
    return key


def find_tick_log(tick_num):
    path = os.path.join(KOMBUCHA_DIR, "ticks", f"tick_{tick_num:04d}.md")
    if os.path.exists(path):
        return path
    raise FileNotFoundError(f"No tick log: {path}")


def find_video(tick_num):
    for d in [os.path.join(KOMBUCHA_DIR, "video", "web"), os.path.join(KOMBUCHA_DIR, "video")]:
        path = os.path.join(d, f"tick_{tick_num:04d}.mp4")
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No video for tick {tick_num}")


def load_frames(video_path, target_fps=15):
    cap = cv2.VideoCapture(video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    skip = max(1, round(src_fps / target_fps))
    frames = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % skip == 0:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
        idx += 1
    cap.release()
    print(f"  Source: {total} frames @ {src_fps:.0f}fps -> {len(frames)} frames @ {target_fps}fps")
    return frames


def upscale_4x(images_tensor):
    """4x upscale with RealESRGAN."""
    from spandrel import ModelLoader
    print("  Loading RealESRGAN_x4plus...")
    model = ModelLoader().load_from_file(UPSCALE_MODEL)
    model = model.to(torch.device("cuda")).eval()

    B, H, W, C = images_tensor.shape
    results = []
    print(f"  Upscaling {B} frames {W}x{H} -> {W*4}x{H*4}...")
    with torch.no_grad():
        for i in range(B):
            frame = images_tensor[i:i+1].permute(0, 3, 1, 2).cuda()
            out = model(frame)
            results.append(out.squeeze(0).permute(1, 2, 0).cpu())
            if (i + 1) % 30 == 0:
                print(f"    {i+1}/{B} frames upscaled")

    # Free GPU memory
    del model
    torch.cuda.empty_cache()

    return torch.stack(results)


def encode_h264(raw_path, out_path, fps, crf=18):
    """Encode with ffmpeg H.264 for Bluesky."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", raw_path,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-profile:v", "high",
        "-level", "4.0",
        out_path,
    ], capture_output=True)


def encode_with_audio(video_path, audio_path, out_path, crf=18):
    """Mux video + audio with ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-profile:v", "high",
        "-level", "4.0",
        out_path,
    ], capture_output=True)


# ── main pipeline ─────────────────────────────────────────────────────────

def produce(tick_num, max_seconds=10, fps=15, crf=18,
            dry_run=False, skip_tts=False, no_upscale=False):

    t_start = time.time()
    print(f"=== Kombucha Bluesky Pipeline: Tick {tick_num} ===\n")

    # ── 1. CONTENT CURATION -- parse tick log ──────────────────────────────
    print("[1] Parsing tick log...")
    log_path = find_tick_log(tick_num)
    parser = ParseTickLog()
    title, mood, monologue, best_quote, tick_number, goal, intent = parser.parse(log_path)

    print(f"  Title:    {title}")
    print(f"  Mood:     {mood}")
    print(f"  Goal:     {goal}")
    print(f"  Quote:    {best_quote[:80]}{'...' if len(best_quote) > 80 else ''}")
    print(f"  TTS text: {len(monologue)} chars")
    print()

    if not monologue or monologue == "...":
        print("  [!] No monologue found -- skipping TTS")
        skip_tts = True

    # ── 2. STAGING -- load video, strip stills ─────────────────────────────
    print("[2] Loading video...")
    video_path = find_video(tick_num)
    frames = load_frames(video_path, target_fps=fps)

    if not frames:
        print("  [X] No frames loaded!")
        return None

    max_frames = int(fps * max_seconds)
    images = torch.from_numpy(np.stack(frames)).float()

    print("  Stripping still frames...")
    mc = MotionClip()
    clipped, count = mc.clip_motion(
        images=images, sensitivity=1.5, min_segment_frames=3,
        merge_gap_frames=8, pad_frames=4, max_output_frames=max_frames,
    )
    clipped = clipped[:max_frames]
    count = clipped.shape[0]
    print(f"  Staged: {count} frames = {count/fps:.1f}s")
    print()

    if dry_run:
        print("── DRY RUN -- stopping here ──")
        print(f"  Would process {count} frames with effects + {'TTS' if not skip_tts else 'no TTS'}")
        return None

    # ── 3. ETHEREAL FILTERS -- at native res ───────────────────────────────
    print("[3] Applying ethereal effects...")
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
    print()

    # ── 4. 4x UPSCALE ────────────────────────────────────────────────────
    if not no_upscale:
        print("[4] Upscaling 4x...")
        effected = upscale_4x(effected)
        print()
    else:
        print("[4] Skipping upscale (--no-upscale)")
        print()

    # ── 5. SQUARE COMPOSITE -- 1080x1080 ──────────────────────────────────
    print("[5] Compositing 1080x1080 square...")
    B, H, W, C = effected.shape
    scale = 1080 / W
    new_h = int(H * scale)
    frames_chw = effected.permute(0, 3, 1, 2)
    scaled = torch.nn.functional.interpolate(
        frames_chw, size=(new_h, 1080), mode="bilinear", align_corners=False,
    )
    scaled_bhwc = scaled.permute(0, 2, 3, 1)

    vfc = VerticalFrameComposite()
    square, top_zone, bot_zone = vfc.composite(
        scaled_bhwc, canvas_width=1080, canvas_height=1080,
        blur_radius=25, blur_darken=0.4, video_y_offset=0,
    )
    print(f"  Output: {square.shape[2]}x{square.shape[1]}, zones: top={top_zone} bottom={bot_zone}")
    print()

    # ── 6. TEXT OVERLAY ───────────────────────────────────────────────────
    print("[6] Burning text overlay...")
    overlay = TextOverlay()
    with_text = overlay.overlay(
        images=square,
        title_text=title,
        subtitle_text=mood,
        body_text=best_quote,
        title_y=50,
        body_y=880,
        font_size_title=72,
        font_size_subtitle=30,
        font_size_body=28,
        title_color="#ffffff",
        subtitle_color="#d4922a",
        body_color="#e8dcc8",
        accent_color="#e8a830",
        max_body_chars_per_line=36,
        max_body_lines=4,
    )
    composited = with_text[0]
    print()

    # ── 7. ELEVENLABS TTS ─────────────────────────────────────────────────
    # ── 7. SCORED SOUNDTRACK (pad + chimes + binaural + TTS) ─────────────
    soundtrack_path = None
    audio_duration = None
    if not skip_tts:
        print("[7] Building scored soundtrack...")
        api_key = load_env()
        if not api_key:
            print("  [!] No ELEVENLABS_API_KEY in .env -- skipping audio")
            skip_tts = True
        else:
            from audio_engine import build_soundtrack
            video_dur = composited.shape[0] / fps
            soundtrack_path, audio_duration = build_soundtrack(
                monologue=monologue,
                duration=video_dur,
                mood=mood,
                output_dir=OUTPUT_DIR,
            )
            print()
    else:
        print("[7] Skipping audio")
        print()

    # ── 8. PAD VIDEO TO AUDIO ─────────────────────────────────────────────
    if soundtrack_path is not None and audio_duration is not None:
        print("[8] Syncing video to soundtrack duration...")
        import torchaudio as _ta
        waveform, sample_rate = _ta.load(soundtrack_path)
        if waveform.dim() == 2:
            waveform = waveform.unsqueeze(0)
        audio_dict = {"waveform": waveform, "sample_rate": sample_rate}

        padder = PadToAudio()
        composited, audio_dict = padder.pad(
            images=composited,
            audio=audio_dict,
            frame_rate=fps,
            buffer_seconds=2.0,
            min_speed=0.5,
            pad_start_ratio=0.3,
        )
        print(f"  Final: {composited.shape[0]} frames = {composited.shape[0]/fps:.1f}s")
        print()
    else:
        audio_dict = None
        print("[8] No audio -- skipping pad")
        print()

    # ── 9. ENCODE ─────────────────────────────────────────────────────────
    print("[9] Encoding H.264...")

    # Write lossless intermediate
    tmp_vid = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
    tmp_vid.close()
    writer = cv2.VideoWriter(
        tmp_vid.name, cv2.VideoWriter_fourcc(*"HFYU"), fps, (1080, 1080),
    )
    for i in range(composited.shape[0]):
        frame_np = (composited[i].numpy() * 255).clip(0, 255).astype(np.uint8)
        writer.write(cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR))
    writer.release()

    out_path = os.path.join(OUTPUT_DIR, f"kombucha_bsky_tick{tick_num:04d}.mp4")

    if audio_dict is not None:
        # Save audio to temp WAV
        tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_audio.close()
        torchaudio.save(tmp_audio.name, audio_dict["waveform"].squeeze(0), audio_dict["sample_rate"])

        encode_with_audio(tmp_vid.name, tmp_audio.name, out_path, crf=crf)
        os.unlink(tmp_audio.name)
    else:
        encode_h264(tmp_vid.name, out_path, fps, crf=crf)

    os.unlink(tmp_vid.name)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    elapsed = time.time() - t_start

    # ── 10. SUMMARY ───────────────────────────────────────────────────────
    print()
    print(f"=== DONE ===")
    print(f"  Output:   {out_path}")
    print(f"  Format:   1080x1080 H.264 CRF {crf}")
    print(f"  Duration: {composited.shape[0]/fps:.1f}s @ {fps}fps")
    print(f"  Size:     {size_mb:.1f}MB")
    print(f"  Audio:    {'yes' if audio_dict else 'no'}")
    print(f"  Time:     {elapsed:.0f}s")
    print()
    print(f"  Title:    {title}")
    print(f"  Mood:     {mood}")
    print(f"  Quote:    {best_quote[:60]}...")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Kombucha -> Bluesky pipeline")
    parser.add_argument("tick", type=int, help="Tick number (e.g. 188)")
    parser.add_argument("--max-seconds", type=int, default=10)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--dry-run", action="store_true", help="Parse + stage only, no render")
    parser.add_argument("--skip-tts", action="store_true", help="Skip ElevenLabs voiceover")
    parser.add_argument("--no-upscale", action="store_true", help="Skip 4x upscale (faster)")
    args = parser.parse_args()

    produce(
        args.tick,
        max_seconds=args.max_seconds,
        fps=args.fps,
        crf=args.crf,
        dry_run=args.dry_run,
        skip_tts=args.skip_tts,
        no_upscale=args.no_upscale,
    )
