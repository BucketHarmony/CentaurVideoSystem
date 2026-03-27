# cc_flora — Cottagecore Kombucha TikTok Pipeline

**Tag:** `cc_flora` (all files prefixed for multi-CC safety)
**Date:** 2026-03-16
**Agent:** Claude Opus 4.6

---

## What We Built

A cottagecore video production pipeline for Kombucha robot TikTok content. Departure from the original amber-on-dark production aesthetic toward soft pastels, dusty rose, film grain, bokeh particles, and Georgia serif typography.

Three iterations, each building on the last:

| Version | Duration | Frames | Key Addition |
|---------|----------|--------|-------------|
| `cc_flora_ep01_first_light.mp4` | 5s | 150 | Real gimbal motion (not slideshow) |
| `cc_flora_masterpiece.mp4` | 10s | 300 | 4x-UltraSharp GPU upscaling, ambient pad, 3-part TTS, film grain, bokeh |
| `cc_flora_30s.mp4` | 30s | 900 | 3 acts across ticks 0001-0003, 6-part narration, act transitions |

---

## Lessons Learned

### Video Production
1. **Static frames = slideshow.** Crossfading between 3 photos looks dead. Always extract real video frames with actual motion, even if the motion is subtle sensor flicker.
2. **Slow the pans.** The real gimbal pans happen in ~1 second. Slowing to 0.33-0.4x makes them dreamy and watchable. The source has plenty of frames.
3. **Motion scanning works.** Computing frame-to-frame pixel diffs at 0.2-0.3s intervals reliably finds every gimbal pan and drive event in the source video. Key thresholds: >5 = something moved, >15 = pan/drive, >25 = fast pan.
4. **Source video mapping:** tick_0001.mp4 pans at t=25-27, 49-51, 80-81. tick_0002.mp4 drives at t=56-58, 102-104. tick_0003.mp4 turns at t=7.5, drives at t=33, looks UP at t=59.5.

### Upscaling
5. **4x-UltraSharp on RTX 4090 is fast.** ~300 frames (640x480 -> 2560x1920) in ~3 minutes. spandrel makes loading trivial.
6. **Upscale BEFORE color grading.** The model works best on the original pixel data. Grade after.

### Color Grading (Cottagecore)
7. **Red wall desaturation is the single biggest lever.** The source rooms have vivid red walls. Mapping red-dominant pixels toward dusty rose (205, 170, 172) transforms the entire mood.
8. **Shadow lifting + range compression = softness.** +20 shadow lift, 0.78 contrast compression, then 0.70 saturation. That's the cottagecore formula.
9. **Bloom matters.** A 40px gaussian blur of a 1.3x brightened copy, blended at 12%, adds the soft "golden hour" glow.
10. **Creamy vignette, not dark.** Edges fade to cream (250, 245, 239), not black. Night and day difference.

### Audio
11. **Separate TTS calls for timing control.** One long narration has unpredictable pacing. Generating each line separately and placing them at exact timestamps gives perfect sync.
12. **ElevenLabs voice:** `wVOQaU8CfoRJqCWsxoLv` (series voice from series_bible.md). Settings: stability=0.65, similarity=0.72, style=0.1.
13. **Synthesized ambient pad works.** A-minor drone (110/164.81/220 Hz) + shimmer harmonics + sparse music-box chime hits. Butterworth low-pass at 3kHz for warmth. Add Bb3 tension in Act 3.

### Pipeline
14. **Tag your files.** Multiple CC instances run concurrently. All files prefixed `cc_flora_*` to avoid collisions.
15. **Unicode in print statements breaks on Windows cp1252.** Don't use arrows or fancy characters in print(). Crashed the first masterpiece render at the finish line.
16. **moviepy 2.x API:** Use `ImageSequenceClip(list_of_arrays, fps=30)`, `clip.with_start()`, `CompositeAudioClip()`, `clip.subclipped()`. The 2.x API changed a lot from 1.x.

---

## File Inventory

### Scripts (`E:/AI/CVS/scripts/`)

| File | Purpose |
|------|---------|
| `cc_flora_ep01_first_light_script.html` | Visual script + source material side-by-side (open in browser) |
| `cc_flora_ep01_first_light.py` | 5-second producer (real motion, no upscaling) |
| `cc_flora_masterpiece.py` | 10-second producer (4x upscale, ambient pad, TTS) |
| `cc_flora_30s.py` | 30-second producer (3 acts, 3 ticks, full pipeline) |

### ComfyUI Workflows (`E:/AI/CVS/ComfyUI/custom_nodes/comfyui-kombucha-pipeline/`)

| File | Purpose |
|------|---------|
| `workflow_kombucha_tiktok.json` | **Main production workflow.** 9-node pipeline: ParseTickLog -> VHS_LoadVideo -> 4x-UltraSharp upscale -> ImageScale 1080x810 -> VerticalFrameComposite 1080x1920 -> TextOverlay -> ElevenLabsTTS -> VHS_VideoCombine. Amber palette, Consolas font, dark background. Produced 46 episodes on 2026-03-15. |
| `workflow_pilot_episode.json` | Pilot/test variant of the tiktok workflow. |
| `cc_flora_workflow_backup_v1.json` | Snapshot of `workflow_kombucha_tiktok.json` taken before cc_flora work began. |

