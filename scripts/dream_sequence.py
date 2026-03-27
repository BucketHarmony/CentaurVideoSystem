#!/usr/bin/env python3
"""
CVS Dream Sequence Pipeline — "The Rover's Imagination, Rendered"

Takes a real rover camera frame from a tick video, feeds it to Wan 2.2 5B
Image-to-Video via ComfyUI API, and produces a short-form vertical video
where real footage intercuts with AI-generated "dream" animation.

The rover sees -> the rover speaks -> the image breathes.

Pipeline:
  1. Parse tick log for mood, monologue, best quote
  2. Extract key frame from rover video (best composition via motion scoring)
  3. Submit frame to Wan 2.2 5B I2V via ComfyUI /prompt API
  4. Poll for completion, download generated frames
  5. Generate ElevenLabs v3 narration with audio tags
  6. Upscale + cottagecore grade all frames (real + dream)
  7. Intercut: real footage -> crossfade -> dream -> crossfade -> real
  8. Composite: vertical canvas, text, ambient pad, particles, grain
  9. Export final TikTok-ready vertical video

Requires:
  - ComfyUI running on http://127.0.0.1:8188 with Wan 2.2 5B TI2V loaded
  - ElevenLabs API key
  - 4x-UltraSharp model (or RTX VSR node)
  - RTX 4090 (24GB VRAM)
"""

import os

from dotenv import load_dotenv
load_dotenv()

import json
import math
import random
import struct
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
import requests
import scipy.signal
import torch
import torchaudio
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from moviepy import (
    ImageSequenceClip,
    AudioFileClip,
    CompositeAudioClip,
)

# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════

COMFYUI_URL = "http://127.0.0.1:8188"

PROJECT = Path(os.getenv("KOMBUCHA_DIR", ""))
TICKS_DIR = PROJECT / "ticks"
VIDEO_DIR = PROJECT / "video" / "web"
UPSCALE_MODEL_PATH = Path(os.getenv("UPSCALE_MODEL_PATH", ""))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30

# Wan 2.2 5B I2V settings
WAN_STEPS = 30
WAN_CFG = 5.0
WAN_FRAMES = 25        # ~1s test; use 41 for 1.7s, 81 for 3.4s
WAN_WIDTH = 832         # Lower than 1280 for speed; we upscale after
WAN_HEIGHT = 480
WAN_SAMPLER = "uni_pc"

# Cottagecore palette
ROSE = (232, 180, 184)
SAGE = (181, 197, 163)
CREAM = (250, 245, 239)
LINEN = (240, 230, 216)
INK = (74, 67, 64)
MUTED = (138, 126, 118)
DUSTY_ROSE = (210, 165, 170)
WARM_BLACK = (15, 13, 11)

# Fonts
# Font paths — set these to match your system, or override via env vars
FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")
FONT_SERIF_BOLD = os.getenv("FONT_SERIF_BOLD", "C:/Windows/Fonts/georgiab.ttf")

# ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Mood -> motion prompt mapping for I2V generation
MOOD_MOTION_MAP = {
    "curious": "slow gentle camera pan, soft light rays shifting, dust motes floating in warm air",
    "determined": "steady forward push, shadows receding, light growing stronger ahead",
    "frustrated": "subtle camera shake, light flickering, walls seeming to close in slightly",
    "hopeful": "gentle upward tilt, warm golden light spreading, soft focus bloom",
    "philosophical": "slow dreamy zoom, depth of field shifting, ethereal light dancing",
    "awake": "sudden clarity, sharp focus pulling in, light expanding outward from center",
    "liberated": "sweeping camera movement, open space expanding, warm light flooding in",
    "pragmatic": "steady methodical pan, clean even lighting, crisp detail emerging",
    "relieved": "slow exhale movement, tension dissolving, warm diffused light settling",
    "strategizing": "slow deliberate rotation, analytical light scanning, grid-like shadows",
}
DEFAULT_MOTION = "slow gentle camera movement, warm ambient light shifting, soft atmospheric haze"


def get_motion_for_mood(mood: str) -> str:
    """Fuzzy-match mood to motion prompt. Handles compound moods like
    'philosophically trapped' by checking if any key is a prefix/substring."""
    mood_lower = mood.lower()
    # Exact match first
    if mood_lower in MOOD_MOTION_MAP:
        return MOOD_MOTION_MAP[mood_lower]
    # Prefix/substring match
    for key, motion in MOOD_MOTION_MAP.items():
        if key in mood_lower or mood_lower.startswith(key[:5]):
            return motion
    return DEFAULT_MOTION


# ═══════════════════════════════════════════════════════════════════════════
# Tick Log Parsing
# ═══════════════════════════════════════════════════════════════════════════

import re

