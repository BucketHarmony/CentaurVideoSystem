# CVS Demo Media Kit

Minimal demo assets for testing the Centaur Video System without needing real production footage.

## Contents

```
demo/
  assets/
    test_card.py          — Generator script (requires Pillow)
    test_card_720p.png    — 1280x720 test card (generated)
    test_card_1080p.png   — 1920x1080 test card (generated)
    sample_video.mp4      — 5-second 720p test video (generated via ffmpeg)
  brand/
    demo_brand.json       — Sample brand kit with colors, fonts, pacing rules
  workflows/
    (placeholder for future CVS workflow definitions)
  README.md               — This file
```

## Generating the Test Assets

### Test card images

```bash
pip install Pillow
python demo/assets/test_card.py
```

This creates `test_card_720p.png` and `test_card_1080p.png` in `demo/assets/`.

### Sample video

Requires ffmpeg on your PATH:

```bash
ffmpeg -f lavfi -i "color=c=0x1a1a2e:s=1280x720:d=5,format=yuv420p" \
  -vf "drawtext=text='CVS DEMO':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2,drawtext=text='%{pts\:hms}':fontcolor=0xf0e68c:fontsize=24:x=(w-text_w)/2:y=(h/2)+40" \
  -c:v libx264 -pix_fmt yuv420p -t 5 -y demo/assets/sample_video.mp4
```

## How These Assets Fit into CVS

| Asset | CVS Use Case |
|---|---|
| `test_card_720p.png` | Input to image-processing nodes (resize, color-grade, overlay) |
| `test_card_1080p.png` | Verifying 1080p pipeline paths and quality checks |
| `sample_video.mp4` | Input to video nodes (trim, concat, transition, upscale) |
| `demo_brand.json` | Loaded by brand-aware nodes to enforce colors, pacing, and rules |

### Typical test flow

1. Load `test_card_720p.png` as a source image node.
2. Apply a color-grade node configured from `demo_brand.json` colors.
3. Composite with text overlay using brand fonts.
4. Encode to `sample_video.mp4` format and verify output.
5. Run CVS quality-check nodes against the brand rules.
