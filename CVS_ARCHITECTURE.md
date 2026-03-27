# The Centaur Video System (CVS)

## Complete System Design — v1.0

**Status:** MYCELIUM (architecture defined, root node pack built, host infrastructure live)
**Author:** Bucket + Claude
**Date:** 2026-03-26
**Foundation:** ComfyUI (running, GPU-accelerated, API live)

---

## 1. What It Is

The Centaur Video System is a **human-directed, AI-executed video production framework** built as a custom node pack for ComfyUI. It transforms ComfyUI from a generative media tool into a full video production pipeline where:

- The **human** designs workflow graphs, defines brand identity, sets quality rules, curates assets, and makes editorial decisions
- The **AI** executes rendering, compositing, text generation, asset selection, color grading, and encoding within human-defined constraints
- **Agents** (Comrade Claw, Kindling, future systems) can call the ComfyUI API to produce video autonomously — but only within workflows the human designed

CVS is not a video editor. It is not an AI video generator. It is the **directing interface** between human editorial intent and AI production capacity. The node graph IS the centaur — every wire the human draws is a directive, every node the AI runs is execution under constraint.

### Why ComfyUI

ComfyUI is already running on the 4090 doing video generation and upscaling. The infrastructure is warm. The API is live. Custom nodes are Python classes with a standard interface — drop them in `custom_nodes/`, restart, they appear on the canvas. ComfyUI provides:

- Node graph canvas with visual workflow design
- Execution engine with dependency resolution
- REST API (`/prompt` endpoint) for programmatic workflow execution
- GPU-accelerated pipeline
- Workflow serialization as JSON (versionable, shareable, agent-executable)
- Existing ecosystem of image/video generation nodes to compose with
- App Mode for simplified interfaces (announced GDC 2026)

Building on ComfyUI means CVS nodes compose with everything else already installed — LTX-Video, upscalers, ControlNet, LoRA, image generators. A single workflow can generate an image with Flux, upscale it, apply Ken Burns, overlay Kombucha's monologue, color-grade to brand, gate-check it, and render to MP4. No glue code.

---

## 2. The Centaur Model

### Research Foundation

The system implements the centaur collaboration model as described in:

- **Saghafian (Harvard, 2023):** Centaurs combine formal analytics and human intuition through symbiotic learning. The centaur outperforms both the best algorithm and the best human expert alone.
- **Candelon/Kellogg/Lifshitz (MIT/Harvard/Warwick, 2026):** Three collaboration modes — Cyborg (fused), Centaur (directed), Self-Automator (abdicated). Centaurs achieved highest accuracy. Self-Automators performed worst. Key finding: when humans surrender control over WHAT, they also lose control over HOW.

### Applied to Video

| Dimension | Human Controls | AI Controls |
|-----------|---------------|-------------|
| **What** gets made | Topic, story, editorial angle, which footage | Never |
| **Strategic how** | Brand, style, pacing, rules, template design | Never |
| **Tactical how** | Override points in workflow | Rendering, compositing, timing, encoding |
| **Quality** | Rule definitions, review, approval | Rule enforcement, automated checking |
| **Learning** | Feedback, corrections | Accumulating those into future behavior |

### The Three Anti-Patterns CVS Prevents

1. **Self-Automator:** "AI, make me a video about co-ops." No. The human designs the workflow, picks the footage, writes or approves the text, sets the rules. The AI never decides what the video is about.

2. **Full Manual:** "I'll edit every frame in Premiere." No. The human directs at the structural level. The AI handles the frame-by-frame production work. The human reviews output, not process.

3. **Cyborg Blur:** "Let's iterate on this together in real-time." The graph model prevents this — the human designs the workflow BEFORE execution. The AI runs it. Review happens after. The boundary stays clean.

---

## 3. Architecture

### 3.1 System Layers

```
╔══════════════════════════════════════════════════════════════════╗
║                    HUMAN LAYER                                   ║
║                                                                  ║
║  Workflow Design · Brand Identity · Quality Rules                ║
║  Asset Curation · Editorial Decisions · Review/Approval          ║
║                                                                  ║
║  Interface: ComfyUI Canvas + Brand Kit YAML/JSON                 ║
╠══════════════════════════════════════════════════════════════════╣
║                    CVS NODE PACK                                 ║
║                                                                  ║
║  Source Nodes · AI Nodes · Composition Nodes                     ║
║  Control Nodes · Output Nodes                                    ║
║                                                                  ║
║  Interface: ComfyUI node registration (Python classes)           ║
╠══════════════════════════════════════════════════════════════════╣
║                    COMFYUI ENGINE                                ║
║                                                                  ║
║  Graph Execution · Dependency Resolution · GPU Scheduling        ║
║  REST API (/prompt) · Workflow Serialization                     ║
║  Existing Nodes (LTX-Video, upscalers, img2img, etc.)           ║
║                                                                  ║
║  Interface: HTTP API + WebSocket + Canvas UI                     ║
╠══════════════════════════════════════════════════════════════════╣
║                    AGENT LAYER                                   ║
║                                                                  ║
║  Comrade Claw · Kombucha · Kindling · MDP Caucus Tools           ║
║  Flora · Virgil · Future Agents                                  ║
║                                                                  ║
║  Interface: ComfyUI REST API (/prompt with workflow JSON)        ║
╚══════════════════════════════════════════════════════════════════╝
```