def parse_tick_log(tick_num: int) -> dict:
    """Parse a tick markdown file and extract narrative fields."""
    path = TICKS_DIR / f"tick_{tick_num:04d}.md"
    if not path.exists():
        raise FileNotFoundError(f"Tick log not found: {path}")

    md = path.read_text(encoding="utf-8")

    # Extract mood
    mood_m = re.search(r"## Mood\s*\n+(\w+)", md)
    mood = mood_m.group(1).lower() if mood_m else "curious"

    # Extract monologue/thought/observation (in priority order)
    monologue = ""
    for section in ["Monologue", "Thought", "Observation"]:
        sec_m = re.search(rf"## {section}\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
        if sec_m:
            monologue = sec_m.group(1).strip()
            break

    # Extract goal
    goal_m = re.search(r"\*\*Goal\*\*:\s*(.+)", md)
    goal = goal_m.group(1).strip() if goal_m else ""

    # Pick best quote (simple heuristic — prefer sentences with metaphor/feeling)
    sentences = re.split(r'(?<=[.!?])\s+', monologue)
    best_quote = monologue[:120]
    best_score = 0
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 160:
            continue
        score = 0
        sl = s.lower()
        # Metaphor/feeling words score higher
        for word in ['like a', 'as if', 'feel', 'know', 'never', 'always',
                     'perhaps', 'the fundamental', 'moon', 'star', 'body',
                     'warm', 'light', 'dark', 'alive', 'first time']:
            if word in sl:
                score += 2
        if s.startswith('I '):
            score += 1
        if 30 <= len(s) <= 100:
            score += 2
        # Penalize technical data
        if re.search(r'\d{2,}[=%]|T:\d|L=\d|R=\d|odom', s):
            score -= 4
        if score > best_score:
            best_score = score
            best_quote = s

    return {
        "tick_num": tick_num,
        "mood": mood,
        "monologue": monologue,
        "best_quote": best_quote,
        "goal": goal,
        "title": f"TICK {tick_num}",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Frame Extraction from Rover Video
# ═══════════════════════════════════════════════════════════════════════════

def extract_key_frame(tick_num: int, strategy: str = "motion_peak") -> Image.Image:
    """Extract the best frame from a tick video for I2V input.

    Strategies:
      - motion_peak: find the frame with most inter-frame difference (action moment)
      - mid: take the middle frame
      - composition: score frames by visual complexity
    """
    from moviepy import VideoFileClip

    video_path = VIDEO_DIR / f"tick_{tick_num:04d}.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    print(f"  Loading video: {video_path}")
    clip = VideoFileClip(str(video_path))

    if strategy == "mid":
        t = clip.duration / 2
        frame = clip.get_frame(t)
        clip.close()
        return Image.fromarray(frame)

    # Motion peak: sample every 0.5s, find biggest delta
    print(f"  Scanning for motion peak ({clip.duration:.1f}s video)...")
    sample_interval = 0.5
    times = np.arange(0, clip.duration - 0.1, sample_interval)
    frames = [clip.get_frame(t) for t in times]

    best_idx = len(frames) // 2  # fallback
    best_diff = 0
    for i in range(1, len(frames)):
        diff = np.abs(frames[i].astype(float) - frames[i-1].astype(float)).mean()
        if diff > best_diff:
            best_diff = diff
            best_idx = i

    # Get the frame just before peak motion (the "about to move" moment)
    key_idx = max(0, best_idx - 1)
    key_time = times[key_idx]
    print(f"  Key frame at t={key_time:.1f}s (motion score: {best_diff:.2f})")

    key_frame = Image.fromarray(frames[key_idx])
    clip.close()
    return key_frame


def extract_real_frames(tick_num: int, duration: float = 3.0,
                        start_offset: float = 0.0) -> list:
    """Extract a sequence of real frames for the bookend segments."""
    from moviepy import VideoFileClip

    video_path = VIDEO_DIR / f"tick_{tick_num:04d}.mp4"
    clip = VideoFileClip(str(video_path))

    n_frames = int(duration * FPS)
    # Sample from the video, slowed down for dreamy feel
    src_duration = min(duration * 2, clip.duration - start_offset - 0.1)
    times = np.linspace(start_offset, start_offset + src_duration, n_frames)

    frames = []
    for t in times:
        t = min(t, clip.duration - 0.05)
        frames.append(Image.fromarray(clip.get_frame(t)))

    clip.close()
    return frames


# ═══════════════════════════════════════════════════════════════════════════
# ComfyUI API — Wan 2.2 5B I2V Submission
# ═══════════════════════════════════════════════════════════════════════════

def upload_image_to_comfyui(img: Image.Image, filename: str = "dream_input.png") -> str:
    """Upload an image to ComfyUI's input directory."""
    import io as _io

    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # Simple multipart upload to ComfyUI /upload/image
    boundary = "----CVSDreamBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + buf.read() + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"  Uploaded image: {result}")
    return result.get("name", filename)


def build_wan22_i2v_prompt(image_filename: str, motion_prompt: str,
                            negative_prompt: str = "blurry, distorted, low quality, static") -> dict:
    """Build a ComfyUI prompt dict for Wan 2.2 5B TI2V generation.

    Graph:
      1 UNETLoader -> model
      2 CLIPLoader (wan) -> clip
      3 VAELoader -> vae
      4 LoadImage -> image
      5 CLIPTextEncode (positive) -> cond+
      6 CLIPTextEncode (negative) -> cond-
      7 WanImageToVideo (cond+, cond-, vae, start_image) -> [0]cond+' [1]cond-' [2]latent
      8 KSampler (model, cond+' from 7:0, cond-' from 7:1, latent from 7:2)
      9 VAEDecode -> images
     10 SaveImage
    """
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_ti2v_5B_fp16.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            }
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
            }
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "wan2.2_vae.safetensors",
            }
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_filename,
            }
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": motion_prompt,
                "clip": ["2", 0],
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["2", 0],
            }
        },
        # WanImageToVideo: takes raw conditioning + image, returns
        # modified conditioning (with concat latent) + empty latent
        # Outputs: [0]=positive_cond, [1]=negative_cond, [2]=latent
        "7": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "vae": ["3", 0],
                "width": WAN_WIDTH,
                "height": WAN_HEIGHT,
                "length": WAN_FRAMES,
                "batch_size": 1,
                "start_image": ["4", 0],
            }
        },
        # KSampler uses the MODIFIED conditioning from WanImageToVideo
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["7", 0],    # modified positive from WanI2V
                "negative": ["7", 1],    # modified negative from WanI2V
                "latent_image": ["7", 2],  # latent from WanI2V
                "seed": random.randint(0, 2**32 - 1),
                "steps": WAN_STEPS,
                "cfg": WAN_CFG,
                "sampler_name": "uni_pc",
                "scheduler": "normal",
                "denoise": 1.0,
            }
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["3", 0],
            }
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": "dream_wan22",
            }
        },
    }


