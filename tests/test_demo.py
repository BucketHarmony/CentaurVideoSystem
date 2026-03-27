"""Tests for demo asset generation and integrity."""

import json
import subprocess
import pytest
from pathlib import Path
from PIL import Image


class TestDemoAssets:
    def test_test_card_720p_exists(self, demo_dir):
        path = demo_dir / "assets" / "test_card_720p.png"
        assert path.exists()

    def test_test_card_1080p_exists(self, demo_dir):
        path = demo_dir / "assets" / "test_card_1080p.png"
        assert path.exists()

    def test_sample_video_exists(self, demo_dir):
        path = demo_dir / "assets" / "sample_video.mp4"
        assert path.exists()

    def test_test_card_720p_dimensions(self, demo_dir):
        img = Image.open(demo_dir / "assets" / "test_card_720p.png")
        assert img.size == (1280, 720)

    def test_test_card_1080p_dimensions(self, demo_dir):
        img = Image.open(demo_dir / "assets" / "test_card_1080p.png")
        assert img.size == (1920, 1080)

    def test_test_card_is_rgb(self, demo_dir):
        img = Image.open(demo_dir / "assets" / "test_card_720p.png")
        assert img.mode == "RGB"

    def test_test_card_not_blank(self, demo_dir):
        """Test card should have color variation (not solid color)."""
        import numpy as np
        img = np.array(Image.open(demo_dir / "assets" / "test_card_720p.png"))
        assert img.std() > 10, "Test card appears blank"

    def test_brand_kit_exists(self, demo_dir):
        path = demo_dir / "brand" / "demo_brand.json"
        assert path.exists()

    def test_brand_kit_valid(self, demo_dir):
        with open(demo_dir / "brand" / "demo_brand.json") as f:
            data = json.load(f)
        assert data["name"] == "CVS Demo"


class TestDemoGeneration:
    def test_test_card_script_runs(self, demo_dir):
        """test_card.py should execute without errors."""
        result = subprocess.run(
            ["python", str(demo_dir / "assets" / "test_card.py")],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, f"test_card.py failed: {result.stderr}"

    def test_regenerated_cards_correct_size(self, demo_dir):
        """After regeneration, cards should still be correct dimensions."""
        subprocess.run(
            ["python", str(demo_dir / "assets" / "test_card.py")],
            capture_output=True, timeout=30
        )
        img720 = Image.open(demo_dir / "assets" / "test_card_720p.png")
        img1080 = Image.open(demo_dir / "assets" / "test_card_1080p.png")
        assert img720.size == (1280, 720)
        assert img1080.size == (1920, 1080)


class TestSampleVideo:
    def test_video_probe(self, demo_dir):
        """Sample video should be valid H.264 MP4."""
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams",
             str(demo_dir / "assets" / "sample_video.mp4")],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        assert stream["codec_name"] == "h264"
        assert int(stream["width"]) == 1280
        assert int(stream["height"]) == 720
        duration = float(data["format"]["duration"])
        assert 4.5 <= duration <= 5.5
