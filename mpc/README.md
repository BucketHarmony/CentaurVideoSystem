# MPC — Michigan Progressive Caucus Social Media Pipeline

Greenfield video production pipeline for the Michigan Progressive Caucus. Produces vertical (1080x1920) social videos for TikTok, Reels, and Shorts with on-brand styling, burned-in captions, and citation-grade lower-thirds.

## Status

**Phase 0 — Brand kit + demo template** (current)
**Phase 1 — Asset ingest, transcription, motion scan** (planned)
**Phase 2 — LLM categorization & tagging** (planned)
**Phase 3 — Hook scoring + composition** (planned)
**Phase 4 — Render & per-platform exports** (planned)

## Layout

```
mpc/
  brand/                       # style kit
    BRAND_KIT.md               # reverse-engineered brand guide
    palette.json               # machine-readable colors + fonts
    logo_wide.png              # primary lockup
  templates/                   # render templates
    template_30s_demo.py       # 30s brand-fit proof
```

Renders land in `E:/AI/CVS/ComfyUI/output/mpc/` to match existing output convention.
Entry-point scripts will live at `E:/AI/CVS/scripts/mpc_*.py` to match the existing `cc_*.py` convention.

## Quick Start

```bash
# Render the demo template (proves brand fit, no source footage needed)
python E:/AI/CVS/mpc/templates/template_30s_demo.py
# Output: E:/AI/CVS/ComfyUI/output/mpc/template_30s_demo.mp4
```
