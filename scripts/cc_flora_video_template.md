# cc_flora Video Template

**Format:** 1080x1920 vertical (TikTok/Reels/Shorts/Bluesky)
**FPS:** 30
**Codec:** H.264 Main profile, yuv420p, 3Mbps, faststart
**Audio:** AAC, 192kbps, 44.1kHz

---

## Template Structure

The cc_flora template is a modular act-based structure. Each act is 10 seconds (300 frames) built from one tick's video. Acts can be stacked for longer videos.

### Single Act (10 seconds)

```
TIME        FRAMES    BEAT                    SOURCE
──────────────────────────────────────────────────────────────
0.0–1.5s    0–44      Fade from black         Static hold from source video
1.5–3.2s    45–95     Motion segment 1        Real gimbal pan / drive (slowed 0.4x)
3.2–4.5s    96–134    Hold                    Static frames post-motion
4.5–6.5s    135–194   Motion segment 2        Real gimbal pan / drive (slowed 0.35x)
6.5–7.5s    195–224   Motion segment 3        Return pan (slowed 0.4x)
7.5–10.0s   225–299   Hold + zoom             Static with 1.5–2.5% slow zoom
```

### Multi-Act (30 seconds = 3 acts)

```
ACT 1 (0–10s)     Establishment    Survey the space. Where am I?
  transition       Soft linen blink (0.4s blend to/from linen color)
ACT 2 (10–20s)    Action           First movement. Something happens.
  transition       Soft linen blink
ACT 3 (20–30s)    Consequence      Discovery. Limit. Realization.
  fade out         1.0s fade to warm black at end
```

---

## Frame Sourcing

### How to find motion in source video

Scan the tick MP4 frame-by-frame diffs:

```python
for t in np.arange(0, clip.duration, 0.3):
    frame = clip.get_frame(t)
    diff = np.abs(frame - prev).mean()
    # diff > 5  = something moved
    # diff > 15 = gimbal pan or drive
    # diff > 25 = fast pan
```

### Frame allocation per beat

| Beat type | Source duration | Output frames | Effective speed |
|-----------|---------------|---------------|-----------------|
| Fade in | 3–5s of static | 45 frames | ~2x (samples across range for subtle life) |
| Pan/drive | 1–2s of motion | 45–60 frames | 0.33–0.5x (dreamy slow-mo) |
| Hold | 5–10s of static | 39–75 frames | ~3-5x (samples for sensor flicker) |
| Zoom hold | 5–6s of static | 45–75 frames | ~3x + 1.5-2.5% digital zoom |

### Source time mapping

Each output frame maps to a `(video_file, timestamp)` pair:

```python
def sample_times(src_start, src_end, num_frames):
    """Evenly space N sample points across a source time range."""
    return [src_start + (src_end - src_start) * i / max(num_frames - 1, 1)
            for i in range(num_frames)]
```

---

## Processing Stack (per frame, in order)

### 1. Upscale (GPU)

```
Input:  640x480 (raw fisheye)
Model:  4x-UltraSharp.pth via spandrel
Output: 2560x1920
Device: CUDA (RTX 4090, ~0.6s per frame)
```

### 2. Cottagecore Color Grade

```python
# Red desaturation (the biggest lever)
# Red-dominant pixels (r > 80, r > g*1.2, r > b*1.2)
# Shift toward dusty rose: target (205, 170, 172), strength 0.45-0.55

# Wood tone warming
# Orange/brown pixels -> honey tones: target (220, 195, _), strength 0.10-0.15

# Shadow lift: +20
# Dynamic range compression: 0.78 (midpoint 128)
# Warm shift: R*1.03, G*1.01, B*0.93
# Saturation: 0.70
# Brightness: 1.08
```

### 3. Soft Bloom

```
Method: 1.3x brightness -> 40px gaussian blur -> 12% additive blend
Effect: Golden hour glow on highlights
```

### 4. Vertical Canvas Composite

```
Background: Source frame scaled to fill 1080x1920, 35px gaussian blur,
            blended 70% toward linen (240, 230, 216)
Foreground: Source frame scaled to 1080px wide, centered vertically
            with -80px offset (slightly above center)
Vignette:   Creamy (edges fade to cream, NOT black)
            Strength 0.28, starts at 35% radius, power curve 1.8
```

### 5. Bokeh Dust Motes

```
Count:     50 particles
Size:      2.0–6.0px radius, 3 concentric rings (soft bokeh)
Movement:  dx: -0.12 to 0.12, dy: -0.25 to -0.04 (float upward)
Alpha:     0.08–0.35 base, sinusoidal pulse (freq 0.3–1.5 Hz)
Colors:    (255,252,245), (255,245,230), (250,240,220), (255,230,215)
```

### 6. Film Grain

```
Type:      Gaussian noise, intensity 6.0
Weighting: Stronger in midtones (luminance ~0.5), weaker in shadows/highlights
           mask = clip(1.0 - 2.0 * abs(luminance - 0.5), 0.3, 1.0)
```

### 7. Transitions

