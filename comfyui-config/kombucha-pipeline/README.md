# Kombucha Pipeline — ComfyUI Custom Nodes

TikTok-native vertical video production pipeline for the Kombucha robot exploration project.

Takes horizontal 640×480 fisheye rover footage + markdown tick logs → produces narrated, upscaled, vertical 1080×1920 TikTok videos.

## Nodes

### ParseTickLog
Reads a Kombucha tick markdown file. Extracts structured fields for the pipeline.

**Inputs:** `log_path` (STRING)
**Outputs:** `title`, `mood`, `monologue` (full text for TTS), `best_quote` (1-2 best sentences for display), `tick_number`, `goal`, `intent`

Best quote selection scores sentences by metaphor/simile patterns, figurative language, length sweet spot (30-120 chars), and penalizes technical data. Searches all narrative sections (Monologue, Thought, Observation, Perception, Orientation, Decision).

### ElevenLabsTTS
Direct ElevenLabs API call. No Comfy Org proxy needed.

**Inputs:** `text` (forceInput), `api_key`, `voice_id`, `model_id`, `stability`, `similarity_boost`
**Outputs:** `AUDIO`

### MotionClip
Detects motion via frame-to-frame pixel difference. Removes static frames, keeps only movement segments. Typically removes 60-75% of rover footage.

**Inputs:** `images`, `sensitivity` (1.5 = median×1.5 threshold), `min_segment_frames`, `merge_gap_frames`, `pad_frames`, `max_output_frames`
**Outputs:** `images` (motion frames only), `frame_count`

### VerticalFrameComposite
Places horizontal video into a 1080×1920 vertical canvas with **blurred video fill** behind the sharp original. No black bars.

**Inputs:** `images`, `canvas_width`, `canvas_height`, `blur_radius` (25), `blur_darken` (0.4 = 40% brightness), `video_y_offset` (-60 pushes video up slightly)
**Outputs:** `images`, `top_zone_height`, `bottom_zone_start`

The blurred background is the same video scaled to fill the full canvas, gaussian blurred, and darkened. The sharp video is composited on top, centered.

### TextOverlay
Burns title, mood badge, and hook quote onto frames. Respects TikTok safe zones. Uses bold sans-serif fonts for readability.

**Inputs:** `images`, `title_text`/`subtitle_text`/`body_text` (all forceInput), positioning (y), font sizes, colors, wrapping config
**Outputs:** `images`

**Safe zones enforced:**
- Top 150px avoided (app tabs)
- Bottom 480px avoided (caption bar)
- Right 120px avoided (engagement icons)
- Left 44px avoided (profile info)

**Fonts:** Impact for title, Arial Bold for badge and quote.

### PadToAudio
Ensures video duration covers the full audio narration.

**Strategy:**
1. If video is already long enough → pass through
2. If slowing to `min_speed` (0.8x) covers the gap → evenly duplicate frames for smooth slow-mo
3. If slow-mo isn't enough → slow to 0.8x AND add held frames split `pad_start_ratio` (40%) at start, remainder (60%) at end

**Inputs:** `images`, `audio`, `frame_rate`, `buffer_seconds` (1.0), `min_speed` (0.8), `pad_start_ratio` (0.4)
**Outputs:** `images`, `audio`

## Template Layout

```
┌────────────────────────────┐
│     (blurred video fill)    │  darkened 40%, gaussian blur r=25
│                              │
│         TICK 189             │  y=160, Impact 96px, white
│        [RESOLVED]            │  y=268, Arial Bold 40px, amber badge
│                              │
│  ┌──────────────────────┐   │
│  │                      │   │  y≈495
│  │   SHARP VIDEO        │   │  1080×810, 4x-UltraSharp upscaled
│  │   (completely clear)  │   │  no text overlays on video
│  │                      │   │
│  └──────────────────────┘   │  y≈1305
│                              │
│   "I am a moon to this       │  y=1400, Arial Bold 40px, white
│    toilet paper's planet."   │  max 4 lines × 30 chars
│                              │
└────────────────────────────┘
         1080 × 1920
```

## Pipeline Flow

```
ParseTickLog ──→ title, mood ──→ TextOverlay
     │                                ↑
     ├──→ monologue ──→ ElevenLabsTTS ──→ PadToAudio ──→ VHS_VideoCombine
     │                                        ↑
     └──→ best_quote ──→ TextOverlay          │
                              ↑               │
VHS_LoadVideo ──→ MotionClip ──→ 4x-UltraSharp ──→ ImageScale
                  ──→ VerticalFrameComposite ──→ TextOverlay ──→ PadToAudio
```

## API Submission

The pipeline runs headlessly via the ComfyUI `/prompt` API. No browser needed.

```python
prompt = {
    '1':  ParseTickLog(log_path="E:/AI/Kombucha/ticks/tick_0189.md"),
    '2':  VHS_LoadVideoPath(video="E:/AI/Kombucha/video/web/tick_0189.mp4", force_rate=10),
    '10': MotionClip(images=[2,0], sensitivity=1.5),
    '3':  UpscaleModelLoader(model_name="4x-UltraSharp.pth"),
    '4':  ImageUpscaleWithModel(upscale_model=[3,0], image=[10,0]),
    '5':  ImageScale(image=[4,0], upscale_method="lanczos", width=1080, height=810),
    '6':  VerticalFrameComposite(images=[5,0], blur_radius=25, blur_darken=0.4, video_y_offset=-60),
    '7':  TextOverlay(images=[6,0], title=[1,0], subtitle=[1,1], body=[1,3]),
    '8':  ElevenLabsTTS(text=[1,2], voice_id="wVOQaU8CfoRJqCWsxoLv"),
    '11': PadToAudio(images=[7,0], audio=[8,0], min_speed=0.8, pad_start_ratio=0.4),
    '9':  VHS_VideoCombine(images=[11,0], audio=[11,1], frame_rate=10),
}
```

## Batch Production

Queue multiple ticks and stitch with ffmpeg:
```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy compiled.mp4
```

## Dependencies

- ComfyUI v0.17.0+
- comfyui-videohelpersuite (VHS_LoadVideoPath, VHS_VideoCombine)
- 4x-UltraSharp.pth upscale model
- ElevenLabs API key
- Windows fonts: impact.ttf, arialbd.ttf

## Configuration

Models are shared from an existing ComfyUI install via `extra_model_paths.yaml`:
```yaml
old_comfyui:
    base_path: E:/AI/ComfyUI/
    upscale_models: models/upscale_models/
```