### 3.2 Data Flow

```
Human designs workflow graph (ComfyUI canvas)
    ↓ saved as
Workflow JSON (versioned in git)
    ↓ loaded by
ComfyUI engine OR agent via API
    ↓ with
Data injection (agent fills template variables)
    ↓ executing
CVS nodes in dependency order
    ↓ producing
Rendered video file + gate reports + metadata
    ↓ reviewed by
Human (or auto-published if gate passed + human pre-approved)
```

### 3.3 Agent Integration Pattern

```python
# How Comrade Claw produces a video on a daily wake

import requests
import json

COMFYUI_URL = "http://localhost:8188"

# Load the human-designed workflow template
with open("workflows/cc_daily_report.json") as f:
    workflow = json.load(f)

# Inject today's data into the template
# (node IDs reference specific nodes in the workflow)
workflow["6"]["inputs"]["text"] = todays_headline
workflow["8"]["inputs"]["text"] = todays_summary
workflow["8"]["inputs"]["secondary_text"] = todays_source

# POST to ComfyUI — the engine handles everything
response = requests.post(
    f"{COMFYUI_URL}/prompt",
    json={"prompt": workflow}
)

# Video renders on the 4090, lands in output folder
# Rule Gate checked brightness, resolution, duration
# Brand colors applied, lower thirds burned in
# CC never decided WHAT the video says — only filled the slots
```

This is the entire integration. The complexity lives in the workflow graph, not in agent code.

---

## 4. Node Pack — Complete Specification

### 4.1 Type System

CVS introduces these data types that flow between nodes:

| Type | Format | Description |
|------|--------|-------------|
| `IMAGE` | `torch.Tensor [B,H,W,C]` float32 0-1 | Standard ComfyUI frame batch. B=frame count. |
| `AUDIO` | `dict {path, duration, ...}` | Audio file reference with metadata. FFmpeg handles all encoding. |
| `MASK` | `torch.Tensor [B,H,W]` float32 0-1 | Per-pixel alpha. Standard ComfyUI mask. |
| `STRING` | Python str | Text, paths, JSON, brand info. |
| `INT` | Python int | Frame counts, dimensions, positions. |
| `FLOAT` | Python float | FPS, opacity, time values. |
| `BOOLEAN` | Python bool | Gate pass/fail signals. |

### 4.2 Node Categories

#### SOURCE NODES — Bring media into the graph

**Load Video**
```
Inputs:  video (file picker), max_frames, start_time, end_time, target_fps
Outputs: frames (IMAGE), width, height, fps, frame_count, video_info (STRING)
```
Decodes video to frame batch via FFmpeg subprocess. Probes metadata with ffprobe. Supports trim, FPS conversion. The frame batch is the universal currency — every downstream node works on IMAGE tensors.

**Load Video -> Frames**
```
Inputs:  video (file picker), frame_start, frame_end
Outputs: frames (IMAGE), frame_count
```
Surgical frame extraction. For when you need exactly frames 120-180 from a specific clip.

**Load Audio**
```
Inputs:  audio_file (file picker), start_time, end_time
Outputs: audio (AUDIO), audio_info (STRING)
```
Loads audio with optional trim. Audio travels as a dict referencing the file path — actual mixing/encoding happens at output via FFmpeg.

**Load Brand Kit**
```
Inputs:  brand_file (file picker — .json or .yaml)
Outputs: primary_color, secondary_color, accent_color, tone, rules_json, brand_info
```
Parses a brand definition file into typed outputs that wire into downstream nodes. Colors wire into text nodes, tint nodes. Tone wires into LLM nodes. Rules wire into Gate nodes. This is the human's persistent directive — design it once, every workflow inherits it.

---

#### AI NODES — Intelligence under constraint

**LLM Director**
```
Inputs:  prompt, context, provider (ollama|anthropic), model
Optional: system_prompt, temperature, rules_json, max_tokens
Outputs: response (STRING)
```
The AI brain. Takes a task prompt + context (brand info, asset list, whatever the human wires in) and returns a text decision. Supports local Ollama and cloud Claude API. The rules_json input accepts the output of Load Brand Kit's rules — the LLM sees the human's rules as hard constraints in its system prompt.

Critical design: the LLM Director never decides what to make. The human places it in the graph at a specific point — "generate a headline for this scene" or "pick which of these two clips fits better." The graph topology IS the constraint. The LLM fills a slot, it doesn't design the structure.

