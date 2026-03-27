"""Tests for MotionClip node."""

import torch
import pytest
from nodes import MotionClip


class TestMotionClip:
    def setup_method(self):
        self.node = MotionClip()

    def test_removes_static_frames(self, static_frames):
        """Static frames should be uniformly sampled (no motion segments)."""
        result, count = self.node.clip_motion(
            static_frames, sensitivity=1.5, min_segment_frames=5,
            merge_gap_frames=15, pad_frames=8, max_output_frames=600
        )
        # All frames identical -> no motion detected -> uniform sample
        assert count <= static_frames.shape[0]
        assert result.shape[0] == count

    def test_keeps_motion_frames(self, sample_frames):
        """Frames with a moving gradient should have motion detected."""
        result, count = self.node.clip_motion(
            sample_frames, sensitivity=1.5, min_segment_frames=2,
            merge_gap_frames=3, pad_frames=2, max_output_frames=600
        )
        assert count > 0
        assert result.shape[0] == count
        assert result.shape[-1] == 3  # RGB channels preserved

    def test_passthrough_tiny_batch(self):
        """2 or fewer frames should pass through unchanged."""
        frames = torch.rand(2, 32, 32, 3)
        result, count = self.node.clip_motion(
            frames, sensitivity=1.5, min_segment_frames=5,
            merge_gap_frames=15, pad_frames=8, max_output_frames=600
        )
        assert count == 2
        assert torch.equal(result, frames)

    def test_max_output_frames_respected(self):
        """Output should not exceed max_output_frames."""
        # 100 frames with strong motion
        frames = torch.zeros(100, 32, 32, 3)
        for i in range(100):
            frames[i] = float(i) / 100.0
        result, count = self.node.clip_motion(
            frames, sensitivity=0.5, min_segment_frames=1,
            merge_gap_frames=100, pad_frames=0, max_output_frames=20
        )
        assert count <= 20

    def test_output_shape_matches_input_dims(self, sample_frames):
        result, count = self.node.clip_motion(
            sample_frames, sensitivity=1.5, min_segment_frames=2,
            merge_gap_frames=3, pad_frames=2, max_output_frames=600
        )
        assert result.shape[1] == sample_frames.shape[1]  # H
        assert result.shape[2] == sample_frames.shape[2]  # W
        assert result.shape[3] == sample_frames.shape[3]  # C

    def test_high_sensitivity_keeps_fewer(self):
        """Higher sensitivity threshold -> fewer motion frames detected."""
        # Create frames with clear motion burst in the middle
        import torch
        frames = torch.zeros(60, 32, 32, 3)
        # First 20 frames: static
        frames[:20] = 0.5
        # Middle 20 frames: strong motion (each frame very different)
        for i in range(20, 40):
            frames[i] = float(i) / 60.0
        # Last 20 frames: static again
        frames[40:] = 0.3

        _, count_low = self.node.clip_motion(
            frames, sensitivity=1.0, min_segment_frames=2,
            merge_gap_frames=3, pad_frames=0, max_output_frames=600
        )
        _, count_high = self.node.clip_motion(
            frames, sensitivity=4.0, min_segment_frames=2,
            merge_gap_frames=3, pad_frames=0, max_output_frames=600
        )
        assert count_high <= count_low

    def test_input_types_schema(self):
        types = MotionClip.INPUT_TYPES()
        assert "images" in types["required"]
        assert "sensitivity" in types["required"]
        assert MotionClip.RETURN_TYPES == ("IMAGE", "INT")
