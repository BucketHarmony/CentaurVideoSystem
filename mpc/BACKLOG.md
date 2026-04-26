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

> **Backlog scope note.** This file lives at `mpc/BACKLOG.md` for
> historical reasons (MPC was the entry point) but now covers the
> whole repo. Move to `E:/AI/CVS/BACKLOG.md` once the cross-pipeline
> work begins.

## Tier 1 — bugs that hurt me today (or will tomorrow)

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

## Tier 2 — Centralize into `cvs_lib/`

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

## Audio overhaul

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

### Rally scout dashboard
HTML or markdown per rally generated from the index. Every clip,
every transcript segment, side-by-side, filterable by speaker /
keyword / motion-level. Click-to-jump to source video at timestamp.
Makes new-reel ideation a 5-min browse.

The infrastructure (faster-whisper segments, motion timeline, scene
thumbs) already exists in `mpc/index/clips/<stem>.json`. Just needs
a render step.

### Reel scaffolder (`cvs_lib/scaffold.py`)
Given a rally + a high-level pitch ("3-beat receipts angle on the
$254M GEO Group number"), generate the script skeleton: imports,
BEATS list with timestamps suggested from the index, default chrome
+ chord progression, ready for hand-edit. New reels start at 80%
done instead of 0%.

### `render_all.py`
Iterate every reel script for a rally, render in sequence, emit
`output/<pipeline>/<rally>/manifest.json` listing each reel's
duration, size, beat structure, source clips. Useful for batch posts
and re-renders after brand changes.

### Per-rally / per-season output namespacing
Today: `output/mpc/north_lake.mp4` flat. At rally 2: collisions or
mental overload. Move to `output/mpc/<rally>/<reel>.mp4`. Same
pattern for cc_flora seasons. Easy after Tier 2 extraction.

### Posting metadata helper
For each rendered reel, emit a sidecar `<reel>.posting.md` with
suggested caption text, hashtags, alt-text from chip labels +
captions. Speeds the actual post step (which today is hand-typed in
each platform).

## Tier 4 — quality-of-life & maintenance

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

### Cover thumbnails
Auto-generate a 1080×1920 cover frame per reel (mid-CTA + headline
overlay, or first beat + chip) for posting workflow. The
comfyui-output-janitor agent could pick these up.

### Dead code removal
After `cvs_lib/` lands and migration is done:
- Delete `mpc/templates/template_30s_demo.py` (or move to
  `cvs_lib/examples/`)
- Delete `mpc/templates/audio_demo.py` (after mining for the audio
  overhaul)
- Audit `cc_hookshot_v2.py` vs `cc_hookshot.py`,
  `cc_hookshot_midnight_v2.py` vs `cc_hookshot_midnight.py`,
  `cc_midnight_final.py` — pick winners, archive losers

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
