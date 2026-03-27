"""Integration tests for ComfyUI API — require running server."""

import json
import os
import shutil
import time

import pytest
import requests

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")


def submit_and_wait(workflow, timeout=60):
    """Submit workflow to ComfyUI and wait for completion."""
    resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=10)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        hist = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5).json()
        if prompt_id in hist:
            status = hist[prompt_id].get("status", {})
            if status.get("completed", False) or hist[prompt_id].get("outputs"):
                return hist[prompt_id]
            if status.get("status_str") == "error":
                pytest.fail(f"Workflow error: {status.get('messages', '')}")
        time.sleep(1)
    pytest.fail(f"Workflow timed out after {timeout}s")


@pytest.fixture(autouse=True)
def require_comfyui():
    """Skip all tests in this module if ComfyUI is not running."""
    try:
        resp = requests.get(f"{COMFYUI_URL}/system_stats", timeout=3)
        resp.raise_for_status()
    except Exception:
        pytest.skip("ComfyUI not running")


class TestComfyUIHealth:
    def test_system_stats(self):
        resp = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        data = resp.json()
        assert "devices" in data
        assert len(data["devices"]) > 0

    def test_object_info(self):
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        data = resp.json()
        assert "LoadImage" in data
        assert "PreviewImage" in data

    def test_queue_status(self):
        resp = requests.get(f"{COMFYUI_URL}/queue", timeout=5)
        data = resp.json()
        assert "queue_running" in data
        assert "queue_pending" in data


class TestLoadImageWorkflow:
    @pytest.fixture(autouse=True)
    def setup_test_image(self, root_dir):
        """Copy test card to ComfyUI input folder."""
        src = root_dir / "demo" / "assets" / "test_card_720p.png"
        comfyui_input = root_dir / "ComfyUI" / "input"
        if src.exists() and comfyui_input.exists():
            shutil.copy2(src, comfyui_input / "cvs_test_card.png")
            yield
        else:
            pytest.skip("Test card or ComfyUI input dir not found")

    def test_load_and_preview(self):
        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "cvs_test_card.png"}
            },
            "2": {
                "class_type": "PreviewImage",
                "inputs": {"images": ["1", 0]}
            }
        }
        result = submit_and_wait(workflow)
        assert "outputs" in result
        assert "2" in result["outputs"]

    def test_load_and_upscale(self):
        """LoadImage -> 4x-UltraSharp -> ScaleBy 0.25x -> Preview."""
        workflow = {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "cvs_test_card.png"}
            },
            "3": {
                "class_type": "UpscaleModelLoader",
                "inputs": {"model_name": "4x-UltraSharp.pth"}
            },
            "4": {
                "class_type": "ImageUpscaleWithModel",
                "inputs": {
                    "upscale_model": ["3", 0],
                    "image": ["1", 0]
                }
            },
            "5": {
                "class_type": "ImageScaleBy",
                "inputs": {
                    "image": ["4", 0],
                    "upscale_method": "lanczos",
                    "scale_by": 0.25
                }
            },
            "6": {
                "class_type": "PreviewImage",
                "inputs": {"images": ["5", 0]}
            }
        }
        result = submit_and_wait(workflow, timeout=120)
        assert "6" in result["outputs"]
        images = result["outputs"]["6"].get("images", [])
        assert len(images) > 0


class TestNodeAvailability:
    """Verify CVS-relevant nodes are registered."""

    def test_kombucha_nodes_registered(self):
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        data = resp.json()
        kombucha_nodes = [
            "ParseTickLog", "ElevenLabsTTS", "MotionClip",
            "VerticalFrameComposite", "TextOverlay"
        ]
        for node in kombucha_nodes:
            assert node in data, f"Node {node} not registered in ComfyUI"

    def test_video_helper_nodes(self):
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        data = resp.json()
        for node in ["VHS_LoadVideoPath", "VHS_VideoCombine"]:
            assert node in data, f"Node {node} not registered"

    def test_text_generate_node(self):
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        data = resp.json()
        assert "TextGenerate" in data

    def test_preview_any_node(self):
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=10)
        data = resp.json()
        assert "PreviewAny" in data