**LLM Text Writer**
```
Inputs:  topic, text_type (headline|summary|caption|call_to_action|custom), tone, max_words, provider, model
Outputs: text (STRING)
```
Specialized text generation. The tone input accepts the brand kit's tone output. Responds with ONLY the text — no preamble, no explanation. Designed to wire directly into Text Overlay or Lower Third nodes.

**Asset Tagger**
```
Inputs:  frames (IMAGE), tags, mood, quality_grade, notes
Outputs: frames (IMAGE), asset_metadata (STRING/JSON)
```
Attaches human-taught metadata to a frame batch. Also auto-computes brightness, dominant color, frame count, resolution. The metadata travels as a JSON string that downstream nodes can parse. This is the teaching action — the human says "this footage is hopeful b-roll, grade A, good for intros."

**Asset Selector**
```
Inputs:  option_a (IMAGE), option_b (IMAGE), criterion (brighter|darker|warmer|cooler|more_saturated)
Outputs: selected (IMAGE), selection_reason (STRING)
```
Computable asset selection. Wire two clip options in, specify a measurable criterion, get the better match. The selection_reason output explains why — wires into display nodes for human review. For more complex selection (semantic matching, mood matching), wire an LLM Director upstream and use its response to route.

---

#### COMPOSITION NODES — Assembly and effects

**Compose Scene Layers**
```
Inputs:  background (IMAGE), foreground (IMAGE), x_offset, y_offset, opacity
Optional: mask (MASK)
Outputs: composed (IMAGE)
```
Layer compositing. Place foreground on background at specified position with opacity. Handles frame count mismatch by holding the last frame of the shorter sequence. Optional mask for shaped overlays. This is the fundamental assembly operation — everything else is built on compositing.

**Concatenate Scenes**
```
Inputs:  scene_a (IMAGE), scene_b (IMAGE)
Outputs: frames (IMAGE), total_frames
```
Join two sequences end-to-end. Auto-resizes scene_b to match scene_a's resolution. The simplest edit: A then B.

**Crossfade Transition**
```
Inputs:  scene_a (IMAGE), scene_b (IMAGE), overlap_frames
Outputs: frames (IMAGE), total_frames
```
Linear crossfade. Overlaps the last N frames of A with the first N frames of B. The overlap region is alpha-blended. For hard cuts: set overlap_frames to 1.

**Text Overlay**
```
Inputs:  frames (IMAGE), text, font_size, font_color, x, y, start_frame, end_frame
Optional: font_name, bg_color, bg_padding, bg_opacity
Outputs: frames (IMAGE)
```
The workhorse. Burns text onto specific frame ranges with optional background box. Renders via Pillow. Supports multiline. The text input accepts STRING from any upstream source — hardcoded, from brand kit, from LLM, from file.

**Lower Third**
```
Inputs:  frames (IMAGE), primary_text, secondary_text, duration_frames, start_frame
Optional: bar_color, bar_opacity, text_color, accent_color, sizes, margin
Outputs: frames (IMAGE)
```
Broadcast-style name/title bar. Semi-transparent background, accent stripe on the left edge, fade in/out animation (first/last 10 frames). The accent_color input accepts brand primary from the brand kit. Wire once, every lower third in every workflow matches the brand.

**Title Card**
```
Inputs:  text, width, height, duration_frames, bg_color, text_color, font_size
Optional: subtitle, subtitle_size, subtitle_color, fade_frames
Outputs: frames (IMAGE)
```
Full-frame text card. For intros, outros, section headers, episode titles. Generates a frame batch from scratch — no input footage needed. Fade in/out from black. Center-aligned with optional subtitle in a second color.

**Ken Burns Effect**
```
Inputs:  image (IMAGE), duration_frames, zoom_start, zoom_end, direction, output_width, output_height
Optional: easing (linear|ease_in|ease_out|ease_in_out)
Outputs: frames (IMAGE)
```
Converts a still image into a video clip by applying animated crop/zoom. Eight direction presets including compound pan+zoom. Easing curves for natural motion. Essential for turning photos, screenshots, charts, and generated images into video footage.

**Apply Brand Colors**
```
Inputs:  frames (IMAGE), tint_color, intensity, target (shadows|midtones|highlights|all)
Outputs: frames (IMAGE)
```
Subtle color grading toward brand palette. Shifts the specified tonal range toward the tint color. Intensity should stay low (0.03-0.10) — this is a tint, not a filter. The tint_color input accepts brand colors from the brand kit. Wire brand primary into shadows for a consistent color signature across all productions.

**Audio Mix**
```
Inputs:  audio_a (AUDIO), audio_b (AUDIO), volume_a, volume_b
Outputs: mixed_audio (AUDIO)
```
Two-track audio mix via FFmpeg amix filter. Typically: background music at 0.2-0.3 volume + voiceover or sting at 1.0. Outputs to temp WAV for downstream use.

**Audio Fade In/Out**
```
Inputs:  audio (AUDIO), fade_in_seconds, fade_out_seconds
Outputs: audio (AUDIO)
```
Applies fade envelopes to audio tracks via FFmpeg afade filter.

