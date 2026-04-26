# cc_flora drift audit — Phase 0 of cvs_lib lift (cc_flora wave)

Generated 2026-04-26. Scratch file; deleted in Phase 7.

## TL;DR

The "ep10 is the latest tuned version" hypothesis from the plan is
**only half right**. ep10 holds the canonical for the *cool/shadow*
lineage (ep05–ep10), but ep01–ep04 + the 30s/masterpiece variants
form a deliberate *warm/cream* lineage with a different look.
Collapsing both to ep10 would be a creative regression, not a drift
fix.

**Strategy:** lib carries **two variants** for `cottagecore_grade`,
`creamy_vignette`, and `soft_bloom`:
- `variant="cool"` (default; matches ep10) — for ep05–ep10
- `variant="warm"` — for ep01–ep04, cc_flora_30s, cc_flora_masterpiece,
  dream_sequence

Hookshot family (`vignette`, hookshot's `cottagecore_grade`) is a
third dialect — see Phase 6 strategy below.

## cottagecore_grade — 23 copies

Two distinct lineages within cc_flora:

| Lineage | Members | shadow lift | range compress | brightness | contrast | saturation |
|---|---|---|---|---|---|---|
| **warm** | ep01, ep02, ep03, ep04, cc_flora_30s, cc_flora_masterpiece, dream_sequence | +20 | 0.78 | 1.08 | 1.0 | 0.70 |
| **cool** (canonical) | ep05, ep06, ep07, ep08, ep09, ep10 | 0 | 0.92 | 0.92 | 1.12 | 0.75 |

Outliers (other pipelines):
- `bluesky_template.py` — simplified +12 only, no red/orange handling, 0.82 compress, 1.05 enhance.
  Not cc_flora; treat as its own variant.
- `demo/run_demo.py` — minimal red-only desaturation + 0.92/0.85 enhances.
  Demo, low priority.
- `cc_hookshot.py / _v2.py / _faith.py` — older cool-ish: 0.78 compression,
  simpler red/orange detection.
- `cc_hookshot_toast.py / _midnight.py / _midnight_v2.py / cc_midnight_final.py`
  — minimalist: 0.92 compress, no red/orange handling, enhanced(1.12, 0.92).

ep01 has type hints (`img: Image.Image -> Image.Image`); the rest don't.

## soft_bloom — 22 copies

| Lineage | Members | API | strength/blend |
|---|---|---|---|
| **warm cc_flora** | ep01, ep02, ep03, ep04, cc_flora_30s, cc_flora_masterpiece, dream_sequence | `(img, strength=0.12)` numpy additive | 0.12 |
| **cool cc_flora** (canonical) | ep05, ep06, ep07, ep08, ep09, ep10 | `(img, strength=0.05)` numpy additive | 0.05 |
| **bluesky** | bluesky_template.py | inline GaussianBlur(30) + 0.08 blend | n/a |
| **demo** | demo/run_demo.py | `(img, radius=21, blend=0.25)` Image.blend | radius/blend |
| **hookshot v1** | cc_hookshot, cc_hookshot_v2, cc_hookshot_faith | `(img, radius=15, blend=0.05)` Image.blend | radius/blend |
| **hookshot minimalist** | cc_hookshot_toast, _midnight, _midnight_v2, cc_midnight_final | `(img)` Image.blend hardcoded 15/0.05 | hardcoded |

## creamy_vignette — 13 copies

| Lineage | Members | tint | start/divisor | exponent | strength default |
|---|---|---|---|---|---|
| **warm** | ep01, ep02, ep03, ep04, cc_flora_30s, cc_flora_masterpiece, dream_sequence | CREAM | 0.35 / 0.65 | 1.8 | 0.28 |
| **cool / shadow** (canonical) | ep05–ep10 | shadow (55,48,42) | 0.25 / 0.55 | 1.4 | 0.55 |

## vignette (hookshot) — 8 copies

Different formula entirely (normalized 0–1 distance, exponent 2,
gradient 0.25/0.75). Not creamy_vignette. cc_hookshot (3 scripts) +
midnight family (4 scripts) + demo (different again, abs-distance
gaussian per axis). **Lib should expose `hookshot_vignette()` as a
sibling to `creamy_vignette()`** — they're conceptually different
operations.

## generate_tts (cc_flora) — 12 copies

| Path | stability | similarity_boost | timeout |
|---|---|---|---|
| ep01 | **0.6** | 0.7 | 120 |
| ep02–ep09, cc_flora_30s, cc_flora_masterpiece | **0.65** | 0.72 | 120 |
| **ep10** | **0.55** | 0.72 | 120 |

ep10's 0.55 is the OUTLIER, not canonical. Consensus is 0.65 (10 of
12 scripts). ep01's 0.6 is also non-conforming.

## Canonical decisions for `cvs_lib/image_filters.py`

| Function | Approach |
|---|---|
| `cottagecore_grade(img, variant="cool")` | Default = ep10. `variant="warm"` for ep01–ep04, 30s, masterpiece, dream_sequence. |
| `soft_bloom(img, strength=0.05, variant="cool")` | Default = 0.05 / numpy additive. `variant="warm"` callers pass strength=0.12 (or just rely on the default and the caller decides). Actually: just expose `strength` and let warm scripts pass 0.12. No variant kwarg needed for soft_bloom — it's already parameterized. |
| `creamy_vignette(img, strength=0.55, variant="cool")` | Default = ep10 (shadow tint, 0.25/0.55, exp 1.4). `variant="warm"` for cream-tinted vignette path. |
| `hookshot_vignette(img, strength=0.55)` | Separate function. Normalized-distance formula. cc_hookshot scripts call this instead of `creamy_vignette`. |

For TTS, cc_flora call sites in Phase 5 will go through
`cvs_lib/elevenlabs_tts.py` (already shipped). Use **stability=0.65**
as the new canonical for cc_flora (consensus pick). ep01 and ep10
will deliberately change — both currently outliers, neither has a
documented justification, so unifying is correct. Audio change is
likely subtle but worth flagging in commit message.

## What this means for the plan

- Phase 1 sign-off grids should show pre/post for **both**
  variants on the relevant scripts — not "everything → ep10".
- The `_legacy.py` frozen-copy regression model still works; only
  ep10 (cool) and ep01 (warm, canary for warm) need migration to
  prove the variant kwarg works correctly.
- `soft_bloom` is the simplest — already takes a `strength` param,
  just centralize the body. No variant kwarg. Warm callers pass 0.12.
- Hookshot's `vignette` and `cottagecore_grade` (the simpler
  variants) get their own canonical entries; not forced through
  cc_flora's variants.
