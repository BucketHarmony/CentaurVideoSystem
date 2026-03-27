# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ComfyUI is a node-based visual AI workflow engine. Users build computation graphs of nodes in a browser UI; the server executes them with optimized GPU memory management.

## Common Commands

```bash
# Run the server
python main.py                          # GPU mode, http://127.0.0.1:8188
python main.py --cpu                    # CPU-only mode
python main.py --listen 0.0.0.0         # Listen on all interfaces
python main.py --port 8080              # Custom port

# Run all tests
python -m pytest tests-unit/            # Unit tests only
python -m pytest tests/ -m execution    # Integration/execution tests (spins up own server)
python -m pytest tests/ -m inference    # Inference tests (requires models)

# Run a single test file or test
python -m pytest tests-unit/comfy_test/graph_utils_test.py -v
python -m pytest tests-unit/comfy_test/graph_utils_test.py::test_name -v

# Quick CI smoke test (starts server, validates startup, exits)
python main.py --quick-test-for-ci

# Install dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
pip install -r tests-unit/requirements.txt  # For running tests
```

## Architecture

### Startup & Execution Flow

`main.py` → creates `PromptServer` (aiohttp web server) → spawns `prompt_worker` thread → worker pulls from `PromptQueue` → `PromptExecutor.execute()` processes the graph.

### Core Components

- **`execution.py`** — `PromptExecutor` class. Receives a prompt (node graph as JSON), topologically sorts it via `ExecutionList`, executes nodes in order, manages caching via `CacheSet`.
- **`server.py`** — `PromptServer` singleton. aiohttp server with WebSocket support for real-time progress updates (`executing`, `executed`, `progress`, `preview_image` events).
- **`nodes.py`** — All built-in node definitions and the node registration system. Nodes are registered in `NODE_CLASS_MAPPINGS` dict.
- **`comfy/model_management.py`** — GPU/VRAM management with automatic model loading/unloading. Handles NVIDIA, AMD, Intel, Apple Silicon, and CPU backends.
- **`folder_paths.py`** — Path resolution for models, inputs, outputs. Maps folder type names (e.g., "checkpoints", "loras") to filesystem search paths.

### Execution Pipeline Detail

1. Client submits prompt JSON via `/prompt` endpoint
2. `PromptQueue` stores it with priority
3. `prompt_worker` thread dequeues and calls `PromptExecutor.execute()`
4. `DynamicPrompt` validates and expands the graph (handles ephemeral/expansion nodes)
5. `ExecutionList` topologically sorts nodes
6. Each node: resolve inputs from upstream cache → call node's execute method → cache outputs
7. Progress sent to clients over WebSocket

### Node System (Two API Versions)

**V1 (legacy, most existing nodes):**
```python
class MyNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",)}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    def run(self, image):
        return (result,)
```

**V3 (modern, schema-based):**
```python
class MyNode(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="MyNode",
            inputs=[io.Image.Input("image")],
            outputs=[io.Image.Output()])
    @classmethod
    def execute(cls, **kwargs):
        return io.NodeOutput(result)
```

### Caching Strategies

Configured via `CacheSet` in `comfy_execution/caching.py`:
- **CLASSIC** — Hash-based input signature caching (default)
- **LRU** — Size-limited eviction
- **RAM_PRESSURE** — Evicts when system memory is low

Node cache invalidation: V1 uses `IS_CHANGED()`, V3 uses `fingerprint_inputs()`.

### Custom Nodes

Placed in `custom_nodes/` directory. Each must export `NODE_CLASS_MAPPINGS` (V1) or `NODES_LIST` (V3). Prestartup scripts (`prestartup_script.py`) run before server initialization.

### Key Subsystems

- **`comfy_execution/`** — Graph utilities, caching, async execution support
- **`comfy_api/`** — Versioned API with typed I/O (`latest/`, `v0_0_1/`, `v0_0_2/`)
- **`api_server/`** — REST endpoint handlers (routes, services, utils)
- **`comfy_extras/`** — Additional built-in nodes (ControlNet, IP-Adapter, upscalers, etc.)
- **`app/`** — User management, model file management, database (optional SQLAlchemy/Alembic)

## Testing

- **`tests-unit/`** — Fast unit tests, no server needed. Use `pytest tests-unit/`.
- **`tests/execution/`** — Integration tests marked `@pytest.mark.execution`. These start their own ComfyUI server subprocess on port 8188 — don't run another instance simultaneously.
- **`tests/inference/`** — Marked `@pytest.mark.inference`. Require model checkpoints to be present.
- pytest config is in `pytest.ini`. `pythonpath = .` is set so imports work from repo root.

## Linting

Ruff is configured in `pyproject.toml` with rules: E, W, F, N, S. Line length 200. Run with `ruff check .`.

## Kombucha Pipeline

Custom node pack at `custom_nodes/comfyui-kombucha-pipeline/` for producing TikTok vertical videos from the Kombucha robot project (`E:/AI/Kombucha`). See `custom_nodes/comfyui-kombucha-pipeline/README.md` for full documentation.

**Nodes:** ParseTickLog, ElevenLabsTTS, MotionClip, VerticalFrameComposite, TextOverlay, PadToAudio

**Run via API** (no browser needed) — submit prompt dicts to `POST /prompt`, poll `GET /history/{id}`.

**Series bible:** `E:/AI/Kombucha/series_bible.md`
**Narrative:** `E:/AI/Kombucha/series_narrative.md`