```
Fade from black: ease_out(t / 1.5s), from warm black (15, 13, 11)
Act transitions: 0.4s blend toward linen, dims to 60% at boundary
Fade to black:   ease_out over final 1.0s
Zoom:            1.5–2.5% over hold beats, ease_out curve
```

---

## Text Overlay System

### Tick Pill (top of frame)

```
Position:  Center horizontal, y=200
Font:      Georgia 20px
Style:     Rounded rectangle pill, linen background (160 alpha)
Text:      "tick 0001" in muted gray
Timing:    Appears at 1.2s, updates at act boundaries
Fade:      ease_out over 0.8s
```

### Narration Lines (lower third)

```
Position:  Center horizontal, y=1350 baseline, 45px line spacing
Font:      Georgia Italic 34px
Color:     Ink (74, 67, 64) at 230 alpha, shadow offset (1,1) at 50 alpha
Backing:   Cream rounded rectangle (250,245,239) at 100 alpha
Timing:    Each line fades in over 0.6s (ease_out)
           Holds for 3.5s
           Fades out over 1.0s
           Multiple lines stack vertically
Max width: Clamped to canvas - 140px margins
```

### Title Card (end)

```
Position:  Center horizontal, y=1560
Title:     "kombucha" — Georgia 48px, dusty rose (210, 165, 170)
Subtitle:  "first light" — Georgia Italic 24px, muted gray, y=title+56
Timing:    Title at 28.0s, subtitle at 28.3s
Fade:      ease_out over 0.8s (title), 0.6s (subtitle)
```

### Ease Function

```python
def ease_out(x):
    """Cubic ease-out: fast start, gentle landing."""
    return 1 - (1 - x) ** 3
```

---

## Audio Template

### Ambient Pad (synthesized)

```
Base drone:  A2 (110 Hz) * 0.05 + E3 (164.81) * 0.035 + A3 (220) * 0.025
Shimmer:     A4 (440) * 0.010 * LFO1 + C#5 (554.37) * 0.007 * LFO2
             E5 (659.25) * 0.005 * LFO1
LFOs:        0.12 Hz and 0.18 Hz sine waves
Tension:     Bb3 (233.08 Hz) fades in during Act 3 (t > 20s)
Chimes:      12 music-box hits (880, 1108.73, 1318.51, 932.33 Hz)
             Envelope: exp(-t * 2.0) * clip(t * 10, 0, 1)
             Placed every 2-3 seconds, A-minor key (Bb in Act 3)
Filter:      Butterworth 4th order low-pass at 3000 Hz
Fade:        2.5s fade in, 2.5s fade out
Normalize:   Peak at 0.22
Format:      WAV, 44100 Hz, 16-bit mono
```

### Narration (ElevenLabs TTS)

```
Voice:       wVOQaU8CfoRJqCWsxoLv (series voice — dry, measured)
Model:       eleven_multilingual_v2
Stability:   0.65
Similarity:  0.72
Style:       0.1

Delivery:    One API call per line (separate files for timing control)
Placement:   Each clip placed at exact start time via CompositeAudioClip
Mixing:      Narration sits on top of ambient pad (no ducking needed,
             pad is quiet enough)
```

### Narration Timing Guide

| Line | Start time | Act | Dramatic purpose |
|------|-----------|-----|-----------------|
| 1 | 2.5s | 1 | First awareness |
| 2 | 5.0s | 1 | Sensory detail |
| 3 | 8.0s | 1 | The joke / hook |
| 4 | 14.5s | 2 | Learning / discovery |
| 5 | 23.5s | 3 | The obstacle |
| 6 | 25.5s | 3 | The limit / punchline |

**Rule:** Never place narration during motion segments. Narration lands on holds. Let the visual pans/drives breathe without text or voice competing.

---

## Adapting the Template

### To produce a new episode

1. **Choose 1-3 ticks** with a narrative arc (discovery, obstacle, resolution)
2. **Scan each tick video** for motion peaks (frame diffs > 5)
3. **Map source times** to output beats using `sample_times()`
4. **Write narration lines** — pull from tick Monologue/Thought/Observation, distill to 1 sentence each
5. **Set narration start times** — place on hold beats, never during motion
6. **Adjust chime times** in ambient pad to complement narration gaps
7. **Run the pipeline** — upscale, grade, composite, render

### To change duration

- **5s:** 1 act, 150 frames, 1-2 narration lines, 2-3 chimes
- **10s:** 1 act, 300 frames, 3 narration lines, 5 chimes
- **15s:** 1.5 acts, 450 frames, 4 narration lines, 7 chimes
- **30s:** 3 acts, 900 frames, 6 narration lines, 12 chimes
- **60s:** 6 acts, 1800 frames, 10-12 narration lines, 20+ chimes

### To change aesthetic (swap the grade)

The entire visual identity lives in these functions:
- `cottagecore_grade()` — color mapping
- `soft_bloom()` — glow character
- `creamy_vignette()` — edge treatment
- `film_grain()` — texture
- `make_vertical_canvas()` — background blend target color

Swap these for a different look (noir, synthwave, documentary) without touching the frame sourcing or audio pipeline.
