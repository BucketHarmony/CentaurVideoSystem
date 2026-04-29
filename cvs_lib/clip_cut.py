"""Frame-accurate clip cutter with HDR → SDR auto-tonemap.

iPhone records HEVC Main 10 HLG (BT.2020). A naive `ffmpeg -ss -to -c
copy` cut preserves those tags and produces a High 10 H.264 file that
browsers / TikTok / Instagram refuse to play. This module's `cut_clip`
auto-detects HDR via ffprobe and routes through a tested tonemap chain
(zscale linear → bt709 → hable tonemap → 8-bit yuv420p, H.264 Main).
SDR sources skip the chain (~3× faster).

Output-seek (`-ss` after `-i`) is always frame-accurate, slower for
late cuts but safe for the typical short rally clip.

CLI:
    python -m cvs_lib.clip_cut <src> <in_t> <out_t> <dst>
    python -m cvs_lib.clip_cut --no-tonemap <src> <in_t> <out_t> <dst>
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

PathLike = Union[str, Path]
TonemapMode = Literal["auto", "hdr", "sdr"]

# HLG and PQ are the two HDR transfer curves we routinely see; bt709 /
# smpte170m / unset all read as SDR. bt2020 primaries with a non-HDR
# transfer is rare but real (high-bit-depth SDR); the pix_fmt 10-bit
# check catches that case as a third signal.
_HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}
_HDR_PRIMARIES = {"bt2020"}


@dataclass
class ProbeResult:
    """Subset of ffprobe video-stream fields used for HDR detection."""
    color_transfer: str
    color_primaries: str
    color_space: str
    pix_fmt: str
    is_hdr: bool


def probe_video(src: PathLike) -> ProbeResult:
    """Run ffprobe and decide whether the source needs HDR tonemap.

    A source is HDR if any of:
      - color_transfer is HLG or PQ
      - color_primaries is bt2020
      - pix_fmt is 10-bit (yuv420p10le, p010, etc.)

    The third check catches mis-tagged HDR sources where the bit depth
    is the only honest signal.
    """
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=color_transfer,color_primaries,color_space,pix_fmt",
        "-of", "json", str(src),
    ]
    out = subprocess.check_output(cmd)
    data = json.loads(out)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"ffprobe found no video stream in {src}")
    s = streams[0]
    transfer = s.get("color_transfer") or ""
    primaries = s.get("color_primaries") or ""
    space = s.get("color_space") or ""
    pix_fmt = s.get("pix_fmt") or ""
    is_hdr = (
        transfer in _HDR_TRANSFERS
        or primaries in _HDR_PRIMARIES
        or "10le" in pix_fmt
        or pix_fmt.startswith("p010")
    )
    return ProbeResult(
        color_transfer=transfer,
        color_primaries=primaries,
        color_space=space,
        pix_fmt=pix_fmt,
        is_hdr=is_hdr,
    )


# ffmpeg -vf chain: HDR HLG/PQ → linear light (npl=100 nits ref white) →
# tonemap hable (preserves highlights better than reinhard) → bt709
# matrix/primaries/transfer → 8-bit yuv420p.
_HDR_VF = (
    "zscale=t=linear:npl=100,format=gbrpf32le,"
    "zscale=p=bt709,tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def build_cmd(
    src: PathLike,
    in_t: float,
    out_t: float,
    dst: PathLike,
    *,
    is_hdr: bool,
    crf: int = 20,
    preset: str = "fast",
    audio_kbps: int = 192,
) -> list:
    """Build the ffmpeg argv. Pure function — no I/O — so tests can
    assert command shape without invoking ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-ss", f"{in_t:.3f}",
        "-to", f"{out_t:.3f}",
    ]
    if is_hdr:
        cmd += ["-vf", _HDR_VF]
    cmd += [
        "-c:v", "libx264", "-profile:v", "main",
        "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", f"{audio_kbps}k",
        "-movflags", "+faststart",
        str(dst),
    ]
    return cmd


def cut_clip(
    src: PathLike,
    in_t: float,
    out_t: float,
    dst: PathLike,
    *,
    tonemap: TonemapMode = "auto",
    crf: int = 20,
    preset: str = "fast",
    audio_kbps: int = 192,
) -> float:
    """Cut `[in_t, out_t]` from `src` to `dst` with frame-accurate seek
    and (when needed) HDR → SDR tonemap. Returns elapsed wall-clock
    seconds.

    `tonemap` modes:
      - "auto" (default): ffprobe the source and tonemap iff HDR.
      - "hdr": always run the tonemap chain.
      - "sdr": skip the chain even if the source looks HDR.

    Raises `subprocess.CalledProcessError` if ffmpeg fails.
    """
    if out_t <= in_t:
        raise ValueError(f"out_t ({out_t}) must be > in_t ({in_t})")

    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists():
        raise FileNotFoundError(f"source not found: {src_p}")
    dst_p.parent.mkdir(parents=True, exist_ok=True)

    if tonemap == "auto":
        is_hdr = probe_video(src_p).is_hdr
    else:
        is_hdr = tonemap == "hdr"

    cmd = build_cmd(
        src_p, in_t, out_t, dst_p,
        is_hdr=is_hdr, crf=crf, preset=preset, audio_kbps=audio_kbps,
    )
    t0 = time.time()
    subprocess.run(cmd, check=True)
    return time.time() - t0


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m cvs_lib.clip_cut",
        description="Frame-accurate cut with optional HDR tonemap.",
    )
    ap.add_argument("src")
    ap.add_argument("in_t", type=float)
    ap.add_argument("out_t", type=float)
    ap.add_argument("dst")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hdr", dest="mode", action="store_const", const="hdr",
                   help="Force HDR tonemap chain.")
    g.add_argument("--no-tonemap", dest="mode", action="store_const",
                   const="sdr", help="Skip tonemap even if source is HDR.")
    ap.set_defaults(mode="auto")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="fast")
    args = ap.parse_args()

    elapsed = cut_clip(
        args.src, args.in_t, args.out_t, args.dst,
        tonemap=args.mode, crf=args.crf, preset=args.preset,
    )
    print(f"  -> {args.dst}  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
