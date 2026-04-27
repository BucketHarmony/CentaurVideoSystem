# Phase 1 audible sign-off — Audio overhaul lift

Plan: `C:/Users/kenne/.claude/plans/bouncing-velvet-tympani.md`
Audit: `cvs_lib/_audio_drift_audit.md`

## What you're listening to

Each `<slug>_AB.wav` is **30 seconds + 0.5s gap + 30 seconds = 60.5s**:

- **First 30s:** the existing inline `generate_ambient_pad` from
  `scripts/<slug>.py`, run in isolation (no MoviePy / TTS / video).
- **Last 30s:** the canonical primitive
  (`cvs_lib._audio_canonical_draft.cottagecore_pad_canonical`)
  rendered against the same chime schedule and mood, with all
  per-episode editorial events deliberately absent.

The sign-off question: **does the second half sound like the first
half's "base layer," modulo the per-episode events that are documented
in the audit?**

## Files

### cc_flora season

| episode | AB file | expected residual |
|---|---|---|
| ep02 | `ep02_AB.wav` | act-3 Bb3 tension partial (t=20–30) |
| ep03 | `ep03_AB.wav` | act-3 hopeful E4 shimmer (t=20–30) |
| ep04 | `ep04_AB.wav` | **battery-death + silence + wake** compound (t=9.5–15) |
| ep05 | `ep05_AB.wav` | **freeze + 5 shutter clicks + glitch** compound (t=10–16.5) |
| ep06 | `ep06_AB.wav` | act-1 Bb3 dying-battery + recharge bloom + cable-catch (22.5) |
| ep07 | `ep07_AB.wav` | collision impact thuds (t=13.0, 17.5) |
| ep08 | `ep08_AB.wav` | tension Bb3 + uncertainty fade + wedge thud (t=15) |
| ep09 | `ep09_AB.wav` | act-2 hope E4 + act-3 wistful Bb3 |
| ep10 | `ep10_AB.wav` | drift Bb + hope E4 + milestone B4 shimmer |
| 30s  | `flora_30s_AB.wav` | act-3 Bb3 tension |
| masterpiece | `masterpiece_AB.wav` | none (mood swap test — should ~match) |

### cc_hookshot family

These are **B-only** (no A — `cc_hookshot.py` returns stereo + has
sting + uses linspace envelope, so a simple A/B comparison isn't
clean). Listen for: hookshot mood characteristics, sting feel, chime
decay relative to cc_flora.

| script | B file | mood |
|---|---|---|
| cc_hookshot | `cc_hookshot_B_canonical.wav` | hookshot_attention (A-min, 4 partials, octave chimes) |
| cc_hookshot_faith | `cc_hookshot_faith_B_canonical.wav` | hookshot_grief (D-min, single LFO 0.08 Hz, 2.8 kHz lowpass) |
| cc_hookshot_toast | `cc_hookshot_toast_B_canonical.wav` | hookshot_attention (no chime octave) |

## Correlation summary (numerical)

| slug | A↔B Pearson | residual RMS |
|---|---|---|
| ep02 | 0.9860 | 0.0624 |
| ep03 | 0.9897 | 0.0536 |
| ep04 | 0.9181 | 0.1506 |
| ep05 | 0.9599 | 0.1838 |
| ep06 | 0.9885 | 0.0588 |
| ep07 | 0.9883 | 0.0961 |
| ep08 | 0.9710 | 0.1191 |
| ep09 | 0.9898 | 0.0553 |
| ep10 | 0.9868 | 0.0598 |
| flora_30s | 0.9859 | 0.0625 |
| masterpiece | 0.9917 | 0.0622 |

A ≥ 0.97 correlation means the canonical primitive faithfully
reproduces the base shape; the residual ≈ the editorial events that
will be added by callers in Phase 4. The two outliers (ep04 0.918,
ep05 0.960) are exactly the two compound-variant episodes.

## Sign-off questions

1. **Does the canonical match the base "feel"?** First half and second
   half should sound like the same instrument with different events
   sprinkled on top.
2. **Are any episodes audibly broken under the canonical?** If yes,
   they need a `variant=` kwarg in Phase 2.
3. **Is the masterpiece mood right?** It's the only mood swap test
   (1.20× drone, 0.15/0.22 LFO, 0.25 pad target). If it sounds like
   a music-box-cottagecore vibe, mood is correct.
4. **Do the three hookshot moods sound distinct?**
   - `hookshot_attention` (cc_hookshot, toast): A-minor with octave-up
     chime brightness.
   - `hookshot_grief` (faith): D-minor, darker, single LFO, narrower
     low-pass.
5. **OK to proceed to Phase 2** (formally land primitives in
   `cvs_lib/audio.py`, migrate ep10 as canary)?
