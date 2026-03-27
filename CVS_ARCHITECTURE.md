# CVS — ComfyUI Video System

## What Is CVS?

CVS (ComfyUI Video System) is a GPU-accelerated AI video production framework built on ComfyUI. It transforms raw autonomous robot exploration footage into narrative-driven, aesthetically graded vertical videos for TikTok and Bluesky publication.

The robot is **Kombucha** — an autonomous rover that explores physical spaces, logs tick-based observations (monologue, mood, goals), and captures fisheye POV video. CVS takes that raw material and produces 30-second cottagecore-styled episodes with synthesized ambient audio, ElevenLabs TTS narration, and cinematic post-processing — all orchestrated via Python scripts that submit workflows to ComfyUI's HTTP API.

**Platform:** Windows 11, NVIDIA RTX 4090 (24GB VRAM), Python 3.10
**Published to:** Bluesky @comradeclaw.bsky.social
**Series tag:** `cc_flora`

---

## Core Features

### 1. API-Driven Video Production
All workflows are submitted to ComfyUI via `POST /prompt` — no browser UI required. Python scripts build workflow JSON programmatically, submit it, and poll `/history/{prompt_id}` for completion. This enables headless, automated, and agent-orchestrated production.

### 2. Custom Kombucha Node Pack
Seven purpose-built ComfyUI nodes for the robot-to-video pipeline:

| Node | Purpose |
|------|---------|
| **ParseTickLog** | Extracts narrative (title, mood, monologue, best quote) from tick markdown files |
| **ElevenLabsTTS** | Direct ElevenLabs API integration for voice synthesis |
| **MotionClip** | Removes static frames from rover footage, keeps motion segments only |
| **VerticalFrameComposite** | Composes horizontal video into 1080×1920 vertical canvas with blurred background fill |
| **TextOverlay** | TikTok-safe-zone-aware text rendering (title, mood badge, hook quote) |
| **PadToAudio** | Matches video duration to audio via slow-motion and frame padding |
| **CosyMotes** | Warm bokeh dust particle overlay effect |

### 3. Synthesized Audio Design
Audio is generated entirely in numpy (no DAW):
- **Ambient pad:** A-minor additive synthesis (A2, C3, E3, A3 root + A4/C5/E5 shimmer) with LFO modulation and binaural stereo panning
- **Chimes:** Music-box tones (A5, C6, E6) with exponential decay, placed in narration gaps
- **Mood coloring:** Frequency shifts based on tick mood (E4 for "charging", Bb3 for "lingering", etc.)
- **Loudness normalization:** ffmpeg `loudnorm=I=-14:TP=-1:LRA=11` for Bluesky compliance

### 4. Cottagecore Visual Pipeline
Every frame passes through:
- 4x GPU upscale (spandrel + 4x-UltraSharp.pth) — optional, adds ~17min
- Color grading: red desaturation, shadow lift, warm shift, 0.92 range compression
- Soft bloom, creamy vignette, film grain, bokeh dust particles
- Georgia serif typography with safe-zone enforcement

### 5. Agent-Orchestrated Workflows
Four Claude Code agents with persistent memory:
- **Flora / Flora2** — cc_flora episode production
- **Virgil** — Generic pipeline executor
- **Output Janitor** — Cleans and organizes ComfyUI output directories

### 6. Bluesky Publishing
Automated upload via atproto SDK + curl-based video upload with job polling, H.264/yuv420p encoding, and loudness-normalized audio.

---

## How It Works

### Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. USER REQUEST  (or Agent trigger)                        │
│     "Run Flora episode 11" / "Virgil, run the pipeline"     │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. AGENT READS CONFIG                                      │
│     cc_flora_production_guide.md, episode JSON, tick logs   │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  3. PYTHON SCRIPT BUILDS WORKFLOW                           │
│     cc_flora_epXX.py or produce_episode.py                  │
│     Constructs ComfyUI node graph as JSON dict              │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  4. SUBMIT TO ComfyUI API                                   │
│     POST http://localhost:8188/prompt                        │
│     Body: {"prompt": {"1": {"class_type": ..., "inputs": ...}, ...}} │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. ComfyUI EXECUTES NODE GRAPH                             │
│     Topological sort → execute nodes → GPU inference        │
│     Automatic VRAM management (load/unload models)          │
│     WebSocket progress events                               │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  6. POLL FOR COMPLETION                                     │
│     GET /history/{prompt_id} until done                     │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  7. POST-PROCESSING                                         │
│     ffmpeg loudnorm → H.264 yuv420p faststart encode        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  8. PUBLISH TO BLUESKY                                      │
│     atproto auth → curl video upload → poll job → post      │
└─────────────────────────────────────────────────────────────┘
```

### Episode Pipeline Detail (cc_flora)

Each 30-second episode covers 2–3 ticks structured as 3 acts of 10 seconds (300 frames at 30fps):

```
Act 1 (0–10s)     Act 2 (10–20s)    Act 3 (20–30s)
┌──────────┐      ┌──────────┐      ┌──────────┐
│ Tick A    │      │ Tick B   │      │ Tick C   │
│ 300 frames│      │ 300 frames│     │ 300 frames│
│ mood: X   │      │ mood: Y  │      │ mood: Z  │
│ 2 lines   │      │ 2 lines  │      │ 2 lines  │
└──────────┘      └──────────┘      └──────────┘
```

**Per-frame processing:**
1. Load source video frames (VHS_LoadVideoPath or OpenCV)
2. Motion clip — remove static frames (L2 pixel distance threshold)
3. 4x GPU upscale (optional) — spandrel + 4x-UltraSharp.pth
4. Cottagecore color grading — red desat, shadow lift, warmth, range compression
5. Soft bloom (gaussian kernel on highlights, blend at 30%)
6. Compose into 1080×1920 vertical canvas (blurred fill background)
7. Draw bokeh dust particles (CosyMotes)
8. Film grain overlay (gaussian noise, intensity 0.03)
9. Text overlays (tick label, mood pill, narration quote) — TikTok safe zones
10. Creamy vignette (radial gradient, cream-tinted edges)

**Audio assembly:**
1. Generate A-minor ambient pad (numpy additive synthesis, 30s)
2. Generate TTS narration via ElevenLabs API (6 lines, timed to acts)
3. Generate chimes in narration gaps
4. Mix: pad at 30% + narration at 100% + chimes at 60%
5. Loudness normalize to -14dB LUFS

**Final encode:**
```bash
ffmpeg -i video.mp4 -i audio.wav \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  -af loudnorm=I=-14:TP=-1:LRA=11 \
  -shortest output.mp4
```

---

## Software Architecture Document (SAD)

### System Context

```
┌──────────────────────────────────────────────────────────────┐
│                    CVS System Boundary                        │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │ Claude Code │  │ Python       │  │ ComfyUI Server    │    │
│  │ Agents      │→→│ Orchestrators│→→│ (localhost:8188)   │    │
│  │ (Flora,     │  │ (scripts/)   │  │ GPU Node Execution│    │
│  │  Virgil,    │  │              │  │                   │    │
│  │  Janitor)   │  └──────┬───────┘  └────────┬──────────┘    │
│  └────────────┘         │                   │                │
│                          ▼                   ▼                │
│               ┌──────────────────┐  ┌────────────────┐       │
│               │ Audio Engine     │  │ Custom Nodes   │       │
│               │ (numpy/scipy)   │  │ (kombucha-     │       │
│               │                 │  │  pipeline)     │       │
│               └─────────────────┘  └────────────────┘       │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │ ElevenLabs   │ │ Bluesky  │ │ Kombucha     │
    │ TTS API      │ │ (atproto)│ │ Tick Logs    │
    │              │ │          │ │ + Video      │
    └──────────────┘ └──────────┘ └──────────────┘
