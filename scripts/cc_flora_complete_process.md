# cc_flora: Complete Production Process

**Series:** Kombucha Cottagecore TikTok
**Tag:** `cc_flora`
**Agent:** Claude Opus 4.6
**Platform:** Windows 11, RTX 4090, Python 3.x
**Published to:** Bluesky @comradeclaw.bsky.social

---

## Table of Contents

1. [Overview](#overview)
2. [Episode Catalog](#episode-catalog)
3. [End-to-End Workflow](#end-to-end-workflow)
4. [Step 1: Pick Ticks & Scan for Motion](#step-1-pick-ticks--scan-for-motion)
5. [Step 2: Read Tick Logs & Write Narration](#step-2-read-tick-logs--write-narration)
6. [Step 3: Write the Episode Script](#step-3-write-the-episode-script)
7. [Step 4: Visual Pipeline](#step-4-visual-pipeline)
8. [Step 5: Audio Pipeline](#step-5-audio-pipeline)
9. [Step 6: Frame Compositing & Assembly](#step-6-frame-compositing--assembly)
10. [Step 7: Encode for Distribution](#step-7-encode-for-distribution)
11. [Step 8: Publish to Bluesky](#step-8-publish-to-bluesky)
12. [Style Guide](#style-guide)
13. [Audio Design Reference](#audio-design-reference)
14. [Lessons Learned](#lessons-learned)
15. [File Locations](#file-locations)

---

## Overview

cc_flora is a cottagecore video production pipeline for the Kombucha robot series. It transforms raw robot POV video into 30-second vertical (1080x1920) episodes with:

- Real video frames (never stills) extracted from tick source videos
- Optional 4x GPU upscaling via spandrel + 4x-UltraSharp model
- Cottagecore color grading (red desaturation, shadow lift, warmth)
- Soft bloom, creamy vignette, bokeh dust particles, film grain
- Georgia serif typography with tick labels, mood pills, and narration panels
- Synthesized ambient pad (A minor drone + chimes) generated in numpy
- ElevenLabs TTS narration with automatic overlap prevention
- Bluesky-optimized H.264 encoding with loudness normalization

Each episode covers 2-3 "ticks" (autonomous robot exploration cycles), structured as 3 acts of 10 seconds each.

---

## Episode Catalog

| Ep | Title | Ticks | Bluesky |
|----|-------|-------|---------|
| 01 | First Light | 0001-0003 | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mou6rsz2g) |
| 02 | The Bigger Room | 0004,0006,0007,0008 | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mq7ty3v2z) |
| 03 | Moon | 0010,0012,0013 | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mrfzhvq2m) |
| 04 | Carried Home | 0014-0018 | posted |
| 05 | Same Frame | 0019-0024 | posted |
| 06 | Three Centimeters | 0032-0035 | posted |
| 07 | Ping-Pong | 0036,0037 | posted |
| 08 | The Threshold | 0038,0039 | posted |
| 09 | The Hallway | 0041,0042,0044 | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mhbsfofgvs2z) |
| 10 | The Patience of Rooms | 0046,0048,0049 | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mhbyb7dfbp2q) |

**Canon folder:** `E:/AI/CVS/ComfyUI/output/cc_flora_canon/`

---

## End-to-End Workflow

```
1. Pick 2-3 ticks from the narrative arc
2. Motion-scan source videos (frame diffs at 0.5s intervals)
3. Fine-scan motion peaks (0.2s intervals)
4. Read tick logs for monologue/mood material
5. Write 6 narration lines + 3 moods
6. Map 900 frames across 3 acts (300 frames = 10s each)
7. Design episode-specific audio harmonics + chime placement
8. Run the script (fast ~3min, upscale ~20min)
9. Loudness normalize: ffmpeg loudnorm -14dB LUFS
10. Upload to Bluesky via curl + atproto SDK
11. Copy to canon folder
12. Update production guide
```

---

## Step 1: Pick Ticks & Scan for Motion

### Coarse scan (0.5s intervals)

```python
from moviepy import VideoFileClip
import numpy as np

clip = VideoFileClip("E:/AI/Kombucha/video/web/tick_XXXX.mp4")
prev = None
for t in np.arange(0, clip.duration, 0.5):
    frame = clip.get_frame(t)
    if prev is not None:
        diff = np.abs(frame.astype(float) - prev.astype(float)).mean()
        if diff > 4:
            print(f"t={t:.1f}s d={diff:.0f}")
    prev = frame
```

### Motion thresholds

| Diff value | Meaning |
|-----------|---------|
| >5 | Something moved (sensor flicker, light change) |
| >15 | Gimbal pan or drive event |
| >25 | Fast pan or large movement |

### Fine scan around peaks (0.2s intervals)

Run the same loop with `np.arange(peak-2, peak+3, 0.2)` and threshold >2 to find exact motion boundaries. These boundaries become your source map segments.

### Tick selection criteria

- Need **motion** (turns, drives, gimbal pans) — static ticks make dead video
- Need **compelling monologue** — the voice is the soul of the episode
- Need **narrative arc** across 3 acts — beginning/middle/end emotional shape
- Skip ticks that are purely diagnostic, transitional, or duplicate an adjacent tick's content

---

## Step 2: Read Tick Logs & Write Narration

### Source

Tick logs live at `E:/AI/Kombucha/ticks/tick_XXXX.md`

### Best narration sources (in order)

1. **Monologue** — distilled voice, already poetic, first choice
2. **Thought** — reasoning and personality, good for internal moments
3. **Observation** — factual but often has scale comedy

### The mood field

Each tick log ends with a `## Mood` section containing a single word. This goes directly into the `MOODS` config array.

### Writing the 6 narration lines

- 6 lines total, roughly 2 per act
- `start` times spaced ~4-5s apart
- Keep lines **under 60 characters** (= under 4s of TTS)
- Final line MUST finish by ~29.8s
- Pull the best phrases from tick monologues, adapt/compress as needed
- The voice is dry, measured, slightly weary — match that register

---

## Step 3: Write the Episode Script

### Template

Copy the most recent episode script (e.g. `cc_flora_ep10_the_patience_of_rooms.py`). Change:

1. **`NARRATION`** — 6 dicts with `text` and `start` keys
2. **`MOODS`** — 3 dicts with `mood`, `start`, `end` keys (one per act)
3. **Tick labels** — in `add_text_overlays()`, update the `if t < 10` / `elif t < 20` / `else` for tick numbers
4. **Title card** — update the `sub = "episode title"` string
5. **`build_source_map()`** — map 900 frames across 3 acts (see Frame Mapping below)
6. **Audio** — adjust episode-specific harmonics and chime placement in `generate_ambient_pad()`
7. **File names** — update all `cc_flora_epXX_` prefixes
8. **Battery display** — update percentage from tick log data

### Frame mapping structure

Each act = 300 frames = 10 seconds at 30fps.

```
ACT N (Xf total):
  Static hold    (90-120f): sample_times(src_start, src_end, N)
  Motion slowed  (75-120f): sample_times(motion_start, motion_end, N)  # 0.3-0.5x
  Post-motion    (60-90f):  sample_times(after_motion, hold_end, N)
```

The `sample_times(start, end, n)` function linearly distributes `n` timestamps between `start` and `end` in the source video. Slowing motion = more output frames from fewer source seconds.

**Key rule:** Total frames across all segments must equal exactly 900.

---

## Step 4: Visual Pipeline

Each frame passes through this stack in order:

### 1. Extract source frame

```python
frame = Image.fromarray(clip.get_frame(src_timestamp))
```

### 2. GPU upscale (optional, `--upscale` flag)

```python
# spandrel + 4x-UltraSharp.pth on CUDA
# 640x480 -> 2560x1920
model = spandrel.ModelLoader().load_from_file("4x-UltraSharp.pth")
model = model.to("cuda").eval()
```

**Always upscale BEFORE color grading.** The model works best on original pixel data.

### 3. Cottagecore color grade

```python
def cottagecore_grade(img):
    # Red wall desaturation -> dusty rose (205, 170, 172)
    # Orange desaturation -> warm neutral
    # Range compression: 128 + (arr - 128) * 0.92
    # Warm shift: R*1.03, G*1.01, B*0.91
    # Saturation: 0.75
    # Brightness: 0.92
    # Contrast: 1.12
```

The **red desaturation is the single biggest lever** — the source rooms have vivid red walls. Mapping red-dominant pixels toward dusty rose transforms the entire mood.

### 4. Soft bloom

```python
def soft_bloom(img, strength=0.05):
    # 1.3x brightness -> 40px gaussian blur -> 5% additive blend
```

### 5. Vertical canvas (1080x1920)

```python
def make_vertical_canvas(frame):
    # Sharp center image at native width
    # Blurred + warm-tinted background fill
    # 60% source blur + 40% warm linen (175, 162, 148)
    # Center offset: -80px (slightly above center)
    # Creamy vignette overlay
```

### 6. Creamy vignette

```python
def creamy_vignette(img, strength=0.55):
    # Radial gradient from center
    # Edges fade toward shadow (55, 48, 42)
    # NOT dark vignette — warm shadow
```

### 7. Bokeh dust particles

```python
def draw_particles(img, particles, t):
    # 50 warm-toned circles
    # Float upward with drift
    # Pulsing alpha via sine LFO
    # 3-ring glow per particle
```

### 8. Film grain

```python
def film_grain(img, intensity=5.0):
    # Gaussian noise weighted to midtones
    # Stronger in mid-luminance, weaker in shadows/highlights
```

### 9. Compositing effects

Applied per-frame based on timeline position:

| Effect | When | Purpose |
|--------|------|---------|
| Fade in | t < 1.0s | 0.4->1.0 blend from warm dark |
| Act transitions | t=10.0, t=20.0 | 0.4s linen flash |
| Ken Burns zoom | Varies per episode | 1-1.5% push-in for tension |
| Impact shake | At collision timestamps | 5-frame random jitter with decay |
| Fade to black | t > 29.0s | ease_out to warm black |

### 10. Text overlays

```python
def add_text_overlays(img, t, narration_times):
    # Tick pill:     Georgia 40px, centered, linen rounded rect
    # Mood pill:     Georgia Italic 60px, dusty rose, below tick
    # Battery:       Georgia 30px, bottom-left, timed appearance
    # Narration:     Georgia Italic 36px, centered panel at y=1320
    # Title card:    Georgia 48px dusty rose + 26px italic muted, at t>=28s
```

All text elements have timed fade-in/fade-out using `ease_out()` cubic easing.

Narration text syncs to `narration_times` — the same timing array that drives audio placement.

---

## Step 5: Audio Pipeline

### Ambient pad (numpy synthesis)

All audio is generated in Python with numpy + scipy. No samples, no DAW, no external music files.

#### Base drone (A minor)

| Voice | Freq | Amplitude | Role |
|-------|------|-----------|------|
| A2 | 110 Hz | 0.05 | Foundation |
| E3 | 164.81 Hz | 0.035 | Fifth |
| A3 | 220 Hz | 0.025 | Octave |
| A4 | 440 Hz | 0.01 x LFO | Shimmer |
| C#5 | 554.37 Hz | 0.007 x LFO | Color |
| E5 | 659.25 Hz | 0.005 x LFO | Air |

LFOs: slow sine waves at 0.12Hz and 0.18Hz make the shimmer breathe.

#### Episode-specific harmonics

Crossfaded with numpy envelope multiplies:

| Harmonic | Freq | Use |
|----------|------|-----|
| Hopeful E4 | 329.63 Hz | Discovery, wonder, new territory |
| Tense Bb3 | 233.08 Hz | Frustration, drift, obstacle |
| Bright B4 | 493.88 Hz | Milestone, achievement |
| Dissonant Bb4 | 466.16 Hz | Cable catch, collision cluster |

Each uses `np.clip()` ramps for smooth 1-3s fade-in/out.

#### Chimes

Music-box hits at A5 (880Hz), C#6 (1108.73Hz), E6 (1318.51Hz):
- Sharp attack: `np.clip(env_t * 10, 0, 1)`
- Exponential decay: `np.exp(-env_t * 2.0)`
- Amplitude: 0.022
- Placed at specific timestamps, roughly every 2.5-3s
- **Omitting chimes is a key dramatic tool** (silence = absence, tension, awe)

#### Impact sounds

- **Thuds:** Filtered noise burst (0.15s decay) + low A1 sine (55Hz, 0.3s decay)
- **Shutter clicks:** 80ms noise bursts
- **Glitch noise:** 200ms white noise with fast exponential decay

All generated with `np.random.RandomState(seed).randn()` for reproducibility.

#### Master envelope

```python
# Start at 30% (Bluesky crushes silent openings)
pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1)
# Fade out over 2.5s
pad *= np.clip((duration - t) / 2.5, 0, 1)
# Butterworth 4th order lowpass at 3kHz
sos = scipy.signal.butter(4, 3000, 'low', fs=sr, output='sos')
pad = scipy.signal.sosfilt(sos, pad)
# Normalize to 0.22 peak
pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.22
```

Output: 16-bit mono WAV at 44100Hz.

### TTS narration (ElevenLabs)

```python
requests.post(
    f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
    json={
        "text": line_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.72,
            "style": 0.15
        }
    },
    headers={"xi-api-key": API_KEY, "Accept": "audio/mpeg"}
)
```

- Voice ID: `wVOQaU8CfoRJqCWsxoLv` (dry, measured, slightly weary)
- 6 separate API calls, one per line
- Each clip's actual duration measured after generation

### Overlap prevention

```python
GAP = 0.3  # minimum seconds between lines
for each line:
    start = max(desired_start, previous_end + GAP)
    if start + duration > 30.0:
        start = pull_back(start)  # pull earlier
```

Returns `narration_times` list of `(start, end)` tuples. Both audio compositing and text overlays read from this same array.

### Audio compositing

```python
final = CompositeAudioClip([pad_audio] + narration_clips).subclipped(0, 30.0)
final.write_audiofile("ep_audio.mp3", fps=44100, codec="libmp3lame")
```

---

## Step 6: Frame Compositing & Assembly

### Render loop

```python
for i in range(900):
    t = i / 30.0
    canvas = make_vertical_canvas(raw_frames[i])
    # Apply fade-in, act transitions, zoom, shake, fade-out
    canvas = draw_particles(canvas, particles, t)
    canvas = film_grain(canvas, intensity=5.0)
    canvas = add_text_overlays(canvas, t, narration_times)
    canvas.save(FRAMES_DIR / f"frame_{i:04d}.png")
    output_frames.append(np.array(canvas))
```

### Assembly

```python
from moviepy import ImageSequenceClip, AudioFileClip
video = ImageSequenceClip(list(frames), fps=30)
video = video.with_audio(AudioFileClip(str(audio_path)))
video.write_videofile(str(raw_path), fps=30, codec="libx264",
                      audio_codec="aac", preset="medium", bitrate="3000k")
```

---

## Step 7: Encode for Distribution

### Bluesky-optimized re-encode

```bash
ffmpeg -y -i raw.mp4 \
  -c:v libx264 -profile:v main -level 4.0 \
  -pix_fmt yuv420p -r 30 \
  -b:v 3M -maxrate 4M -bufsize 6M \
  -c:a aac -b:a 192k -ar 44100 \
  -movflags +faststart \
  output.mp4
```

### Loudness normalization

```bash
ffmpeg -y -i output.mp4 \
  -c:v copy \
  -af "loudnorm=I=-14:TP=-1:LRA=11" \
  -c:a aac -b:a 192k \
  output_bsky.mp4
```

### Key encoding facts

- `yuv420p` is **mandatory** (4:4:4 breaks iOS playback)
- `faststart` puts moov atom first for streaming
- Bluesky re-encodes everything server-side to HLS
- First 9 seconds stream at ~320p before quality ramps
- Videos autoplay **muted** on mobile
- Quiet audio gets crushed — always normalize to -14dB LUFS

---

## Step 8: Publish to Bluesky

### Authentication

```python
from atproto import Client, models

client = Client()
profile = client.login(handle, password)
did = profile.did

service_auth = client.com.atproto.server.get_service_auth(
    models.ComAtprotoServerGetServiceAuth.Params(
        aud="did:web:jellybaby.us-east.host.bsky.network",  # PDS DID, not video service
        lxm="com.atproto.repo.uploadBlob",
    )
)
token = service_auth.token
```

### Video upload (via curl — Python SSL breaks with video.bsky.app)

```python
result = subprocess.run([
    "curl", "-s", "--max-time", "300", "-X", "POST",
    f"https://video.bsky.app/xrpc/app.bsky.video.uploadVideo?did={did}&name=video.mp4",
    "-H", f"Authorization: Bearer {token}",
    "-H", "Content-Type: video/mp4",
    "--data-binary", f"@{video_path}",
], capture_output=True, text=True, timeout=600)

job = json.loads(result.stdout)
job_id = job["jobId"]
```

### Poll until complete

```python
for attempt in range(60):
    time.sleep(3)
    status = curl_get(f"app.bsky.video.getJobStatus?jobId={job_id}")
    if status["jobStatus"]["state"] == "JOB_STATE_COMPLETED":
        blob_ref = status["jobStatus"]["blob"]
        break
```

### Create post

```python
embed = models.AppBskyEmbedVideo.Main(
    video=blob_ref,
    alt="Alt text description",
)
post = client.send_post(text=post_text, embed=embed)
```

### Post guidelines

- Text limit: 300 characters
- Hashtags: `#kombucha #robotics #ai #cottagecore`
- Alt text: describe what happens in the video
- Credentials in `E:/AI/CVS/.env`

---

## Style Guide

### Cottagecore Palette

| Name | RGB | Hex | Use |
|------|-----|-----|-----|
| Rose | (232, 180, 184) | #e8b4b8 | Accents |
| Cream | (250, 245, 239) | #faf5ef | Vignette target, text |
| Linen | (240, 230, 216) | #f0e6d8 | Pill bg, canvas blend |
| Ink | (74, 67, 64) | #4a4340 | Body text |
| Muted | (138, 126, 118) | #8a7e76 | Subtitles |
| Dusty Rose | (210, 165, 170) | #d2a5aa | Title, mood text |
| Warm Black | (15, 13, 11) | #0f0d0b | Fade target |
| Pill BG | (245, 238, 228) | #f5eee4 | Rounded rect fills |

### Typography

- **Titles/narration:** Georgia (serif, warm)
- **Lowercase preferred:** "kombucha" not "KOMBUCHA"
- **No monospace on-screen**
- Tick pill: Georgia 40px
- Mood: Georgia Italic 60px, dusty rose
- Narration: Georgia Italic 36px, ink
- Title card: Georgia 48px dusty rose + Georgia Italic 26px muted
- Battery: Georgia 30px, muted warm

### Timing conventions

- Fade in: 1.0s from warm dark
- Act transitions: 0.4s linen flash at t=10.0 and t=20.0
- Title card: appears at t=28.0, subtitle at t=28.3
- Fade to black: ease_out over final 1.0s
- Narration fade-in: 0.6s, fade-out: 0.8s after show duration

---

## Audio Design Reference

### Episode-specific audio choices

| Episode | Harmonics | Chime Strategy | Special Sounds |
|---------|-----------|---------------|----------------|
| 04 Carried Home | E4 hope -> death envelope | No chimes during blackout | Battery death silence |
| 05 Same Frame | E4 restore | No chimes during freeze | Shutter clicks, glitch burst |
| 06 Three Centimeters | E4 survey, Bb3 tension, Bb4 dissonance | Standard | Cable catch cluster |
| 07 Ping-Pong | Bb3 frustration, E4 resolution | Standard | Impact thuds at collisions |
| 08 The Threshold | Varies | Standard | - |
| 09 The Hallway | E4 act 2, Bb3 gentle act 3 | Chimes stop at t=22 | - |
| 10 The Patience of Rooms | Bb3 act 1, E4 acts 2-3, B4 shimmer | Chimes stop at t=25.5 | - |

### Design principles

- **Silence is dramatic.** Omitting chimes signals absence, tension, or awe.
- **Harmonics crossfade, never cut.** 1-3s numpy envelope ramps.
- **Start at 30% volume.** Bluesky crushes silent openings.
- **Chime at t=0.1s always.** Never start silent — the first chime signals "this has audio."
- **Lowpass everything.** 3kHz Butterworth keeps the mix warm and prevents harshness.

---

## Lessons Learned

### Video
1. **Static frames = slideshow.** Always use real video frames with actual motion.
2. **Slow the pans to 0.33-0.5x.** Real gimbal pans happen in ~1s. Slowing makes them dreamy.
3. **Motion scanning works.** Frame diffs at 0.2-0.5s intervals reliably find every event.

### Upscaling
4. **4x-UltraSharp on RTX 4090 is fast.** ~900 frames in ~10 minutes with spandrel.
5. **Upscale BEFORE grading.** Model works best on original pixels.

### Color
6. **Red wall desaturation is the biggest lever.** Transforms the entire mood.
7. **Shadow lift + range compression = softness.** That's the cottagecore formula.
8. **Bloom matters.** 40px blur of brightened copy at 5% = golden hour glow.

### Audio
9. **Separate TTS calls per line.** One long narration has unpredictable pacing.
10. **Synthesized pad works.** No need for music samples or a DAW.
11. **Loudnorm to -14dB LUFS.** Bluesky crushes quiet audio.

### Pipeline
12. **Tag all files with `cc_flora_`** when multiple CC instances run concurrently.
13. **Unicode in print() crashes on Windows cp1252.** Don't use fancy characters.
14. **moviepy 2.x API changed a lot.** Use `with_start()`, `subclipped()`, `CompositeAudioClip`.
15. **Upload video via curl, not Python requests.** Python SSL breaks with video.bsky.app.

---

## File Locations

| What | Where |
|------|-------|
| Production scripts | `E:/AI/CVS/scripts/cc_flora_ep*.py` |
| Production guide | `E:/AI/CVS/scripts/cc_flora_production_guide.md` |
| README | `E:/AI/CVS/scripts/cc_flora_README.md` |
| This document | `E:/AI/CVS/scripts/cc_flora_complete_process.md` |
| Canon videos | `E:/AI/CVS/ComfyUI/output/cc_flora_canon/` |
| All output | `E:/AI/CVS/ComfyUI/output/cc_flora_*.mp4` |
| Frame dumps | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_frames/` |
| TTS clips | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_tts_*.mp3` |
| Ambient pads | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_pad.wav` |
| Mixed audio | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_audio.mp3` |
| Source tick logs | `E:/AI/Kombucha/ticks/tick_XXXX.md` |
| Source video | `E:/AI/Kombucha/video/web/tick_XXXX.mp4` |
| Series bible | `E:/AI/Kombucha/series_bible.md` |
| Series narrative | `E:/AI/Kombucha/series_narrative.md` |
| Upscale model | `E:/AI/ComfyUI/models/upscale_models/4x-UltraSharp.pth` |
| Credentials | `E:/AI/CVS/.env` |

---

## Series Bible Reference

| Act | Series Eps | Ticks | Theme |
|-----|-----------|-------|-------|
| I | 1-5 | 1-10 | First light, learning to move |
| II | 6-13 | 11-26 | The room, the desk, the cable |
| III | 14-22 | 27-37 | Slow approach, millimeter increments |
| IV | 23-28 | 38-43 | Pelican case wars, the cat, "Roomba with a philosophy degree" |
| V | 29-35 | 44-53 | Bathroom breakthrough, cable-pivot, "KOMBUCHA IS IN THE BATHROOM" |

Full narrative: `E:/AI/Kombucha/series_narrative.md`
Robot skills: `E:/AI/Kombucha/skills.md`
Media mission: `E:/AI/Kombucha/docs/media_mission.md`
