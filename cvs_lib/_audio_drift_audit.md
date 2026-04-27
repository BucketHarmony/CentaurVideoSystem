# Audio drift audit (Phase 0)

Scope: 18 inline audio generators across cc_flora (12) and cc_hookshot
(6). Captured every numeric parameter that can plausibly drift between
copies. Source line numbers are absolute, against current `master`.

**Sample rate** is `sr=44100` (cc_flora positional default) or
`SR=44100` module-constant (cc_hookshot) for *every* file in scope —
no drift, not tabled below.

**ep01 has no inline pad.** `cc_flora_ep01_first_light.py` is
TTS-only — narration sits on silence. It still has its own TTS
settings (table 12) but does not appear in any pad-related table.
Surfaced explicitly so the canonical doesn't quietly invent a pad
for it.

---

## File → audio function map

| script | function | line | shape |
|---|---|---|---|
| cc_flora_ep01_first_light.py | *(no pad)* | — | TTS-only |
| cc_flora_ep02_bigger_room.py | `generate_ambient_pad` | 348 | flora-base |
| cc_flora_ep03_moon.py | `generate_ambient_pad` | 328 | flora-base + act3 hope |
| cc_flora_ep04_carried_home.py | `generate_ambient_pad` | 371 | flora-base + battery-death + silence + wake |
| cc_flora_ep05_same_frame.py | `generate_ambient_pad` | 424 | flora-base + freeze zone + shutter clicks + glitch |
| cc_flora_ep06_three_centimeters.py | `generate_ambient_pad` | 378 | flora-base + recharge + cable-catch dissonance |
| cc_flora_ep07_ping_pong.py | `generate_ambient_pad` | 375 | flora-base + collision impacts + thuds |
| cc_flora_ep08_the_threshold.py | `generate_ambient_pad` | 379 | flora-base + tension build + uncertainty fade + wedge thud |
| cc_flora_ep09_the_hallway.py | `generate_ambient_pad` | 376 | flora-base + hope + wistful Bb3 |
| cc_flora_ep10_the_patience_of_rooms.py | `generate_ambient_pad` | 377 | flora-base + drift Bb + hope + B4 shimmer |
| cc_flora_30s.py | `generate_ambient_pad` | 368 | flora-base + act3 Bb |
| cc_flora_masterpiece.py | `generate_ambient_pad` | 381 | **divergent shape** (no act tensions; warmer constants) |
| cc_hookshot.py | `generate_bed_audio` | 290 | hookshot-base (sting + pad + chimes + stereo) |
| cc_hookshot_v2.py | `generate_bed_audio` | 290 | **byte-identical to cc_hookshot.py** |
| cc_hookshot_faith.py | `generate_audio` | 218 | hookshot variant: D-minor, deeper sub, sparse chimes, eyes-back sting |
| cc_hookshot_toast.py | `generate_audio` | 187 | hookshot variant: A-minor, thinner shimmer, no chime octaves |
| cc_hookshot_midnight.py | `generate_audio` | 172 | hookshot variant: A-minor pre / D-minor post + crash + 2nd thud |
| cc_hookshot_midnight_v2.py | `generate_audio` | 212 | hookshot variant: R2 tones + crash + D-minor aftermath |

---

## 1. Pad fundamentals (chord notes, Hz × gain)

### cc_flora family (drone layer)

| episode | A2 | E3 | A3 | line |
|---|---|---|---|---|
| ep02 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 350–352 |
| ep03 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 330–332 |
| ep04 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 374–376 |
| ep05 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 426–428 |
| ep06 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 380–382 |
| ep07 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 377–379 |
| ep08 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 381–383 |
| ep09 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 378–380 |
| ep10 | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 379–381 |
| 30s | `110 × 0.05` | `164.81 × 0.035` | `220 × 0.025` | 373–375 |
| masterpiece | `110 × 0.06` | `164.81 × 0.04` | `220 × 0.03` | 387–389 |

**Drift:** `masterpiece` is 1.20× louder on every drone partial
(0.06/0.05, 0.04/0.035, 0.03/0.025). All others identical.

### cc_hookshot family (drone layer)

| script | A2 | C3 | E3 | A3 | D2 | F2 | line |
|---|---|---|---|---|---|---|---|
| cc_hookshot | `110 × 0.040` | `130.81 × 0.025` | `164.81 × 0.030` | `220 × 0.020` | — | — | 305–308 |
| cc_hookshot_v2 | `110 × 0.040` | `130.81 × 0.025` | `164.81 × 0.030` | `220 × 0.020` | — | — | 305–308 |
| cc_hookshot_toast | `110 × 0.040` | `130.81 × 0.025` | `164.81 × 0.030` | `220 × 0.020` | — | — | 200–202 |
| cc_hookshot_faith | — | — | — | `110 × 0.035`, `220 × 0.020` (A2/A3 only) | `73.42 × 0.045` | `87.31 × 0.025` (D-min: D2/F2/A2/D3) | 232–235 |
| cc_hookshot_midnight (pre-crash) | `110 × 0.015` | `130.81 × 0.020` | `164.81 × 0.025` | `110 × 0.035` (A2 dup) | — | — | 178–180 |
| cc_hookshot_midnight (post-crash) | `110 × 0.025` | — | — | — | `73.42 × 0.030` | `87.31 × 0.020` | 218–220 |
| cc_hookshot_midnight_v2 (post only) | `110 × 0.025` | — | — | — | `73.42 × 0.030` | `87.31 × 0.020` | 271–272 |

**Drift family-level:** hookshot uses A-minor C3 pad (4 partials);
faith uses D-minor (different fundamentals); midnight pair uses
A-min→D-min transition. `cc_hookshot.py` and `cc_hookshot_v2.py`
are byte-identical.

---

## 2. Shimmer / octave-up layer

### cc_flora family (shimmer Hz × gain × LFO)

