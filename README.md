# Centaur Video System (CVS)

A **human-directed, AI-executed video production framework** built on [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

CVS transforms ComfyUI from a generative media tool into a full video production pipeline where the human designs workflow graphs, defines brand identity, and sets quality rules — and the AI executes rendering, compositing, text generation, and encoding within those constraints.

The node graph IS the centaur: every wire the human draws is a directive, every node the AI runs is execution under constraint.

## The Centaur Model

Based on collaboration research from Harvard (Saghafian, 2023) and MIT/Harvard/Warwick (Candelon/Kellogg/Lifshitz, 2026):

| Dimension | Human | AI |
|-----------|-------|-----|
| **What** gets made | Always | Never |
| **Strategic how** (brand, style, rules) | Always | Never |
| **Tactical how** (rendering, compositing) | Override points | Execution |
| **Quality** | Define rules, review | Enforce rules, check |

CVS prevents three anti-patterns: **Self-Automator** (AI decides everything), **Full Manual** (human edits every frame), and **Cyborg Blur** (no clear boundary). The workflow graph enforces the boundary — design before execution, review after.

## What's Inside

```
CVS/
├── CVS_ARCHITECTURE.md          # Complete system design document (v1.0)
├── comfyui-config/
│   └── kombucha-pipeline/       # Custom ComfyUI node pack (v0 precursor)
├── scripts/                     # Episode scripts, orchestrators, production guides
├── demo/                        # Demo assets, brand kit, test media
├── ComfyUI_Workflows/           # Saved workflow JSONs
└── .claude/agents/              # AI agent definitions (Flora, Virgil, Janitor)
```

## Key Components

### Node Pack (v0.1 Spec)

| Category | Nodes |
|----------|-------|
| **Source** | Load Video, Load Video->Frames, Load Audio, Load Brand Kit |
| **AI** | LLM Director, LLM Text Writer, Asset Tagger, Asset Selector |
| **Composition** | Compose Layers, Concatenate, Crossfade, Text Overlay, Lower Third, Title Card, Ken Burns, Apply Brand Colors, Audio Mix, Audio Fade |
| **Control** | Rule Gate (human-defined quality enforcement) |
| **Output** | Save Video (H.264/VP9/GIF via FFmpeg) |

### Brand Kit System

Design once, apply everywhere. A YAML/JSON file that encodes colors, fonts, tone, and rules — wired into every workflow automatically.

```yaml
brand:
  colors:
    primary: "#DC143C"
    secondary: "#1a1a2e"
    accent: "#f0e68c"
  tone: "warm, intellectual, hopeful"
rules:
  - "Minimum brightness 0.05"
  - "Hold text cards minimum 3 seconds"
```

### Agent Integration

Agents (Comrade Claw, Kindling, etc.) produce video by filling human-designed workflow templates and POSTing to ComfyUI's API. The agent fills slots — it never designs the graph.

```python
workflow["6"]["inputs"]["text"] = todays_headline
requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for installation and first run.

See [GUIDE.md](GUIDE.md) for detailed usage, workflow design, and brand kit authoring.

See [CVS_ARCHITECTURE.md](CVS_ARCHITECTURE.md) for the complete system design document.

## Requirements

- **GPU:** NVIDIA with 8GB+ VRAM (24GB recommended)
- **OS:** Windows 10/11 or Linux
- **Python:** 3.10+
- **ComfyUI:** Latest version
- **FFmpeg:** In system PATH

## Status

**MYCELIUM** — Architecture defined, root node pack built, host infrastructure live. 10 episodes produced with the v0 pipeline (Kombucha cc_flora series).

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.1** | Root node pack (source, AI, composition, control, output nodes) |
| **v0.2** | Symbiotic learning (feedback capture, style memory, human review gate) |
| **v0.3** | Multi-format + batch rendering |
| **v0.4** | Publishing nodes (Bluesky, YouTube, TTS, subtitles) |
| **v0.5** | Advanced directing (storyboard, A/B comparison, App Mode) |

## Authors

**Bucket** — Human director, system designer, editorial authority
**Claude** — AI executor, code implementation, production engine

## License

This project is provided as-is for educational and reference purposes. The centaur model, brand kit system, and workflow template patterns are free to adapt for your own projects.