### Output (`E:/AI/CVS/ComfyUI/output/`)

| File | Details |
|------|---------|
| `cc_flora_ep01_first_light.mp4` | 5s, 1080x1920, real motion, TTS narration |
| `cc_flora_masterpiece.mp4` | 10s, 1080x1920, 4x upscaled, ambient + TTS |
| `cc_flora_30s.mp4` | 30s, 1080x1920, 3 acts, 900 frames (rendering) |
| `cc_flora_ep01_frames/` | 150 PNGs from 5s version |
| `cc_flora_masterpiece_frames/` | 300 PNGs from 10s version |
| `cc_flora_30s_frames/` | 900 PNGs from 30s version |
| `cc_flora_*_audio.mp3` | Mixed audio tracks |
| `cc_flora_*_pad.wav` | Synthesized ambient pads |
| `cc_flora_*_tts_*.mp3` | Individual ElevenLabs narration clips |

---

## ComfyUI Workflow Documentation

### workflow_kombucha_tiktok.json (9 nodes)

The original batch production workflow. Designed for submitting via ComfyUI API (`POST /prompt`).

```
Node 1: ParseTickLog
  Input:  log_path (e.g. "E:/AI/Kombucha/ticks/tick_0053.md")
  Output: title, mood, monologue, tick_number, goal, intent

Node 2: VHS_LoadVideoPath
  Input:  video path (e.g. "E:/AI/Kombucha/video/web/tick_0053.mp4")
  Config: force_rate=30, frame_load_cap=90
  Output: IMAGE frames, frame_count, audio, video_info

Node 3: UpscaleModelLoader
  Model:  4x-UltraSharp.pth
  Output: UPSCALE_MODEL

Node 4: ImageUpscaleWithModel
  Input:  upscale_model (from 3), image (from 2)
  Output: IMAGE (640x480 -> 2560x1920)

Node 5: ImageScale
  Input:  image (from 4)
  Config: lanczos, 1080x810
  Output: IMAGE

Node 6: VerticalFrameComposite
  Input:  images (from 5)
  Config: 1080x1920, bg=#0a0a0f, y_offset=0
  Output: images, top_zone_height, bottom_zone_start

Node 7: TextOverlay
  Input:  images (from 6), title/subtitle/body (from 1)
  Config: title=#e8a830 64px, subtitle=#d4922a 32px, body=#e8dcc8 28px
  Font:   C:/Windows/Fonts/consola.ttf
  Output: IMAGE

Node 8: ElevenLabsTTS
  Input:  text=monologue (from 1)
  Config: voice=pNInz6obpgDQGcFmaJgB, model=eleven_multilingual_v2
  Output: AUDIO

Node 9: VHS_VideoCombine
  Input:  images (from 7), audio (from 8)
  Config: frame_rate=30, format=h264-mp4, prefix="kombucha_tiktok"
  Output: Filenames
```

**Link topology:**
```
ParseTickLog --(title)--> TextOverlay
             --(mood)---> TextOverlay
             --(mono)---> TextOverlay
             --(mono)---> ElevenLabsTTS

VHS_LoadVideo --> ImageUpscaleWithModel --> ImageScale --> VerticalFrameComposite --> TextOverlay --> VHS_VideoCombine
UpscaleModelLoader --> ImageUpscaleWithModel
ElevenLabsTTS --> VHS_VideoCombine
```

### Custom Nodes (`nodes.py`)

| Node | Purpose |
|------|---------|
| `ParseTickLog` | Parse tick markdown, extract fields, pick best quote |
| `ElevenLabsTTS` | Direct ElevenLabs API call, returns AUDIO tensor |
| `MotionClip` | Detect motion segments, remove static frames |
| `VerticalFrameComposite` | Blurred video fill background + sharp center |
| `TextOverlay` | TikTok safe-zone-aware text with outline |
| `PadToAudio` | Stretch video frames to match audio duration |

---

## Cottagecore Style Guide

### Palette
| Name | Hex | RGB | Use |
|------|-----|-----|-----|
| Rose | #e8b4b8 | (232, 180, 184) | Titles, accents |
| Sage | #b5c5a3 | (181, 197, 163) | Section headers |
| Cream | #faf5ef | (250, 245, 239) | Text, vignette target |
| Linen | #f0e6d8 | (240, 230, 216) | Pill backgrounds, blurred bg blend |
| Ink | #4a4340 | (74, 67, 64) | Body text |
| Muted | #8a7e76 | (138, 126, 118) | Subtitles, metadata |
| Dusty Rose | #d2a5aa | (210, 165, 170) | Title card |

### Typography
- Titles/narration: Georgia (serif, warm)
- Lowercase preferred: "kombucha" not "KOMBUCHA"
- No monospace on-screen

### Post-Processing Stack (per frame)
1. cottagecore_grade() — red desaturation, shadow lift, range compression, warmth
2. soft_bloom() — 40px gaussian, 12% additive
3. make_vertical_canvas() — blurred linen background, sharp center, vignette
4. draw_particles() — 50 bokeh dust motes, warm palette
5. film_grain() — midtone-weighted gaussian noise, intensity=6
6. add_text_overlays() — tick pill, narration, title card with timing
