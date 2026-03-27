"""CVS test configuration and shared fixtures."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project paths for imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "comfyui-config" / "kombucha-pipeline"))
sys.path.insert(0, str(ROOT / "scripts"))

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")


@pytest.fixture
def root_dir():
    return ROOT


@pytest.fixture
def demo_dir():
    return ROOT / "demo"


@pytest.fixture
def brand_kit(demo_dir):
    with open(demo_dir / "brand" / "demo_brand.json") as f:
        return json.load(f)


@pytest.fixture
def sample_tick_log(tmp_path):
    """Create a minimal tick log for ParseTickLog testing."""
    content = """# Tick 0042

## Mood
curious

## Monologue
The hallway stretches ahead like a promise I cannot verify. Each centimeter is a negotiation with gravity. The walls are closer than they appear — or perhaps I am smaller than I remember.

## Thought
I should map this corridor before the battery decides otherwise.

## Observation
Flat terrain. Low obstacles. The light source is approximately 2.4 meters ahead at bearing 015.

## Perception
Distance sensors read 0.8m to left wall, 1.2m to right wall. Floor is smooth tile.

**Goal**: Reach the end of the hallway
**Intent**: Systematic forward exploration with wall-following
"""
    log_path = tmp_path / "tick_0042.md"
    log_path.write_text(content, encoding="utf-8")
    return log_path


@pytest.fixture
def sample_frames():
    """Generate a batch of synthetic video frames as torch tensor."""
    import torch
    # 30 frames of 64x64 RGB with a moving gradient
    B, H, W, C = 30, 64, 64, 3
    frames = torch.zeros(B, H, W, C)
    for i in range(B):
        # Create gradient that shifts per frame (simulates motion)
        x = torch.linspace(0, 1, W).unsqueeze(0).expand(H, -1)
        offset = i / B
        frames[i, :, :, 0] = (x + offset) % 1.0  # Red shifts
        frames[i, :, :, 1] = 0.2                    # Green constant
        frames[i, :, :, 2] = 1.0 - (x + offset) % 1.0  # Blue inverse
    return frames


@pytest.fixture
def static_frames():
    """Generate a batch of identical frames (no motion)."""
    import torch
    B, H, W, C = 30, 64, 64, 3
    frame = torch.rand(1, H, W, C)
    return frame.expand(B, -1, -1, -1).clone()


@pytest.fixture
def comfyui_available():
    """Check if ComfyUI is running and skip if not."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=3)
        return True
    except Exception:
        pytest.skip("ComfyUI not running")
