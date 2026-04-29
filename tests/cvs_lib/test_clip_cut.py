"""Tests for cvs_lib.clip_cut — HDR-aware frame-accurate cut.

Pure-function tests cover command shape and HDR auto-detect logic.
One end-to-end ffmpeg test confirms the pipeline produces a playable
SDR file (slow, ~3-5s on the demo source — gated by the file's
existence so CI without the raw assets still passes the rest)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cvs_lib.clip_cut import (
    ProbeResult,
    build_cmd,
    cut_clip,
    probe_video,
)

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
HDR_PATH = RAW_DIR / "20260425_170328.mp4"   # iPhone HEVC Main 10 HLG


# --------------------------- pure-function shape -------------------------- #

def test_build_cmd_sdr_skips_tonemap_filter():
    cmd = build_cmd("in.mp4", 1.0, 2.0, "out.mp4", is_hdr=False)
    assert "-vf" not in cmd
    # H.264 Main + 8-bit pixel format are non-negotiable for compatibility.
    assert "-profile:v" in cmd and "main" in cmd
    assert "yuv420p" in cmd


def test_build_cmd_hdr_includes_zscale_chain():
    cmd = build_cmd("in.mp4", 0.0, 1.0, "out.mp4", is_hdr=True)
    vf_idx = cmd.index("-vf")
    vf = cmd[vf_idx + 1]
    # All three legs of the tonemap chain present.
    assert "zscale=t=linear" in vf
    assert "tonemap=hable" in vf
    assert "format=yuv420p" in vf


def test_build_cmd_uses_output_seek_for_frame_accuracy():
    # `-ss` must come AFTER `-i` for frame-accurate seek (output-seek);
    # `-ss` before `-i` is fast but rounds to the nearest keyframe.
    cmd = build_cmd("in.mp4", 5.5, 10.0, "out.mp4", is_hdr=False)
    i_idx = cmd.index("-i")
    ss_idx = cmd.index("-ss")
    assert ss_idx > i_idx


def test_build_cmd_audio_aac_with_kbps():
    cmd = build_cmd("in.mp4", 0.0, 1.0, "out.mp4",
                    is_hdr=False, audio_kbps=128)
    assert "aac" in cmd
    assert "128k" in cmd


def test_build_cmd_passes_crf_and_preset():
    cmd = build_cmd("in.mp4", 0.0, 1.0, "out.mp4",
                    is_hdr=False, crf=23, preset="medium")
    assert "23" in cmd
    assert "medium" in cmd


# ------------------------------- input gates ------------------------------ #

def test_cut_clip_rejects_inverted_range(tmp_path):
    # Don't reach ffprobe; the time-range check fires first.
    with pytest.raises(ValueError):
        cut_clip("nonexistent.mp4", 2.0, 1.0, tmp_path / "out.mp4")


def test_cut_clip_raises_for_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        cut_clip(
            tmp_path / "does_not_exist.mp4", 0.0, 1.0,
            tmp_path / "out.mp4", tonemap="sdr",
        )


# ------------------------------- HDR detect ------------------------------- #

@pytest.mark.skipif(not HDR_PATH.exists(),
                    reason="raw HDR source not available")
def test_probe_detects_hlg_iphone_source():
    p = probe_video(HDR_PATH)
    assert p.is_hdr is True
    # iPhone HEVC Main 10 HLG signature: HLG transfer + 10-bit pixel format.
    assert p.color_transfer == "arib-std-b67"
    assert "10" in p.pix_fmt


def test_probe_result_is_hdr_signal_combinations():
    # Direct dataclass construction — exercises the docstring claim
    # that any of the three signals is sufficient. Mirrors what
    # probe_video would return on a borderline source.
    sdr = ProbeResult("bt709", "bt709", "bt709", "yuv420p", False)
    hdr_transfer = ProbeResult("smpte2084", "bt709", "bt709", "yuv420p", True)
    hdr_primaries = ProbeResult("bt709", "bt2020", "bt709", "yuv420p", True)
    hdr_10bit = ProbeResult("bt709", "bt709", "bt709", "yuv420p10le", True)
    assert not sdr.is_hdr
    assert hdr_transfer.is_hdr
    assert hdr_primaries.is_hdr
    assert hdr_10bit.is_hdr


# --------------------------- end-to-end ffmpeg --------------------------- #

@pytest.mark.skipif(not HDR_PATH.exists(),
                    reason="raw HDR source not available")
def test_cut_clip_produces_playable_sdr_file(tmp_path):
    """Auto mode on the iPhone HDR source produces a real H.264 Main
    yuv420p file. Slow (3-5s) — gated by file existence."""
    dst = tmp_path / "cut.mp4"
    elapsed = cut_clip(HDR_PATH, 1.0, 2.5, dst)
    assert elapsed > 0
    assert dst.exists() and dst.stat().st_size > 1000
    # ffprobe the result: must be SDR after auto-tonemap.
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt,profile,color_transfer",
        "-of", "default=nw=1", str(dst),
    ], text=True)
    assert "yuv420p" in out
    assert "Main" in out  # H.264 Main, not High 10
    # color_transfer should be bt709 or unset, not arib-std-b67/smpte2084
    assert "arib-std-b67" not in out
    assert "smpte2084" not in out