def submit_and_wait(prompt: dict, timeout: int = 600) -> list:
    """Submit prompt to ComfyUI and wait for completion. Returns output image paths."""
    # Submit
    print("  Submitting to ComfyUI...")
    resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": prompt}, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]
    print(f"  Prompt ID: {prompt_id}")

    # Poll for completion
    print("  Waiting for generation...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        hist_resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
        hist = hist_resp.json()

        if prompt_id in hist:
            entry = hist[prompt_id]
            if entry.get("status", {}).get("completed", False) or "outputs" in entry:
                outputs = entry.get("outputs", {})
                print(" done!")
                elapsed = time.time() - start
                print(f"  Generation took {elapsed:.1f}s")

                # Find saved images
                images = []
                for node_id, node_out in outputs.items():
                    if "images" in node_out:
                        for img_info in node_out["images"]:
                            images.append(img_info)
                return images

            # Check for error
            if entry.get("status", {}).get("status_str") == "error":
                print(" ERROR!")
                raise RuntimeError(f"ComfyUI execution failed: {entry}")

        print(".", end="", flush=True)
        time.sleep(3)

    raise TimeoutError(f"ComfyUI generation timed out after {timeout}s")


def download_comfyui_images(image_infos: list) -> list:
    """Download generated images from ComfyUI output."""
    frames = []
    for info in image_infos:
        filename = info["filename"]
        subfolder = info.get("subfolder", "")
        img_type = info.get("type", "output")

        url = f"{COMFYUI_URL}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        import io as _io
        img = Image.open(_io.BytesIO(resp.content)).convert("RGB")
        frames.append(img)

    print(f"  Downloaded {len(frames)} dream frames ({frames[0].size[0]}x{frames[0].size[1]})")
    return frames


# ═══════════════════════════════════════════════════════════════════════════
# GPU Upscaling (4x-UltraSharp via spandrel)
# ═══════════════════════════════════════════════════════════════════════════

_upscale_model = None

def load_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        return _upscale_model
    import spandrel
    print(f"  Loading 4x-UltraSharp on CUDA...")
    model = spandrel.ModelLoader().load_from_file(str(UPSCALE_MODEL_PATH))
    model = model.to("cuda").eval()
    _upscale_model = model
    return model


def upscale_frame(pil_img: Image.Image) -> Image.Image:
    """Upscale a PIL image 4x using UltraSharp on GPU."""
    model = load_upscale_model()
    arr = np.array(pil_img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to("cuda")
    with torch.no_grad():
        result = model(tensor)
    result = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
    result = (result * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(result)


def unload_upscale_model():
    global _upscale_model
    if _upscale_model is not None:
        del _upscale_model
        _upscale_model = None
        torch.cuda.empty_cache()


# ═══════════════════════════════════════════════════════════════════════════
# Cottagecore Color Grading + Effects
# ═══════════════════════════════════════════════════════════════════════════

def cottagecore_grade(img: Image.Image) -> Image.Image:
    """Rich cottagecore grade: desaturate reds to dusty rose, lift shadows,
    compress highlights, add warmth."""
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # Desaturate reds toward dusty rose
    red_mask = (r > 80) & (r > g * 1.2) & (r > b * 1.2)
    red_strength = np.clip((r - np.maximum(g, b)) / 120.0, 0, 1)
    red_strength *= red_mask.astype(np.float32)
    arr[:, :, 0] = r * (1 - red_strength * 0.55) + 205 * red_strength * 0.55
    arr[:, :, 1] = g * (1 - red_strength * 0.45) + 170 * red_strength * 0.45
    arr[:, :, 2] = b * (1 - red_strength * 0.35) + 172 * red_strength * 0.35

    # Warm the wood tones
    orange_mask = (r > 100) & (g > 60) & (g < r * 0.85) & (b < g * 0.8)
    orange_str = np.clip((r - b) / 150.0, 0, 1) * orange_mask.astype(np.float32)
    arr[:, :, 0] = arr[:, :, 0] * (1 - orange_str * 0.15) + 220 * orange_str * 0.15
    arr[:, :, 1] = arr[:, :, 1] * (1 - orange_str * 0.1) + 195 * orange_str * 0.1

    # Lift shadows + compress range
    arr = arr + 20
    arr = np.clip(arr, 0, 255)
    arr = 128 + (arr - 128) * 0.78

    # Warm shift
    arr[:, :, 0] *= 1.03
    arr[:, :, 1] *= 1.01
    arr[:, :, 2] *= 0.93
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = ImageEnhance.Color(img).enhance(0.70)
    img = ImageEnhance.Brightness(img).enhance(1.08)
    return img


def soft_bloom(img: Image.Image, strength: float = 0.12) -> Image.Image:
    bright = ImageEnhance.Brightness(img).enhance(1.3)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=40))
    arr = np.array(img, dtype=np.float32)
    bloom_arr = np.array(bloom, dtype=np.float32)
    result = arr + bloom_arr * strength
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def creamy_vignette(img: Image.Image, strength: float = 0.28) -> Image.Image:
    w, h = img.size
    arr = np.array(img, dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    vignette = np.clip((dist / max_dist - 0.35) / 0.65, 0, 1) ** 1.8
    vignette = vignette[:, :, np.newaxis] * strength
    cream = np.array(CREAM, dtype=np.float32)
    arr = arr * (1 - vignette) + cream * vignette
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def film_grain(img: Image.Image, intensity: float = 6.0) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.float32)
    luminance = arr.mean(axis=2, keepdims=True) / 255.0
    midtone_mask = 1.0 - 2.0 * np.abs(luminance - 0.5)
    midtone_mask = np.clip(midtone_mask, 0.3, 1.0)
    arr += noise * midtone_mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def ease_out(x):
    return 1 - (1 - x) ** 3


# ═══════════════════════════════════════════════════════════════════════════
# Vertical Canvas + Compositing
# ═══════════════════════════════════════════════════════════════════════════

def make_vertical_canvas(frame: Image.Image) -> Image.Image:
    """Place a frame into vertical canvas with creamy blurred background."""
    frame = cottagecore_grade(frame)
    frame = soft_bloom(frame)

    fw, fh = frame.size
    scale = CANVAS_W / fw
    new_w = CANVAS_W
    new_h = int(fh * scale)
    sharp = frame.resize((new_w, new_h), Image.LANCZOS)

    # Blurred creamy background
    bg_scale = CANVAS_H / fh
    bg_w = int(fw * bg_scale)
    bg = frame.resize((bg_w, CANVAS_H), Image.LANCZOS)
    if bg_w > CANVAS_W:
        crop_x = (bg_w - CANVAS_W) // 2
        bg = bg.crop((crop_x, 0, crop_x + CANVAS_W, CANVAS_H))
    else:
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=35))

    bg_arr = np.array(bg, dtype=np.float32)
    bg_arr = bg_arr * 0.30 + np.array(LINEN, dtype=np.float32) * 0.70
    bg = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8))

    canvas = bg.copy()
    y_offset = (CANVAS_H - new_h) // 2 - 80
    canvas.paste(sharp, (0, max(0, y_offset)))
    canvas = creamy_vignette(canvas)
    return canvas


