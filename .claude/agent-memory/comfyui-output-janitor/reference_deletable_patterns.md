---
name: Confirmed deletable output patterns
description: File patterns that are always safe to delete in this ComfyUI setup, verified by 2026-03-17 cleanup
type: reference
---

These patterns are confirmed waste in this pipeline:

1. **`<project>_ep##_frames/` directories** — 900-frame upscaled PNG sequences, ~3 GB each.
   Delete as soon as a confirmed final mp4 exists for that episode in finals/.

2. **`deforum_flora_synced_N.mp4`** — Progressive build series (0 through N).
   Each file = previous + 1 frame. Only the highest-numbered or FINAL.mp4 matters.
   Delete all intermediate ones.

3. **`kombucha_tick###_00001.mp4`** (no -audio suffix) — Silent render, superseded by -audio version.
   Always delete the silent version; keep kombucha_tick###_00001-audio.mp4.
   Same pattern applies to v2_tick* and v3_tick* variants.

4. **`kombucha_bsky_tick####.mp4`** — Per-tick Bluesky preview crops.
   Delete once the finalized `kombucha_ep##_bsky.mp4` exists.

5. **`deforum_frame_#####_.png`** — Intermediate deforum frames. Delete once FINAL mp4 exists.

6. **`*_frames/` directories in general** — Any directory matching this pattern is an
   intermediate frame sequence dump. Confirm a final mp4 exists before deleting.

Patterns to ARCHIVE instead of delete (unknown project status):
- `deforum_cosmic_*.mp4` — unknown experiment, no final, archive/deforum_cosmic/
- Early style-test tick renders (`kombucha_clean_*, _cosyfocus_*, _ethereal_*, _rackfocus_*`)
