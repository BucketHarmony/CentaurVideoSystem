#!/usr/bin/env python3
"""
Deforum + cc_flora audio: 30 seconds of synced visuals and sound.

Generates the cc_flora ambient pad + chimes in numpy, then runs a Deforum
animation where zoom/rotation/translation keyframes are keyed to the music:
  - Chime hits → zoom pulses
  - Act transitions → rotation shifts
  - Harmonic envelopes → translation sway
  - Master envelope → denoise strength

Finally composites the audio onto the Deforum video.

Usage:
    python deforum_flora_synced.py
"""

import json
import math
import os
import subprocess
import time
import uuid
import urllib.request
import urllib.error
import wave
from pathlib import Path

import numpy as np
import scipy.signal

# ===================================================================
# Config
# ===================================================================

SERVER = "http://127.0.0.1:8188"
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output")
SR = 44100
DURATION = 2.0
FPS = 24
TOTAL_FRAMES = int(DURATION * FPS)  # 48

# Chime timestamps and frequencies (from cc_flora audio design)
CHIMES = [
    (0.1, 880), (3.0, 1108.73), (5.5, 880), (8.0, 1318.51),
    (10.5, 880), (13.5, 1108.73), (16.0, 1318.51), (19.0, 880),
    (22.0, 1108.73), (25.5, 880),
]

# Mood acts
ACTS = [
    {"name": "tension",   "start": 0.0,  "end": 10.0},
    {"name": "opening",   "start": 10.0, "end": 20.0},
    {"name": "arrival",   "start": 20.0, "end": 30.0},
]

# Prompts keyed to acts
PROMPTS = {
    0:   "'a dark crystalline cave, bioluminescent fungi growing on obsidian walls, faint blue light, mist, tension, ultra detailed, 8k'",
    180: "'an ancient stone archway opening into a sunlit meadow, golden light streaming through, wildflowers, hope rising, ultra detailed, 8k'",
    480: "'a vast celestial garden floating in space, luminous flowers, aurora borealis ribbons, peaceful arrival, crystalline structures, ultra detailed, 8k'",
}


# ===================================================================
# Audio Generation (pure numpy, cc_flora style)
# ===================================================================