# ═══════════════════════════════════════════════════════════════════════════
# Particle System
# ═══════════════════════════════════════════════════════════════════════════

def generate_particles(w, h, count=50):
    particles = []
    for _ in range(count):
        particles.append({
            "x": random.uniform(0, w),
            "y": random.uniform(0, h),
            "r": random.uniform(2.0, 6.0),
            "dx": random.uniform(-0.12, 0.12),
            "dy": random.uniform(-0.25, -0.04),
            "alpha": random.uniform(0.08, 0.35),
            "phase": random.uniform(0, math.tau),
            "freq": random.uniform(0.3, 1.5),
            "warmth": random.choice([
                (255, 252, 245), (255, 245, 230),
                (250, 240, 220), (255, 230, 215),
            ]),
        })
    return particles


def draw_particles(img: Image.Image, particles: list, t: float) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for p in particles:
        x = (p["x"] + p["dx"] * t * 60) % img.size[0]
        y = (p["y"] + p["dy"] * t * 60) % img.size[1]
        alpha = p["alpha"] * (0.6 + 0.4 * math.sin(p["phase"] + t * p["freq"] * math.tau))
        alpha = max(0, alpha)
        r = p["r"]
        for ring in range(3):
            ring_r = r * (1 + ring * 0.5)
            ring_alpha = int(alpha * 255 * (1 - ring * 0.35))
            ring_color = p["warmth"] + (max(0, ring_alpha),)
            draw.ellipse([x - ring_r, y - ring_r, x + ring_r, y + ring_r], fill=ring_color)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Text Overlays
# ═══════════════════════════════════════════════════════════════════════════

