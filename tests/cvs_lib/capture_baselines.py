"""Capture pre-migration baselines for the 8 MPC reels.

For each reel:
- SHA-256 of the audio WAV file
- 3 reference frames at t=2.0, 15.0, 28.0 saved as PNG

Writes tests/cvs_lib/fixtures/baseline_manifest.json with the manifest.

Run:
    python E:/AI/CVS/tests/cvs_lib/capture_baselines.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REELS = [
    ("abolish_ice_congress", "mpc_ep_abolish_ice_congress.py"),
    ("detroit_knows",        "mpc_ep_detroit_knows.py"),
    ("follow_the_money",     "mpc_ep_follow_the_money.py"),
    ("north_lake",           "mpc_ep_north_lake.py"),
    ("people_power",         "mpc_ep_people_power.py"),
    ("romulus_rapid_response", "mpc_ep_romulus.py"),
    ("ten_weeks",            "mpc_ep_ten_weeks.py"),
    ("we_dont_back_down",    "mpc_ep_we_dont_back_down.py"),
]
FRAME_TIMES = [2.0, 15.0, 28.0]

ROOT = Path("E:/AI/CVS")
OUT_DIR = ROOT / "ComfyUI" / "output" / "mpc"
FIX_DIR = ROOT / "tests" / "cvs_lib" / "fixtures" / "baselines"
AUDIO_DIR = FIX_DIR / "audio"
FRAME_DIR = FIX_DIR / "frames"
MANIFEST = FIX_DIR.parent / "baseline_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_frame(mp4: Path, t: float, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(mp4),
        "-frames:v", "1", "-q:v", "2", str(out),
    ]
    subprocess.run(cmd, check=True)


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "frame_times_s": FRAME_TIMES,
        "reels": {},
    }

    for slug, script in REELS:
        mp4 = OUT_DIR / f"{slug}.mp4"
        wav = OUT_DIR / f"{slug}_audio.wav"
        if not mp4.exists():
            print(f"  MISSING mp4: {mp4}")
            continue
        if not wav.exists():
            print(f"  MISSING wav: {wav}")
            continue

        audio_sha = sha256_file(wav)
        mp4_sha = sha256_file(mp4)

        frame_paths = []
        for t in FRAME_TIMES:
            out = FRAME_DIR / f"{slug}_t{int(t):02d}.png"
            extract_frame(mp4, t, out)
            frame_paths.append({
                "t_s": t,
                "path": str(out.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(out),
            })

        manifest["reels"][slug] = {
            "script": f"scripts/{script}",
            "mp4": str(mp4.relative_to(ROOT)).replace("\\", "/"),
            "wav": str(wav.relative_to(ROOT)).replace("\\", "/"),
            "audio_wav_sha256": audio_sha,
            "mp4_sha256": mp4_sha,
            "frames": frame_paths,
        }
        print(f"  {slug:30s} audio={audio_sha[:12]} mp4={mp4_sha[:12]} frames=3")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {MANIFEST}  ({len(manifest['reels'])}/8 reels)")


if __name__ == "__main__":
    main()
