# CVS Demo

A self-contained showcase of the Centaur Video System's production pipeline. Generates a 15-second branded vertical video with synthesized audio, animated text, and cinematic post-processing — no API keys, no ComfyUI, no external services required.

## Quick Run

```bash
pip install Pillow numpy scipy
python demo/run_demo.py
```

Output lands in `demo/output/cvs_demo.mp4`.

## What It Produces

A 1080x1920 vertical video (TikTok/Reels format) with three scenes:

| Time | Scene | Techniques Used |
|------|-------|----------------|
| 0-5s | **Animated Title Card** | Timed text reveals, accent line animation, brand colors, fade-in |
| 5-10s | **Test Card Showcase** | Ken Burns zoom, blurred background fill, cottagecore color grading, soft bloom |
| 10-15s | **Design Principles** | Staggered text reveals, accent dots, URL fade-in |

Plus these effects applied to every frame:
- **Film grain** (gaussian noise at 2% intensity)
- **Cream vignette** (warm-tinted radial falloff)
- **Narration overlays** (timed text with semi-transparent pill backgrounds)
- **Crossfade transitions** (15-frame blend between scenes)

And a fully synthesized stereo soundtrack:
- **A-minor ambient drone** (A2, C3, E3, A3 additive synthesis)
- **Shimmer layer** (A4, C5, E5 with LFO modulation at 0.12/0.18/0.07 Hz)
- **Music-box chimes** (A5, C6, E6 with exponential decay)
- **Binaural stereo panning** (slow L/R sweeps + 2Hz beat for spatial depth)
- **Mood coloring** (F4 "curious" tone)
- **3-second fade in/out envelope**
- **Butterworth low-pass filter at 3kHz**

## How It Works

### Pipeline Architecture

```
Brand Kit (colors, identity)
    |
    v
Scene Generators (3 scenes x 150 frames each)
    |
    +--> Title Card Generator ----+
    |    (text animation, lines)  |
    |                             |
    +--> Showcase Generator ------+--> Crossfade Blend
    |    (Ken Burns, blur fill)   |         |
    |                             |         v
    +--> Principles Generator ----+    Post-Processing
         (staggered reveals)           (grain, vignette,
                                        narration overlay)
                                            |
                                            v
Audio Synthesis (numpy)              Frame Sequence (PNG)
    |                                       |
    +--- A-minor drone                      |
    +--- Shimmer + LFO                      |
    +--- Chimes                             |
    +--- Binaural panning                   |
    +--- Low-pass filter                    |
    +--- Envelope                           |
    |                                       |
    v                                       v
  WAV file                             ffmpeg encode
    |                                       |
    +----------------> mux <----------------+
                        |
                        v
                   cvs_demo.mp4
                (H.264 + AAC, yuv420p)
```

### Step-by-Step Breakdown

#### 1. Brand Configuration

Colors are loaded from the demo brand kit (`demo/brand/demo_brand.json`):

```python
PRIMARY   = "#DC143C"   # Crimson — accent lines, dots
SECONDARY = "#1a1a2e"   # Dark navy — backgrounds
ACCENT    = "#f0e68c"   # Khaki gold — subtitles, narration text
```

This mirrors how CVS workflows load a brand kit and wire colors to every downstream node. In a real CVS workflow, these come from the Load Brand Kit node.

#### 2. Frame Generation (450 frames)

Each of the three scenes generates 150 frames (5 seconds at 30fps):

**Scene 1 — Title Card:**
- Dark navy background
- Crimson accent lines animate outward from center (`line_width = WIDTH * 0.6 * min(progress * 3, 1.0)`)
- "CENTAUR VIDEO SYSTEM" fades in with alpha ramp
- Tagline reveals with delayed timing

**Scene 2 — Showcase:**
- Test card image loaded and animated with Ken Burns (1.0x to 1.2x zoom + pan)
- Blurred background fill: same image scaled to canvas, gaussian blur r=25, darkened to 35%
- Sharp video composited on center
- Cottagecore color grading applied:
  - Red desaturation on pixels where R > 0.5 and dominates G/B
  - Warm shadow lift (+0.03 red, +0.01 green on dark pixels)
  - Range compression: `pixel * 0.92 + 0.04`
- Soft bloom: gaussian blur blended at 20%

**Scene 3 — Principles:**
- Three text blocks revealed sequentially with staggered timing
- Each has: crimson dot indicator, white heading, gold body text
- GitHub URL fades in at bottom after 60% progress

#### 3. Crossfade Transitions

At scene boundaries, the first 15 frames of the new scene are alpha-blended with the last frame of the previous scene:

```python
blend = local_idx / overlap  # 0.0 -> 1.0 over 15 frames
img = Image.blend(prev_frame, new_frame, blend)
```

#### 4. Global Post-Processing

Applied to every frame after scene generation:

**Film Grain:**
```python
noise = np.random.normal(0, 0.02, shape)  # 2% intensity
pixel = clip(pixel + noise, 0, 1)
```

