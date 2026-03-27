#!/usr/bin/env python3
"""
LTX-Video smoke test -- 1-second candle flame.

Downloads required models (if missing), builds a minimal text-to-video
workflow, submits it to the running ComfyUI server, and waits for output.

Uses split model loading (UNETLoader + VAELoader + LTXAVTextEncoderLoader)
to fit within 24GB VRAM on RTX 4090.

Usage:
    python ltx_smoke_test.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SERVER = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFY = Path(os.getenv("COMFYUI_DIR", str(Path(__file__).resolve().parents[1] / "ComfyUI")))

MODELS = [
    {
        "url": "https://huggingface.co/Kijai/LTXV2_comfy/resolve/main/diffusion_models/ltx-2-19b-dev_fp4_transformer_only.safetensors",
        "dest": COMFY / "models" / "diffusion_models" / "ltx-2-19b-dev_fp4_transformer_only.safetensors",
        "label": "LTX-2 19B transformer (FP4)",
    },
    {
        "url": "https://huggingface.co/Kijai/LTXV2_comfy/resolve/main/VAE/LTX2_video_vae_bf16.safetensors",
        "dest": COMFY / "models" / "vae" / "LTX2_video_vae_bf16.safetensors",
        "label": "LTX-2 video VAE (BF16)",
    },
    {
        "url": "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
        "dest": COMFY / "models" / "text_encoders" / "gemma_3_12B_it_fp4_mixed.safetensors",
        "label": "Gemma-3 12B text encoder (FP4)",
    },
]

# -- Prompt ----------------------------------------------------------------
POSITIVE = (
    "A single candle flame flickering gently in a dark room, "
    "warm orange light casting soft shadows on a wooden table, "
    "close-up shot, shallow depth of field, cinematic lighting"
)
NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, "
    "distorted, watermarks"
)

FRAMES = 25      # 1 second @ 25 fps
WIDTH = 512
HEIGHT = 384
FPS = 25.0
STEPS = 20


def download_models():
    """Download any missing model files via curl (resume-capable)."""
    for m in MODELS:
        dest = m["dest"]
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"  OK {m['label']} ({dest.stat().st_size / 1e9:.1f} GB)")
            continue
        print(f"  Downloading {m['label']}...")
        print(f"    -> {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["curl", "-L", "-C", "-", "--progress-bar",
             "-o", str(dest), m["url"]],
            check=True,
        )
        print(f"  Done ({dest.stat().st_size / 1e9:.1f} GB)")


def build_workflow():
    """Build a minimal LTX-2 text-to-video API workflow using split loaders."""
    return {
        # 1. Load diffusion model (transformer only)
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "ltx-2-19b-dev_fp4_transformer_only.safetensors",
                "weight_dtype": "default",
            },
        },
        # 2. Load VAE separately
        "2": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "LTX2_video_vae_bf16.safetensors",
            },
        },
        # 3. Load text encoder (Gemma-3)
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "gemma_3_12B_it_fp4_mixed.safetensors",
                "type": "ltxv",
            },
        },
        # 4. Positive prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["3", 0],
                "text": POSITIVE,
            },
        },
        # 5. Negative prompt
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["3", 0],
                "text": NEGATIVE,
            },
        },
        # 6. Frame-rate conditioning
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "frame_rate": FPS,
            },
        },
        # 7. Empty latent video
        "7": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": WIDTH,
                "height": HEIGHT,
                "length": FRAMES,
                "batch_size": 1,
            },
        },
        # 8. LTX scheduler -> sigmas
        "8": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": STEPS,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["7", 0],
            },
        },
        # 9. Random noise
        "9": {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": 42,
            },
        },
        # 10. Sampler selection
        "10": {
            "class_type": "KSamplerSelect",
            "inputs": {
                "sampler_name": "euler",
            },
        },
        # 11. CFG Guider
        "11": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["6", 1],
                "cfg": 3.0,
            },
        },
        # 12. Sample
        "12": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["11", 0],
                "sampler": ["10", 0],
                "sigmas": ["8", 0],
                "latent_image": ["7", 0],
            },
        },
        # 13. VAE Decode
        "13": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["12", 0],
                "vae": ["2", 0],
            },
        },
        # 14. Create video from frames
        "14": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["13", 0],
                "fps": FPS,
            },
        },
        # 15. Save video
        "15": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["14", 0],
                "filename_prefix": "ltx_smoke_test",
                "format": "mp4",
                "codec": "h264",
            },
        },
    }


def queue_prompt(prompt_data):
    client_id = str(uuid.uuid4())
    payload = json.dumps({"prompt": prompt_data, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{SERVER}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    if "error" in result:
        print(f"ERROR: {result['error']}")
        if "node_errors" in result:
            for nid, err in result["node_errors"].items():
                print(f"  Node {nid}: {err}")
        sys.exit(1)
    return result["prompt_id"]


def wait_for_completion(prompt_id, timeout=900):
    start = time.time()
    last_print = 0
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{SERVER}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass

        elapsed = int(time.time() - start)
        if elapsed - last_print >= 15:
            print(f"  ... {elapsed}s elapsed")
            last_print = elapsed
        time.sleep(3)

    raise TimeoutError(f"Workflow did not complete within {timeout}s")


def main():
    # Check server
    print("Checking ComfyUI server...")
    try:
        urllib.request.urlopen(f"{SERVER}/system_stats")
    except Exception:
        print(f"ERROR: ComfyUI not running at {SERVER}")
        sys.exit(1)
    print("  Server is up\n")

    # Download models
    print("Checking models...")
    download_models()
    print()

    # Build and submit
    workflow = build_workflow()
    print("Submitting LTX-2 smoke test workflow...")
    print(f"  Prompt: {POSITIVE[:60]}...")
    print(f"  Resolution: {WIDTH}x{HEIGHT}, {FRAMES} frames @ {FPS} fps (1 second)")
    print(f"  Steps: {STEPS}, Sampler: euler, CFG: 3.0")
    print()

    prompt_id = queue_prompt(workflow)
    print(f"  Queued: {prompt_id}")
    print("  Waiting for generation (first run loads models, may take a few minutes)...")

    result = wait_for_completion(prompt_id, timeout=900)

    status = result.get("status", {})
    if status.get("status_str") == "error":
        print("\n  FAILED")
        for m in status.get("messages", []):
            print(f"    {m}")
        sys.exit(1)

    outputs = result.get("outputs", {})
    saved = []
    for node_id, node_out in outputs.items():
        for key in ("videos", "images", "gifs"):
            if key in node_out:
                for item in node_out[key]:
                    fn = item.get("filename", "?")
                    sub = item.get("subfolder", "")
                    full = os.path.join(sub, fn) if sub else fn
                    saved.append(full)

    print(f"\n  SMOKE TEST PASSED")
    for s in saved:
        out_path = COMFY / "output" / s
        size = out_path.stat().st_size if out_path.exists() else 0
        print(f"    Saved: {s} ({size / 1024:.0f} KB)")

    print("\nValidation checklist:")
    print("  [ ] Open the video and check for smooth candle flicker (temporal coherence)")
    print("  [ ] Verify warm orange tones (color rendering)")
    print("  [ ] Confirm no frame stuttering or smearing (temporal stability)")
    print(f"\n  Output dir: {COMFY / 'output'}")


if __name__ == "__main__":
    main()
