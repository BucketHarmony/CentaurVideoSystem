---
name: ComfyUI output structure post-cleanup
description: Established output directory structure after 2026-03-17 cleanup, including what lives where and which patterns are deletable
type: project
---

After the 2026-03-17 cleanup (34 GB -> 1.3 GB), the output directory uses this structure:

output/
  finals/cc_flora/     — All cc_flora episode mp4s (ep01-10 main + bsky variants, 30s pilot, masterpiece)
  finals/kombucha/     — Finalized episode mp4s (ep11-13 main + bsky)
  finals/deforum/      — deforum_flora_FINAL.mp4, deforum_flora_FINAL_norm.mp4
  finals/dream/        — dream_tick0013.mp4, dream_audio.mp3
  projects/cc_flora/audio/    — Per-episode tts/pad/chime/mixed mp3+wav (81 files)
  projects/cc_flora/stills/   — Test frames, text test PNGs
  projects/kombucha/per-tick-audio/  — All kombucha_tick*-audio.mp4 (61 files, v1/v2/v3)
  projects/kombucha/audio/    — Ep11-13 tts/pad/mixed + soundtrack.wav
  projects/kombucha/stills/   — Depth maps, tiltshift, cosymotes, style-test PNGs
  projects/kombucha/proto/    — Compiled multi-tick, pilot, style-variant mp4s
  projects/deforum/audio/     — deforum_flora_pad.wav
  projects/dream/audio/       — Ambient pad, TTS clips, keyframe stills
  misc/               — Style-comparison PNGs, 8bit experiments, SD test renders
  archive/deforum_cosmic/     — Unknown project, 7 mp4s, archived not deleted
  archive/kombucha_old/       — Early v1/v2 style experiments, 10 mp4s

**Why:** Flat output/ was 34 GB dominated by 13 frame-sequence dirs (32 GB).
**How to apply:** Future cleanups should recognize this structure as the baseline.
  New episodes will drop into output/ root again — move finals to finals/<project>/,
  audio to projects/<project>/audio/, frame dirs are always deletable once mp4 confirmed.