**Vignette:**
```python
dist = sqrt((x - cx)^2 + (y - cy)^2) / max_dist
mask = 1.0 - clip(dist * 0.35, 0, 0.6)
# Cream tint in darkened edges (warm R=0.95, G=0.90, B=0.82)
```

**Narration Overlay:**
- Each line has a start time and auto-calculated end time
- Text fades in over 0.25s, fades out over 0.25s
- Rendered onto semi-transparent rounded rectangle ("pill") background
- Positioned in TikTok safe zone (above bottom 560px)

#### 5. Audio Synthesis

All audio generated in numpy at 44100 Hz:

**Drone (4 voices):**
```
A2 (110 Hz)   amplitude 0.050
C3 (130.81 Hz) amplitude 0.030
E3 (164.81 Hz) amplitude 0.035
A3 (220 Hz)   amplitude 0.025
```

**Shimmer (3 voices with LFOs):**
```
A4 (440 Hz)    amp 0.012  LFO: 0.12 Hz
C5 (523.25 Hz) amp 0.008  LFO: 0.18 Hz (phase +1.0)
E5 (659.25 Hz) amp 0.006  LFO: 0.07 Hz (phase +2.5)
```

**Chimes (6 strikes at timed intervals):**
```
t=0.1s  A5 (880 Hz)     t=6.0s  E6 (1318 Hz)
t=3.5s  C6 (1046.5 Hz)  t=8.5s  A5 (880 Hz)
t=11.5s E6 (1318 Hz)    t=14.0s C6 (1046.5 Hz)

Each chime: sine + overtone (2x freq), exponential decay (e^{-2.5t})
Panned alternately: 30%, 50%, 70% right
```

**Stereo Processing:**
- Drone panned with slow sweep (0.05 Hz, ~20s cycle)
- Binaural beat: right channel gets A2+2Hz for perceived spatial depth
- Butterworth 4th-order low-pass at 3000 Hz
- Envelope: 3s linear fade in, 3s fade out

#### 6. Video Encoding

```bash
ffmpeg -framerate 30 -i frame_%05d.png -i soundtrack.wav \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart -crf 18 \
  -shortest output.mp4
```

- **H.264** for universal playback
- **yuv420p** for platform compatibility
- **faststart** for streaming/web playback
- **CRF 18** for high quality

## Adapting for Your Own Projects

### Change the Brand

Edit `demo/brand/demo_brand.json` or modify the constants in `run_demo.py`:

```python
PRIMARY = "#your_color"
SECONDARY = "#your_bg"
ACCENT = "#your_accent"
```

### Change the Content

Modify the `NARRATION` list to change timed text:

```python
NARRATION = [
    (1.0, "Your first line"),
    (4.0, "Second line appears here"),
    (8.0, "And so on."),
]
```

Edit the scene generator functions to change visuals. Each returns a PIL Image for a single frame.

### Change the Audio

Modify `generate_soundtrack()` to:
- **Change key:** Replace the frequency constants (A2, C3, etc.) with your desired chord
- **Change mood:** Adjust the mood tone frequency
- **Change chime timing:** Edit the `chime_times` list
- **Change tempo:** Adjust LFO rates (higher = faster shimmer movement)

### Use Your Own Images

Replace the test card with any image:

```python
test_card = Image.open("path/to/your/image.png")
```

The Ken Burns effect and blurred background fill adapt to any input resolution.

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| Pillow | Frame rendering, text, compositing | Yes |
| numpy | Audio synthesis, color math | Yes |
| scipy | Butterworth low-pass filter | Optional (skipped if missing) |
| ffmpeg | Video encoding (CLI) | Yes |

## Files

```
demo/
├── run_demo.py               # Main demo script (standalone)
├── README.md                 # This file
├── assets/
│   ├── test_card.py          # Test card generator
│   ├── test_card_720p.png    # 1280x720 test card
│   ├── test_card_1080p.png   # 1920x1080 test card
│   └── sample_video.mp4      # 5-second sample clip
├── brand/
│   └── demo_brand.json       # Sample brand kit
└── output/                   # Generated by run_demo.py
    ├── cvs_demo.mp4          # The demo video
    └── demo_soundtrack.wav   # The synthesized audio
```

## Connection to CVS

This demo implements the same patterns used in CVS production workflows, but as a standalone Python script instead of a ComfyUI node graph:

| Demo Function | CVS Node Equivalent |
|---------------|-------------------|
| `cottagecore_grade()` | Apply Brand Colors node |
| `soft_bloom()` | Composition pipeline effect |
| `ken_burns()` | Ken Burns Effect node |
| `film_grain()` | Composition pipeline effect |
| `vignette()` | Composition pipeline effect |
| `add_narration_overlay()` | Text Overlay / Lower Third node |
| `generate_soundtrack()` | Audio Engine (audio_engine.py) |
| `make_scene_*()` | Title Card / Compose Layers nodes |
| Crossfade between scenes | Crossfade Transition node |
| Brand color constants | Load Brand Kit node |
| ffmpeg encode | Save Video node |

In a full CVS workflow, these would be individual nodes on the ComfyUI canvas, wired together visually. The human designs the graph; the AI executes it. This demo shows what the execution produces.
