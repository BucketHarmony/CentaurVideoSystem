# Michigan Progressive Caucus — Brand Kit (Reverse-Engineered)

**Source:** https://www.miprogressivecaucus.com/ (logo extracted 2026-04-25)
**Status:** UNOFFICIAL — colors estimated from logo PNG. Confirm hex codes with caucus comms before high-stakes publishing.

## Logo

A stylized **bird (sparrow/finch)** standing on stylized water lines. The bird's body is rendered as a flag-like pattern with a white star on the wing/back area and horizontal color bands (sky blue head, pink mid, deep magenta belly). Wordmark sits to the right: "MICHIGAN DEMOCRATIC PARTY" in pink (smaller, condensed) stacked above "PROGRESSIVE CAUCUS" in sky blue (large, bold).

- **Wide lockup:** `logo_wide.png` (this directory) — primary use
- **Stacked / square variant:** NOT YET OBTAINED — needed for vertical safe-zones in 1080x1920 frames

## Color Palette (estimated)

| Role | Name | Hex | RGB | Usage |
|------|------|-----|-----|-------|
| Primary | Sky Blue | `#5CB7DD` | 92, 183, 221 | Wordmark, water lines, primary CTAs, lower-third backgrounds |
| Secondary | Soft Pink | `#F4A8C0` | 244, 168, 192 | Tagline text, accents, friendly callouts |
| Accent | Deep Magenta | `#8B3A52` | 139, 58, 82 | Depth/weight, drop shadows, caption outlines |
| Light | White | `#FFFFFF` | 255, 255, 255 | Backgrounds, star, text on dark |
| Dark | Near-Black | `#1A1A1A` | 26, 26, 26 | Body text on light backgrounds |

The palette is **soft and warm** — distinctly NOT the harsh navy/red of standard partisan branding. Preserve this in social content; do not introduce harsh reds/navys.

## Typography

**Wordmark:** bold, all-caps, geometric sans-serif (looks like Gotham/Proxima Nova family at heavy weight).

**Recommended substitutes (free, locally available):**
- Headlines: **Montserrat Black / ExtraBold** — installed at `C:/Windows/Fonts/Montserrat.otf`
- Body / sub: **Montserrat Regular** or **Arial Bold** as fallback
- Mono / data: **Consolas** if monospace is needed
- Avoid: Georgia, serifs in general — stay sans-serif to match brand

## Voice & Tone

Site CTA language: "push boundaries with us... forge something extraordinary together."
- Aspirational + collaborative
- Invite-in tone, NOT call-out tone
- Warm progressive — community-first
- Friendly bird mascot softens political content; lean into that visual language

## Social Presence

| Platform | Handle / URL |
|----------|--------------|
| Instagram | @michiganprogressive |
| Facebook | MDPProgressiveCaucus |
| Email | michiganprogressivecaucus@gmail.com |
| Website | miprogressivecaucus.com |
| TikTok | NOT FOUND — pipeline target is greenfield |
| X / YouTube | NOT FOUND |

## Logo Placement Rule (REQUIRED)

**Whenever the logo sits over a non-white background — solid color OR gradient — it MUST sit on a full-width white horizontal bar.**

- The wordmark and bird artwork were designed against white. The alpha-knockout PNG (`logo_wide_alpha.png`) has antialiased edges that fringe visibly against any colored backdrop.
- Standard bar: full canvas width × `(logo_height + 80px)`, `#FFFFFF`, no border. The bar reads as an "official banner" header — a useful side-effect for civic/political content.
- The only exception is when the bg is already pure white — then the bar is a no-op and can be omitted.
- In code (`template_30s_demo.py`): pass `bar_color=C["white"], bar_padding=40` on every `{"kind": "logo", ...}` block whose backdrop isn't white.

**Why this is a rule and not a suggestion:** alpha fringing is subtle on a desktop monitor but very visible on a phone screen at TikTok contrast levels. Skipping the bar was the most consistent visual bug in the v1/v2 demo iterations.

## Vertical Video Safe Zones (1080x1920)

For TikTok / Reels / Shorts, keep critical content within these bounds:
- **Top 150px** — clear (app tabs, profile pic overlay)
- **Bottom 480px** — clear (caption bar, CTA button, engagement bar)
- **Right 120px** — clear (like/comment/share icons)
- **Safe content area:** roughly `(40, 200)` to `(960, 1440)`

## Production Notes (lessons from `mpc_ep_romulus.py`)

### Phone-source rotation must be baked before MoviePy reads it

Phones record to a landscape sensor and tag the file with `rotation=-90` so players know to display upright. **MoviePy 1.0.3 silently ignores this metadata**: `clip.rotation` reports `0`, `clip.size` reports the un-rotated buffer dimensions, and frames come back visually upright but stretched into the original landscape aspect — subjects look squat and wide.

**Symptom in finished video:** people look "squished vertically" / "smushed" — the give-away that we're shipping aspect-distorted footage.

**Fix:** detect rotation with `ffprobe -show_entries stream_side_data=rotation` and pre-bake any rotated source into a cached re-encoded copy with `ffmpeg -i <src> -metadata:s:v rotate=0 ...` (default ffmpeg autorotate handles the actual pixels correctly). Implemented in `mpc_ep_romulus.py::_rotation_baked_path` — cache lives under `ComfyUI/output/mpc/_rot_cache/`. Always run unfamiliar phone footage through this helper before passing to MoviePy.

### Caption strips must be dynamically sized + bottom-anchored

A fixed-height transcript strip (e.g. 200px) silently clips multi-line captions at the **top** because `wrap()` produces N lines and `block_h = N * line_h` overflows when N ≥ 3. The clipped line is the FIRST one, which is the most visible regression on a phone screen.

**Pattern (in `render_caption_strip` + `make_caption_clips`):** size the strip image to fit the wrapped text plus padding/stroke, then position it so its **bottom edge** anchors at a fixed `CAPTION_BOTTOM` y. Multi-line captions then grow upward into the video well rather than down into the TikTok UI safe zone.

### Video-first layout = wells eat ~84% of the frame

For pure-quote or quote-driven content (Romulus, candidate testimony, witness clips), captions overlay the video well rather than sitting in their own band. Current well dimensions: `WELL_TOP=140`, `WELL_BOTTOM=1750`. CTA scenes use a split layout with chrome compressed to the top 720px and chant footage filling 720..1920.

### Source-audio + synth-VO mixing

Three-track architecture: harmonic hum bed (50% level), synth VO (100%), source-audio (100% normally, ducked to 50% under VO via an attack/release envelope follower in `vo_duck_envelope`). Native sync sound (e.g. a speaker's voice from clip audio) replaces synth VO entirely on the FIGHT beat — set `audio_in/audio_out` on the FOOTAGE entry to trim it cleanly to a sentence boundary.

## Open Questions / Brand Gaps

1. Official hex codes — current values are eyeballed from a JPEG-compressed PNG (±5% per channel)
2. Official typeface — guessing Gotham/Proxima; could be wrong family
3. FEC / MDP disclaimer requirements — does caucus content need a "Paid for by..." overlay?
4. Square / stacked logo variant — wide lockup is hard to read at small vertical sizes
5. Approved photography style guide — any rules on photo treatment, color grades, etc.?