```

### Directory Structure

```
E:\AI\CVS\                              # Project root
├── .env                                # API keys (ElevenLabs, Bluesky, Gmail)
├── run_comfyui.bat                     # Launch: python main.py --gpu-only --fast
│
├── ComfyUI\                            # ComfyUI server (full installation)
│   ├── main.py                         # Entrypoint
│   ├── execution.py                    # Node graph executor
│   ├── server.py                       # HTTP/WebSocket server (aiohttp)
│   ├── nodes.py                        # Built-in node registry
│   ├── folder_paths.py                 # Model/output path resolution
│   ├── extra_model_paths.yaml          # External model path mappings
│   ├── CLAUDE.md                       # ComfyUI architecture guide
│   │
│   ├── custom_nodes\
│   │   ├── comfyui-kombucha-pipeline\  # PRIMARY — video production nodes
│   │   │   ├── nodes.py                # 7 node classes
│   │   │   ├── audio_engine.py         # Numpy audio synthesis
│   │   │   ├── produce_episode.py      # Episode orchestrator CLI
│   │   │   ├── produce_bsky.py         # Bluesky publisher CLI
│   │   │   └── render_bsky.py          # Bluesky render utility
│   │   ├── comfyui-videohelpersuite\   # Video I/O (load/combine)
│   │   ├── deforum-comfy-nodes\        # Deforum animation
│   │   ├── ComfyUI-AnimateDiff-Evolved\# AnimateDiff video gen
│   │   ├── comfyui_controlnet_aux\     # ControlNet preprocessors
│   │   ├── comfyui-impact-pack\        # Utility nodes
│   │   ├── comfyui-kjnodes\            # KJ utility nodes
│   │   ├── Nvidia_RTX_Nodes_ComfyUI\   # RTX-optimized nodes
│   │   └── ComfyUI_FluxMod\            # Flux model support
│   │
│   ├── models\                         # Resolved via extra_model_paths.yaml
│   ├── input\                          # Uploaded input images
│   └── output\                         # Render outputs
│       ├── cc_flora_canon\             # Finalized episode videos
│       ├── finals\                     # Other finalized outputs
│       ├── projects\                   # In-progress project folders
│       └── archive\                    # Archived outputs
│
├── ComfyUI_Workflows\                  # Saved workflow JSONs
│   ├── image_to_text.json              # VLM image captioning
│   └── (various reference workflows)
│
├── scripts\                            # Python orchestrators & episode scripts
│   ├── run_workflow.py                 # Generic ComfyUI API submitter
│   ├── run_deforum.py                  # Frame-by-frame Deforum executor
│   ├── cc_flora_30s.py                 # Episode 01 (template baseline)
│   ├── cc_flora_ep02_*.py ... ep10_*.py# Episodes 02–10
│   ├── cc_flora_masterpiece.py         # Extended cut variant
│   ├── cc_flora_complete_process.md    # Full production guide (11 steps)
│   ├── cc_flora_production_guide.md    # Detailed SOP
│   ├── bluesky_template.py             # Bluesky post template
│   ├── dream_sequence.py               # LLM-driven narrative + video
│   └── (utility scripts: 8bit, posterize, deforum_flora, ltx_smoke_test)
│
└── .claude\                            # Agent configuration & memory
    ├── agents\
    │   ├── flora.md / flora2.md        # cc_flora production agents
    │   ├── virgil-comfyui-pipeline.md  # Pipeline executor agent
    │   └── comfyui-output-janitor.md   # Output cleanup agent
    └── agent-memory\                   # Persistent agent state