| episode | A4 | C#5 | E5 | line |
|---|---|---|---|---|
| ep02 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 355–357 |
| ep03 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 335–337 |
| ep04 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 379–381 |
| ep05 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 431–433 |
| ep06 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 385–387 |
| ep07 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 382–384 |
| ep08 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 386–388 |
| ep09 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 383–385 |
| ep10 | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 384–386 |
| 30s | `440 × 0.010 × lfo1` | `554.37 × 0.007 × lfo2` | `659.25 × 0.005 × lfo1` | 380–382 |
| masterpiece | `440 × 0.012 × lfo1` | `554.37 × 0.008 × lfo2` | `659.25 × 0.006 × lfo1` | 394–396 |

**Drift:** `masterpiece` is +20%/+14%/+20% louder on shimmer partials.
All others identical.

### cc_hookshot family

| script | A4/D4 | C5/F4 | E5 | line |
|---|---|---|---|---|
| cc_hookshot | `440 × 0.010 × lfo1` | `523.25 × 0.007 × lfo2` | `659.25 × 0.005` (no LFO) | 311–312 |
| cc_hookshot_v2 | identical to cc_hookshot | — | — | 311–312 |
| cc_hookshot_toast | `440 × 0.010 × lfo` | `523.25 × 0.007 × (1-lfo)` | — | 204 |
| cc_hookshot_faith | `293.66 × 0.008 × lfo` | `349.23 × 0.006 × (1-lfo)` | — | 238–239 |
| cc_hookshot_midnight (pre) | `440 × 0.008 × lfo` | `523.25 × 0.005 × (1-lfo)` | — | 182 |
| cc_hookshot_midnight_v2 (post) | `293.66 × 0.006 × lfo` (D4 only) | — | — | 274 |

