"""MPC source scanner — batch driver over a source folder.

Per-clip work delegates to `cvs_lib.scanner` (see that module for
schema + Phase 0 findings). This script handles batch orchestration:
SQLite indexing (clips/scenes/tags/transcripts FTS5), per-clip JSON
persistence, thumbnail dir, and the human-readable scan_report.md.

Outputs land in E:/AI/CVS/mpc/index/ (clips/, thumbnails/, clips.db,
scan_report.md).

Defaults reflect Phase 0 findings: large-v3 + VAD off + vocab prompt
auto-resolved from mpc/scanner_prompts.json. To use the legacy small
model on a clip set with no domain prompt, pass --whisper-model small
--vad.

Usage:
    python E:/AI/CVS/scripts/mpc_scan_sources.py
    python E:/AI/CVS/scripts/mpc_scan_sources.py --root "E:/AI/CVS/raw/MPC/Other Event"
    python E:/AI/CVS/scripts/mpc_scan_sources.py --whisper-model medium --device cuda
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cvs_lib import scanner

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_ROOT = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
INDEX_DIR = Path("E:/AI/CVS/mpc/index")
THUMB_DIR = INDEX_DIR / "thumbnails"
CLIPS_DIR = INDEX_DIR / "clips"
DB_PATH = INDEX_DIR / "clips.db"


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
        whisper_model TEXT,
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


def write_db(conn: sqlite3.Connection, record: dict) -> None:
    """Persist one scanner.scan_clip record to the SQLite index."""
    meta = record["meta"]
    timeline = record["motion_timeline"]
    scenes = record["scenes"]
    tags = record["tags"]
    transcript = record["transcript"]

    motions = [e["motion"] for e in timeline] if timeline else [0.0]
    avg_m = round(sum(motions) / len(motions), 3)
    max_m = round(max(motions), 3) if motions else 0.0

    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO clips
        (filename, path, duration_s, fps, width, height, size_bytes, codec,
         scanned_at, transcript, language, whisper_model,
         avg_motion, max_motion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (meta["filename"], meta["path"], meta["duration_s"], meta["fps"],
          meta["width"], meta["height"], meta["size_bytes"], meta["codec"],
          datetime.utcnow().isoformat(timespec="seconds") + "Z",
          transcript.get("text", ""), transcript.get("language", "unknown"),
          transcript.get("model", "unknown"),
          avg_m, max_m))

    for s in scenes:
        c.execute("""INSERT INTO scenes (filename, idx, start_t, thumbnail_path)
                     VALUES (?, ?, ?, ?)""",
                  (meta["filename"], s["idx"], s["t"], s.get("path", "")))
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

def scan_one(path: Path, model, conn: sqlite3.Connection,
             vad: bool, initial_prompt: str | None) -> dict:
    print(f"\n=== {path.name} ===")
    record = scanner.scan_clip(
        path, model,
        thumbnails_dir=THUMB_DIR,
        initial_prompt=initial_prompt,
        vad=vad,
        verbose=True,
    )
    meta = record["meta"]
    text = record["transcript"]["text"]
    print(f"  meta: {meta['duration_s']:.1f}s "
          f"{meta['width']}x{meta['height']} @{meta['fps']:.1f}fps "
          f"{meta['size_bytes']/1e6:.1f}MB")
    if text:
        preview = text[:90].replace("\n", " ")
        print(f"  text: {preview!r}{' …' if len(text) > 90 else ''}")
    else:
        print(f"  text: (no speech)")
    print(f"  tags: {', '.join(record['tags'])}")

    out_json = CLIPS_DIR / f"{path.stem}.json"
    out_json.write_text(json.dumps(record, indent=2), encoding="utf-8")

    write_db(conn, record)

    timeline = record["motion_timeline"]
    return {
        "meta": meta,
        "tags": record["tags"],
        "scene_count": len(record["scenes"]),
        "transcript_text": text,
        "avg_motion": (sum(e["motion"] for e in timeline) / len(timeline))
                       if timeline else 0.0,
    }


def write_report(results: list[dict], out_path: Path) -> None:
    lines = ["# MPC Source Scan Report",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_\n"]
    total = sum(r["meta"]["duration_s"] for r in results)
    lines.append(f"**{len(results)} clips** scanned · "
                 f"**{total:.0f}s ({total/60:.1f} min)** total\n")

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
    ap.add_argument("--whisper-model", default="large-v3",
                    help="tiny | base | small | medium | large-v3 (default: large-v3)")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--compute-type", default="float16",
                    help="float16 | int8_float16 | int8 (use int8 on cpu)")
    ap.add_argument("--vad", action="store_true",
                    help="Enable VAD filter (default off — VAD drops sung content)")
    ap.add_argument("--prompt",
                    help="Explicit initial_prompt override. If absent, "
                         "auto-resolved per-clip from "
                         "mpc/scanner_prompts.json by source folder.")
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
    model = scanner.load_whisper(args.whisper_model, args.device, args.compute_type)

    conn = init_db(DB_PATH)
    results: list[dict] = []
    for v in videos:
        try:
            results.append(scan_one(v, model, conn,
                                    vad=args.vad, initial_prompt=args.prompt))
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