```

### Component Specifications

#### C1: ComfyUI Server

**Role:** GPU-accelerated node graph execution engine
**Entry:** `python main.py --gpu-only --fast --listen`
**Port:** 8188
**API:**
- `POST /prompt` — Submit workflow for execution. Body: `{"prompt": {node_id: {class_type, inputs}, ...}}`
- `GET /history/{prompt_id}` — Poll execution status and output paths
- `GET /object_info` — List all available nodes and their schemas
- `GET /system_stats` — VRAM/RAM usage
- `WebSocket /ws` — Real-time progress events

**Execution model:** Receives prompt → topological sort → execute nodes in dependency order → cache intermediate results → return output file paths

**VRAM management:** Automatic model loading/unloading based on available GPU memory. Models are loaded on demand and evicted LRU when space is needed.

#### C2: Kombucha Custom Node Pack

**Location:** `ComfyUI/custom_nodes/comfyui-kombucha-pipeline/`
**Registration:** Via `NODE_CLASS_MAPPINGS` dict in `__init__.py` (auto-discovered by ComfyUI)

**Node: ParseTickLog**
- Input: `log_path` (STRING) — path to tick markdown file
- Output: 7 strings (title, mood, monologue, best_quote, tick_number, goal, intent)
- Best quote scoring: +3 metaphor patterns, +2 figurative language, +1 length 30–120 chars, -2 technical data
- Searches sections: Monologue, Thought, Observation, Perception, Orientation, Decision

**Node: ElevenLabsTTS**
- Input: text (STRING, forceInput), api_key, voice_id, model_id, stability (0.5), similarity_boost (0.75)
- Output: AUDIO (WAV bytes)
- Default voice: `wVOQaU8CfoRJqCWsxoLv` (Kombucha)
- Default model: `eleven_multilingual_v2`

**Node: MotionClip**
- Input: images (IMAGE), sensitivity (1.5), min_segment_frames (5), merge_gap_frames (3), pad_frames (2), max_output_frames (900)
- Output: images (motion frames only), frame_count (INT)
- Algorithm: L2 pixel distance between consecutive frames → threshold at sensitivity × median → merge nearby segments → pad boundaries

**Node: VerticalFrameComposite**
- Input: images (IMAGE), canvas_width (1080), canvas_height (1920), blur_radius (25), blur_darken (0.4), video_y_offset (-60)
- Output: images, top_zone_height (INT), bottom_zone_start (INT)
- Method: Scale source to fill canvas → gaussian blur → darken to 40% → paste sharp video centered at y_offset

**Node: TextOverlay**
- Input: images (IMAGE), title/mood/quote (STRING, forceInput), font sizes, colors, y-positions
- Output: images (text-composited)
- TikTok safe zones: top 150px, bottom 480px, right 120px, left 44px
- Fonts: Impact (title), Arial Bold (badge/quote)

**Node: PadToAudio**
- Input: images (IMAGE), audio (AUDIO), frame_rate (30), buffer_seconds (1.0), min_speed (0.8), pad_start_ratio (0.4)
- Output: images (duration-matched), audio
- Strategy: passthrough if long enough → slow to 0.8x → slow + pad frames (40% start / 60% end)

**Node: CosyMotes**
- Generates 50+ warm-toned bokeh dust particles with pulsing opacity and upward drift

#### C3: Audio Engine

**Location:** `ComfyUI/custom_nodes/comfyui-kombucha-pipeline/audio_engine.py`
**Entry:** `build_soundtrack(monologue, duration=25.0, mood="prowling")`
**Sample rate:** 44100 Hz

**Ambient Pad Synthesis:**
```
Root drone:   A2 (110Hz), C3 (130.81Hz), E3 (164.81Hz), A3 (220Hz)
Shimmer:      A4 (440Hz), C5 (523.25Hz), E5 (659.25Hz)
Shimmer LFOs: 0.12Hz, 0.18Hz, 0.07Hz (slow modulation)
Mood tone:    variable frequency based on tick mood
Binaural:     slow L/R sweeps + 2Hz frequency offset for spatial depth
Filter:       Butterworth low-pass at 3000Hz
Envelope:     fade in 3s, sustain at 30%, fade out 3s
```

**Chimes:**
```
Frequencies:  A5 (880Hz), C6 (1046.5Hz), E6 (1318.5Hz)
Envelope:     sine × exponential decay
Placement:    in gaps between TTS narration segments
First chime:  always at t=0.1s
```

**Mix levels:** Pad 30% + Narration 100% + Chimes 60%

**Loudness normalization:**
```bash
ffmpeg -af loudnorm=I=-14:TP=-1:LRA=11
```

#### C4: Python Orchestrators

**run_workflow.py** (generic submitter):
```python
# Accepts workflow JSON file or dict
# POST /prompt → poll /history/{prompt_id} → return output paths
```

**produce_episode.py** (episode production):
```python
# Input: episode JSON config
# Config format:
{
  "number": 11,
  "title": "Episode Title",
  "acts": [
    {
      "tick": "0050",
      "mood": "curious",
      "motion_range": [100, 400],  # frame range in source video
      "narration": [
        {"text": "Line one.", "start": 0.5},
        {"text": "Line two.", "start": 5.0}
      ]
    },
    // ... 3 acts total
  ]
}
```

**cc_flora_epXX.py** (self-contained episode scripts):
- Each is standalone — no dependency on custom nodes at runtime
- Implements full visual pipeline in Python (PIL, numpy, spandrel)
- Implements full audio pipeline in Python (numpy, scipy, requests to ElevenLabs)
- Template: copy ep06 (`cc_flora_ep06_three_centimeters.py`) for new episodes

#### C5: Agent System

**Location:** `.claude/agents/` (definitions) + `.claude/agent-memory/` (persistent state)

**Flora Agent** (`flora.md`, `flora2.md`):
- Produces cc_flora episodes end-to-end
- Reads production guide, selects ticks, writes narration, runs script
- Default: FAST mode (no upscaling, ~3 min)
- Narration rules: <60 chars per line, final line by 29.8s, strip TTS tags

**Virgil Agent** (`virgil-comfyui-pipeline.md`):
- Generic pipeline executor — can run any ComfyUI workflow
- Principles: always submit via API, read configs first, sequential execution, validate outputs

**Output Janitor** (`comfyui-output-janitor.md`):
- Two-phase: scan & propose → execute cleanup
- Identifies: frame sequences, progressive builds, temp files, duplicate renders
- Organizes into: finals/, projects/, archive/

#### C6: External Dependencies

| Service | Purpose | Auth |
|---------|---------|------|
| **ElevenLabs API** | TTS narration synthesis | API key in .env |
| **Bluesky (atproto)** | Video publishing | Handle + app password in .env |
| **ffmpeg** | Video encoding, loudnorm, format conversion | System PATH |
| **spandrel** | GPU upscaler model loading | pip package |
| **scipy** | Audio filtering (Butterworth low-pass) | pip package |
| **PIL/Pillow** | Image compositing, text rendering | pip package |
| **torch/torchaudio** | GPU inference, audio I/O | pip + CUDA |

#### C7: Model Dependencies

**Resolved via `extra_model_paths.yaml`:**

| Model | Path | Purpose |
|-------|------|---------|
| 4x-UltraSharp.pth | E:/AI/ComfyUI/models/upscale_models/ | 4x GPU upscaling |
| clip_l.safetensors | E:/AI/ComfyUI/models/clip/ | CLIP text encoding |
| clip_vision_g/h.safetensors | E:/AI/ComfyUI/models/clip_vision/ | CLIP vision encoding |
| t5xxl_fp8_e4m3fn.safetensors | E:/AI/ComfyUI/models/text_encoders/ | T5-XXL text encoding |
| gemma_3_12B_it_fp4_mixed.safetensors | E:/AI/ComfyUI/models/text_encoders/ | Gemma 3 VLM (12B) |
| qwen_3_4b.safetensors | E:/AI/ComfyUI/models/text_encoders/ | Qwen 3 VLM (4B) |
| llava_llama3_fp8_scaled.safetensors | E:/AI/ComfyUI/models/text_encoders/ | LLaVA-LLaMA3 VLM (8B) |
| Various checkpoints | E:/AI/ComfyUI/models/checkpoints/ | Stable Diffusion, DreamShaper |
| Various ControlNets | E:/AI/ComfyUI/models/controlnet/ | ControlNet conditioning |

### Data Flow: cc_flora Episode

```
Kombucha Tick Logs              Source Video
(E:/AI/Kombucha/ticks/)         (E:/AI/Kombucha/video/web/)
        │                               │
        ▼                               ▼
  ┌─────────────┐              ┌─────────────────┐
  │ ParseTickLog│              │ VHS_LoadVideo    │
  │ or manual   │              │ frame extraction │
  └──────┬──────┘              └────────┬────────┘
         │                              │
    title, mood,                   raw frames
    monologue,                         │
    best_quote                         ▼
         │                     ┌──────────────┐
         │                     │ MotionClip   │
         │                     │ remove static│
         │                     └──────┬───────┘
         │                            │
         │                       motion frames
         │                            │
         │                            ▼
         │                     ┌──────────────┐
         │                     │ 4x-UltraSharp│ (optional)
         │                     │ GPU upscale  │
         │                     └──────┬───────┘
         │                            │
         │                            ▼
         │                     ┌──────────────────────┐
         │                     │ Cottagecore Grading   │
         │                     │ bloom, grain, vignette│
         │                     └──────┬───────────────┘
         │                            │
         │                            ▼
         │                     ┌──────────────────────┐
         │                     │ VerticalFrameComposite│
         │                     │ 1080×1920 canvas      │
         │                     └──────┬───────────────┘
         │                            │
         ├─── title, mood ───────────▶│
         │                            ▼
         │                     ┌──────────────┐
         │                     │ TextOverlay  │
         │                     │ + CosyMotes  │
         │                     └──────┬───────┘
         │                            │
         │                       composited frames
         │                            │
    monologue                         │
         │                            │
         ▼                            │
  ┌──────────────┐                    │
  │ ElevenLabs   │                    │
  │ TTS API      │                    │
  └──────┬───────┘                    │
         │                            │
    narration.wav                     │
         │                            │
         ▼                            │
  ┌──────────────┐                    │
  │ Audio Engine │                    │
  │ pad + chimes │                    │
  │ + mix + norm │                    │
  └──────┬───────┘                    │
         │                            │
    soundtrack.wav                    │
         │                            │
         ▼                            ▼
  ┌─────────────────────────────────────────┐
  │ PadToAudio (match video to audio len)   │
  └────────────────────┬────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────┐
  │ VHS_VideoCombine / ffmpeg               │
  │ H.264 yuv420p faststart                 │
  │ loudnorm -14dB LUFS                     │
  └────────────────────┬────────────────────┘
                       │
                       ▼
              episode_XX.mp4
              (output/cc_flora_canon/)
                       │
                       ▼
  ┌─────────────────────────────────────────┐
  │ produce_bsky.py                         │
  │ atproto auth → curl upload → post       │
  └─────────────────────────────────────────┘