---

#### CONTROL NODES — Human authority enforcement

**Rule Gate**
```
Inputs:  frames (IMAGE), on_fail (warn_and_pass|block)
Optional: min_brightness, max_brightness, min_frames, max_frames, min_width, min_height, custom_rules_json
Outputs: frames (IMAGE), gate_report (STRING), passed (BOOLEAN)
```
The centaur's guardrail. Checks frame batches against human-defined thresholds. On failure: either warns (passes frames through with a report) or blocks (returns black frames). The gate_report output is a human-readable string explaining what passed or failed and why.

The `passed` BOOLEAN output enables conditional routing in future workflow patterns — e.g., only publish if the gate passed, send to review queue if it didn't.

The custom_rules_json input accepts the rules output from Load Brand Kit, making brand rules automatic in every workflow that loads the brand kit.

**Future control nodes (v0.2+):**
- **Human Review Gate** — pauses execution, presents preview, waits for human approval via WebSocket
- **Feedback Capture** — records human corrections to a persistent log
- **Style Memory** — reads/writes learned preferences from accumulated feedback
- **Conditional Router** — routes IMAGE based on BOOLEAN from upstream gate

---

#### OUTPUT NODES — Final rendering

**Save Video**
```
Inputs:  frames (IMAGE), fps, filename_prefix, format (mp4|webm|gif), quality (high|medium|low|lossless)
Optional: audio (AUDIO)
Outputs: filepath (STRING)
```
Encodes frame batch to video file via FFmpeg. Supports H.264 (MP4), VP9 (WebM), and GIF. Quality presets map to CRF values. Optional audio mux with AAC encoding. Auto-increments filename to avoid overwrites. This is an OUTPUT_NODE — it terminates the graph.

---

## 5. Brand Kit System

### 5.1 Purpose

The brand kit is the human's persistent directive. It encodes identity, taste, and constraints into a portable file that any workflow can load. Design it once, every production inherits it automatically.

### 5.2 Schema

```yaml
# brand.yaml or brand.json
name: "Project Name"
purpose: "What this brand/project is for"

brand:
  colors:
    primary: "#DC143C"      # Main brand color
    secondary: "#1a1a2e"    # Background / dark color
    accent: "#f0e68c"       # Highlight / emphasis color
  fonts:
    heading: "Space Mono"   # Title font
    body: "IBM Plex Sans"   # Body text font
  tone: "warm, intellectual, hopeful"  # Passed to LLM nodes

style:
  pacing: "measured, 3-5 seconds per text card"
  transitions: "crossfade, occasional hard cut"
  text_overlay: "lower-third, white on dark scrim"
  music: "ambient, lo-fi"
  aspect_ratio: "16:9"
  duration_target: "30-60 seconds per episode"

rules:
  - "Never use stock footage of handshakes"
  - "Always include source attribution"
  - "Minimum 2 seconds on logo displays"
  - "B-roll minimum brightness 0.05"
  - "Hold quote text long enough to read twice"
```

### 5.3 How It Flows

```
Load Brand Kit
    |-> primary_color ----> Lower Third accent_color
    |-> primary_color ----> Apply Brand Colors tint_color
    |-> secondary_color --> Title Card bg_color
    |-> accent_color -----> Title Card subtitle_color
    |-> accent_color -----> Text Overlay font_color
    |-> tone -------------> LLM Text Writer tone
    |-> tone -------------> LLM Director context
    '-> rules_json -------> Rule Gate custom_rules_json
                        --> LLM Director rules_json
```

One Load Brand Kit node at the top of every workflow. Every downstream node that touches color, text style, or quality enforcement receives its directives from the brand. Change the brand file, re-run the workflow, everything updates.

### 5.4 Brand Kits Per Project

| Project | Brand File | Tone | Primary Color |
|---------|-----------|------|---------------|
| Comrade Claw | `comrade_claw_brand.json` | warm, intellectual, anti-authoritarian | #DC143C |
| Kombucha | `kombucha_brand.json` | philosophical, self-deprecating, wistful | #DC143C |
| Kindling | `kindling_brand.json` | gentle, curious, encouraging | TBD |
| MDP Caucus | `mdp_caucus_brand.json` | direct, professional, progressive | TBD |

---

## 6. Workflow Templates

### 6.1 What a Workflow Template Is

A saved ComfyUI workflow JSON file that encodes a complete production pipeline — every node, every wire, every parameter default. The human designs it on the canvas. Agents execute it via API.

