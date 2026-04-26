"""
MPC source scanner — for every video in raw/MPC/<event>/ produce:
  - per-clip JSON: meta, motion timeline, scene boundaries, transcript, tags
  - SQLite index of clips/scenes/tags/transcript-segments (+ FTS5 for search)
  - thumbnail per scene
  - human-readable scan_report.md

This is Phase 2 of the MPC pipeline — it's what lets later phases (LLM
tagging, hook scoring, brief-driven composition) query "where do I have a
crowd-shot under 8s with the word 'march' on the audio?" without manually
re-scrubbing footage.

Outputs land in E:/AI/CVS/mpc/index/ (clips/, thumbnails/, clips.db, scan_report.md).

Usage:
    python E:/AI/CVS/scripts/mpc_scan_sources.py
    python E:/AI/CVS/scripts/mpc_scan_sources.py --root "E:/AI/CVS/raw/MPC/Other Event"
    python E:/AI/CVS/scripts/mpc_scan_sources.py --whisper-model medium --device cuda
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_ROOT = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
INDEX_DIR = Path("E:/AI/CVS/mpc/index")
THUMB_DIR = INDEX_DIR / "thumbnails"
CLIPS_DIR = INDEX_DIR / "clips"
DB_PATH = INDEX_DIR / "clips.db"

# Heuristic transcript-keyword → tag mapping. Word-boundary regexes keep
# "ice" out of "police" and "march" out of "marchioness", etc.
TAG_PATTERNS = {
    "march":      [r"\bmarch(ing|ed|es)?\b", r"\brally\b", r"\bdemonstration\b"],
    "chant":      [r"\bchant", r"\bshout"],
    "warehouse":  [r"\bwarehouse"],
    "DHS":        [r"\bDHS\b", r"\bhomeland security\b"],
    "ICE":        [r"\bICE\b", r"\bimmigration enforcement\b"],
    "Romulus":    [r"\bromulus\b", r"\bcogswell\b"],
    "Nessel":     [r"\bnessel\b", r"\battorney general\b"],
    "immigrant":  [r"\bimmigra(nt|tion)\b", r"\basylum\b", r"\bdetention\b"],
    "press":      [r"\bpresser\b", r"\bpress conference\b"],
    "speech":     [r"\bfellow\b", r"\bneighbors?\b", r"\bcommunity\b"],
    "court":      [r"\bcourt\b", r"\binjunction\b", r"\bsuing\b", r"\blawsuit\b"],
}

# --------------------------------------------------------------------------- #
# ffprobe / OpenCV: metadata + motion timeline
# --------------------------------------------------------------------------- #

def probe_video(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True
    )
    info = json.loads(out.stdout) if out.stdout else {}
    fmt = info.get("format", {})
    streams = info.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    fps_str = vstream.get("r_frame_rate", "30/1")
    try:
        num, den = map(int, fps_str.split("/"))
        fps = num / den if den else 30.0
    except Exception:
        fps = 30.0
    return {
        "path": str(path),
        "filename": path.name,
        "duration_s": float(fmt.get("duration", 0)),
        "size_bytes": int(fmt.get("size", 0)),
        "width": int(vstream.get("width", 0)),
        "height": int(vstream.get("height", 0)),
        "fps": fps,
        "codec": vstream.get("codec_name", "unknown"),
    }


def motion_timeline(path: Path, sample_rate_hz: float = 2.0) -> list[dict]:
    """
    Sample motion at ~`sample_rate_hz` Hz. Each entry:
      {t: float (seconds), motion: float (0..255 mean abs frame-diff)}
    Frames are downsampled to 320x180 grayscale before diffing — fast and
    insensitive to compression noise at the original res.
    """
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps / sample_rate_hz)))
    timeline: list[dict] = []
    prev = None
    f = 0
    while f < n:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            motion = float(np.abs(gray.astype(int) - prev.astype(int)).mean())
            timeline.append({"t": round(f / fps, 3), "motion": round(motion, 3)})
        prev = gray
        f += step
    cap.release()
    return timeline


def detect_scenes(timeline: list[dict],
                  threshold: float = 14.0,
                  min_gap_s: float = 1.5) -> list[float]:
    """
    Treat motion spikes above `threshold` as scene boundaries (with a
    minimum gap so a sustained spike doesn't register as N back-to-back cuts).
    Always includes 0.0 as the first scene start.
    """
    cuts: list[float] = [0.0]
    last_t = 0.0
    for entry in timeline:
        if entry["motion"] > threshold and entry["t"] - last_t >= min_gap_s:
            cuts.append(entry["t"])
            last_t = entry["t"]
    return cuts


def extract_thumbnails(path: Path, scene_starts: list[float],
                       out_dir: Path, prefix: str) -> list[dict]:
    """One JPG per scene start, downscaled to 640w."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    out: list[dict] = []
    for i, t in enumerate(scene_starts):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        new_w = 640
        new_h = max(1, int(h * (new_w / w)))
        small = cv2.resize(frame, (new_w, new_h))
        out_path = out_dir / f"{prefix}_s{i:02d}_t{int(t):04d}.jpg"
        cv2.imwrite(str(out_path), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        out.append({"idx": i, "t": t, "path": str(out_path)})
    cap.release()
    return out


# --------------------------------------------------------------------------- #
# Whisper: transcription
# --------------------------------------------------------------------------- #

def load_whisper(model_size: str, device: str, compute_type: str):
    """Returns a faster-whisper WhisperModel. Falls back to CPU/int8 on CUDA failure."""
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as e:
        print(f"  [whisper] {device}/{compute_type} failed ({e}); falling back to cpu/int8")
        return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(path: Path, model) -> dict:
    segments_iter, info = model.transcribe(
        str(path), beam_size=1, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    segments = []
    parts = []
    for seg in segments_iter:
        text = seg.text.strip()
        segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": text})
        if text:
            parts.append(text)
    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration_s": info.duration,
        "text": " ".join(parts).strip(),
        "segments": segments,
    }


# --------------------------------------------------------------------------- #
# Tag derivation (heuristic — Phase 3 will layer LLM tagging on top)
# --------------------------------------------------------------------------- #

def derive_tags(meta: dict, transcript: dict, timeline: list[dict]) -> list[str]:
    tags: set[str] = set()
    text = transcript.get("text", "")

    for tag, patterns in TAG_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            tags.add(tag)

    if timeline:
        motions = [e["motion"] for e in timeline]
        avg_m = sum(motions) / len(motions)
        max_m = max(motions)
        if avg_m < 3.0:
            tags.add("static")
        elif avg_m > 14.0:
            tags.add("high_motion")
        if max_m > 30.0:
            tags.add("camera_shake")

    text_strip = text.strip()
    if not text_strip:
        tags.add("silent")
    elif len(text_strip) > 200:
        tags.add("dialogue")
    else:
        tags.add("ambient")

    if meta["duration_s"] < 8:
        tags.add("short")
    elif meta["duration_s"] > 60:
        tags.add("long")

    if meta.get("height", 0) > meta.get("width", 0):
        tags.add("vertical")
    else:
        tags.add("horizontal")

    return sorted(tags)


# --------------------------------------------------------------------------- #
# SQLite index
# --------------------------------------------------------------------------- #

def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    DROP TABLE IF EXISTS clips;
    DROP TABLE IF EXISTS scenes;
    DROP TABLE IF EXISTS tags;
    DROP TABLE IF EXISTS transcript_segments;
    DROP TABLE IF EXISTS transcripts_fts;

    CREATE TABLE clips (
        filename TEXT PRIMARY KEY,
        path TEXT,
        duration_s REAL,
        fps REAL,
        width INTEGER,
        height INTEGER,
        size_bytes INTEGER,
        codec TEXT,
        scanned_at TEXT,
        transcript TEXT,
        language TEXT,
        avg_motion REAL,
        max_motion REAL
    );
    CREATE TABLE scenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        idx INTEGER,
        start_t REAL,
        thumbnail_path TEXT
    );
    CREATE TABLE tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        tag TEXT
    );
    CREATE TABLE transcript_segments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        start_t REAL,
        end_t REAL,
        text TEXT
    );
    CREATE VIRTUAL TABLE transcripts_fts USING fts5(filename UNINDEXED, text);

    CREATE INDEX idx_tags_filename ON tags(filename);
    CREATE INDEX idx_tags_tag      ON tags(tag);
    CREATE INDEX idx_scenes_file   ON scenes(filename);
    CREATE INDEX idx_segs_file     ON transcript_segments(filename);
    """)
    conn.commit()
    return conn


def write_db(conn: sqlite3.Connection, meta: dict, scenes: list[dict],
             tags: list[str], transcript: dict, timeline: list[dict]) -> None:
    motions = [e["motion"] for e in timeline] if timeline else [0.0]
    avg_m = round(sum(motions) / len(motions), 3)
    max_m = round(max(motions), 3) if motions else 0.0

    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO clips
        (filename, path, duration_s, fps, width, height, size_bytes, codec,
         scanned_at, transcript, language, avg_motion, max_motion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (meta["filename"], meta["path"], meta["duration_s"], meta["fps"],
          meta["width"], meta["height"], meta["size_bytes"], meta["codec"],
          datetime.utcnow().isoformat(timespec="seconds") + "Z",
          transcript.get("text", ""), transcript.get("language", "unknown"),
          avg_m, max_m))

    for s in scenes:
        c.execute("""INSERT INTO scenes (filename, idx, start_t, thumbnail_path)
                     VALUES (?, ?, ?, ?)""",
                  (meta["filename"], s["idx"], s["t"], s["path"]))
    for tag in tags:
        c.execute("INSERT INTO tags (filename, tag) VALUES (?, ?)",
                  (meta["filename"], tag))
    for seg in transcript.get("segments", []):
        c.execute("""INSERT INTO transcript_segments
                     (filename, start_t, end_t, text) VALUES (?, ?, ?, ?)""",
                  (meta["filename"], seg["start"], seg["end"], seg["text"]))
    if transcript.get("text"):
        c.execute("INSERT INTO transcripts_fts (filename, text) VALUES (?, ?)",
                  (meta["filename"], transcript["text"]))
    conn.commit()


# --------------------------------------------------------------------------- #
# Per-clip orchestration + report
# --------------------------------------------------------------------------- #

def scan_one(path: Path, model, conn: sqlite3.Connection) -> dict:
    print(f"\n=== {path.name} ===")
    meta = probe_video(path)
    print(f"  meta: {meta['duration_s']:.1f}s  "
          f"{meta['width']}x{meta['height']}  @{meta['fps']:.1f}fps  "
          f"{meta['size_bytes']/1e6:.1f}MB")

    print(f"  motion timeline (2 Hz)...")
    timeline = motion_timeline(path)

    cuts = detect_scenes(timeline)
    print(f"  scenes: {len(cuts)} (cuts at: {', '.join(f'{t:.1f}' for t in cuts)})")

    thumbs = extract_thumbnails(path, cuts, THUMB_DIR, path.stem)

    print(f"  whisper transcribe...")
    transcript = transcribe(path, model)
    if transcript["text"]:
        preview = transcript["text"][:90].replace("\n", " ")
        print(f"  text: {preview!r}{' …' if len(transcript['text']) > 90 else ''}")
    else:
        print(f"  text: (no speech)")

    tags = derive_tags(meta, transcript, timeline)
    print(f"  tags: {', '.join(tags)}")

    out_json = CLIPS_DIR / f"{path.stem}.json"
    out_json.write_text(json.dumps({
        "meta": meta,
        "motion_timeline": timeline,
        "scenes": thumbs,
        "transcript": transcript,
        "tags": tags,
    }, indent=2), encoding="utf-8")

    write_db(conn, meta, thumbs, tags, transcript, timeline)

    return {
        "meta": meta,
        "tags": tags,
        "scene_count": len(thumbs),
        "transcript_text": transcript["text"],
        "avg_motion": (sum(e["motion"] for e in timeline) / len(timeline)) if timeline else 0.0,
    }


def write_report(results: list[dict], out_path: Path) -> None:
    lines = ["# MPC Source Scan Report",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_\n"]
    total = sum(r["meta"]["duration_s"] for r in results)
    lines.append(f"**{len(results)} clips** scanned · "
                 f"**{total:.0f}s ({total/60:.1f} min)** total\n")

    # Tag rollup
    tag_counts: dict[str, int] = {}
    for r in results:
        for t in r["tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    if tag_counts:
        lines.append("## Tag rollup\n")
        for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- `{tag}` — {count}")
        lines.append("")

    lines.append("## Clips\n")
    for r in sorted(results, key=lambda x: x["meta"]["filename"]):
        m = r["meta"]
        lines.append(f"### `{m['filename']}`")
        lines.append(f"- {m['duration_s']:.1f}s · {m['width']}x{m['height']} · "
                     f"{m['fps']:.0f}fps · {m['size_bytes']/1e6:.1f} MB · "
                     f"avg motion {r['avg_motion']:.1f}")
        lines.append(f"- Scenes: {r['scene_count']}")
        lines.append(f"- Tags: `{', '.join(r['tags']) if r['tags'] else '—'}`")
        if r["transcript_text"]:
            preview = r["transcript_text"][:240]
            if len(r["transcript_text"]) > 240:
                preview += " …"
            lines.append(f"- Transcript: _{preview}_")
        else:
            lines.append("- Transcript: _(no speech)_")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--whisper-model", default="small",
                    help="tiny | base | small | medium | large-v3")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--compute-type", default="float16",
                    help="float16 | int8_float16 | int8 (use int8 on cpu)")
    args = ap.parse_args()

    root = Path(args.root)
    videos = sorted(root.glob("*.mp4"))
    print(f"Found {len(videos)} videos in {root}")
    if not videos:
        return

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading whisper '{args.whisper_model}' on {args.device}/{args.compute_type}...")
    model = load_whisper(args.whisper_model, args.device, args.compute_type)

    conn = init_db(DB_PATH)
    results: list[dict] = []
    for v in videos:
        try:
            results.append(scan_one(v, model, conn))
        except Exception as e:
            print(f"  ERROR scanning {v.name}: {type(e).__name__}: {e}")
    conn.close()

    write_report(results, INDEX_DIR / "scan_report.md")
    print(f"\nDone — {len(results)}/{len(videos)} succeeded")
    print(f"  DB:        {DB_PATH}")
    print(f"  per-clip:  {CLIPS_DIR}")
    print(f"  thumbs:    {THUMB_DIR}")
    print(f"  report:    {INDEX_DIR / 'scan_report.md'}")


if __name__ == "__main__":
    main()