def generate_synced_audio():
    """Generate the ambient pad + chimes. Returns path and event timing."""
    print("Generating cc_flora ambient pad + chimes...")
    t = np.linspace(0, DURATION, int(DURATION * SR), dtype=np.float64)

    # === Foundation pad (A minor) ===
    pad = np.sin(2 * np.pi * 110 * t) * 0.05          # A2
    pad += np.sin(2 * np.pi * 164.81 * t) * 0.035     # E3
    pad += np.sin(2 * np.pi * 220 * t) * 0.025        # A3

    # === Shimmering upper voices with LFO ===
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t)
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.18 * t + 1.0)
    pad += np.sin(2 * np.pi * 440 * t) * 0.010 * lfo1     # A4 shimmer
    pad += np.sin(2 * np.pi * 554.37 * t) * 0.007 * lfo2  # C#5 color
    pad += np.sin(2 * np.pi * 659.25 * t) * 0.005 * lfo1  # E5 air

    # === Act 1: Bb tension (0-10s) ===
    tension_env = np.clip(t / 2.0, 0, 1) * np.clip((10.0 - t) / 3.0, 0, 1)
    pad += np.sin(2 * np.pi * 233.08 * t) * 0.008 * tension_env

    # === Act 2-3: hopeful E4 rises (10-30s) ===
    hope_env = np.clip((t - 10) / 4.0, 0, 1) * np.clip((DURATION - t) / 3.0, 0, 1)
    pad += np.sin(2 * np.pi * 329.63 * t) * 0.016 * hope_env

    # === Act 3: bright B4 shimmer (22-28s) ===
    shimmer_env = np.clip((t - 22) / 3.0, 0, 1) * np.clip((28.0 - t) / 2.0, 0, 1)
    pad += np.sin(2 * np.pi * 493.88 * t) * 0.006 * shimmer_env

    # === Chimes ===
    for ct, cf in CHIMES:
        env_t = t - ct
        env = np.where(env_t >= 0, np.exp(-env_t * 2.0) * np.clip(env_t * 10, 0, 1), 0)
        pad += np.sin(2 * np.pi * cf * t) * 0.025 * env

    # === Impact thuds at act transitions ===
    rng = np.random.RandomState(42)
    for act_t in [10.0, 20.0]:
        thud_env = t - act_t
        thud_mask = (thud_env >= 0) & (thud_env < 0.3)
        noise_burst = rng.randn(len(t)) * 0.015
        noise_burst *= thud_mask * np.exp(-np.clip(thud_env, 0, 1) * 8)
        pad += noise_burst
        # Low sine thud
        low_env = np.where(thud_env >= 0, np.exp(-thud_env * 4) * np.clip(thud_env * 20, 0, 1), 0)
        pad += np.sin(2 * np.pi * 55 * t) * 0.03 * low_env * thud_mask

    # === Master envelope ===
    pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1) * np.clip((DURATION - t) / 2.5, 0, 1)

    # === Butter lowpass at 3kHz ===
    sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
    pad = scipy.signal.sosfilt(sos, pad)

    # === Normalize ===
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22

    # === Save ===
    audio_path = OUTPUT_DIR / "deforum_flora_pad.wav"
    with wave.open(str(audio_path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((pad * 32767).astype(np.int16).tobytes())

    print(f"  Saved: {audio_path}")
    return audio_path


# ===================================================================
# Build Deforum Keyframes from Audio Events
# ===================================================================

def time_to_frame(t_sec):
    return int(t_sec * FPS)

def build_keyframe_schedules():
    """Map audio events to Deforum parameter keyframes."""
    print("Building keyframe schedules from audio events...")

    # --- Zoom: base gentle zoom + pulses on chime hits ---
    zoom_keys = {}
    # Base zoom curve
    for f in range(TOTAL_FRAMES):
        t = f / FPS
        base = 1.003 + 0.002 * math.sin(2 * math.pi * t / 15)
        zoom_keys[f] = base

    # Chime pulses: spike zoom on each chime, decay over ~0.5s
    for ct, cf in CHIMES:
        hit_frame = time_to_frame(ct)
        intensity = 0.008 if cf > 1000 else 0.005  # higher freq = bigger pulse
        for df in range(int(0.5 * FPS)):
            f = hit_frame + df
            if f < TOTAL_FRAMES:
                decay = math.exp(-df / (0.15 * FPS))
                zoom_keys[f] = zoom_keys.get(f, 1.003) + intensity * decay

    zoom_str = ",".join(f"{f}:({v:.6f})" for f, v in sorted(zoom_keys.items()))

    # --- Translation X: sway that increases with hope ---
    tx_keys = {}
    for f in range(0, TOTAL_FRAMES, 6):
        t = f / FPS
        # Act 1: tight sway, Act 2: opens up, Act 3: wide and slow
        if t < 10:
            amp = 1.0
            freq = 1.5
        elif t < 20:
            amp = 2.5
            freq = 0.8
        else:
            amp = 3.5
            freq = 0.4
        tx_keys[f] = amp * math.sin(2 * math.pi * freq * t / 10)
    tx_str = ",".join(f"{f}:({v:.3f})" for f, v in sorted(tx_keys.items()))

    # --- Rotation Z: slow drift, jerks at act transitions ---
    rz_keys = {}
    for f in range(0, TOTAL_FRAMES, 6):
        t = f / FPS
        base_rot = 0.2 * math.sin(2 * math.pi * t / 20)
        # Jerk at act transitions
        for act_t in [10.0, 20.0]:
            dt = t - act_t
            if 0 <= dt < 1.0:
                base_rot += 0.8 * math.exp(-dt * 4) * (1 if act_t == 10 else -1)
        rz_keys[f] = base_rot
    rz_str = ",".join(f"{f}:({v:.4f})" for f, v in sorted(rz_keys.items()))

    # --- Angle: gentle tilt that follows the mood ---
    angle_keys = {}
    for f in range(0, TOTAL_FRAMES, 12):
        t = f / FPS
        if t < 10:
            angle_keys[f] = 0.15 * math.sin(2 * math.pi * t / 8)
        elif t < 20:
            angle_keys[f] = 0.1 * math.sin(2 * math.pi * t / 12)
        else:
            angle_keys[f] = 0.05 * math.sin(2 * math.pi * t / 16)
    angle_str = ",".join(f"{f}:({v:.4f})" for f, v in sorted(angle_keys.items()))

    # --- Prompts: keyed to acts ---
    prompt_str = "\n".join(f"{f}:{p}" for f, p in sorted(PROMPTS.items()))

    print(f"  Zoom: {len(zoom_keys)} keyframes")
    print(f"  Translation X: {len(tx_keys)} keyframes")
    print(f"  Rotation Z: {len(rz_keys)} keyframes")
    print(f"  Chime sync points: {len(CHIMES)}")

    return {
        "zoom": zoom_str,
        "translation_x": tx_str,
        "rotation_3d_z": rz_str,
        "angle": angle_str,
        "prompts": prompt_str,
    }


# ===================================================================
# Build & Run Deforum Workflow
# ===================================================================

def build_workflow(schedules):
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "dreamshaper_8.safetensors"}
        },
        "2": {
            "class_type": "DeforumPromptNode",
            "inputs": {"prompts": schedules["prompts"]}
        },
        "3": {
            "class_type": "DeforumBaseParamsNode",
            "inputs": {
                "deforum_data": ["2", 0],
                "width": 512, "height": 512,
                "seed_schedule": "0: (777)",
                "seed_behavior": "fixed",
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "prompt_weighting": True,
                "normalize_prompt_weights": True,
                "log_weighted_subprompts": False,
            }
        },
        "4": {
            "class_type": "DeforumAnimParamsNode",
            "inputs": {
                "deforum_data": ["3", 0],
                "animation_mode": "2D",
                "max_frames": TOTAL_FRAMES,
                "border": "wrap",
            }
        },
        "5": {
            "class_type": "DeforumTranslationParamsNode",
            "inputs": {
                "deforum_data": ["4", 0],
                "angle": schedules["angle"],
                "zoom": schedules["zoom"],
                "translation_x": schedules["translation_x"],
                "translation_y": "0:(0)",
                "translation_z": "0:(1.75)",
                "transform_center_x": "0:(0.5)",
                "transform_center_y": "0:(0.5)",
                "rotation_3d_x": "0:(0)",
                "rotation_3d_y": "0:(0)",
                "rotation_3d_z": schedules["rotation_3d_z"],
            }
        },
        "10": {
            "class_type": "DeforumGetCachedLatentNode",
            "inputs": {"cache_index": 0}
        },
        "11": {
            "class_type": "DeforumIteratorNode",
            "inputs": {
                "deforum_data": ["5", 0],
                "latent_type": "stable_diffusion",
                "latent": ["10", 0],
                "seed": 777777,
                "subseed": 0,
                "subseed_strength": 0.8,
                "slerp_strength": 0.1,
                "reset_counter": False,
                "reset_latent": False,
                "enable_autoqueue": False,
            }
        },
        "20": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "masterpiece, best quality, ultra detailed, cinematic lighting, volumetric fog",
                "clip": ["1", 1],
            }
        },
        "21": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly, blurry, low quality, deformed, watermark, text, boring, flat",
                "clip": ["1", 1],
            }
        },
        "30": {
            "class_type": "DeforumKSampler",
            "inputs": {
                "model": ["1", 0],
                "latent": ["11", 1],
                "positive": ["20", 0],
                "negative": ["21", 0],
                "deforum_frame_data": ["11", 0],
            }
        },
        "31": {
            "class_type": "DeforumCacheLatentNode",
            "inputs": {"latent": ["30", 0], "cache_index": 0}
        },
        "32": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["30", 0], "vae": ["1", 2]}
        },
        "40": {
            "class_type": "DeforumVideoSaveNode",
            "inputs": {
                "image": ["32", 0],
                "filename_prefix": "deforum_flora_synced",
                "fps": FPS,
                "codec": "libx264",
                "pixel_format": "yuv420p",
                "format": "mp4",
                "quality": 9,
                "dump_by": "max_frames",
                "dump_every": 0,
                "dump_now": False,
                "skip_save": False,
                "skip_return": True,
                "enable_preview": False,
                "restore": False,
                "clear_cache": False,
                "deforum_frame_data": ["11", 0],
            }
        },
    }


