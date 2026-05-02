# CVS Video Pipeline Backlog

Improvements to the video-production process across all four CVS
pipelines:

- **MPC** (`mpc_ep_*.py`, 8 scripts) — political reels, edit-driven
- **cc_flora** (`cc_flora_ep*.py`, 10 scripts) — cottagecore episodes,
  TTS + painterly procedural
- **cc_ep** (`cc_ep_*.py`, 6 scripts) — motion-reactive procedural
- **cc_hookshot** (`cc_hookshot*.py`, 6 scripts) — motion-reactive +
  archival overlays

Total: ~21K lines of production code, almost all of it copy-paste
forks from earlier scripts. Tier 1 = removes sources of bugs that
already cost time. The big-rock work is **Tier 2 — Centralize into
`cvs_lib/`**: extract the duplicated infrastructure once so every
future video benefits from one bug fix, one improvement.

> **Backlog scope note.** This file covers the whole repo (MPC,
> cc_flora, cc_ep, cc_hookshot). Originally lived at `mpc/BACKLOG.md`
> while MPC was the only pipeline being centralized; moved to repo
> root 2026-04-26 with the start of the cc_flora lift.

## Status — cc_flora + cc_hookshot scope (2026-04-26)

**cc_flora + cc_hookshot lift shipped** in `cvs_lib/image_filters.py`.
All 12 cc_flora scripts (ep01-ep10 + 30s + masterpiece) and all 6
cc_hookshot scripts now import canonical filter implementations.
Two additional scripts (`cc_midnight_final.py`, `dream_sequence.py`)
migrated as filter-only stragglers.

Filter API:
- `cottagecore_grade(img, variant="cool"|"warm")` — cool default
  (ep05-ep10); warm matches ep02-ep04 + 30s + masterpiece + dream_sequence
- `soft_bloom(img, strength=0.05)` — strength controls bloom intensity
- `creamy_vignette(img, strength=None, variant="cool"|"warm")` —
  variant defaults: cool=0.55, warm=0.28
- `hookshot_cottagecore_grade(img)` / `hookshot_soft_bloom(img, ...)` /
  `hookshot_vignette(img, strength=0.55)` — sibling formulas for the
  hookshot dialect (no red/orange masking, contrast-based)

TTS migration: cc_flora scripts now route through `cvs_lib.elevenlabs_tts`
with style param. ep01 stability moved 0.6 → 0.65 (deliberate, signed off).
ep04 preserves cool TTS (0.55/0.72/0.15) as documented warm-grade-cool-TTS
outlier. ElevenLabs `style` parameter pass-through added to lib.

Skipped from straggler scope: `bluesky_template.py` and `demo/run_demo.py`
each use a 4th/5th filter dialect that doesn't match the lib's three
documented variants. Preserving inline avoids forcing visual changes
on out-of-scope outputs.

Test coverage: 64 tests in `tests/cvs_lib/` (17 in `test_image_filters.py`).

Out of scope, deferred to separate plans:
- cc_ep migration (6 untracked scripts: beetle, catdoor, ghost,
  sommelier, toast15, underworld)
- Audio overhaul (cc_flora's TTS+ambient pad vs MPC's sidechain
  ducking are deliberately different audio philosophies)

## Status — MPC scope (2026-04-26)

**Tier 1 + Tier 2 (MPC scope) shipped** in `cvs_lib/` lift. All 8 MPC
reels (`mpc_ep_*.py`) now import shared infrastructure:
`cvs_lib.audio`, `.captions`, `.elevenlabs_tts`, `.env`, `.index`,
`.moviepy_helpers`, `.mpc_chrome`, `.preflight`, `.preview`,
`.beat_builder`. Per-script size dropped 36–52%. Byte-identical audio
verified for all 7 migrated scripts vs. the now-deleted
`mpc_ep_*_legacy.py` frozen copies.

Tier 1 features wired:
- **Preflight** — auto-runs before TTS in every reel; catches
  duration mismatches, missing sources, in_t/out_t ordering, multi-
  shot list specs, missing path/in_t/out_t keys. `--strict` promotes
  warnings to errors.
- **`--preview` flag** — emits one PNG per beat in ~6 s. Wired into
  all 8 scripts.
- **Beat-builder** — `python -m cvs_lib.beat_builder` produces a
  one-beat mp4 in ~52 s.
- **Caption auto-fill** — `cvs_lib.captions.events_from_beats` pulls
  segments from the transcript index when `caption_lines` is absent.
  Available everywhere; applied per-reel as an editorial choice.
- **CTA externalized** — `mpc/cta.json` (multi-rally schema).

Test coverage: 45 tests in `tests/cvs_lib/`.

### Factcheck + LLM-driven claims verifier (2026-04-26)

Pre-render fact-check shipped in `cvs_lib/factcheck.py`. Wired into
`cvs_lib.preflight.run()` — every MPC reel now passes `reel_slug=` and
gets:

- **Name validation** against `mpc/roster.json` (8 entries: 7 people +
  GEO Group as org). Misspelling → ERROR. Non-progressive figure
  mention (e.g. Kristi Noem) → WARN. Unknown multi-word capitalized
  phrase → WARN. Smart filtering keeps ALL-CAPS chip slogans,
  deny-only phrases, and honorific-extended forms (e.g. "Rep. Donovan
  McKinney") silent.
- **Claims verification** via `mpc/claims/<reel_slug>.json`. The
  legacy human sign-off was replaced (2026-04-26) by the
  `mpc-claims-verifier` subagent (`.claude/agents/`), which extracts
  factual claims from the reel's caption_lines + chips, web-verifies
  each (.gov, AP, local MI press), records verdicts + source URLs,
  and writes the file. Each record pins the reel's text to a 16-char
  content_hash; any edit drifts the hash and blocks render until the
  verifier subagent re-runs.

Test coverage: +29 tests in `tests/cvs_lib/test_factcheck.py`
(roster/extraction/match paths, content_hash stability, verifier
field requirement, legacy human-sign rejection, preflight integration).
Total: 93 tests in `tests/cvs_lib/`.

To verify a reel before render, in Claude Code ask: "verify claims
for `<slug>`" → spawns the verifier subagent.

Status report any time:
```
python mpc/seed_claims.py
```

Remaining MPC follow-ups (post-lift):
- Whether to drop `caption_lines` from individual reels and use the
  index auto-fill is an editorial decision per reel (raw Whisper text
  isn't always tighter than the curated em-dash phrasing).
- Audio overhaul (sub-bass, motifs, transient hits) — see "Audio
  overhaul" section below; depends on this lift but is a separate
  session.

The cc_flora / cc_ep / cc_hookshot pipelines have NOT been migrated;
that's a separate plan.

## Tier 1 — bugs that hurt me today (or will tomorrow) — SHIPPED

### Critical bug duplication (fix in lib during extraction)
The codebase scan surfaced bugs that exist in many copies, with fixes
in only one. These will keep biting until centralization happens:

- **TTS API failure crashes 7/8 MPC scripts.** Only
  `mpc_ep_romulus.py` checks `r.status_code != 200` and returns
  `None`. The other 7 will throw on any ElevenLabs hiccup. Fix once
  in `cvs_lib/elevenlabs_tts.py`.
- **`vo_duck_envelope` vs `sidechain_duck` inconsistency.** When
  `voice=None`, one returns zeros and the other returns ones. Same
  bug in all 8 MPC scripts. Pick one convention (probably "all ones"
  = no ducking) and enforce in lib.
- **`cottagecore_grade` parameter drift.** 21 copies across cc_flora
  + cc_hookshot + bluesky_template. ep01 has type hints; ep02-ep10
  use different red/orange masking. Whichever ep got tuned latest is
  "correct" but no one knows which.
- **`soft_bloom` parameter drift.** 19 copies; ep02 uses
  `strength=0.12`, cc_hookshot uses `radius=15, blend=0.05`. Visual
  output across the cc_flora season is silently inconsistent.
- **`generate_tts` stability params drift.** ep01=0.6, ep02=0.65 with
  no record of why. Timeout inconsistency (60s vs 120s).

### Adopt the existing transcript index
**Correction:** the transcript index already exists at
`mpc/index/clips/<stem>.json` with full faster-whisper segments,
motion timelines, scene thumbnails, and auto-tags. I missed this and
re-ran whisper on 20260425_155313 by hand to discover Juan's
testimony — content that was sitting in the index the whole time.
The work isn't *creating* the index, it's *using* it:
- Memory entry pointing at the index location and schema
- A helper (`cvs_lib/index.py`) that loads `<stem>.json` and exposes
  `segments_in_window(stem, t0, t1)` for caption auto-fill
- Migrate `mpc_ep_*` scripts to read it (currently only romulus +
  we_dont_back_down reference it, and only as comments)

### Pre-flight validation
Catch what bit me building Follow the Money:
- Audio in_t/out_t lands inside speech (not mid-word, not after the
  segment ends) — verifiable via the transcript index
- Sum of beat durations == DURATION (today this is a comment, not an
  assert)
- Source files exist and contain audio
- Rotation-baked cache exists or can be rebuilt
Run before any TTS calls or render. Fails fast with actionable
messages.

### Still-frame preview before full render
Rendering takes 3–5 min per reel. Right now my only feedback loop is
"render → ffmpeg-extract frames → look." A `--preview` flag that emits
one PNG per beat (mid-beat composition: chrome + footage + caption)
catches layout/caption/chip-color bugs in seconds. Same compositor
code as production; just skip video encode + audio.

### Beat-builder tool
Given `(source, in_t, out_t, chip, caption_lines)`, render that single
beat as a 5–10s vertical mp4 for review. Lets editorial pick lines
without committing to a 4-min full-reel render. Reuses
`build_beat_clip()` directly.

## Tier 2 — Centralize into `cvs_lib/` — SHIPPED (MPC scope)

This is the big rock. **8 functions are copy-pasted verbatim across
all 8 MPC scripts**; visual filters are duplicated 19–21 times across
cc_flora + cc_hookshot. Until this lands, every fix or improvement
has to be applied N times and N+1 will drift.

### Existing partial abstractions (clean up first)
- `mpc/templates/template_30s_demo.py` — defines `sidechain_duck`,
  `synthesize_narration`, `to_int16_stereo`, but **no production
  script imports from it**. It's a standalone demo that became dead.
  Either promote to `cvs_lib/` or delete after extraction.
- `mpc/templates/audio_demo.py` — `anthem_pad`, `heartbeat`,
  `hand_clap` etc. **Never imported.** Mine the good ideas (these
  could feed the audio overhaul) then delete.

### Target package layout
```
cvs_lib/
  __init__.py
  env.py                 # load_env (5 redundant copies today)
  audio.py               # sidechain_duck, vo_duck_envelope,
                         # to_int16_stereo, harmonic_hum,
                         # render_chord_window
  elevenlabs_tts.py      # generate_tts, measure_tts_duration,
                         # synthesize_narration_track  (with the
                         # romulus-only error handling promoted)
  image_filters.py       # cottagecore_grade(strength=...),
                         # soft_bloom(...), vignette(...),
                         # creamy_vignette(...)  — params resolve
                         # the 19-21-copy drift
  moviepy_helpers.py     # make_vertical_canvas, prepare_footage,
                         # prepare_one_clip, sample_times,
                         # _get_rotation, _rotation_baked_path
  mpc_chrome.py          # render_caption_strip, render_beat_chrome,
                         # render_cta_chrome, make_chrome_clip
                         # (MPC-specific brand chrome)
  index.py               # load_clip_index, segments_in_window,
                         # motion_at, scenes_in_window
  captions.py            # caption-event spec → MoviePy clips
                         # (with auto-fill from index when absent)
  preflight.py           # validators (Tier 1)
```

### Estimated impact
- MPC scripts: 840 lines → ~400 (after imports + thin specs)
- cc_flora: 600–800 lines → ~300–400
- ~8K lines of copy-paste removed
- One bug fix instead of 7+

### Migration strategy
1. Create `cvs_lib/` with audio + tts modules first (highest
   duplication, lowest divergence). Add tests on byte-identical audio
   output before/after migration (audio processing is sensitive).
2. Migrate one MPC script (pick `mpc_ep_north_lake.py` — most recent,
   fewest drift artifacts). Diff-test render output.
3. Migrate remaining 7 MPC scripts.
4. Move to image filters; resolve cc_flora drift first by picking the
   "correct" parameter set per filter, then migrate ep01–ep10.
5. Migrate cc_hookshot (vignette + grading shared with cc_flora).
6. Migrate cc_ep last — it's the most procedurally distinct and may
   not need much beyond `env.py` + `moviepy_helpers.py`.

### Pipeline divergence to preserve (NOT centralize)
- **Aspect ratio** — all four happen to be 1080×1920 today, but cc_ep
  could go elsewhere; keep configurable.
- **Audio philosophy** — MPC is synth-VO + bed + sidechain; cc_flora
  is TTS-narration + ambient pad with no ducking; cc_ep & cc_hookshot
  are procedural motion-reactive. Don't force a single audio
  pipeline; share *primitives*, not the assembly.
- **Visual chrome** — MPC has brand banners + chips; cc_flora has
  painterly grading + bloom; cc_hookshot adds archival overlays.
  Each pipeline keeps its own chrome module.

### CTA / brand config externalization
`CTA_URL`, ActBlue link, "@michiganprogressive" handle hardcoded in
every MPC script. Move to `mpc/cta.json` alongside `palette.json`.
Same pattern in cc_flora for series-specific text. After extraction,
these become library inputs not script literals.

### Caption auto-fill from index
Once `cvs_lib/index.py` exists, default caption behavior is: pull
segments inside the beat's window automatically. Hand-written
`caption_lines` only needed for sanitization (e.g., AIC profanity)
or pacing tweaks. Removes ~100 lines per MPC script.

## Audio overhaul — SHIPPED (cottagecore + hookshot scope, 2026-04-27)

cc_flora + cc_hookshot drift consolidation lift shipped. Canonical
audio primitives in `cvs_lib/audio.py`:

- `ambient_pad(duration, mood, ...)` — drone + shimmer, mood-driven.
- `chime_layer(duration, schedule, mood, ...)` — placed pitched hits.
- `pad_envelope(duration, mood|variant, ...)` — master gain curve.
- `sting(duration, mood, rng_seed, ...)` — sub thump + transient
  noise (+ optional high tone with per-mood attack/decay).
- `tension_partial(...)` — gated sine partial for act-tension layers.
- `impact(...)` — percussive thuds (ep07/ep08).
- `lowpass_normalize(pad, mood, ...)` — cc_flora pad finishing.
- `sub_bass(duration, mood, sub_octave, ...)` — sub layer at the
  mood's drone fundamental shifted by N octaves.
- `motif(name, t_start, mood, ...)` — pre-baked melodic snippets
  (`hook_land`, `act_break`, `resolve`, `reveal`).
- `MOODS` registry: `cottagecore_warm`, `cottagecore_masterpiece`,
  `hookshot_attention`, `hookshot_grief`, `hookshot_toast`.

Migrations: 11 cc_flora scripts (ep02-ep10 + 30s + masterpiece;
ep01 was TTS-only and unaffected) and 5 cc_hookshot scripts
(cc_hookshot, toast, faith, midnight, midnight_v2). All migrations
verified bit-identical (max abs diff ≤ 3e-16) against frozen
`*_legacy.py` references; legacy copies deleted in Phase 7.
`cc_hookshot_v2.py` retired as a stale duplicate.

Two philosophies preserved (documented at top of `cvs_lib/audio.py`):
MPC ducks (sidechain), cc_flora doesn't, cc_hookshot ducks
aggressively. The lift shares primitives, not the assembly pipeline.

Test coverage: 48 tests in `tests/cvs_lib/test_audio.py`
(envelope/pad/chime/sting/sub_bass/motif/sidechain math).

Out of scope, deferred to separate plans:
- cc_ep audio (motion-driven, procedurally distinct).
- MPC-side adoption of `sub_bass` / `motif` / mood templates.

### Original backlog (pre-lift, kept for next-pass MPC adoption)

Current bed is `harmonic_hum()` — additive sine partials, vibrato,
breath modulation, butter LPF, single chord per beat. It works, but
it's a *drone*, not music: no rhythm, no melodic motion, no low end,
no transitions, no stereo width. Every reel in the suite shares the
same palette with only the chord swapped. On TikTok where the first
3s decides everything, a static drone is dead air. **Depends on Tier
2 `cvs_lib/audio.py` extraction** — otherwise these improvements
have to be duplicated 7+ times.

Idea-mining: `mpc/templates/audio_demo.py` has `anthem_pad`,
`heartbeat`, `hand_clap`, etc. that no one ever called. Some of
these are exactly the building blocks the overhaul needs.

### Quick wins (cheap, big impact)
- **Sub-bass layer.** Current chords start at 73 Hz; phones with even
  modest speakers reproduce 40–60 Hz. Add a sine-or-triangle sub
  doubling the chord root, lightly compressed, side-chained against
  itself. Gives the bed a body the drone never had.
- **Transient hits at beat changes.** Filtered noise burst + sub thump
  on every HOOK→STAKES→ANSWER→CTA transition. Free editorial
  punctuation; turns crossfades into *cuts*.
- **Pulse / heartbeat.** Subtle kick at 60–80 BPM on alternating
  beats, ducked under speech. Reels feel like they're moving forward,
  not sitting. Mute on testimony beats where stillness serves the
  content.
- **Stereo width.** Pan octave doublings hard-L/hard-R; keep
  fundamental center. Wider field on phones with stereo speakers /
  headphones for ~zero cost.
- **Light reverb on the bed.** Schroeder or simple convolution IR.
  Dries-too-clean is the current bed's defining feature.
- **CTA cadence.** Right now CTA is just `resolve` chord, which is
  the same drone in a brighter key. Replace with an actual V→I lift +
  bell/chime hit on the headline reveal. Donate-pitch lands harder.

### Core upgrades (real composition)
- **Melodic motif library.** Each reel gets a 3–5-note motif played
  on a soft pluck or bell over the chord bed, repeating with
  variation across beats. Establishes reel identity and series
  recognizability.
- **Filter automation.** Slow LPF cutoff sweep across each beat
  (closed → open) and across the full reel (dark → bright). Free
  motion via time-varying `lfilter`.
- **Per-beat mood, not just chord.** Today `SCENE_CHORDS` only swaps
  notes. Extend so each scene tag (`grief`, `minor`, `build`,
  `resolve`) carries: chord, tempo, motif preset, presence/absence of
  pulse, filter envelope.
- **Source audio EQ + level matching.** Chant clips are loud; speech
  clips vary wildly. Apply HP filter (rumble out), gentle de-ess,
  RMS-target normalization per source before mixing. Removes
  hand-tuning `audio_gain` per beat.
- **VO chain.** ElevenLabs output is dry. Mild compression + light EQ
  (presence boost ~3 kHz) + short tail reverb makes the synth voice
  sit in the mix instead of floating above it.

### Mood templates
Each script picks one of 4–5 named moods instead of cobbling chords
+ tempo per beat:
- `receipts` — punchy minor + kick + sub, urgent
- `testimony` — sparse pad + soft Rhodes-ish pluck, intimate, no pulse
- `endurance` — warm major-leaning pad + slow heartbeat
- `energy` — driven pulse + wide pad, chant-forward
- `legislation` — clean low brass + sub, institutional gravity

Authoring a new reel becomes: pick mood, pick beats. Mix sounds
intentional across the suite, not accidental.

### Stretch
- **CC0 / licensed loops library.** For reels where music carries the
  energy (People Power), having actual produced loops would let MPC
  compete with TikTok's music-driven baseline.
- **MIDI export.** Render the chord/motif track to MIDI alongside
  the audio so a real producer could later remix.

## Tier 3 — editorial accelerators (for FUTURE videos)

Future-video flow: rally happens → footage lands → reels go up. The
faster this loop, the more responsive MPC can be. Same applies to
cc_flora (next episode) and cc_hookshot (new clip).

### Ingest pipeline (`scripts/ingest.py`)
Today: copy raw files into `E:/AI/CVS/raw/MPC/<rally>/`, manually run
`mpc_scan_sources.py`, manually verify the index. Make this one
command:
```
python ingest.py --pipeline mpc --rally "Ice Out Romulus" \
    --source-dir <phone-export>
```
Copies, runs scan, verifies index, prints "ready" with N clips
indexed and M minutes transcribed.

### Rally scout dashboard — SHIPPED (2026-04-29)
`scripts/scout_dashboard.py` walks `<pipeline>/index/clips/*.json`
and emits a markdown page per stem (meta, tags, transcript with
mm:ss timestamps, top-N motion peaks, scene thumbnail gallery)
plus a top-level `_index.md` table linking each. Output:
`output/<pipeline>/_scout/<rally_slug>/`. Pure renderers in
`cvs_lib/scout.py` so the markdown is testable without disk I/O.
Verified 2026-04-29: 19 stems × Ice Out Romulus rendered in <1s,
21 tests in `tests/cvs_lib/test_scout.py`. Pairs with
`scripts/find_phrase.py` (search vs. browse).

### Reel scaffolder (`cvs_lib/scaffold.py`)
Given a rally + a high-level pitch ("3-beat receipts angle on the
$254M GEO Group number"), generate the script skeleton: imports,
BEATS list with timestamps suggested from the index, default chrome
+ chord progression, ready for hand-edit. New reels start at 80%
done instead of 0%.

### `render_all.py` — SHIPPED (MPC, 2026-04-29)
`scripts/mpc_render_all.py` discovers every `scripts/mpc_ep_*.py`,
renders each whose output is missing or older than the script
(`--force` to re-render all, `--manifest-only` to skip render),
and emits `output/mpc/manifest.json` with per-reel duration, size,
codec, dimensions, source script, and matching cover.
Output-path inference: regex on `OUTPUT_PATH = OUT_DIR / "..."`,
docstring `Output:` line, then stem-match fallback. Verified
2026-04-29: 10 reels discovered, 10/10 rendered, 10/10 covers
matched. cc_flora / cc_hookshot equivalents not yet shipped.

### Per-rally / per-season output namespacing
Today: `output/mpc/north_lake.mp4` flat. At rally 2: collisions or
mental overload. Move to `output/mpc/<rally>/<reel>.mp4`. Same
pattern for cc_flora seasons. Easy after Tier 2 extraction.

### Posting metadata helper — SHIPPED (2026-04-29)
`cvs_lib/posting.py` AST-parses each reel script (no module imports
— side-effect free) for docstring + `CTA_HEADLINE` / `CTA_SUBHEAD` /
`CTA_RALLY` constants, merges with the manifest entry from
`mpc_render_all.py`, and renders a `.posting.md` sidecar. Sections:
file/cover paths + sizes, synopsis (docstring body up to
`Beats:`/`Output:`/`Run:`), suggested caption, brand+reel hashtags
(MichiganProgressive / ImmigrantRights / AbolishICE / IceOutRomulus +
headline-derived tag), accessibility alt-text, per-platform posting
checklist (TikTok / Instagram / Bluesky / Facebook with char-count
guidance). Driver: `scripts/mpc_make_posting.py`. Verified 2026-04-29:
10 sidecars written next to the rendered reels. 24 tests in
`tests/cvs_lib/test_posting.py`.

## Tier 4 — quality-of-life & maintenance

### Caption auto-fill test drift (2026-04-29)
`tests/cvs_lib/test_captions.py` has 4 failing tests
(`test_autofill_pulls_segments_when_caption_lines_absent`,
`test_autofill_offsets_relative_to_beat_start`,
`test_autofill_respects_scene_t0`,
`test_caption_overrides_substitute_text_by_segment_start`).
Tests expect fine-grained transcript segments
(e.g. 12.16-15.52, 15.52-19.36); current
`mpc/index/clips/20260425_155313.json` has only 2 coarse segments
(0.0-29.64, 30.0-44.96). Either whisper was re-run with different
chunking params, or the tests were authored against a never-shipped
index version. Fix: re-tune test expectations to match current
segmentation, OR re-run scanner with finer granularity. Pre-existing
— not caused by recent lifts.

### Smoke tests
Zero tests on the audio mix or caption positioning today. After
extraction, a handful in `tests/cvs_lib/`:
- caption strip is bottom-anchored at CAPTION_BOTTOM=1620 for
  various text lengths
- audio mix peak after normalization is in [0.85, 0.95]
- chord-window shape (fade in/out > 0, no clicks at boundaries)
- TTS cache hit/miss behavior
- rotation cache rebuild on source mtime change
Catches regressions during the Tier 2 refactor.

### Rotation pre-bake speed
First-run baking is libx264 ultrafast crf=18 — ~30s per rotated
source. With NVENC available (RTX 4090) this could drop to ~3s.
Either swap codec or parallelize across the BEATS list at startup.
Belongs in `cvs_lib/moviepy_helpers.py`.

### Visual filter regression diff
Once cc_flora grading is centralized, render-diff a representative
frame of every existing episode against the pre-extraction render.
The drift across ep01–ep10 means there isn't one "right answer";
this catches whichever episodes silently change look.

### Brand version pinning
`palette.json` is read at render time. If brand updates and we
re-render an old reel, output drifts from what was posted. Snapshot
brand into the manifest, or stamp a `brand_version` into the
rendered file's metadata.

### Caption-line override convention in code
Empty list `[]` suppresses captions; key absent pulls from index.
This convention lives in memory, not in code. After Tier 2,
document in `cvs_lib/captions.py` docstring with examples.

### Cover thumbnails — SHIPPED (MPC, 2026-04-29)
`cvs_lib/cover.py` provides `extract_frame()` (fast input-seek
ffmpeg single-frame extract) and `make_cover()` (extract +
optional stencil headline overlay with magenta stroke, gradient
scrim, autosized via `_fit_font`). Per-reel config lives in
`scripts/mpc_make_covers.py` (`COVERS` list with `t`, `headline`,
`sub` per reel). Covers land in `output/mpc/covers/<reel>.png` at
1080×1920 PNG. 11 covers shipped; `mpc_render_all.py` matches them
into the manifest. Headline timestamps tuned to avoid scene fades
(`abolish_ice_congress` t=24→14) and chrome competition
(`romulus_rapid_response` t=18→2 with no overlay since in-video
HOOK chrome already lands).

### Dead code removal
After `cvs_lib/` lands and migration is done:
- Delete `mpc/templates/template_30s_demo.py` (or move to
  `cvs_lib/examples/`)
- Delete `mpc/templates/audio_demo.py` (after mining for the audio
  overhaul)
- Audit `cc_hookshot_v2.py` vs `cc_hookshot.py`,
  `cc_hookshot_midnight_v2.py` vs `cc_hookshot_midnight.py`,
  `cc_midnight_final.py` — pick winners, archive losers

## Tier 5 — clip-locator follow-ups (2026-04-29)

`cvs_lib/clip_locator.py` + `cvs_lib/clip_snap.py` + SNR gate shipped
this week — phrase-in, cleanly-cut-clip-out with on-mic verification.
Demonstrated end-to-end via `scripts/mpc_demo_clips.py` (5 hand-picked
phrases across 5 stems; SNR gate matched the ear's grading exactly).
The toolset works. These items put it to work.

### Status (2026-04-29 lift)
- **SHIPPED**: HDR→SDR cutter promotion → `cvs_lib/clip_cut.py` with
  ffprobe auto-detect (HLG, PQ, bt2020, 10-bit pix_fmt). 10 tests in
  `tests/cvs_lib/test_clip_cut.py`. `mpc_demo_clips.py` now imports.
- **SHIPPED**: cross-rally search CLI → `scripts/find_phrase.py`. Auto
  pipeline-aware (mpc / cc_flora / cc_hookshot), `--audition` ffmpeg-
  cuts via `clip_cut`, output goes to
  `output/<pipeline>/_audition/<phrase_slug>/`. Exit 1 on no matches.
- **SHIPPED**: smoke test → `tests/cvs_lib/test_locator_smoke.py`
  pinning the 5 demo phrases' duration + SNR + off-mic flag against
  the 2026-04-29 baseline. Includes the geogroup VAD-interval
  extension regression pin (`in_t < 21.0`).
- Remaining: phrase-driven beats in MPC reels (#1) and SNR override +
  off-mic rescue chain (#4).

### Phrase-driven beats in MPC reels — MECHANISM SHIPPED (2026-05-01)
Today MPC scripts hand-code `(stem, in_t, out_t)` per beat from the
transcript index. Editorial picks live in code as magic numbers; if
whisper re-runs and timestamps shift, every reel breaks silently.

**Mechanism shipped:** `cvs_lib/beat_resolver.py` resolves `phrase=`
specs into `in_t`/`out_t` via `locate_phrase_clip`. Three modes:

- **Phrase-driven** — `{path, phrase}` only → resolver fills both edges
  from the snap-refined cut.
- **In-anchor** — `{path, phrase, out_t}` → fills `in_t`; static `out_t`
  wins (or vice versa).
- **Documentation + drift sentinel** — `{path, phrase, in_t, out_t}` →
  both static; resolver re-runs at preflight time and emits a WARN if
  the phrase resolution disagrees by > 100 ms (catches index drift on
  re-transcription).

`resolve_or_exit(BEATS, raw_dir=...)` is the ergonomic reel-script
wrapper: prints issues, exits 1 on ERROR, optional `strict=` promotes
WARN to fatal. Pass-through fast-path when no spec uses `phrase=`,
so legacy reels stay unchanged.

`cvs_lib.preflight` gained `assert_phrases_were_resolved()` which fires
a pointed ERROR if any spec still has `phrase=` without `in_t`/`out_t`
at preflight time — catches reels that forgot to call `resolve_or_exit`
before render.

**Files**: `cvs_lib/beat_resolver.py` (~280 LOC),
`tests/cvs_lib/test_beat_resolver.py` (21 tests; live + pure mix),
`cvs_lib/preflight.py` (added `assert_phrases_were_resolved`).

**Per-reel canary deferred (editorial work).** Migration of any reel
beat is an editorial decision: phrase-resolved durations rarely match
the existing editorial `dur` exactly, so each beat needs `dur` retuned
and the BEATS sum rebalanced. The mechanism + tests are in place; per-
reel migration ships separately, with audition cuts via `find_phrase
--audition` to confirm the phrase boundaries land cleanly before
swapping out the magic numbers.

Migration playbook (per beat):
1. Run `python scripts/find_phrase.py "<phrase>" --pipeline mpc --audition`
   to verify the phrase resolves cleanly + SNR is acceptable.
2. In the reel: replace `{path, in_t, out_t}` with `{path, phrase}`.
3. Note the resolver's reported `resolved_dur`; retune the beat tuple's
   `dur=` to match (or accept dur_drift WARN).
4. Rebalance other beats to keep `sum(beat durs) == DURATION`.
5. Add `BEATS = resolve_or_exit(BEATS, raw_dir=RAW_DIR)` near the top.
6. Render; the existing preflight catches mismatches.

### Cross-rally phrase search CLI — SHIPPED (2026-04-29)
`scripts/find_phrase.py "<phrase>" [--pipeline mpc|cc_flora|cc_hookshot]
[--exact] [--audition] [--top N] [--json]`. Walks all `<pipeline>/index/
clips/*.json`, calls `locate_phrase_across_stems`, prints SNR-sorted
table with `OFF-MIC` / `VOICE-EDGE` flags. `--audition` ffmpeg-cuts
each match via `cvs_lib.clip_cut` into
`output/<pipeline>/_audition/<phrase_slug>/NN_<stem>.mp4` plus a
manifest. Verified 2026-04-29: 19 stems × "abolish ICE" → top-5 in
~7s; `$254 million` → exactly one match at SNR +23.5 dB.

### Promote HDR→SDR cutter to `cvs_lib/clip_cut.py` — SHIPPED (2026-04-29)
`cvs_lib/clip_cut.py` provides `cut_clip(src, in_t, out_t, dst, *,
tonemap="auto"|"hdr"|"sdr")`. Auto mode runs ffprobe on the source and
tonemaps iff any of: `color_transfer ∈ {arib-std-b67, smpte2084}`,
`color_primaries == bt2020`, or 10-bit pix_fmt. HDR path is the same
zscale-linear → hable → bt709 → yuv420p chain that worked in
`mpc_demo_clips.py`; SDR fast-path skips the chain entirely. Pure
`build_cmd()` is exposed for tests. `cut_clip` rejects inverted ranges
and missing sources before reaching ffmpeg.
**Files**: `cvs_lib/clip_cut.py`, `tests/cvs_lib/test_clip_cut.py`
(10 tests). `scripts/mpc_demo_clips.py` migrated.

### SNR threshold override + off-mic rescue chain
The +10 dB floor matched 5 hand-graded MPC clips, but cc_flora's
ambient-bed audio philosophy will need a different threshold; field
recordings on a different mic could too. Add `mpc/snr.json`
(per-rally optional override) read by preflight. Separately:
clips currently rejected at +5 dB ("to oppose the construction") may
be salvageable with HP filter + de-ess + RMS normalization + light
denoise (RNNoise / spectral gate). Add `cvs_lib.audio.rescue_voice()`
that takes a `(audio, in_t, out_t)` candidate and returns a
processed mono buffer suitable for re-injection at mix time. Pairs
with the existing `is_off_mic` flag: instead of hard-rejecting,
preflight could mark the beat as "needs rescue" and route it through
the chain.

### Smoke test for clip_locator against demo phrases — SHIPPED (2026-04-29)
`tests/cvs_lib/test_locator_smoke.py` parametrizes the 5 canonical
demos (north_lake_testimony / nbcm_origin / community_engaged /
naz_fearful / geogroup_254m) and asserts each: `match_score == 1.0`,
duration within ±0.25s of baseline, SNR within ±2 dB, off-mic flag
exact. Plus a regression-pin specifically for the 2026-04-29 VAD-
interval extension fix (`geogroup_254m.in_t < 21.0` so "two" stays
captured). 6 tests total, ~3.8s wall clock with shared silero load.
Total clip-suite tests: 45 across `test_clip_snap.py`,
`test_clip_locator.py`, `test_clip_cut.py`, `test_locator_smoke.py`.

## Tier 6 — post-mechanism follow-ups (2026-05-01)

Suite of items added after the beat-resolver lift (commit `73240ee`).
The mechanism work for the past three weeks (clip locator → snap →
SNR gate → cut → resolver) is in place; these are the items that put
it to work *and* close the gaps that became visible once it shipped.

### Migrate north_lake.py to phrase-driven beats (canary)
First per-reel canary for the deferred beat_resolver migration. Pick
`mpc_ep_north_lake.py` because its 3 testimony beats are purely
phrase-content (the 4th is chant b-roll, leave legacy). Resolve full-
thought phrases, retune `dur` per beat, rebalance reel sum to 30s,
audition cuts via `find_phrase --audition` before swap. Acceptance:
reel renders, audio is coherent, output is 30s ± 0.05s, posting
markdown still generates from manifest.

### Phrase resolution cache (`mpc/phrase_cache.json`)
The resolver re-runs whisper-word-index lookup + silero-VAD snap on
every render. ~200ms × 8 beats × 8 reels = ~13s per `mpc_render_all`
run, all wasted after the first resolution. Add a JSON cache keyed
by `(stem, phrase, snap-params-fingerprint, index-mtime)` returning
`(in_t, out_t, snap_quality)`. Invalidate on index re-scan. Belongs
in `cvs_lib/beat_resolver.py` behind a `cache_path=` kwarg.

### SNR threshold per-rally override + rescue chain (Tier 5 #4 split)
Existing Tier 5 #4 conflates two items. Split: (a) `mpc/snr.json`
per-rally floor override read by `clip_locator` via preflight wiring,
(b) `cvs_lib.audio.rescue_voice(audio, in_t, out_t)` that returns a
HP-filtered + de-essed + RMS-normalized + RNNoise-denoised buffer for
re-injection at mix time. (a) is ~30 LOC; (b) is the real work.

### cc_flora scout dashboard parity
`cvs_lib/scout.py` and `scripts/scout_dashboard.py` read MPC's index
shape. cc_flora has its own index but no scout output; editorial
flies blind on which clip has which line. Extend `PIPELINE_DEFAULTS`
to include cc_flora and verify renderers don't assume MPC-specific
fields. ~50 LOC plus a smoke test. Same for `cc_hookshot` since both
already share `cvs_lib/scanner`.

### cc_flora posting metadata parity
`cvs_lib/posting.py` is MPC-specific (parses `CTA_HEADLINE`/`CTA_SUBHEAD`
constants from reel docstrings; reads `mpc/cta.json`). cc_flora reels
don't carry CTA constants — they have a TTS narration script + an
ambient mood. Define what the cc_flora sidecar should look like (probably
pulls the narration text + the brand cottagecore hashtags) and add
a sibling renderer.

### Re-transcribe MPC index for fine-grained segments
4 caption-autofill tests in `test_captions.py` fail because the index
has only 2 coarse segments (0-29.64, 30-44.96) where the tests expect
~12-16s and 16-19s slices. Either re-run `mpc_scan_sources.py` with
finer chunking params and refresh the index, OR rewrite tests to match
current segmentation. Pre-existing — surfaces every full-suite run as
noise. Pick one and ship it.

### Soundbite extractor CLI
The opposite of `find_phrase`: given a stem (or all stems), list every
contiguous voiced span ≥ N seconds with SNR ≥ M dB, sorted by quality.
Output: a manifest of "ready-to-cut" soundbites the editor can browse.
Especially useful when starting a new reel — "show me everything
quotable in this rally." Reuses `cvs_lib.word_index` + `clip_snap` +
SNR analysis already in place. ~120 LOC under `scripts/find_bites.py`.

### Render timing telemetry
Each MPC reel takes ~60-90s end-to-end; cc_flora reels ~3-5min with
upscale. Today there's no way to know which phase (TTS / video build /
audio mix / mux) is the slow one. Add a context manager
`cvs_lib.timing.phase("name")` that logs to `output/<pipeline>/
_render_log.jsonl`. Aggregator script reads the log and surfaces the
slow phases. Concrete optimization targets follow.

### Loudness normalization to per-platform LUFS targets
TikTok normalizes to -14 LUFS, IG Reels -14, YouTube -14, Bluesky no
target. Today `cvs_audio.lowpass_normalize` peak-normalizes to ~0.9 —
not loudness-normalized. Add a final `pyloudnorm`-based pass before
mux, with platform target as a kwarg. One LUFS measurement at render
time + linear gain to target. Catches the "this reel sounds quieter
than the others" failure mode.

### EDL export from BEATS
Editor handoff: `python scripts/mpc_export_edl.py <reel>` writes a
CMX 3600 EDL (or a Resolve `.fcpxml`) describing source→cut→sequence
mappings. Useful when a reel needs human polish in Resolve before
publish. ~80 LOC; standard EDL format is well-documented. Optional
phrase= comment per cut for editorial provenance.

### Beat-builder phrase-aware
`python -m cvs_lib.beat_builder` currently builds a one-beat preview
from explicit `(stem, in_t, out_t)`. Add `--phrase "..."` that calls
the resolver internally, so editorial can preview a phrase cut without
hand-typing timestamps. Composes existing modules; ~30 LOC.

### Audio mix regression test
Today there's zero coverage on the final mix. Render a small fixture
beat (1s of synth bed + 1s of TTS) and pin its WAV checksum. Catches
silent regressions from numpy / pyloudnorm / scipy version drift,
which has historically broken renders without a Python-level error.
Belongs in `tests/cvs_lib/test_audio_mix.py`.

### Stale-derivative auto-detect
Today the rotation cache (and any future derivative — phrase cache,
tonemapped sources) trusts its own existence: if the file is there,
use it. When the source video is re-encoded or the rotation flag
changes, derivatives go stale silently and the next render quietly
ships the old footage. Add an mtime-based staleness check in
`cvs_lib/moviepy_helpers.py` (and the upcoming phrase cache): if
`source.mtime > derivative.mtime`, rebuild. ~20 LOC per derivative,
catches a surprisingly nasty silent-staleness class.

### Background render queue
`mpc_render_all.py` renders reels sequentially (~10 min for 10 reels).
RTX 4090 has plenty of GPU headroom for 2-3 parallel renders. Add a
`--workers N` flag using `multiprocessing` (process-per-reel — moviepy
isn't thread-safe). Shave the batch by 60-70%. Manifest writes need
a lock.

### cc_ep migration disposition (6 untracked scripts)
The 6 `scripts/cc_ep_*.py` files (beetle, catdoor, ghost, sommelier,
toast15, underworld) are uncommitted and their relationship to
existing cc_ep needs clarification. Either commit (with provenance
note in the BACKLOG), discard, or move to `scratch/`. Don't leave them
untracked — the working tree has been "dirty by default" for two
weeks and that's a cognitive tax on every `git status`. Decision is
trivial; the open question is whether any of them are partial work.

## Anti-backlog (intentionally not doing)

- **Web UI for editorial decisions.** The CLI + still-preview loop is
  fast enough; UI is overhead.
- **Full DAW automation.** Numpy synthesis is 100ms. A real DAW would
  add hours of process for marginal audio gain.
- **Video upscaling on rally footage.** Source is 1920×1080 phone
  capture; 1080×1920 vertical crop already maxes out useful
  resolution.
- **Forcing one audio pipeline across all four projects.** MPC,
  cc_flora, cc_ep, and cc_hookshot have genuinely different sound
  philosophies. Share primitives, not the assembly.
- **Eager rewrite of cc_ep & cc_hookshot.** They're shorter (~310
  lines for cc_ep) and procedurally distinct. They benefit less from
  centralization than MPC + cc_flora. Migrate last; consider
  partial.