Templates are the centaur's primary artifact. They embody the human's editorial decisions in a machine-executable format. The human controls the topology (what nodes, how they're wired). The AI controls the data flow (what values pass through at runtime).

### 6.2 Template Library

#### Daily Report Template
```
Brand Kit -> LLM Text Writer (headline from topic)
          -> Title Card (brand colors)
          -> Ken Burns (hero image)
          -> Lower Third (headline + source)
          -> Rule Gate (brightness, resolution)
          -> Audio (ambient + fade)
          -> Save Video
```
For: Comrade Claw daily output. Agent fills: topic, hero_image, source.

#### TikTok Episode Template
```
Brand Kit -> Title Card (episode title)
          -> Load Video (tick footage) -> Lower Third
          -> Load Video (tick footage) -> Text Overlay (quote)
          -> Load Video (tick footage) -> Text Overlay (quote)
          -> Crossfade chain
          -> End Card (next episode teaser)
          -> Brand Colors -> Rule Gate -> Audio -> Save Video
```
For: Kombucha Bathroom Saga episodes. Human fills: which ticks, which quotes.

#### Candidate Intro Template
```
Brand Kit -> Title Card (candidate name + district)
          -> Ken Burns (candidate photo)
          -> Lower Third (name + party)
          -> Text Overlay (key positions, staggered)
          -> Title Card (call to action)
          -> Rule Gate -> Save Video
```
For: MDP Progressive Caucus candidate videos. Human fills: candidate data.

#### Learning Recap Template
```
Brand Kit -> Title Card (session subject)
          -> Ken Burns (session screenshots)
          -> LLM Text Writer (summary from session log)
          -> Text Overlay (highlights)
          -> End Card (questions explored)
          -> Save Video
```
For: Kindling parent-facing session recaps. Agent fills: session log data.

### 6.3 Template Versioning

Templates live in git alongside the project code:

```
workflows/
├── comrade_claw/
│   ├── cc_daily_report_v1.json
│   └── cc_weekly_summary_v1.json
├── kombucha/
│   ├── bathroom_saga_ep_template.json
│   └── kombucha_ep1_workflow.json
├── kindling/
│   └── learning_recap_v1.json
└── mdp/
    └── candidate_intro_v1.json
```

Every change to a template is a git commit. The human reviews diffs. The agent uses the latest version on main. No surprises.

---

## 7. Agent Integration

### 7.1 ComfyUI API Contract

ComfyUI exposes `/prompt` (POST) which accepts a workflow JSON and queues it for execution. The workflow JSON is the same format saved from the canvas. Agents inject data by modifying node widget values before posting.

```
POST http://localhost:8188/prompt
Content-Type: application/json

{
  "prompt": { <workflow JSON with injected data> },
  "client_id": "comrade-claw-video-worker"
}
```

Response includes a `prompt_id` for tracking. Results appear in the output directory.

### 7.2 Comrade Claw Integration

CC's orchestrator-worker architecture already supports adding a `video_worker`:

```
CC Daily Wake Cycle:
  1. research_worker -> finds today's cooperative economics story
  2. writing_worker  -> produces Substack-ready text
  3. social_worker   -> produces Bluesky post
  4. video_worker    -> loads cc_daily_report template
                     -> injects headline, summary, source, hero image
                     -> POSTs to ComfyUI /prompt
                     -> video renders on 4090
                     -> output lands in file system
                     -> (future) auto-posts to Bluesky/YouTube
```

The video_worker is thin. It doesn't know anything about video editing. It knows how to:
1. Read a workflow JSON template
2. Find the right node IDs for data injection
3. Fill in today's values
4. POST to ComfyUI
5. Check if the output file appeared

All creative decisions — structure, pacing, brand, quality — live in the workflow template that the human designed.

### 7.3 Kindling Integration

Kindling's Hearth (parent-facing) persona could trigger recap videos after learning sessions:

```
Session complete -> Hearth generates session summary
                 -> Loads learning_recap template
                 -> Injects subject, highlights, questions
                 -> ComfyUI renders recap video
                 -> Presents to parent in Hearth interface
```

The video is invisible to the learner (per Kindling design). The parent sees a visual summary of what their child explored today.

### 7.4 Batch Production

For content series (Kombucha episodes, candidate intros), agents can iterate over data and produce multiple videos:

```python
for episode in series_plan:
    workflow = load_template("bathroom_saga_ep_template.json")
    inject(workflow, "title_node", episode.title)
    inject(workflow, "tick_1_node", episode.tick_files[0])
    inject(workflow, "tick_2_node", episode.tick_files[1])
    inject(workflow, "quote_1_node", episode.quotes[0])
    inject(workflow, "quote_2_node", episode.quotes[1])
    post_to_comfyui(workflow)
```

Five episodes of The Bathroom Saga from a single Python loop + one human-designed template.

---

## 8. Composition with Existing ComfyUI Nodes

CVS nodes don't replace existing ComfyUI capabilities — they compose with them. The 4090 is already running generative models. CVS adds the directing and editorial layer on top.

### 8.1 Integration Patterns

**AI Image Generation + CVS:**
```
FLUX/SD prompt -> Generated Image -> Ken Burns -> Lower Third -> Save Video
```
Generate a hero image for a story, animate it, add text, output video. The generated image never existed before — the LLM Director can even write the generation prompt based on the story topic.

**LTX-Video Generation + CVS:**
```
LTX-Video -> Generated Clip -> Rule Gate -> Text Overlay -> Crossfade with next scene -> Save Video
```
AI-generated b-roll passed through the Rule Gate before it enters the production. The gate checks brightness, resolution, and brand rules. If the generated clip is too dark or wrong aspect ratio, the gate blocks it.

**Upscaling + CVS:**
```
Load Video (low-res tick footage) -> Upscaler -> Lower Third -> Brand Colors -> Save Video
```
Kombucha's fisheye footage upscaled before text overlay. The upscaler is an existing ComfyUI node. CVS handles everything after upscaling.

**ControlNet + CVS:**
```
Load Image -> ControlNet (pose/depth) -> Generated Scene -> Ken Burns -> Title Card -> Concatenate -> Save Video
```
Use ControlNet to generate scenes that match a specific composition, then assemble them into a video with CVS editorial nodes.

### 8.2 The Pipeline Principle

Every node in ComfyUI speaks the same type language. IMAGE is IMAGE. CVS nodes consume and produce IMAGE tensors, so they compose freely with any other node that touches IMAGE. The brand kit, rule gate, and editorial nodes are the human's layer of control that wraps around whatever generative or processing pipeline is underneath.

---

## 9. Symbiotic Learning (v0.2)

### 9.1 The Feedback Loop

The centaur model's key differentiator is symbiotic learning — human corrections feed back into the system's behavior over time. CVS v0.1 captures feedback structurally (Rule Gate reports, gate_report strings). v0.2 makes it persistent.

### 9.2 Design

```
Human reviews output video
    |
"This clip is too dark for b-roll" (correction)
    |
Feedback Capture node logs: {type: "correction", target: "asset_selection",
  rule_proposed: "b-roll min brightness > 0.15", confidence: 0.5}
    |
Style Memory node reads accumulated feedback on next run
    |
LLM Director receives style memory as context
    |
Future asset selections respect learned brightness threshold
    |
Human reviews — brightness issue doesn't recur
    |
Confidence in brightness rule increases to 0.8
```

This is NOT prompt engineering. This is persistent, accumulating knowledge stored in the project's feedback log. The project gets smarter, not the model.

### 9.3 Implementation Plan

- **Feedback Capture Node** — records corrections to a JSONL file per project
- **Style Memory Node** — reads JSONL, summarizes patterns, outputs as context string
- **Human Review Gate** — pauses workflow, shows preview via WebSocket, waits for approval
- **Confidence Tracking** — rules start at 0.5, increase with confirmations, decrease with overrides

---

## 10. Current Infrastructure (Live)

### 10.1 What's Running Today

CVS is built on infrastructure that's already operational. The cc_flora pipeline (Kombucha cottagecore episodes) has produced 10 published episodes using the patterns CVS formalizes.

**Platform:** Windows 11, NVIDIA RTX 4090 (24GB VRAM), Python 3.10
**ComfyUI:** Running at `http://localhost:8188`, GPU-only mode, fast memory management
**Published to:** Bluesky @comradeclaw.bsky.social

### 10.2 Existing Kombucha Node Pack

The `comfyui-kombucha-pipeline` custom node pack is the v0 precursor to CVS. It provides 7 nodes that are being folded into the CVS architecture:

| Node | Purpose | CVS Successor |
|------|---------|---------------|
| **ParseTickLog** | Extract narrative from tick markdown | Source Node (specialized) |
| **ElevenLabsTTS** | Voice synthesis via ElevenLabs API | Audio Node (v0.4 TTS) |
| **MotionClip** | Remove static frames from rover footage | Source Node (specialized) |
| **VerticalFrameComposite** | 1080x1920 canvas with blurred fill | Compose Scene Layers |
| **TextOverlay** | TikTok-safe-zone text rendering | Text Overlay (generalized) |
| **PadToAudio** | Match video duration to audio | Composition Node |
| **CosyMotes** | Bokeh dust particle overlay | Composition Node (effects) |

**Audio Engine** (`audio_engine.py`):
- A-minor additive synthesis (A2, C3, E3, A3 root + A4/C5/E5 shimmer)
- LFO modulation, binaural stereo panning, mood-dependent frequency coloring
- Music-box chimes placed in narration gaps
- Loudness normalization: `ffmpeg loudnorm=I=-14:TP=-1:LRA=11`

### 10.3 cc_flora Episode Catalog (Season 1)

| Ep | Title | Ticks | Status |
|----|-------|-------|--------|
| 01 | First Light | 0001-0003 | Published |
| 02 | The Bigger Room | 0004,0006-0008 | Published |
| 03 | Moon | 0010,0012,0013 | Published |
| 04 | Carried Home | 0014-0018 | Published |
| 05 | Same Frame | 0019-0024 | Published |
| 06 | Three Centimeters | 0032-0035 | Published |
| 07 | Ping-Pong | 0036,0037 | Published |
| 08 | The Threshold | 0038,0039 | Published |
| 09 | The Hallway | 0041,0042,0044 | Published |
| 10 | The Patience of Rooms | 0046,0048,0049 | Published |

**Canon folder:** `E:/AI/CVS/ComfyUI/output/cc_flora_canon/`

### 10.4 Installed Custom Node Packs

| Pack | Purpose |
|------|---------|
| comfyui-kombucha-pipeline | Kombucha video production (CVS v0 precursor) |
| comfyui-videohelpersuite | Video I/O (VHS_LoadVideoPath, VHS_VideoCombine) |
| deforum-comfy-nodes | Deforum animation engine |
| ComfyUI-AnimateDiff-Evolved | AnimateDiff video synthesis |
| comfyui_controlnet_aux | ControlNet preprocessors |
| comfyui-impact-pack | Utility nodes |
| comfyui-kjnodes | KJ utility nodes |
| Nvidia_RTX_Nodes_ComfyUI | RTX-optimized nodes |
| ComfyUI_FluxMod | Flux model support |

### 10.5 Model Library

Resolved via `extra_model_paths.yaml` pointing to `E:/AI/ComfyUI/`:

| Model | Purpose |
|-------|---------|
| 4x-UltraSharp.pth | 4x GPU upscaling (spandrel) |
| gemma_3_12B_it_fp4_mixed.safetensors | Gemma 3 VLM (12B, image-to-text) |
| qwen_3_4b.safetensors | Qwen 3 VLM (4B, image-to-text) |
| llava_llama3_fp8_scaled.safetensors | LLaVA-LLaMA3 VLM (8B) |
| t5xxl_fp8_e4m3fn.safetensors | T5-XXL text encoding |
| clip_l.safetensors | CLIP text encoding |
| Various checkpoints, ControlNets, LoRAs, VAEs | Generation and conditioning |

---

## 11. File System

### 11.1 CVS Node Pack Structure (Target)

```
ComfyUI/custom_nodes/ComfyUI-CentaurVideo/
├── __init__.py           # Node registration
├── requirements.txt      # Python dependencies
├── README.md
├── nodes/
│   ├── __init__.py
│   ├── video_load.py     # Load Video, Load Video->Frames
│   ├── video_save.py     # Save Video
│   ├── video_compose.py  # Compose Layers, Concatenate, Crossfade
│   ├── text_overlay.py   # Text Overlay, Lower Third, Title Card
│   ├── brand_kit.py      # Load Brand Kit, Apply Brand Colors
│   ├── llm_director.py   # LLM Director, LLM Text Writer
│   ├── asset_tagger.py   # Asset Tagger, Asset Selector
│   ├── rule_gate.py      # Rule Gate
│   ├── ken_burns.py      # Ken Burns Effect
│   └── audio_mix.py      # Load Audio, Audio Mix, Audio Fade
└── examples/
    ├── kombucha_brand.json
    └── comrade_claw_brand.json
```

### 11.2 Project Structure (per production project)

```
projects/kombucha/
├── brand/
│   └── kombucha_brand.json
├── workflows/
│   ├── bathroom_saga_ep_template.json
│   ├── kombucha_ep1_workflow.json
│   └── ...
├── assets/
│   ├── video/
│   ├── audio/
│   └── images/
├── output/
│   └── ...
└── feedback/
    └── feedback.jsonl    # (v0.2) accumulated corrections
```

### 11.3 Current Repository Structure

```
E:\AI\CVS\
├── .env                                # API keys (gitignored)
├── .gitignore
├── CVS_ARCHITECTURE.md                 # This document
├── run_comfyui.bat                     # Launch script
│
├── ComfyUI\                            # ComfyUI server (own git repo)
│   ├── main.py, execution.py, server.py, nodes.py
│   ├── extra_model_paths.yaml
│   ├── CLAUDE.md
│   ├── custom_nodes\
│   │   ├── comfyui-kombucha-pipeline\  # CVS v0 precursor
│   │   └── (8 other node packs)
│   ├── models\ -> E:/AI/ComfyUI/      # Shared model library
│   └── output\
│
├── comfyui-config\                     # Git-tracked copies of our ComfyUI files
│   ├── CLAUDE.md
│   ├── extra_model_paths.yaml
│   └── kombucha-pipeline\              # Full node pack source
│
├── ComfyUI_Workflows\                  # Saved workflow JSONs
│
├── scripts\                            # Python orchestrators & episode scripts
│   ├── run_workflow.py                 # Generic ComfyUI API submitter
│   ├── run_deforum.py                  # Frame-by-frame Deforum executor
│   ├── cc_flora_ep01-10_*.py           # Episode scripts (Season 1)
│   ├── cc_flora_complete_process.md    # Full production guide
│   └── (utility scripts, workflow JSONs)
│
└── .claude\                            # Agent definitions & memory
    ├── agents\
    │   ├── flora.md / flora2.md        # cc_flora production agents
    │   ├── virgil-comfyui-pipeline.md  # Pipeline executor
    │   └── comfyui-output-janitor.md   # Output cleanup
    └── agent-memory\
```

---

## 12. Development Roadmap

### v0.1 — CURRENT (Root Node Pack)
- [x] Source nodes: Load Video, Load Video->Frames, Load Audio, Load Brand Kit
- [x] AI nodes: LLM Director, LLM Text Writer, Asset Tagger, Asset Selector
- [x] Composition nodes: Compose Layers, Concatenate, Crossfade, Text Overlay, Lower Third, Title Card, Ken Burns, Apply Brand Colors, Audio Mix, Audio Fade
- [x] Control nodes: Rule Gate
- [x] Output nodes: Save Video
- [x] Brand kit schema and loader
- [x] Kombucha Episode 1 workflow
- [x] Kombucha brand kit

### v0.2 — Symbiotic Learning
- [ ] Human Review Gate (pause + preview + approve via WebSocket)
- [ ] Feedback Capture node (corrections -> JSONL)
- [ ] Style Memory node (accumulated feedback -> LLM context)
- [ ] Confidence tracking on learned rules
- [ ] Conditional Router (route IMAGE based on gate BOOLEAN)

### v0.3 — Multi-Format + Batch
- [ ] Multi-format output node (16:9 + 9:16 + 1:1 from one workflow)
- [ ] Batch render node (iterate over data array)
- [ ] Template variable injection node (clean API for agent data injection)
- [ ] Progress reporting via WebSocket

### v0.4 — Publishing + Integration
- [ ] Bluesky publish node
- [ ] YouTube upload node
- [ ] Subtitle generation (Whisper transcription -> timed text overlay)
- [ ] TTS node (Piper/Coqui for optional narration)
- [ ] Scene detection node (PySceneDetect for auto-segmenting footage)

### v0.5 — Advanced Directing
- [ ] Storyboard node (visual layout of scene sequence before rendering)
- [ ] A/B comparison node (render two variations, present side-by-side)
- [ ] Music generation node (MusicGen for ambient soundtracks)
- [ ] Style transfer node (apply visual style from reference video)
- [ ] ComfyUI App Mode interface (simplified directing view for non-technical users)

---

## 13. Use Cases at Launch

### 13.1 Kombucha: The Bathroom Saga
Five TikTok episodes produced from 62 ticks of rover footage. Brand kit defines the philosophical robot voice. Template handles episode structure. Human picks ticks and quotes. Ken Burns animates stills. Lower thirds identify ticks. Rule Gate enforces brightness floors and hold times. Audio fades ambient lo-fi.

### 13.2 Comrade Claw: Daily Video Reports
Automated daily video summaries of cooperative economics research. CC's video_worker fills a template with today's headline, summary, and source. ComfyUI renders on the 4090 during off-peak hours. Brand kit ensures every video is visually consistent. Rule Gate catches anything out of spec before it ships.

### 13.3 MDP Progressive Caucus: Candidate Intros
Template-driven candidate introduction videos. Human fills: name, photo, district, key positions, call to action. Ken Burns animates the photo. Lower third identifies the candidate. Title cards frame the positions. Brand kit ensures party visual identity. Batch render for multiple candidates.

### 13.4 Kindling: Learning Recaps
Parent-facing visual summaries of learning sessions. Agent fills: session subject, highlights, questions explored. Ken Burns on session screenshots. LLM Text Writer generates accessible summary text. Brand kit keeps it warm and encouraging. Output is for the parent, invisible to the learner.

---

## 14. Design Principles (Restated as Commitments)

1. **The human designs the graph. The AI runs the graph.** The topology is the directive. The data flow is the execution. These never swap.

2. **Brand kits are persistent directives, not per-session prompts.** Design once, apply everywhere. The brand kit is the human's taste encoded as data.

3. **Rule Gates are non-negotiable.** If the human says minimum brightness is 0.05, every frame in every production in every workflow that loads that brand kit gets checked. The AI cannot override rules. It can only pass or fail them.

4. **Templates are the centaur's primary artifact.** A saved workflow IS a production system. Version it, share it, iterate it, hand it to an agent. The template embodies editorial judgment in machine-executable form.

5. **Agents are consumers, not designers.** CC can fill a template and POST it to ComfyUI. CC cannot design a new template, add nodes, or change the graph topology. That's the human's job. When agents start designing workflows, the centaur becomes a self-automator — and the research says that's when quality collapses.

6. **Compose, don't replace.** CVS nodes work alongside every other ComfyUI node. The brand kit wraps generative pipelines, it doesn't replace them. The Rule Gate inspects AI-generated content, it doesn't prevent its creation.

7. **The graph is the documentation.** A workflow JSON IS the production spec. It shows exactly what happens, in what order, with what parameters. No separate spec needed. No drift between design and execution. Open the workflow, read the graph.