def queue_prompt(prompt_data, client_id):
    payload = json.dumps({"prompt": prompt_data, "client_id": client_id}).encode()
    req = urllib.request.Request(f"{SERVER}/prompt", data=payload,
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["prompt_id"]


def wait_for_completion(prompt_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{SERVER}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    return False
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_deforum(workflow):
    client_id = str(uuid.uuid4())
    print(f"\nRunning Deforum: {TOTAL_FRAMES} frames at {FPS}fps = {DURATION:.0f}s")
    start_time = time.time()

    for frame in range(TOTAL_FRAMES):
        t0 = time.time()
        prompt_id = queue_prompt(workflow, client_id)
        success = wait_for_completion(prompt_id)
        elapsed = time.time() - t0
        if frame % 24 == 0 or frame == TOTAL_FRAMES - 1:
            t_sec = frame / FPS
            print(f"  Frame {frame+1}/{TOTAL_FRAMES} "
                  f"(t={t_sec:.1f}s) [{elapsed:.1f}s]")
        if not success:
            print(f"  Frame {frame+1} FAILED — stopping")
            break

    total = time.time() - start_time
    print(f"\nDeforum done: {TOTAL_FRAMES} frames in {total:.0f}s "
          f"({total/TOTAL_FRAMES:.1f}s/frame)")


# ===================================================================
# Composite Audio onto Video
# ===================================================================

def composite_audio_video(audio_path):
    """Find the latest deforum_flora_synced mp4 and mux the audio in."""
    # Find latest video
    videos = sorted(OUTPUT_DIR.glob("deforum_flora_synced*.mp4"),
                    key=lambda p: p.stat().st_mtime)
    if not videos:
        print("ERROR: No deforum video found!")
        return None

    video_path = videos[-1]
    final_path = OUTPUT_DIR / "deforum_flora_FINAL.mp4"

    print(f"\nCompositing audio onto video...")
    print(f"  Video: {video_path}")
    print(f"  Audio: {audio_path}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        str(final_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Loudness normalize
    norm_path = OUTPUT_DIR / "deforum_flora_FINAL_norm.mp4"
    cmd2 = [
        "ffmpeg", "-y",
        "-i", str(final_path),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-c:v", "copy",
        str(norm_path),
    ]
    subprocess.run(cmd2, check=True, capture_output=True)

    print(f"  Final: {norm_path}")
    return norm_path


# ===================================================================
# Main
# ===================================================================

def main():
    print("=" * 60)
    print("  DEFORUM x cc_flora — Audio-Synced Animation")
    print("=" * 60)

    # Step 1: Generate audio
    audio_path = generate_synced_audio()

    # Step 2: Build keyframe schedules from audio events
    schedules = build_keyframe_schedules()

    # Step 3: Build and run Deforum workflow
    workflow = build_workflow(schedules)
    run_deforum(workflow)

    # Step 4: Composite audio onto video
    final = composite_audio_video(audio_path)

    print("\n" + "=" * 60)
    if final:
        print(f"  DONE: {final}")
        print(f"  Duration: {DURATION:.0f}s | Frames: {TOTAL_FRAMES} | FPS: {FPS}")
        print(f"  Chime sync points: {len(CHIMES)}")
        print(f"  Act transitions: {len(ACTS)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