**Drift surprises:**
- cc_flora uses `554.37` (C#5); cc_hookshot uses `523.25` (C5). The
  same chord lineage names notes a half-step apart. Per Phase 1 this
  is a deliberate mood split (cottagecore vs hookshot) but it should
  be encoded as the chord set in the mood template, not silently
  embedded in note tables.
- cc_flora always uses `lfo1/lfo2` (independent partials);
  cc_hookshot uses `lfo / (1-lfo)` (anti-correlated partials) on its
  variants but `lfo1/lfo2` on cc_hookshot.py/v2.py — drift inside the
  hookshot family.
- cc_hookshot.py/v2.py give E5 *no LFO at all*; flora gives E5 lfo1.

---

## 3. LFO frequencies (Hz) and phase offsets

| script | lfo1 Hz | lfo2 Hz | phase offset (rad) | line |
|---|---|---|---|---|
| ep02 | 0.12 | 0.18 | +1.0 on lfo2 | 353–354 |
| ep03 | 0.12 | 0.18 | +1.0 on lfo2 | 333–334 |
| ep04 | 0.12 | 0.18 | +1.0 on lfo2 | 377–378 |
| ep05 | 0.12 | 0.18 | +1.0 on lfo2 | 429–430 |
| ep06 | 0.12 | 0.18 | +1.0 on lfo2 | 383–384 |
| ep07 | 0.12 | 0.18 | +1.0 on lfo2 | 380–381 |
| ep08 | 0.12 | 0.18 | +1.0 on lfo2 | 384–385 |
| ep09 | 0.12 | 0.18 | +1.0 on lfo2 | 381–382 |
| ep10 | 0.12 | 0.18 | +1.0 on lfo2 | 382–383 |
| 30s | 0.12 | 0.18 | +1.0 on lfo2 | 378–379 |
| masterpiece | **0.15** | **0.22** | +1.0 on lfo2 | 392–393 |
| cc_hookshot | 0.12 | 0.18 | +1.0 on lfo2 | 309–310 |
| cc_hookshot_v2 | 0.12 | 0.18 | +1.0 on lfo2 | 309–310 |
| cc_hookshot_toast | **single LFO 0.12** | (uses `(1-lfo)` for second) | — | 203 |
| cc_hookshot_faith | **single LFO 0.08** | (uses `(1-lfo)` for second) | — | 237 |
| cc_hookshot_midnight | **single LFO 0.12** | — | — | 181 |
| cc_hookshot_midnight_v2 | **single LFO 0.08** | — | — | 273 |

**Drift cases:**
- `masterpiece` uses `0.15 / 0.22` instead of `0.12 / 0.18`.
- Hookshot variants alternate between 0.08 (faith, midnight_v2) and
  0.12 (others). `0.08` reads as "slower / more uneasy".
- cc_hookshot.py / cc_hookshot_v2.py keep flora's two-LFO pattern;
  the four newer hookshot scripts collapse to single LFO with anti-
  phase on the second partial.
- The `+1.0 rad` decoupling phase is consistent in all two-LFO
  scripts.

---

## 4. Master pad envelope (fade-in / fade-out)

cc_flora "base" envelope: `pad *= np.clip(0.3 + 0.7 * (t / 2.0), 0, 1)
* np.clip((duration - t) / 2.5, 0, 1)`

This is a clipped-line fade-in starting at 30% gain ramping to 100%
over 2.0s, and a clipped-line fade-out over the last 2.5s.

| script | fade_in formula | fade_out formula | line |
|---|---|---|---|
| ep02 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 372 |
| ep03 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 350 |
| ep04 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 405 |
| ep05 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 452 |
| ep06 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 418 |
| ep07 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 423 |
| ep08 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 428 |
| ep09 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 407 |
| ep10 | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 413 |
| 30s | `clip(0.3 + 0.7*(t/2.0), 0, 1)` | `clip((dur-t)/2.5, 0, 1)` | 402 |
| masterpiece | **`clip(t/2.0, 0, 1)`** (starts at 0%, no `0.3 +`) | **`clip((dur-t)/2.0, 0, 1)`** (2.0s tail) | 408–410 |
| cc_hookshot | linspace 1s→4s ramp + linspace 3s tail | (see below) | 315–322 |
| cc_hookshot_v2 | identical to cc_hookshot | identical | 315–322 |
| cc_hookshot_toast | `clip(t/2.5, 0, 1)` × `clip((dur-t)/3.0, 0, 1)` | clipped, 3.0s tail | 206 |
| cc_hookshot_faith | linspace ramp 0→1 over 2s; linspace 3s tail | (see below) | 242–247 |
| cc_hookshot_midnight pre-crash | `clip(t/1.0, 0, 1) × clip((dur-t)/3.0, 0, 1)` | clipped, 3.0s tail | 186 |
| cc_hookshot_midnight post-crash | `clip((t-post_start)/3.0, 0, 1) × clip((dur-t)/3.0, 0, 1)` | clipped, 3.0s tail | 221 |
| cc_hookshot_midnight_v2 post | `clip((t - 4.0)/3.0, 0, 1) × clip((dur-t)/3.0, 0, 1)` | clipped, 3.0s tail | 275 |

**Drift cases:**
- `masterpiece` differs from rest of cc_flora: starts from 0
  (no 0.3 floor) and uses 2.0s tail instead of 2.5s.
- cc_hookshot.py/v2.py is structurally different from all others:
  uses `np.linspace` to construct the envelope (silence 0–1s, ramp
  1s→4s, sustain, linspace tail over last 3s) — see lines 315–322.
- All other hookshot scripts use the cc_flora `clip(...)` style with
  varying time constants (1.0s, 2.0s, 2.5s in, 3.0s out).
- The cc_flora "0.3 + 0.7" floor (start at 30% gain) shows up
  consistently in every flora episode except masterpiece. This is
  the documented "Bluesky doesn't crush the quiet opening" comment
  in 30s.

---

## 5. Chime layer

### Decay constant — `np.exp(-env_t * K)`

| script | K | line |
|---|---|---|
| ep02 | 2.0 | 370 |
| ep03 | 2.0 | 348 |
| ep04 | 2.0 | 401 |
| ep05 | 2.0 | 448 |
| ep06 | 2.0 | 410 |
| ep07 | 2.0 | 420 |
| ep08 | 2.0 | 425 |
| ep09 | 2.0 | 403 |
| ep10 | 2.0 | 409 |
| 30s | 2.0 | 398 |
| masterpiece | **2.5** | 403 |
| cc_hookshot | **2.5** | 332 |
| cc_hookshot_v2 | **2.5** | 332 |
| cc_hookshot_toast | **2.5** | 216 |
| cc_hookshot_faith | **3.0** | 257 |
| cc_hookshot_midnight (post-crash chimes) | **3.0** | 232 |
| cc_hookshot_midnight_v2 | **3.0** | 282 |

**Drift:** cc_flora uses 2.0 (longer ring); hookshot family is 2.5
or 3.0 (shorter ring, tighter mix). `masterpiece` is the
out-of-family flora script using 2.5 — matches its different
chime envelope formula (see attack below).

### Attack constant — `np.clip(env_t * K, 0, 1)`

| script | K | line |
|---|---|---|
| ep02 | 10 | 370 |
| ep03 | 10 | 348 |
| ep04 | 10 | 401 |
| ep05 | 10 | 448 |
| ep06 | 10 | 410 |
| ep07 | 10 | 420 |
| ep08 | 10 | 425 |
| ep09 | 10 | 403 |
| ep10 | 10 | 409 |
| 30s | 10 | 398 |
| masterpiece | **`env_t * 8`** then `clip(env, 0, 1)` (different formula) | 403–404 |
| cc_hookshot | **20** | 332 |
| cc_hookshot_v2 | **20** | 332 |
| cc_hookshot_toast | **20** | 216 |
| cc_hookshot_faith | **20** | 257 |
| cc_hookshot_midnight | **20** (chimes only; crash uses 50/100) | 232 |
| cc_hookshot_midnight_v2 | **20** | 282 |

**Drift:** cc_flora is 10× attack constant; hookshot is 20× (twice
as fast, percussive). `masterpiece` uses a structurally different
formula `env_t * 8` clipped to (0,1) — that means a *ramp* up to
0.125s then flat 1.0, vs cc_flora's clipped ramp to 0.1s.

### Chime gain (sine partial multiplier)

| script | base gain | octave gain | line |
|---|---|---|---|
| ep02 | 0.022 | — | 371 |
| ep03 | 0.022 | — | 349 |
| ep04 | 0.022 | — | 402 |
| ep05 | 0.022 | — | 449 |
| ep06 | 0.022 | — | 411 |
| ep07 | 0.022 | — | 421 |
| ep08 | 0.022 | — | 426 |
| ep09 | 0.022 | — | 404 |
| ep10 | 0.022 | — | 410 |
| 30s | 0.022 | — | 399 |
| masterpiece | **0.025** | — | 405 |
| cc_hookshot | **0.025** | **0.008 (octave-up)** | 333–334 |
| cc_hookshot_v2 | 0.025 | 0.008 | 333–334 |
| cc_hookshot_toast | 0.025 | — (no octave layer) | 217 |
| cc_hookshot_faith | **0.020** | **0.006 (octave-up)** | 258–259 |
| cc_hookshot_midnight | **0.018** | — | 233 |
| cc_hookshot_midnight_v2 | **0.015** | — | 283 |

**Drift:** cc_flora is uniform 0.022 (10/12 scripts); masterpiece is
0.025; hookshot family ranges 0.015–0.025. cc_hookshot.py/v2.py and
faith add an *octave-up* harmonic at the chime frequency × 2 (lines
334, 259). flora and other hookshot variants don't.

### Chime schedules

The schedule (`(t, freq_Hz)` pairs) is **always editorial**, not
drift. Documented per script for canonical extraction:

| script | chimes (t, Hz) | line |
|---|---|---|
| ep02 | 13 chimes 0.1→28.5s; A5/C#6/E6 cluster | 361–366 |
| ep03 | 12 chimes evenly spaced 0.1→28.0s | 341–344 |
| ep04 | 9 chimes; **t=8.5s last before silence; t=13.5s first after** | 392–397 |
| ep05 | 10 chimes; **none in t=12–16 freeze** | 440–444 |
| ep06 | 11 chimes; cable-catch at 22.5 | 402–406 |
| ep07 | 10 chimes; collisions at 13.0 / 17.5 distinct | 413–416 |
| ep08 | 10 chimes; thins after wedge impact 15.0 | 417–422 |
| ep09 | 9 chimes; last at 22.0 (wistful absence) | 396–400 |
| ep10 | 10 chimes; **none after 25.5 (let milestone breathe)** | 401–406 |
| 30s | 13 chimes (same pattern as ep02) | 389–394 |
| masterpiece | 5 chimes; **schedule is a `zip(times, freqs)` not a tuple list** | 399–400 |
| cc_hookshot | **algorithmic loop**: notes `[880,1046.5,1318.5,880,1318.5,1046.5]` starting `ct=3.0`, step `+4.5s` | 326–336 |
| cc_hookshot_toast | fixed schedule `[(4,880),(9,1046.5),(15,1318.5),(21,880),(27,1046.5)]` | 210–211 |
| cc_hookshot_faith | sparse `[(5,587.33),(12,698.46),(20,880),(28,587.33)]` (D5/F5/A5) + eyes-back chord at duration-6 | 251–268 |
| cc_hookshot_midnight | sparse post-crash `[(post_start+2,587.33), (+8,698.46), (+15,880), (+22,587.33)]` (D5/F5/A5) | 228–229 |
| cc_hookshot_midnight_v2 | fixed `[(8,587.33),(16,698.46),(24,880),(32,587.33),(40,698.46)]` | 280 |

**Architectural note:** `cc_hookshot.py` is the only one using an
algorithmic step (4.5 s rhythm). All others use explicit
`(t, freq)` lists.

---

## 6. Lowpass filter

| script | cutoff Hz | order | applied to | line |
|---|---|---|---|---|
| ep02 | 3000 | 4 | pad only | 373 |
| ep03 | 3000 | 4 | pad only | 351 |
| ep04 | 3000 | 4 | pad only | 424 |
| ep05 | 3000 | 4 | pad only | 483 |
| ep06 | 3000 | 4 | pad only | 421 |
| ep07 | 3000 | 4 | pad only | 425 |
| ep08 | 3000 | 4 | pad only | 430 |
| ep09 | 3000 | 4 | pad only | 409 |
| ep10 | 3000 | 4 | pad only | 415 |
| 30s | 3000 | 4 | pad only | 405 |
| masterpiece | 3000 | 4 | pad only | 413 |
| cc_hookshot | 3000 | 4 | **whole mix (sting + pad + chimes)** | 341 |
| cc_hookshot_v2 | 3000 | 4 | whole mix | 341 |
| cc_hookshot_toast | 3000 | 4 | whole mix | 222 |
| cc_hookshot_faith | **2800** | 4 | whole mix | 273 |
| cc_hookshot_midnight | 3000 | 4 | whole mix | 238 |
| cc_hookshot_midnight_v2 | 3000 | 4 | whole mix | 289 |

**Drift:**
- Cutoff is 3000 Hz everywhere except `cc_hookshot_faith` (2800 Hz —
  darker, deliberate per "more tension" comment).
- **Apply target differs by family:** cc_flora applies pre-mix
  (pad only, before chimes are summed in numpy → wait, actually
  chimes are added to `pad` *before* the lowpass in cc_flora too;
  see ep02 lines 361–375). In *cc_flora* the lowpass attenuates
  pad+chimes. In cc_hookshot, lowpass applies *after* sting is
  summed in, so the sting transient is also attenuated. Effective
  difference = **chimes are filtered in both, but sting transients
  are filtered only in hookshot**.

---

## 7. Sting (cc_hookshot only)

Sting = sub thump + transient noise + (optional) high tonal lift.

| script | sub Hz × gain × decay | transient dur (s) × gain × decay | high tone | line |
|---|---|---|---|---|
| cc_hookshot | `60 × 0.35 × exp(-st*8)` over 0.5s | `0.02 × 0.25 × exp(-... *10)` | `880 × 0.08 × clip(st*4) × exp(-st*3)` over 0.5s | 296–302 |
| cc_hookshot_v2 | identical | identical | identical | 296–302 |
| cc_hookshot_toast | `55 × 0.4 × exp(-st*7)` over 0.5s | `0.025 × 0.3 × exp(-... *9)` | — (no high tone) | 192–197 |
| cc_hookshot_faith | `50 × 0.5 × exp(-st*6)` over 0.6s | `0.03 × 0.35 × exp(-... *8)` | `440 × 0.06 × clip(st*3) × exp(-st*4)` over 0.6s | 224–229 |
| cc_hookshot_midnight | *no opening sting* — replaced by crash impact at `crash_time` (sub 30Hz) | — | — | 189–213 |
| cc_hookshot_midnight_v2 | *no opening sting* — replaced by crash at `flip_time` | — | — | 244–267 |

**Drift:**
- Sub frequency: 50 / 55 / 60 Hz (faith/toast/cc_hookshot).
- Sub gain: 0.35 (cc_hookshot) → 0.4 (toast) → 0.5 (faith).
  Increasing intensity per editorial.
- Transient duration: 0.02 / 0.025 / 0.03 s — within ±50%, all sub
  perceptual-threshold differences.
- Decay constants vary 6–10 (sub) and 8–10 (transient) — small.
- High tonal lift only in cc_hookshot/v2 (880 Hz) and faith (440 Hz).
- Midnight pair has no opening sting at all — they emit a CRASH
  instead, treated below as an editorial event (table 9).

### Crash impact (midnight family)

| script | sub Hz × gain × decay | metal clang harmonics | noise burst | second thud | line |
|---|---|---|---|---|---|
| cc_hookshot_midnight | `30 × 0.6 × exp(-... *4)` ×clip(*50) | `[(587,0.15,6),(1174,0.08,8),(1760,0.05,10),(2349,0.03,12)]` | `randn × 0.2 × exp(-... *15) × clip(*100)` | at `crash_time + 2.5`: `40 × 0.4 × exp(-...*5)` + `randn × 0.15 × exp(-...*12)` | 196–213 |
| cc_hookshot_midnight_v2 | `30 × 0.5 × exp(-... *4)` ×clip(*50) | `[(587,0.12,6),(1174,0.07,8),(1760,0.04,10)]` (no 2349) | `randn × 0.15 × exp(-... *15) × clip(*100)` | at `flip_time + 2.0`: `40 × 0.35 × exp(-...*5)` + `randn × 0.12 × exp(-...*12)` | 250–267 |

Drift: v2 is ~17–20% softer on sub and noise, drops the highest
clang harmonic (2349 Hz), and lands the second thud 0.5 s sooner.

---

## 8. Master gains (final mix multiplier)

Three master-gain decisions:
1. **Pad target gain** — final normalized peak.
2. **TTS multiplier** — gain applied to TTS clip when summed into
   composite (cc_flora MoviePy composite vs cc_hookshot inline mix).
3. **Final mix headroom** — peak ceiling on full output.

### Pad target gain (after `pad / max(abs(pad)) * G`)

| script | G | line |
|---|---|---|
| ep02 | 0.22 | 375 |
| ep03 | 0.22 | 353 |
| ep04 | 0.22 | 426 |
| ep05 | 0.22 | 485 |
| ep06 | 0.22 | 423 |
| ep07 | 0.22 | 427 |
| ep08 | 0.22 | 432 |
| ep09 | 0.22 | 411 |
| ep10 | 0.22 | 417 |
| 30s | 0.22 | 409 |
| masterpiece | **0.25** | 417 |
| cc_hookshot | 0.7 (peak ceiling on stereo, not pad alone) | 354 |
| cc_hookshot_v2 | 0.7 | 354 |
| cc_hookshot_toast | 0.7 | 230 |
| cc_hookshot_faith | 0.7 | 286 |
| cc_hookshot_midnight | **0.75** | 246 |
| cc_hookshot_midnight_v2 | **0.75** | 298 |

**Drift:** cc_flora is uniform 0.22 except masterpiece at 0.25.
Hookshot stereo peak is 0.7 except midnight pair at 0.75.

### TTS / narration multiplier in mix

| script | multiplier | mechanism | line |
|---|---|---|---|
| cc_flora ep02–ep10, 30s, masterpiece | 1.0 (MoviePy `CompositeAudioClip`, no manual gain) | composite | n/a |
| cc_hookshot | 1.2 | manual `narration * 1.2` | 392 |
| cc_hookshot_v2 | 1.2 | identical | 392 |
| cc_hookshot_toast | 1.2 | identical | 261 |
| cc_hookshot_faith | 1.2 | identical | 319 |
| cc_hookshot_midnight | 1.2 | identical | 277 |
| cc_hookshot_midnight_v2 | 1.2 | identical | 342 |

No drift on the multiplier — uniform 1.2× across hookshot family.

### Final mix peak ceiling

| script | ceiling | line |
|---|---|---|
| cc_flora all | (none — relies on MoviePy default) | n/a |
| cc_hookshot all | 0.88 | 395 / 263 / 322 / 278 / 344 |

No drift on ceiling.

### Sidechain duck depth (hookshot only)

| script | reduction | smoothing window | line |
|---|---|---|---|
| cc_hookshot | 0.6 (60%) | `int(0.15 * sr)` | 386, 391 |
| cc_hookshot_v2 | 0.6 | 0.15 s | 386, 391 |
| cc_hookshot_toast | 0.6 | 0.15 s | 255, 260 |
| cc_hookshot_faith | 0.6 | 0.15 s | 313, 318 |
| cc_hookshot_midnight | 0.6 | 0.15 s | 271, 276 |
| cc_hookshot_midnight_v2 | 0.6 | 0.15 s | 338, 341 |

No drift — uniform across hookshot family. Codifies the
"hookshot ducks aggressively" philosophy in the plan.

---

## 9. Special editorial windows (per-episode events)

These are deliberate per-episode, *not* drift to canonicalize. They
must survive the lift either as `variant=` kwargs or via callable
inserts into the chime/event schedule.

| script | event | window | mechanism | line |
|---|---|---|---|---|
| ep02 | act-3 Bb3 minor-second tension | t=20→duration | additive sine 233.08 × 0.015 × env | 358–360 |
| ep03 | act-3 hopeful E4 shimmer | t=20→duration | `329.63 × 0.012 × act3_env` | 338–340 |
| **ep04** | **battery-death low-pass + silence + wake** | **9.5–10.5 fade, 10.5–13.0 silence, 13.0–15.0 wake-in** | `death_env`, `silence_mask`, `wake_env` | 408–421 |
| ep04 | wake-up E4 bloom | t=13–15 | `329.63 × 0.018 × wake` | 387–389 |
| ep05 | freeze-zone thin + 5 shutter clicks + glitch noise + restore | 10–12 thin to 0.4×, 12–15 quiet, 12.0/12.6/13.2/13.8/14.4 clicks, 15.0–15.2 glitch, 15.0–16.5 restore | mask + ease_out_np + per-click random RandomState | 454–480 |
| ep06 | act-1 Bb3 dying-battery dissonance | t=0→10 | `233.08 × 0.008 × act1_tension` | 389–391 |
| ep06 | recharge E4 bloom | t=10–13 | `329.63 × 0.015 × recharge` | 393–395 |
| ep06 | cable-catch dissonant burst | t=22.5–22.7 | `466.16 × 0.03 × exp(-...*15)` | 413–415 |
| ep07 | collision impacts + low thuds | t=13.0 / 17.5 | `randn × 0.08 × exp(-...*25)` + `55Hz × 0.04 × exp(-...*10)` | 397–410 |
| ep08 | tension Bb3 build (act 2) | t=10→20 | `233.08 × 0.012 × tension` | 394–396 |
| ep08 | uncertainty pad-thin | t=20→duration | `pad *= 1.0 - uncertain * 0.4` (drops to 60%) | 398–400 |
| ep08 | wedge impact at 15.0 | 0.2s noise + 0.4s 55Hz thud | `randn × 0.06 × exp(-...*20)` + `55Hz × 0.04 × exp(-...*8)` | 402–414 |
| ep09 | act-2 hope E4 | t=10→20 | `329.63 × 0.012 × hope` | 387–389 |
| ep09 | act-3 wistful Bb3 | t=20→duration | `233.08 × 0.006 × wistful` (gentle) | 391–393 |
| ep10 | act-1 Bb3 drift frustration | t=0→10 | `233.08 × 0.006 × drift_env` | 388–390 |
| ep10 | act-2/3 hope E4 | t=10→duration | `329.63 × 0.014 × hope` | 392–394 |
| ep10 | act-3 B4 milestone shimmer | t=22–28 | `493.88 × 0.005 × shimmer` | 396–398 |
| 30s | act-3 Bb3 tension | t=20→duration | `233.08 × 0.015 × act3_env` | 385–386 |
| cc_hookshot_faith | "eyes back" sting | t=duration-6 | A5/C6/E6 chord with rising attack `clip(ebt*5)` × `exp(-ebt*2)` | 263–268 |
| cc_hookshot_midnight | crash + 2nd thud + post-crash D-minor cross-fade | crash_time / +2.5 / post_start=+4 | thud + clang + noise + cross-fade pre/post pad | 189–224 |
| cc_hookshot_midnight_v2 | R2 mood tones at 0.25/2.0/4.0/12.0 + crash + post drone | 4 R2 events + crash + 4-sec ramp | `render_mood_tones` snippets summed in | 217–276 |

**Surprises beyond the plan's note:**
- ep04's "battery death" (plan-mentioned) is paired with a
  dedicated **wake-up envelope** that *adds* a louder E4 partial
  exactly when the silence ends. The plan describes the silence; it
  doesn't describe the wake bloom. They're a unit.
- **ep05 has 5 shutter clicks + a 200ms glitch noise burst + a
  pad-thin window.** That's three editorial events bundled — one of
  the more complex per-episode insert sets. Worth capturing as a
  named compound variant rather than three separate kwargs.
- **ep07 has audible impacts** (Pelican thud at 13.0, barrel thud
  at 17.5) — same structural pattern as ep08's wedge impact at 15.0.
  These four impact-thud events across ep07/ep08 are the same
  primitive (call it `impact(t, decay=8|10|25, gain=0.04|0.06|0.08)`)
  with mild parameter drift — a candidate for a real lib helper, not
  a variant flag.
- **ep10 is the only flora script with B4** (`493.88 Hz`). All
  others stay in {A2, E3, A3, A4, C#5, E5, Bb3, E4} ± act-tension
  partials. ep10 reaches up to B4 for the milestone — should be
  preserved as the "ep10_milestone" variant or as a chord parameter.
- **cc_hookshot_midnight_v2 imports a different module** (R2-style
  `render_mood_tones`) defined elsewhere in the file. This is its
  signature feature; not drift, but it means midnight_v2 cannot
  simply call into a generic primitive — it needs the mood-tone
  generator preserved.

---

## 10. TTS stability / similarity_boost / style / timeout

| script | stability | similarity_boost | style | timeout | line |
|---|---|---|---|---|---|
| ep01 | **0.6** | **0.7** | 0.15 | 120 | 96–99 |
| ep02 | 0.65 | 0.72 | 0.1 | 120 | 389 |
| ep03 | 0.65 | 0.72 | 0.1 | 120 | 366 |
| ep04 | 0.55 | 0.72 | 0.15 | 120 | 451 |
| ep05 | 0.55 | 0.72 | 0.15 | 120 | 507–510 |
| ep06 | 0.55 | 0.72 | 0.15 | 120 | 445–448 |
| ep07 | 0.55 | 0.72 | 0.15 | 120 | 449–452 |
| ep08 | 0.55 | 0.72 | 0.15 | 120 | 454–457 |
| ep09 | 0.55 | 0.72 | 0.15 | 120 | 430 |
| ep10 | 0.55 | 0.72 | 0.15 | 120 | 436 |
| 30s | 0.65 | 0.72 | 0.1 | 120 | 427 |
| masterpiece | 0.65 | 0.72 | 0.1 | 120 | 437 |
| cc_hookshot | 0.65 | 0.72 | 0.1 | 120 | 171, 174 |
| cc_hookshot_v2 | 0.65 | 0.72 | 0.1 | 120 | 171, 174 |
| cc_hookshot_toast | 0.65 | 0.72 | 0.1 | 120 | 171, 173 |
| cc_hookshot_faith | 0.65 | 0.72 | 0.1 | 120 | 201, 203 |
| cc_hookshot_midnight | 0.65 | 0.72 | 0.1 | 120 | 156, 158 |
| cc_hookshot_midnight_v2 | 0.65 | 0.72 | 0.1 | 120 | 313, 315 |

**Drift cases:**
- ep01: `0.6 / 0.7 / 0.15` (the comment says "preserves ep01's
  original 0.6/0.7/0.15 voice settings"). One-off.
- ep02 / ep03 / 30s / masterpiece: `0.65 / 0.72 / 0.1` (early flora
  era + script-canon).
- ep04 → ep10: `0.55 / 0.72 / 0.15` (later flora era — slightly
  less stable, slightly more expressive).
- All hookshot scripts: `0.65 / 0.72 / 0.1`.
- `timeout=120` is uniform.

The pattern is **a flora-era split** between the early scripts
(ep02/ep03 + 30s/masterpiece) and the later season (ep04–ep10).

---

## Canonical recommendation summary

For each parameter family, proposed canonical + the episodes that
need a `variant=` kwarg.

### 1. Pad fundamentals (drone)
- **Canonical:** `[(110, 0.05), (164.81, 0.035), (220, 0.025)]` for
  cc_flora; `[(110, 0.04), (130.81, 0.025), (164.81, 0.030),
  (220, 0.020)]` for hookshot A-minor; D-minor swap available via
  mood. Two mood templates: `cottagecore_warm` (flora 3-partial) and
  `hookshot_attention` (4-partial).
- **Variants:** `masterpiece` keeps current 1.20× louder drone via
  `mood="cottagecore_masterpiece"` or `gain_scale=1.20` kwarg.
  Faith uses `mood="hookshot_grief"` (D-min). Midnight pair maps to
  `mood="hookshot_collapse"` (A-min pre, D-min post — the cross-fade
  itself is the variant, see Phase 6 mood templates).

### 2. Shimmer
- **Canonical:** `[(440, 0.010), (554.37, 0.007), (659.25, 0.005)]`
  with lfo1/lfo2 multiplications matching cc_flora's pattern (lfo1
  on partials 1+3, lfo2 on partial 2).
- **Variants:** masterpiece +20% gains; hookshot mood swaps to
  `523.25` (C5) instead of `554.37` (C#5). The hookshot script-
  era variants that use anti-correlated `(1-lfo)` instead of two
  LFOs need a `lfo_mode="anti"` kwarg (or just live in their mood).

### 3. LFO Hz
- **Canonical:** `lfo1=0.12 Hz, lfo2=0.18 Hz, phase_offset=1.0 rad`
  on lfo2.
- **Variants:** `masterpiece` uses `0.15/0.22`; faith and
  midnight_v2 use `0.08`. Two extra mood entries.

### 4. Master pad envelope
- **Canonical:** `clip(0.3 + 0.7*(t/2.0), 0, 1) * clip((dur-t)/2.5,
  0, 1)` (the cc_flora 0.3-floor 2.0s-in 2.5s-out pattern).
- **Variants:**
  - `variant="hookshot_linspace"` for cc_hookshot.py / v2.py (the
    1s-silent / 1→4s ramp / 3s linspace tail formulation).
  - `variant="masterpiece_zerofloor"` (no 0.3 floor, 2.0s out).
  - `variant="hookshot_short_in"` for midnight pre-crash (1.0s in).
  - `variant="post_crash_delayed"` for midnight post-crash (envelope
    starts at `t-post_start`, not 0).

### 5. Chime decay constant K
- **Canonical:** `K=2.0` for `cottagecore_warm` mood; `K=2.5` for
  `hookshot_attention`; `K=3.0` for `hookshot_grief` (faith,
  midnight). Drives off mood, no variant kwarg needed.
- (`masterpiece` `K=2.5` — its mood is "music-box-cottagecore" so
  call it a variant or push it to its own mood.)

### 6. Chime attack constant K
- **Canonical:** `K=10` (cottagecore mood); `K=20` (hookshot mood).
- masterpiece's `env_t * 8 → clip(0,1)` is structurally close but
  slightly slower (clipped at 0.125s vs 0.1s); make it variant
  `attack_curve="masterpiece"` or absorb into its mood.

### 7. Chime gain
- **Canonical:** `0.022` cottagecore, `0.025` hookshot, `0.020`
  hookshot_grief. Editorial via mood.
- Octave-up (`+ sin(freq*2) * 0.008`) is a hookshot-only feature;
  attach to mood as `chime_octave_gain=0.008` (cottagecore = 0.0).

### 8. Lowpass
- **Canonical cutoff:** 3000 Hz, order 4.
- **Apply target:** **pad-only** (cc_flora) vs **whole-mix**
  (cc_hookshot). Make the mix-stage a parameter
  `apply_lowpass_to="pad" | "mix"` on the assembler (not the
  primitive). The primitive returns unfiltered; the pipeline
  decides what to filter.
- **Variant:** `cc_hookshot_faith` 2800 Hz cutoff — pass via
  `lowpass_hz=2800` kwarg.

### 9. Sting
- **Canonical (hookshot_attention):** `sub_hz=60, sub_gain=0.35,
  sub_decay=8, dur=0.5, transient_dur=0.02, transient_gain=0.25,
  transient_decay=10, high_hz=880, high_gain=0.08, high_dur=0.5`.
- **Variants:** toast (sub=55, gain=0.4, no high tone); faith
  (sub=50, gain=0.5, longer 0.6s, high=440). Encode as mood
  parameters, not variant kwargs.

### 10. Crash (midnight family — new primitive)
- New primitive `crash_impact(t_start, *, sub_hz=30, sub_gain=0.6,
  clang_partials, noise_gain=0.2, second_thud_offset=2.5)`.
- Variant `crash_impact_v2` for midnight_v2's slightly softer +
  3-harmonic version. Two flavors total.

### 11. Master gains
- **Pad target:** 0.22 cottagecore, 0.7 hookshot stereo peak.
  masterpiece (0.25) and midnight (0.75) get mood-level overrides.
- **TTS multiplier:** 1.2 in hookshot mix (codify as
  `narration_gain=1.2` default). cc_flora composites without manual
  gain — leave alone.
- **Final ceiling:** 0.88 in hookshot. cc_flora doesn't apply one.

### 12. TTS settings
- **Canonical:** `stability=0.55, similarity_boost=0.72, style=0.15,
  timeout=120` (current cc_flora "late season" preset, ep04–ep10).
  This was the consensus per Phase 4 sign-off in the previous lift.
- **Variants:**
  - **ep01** keeps `0.6 / 0.7 / 0.15` (already documented in code
    comment as deliberate). One-off legacy preset.
  - **ep02 / ep03 / 30s / masterpiece / all hookshot scripts**:
    `0.65 / 0.72 / 0.1`. Likely candidates to migrate to canonical
    0.55/0.72/0.15 — but listen-test first. Mark as `tts_preset=
    "early_flora"` if the tone difference is preserved.

---

## Drift counts per family

| family | drift cases | notes |
|---|---|---|
| 1. Pad fundamentals | 1 (masterpiece +20%) + family split (flora/hookshot) | identical inside cc_flora ep02–ep10 + 30s |
| 2. Shimmer | 1 (masterpiece +20%) + family split | identical inside cc_flora ep02–ep10 + 30s |
| 3. LFO Hz | 3 (masterpiece, faith, midnight_v2) | identical inside cc_flora ep02–ep10 + 30s |
| 4. Master envelope | 5 distinct shapes (flora-base, masterpiece, hookshot-linspace, midnight-pre 1.0s in, midnight-post delayed) | flora-base shared by 10 of 12 cc_flora scripts |
| 5. Chime decay K | 3 values (2.0, 2.5, 3.0) | flora-uniform 2.0 except masterpiece |
| 6. Chime attack K | 3 values (10, 20, masterpiece-formula) | flora-uniform 10 except masterpiece |
| 7. Chime gain | 5 values (0.015, 0.018, 0.020, 0.022, 0.025) | flora-uniform 0.022 except masterpiece |
| 8. Lowpass | 1 cutoff drift (faith 2800) + family-level apply-target split | otherwise uniform 3000/4 |
| 9. Sting / crash | every hookshot variant differs | toast/faith differ from cc_hookshot.py; midnight pair has crash, no sting |
| 10. Master gains | 2 drifts (masterpiece pad 0.25, midnight pair stereo 0.75) | TTS gain + ceiling + duck depth all uniform inside hookshot |
| 11. Editorial windows | every cc_flora script (except 30s and masterpiece) has unique inserts | per-episode by design, not drift |
| 12. TTS settings | 3 distinct presets: ep01, early-flora (4 scripts), late-flora (7 scripts) + hookshot (6 scripts) match early-flora | ep01 is the one-off |

---

## Key surprises

1. **`cc_hookshot.py` and `cc_hookshot_v2.py` are byte-identical**
   in their `generate_bed_audio` and `mix_tts` blocks. Either v2 is
   a rename or one of them should be retired before the lift.
   (Investigation: confirm via diff outside this audit.)
2. **ep01 has no inline pad at all.** The plan's Phase 3 ("ep01
   warm canary") needs to be reframed: ep01's migration is *only*
   TTS-stability canonicalization, not pad migration. There's
   nothing to swap to a lib `ambient_pad` call because there's no
   pad rendering today.
3. **masterpiece is the most-divergent cc_flora script**, not ep02
   as the plan hypothesizes ("ep02 most-divergent in cc_flora").
   ep02 has only one editorial insert (act-3 Bb3) and otherwise
   matches the flora-base perfectly. **masterpiece** has different
   drone gains (1.20×), different shimmer gains, different LFO
   frequencies, different chime envelope formula, different chime
   gain, different fade-in floor, and different pad target gain.
   It is closer to a *different mood* than to ep02–ep10.
4. **The cc_hookshot family fractures into 3 micro-eras** by chime
   gain / shimmer pattern: cc_hookshot.py + v2.py (octave-up
   chimes, 2-LFO shimmer, A-min) — toast (no octave, 1-LFO,
   A-min) — faith + midnight pair (no octave on faith aside, 1-LFO,
   D-min). Mood templates need three slots, not one.
5. **ep04's "battery death" is paired with a wake-up bloom** that
   the plan doesn't describe. Treat as one compound variant
   `variant="ep04_battery_death_wake"`, not just a fade.
6. **ep05's freeze-zone is the most complex per-episode insert** —
   pad-thin + 5 shutter clicks (each with seeded RandomState for
   reproducibility) + 200 ms glitch noise burst + 1.5 s pad
   restore. Capture as `variant="ep05_freeze_compound"` rather than
   four kwargs.
7. **ep07's collision impacts and ep08's wedge impact share a
   primitive** that is not abstracted today — three call sites of
   essentially the same `noise + low-thud` formula with parameter
   drift (decay 8/10/25, gain 0.04/0.06/0.08). This is a candidate
   for an `impact(t, *, decay, gain)` lib helper that callers
   schedule explicitly — don't fold it into a `variant=` flag.
8. **Lowpass apply-target is a pipeline decision, not a primitive
   one.** cc_flora filters pad+chimes (sting absent); cc_hookshot
   filters pad+chimes+sting. The `ambient_pad` primitive should
   return *unfiltered* and let the assembler decide. Otherwise the
   lib has to duplicate the lowpass per family.
9. **TTS settings show two flora eras, not one.** ep02/ep03/30s/
   masterpiece (`0.65/0.72/0.1`) precede ep04–ep10 (`0.55/0.72/
   0.15`). Plan currently treats only ep01 as the legacy outlier;
   the early-flora scripts are also a documented preset that needs
   either migration or `tts_preset=` retention.
10. **cc_hookshot_midnight_v2 uses a separate R2 mood-tone
    generator** (`render_mood_tones`) that is not present in the
    other 17 scripts. It cannot collapse to a generic primitive
    without preserving (or re-implementing) that subsystem. Mark as
    a no-go for full primitive collapse — keep R2 inline.
