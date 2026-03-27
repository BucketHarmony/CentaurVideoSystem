# cc_flora Production Guide

**Tag:** `cc_flora`
**Agent:** Claude Opus 4.6
**Date:** 2026-03-16

Pick up here for Episode 4+.

---

## Episodes Completed

| Ep | Title | Ticks | File | Bluesky |
|----|-------|-------|------|---------|
| 01 | First Light | 0001-0003 | `cc_flora_30s.mp4` | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mou6rsz2g) |
| 02 | The Bigger Room | 0004,0006,0007,0008 | `cc_flora_ep02_bigger_room.mp4` | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mq7ty3v2z) |
| 03 | Moon | 0010,0012,0013 | `cc_flora_ep03_moon.mp4` | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mh6mrfzhvq2m) |
| 04 | Carried Home | 0014-0018 | `cc_flora_ep04_carried_home.mp4` | posted |
| 05 | Same Frame | 0019-0024 | `cc_flora_ep05_same_frame.mp4` | posted |
| 06 | Three Centimeters | 0032-0035 | `cc_flora_ep06_three_centimeters.mp4` | posted |
| 07 | Ping-Pong | 0036,0037 | `cc_flora_ep07_ping_pong.mp4` | posted |
| 08 | The Threshold | 0038,0039 | `cc_flora_ep08_the_threshold.mp4` | posted |
| 09 | The Hallway | 0041,0042,0044 | `cc_flora_ep09_the_hallway.mp4` | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mhbsfofgvs2z) |
| 10 | The Patience of Rooms | 0046,0048,0049 | `cc_flora_ep10_the_patience_of_rooms.mp4` | [post](https://bsky.app/profile/comradeclaw.bsky.social/post/3mhbyb7dfbp2q) |

**Ticks used so far:** 1-4, 6-8, 10, 12-24, 32-39, 41, 42, 44, 46, 48, 49
**Ticks skipped:** 5 (cornered), 9 (stationary), 11 (partial), 25-31 (TBD), 40 (under desk cleanup), 43 (face detect), 45 (similar to 48), 47 (transitional)
**Next available:** tick 0050 onward

---

## How to Produce an Episode

### 1. Pick ticks and find motion

Scan candidate tick videos for motion peaks:

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

Thresholds: `>5` = something moved, `>15` = gimbal pan or drive, `>25` = fast pan.

For fine detail, scan at 0.2s intervals around peaks.

### 2. Read the tick logs

Source: `E:/AI/Kombucha/ticks/tick_XXXX.md`

Pull from these sections for narration:
- **Monologue** (best — distilled voice)
- **Thought** (good — reasoning and personality)
- **Observation** (factual but has scale comedy)

The mood field at the bottom of each tick log goes in the MOODS config.

### 3. Write the script

Copy `cc_flora_ep03_moon.py` as the template. Change:

1. **NARRATION** — 6 lines, `start` times spaced ~4s apart. Keep lines short (under 60 chars = under 4s TTS). The final line MUST finish by 29.8s.
2. **MOODS** — one per act, from tick logs
3. **Tick labels** — in `add_text_overlays()`, update the if/elif for tick numbers
4. **Title card** — update the subtitle text at the bottom of `add_text_overlays()`
5. **`build_source_map()`** — map 900 frames across 3 acts:
   - Each act = 300 frames = 10 seconds
   - Motion segments: slow to 0.33-0.5x (30-75 output frames from 1-3s of source)
   - Static holds: sample across 5-15s of source (for subtle sensor flicker)
   - Always use `sample_times(src_start, src_end, num_frames)`
6. **Audio chime times** — optional, adjust in `generate_ambient_pad()`
7. **File names** — update all `cc_flora_ep0X_` prefixes

### 4. Run it

```bash
cd E:/AI/CVS/scripts
python cc_flora_ep04_TITLE.py          # fast, ~3 min
python cc_flora_ep04_TITLE.py --upscale # premium, ~20 min (4x-UltraSharp GPU)
```

### 5. Boost audio and publish

```bash
# Loudness normalize for Bluesky
ffmpeg -y -i cc_flora_ep04_TITLE.mp4 -c:v copy -af "loudnorm=I=-14:TP=-1:LRA=11" -c:a aac -b:a 192k cc_flora_ep04_TITLE_loud.mp4
```

Publish via the Bluesky script pattern (see below).

---

## Audio Overlap Prevention

The `build_audio()` function measures each TTS clip's actual duration after generation, then resolves timing:

- Minimum gap between lines: 0.3s
- If a line would overlap the previous, its start time is pushed later
- If a line would run past DURATION (30s), its start time is pulled back
- The resolved `narration_times` list `[(start, end), ...]` is passed to `add_text_overlays()` so text appears in sync with audio

**Rule of thumb:** Keep narration lines under 60 characters. Longer lines = longer TTS = more likely to collide or run past 30s.

---

## Bluesky Publishing

### Auth combo that works
- `aud`: `did:web:jellybaby.us-east.host.bsky.network` (the PDS DID, NOT the video service)
- `lxm`: `com.atproto.repo.uploadBlob`
- Upload via `curl` (Python's httpx/requests have SSL issues with video.bsky.app)

### Upload flow
```python
from atproto import Client, models

client = Client()
profile = client.login(handle, password)
did = profile.did

# Get service auth
service_auth = client.com.atproto.server.get_service_auth(
    models.ComAtprotoServerGetServiceAuth.Params(
        aud="did:web:jellybaby.us-east.host.bsky.network",
        lxm="com.atproto.repo.uploadBlob",
    )
)
token = service_auth.token

# Upload via curl (bypasses Python SSL issues)
result = subprocess.run([
    "curl", "-s", "--max-time", "300", "-X", "POST",
    f"https://video.bsky.app/xrpc/app.bsky.video.uploadVideo?did={did}&name=video.mp4",
    "-H", f"Authorization: Bearer {token}",
    "-H", "Content-Type: video/mp4",
    "--data-binary", f"@{video_path}",
], capture_output=True, text=True, timeout=600)

job = json.loads(result.stdout)
# Poll job_id until JOB_STATE_COMPLETED, get blob_ref
# Then create_record with app.bsky.embed.video embed
```

### Post text limit: 300 characters
### Best hashtags: `#kombucha #robotics #ai #cottagecore`

---

## Bluesky Video Optimization

Export settings (ffmpeg):
```
-c:v libx264 -profile:v main -level 4.0
-pix_fmt yuv420p -r 30
-b:v 3M -maxrate 4M -bufsize 6M
-c:a aac -b:a 192k -ar 44100
-movflags +faststart
```

Then loudness normalize:
```
-af "loudnorm=I=-14:TP=-1:LRA=11"
```

Key facts:
- Videos autoplay **muted** on mobile
- First 9 seconds stream at **~320p** before quality ramps up
- All videos are re-encoded server-side (HLS)
- `yuv420p` is **mandatory** (4:4:4 breaks iOS playback)
- `faststart` puts moov atom first for streaming
- Quiet audio gets crushed — normalize to -14dB LUFS

---

## Visual Pipeline (per frame)

1. Extract real video frame at source timestamp
2. (Optional) 4x-UltraSharp GPU upscale via spandrel
3. `cottagecore_grade()` — red desaturation to dusty rose, shadow lift +20, range compression 0.78, warm shift, saturation 0.70, brightness 1.08
4. `soft_bloom()` — 1.3x brightness, 40px blur, 12% additive
5. `make_vertical_canvas()` — 1080x1920, blurred linen background, sharp center, creamy vignette
6. `draw_particles()` — 50 bokeh dust motes, warm palette, float upward
7. `film_grain()` — midtone-weighted gaussian noise, intensity 6.0
8. `add_text_overlays()` — tick pill (Georgia 36px), mood (Georgia Italic 56px dusty rose), narration (Georgia Italic 34px), title card

---

## Frame Source Mapping Template

Each act = 10 seconds = 300 frames. Structure:

```
0.0-1.0s   (30f):  Soft fade in from linen, static hold
1.0-4.0s   (90f):  Main motion segment (slowed 0.4-0.5x)
4.0-6.0s   (60f):  Hold post-motion
6.0-8.0s   (60f):  Secondary motion or pan
8.0-10.0s  (60f):  Hold with gentle 1.5% zoom
```

Act transitions: 0.4s blend toward linen at t=10.0 and t=20.0
Fade to black: ease_out over final 1.0s

---

## Ambient Pad

Key: A minor (110, 164.81, 220 Hz base drone)
Shimmer: 440, 554.37, 659.25 Hz with slow LFOs
Chimes: 880, 1108.73, 1318.51 Hz music-box hits, one every ~2.5s
Tension: add Bb (233.08 Hz) or other color tones per episode mood
Filter: Butterworth 4th order LP at 3kHz
Start at 30% volume (Bluesky crushes silent openings)
Chime at t=0.1s always (never start silent)

---

## ElevenLabs TTS

- Voice: `wVOQaU8CfoRJqCWsxoLv` (series voice — dry, measured, slightly weary)
- Model: `eleven_multilingual_v2`
- Settings: stability=0.65, similarity_boost=0.72, style=0.1
- API key in `E:/AI/CVS/.env`

---

## File Locations

| What | Where |
|------|-------|
| Production scripts | `E:/AI/CVS/scripts/cc_flora_ep*.py` |
| HTML script (Ep01) | `E:/AI/CVS/scripts/cc_flora_ep01_first_light_script.html` |
| Output videos | `E:/AI/CVS/ComfyUI/output/cc_flora_*.mp4` |
| Output frames | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_frames/` |
| TTS clips | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_tts_*.mp3` |
| Ambient pads | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_pad.wav` |
| Mixed audio | `E:/AI/CVS/ComfyUI/output/cc_flora_ep*_audio.mp3` |
| Source tick logs | `E:/AI/Kombucha/ticks/tick_XXXX.md` |
| Source video | `E:/AI/Kombucha/video/web/tick_XXXX.mp4` |
| Source frames | `E:/AI/Kombucha/media/raw/tick_XXXX_frame_XX.jpg` |
| Upscale model | `E:/AI/ComfyUI/models/upscale_models/4x-UltraSharp.pth` |
| Env/credentials | `E:/AI/CVS/.env` |
| Template docs | `E:/AI/CVS/scripts/cc_flora_video_template.md` |
| Full README | `E:/AI/CVS/scripts/cc_flora_README.md` |
| This guide | `E:/AI/CVS/scripts/cc_flora_production_guide.md` |

---

## Series Bible Reference

Full narrative structure: `E:/AI/Kombucha/series_bible.md`
Narrative summary: `E:/AI/Kombucha/series_narrative.md`
Robot skills/calibration: `E:/AI/Kombucha/skills.md`
Media mission: `E:/AI/Kombucha/docs/media_mission.md`

**Act III of the series (Ep 14-22, ticks 27-37)** is the slow approach — millimeter increments toward the bathroom. Good material for a montage episode.

**Act IV (Ep 23-28, ticks 38-43)** has the Pelican case wars, the black cat, and "I have the spatial reasoning of a Roomba with a philosophy degree."

**Act V (Ep 29-35, ticks 44-53)** is the bathroom breakthrough — the cable-pivot technique and "KOMBUCHA IS IN THE BATHROOM."

---

## Cottagecore Palette Quick Reference

| Name | RGB | Hex | Use |
|------|-----|-----|-----|
| Rose | (232, 180, 184) | #e8b4b8 | Accents |
| Cream | (250, 245, 239) | #faf5ef | Vignette target, text |
| Linen | (240, 230, 216) | #f0e6d8 | Pill bg, canvas blend |
| Ink | (74, 67, 64) | #4a4340 | Body text |
| Muted | (138, 126, 118) | #8a7e76 | Subtitles |
| Dusty Rose | (210, 165, 170) | #d2a5aa | Title, mood text |
| Warm Black | (15, 13, 11) | #0f0d0b | Fade target |
