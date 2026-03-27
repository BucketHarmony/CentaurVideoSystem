# Quick Start

Get CVS running in 10 minutes.

## Prerequisites

- NVIDIA GPU with 8GB+ VRAM
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) in your system PATH
- Git

Verify FFmpeg:
```bash
ffmpeg -version
```

## 1. Clone and Install ComfyUI

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

## 2. Install CVS Node Pack

Copy the node pack into ComfyUI's custom nodes:

```bash
cp -r ../comfyui-config/kombucha-pipeline ComfyUI/custom_nodes/comfyui-kombucha-pipeline
```

Install dependencies:
```bash
pip install elevenlabs requests python-dotenv scipy spandrel pillow torchaudio
pip install "numpy>=1.21.6,<1.28.0"
```

## 3. Configure Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE=your_voice_id_here
ELEVENLABS_MODEL=eleven_multilingual_v2
```

Only ElevenLabs is required for TTS. Bluesky credentials are optional (for publishing).

## 4. Start ComfyUI

```bash
cd ComfyUI
python main.py --gpu-only --fast --listen
```

Verify it's running:
```bash
curl http://localhost:8188/system_stats
```

You should see GPU info in the response.

## 5. Run the Demo

Generate demo test assets:
```bash
cd demo
python assets/test_card.py
```

This creates test card images and verifies your environment is working.

## 6. Submit a Workflow

Use the generic workflow submitter to test the API:

```python
python scripts/run_workflow.py scripts/workflow_01_basic_txt2img.json
```

This submits a basic txt2img workflow to ComfyUI and polls for completion.

## 7. Design Your First Workflow

Open ComfyUI in your browser at `http://localhost:8188` and:

1. **Load a brand kit** — Drag `demo/brand/demo_brand.json` into the canvas (once Brand Kit nodes are available), or reference it in your scripts
2. **Add source nodes** — Load Video, Load Image
3. **Add composition** — Text Overlay, Lower Third, Ken Burns
4. **Add a Rule Gate** — Set minimum brightness, resolution checks
5. **Save as JSON** — This is your workflow template

## What's Next

- Read [GUIDE.md](GUIDE.md) for workflow design patterns, brand kit authoring, and agent integration
- Read [CVS_ARCHITECTURE.md](CVS_ARCHITECTURE.md) for the complete system design
- Explore `scripts/` for episode production examples
- Check `demo/` for sample assets and brand kits

## Troubleshooting

**numpy/scipy error on startup:**
```bash
pip install "numpy>=1.21.6,<1.28.0"
```

**Port 8188 already in use:**
```bash
python main.py --port 8189
```

**CUDA out of memory:**
Remove `--gpu-only` flag to allow CPU offloading, or reduce batch sizes in your workflow.
