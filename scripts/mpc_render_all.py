"""Batch driver for MPC reels.

Iterates every `scripts/mpc_ep_*.py`, renders each whose output is
missing or older than the script source, and emits a manifest at
`output/mpc/manifest.json` listing duration, size, source script, and
matching cover for every rendered reel.

Defaults to skip-if-newer so it's safe to run repeatedly. Use
`--force` to re-render everything, `--manifest-only` to skip rendering
and just refresh the manifest from existing outputs.

Each script is expected to write to `output/mpc/<output_name>.mp4`.
The script-to-output mapping is inferred by matching `OUTPUT_PATH = ...`
or the docstring's `Output:` line; if neither is found, the script is
flagged in the manifest with `output_inferred=false`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
OUT_DIR = REPO / "ComfyUI" / "output" / "mpc"
COVERS_DIR = OUT_DIR / "covers"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Reels are scripts/mpc_ep_*.py; mpc_still_*.py and mpc_make_*.py are not reels.
REEL_GLOB = "mpc_ep_*.py"


def discover_scripts() -> list[Path]:
    return sorted(SCRIPTS_DIR.glob(REEL_GLOB))


_OUTPUT_PATH_RX = re.compile(
    r"OUTPUT_PATH\s*=\s*[A-Z_]+\s*/\s*[\"']([^\"']+\.mp4)[\"']", re.M)
_DOCSTRING_OUTPUT_RX = re.compile(
    r"Output:\s*([^\s]+\.mp4)", re.M)


def infer_output_path(script: Path) -> tuple[Path | None, bool]:
    """Find the mp4 path the script writes to.

    Returns (path, inferred_strictly). `inferred_strictly` is True if
    found from the OUTPUT_PATH constant; False if from the docstring or
    by stem-matching fallback.
    """
    src = script.read_text(encoding="utf-8")
    m = _OUTPUT_PATH_RX.search(src)
    if m:
        return OUT_DIR / m.group(1), True
    m = _DOCSTRING_OUTPUT_RX.search(src)
    if m:
        p = Path(m.group(1))
        return p, False
    # Fallback: stem-match. mpc_ep_foo.py -> foo.mp4
    stem = script.stem.replace("mpc_ep_", "")
    return OUT_DIR / f"{stem}.mp4", False


def needs_render(script: Path, out_path: Path) -> bool:
    if not out_path.exists():
        return True
    return out_path.stat().st_mtime < script.stat().st_mtime


def render_one(script: Path) -> tuple[bool, float, str]:
    """Subprocess `python <script>`. Returns (ok, elapsed_s, last_line)."""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO),
        capture_output=True, text=True,
    )
    elapsed = time.time() - t0
    last_line = ""
    if proc.stdout:
        for line in proc.stdout.splitlines()[::-1]:
            if line.strip():
                last_line = line.strip()
                break
    if proc.returncode != 0:
        # Surface stderr tail on failure
        err_tail = "\n".join(proc.stderr.splitlines()[-10:])
        print(f"  STDERR (tail): {err_tail}")
        return (False, elapsed, last_line)
    return (True, elapsed, last_line)


def probe_video(p: Path) -> dict:
    """ffprobe a video for duration + size. Returns minimal dict."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error",
             "-show_entries",
             "format=duration,size,bit_rate:stream=codec_name,width,height",
             "-of", "json", str(p)],
            stderr=subprocess.STDOUT,
        ).decode()
        data = json.loads(out)
        fmt = data.get("format", {})
        v_stream = next((s for s in data.get("streams", [])
                         if s.get("codec_name") in ("h264", "hevc", "vp9", "av1")), {})
        return {
            "duration_s": float(fmt.get("duration", 0.0)),
            "size_bytes": int(fmt.get("size", 0)),
            "bit_rate": int(fmt.get("bit_rate", 0) or 0),
            "codec": v_stream.get("codec_name"),
            "width": v_stream.get("width"),
            "height": v_stream.get("height"),
        }
    except Exception as e:
        return {"probe_error": str(e)}


def find_cover(reel_stem: str) -> Path | None:
    p = COVERS_DIR / f"{reel_stem}.png"
    return p if p.exists() else None


def build_manifest(scripts: list[Path]) -> dict:
    reels = []
    for s in scripts:
        out, strict = infer_output_path(s)
        entry = {
            "script": str(s.relative_to(REPO)).replace("\\", "/"),
            "output": str(out.relative_to(REPO)).replace("\\", "/") if out else None,
            "output_inferred_strictly": strict,
            "rendered": out.exists() if out else False,
        }
        if out and out.exists():
            entry.update(probe_video(out))
            cover = find_cover(out.stem)
            if cover:
                entry["cover"] = str(cover.relative_to(REPO)).replace("\\", "/")
                entry["cover_size_bytes"] = cover.stat().st_size
        reels.append(entry)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reel_count": len(reels),
        "rendered_count": sum(1 for r in reels if r.get("rendered")),
        "reels": reels,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Re-render every reel, ignoring mtime check.")
    ap.add_argument("--manifest-only", action="store_true",
                    help="Skip rendering; just refresh manifest.json.")
    ap.add_argument("--filter", type=str, default=None,
                    help="Only operate on scripts whose stem contains this.")
    args = ap.parse_args()

    scripts = discover_scripts()
    if args.filter:
        scripts = [s for s in scripts if args.filter in s.stem]
    print(f"Found {len(scripts)} reel scripts in {SCRIPTS_DIR}")

    if not args.manifest_only:
        for s in scripts:
            out, _ = infer_output_path(s)
            if out is None:
                print(f"  ? {s.name}  (no output path inferred — skip)")
                continue
            if not args.force and not needs_render(s, out):
                age_s = (s.stat().st_mtime - out.stat().st_mtime) if out.exists() else 0
                print(f"  - {s.name}  (cached, output newer)")
                continue
            print(f"  > {s.name}  -> {out.name}")
            ok, elapsed, last = render_one(s)
            tag = "OK" if ok else "FAIL"
            print(f"    {tag}  ({elapsed:.1f}s)  {last}")

    print("\nBuilding manifest...")
    manifest = build_manifest(scripts)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  {MANIFEST_PATH}  ({manifest['rendered_count']}/{manifest['reel_count']} rendered)")


if __name__ == "__main__":
    main()
