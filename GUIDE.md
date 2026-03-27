# CVS User Guide

A practical guide to designing workflows, authoring brand kits, integrating agents, and producing video with the Centaur Video System.

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Workflow Design](#2-workflow-design)
3. [Brand Kit Authoring](#3-brand-kit-authoring)
4. [Node Reference](#4-node-reference)
5. [Agent Integration](#5-agent-integration)
6. [The cc_flora Pipeline (Case Study)](#6-the-cc_flora-pipeline)
7. [Audio Design](#7-audio-design)
8. [Publishing](#8-publishing)
9. [Tips and Patterns](#9-tips-and-patterns)

---

## 1. Core Concepts

### The Centaur Boundary

CVS enforces a clean split between human direction and AI execution:

```
HUMAN SIDE                          AI SIDE
─────────────────────────────────── ───────────────────────────────
Design the workflow graph            Execute nodes in order
Choose which footage to use          Render, composite, encode
Write or approve all text            Apply color grading per rules
Define brand colors and rules        Enforce rules via Rule Gate
Review final output                  Report gate pass/fail
```

The workflow graph IS the boundary. You design it before execution. The AI runs it. You review after.

### Workflows as Artifacts

A saved ComfyUI workflow JSON is a complete production system. It encodes:
- What nodes run (your editorial choices)
- How they connect (your structural decisions)
- What parameters they use (your quality settings)
- What the brand kit enforces (your identity rules)

Version workflows in git. Hand them to agents. The template is the centaur's primary artifact.

### The API-First Principle

All production happens through ComfyUI's REST API:

```
POST http://localhost:8188/prompt
Body: {"prompt": {node_id: {class_type, inputs}, ...}}
```

This means:
- No browser UI required for production runs
- Agents can produce video programmatically
- Batch production is a Python loop
- Everything is reproducible and auditable

---

## 2. Workflow Design

### Anatomy of a CVS Workflow

Every CVS workflow follows this pattern:

```
Brand Kit (identity + rules)
    |
Source Nodes (bring in media)
    |
AI Nodes (generate text, select assets)
    |
Composition Nodes (assemble, overlay, transition)
    |
Control Nodes (Rule Gate — quality check)
    |
Output Nodes (encode to video)
```

### Building a Workflow

**Step 1: Start with the Brand Kit**

Place a Load Brand Kit node at the top. Wire its outputs to every downstream node that touches color, text style, or quality:
- `primary_color` -> Lower Third accent, Apply Brand Colors tint
- `tone` -> LLM Text Writer, LLM Director
- `rules_json` -> Rule Gate

**Step 2: Bring in Source Media**

Add source nodes for your footage:
- `Load Video` for video files (outputs IMAGE frame batch)
- `Load Audio` for background music or sound effects
- `Load Video -> Frames` for surgical frame extraction

**Step 3: Add AI Nodes (Optional)**

If you need generated text:
- `LLM Text Writer` for headlines, captions, summaries
- `LLM Director` for complex decisions (asset selection, scene description)

Wire the brand kit's `tone` into these nodes so generated text matches your voice.

**Step 4: Compose**

Build your edit:
- `Concatenate Scenes` to join clips end-to-end
- `Crossfade Transition` for smooth scene changes
- `Text Overlay` for titles, quotes, captions
- `Lower Third` for name/title bars
- `Title Card` for full-frame text screens
- `Ken Burns` to animate still images
- `Apply Brand Colors` for subtle color grading

**Step 5: Gate Check**

Place a `Rule Gate` before output:
- Wire `rules_json` from the brand kit
- Set brightness, resolution, and duration thresholds
- Choose `warn_and_pass` during development, `block` for production

**Step 6: Render**

End with `Save Video`:
- Set format (mp4, webm, gif)
- Set quality preset
- Wire audio if you have it
- Set filename prefix

### Example: Minimal Workflow

```
Load Brand Kit ("demo_brand.json")
    |
    |-> primary_color ─────────────────────┐
    |-> rules_json ──────────────────┐     |
    |                                |     |
Load Video ("interview.mp4")         |     |
    |                                |     |
    v                                |     |
Lower Third                          |     |
  primary_text: "Jane Smith"         |     |
  secondary_text: "Co-op Founder"    |     |
  accent_color: <─────────────────────────┘
    |                                |
    v                                |
Rule Gate <──────────────────────────┘
  min_brightness: 0.05
  min_width: 1280
    |
    v
Save Video
  format: mp4
  quality: high
  fps: 30
```

---

## 3. Brand Kit Authoring

### Creating a Brand Kit

Create a JSON or YAML file:

```json
{
  "name": "My Project",
  "purpose": "What this project is about",
  "brand": {
    "colors": {
      "primary": "#DC143C",
      "secondary": "#1a1a2e",
      "accent": "#f0e68c"
    },
    "fonts": {
      "heading": "Space Mono",
      "body": "IBM Plex Sans"
    },
    "tone": "warm, intellectual, hopeful"
  },
  "style": {
    "pacing": "measured, 3-5 seconds per text card",
    "transitions": "crossfade, occasional hard cut",
    "text_overlay": "lower-third, white on dark scrim",
    "music": "ambient, lo-fi",
    "aspect_ratio": "16:9",
    "duration_target": "30-60 seconds per episode"
  },
  "rules": [
    "Always include source attribution",
    "Minimum 2 seconds on text displays",
    "B-roll minimum brightness 0.05",
    "Hold quote text long enough to read twice"
  ]
}
```

### Color Selection Tips

- **Primary:** Your signature color. Used for accents, stripes, highlights. Should be recognizable.
- **Secondary:** Background/dark color. Used for title card backgrounds, scrims.
- **Accent:** Emphasis color. Used for subtitles, call-to-action elements.

Keep primary and accent high-contrast against secondary.

### Tone Guidelines

The `tone` string is passed directly to LLM nodes as context. Be specific:
- Bad: "nice"
- Good: "warm, intellectual, slightly irreverent, avoids jargon"

### Rules as Constraints

Rules in the brand kit flow into two places:
1. **Rule Gate** — enforces measurable rules (brightness, resolution, duration)
2. **LLM Director** — receives rules as system prompt constraints

Write rules that are actionable:
- Bad: "Make it look good"
- Good: "Minimum brightness 0.05 for all b-roll footage"

---

## 4. Node Reference

### Source Nodes

| Node | Inputs | Outputs | Notes |
|------|--------|---------|-------|
| Load Video | file, max_frames, start/end_time, fps | IMAGE, dimensions, fps, count | FFmpeg decode |
| Load Video->Frames | file, frame_start, frame_end | IMAGE, count | Exact frame range |
| Load Audio | file, start/end_time | AUDIO, info | Optional trim |
| Load Brand Kit | file (.json/.yaml) | colors, tone, rules | Wire everywhere |

### AI Nodes

| Node | Inputs | Outputs | Notes |
|------|--------|---------|-------|
| LLM Director | prompt, context, provider, model | STRING | General intelligence |
| LLM Text Writer | topic, type, tone, max_words | STRING | Text generation |
| Asset Tagger | IMAGE, tags, mood, grade | IMAGE, metadata | Teaching action |
| Asset Selector | IMAGE_a, IMAGE_b, criterion | IMAGE, reason | Measurable selection |

### Composition Nodes

| Node | Key Inputs | Output | Notes |
|------|-----------|--------|-------|
| Compose Layers | bg, fg, position, opacity | IMAGE | Layer compositing |
| Concatenate | scene_a, scene_b | IMAGE | A then B |
| Crossfade | scene_a, scene_b, overlap | IMAGE | Smooth transition |
| Text Overlay | IMAGE, text, position, style | IMAGE | Burn text onto frames |
| Lower Third | IMAGE, primary/secondary text | IMAGE | Broadcast-style bar |
| Title Card | text, dimensions, colors | IMAGE | Full-frame text |
| Ken Burns | IMAGE, zoom, direction, easing | IMAGE | Still -> video |
| Apply Brand Colors | IMAGE, tint, intensity, target | IMAGE | Color grading |
| Audio Mix | audio_a, audio_b, volumes | AUDIO | Two-track mix |
| Audio Fade | audio, fade_in, fade_out | AUDIO | Envelope |

### Control Nodes

| Node | Inputs | Outputs | Notes |
|------|--------|---------|-------|
| Rule Gate | IMAGE, thresholds, rules_json | IMAGE, report, passed | Quality enforcement |

### Output Nodes

| Node | Inputs | Outputs | Notes |
|------|--------|---------|-------|
| Save Video | IMAGE, fps, format, quality, audio | filepath | Terminal node |

---

## 5. Agent Integration

### How Agents Use CVS

Agents are **template consumers**, not designers. The pattern:

1. Load a human-designed workflow JSON
2. Inject runtime data (today's headline, selected footage, etc.)
3. POST to ComfyUI `/prompt`
4. Poll `/history/{prompt_id}` for completion
5. Check output file exists

### Minimal Agent Code

```python
import json
import time
import requests

COMFYUI = "http://localhost:8188"

def produce_video(template_path, injections):
    """Fill a workflow template and render it."""
    with open(template_path) as f:
        workflow = json.load(f)

    # Inject data into specific nodes
    for node_id, values in injections.items():
        for key, value in values.items():
            workflow[node_id]["inputs"][key] = value

    # Submit
    resp = requests.post(f"{COMFYUI}/prompt", json={"prompt": workflow})
    prompt_id = resp.json()["prompt_id"]

    # Poll for completion
    while True:
        history = requests.get(f"{COMFYUI}/history/{prompt_id}").json()
        if prompt_id in history:
            return history[prompt_id]["outputs"]
        time.sleep(2)

# Usage
outputs = produce_video("workflows/daily_report.json", {
    "6": {"text": "Today's Headline"},
    "8": {"text": "Summary paragraph here."},
})
```

### Template Design for Agents

When designing workflows that agents will fill:

1. Give text input nodes memorable titles (shown in the JSON as node IDs)
2. Document which node IDs accept injected data
3. Use sensible defaults — the template should produce valid output even without injection
4. Wire Rule Gate to catch bad injections (too-dark images, missing text)

### Batch Production

```python
episodes = [
    {"title": "Episode 1", "footage": "clip_01.mp4", "quote": "First light."},
    {"title": "Episode 2", "footage": "clip_02.mp4", "quote": "The bigger room."},
]

for ep in episodes:
    produce_video("workflows/episode_template.json", {
        "3": {"text": ep["title"]},
        "5": {"video": ep["footage"]},
        "9": {"text": ep["quote"]},
    })
```

---

## 6. The cc_flora Pipeline (Case Study)

The cc_flora pipeline produced 10 published TikTok episodes for the Kombucha robot series. It's the v0 implementation of CVS concepts.

### What It Does

Transforms raw autonomous rover POV footage into 30-second vertical (1080x1920) episodes with:
- Cottagecore color grading (red desaturation, shadow lift, warmth)
- Soft bloom, film grain, bokeh dust particles
- TikTok-safe-zone text overlays
- Synthesized ambient audio (A-minor drone + music-box chimes)
- ElevenLabs TTS narration
- Bluesky-optimized encoding

### Episode Structure

Each 30-second episode = 3 acts of 10 seconds (300 frames at 30fps):

```
Act 1 (0-10s)      Act 2 (10-20s)     Act 3 (20-30s)
Tick A footage      Tick B footage      Tick C footage
mood: curious       mood: uncertain     mood: resolved
2 narration lines   2 narration lines   2 narration lines
```

### Per-Frame Pipeline

1. Load source video frames
2. Motion clip (remove static frames)
3. 4x GPU upscale (optional, +17 min)
4. Cottagecore color grade
5. Soft bloom
6. Compose into 1080x1920 vertical canvas (blurred fill background)
7. Bokeh dust particles
8. Film grain
9. Text overlays (tick label, mood pill, narration)
10. Creamy vignette

### Audio Assembly

1. Generate A-minor ambient pad (numpy additive synthesis)
2. Generate TTS narration (ElevenLabs API, 6 lines timed to acts)
3. Generate chimes in narration gaps
4. Mix: pad 30% + narration 100% + chimes 60%
5. Loudness normalize to -14dB LUFS

### Episode Scripts

Each episode is a self-contained Python script in `scripts/`:
- `cc_flora_ep01_first_light.py` through `cc_flora_ep10_the_patience_of_rooms.py`
- Template for new episodes: copy ep06 and modify

---

## 7. Audio Design

### Ambient Pad Synthesis

CVS generates audio entirely in numpy (no DAW required):

```
Root drone:   A2 (110Hz), C3 (130.81Hz), E3 (164.81Hz), A3 (220Hz)
Shimmer:      A4 (440Hz), C5 (523.25Hz), E5 (659.25Hz)
LFOs:         0.12Hz, 0.18Hz, 0.07Hz (slow modulation on shimmer)
Filter:       Butterworth low-pass at 3000Hz
Binaural:     Slow L/R sweeps + 2Hz offset for spatial depth
Envelope:     3s fade in, sustain at 30%, 3s fade out
```

### Mood Coloring

Different moods shift a frequency into the mix:
- `charging` -> E4 (329Hz)
- `lingering` -> Bb3 (233Hz)
- `curious` -> D4 (293Hz)

### Chimes

Music-box tones (A5, C6, E6) with exponential decay, placed in gaps between narration.

### Loudness Normalization

All output is normalized for platform compliance:
```bash
ffmpeg -af loudnorm=I=-14:TP=-1:LRA=11
```

---

## 8. Publishing

### Bluesky

The cc_flora pipeline publishes to Bluesky via atproto:

1. Authenticate with handle + app password
2. Upload video via curl (bypasses Python SSL issues)
3. Poll upload job until `JOB_STATE_COMPLETED`
4. Create post with video embed, caption, hashtags

### Video Encoding for Bluesky

```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  -af loudnorm=I=-14:TP=-1:LRA=11 \
  -shortest output.mp4
```

Key settings: H.264, yuv420p (compatibility), faststart (streaming), loudnorm (platform compliance).

---

## 9. Tips and Patterns

### Start Simple

Your first workflow should be:
```
Load Video -> Text Overlay -> Save Video
```

Add complexity only when you need it.

### Brand Kit First

Always start by creating your brand kit. Even a minimal one (primary color + tone) dramatically improves consistency across productions.

### Rule Gates in Development

Use `warn_and_pass` mode during development so you can see gate reports without blocking output. Switch to `block` for production.

### Template Discipline

When an agent will use a workflow:
1. Design and test it manually first
2. Document which nodes accept injected data
3. Set good defaults for everything
4. Add a Rule Gate before output
5. Version it in git

### Batch Rendering

For series production, design ONE template and iterate over data:
```python
for item in data:
    inject(template, node_id, item.value)
    submit(template)
```

Don't design a new workflow per episode. The template IS the editorial decision.

### Audio Mixing

Keep background music at 20-30% volume. Narration at 100%. Always normalize loudness for your target platform.

### TikTok Safe Zones

When composing for TikTok (9:16 vertical):
- Top 150px: app tabs (no text)
- Bottom 480px: caption bar (no text)
- Right 120px: engagement icons (no text)
- Left 44px: profile info (no text)

All text must fit within the safe zone rectangle.