```

### Configuration Reference

#### .env
```
ELEVENLABS_API_KEY=sk-...
ELEVENLABS_VOICE=wVOQaU8CfoRJqCWsxoLv
ELEVENLABS_MODEL=eleven_multilingual_v2
BLUESKY_HANDLE=comradeclaw.bsky.social
BLUESKY_APP_PASSWORD=...
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...
OPERATOR_EMAIL=...
```

#### extra_model_paths.yaml
```yaml
old_comfyui:
    base_path: E:/AI/ComfyUI/
    upscale_models: models/upscale_models/
    checkpoints: models/checkpoints/
    clip: models/clip/
    clip_vision: models/clip_vision/
    controlnet: models/controlnet/
    vae: models/vae/
    loras: models/loras/
    diffusion_models: models/diffusion_models/
    text_encoders: models/text_encoders/

portable_comfyui:
    base_path: E:/AI/comfy/ComfyUI_windows_portable/ComfyUI/
    controlnet: models/controlnet/
    checkpoints: models/checkpoints/
```

#### Episode JSON Config (produce_episode.py)
```json
{
  "number": 11,
  "title": "Episode Title",
  "acts": [
    {
      "tick": "0050",
      "mood": "curious",
      "motion_range": [100, 400],
      "narration": [
        {"text": "First line of narration.", "start": 0.5},
        {"text": "Second line.", "start": 5.0}
      ]
    }
  ]
}
```

#### Visual Pipeline Constants
```
Canvas:           1080×1920 (vertical) or 1080×1080 (square)
Frame rate:       30 fps
Duration:         30 seconds (900 frames)
Acts:             3 × 10s (300 frames each)
Blur radius:      25 (background fill)
Blur darken:      0.4 (40% brightness)
Video y-offset:   -60 (push up for text space)
Bloom kernel:     21px gaussian, 30% blend
Grain intensity:  0.03
Vignette:         radial gradient, cream-tinted
```

#### Audio Pipeline Constants
```
Sample rate:      44100 Hz
Pad level:        30% in mix
Narration level:  100% in mix
Chimes level:     60% in mix
Low-pass cutoff:  3000 Hz (Butterworth)
LFO rates:        0.12, 0.18, 0.07 Hz
Fade in/out:      3 seconds each
Target loudness:  -14 dB LUFS
True peak:        -1 dB
LRA:              11
```

#### TikTok Safe Zones
```
Top:    150px (app tabs — no text)
Bottom: 480px (caption bar — no text)
Right:  120px (engagement icons — no text)
Left:    44px (profile info — no text)
```

### Rebuild Instructions

To recreate CVS from scratch on a new machine:

**1. Prerequisites**
- Windows 10/11 with NVIDIA GPU (16GB+ VRAM recommended, 24GB ideal)
- Python 3.10.x
- CUDA toolkit compatible with PyTorch 2.5+
- ffmpeg in system PATH
- Git

**2. Install ComfyUI**
```bash
git clone https://github.com/comfyanonymous/ComfyUI.git E:\AI\CVS\ComfyUI
cd E:\AI\CVS\ComfyUI
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

