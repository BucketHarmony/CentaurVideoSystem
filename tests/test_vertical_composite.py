"""Tests for VerticalFrameComposite node."""

import torch
import pytest
from nodes import VerticalFrameComposite


class TestVerticalFrameComposite:
    def setup_method(self):
        self.node = VerticalFrameComposite()

    def test_output_dimensions(self):
        """Output should match requested canvas size."""
        frames = torch.rand(5, 480, 640, 3)  # 640x480 landscape
        result, top, bottom = self.node.composite(
            frames, canvas_width=1080, canvas_height=1920,
            blur_radius=25, blur_darken=0.4, video_y_offset=0
        )
        assert result.shape == (5, 1920, 1080, 3)

    def test_frame_count_preserved(self):
        """Number of frames in == number of frames out."""
        frames = torch.rand(10, 100, 200, 3)
        result, _, _ = self.node.composite(
            frames, canvas_width=540, canvas_height=960,
            blur_radius=10, blur_darken=0.5, video_y_offset=0
        )
        assert result.shape[0] == 10

    def test_zone_heights_returned(self):
        """Top zone and bottom zone start should be valid positions."""
        frames = torch.rand(3, 480, 640, 3)
        _, top_zone, bottom_start = self.node.composite(
            frames, canvas_width=1080, canvas_height=1920,
            blur_radius=25, blur_darken=0.4, video_y_offset=0
        )
        assert isinstance(top_zone, int)
        assert isinstance(bottom_start, int)
        assert top_zone < bottom_start
        assert bottom_start <= 1920

    def test_y_offset_shifts_video(self):
        """Negative offset should push video up (smaller top zone)."""
        frames = torch.rand(2, 480, 640, 3)
        _, top_zero, _ = self.node.composite(
            frames, 1080, 1920, 25, 0.4, video_y_offset=0
        )
        _, top_neg, _ = self.node.composite(
            frames, 1080, 1920, 25, 0.4, video_y_offset=-100
        )
        assert top_neg < top_zero

    def test_blur_darken_affects_background(self):
        """blur_darken=0 should make background black."""
        frames = torch.ones(2, 100, 200, 3) * 0.8  # Bright frames
        result, top, _ = self.node.composite(
            frames, canvas_width=200, canvas_height=400,
            blur_radius=0, blur_darken=0.0, video_y_offset=0
        )
        # Top zone (above video) should be near black
        if top > 0:
            bg_region = result[:, :top, :, :]
            assert bg_region.mean().item() < 0.01

    def test_no_blur(self):
        """blur_radius=0 should still produce valid output."""
        frames = torch.rand(2, 100, 200, 3)
        result, _, _ = self.node.composite(
            frames, 200, 400, blur_radius=0, blur_darken=0.5, video_y_offset=0
        )
        assert result.shape == (2, 400, 200, 3)

    def test_square_canvas(self):
        """Should work with square output (1080x1080)."""
        frames = torch.rand(3, 480, 640, 3)
        result, top, bottom = self.node.composite(
            frames, 1080, 1080, 15, 0.4, 0
        )
        assert result.shape == (3, 1080, 1080, 3)

    def test_values_in_range(self):
        """All pixel values should remain in [0, 1]."""
        frames = torch.rand(5, 100, 200, 3)
        result, _, _ = self.node.composite(
            frames, 200, 400, 25, 0.4, 0
        )
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_input_types_schema(self):
        types = VerticalFrameComposite.INPUT_TYPES()
        assert "images" in types["required"]
        assert "canvas_width" in types["required"]
        assert VerticalFrameComposite.RETURN_TYPES == ("IMAGE", "INT", "INT")