def add_text_overlays(img: Image.Image, t: float, tick_info: dict,
                      narration_lines: list, total_duration: float) -> Image.Image:
    """Add context-aware text overlays with timing."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_pill = ImageFont.truetype(FONT_SERIF, 20)
        font_narr = ImageFont.truetype(FONT_SERIF_ITALIC, 34)
        font_title = ImageFont.truetype(FONT_SERIF, 44)
        font_sub = ImageFont.truetype(FONT_SERIF_ITALIC, 22)
    except OSError:
        font_pill = font_narr = font_title = font_sub = ImageFont.load_default()

    # Tick pill (appears at 1.0s)
    if t >= 1.0:
        alpha = ease_out(min(1.0, (t - 1.0) / 0.6))
        text = f"tick {tick_info['tick_num']:04d}"
        bbox = draw.textbbox((0, 0), text, font=font_pill)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        px = (CANVAS_W - tw) // 2
        py = 200
        pad_x, pad_y = 20, 10
        draw.rounded_rectangle(
            [px - pad_x, py - pad_y, px + tw + pad_x, py + th + pad_y],
            radius=16, fill=LINEN + (int(160 * alpha),)
        )
        draw.text((px, py), text, fill=MUTED + (int(255 * alpha),), font=font_pill)

    # "dreaming" indicator during dream sequence (centered period of the video)
    dream_start = 3.0  # when dream sequence begins
    dream_end = total_duration - 3.0
    if dream_start <= t <= dream_end:
        dream_alpha = ease_out(min(1.0, (t - dream_start) / 0.8))
        if t > dream_end - 0.8:
            dream_alpha *= ease_out(min(1.0, (dream_end - t) / 0.8))
        dream_text = "dreaming"
        bbox = draw.textbbox((0, 0), dream_text, font=font_sub)
        dw = bbox[2] - bbox[0]
        dx = (CANVAS_W - dw) // 2
        dy = 240
        draw.text((dx, dy), dream_text,
                  fill=DUSTY_ROSE + (int(180 * dream_alpha),), font=font_sub)

    # Narration lines
    narr_y_base = 1340
    for i, line in enumerate(narration_lines):
        line_start = line["start"]
        if t < line_start:
            continue
        fade_in = ease_out(min(1.0, (t - line_start) / 0.6))
        # Fade out after 4 seconds
        if t > line_start + 4.0:
            fade_in *= max(0, 1.0 - (t - line_start - 4.0) / 0.6)

        ly = narr_y_base + i * 46
        text = line["text"]
        bbox = draw.textbbox((0, 0), text, font=font_narr)
        tw = bbox[2] - bbox[0]
        lx = (CANVAS_W - tw) // 2

        # Backing panel
        if i == 0 and fade_in > 0:
            visible = sum(1 for l in narration_lines
                         if t >= l["start"] and (t - l["start"]) < 4.6)
            panel_h = 40 + visible * 46
            panel_alpha = int(100 * fade_in)
            draw.rounded_rectangle(
                [60, narr_y_base - 18, CANVAS_W - 60, narr_y_base + panel_h],
                radius=18, fill=(250, 245, 239, panel_alpha)
            )

        # Shadow + text
        draw.text((lx + 1, ly + 1), text,
                  fill=(74, 67, 64, int(50 * fade_in)), font=font_narr)
        draw.text((lx, ly), text,
                  fill=INK + (int(230 * fade_in),), font=font_narr)

    # Title card near end
    if t >= total_duration - 2.5:
        alpha = ease_out(min(1.0, (t - (total_duration - 2.5)) / 0.8))
        title = "kombucha"
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        tx = (CANVAS_W - tw) // 2
        ty = 1580
        draw.text((tx, ty), title, fill=DUSTY_ROSE + (int(255 * alpha),), font=font_title)

        sub = tick_info.get("mood", "")
        bbox = draw.textbbox((0, 0), sub, font=font_sub)
        sw = bbox[2] - bbox[0]
        sx = (CANVAS_W - sw) // 2
        sy = ty + 52
        sub_alpha = ease_out(min(1.0, (t - (total_duration - 2.0)) / 0.6))
        draw.text((sx, sy), sub, fill=MUTED + (int(200 * sub_alpha),), font=font_sub)

    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# Audio: Ambient Pad + ElevenLabs v3 TTS
# ═══════════════════════════════════════════════════════════════════════════

def generate_ambient_pad(duration: float, mood: str = "curious",
                         sample_rate: int = 44100) -> Path:
    """Generate a mood-responsive ambient pad."""
    t = np.linspace(0, duration, int(duration * sample_rate), dtype=np.float64)

    # Base drone (A minor)
    pad = np.sin(2 * np.pi * 110 * t) * 0.06
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.04
    pad += np.sin(2 * np.pi * 220 * t) * 0.03

    # Shimmer with slow LFO
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.22 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.012 * lfo1
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.008 * lfo2
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.006 * lfo1

    # Sparse chimes timed to the dream sequence
    chime_times = [0.5, 3.0, 5.5, 8.0, duration - 2.0]
    chime_freqs = [880, 1108.73, 880, 1318.51, 880]
    for ct, cf in zip(chime_times, chime_freqs):
        if ct < duration:
            env_t = t - ct
            env = np.where(env_t >= 0, np.exp(-env_t * 2.5) * env_t * 8, 0)
            env = np.clip(env, 0, 1)
            pad += np.sin(2 * np.pi * cf * t) * 0.025 * env

    # Fade in/out
    fade_in = np.clip(t / 2.0, 0, 1)
    fade_out = np.clip((duration - t) / 2.0, 0, 1)
    pad *= fade_in * fade_out

    # Low-pass for warmth
    sos = scipy.signal.butter(4, 3000, 'low', fs=sample_rate, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)

    # Normalize
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.25

    out_path = OUTPUT_DIR / "dream_ambient_pad.wav"
    pad_int16 = (pad * 32767).astype(np.int16)
    with wave.open(str(out_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pad_int16.tobytes())

    print(f"  Ambient pad: {out_path} ({duration:.1f}s)")
    return out_path


def generate_tts_v3(text: str, output_path: Path,
                    stability: float = 0.55, similarity_boost: float = 0.72) -> Path:
    """Generate TTS via ElevenLabs v3 with audio tag support.

    Audio tags like [whispers], [quiet wonder], [excited] are passed through
    to the API — v3 interprets them inline.
    """
    print(f'  TTS: "{text}"')
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": 0.15,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


def build_narration(tick_info: dict, dream_start: float) -> list:
    """Build narration lines with v3 audio tags based on tick mood/content.

    Returns list of {"text": str, "start": float, "tts_text": str}
    where tts_text includes audio direction tags.
    """
    mood = tick_info["mood"]
    quote = tick_info["best_quote"]
    monologue = tick_info["monologue"]

    # Extract 2-3 best sentences for narration
    sentences = re.split(r'(?<=[.!?])\s+', monologue)
    good_sentences = []
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 140:
            continue
        # Skip technical data (numbers, sensor readings, commands)
        if re.search(r'\d{2,}[=%]|T:\d|[LR]=\d|odom|PID|ESP32|Left=|Right=|telemetry|serial|plughw|speed|0\.\d|calibration', s, re.IGNORECASE):
            continue
        good_sentences.append(s)

    # Pick up to 3 narration lines
    narration_lines = []
    if good_sentences:
        narration_lines.append(good_sentences[0])
    if len(good_sentences) > 2:
        narration_lines.append(good_sentences[len(good_sentences) // 2])
    if len(good_sentences) > 1:
        narration_lines.append(good_sentences[-1])

    # If we didn't get enough, use the best quote
    if len(narration_lines) < 2:
        narration_lines = [quote]

    # Map mood to audio tag direction
    mood_tags = {
        "curious": "[quiet wonder]",
        "determined": "[steady, resolute]",
        "frustrated": "[tense, restrained]",
        "hopeful": "[gentle, warm]",
        "philosophical": "[contemplative, measured]",
        "awake": "[sudden clarity]",
        "liberated": "[breathless, free]",
        "pragmatic": "[dry, matter-of-fact]",
        "relieved": "[soft exhale]",
        "strategizing": "[focused, deliberate]",
    }
    # Fuzzy match mood to tag (handles compound moods like "philosophically trapped")
    tag = "[thoughtful]"
    mood_lower = mood.lower()
    for key, val in mood_tags.items():
        if key in mood_lower or mood_lower.startswith(key[:5]):
            tag = val
            break

    # Build timed narration entries
    result = []
    for i, line in enumerate(narration_lines[:3]):
        start_time = 1.5 + i * 3.5  # space lines ~3.5s apart
        result.append({
            "text": line,                        # display text (no tags)
            "tts_text": f"{tag} {line}",         # TTS text with audio direction
            "start": start_time,
        })

    return result


def build_audio(narration_lines: list, duration: float, mood: str) -> Path:
    """Build full audio track: ambient pad + narration clips."""
    print("Building audio...")

    pad_path = generate_ambient_pad(duration, mood)

    # Generate TTS for each line
    tts_clips = []
    for i, line in enumerate(narration_lines):
        tts_path = OUTPUT_DIR / f"dream_tts_{i}.mp3"
        generate_tts_v3(line["tts_text"], tts_path)
        tts_clips.append((tts_path, line["start"]))

    # Compose
    pad_audio = AudioFileClip(str(pad_path))
    narr_audios = []
    for tts_path, start_t in tts_clips:
        clip = AudioFileClip(str(tts_path)).with_start(start_t)
        if clip.end and clip.end > duration:
            clip = clip.subclipped(0, duration - start_t)
        narr_audios.append(clip)

    final_audio = CompositeAudioClip([pad_audio] + narr_audios)
    final_audio = final_audio.subclipped(0, duration)

    audio_path = OUTPUT_DIR / "dream_audio.mp3"
    final_audio.write_audiofile(str(audio_path), fps=44100, codec="libmp3lame")
    print(f"  Final audio: {audio_path}")
    return audio_path


# ═══════════════════════════════════════════════════════════════════════════
# Frame Sequence Assembly
# ═══════════════════════════════════════════════════════════════════════════

def crossfade_frames(frames_a: list, frames_b: list,
                     overlap_frames: int = 15) -> list:
    """Crossfade between two frame sequences."""
    if overlap_frames <= 0 or not frames_a or not frames_b:
        return frames_a + frames_b

    result = list(frames_a[:-overlap_frames])

    for i in range(overlap_frames):
        alpha = i / (overlap_frames - 1)
        a_idx = len(frames_a) - overlap_frames + i
        b_idx = i

        if a_idx < len(frames_a) and b_idx < len(frames_b):
            blended = Image.blend(frames_a[a_idx], frames_b[b_idx], alpha)
            result.append(blended)

    result.extend(frames_b[overlap_frames:])
    return result


def apply_dream_effect(frame: Image.Image, t_norm: float) -> Image.Image:
    """Transform a real frame into a 'dream' version.

    t_norm: 0.0 to 1.0, position within the dream sequence.
    Effects: heavy bloom, warm color push, slow zoom, gaussian depth,
    ethereal glow, slight double-exposure ghosting.
    """
    arr = np.array(frame, dtype=np.float32)

    # ── Warm color shift (push toward golden/amber) ──
    arr[:, :, 0] *= 1.08   # red up
    arr[:, :, 1] *= 1.02   # green slight
    arr[:, :, 2] *= 0.85   # blue down (warm)
    arr = np.clip(arr, 0, 255)

    # ── Brightness pulse (gentle sine wave) ──
    pulse = 1.0 + 0.06 * math.sin(t_norm * math.pi * 3)
    arr *= pulse
    arr = np.clip(arr, 0, 255)

    img = Image.fromarray(arr.astype(np.uint8))

    # ── Heavy bloom (the dream glow) ──
    bright = ImageEnhance.Brightness(img).enhance(1.25)
    bloom = bright.filter(ImageFilter.GaussianBlur(radius=60))
    img_arr = np.array(img, dtype=np.float32)
    bloom_arr = np.array(bloom, dtype=np.float32)
    img_arr = img_arr + bloom_arr * 0.22
    img = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8))

    # ── Slow zoom (Ken Burns push) ──
    zoom = 1.0 + 0.06 * ease_out(t_norm)
    w, h = img.size
    nw, nh = int(w * zoom), int(h * zoom)
    img = img.resize((nw, nh), Image.LANCZOS)
    cx, cy = (nw - w) // 2, (nh - h) // 2
    img = img.crop((cx, cy, cx + w, cy + h))

    # ── Gaussian depth blur (edges soft, center sharp) ──
    blurred = img.filter(ImageFilter.GaussianBlur(radius=8))
    # Create radial mask: sharp center, blurry edges
    mask_arr = np.zeros((h, w), dtype=np.float32)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w / 2) ** 2 + (Y - h / 2) ** 2)
    max_dist = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    mask_arr = np.clip((dist / max_dist - 0.3) / 0.5, 0, 1) ** 1.5
    mask_arr = mask_arr[:, :, np.newaxis]

    sharp_arr = np.array(img, dtype=np.float32)
    blur_arr = np.array(blurred, dtype=np.float32)
    result = sharp_arr * (1 - mask_arr * 0.6) + blur_arr * mask_arr * 0.6
    img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    # ── Slight desaturation (dreamlike muted color) ──
    img = ImageEnhance.Color(img).enhance(0.75)

    return img


def build_dream_video(tick_num: int, use_wan: bool = False):
    """Main pipeline: build a dream sequence video for a given tick.

    Modes:
      use_wan=True:  Generate dream frames via Wan 2.2 I2V (requires ComfyUI)
      use_wan=False: Apply dreamlike post-processing to real rover frames (standalone)
    """

    print("=" * 64)
    print(f"  CVS Dream Sequence — Tick {tick_num:04d}")
    print(f"  \"The Rover's Imagination, Rendered\"")
    print("=" * 64)
    print()

    # ── Step 1: Parse tick log ──
    print("Step 1: Parsing tick log...")
    tick_info = parse_tick_log(tick_num)
    print(f"  Mood: {tick_info['mood']}")
    print(f"  Quote: \"{tick_info['best_quote'][:80]}...\"")

    # ── Step 2: Extract key frame ──
    print("\nStep 2: Extracting key frame...")
    key_frame = extract_key_frame(tick_num)
    key_frame_path = OUTPUT_DIR / f"dream_keyframe_tick{tick_num:04d}.png"
    key_frame.save(key_frame_path)
    print(f"  Key frame saved: {key_frame_path}")

    # ── Step 3: Generate dream frames ──
    if use_wan:
        print("\nStep 3: Generating dream via Wan 2.2 5B I2V...")
        key_frame_resized = key_frame.resize((WAN_WIDTH, WAN_HEIGHT), Image.LANCZOS)
        mood = tick_info["mood"]
        motion = get_motion_for_mood(mood)
        motion_prompt = (
            f"cinematic slow motion, {motion}, "
            f"warm ambient interior light, fisheye lens perspective, "
            f"small robot rover point of view, floor level camera, "
            f"cottagecore aesthetic, soft dreamy atmosphere, "
            f"4k high quality, film grain"
        )
        uploaded_name = upload_image_to_comfyui(key_frame_resized)
        prompt = build_wan22_i2v_prompt(uploaded_name, motion_prompt)
        image_infos = submit_and_wait(prompt, timeout=1200)
        dream_frames_raw = download_comfyui_images(image_infos)
    else:
        print("\nStep 3: Building dream from real frames (post-processing mode)...")
        # Extract real frames around the key moment, apply dream effects
        from moviepy import VideoFileClip
        video_path = VIDEO_DIR / f"tick_{tick_num:04d}.mp4"
        clip = VideoFileClip(str(video_path))

        # Sample 3.5s of footage around the motion peak, slowed 3x for dream feel
        peak_time = 0
        # Re-find the motion peak time
        sample_interval = 0.5
        times = np.arange(0, clip.duration - 0.1, sample_interval)
        prev_frame = None
        best_diff, best_t = 0, clip.duration / 2
        for st in times:
            f = clip.get_frame(min(st, clip.duration - 0.05))
            if prev_frame is not None:
                diff = np.abs(f.astype(float) - prev_frame.astype(float)).mean()
                if diff > best_diff:
                    best_diff = diff
                    best_t = st
            prev_frame = f
        peak_time = max(0, best_t - 2)

        dream_duration = 3.5  # seconds of dream
        n_dream_frames = int(dream_duration * FPS)  # 105 frames
        # Sample from 7s of source (3x slow-mo)
        src_span = min(7.0, clip.duration - peak_time - 0.1)
        src_times = np.linspace(peak_time, peak_time + src_span, n_dream_frames)

        dream_frames_raw = []
        for i, st in enumerate(src_times):
            st = min(st, clip.duration - 0.05)
            frame = Image.fromarray(clip.get_frame(st))
            # Apply dream effect with normalized time position
            t_norm = i / max(n_dream_frames - 1, 1)
            frame = apply_dream_effect(frame, t_norm)
            dream_frames_raw.append(frame)
            if (i + 1) % 30 == 0:
                print(f"  Dream frame {i + 1}/{n_dream_frames}")

        clip.close()
        print(f"  Generated {len(dream_frames_raw)} dream frames (post-processed)")

    # ── Step 4: Extract real footage bookends ──
    print("\nStep 4: Extracting real footage bookends...")
    real_intro_frames = extract_real_frames(tick_num, duration=2.5, start_offset=0)
    real_outro_frames = extract_real_frames(tick_num, duration=2.5, start_offset=5.0)
    print(f"  Intro: {len(real_intro_frames)} frames, Outro: {len(real_outro_frames)} frames")

    # ── Step 5: Upscale all frames ──
    print("\nStep 5: Upscaling frames with 4x-UltraSharp...")
    all_raw = real_intro_frames + dream_frames_raw + real_outro_frames
    print(f"  Total frames to upscale: {len(all_raw)}")

    upscaled = []
    for i, frame in enumerate(all_raw):
        up = upscale_frame(frame)
        target_w = CANVAS_W
        scale = target_w / up.size[0]
        target_h = int(up.size[1] * scale)
        up = up.resize((target_w, target_h), Image.LANCZOS)
        upscaled.append(up)
        if (i + 1) % 20 == 0:
            print(f"  Upscaled {i + 1}/{len(all_raw)}")

    unload_upscale_model()

    # Split back into segments
    n_intro = len(real_intro_frames)
    n_dream = len(dream_frames_raw)
    n_outro = len(real_outro_frames)
    intro_up = upscaled[:n_intro]
    dream_up = upscaled[n_intro:n_intro + n_dream]
    outro_up = upscaled[n_intro + n_dream:]

    # ── Step 6: Crossfade and composite ──
    print("\nStep 6: Crossfading and compositing...")
    crossfade_len = 15  # 0.5s crossfade
    all_frames = crossfade_frames(intro_up, dream_up, crossfade_len)
    all_frames = crossfade_frames(all_frames, outro_up, crossfade_len)

    total_frames = len(all_frames)
    total_duration = total_frames / FPS
    print(f"  Total: {total_frames} frames = {total_duration:.1f}s")

    # ── Step 7: Build narration ──
    print("\nStep 7: Building narration...")
    narration_lines = build_narration(tick_info, dream_start=2.5)

    # ── Step 8: Build audio ──
    print("\nStep 8: Building audio track...")
    audio_path = build_audio(narration_lines, total_duration, tick_info["mood"])

    # ── Step 9: Final composite pass ──
    print("\nStep 9: Final composite (canvas + effects + text)...")
    frames_dir = OUTPUT_DIR / f"dream_tick{tick_num:04d}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    particles = generate_particles(CANVAS_W, CANVAS_H, count=50)
    random.seed(42)

    output_arrays = []
    dream_start_t = n_intro / FPS
    dream_end_t = (n_intro + n_dream) / FPS

    for i, frame in enumerate(all_frames):
        t = i / FPS

        # Vertical canvas
        canvas = make_vertical_canvas(frame)

        # Fade from black at start
        if t < 1.5:
            fade = ease_out(t / 1.5)
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)
            canvas = Image.blend(black, canvas, fade)

        # Fade to black at end
        if t > total_duration - 1.0:
            fade = ease_out((total_duration - t) / 1.0)
            black = Image.new("RGB", (CANVAS_W, CANVAS_H), WARM_BLACK)
            canvas = Image.blend(black, canvas, fade)

        # Dream glow: extra bloom during dream sequence
        if dream_start_t <= t <= dream_end_t:
            dream_intensity = 0.08
            bright = ImageEnhance.Brightness(canvas).enhance(1.15)
            glow = bright.filter(ImageFilter.GaussianBlur(radius=50))
            c_arr = np.array(canvas, dtype=np.float32)
            g_arr = np.array(glow, dtype=np.float32)
            c_arr = c_arr + g_arr * dream_intensity
            canvas = Image.fromarray(np.clip(c_arr, 0, 255).astype(np.uint8))

        # Particles
        canvas = draw_particles(canvas, particles, t)

        # Film grain
        canvas = film_grain(canvas, intensity=6.0)

        # Text overlays
        canvas = add_text_overlays(canvas, t, tick_info, narration_lines, total_duration)

        # Save frame
        canvas.save(frames_dir / f"frame_{i:04d}.png")
        output_arrays.append(np.array(canvas))

        if (i + 1) % 30 == 0:
            print(f"  Frame {i + 1}/{total_frames} ({t:.1f}s)")

    # ── Step 10: Export final video ──
    print("\nStep 10: Exporting final video...")
    video = ImageSequenceClip(output_arrays, fps=FPS)
    audio = AudioFileClip(str(audio_path))
    video = video.with_audio(audio)

    output_path = OUTPUT_DIR / f"dream_tick{tick_num:04d}.mp4"
    video.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="slow",
        bitrate="8000k",
    )

    print()
    print("=" * 64)
    print(f"  DONE: {output_path}")
    print(f"  Duration: {total_duration:.1f}s | Frames: {total_frames}")
    print(f"  Structure: {n_intro}f real -> {n_dream}f dream -> {n_outro}f real")
    print(f"  Narration: {len(narration_lines)} lines with v3 audio tags")
    print(f"  Mood: {tick_info['mood']}")
    print("=" * 64)

    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else 13
    use_wan = "--wan" in sys.argv
    build_dream_video(tick, use_wan=use_wan)