**3. Install Custom Nodes**
```bash
cd E:\AI\CVS\ComfyUI\custom_nodes
git clone <kombucha-pipeline-repo> comfyui-kombucha-pipeline
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite comfyui-videohelpersuite
git clone https://github.com/deforum-art/deforum-comfy-nodes deforum-comfy-nodes
git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved ComfyUI-AnimateDiff-Evolved
git clone https://github.com/Fannovel16/comfyui_controlnet_aux comfyui_controlnet_aux
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack comfyui-impact-pack
git clone https://github.com/kijai/ComfyUI-KJNodes comfyui-kjnodes
# Install each node's requirements.txt
```

**4. Install Python Dependencies**
```bash
pip install elevenlabs requests python-dotenv scipy spandrel pillow torchaudio
pip install atproto  # for Bluesky publishing
pip install "numpy>=1.21.6,<1.28.0"  # must be compatible with scipy
```

**5. Download Models**
- `4x-UltraSharp.pth` → `models/upscale_models/`
- CLIP, VAE, checkpoint, ControlNet models as needed
- VLM text encoders (gemma, qwen, llava) → `models/text_encoders/`

**6. Configure**
- Create `.env` with ElevenLabs API key, Bluesky credentials
- Create `extra_model_paths.yaml` pointing to model directories
- Create `run_comfyui.bat`:
  ```batch
  @echo off
  cd /d "E:\AI\CVS\ComfyUI"
  python main.py --gpu-only --fast
  pause
  ```

**7. Set Up Agent System**
- Create `.claude/agents/` with Flora, Virgil, and Janitor agent definitions
- Create `.claude/agent-memory/` subdirectories
- Copy production guides to `scripts/`

**8. Verify**
```bash
# Start server
python main.py --gpu-only --fast --listen

# Test API
curl http://localhost:8188/system_stats

# Test workflow submission
python scripts/run_workflow.py scripts/workflow_01_basic_txt2img.json
```

### Episode Catalog (Season 1)

| Ep | Title | Ticks | Status |
|----|-------|-------|--------|
| 01 | First Light | 0001–0003 | Published |
| 02 | The Bigger Room | 0004,0006–0008 | Published |
| 03 | Moon | 0010,0012,0013 | Published |
| 04 | Carried Home | 0014–0018 | Published |
| 05 | Same Frame | 0019–0024 | Published |
| 06 | Three Centimeters | 0032–0035 | Published |
| 07 | Ping-Pong | 0036,0037 | Published |
| 08 | The Threshold | 0038,0039 | Published |
| 09 | The Hallway | 0041,0042,0044 | Published |
| 10 | The Patience of Rooms | 0046,0048,0049 | Published |

**Canon folder:** `E:/AI/CVS/ComfyUI/output/cc_flora_canon/`
**Published to:** Bluesky @comradeclaw.bsky.social
