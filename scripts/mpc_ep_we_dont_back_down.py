"""
MPC "We Don't Back Down" — 30s vertical reel, Juan + chant + tagline.

Three beats: a survivor's voice, the chant that names who we're for, and
the tagline as conclusion. No politicians, no opening card — the released
detainee leads, the crowd echoes, MPC closes the loop.

Beats (30s):
  0:00-0:17  JUAN          — Dm — released after 90 days at North Lake .........
                             "I was released Friday the 24th of April. Detained
                              three months at North Lake, 90 days..."
  0:17-0:24  FOR OUR       — Am — chant: locked-inside ........................
                             "This is for our neighbors who are locked inside,
                              together we'll abolish ICE."
  0:24-0:30  WE DON'T      — A  — chant b-roll + tagline + synth VO ............
                             "We don't back down. Chip in. Link in bio."

Output: E:/AI/CVS/ComfyUI/output/mpc/we_dont_back_down.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_we_dont_back_down.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path as _Path

# Make `import cvs_lib` work when running this script directly.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

from cvs_lib import audio as cvs_audio
from cvs_lib.elevenlabs_tts import (
    measure_tts_duration as _lib_measure_tts_duration,
    synthesize_narration as _lib_synthesize_narration,
)
from cvs_lib.env import load_env as _lib_load_env
from cvs_lib.mpc_chrome import ChromeRenderer, Layout, load_palette
from cvs_lib.moviepy_helpers import build_beat_clip as _lib_build_beat_clip
from cvs_lib.moviepy_helpers import spec_well as _lib_spec_well
from cvs_lib.preflight import run_or_exit as _preflight
from cvs_lib.preview import render_beat_stills as _render_beat_stills

# --------------------------------------------------------------------------- #
# Paths + brand
# --------------------------------------------------------------------------- #

FPS = 30
DURATION = 30.0
LAYOUT = Layout(
    BANNER_H=140, WELL_TOP=140, WELL_H=1750 - 140,
    CAPTION_BOTTOM=1620, CHIP_Y=168,
    CTA_CHROME_BOTTOM=720, CTA_WELL_TOP=720,
)
W, H = LAYOUT.W, LAYOUT.H

ROOT = Path("E:/AI/CVS/mpc")
BRAND = ROOT / "brand"
ENV_PATH = Path("E:/AI/CVS/.env")
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "we_dont_back_down.mp4"
AUDIO_PATH = OUTPUT_DIR / "we_dont_back_down_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
TTS_PREFIX = "wdbd"
_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")

PALETTE = load_palette(BRAND / "palette.json")
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")

CHROME = ChromeRenderer(
    palette=PALETTE,
    font_headline=PALETTE["fonts"]["headline"]["path"],
    font_body=PALETTE["fonts"]["body"]["path"],
    logo_path=LOGO_PATH,
    layout=LAYOUT,
)
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]

CAPTION_BOTTOM = LAYOUT.CAPTION_BOTTOM
WELL_TOP = LAYOUT.WELL_TOP
WELL_H = LAYOUT.WELL_H
CTA_WELL_TOP = LAYOUT.CTA_WELL_TOP
CTA_WELL_H = LAYOUT.CTA_WELL_H

# --------------------------------------------------------------------------- #
# Beats. Each entry is one cut: (slug, label_for_chip, chord_key, duration,
# footage spec). chord_key indexes SCENE_CHORDS below.
# --------------------------------------------------------------------------- #

BEATS = [
    # JUAN — released after 90 days at North Lake. Source starts at 11.0 to
    # catch the tail of "So this is from Juan." into his actual testimony.
    # 17s holds through the regulatory critique without going past it.
    ("juan",    17.0, "grief",  "JUAN  •  RELEASED 4/24",
     {"path": RAW_DIR / "20260425_155313.mp4", "in_t": 11.0, "out_t": 28.0,
      "audio_gain": 1.2}),
    # FOR OUR NEIGHBORS — the chant that says who Juan IS to the rally.
    # Bridges from one survivor's voice to the collective answer.
    ("neighbors", 7.0, "minor",  "FOR OUR NEIGHBORS",
     {"path": RAW_DIR / "20260425_170245.mp4", "in_t": 7.5, "out_t": 14.5,
      "audio_gain": 1.0}),
    # CTA — chant b-roll bottom half, brand chrome top, synth VO closes.
    ("cta",     6.0, "resolve", "WE DON'T BACK DOWN",
     {"path": RAW_DIR / "20260425_170137.mp4", "in_t": 12.0, "out_t": 18.0,
      "audio_gain": 0.55,
      "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H}),
]
# Sanity: 17+7+6 = 30 ✓

def _build_scenes():
    out, t = [], 0.0
    for slug, dur, *_ in BEATS:
        out.append((t, t + dur, slug))
        t += dur
    return out

SCENES = _build_scenes()

# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #

SR = 44100
N = int(SR * DURATION)

SCENE_CHORDS = {
    "minor":   [110.00, 164.81, 220.00],
    "grief":   [73.42,  110.00, 146.83, 174.61],
    "build":   [130.81, 196.00, 261.63],
    "resolve": [110.00, 164.81, 220.00, 277.18],
}

NARRATION_LINES = [
    {"slug": "cta", "start_in_beat": 0.6,
     "text": "We don't back down. Chip in. Link in bio."},
]

CTA_RALLY = "ice_out_romulus"
_CTA_CFG = json.loads((ROOT / "cta.json").read_text(encoding="utf-8"))
_CTA_DEFAULTS = _CTA_CFG.get("defaults", {})
_CTA_RALLY_CFG = _CTA_CFG["rallies"][CTA_RALLY]
CTA_URL = _CTA_RALLY_CFG.get("url", _CTA_DEFAULTS.get("url", ""))
CTA_HANDLE_LINE = _CTA_RALLY_CFG.get(
    "handle_line", _CTA_DEFAULTS.get("handle_line", ""))
# CTA chrome typography — "WE DON'T BACK DOWN" is wider than other taglines
# so it ships at 72/48 (vs 96/44 default) to keep it on a single line.
CTA_HEADLINE = "WE DON'T BACK DOWN"
CTA_HEADLINE_SIZE = 72
CTA_SUBHEAD = "CHIP IN"
CTA_SUBHEAD_SIZE = 48

# --------------------------------------------------------------------------- #
# Brand chrome (delegates to cvs_lib.mpc_chrome.ChromeRenderer)
# --------------------------------------------------------------------------- #

# Per-beat chip color. Both survivor beats stay in the same warm magenta
# so the visual register reads "same KIND of evidence" — no chip-color cut
# distracts from the testimony.
CHIP_COLORS = {
    "juan":      C["deep_magenta"],
    "neighbors": C["deep_magenta"],
    "cta":       C["deep_magenta"],
}


def render_beat_chrome(slug, chip_label, well_transparent=True):
    return CHROME.render_beat(
        chip_label=chip_label,
        chip_color=CHIP_COLORS.get(slug),
        well_transparent=well_transparent,
    )


def render_cta_chrome(well_transparent=True):
    return CHROME.render_cta(
        headline=CTA_HEADLINE, subhead=CTA_SUBHEAD,
        url=CTA_URL, handle_line=CTA_HANDLE_LINE,
        well_transparent=well_transparent,
        gradient_angle=300.0,
        headline_size=CTA_HEADLINE_SIZE,
        subhead_size=CTA_SUBHEAD_SIZE,
    )


def font(size, bold=True):
    return CHROME.font(size, bold=bold)


# --------------------------------------------------------------------------- #
# Audio synthesis (delegates to cvs_lib.audio + cvs_lib.elevenlabs_tts)
# --------------------------------------------------------------------------- #

def _scene_start(slug):
    return next(s[0] for s in SCENES if s[2] == slug)


def load_env(path=ENV_PATH):
    return _lib_load_env(path)


def harmonic_hum():
    return cvs_audio.harmonic_hum(
        SCENES, BEATS, SCENE_CHORDS,
        duration=DURATION, sr=SR,
    )


def synthesize_narration(env):
    # AI VO disabled 2026-04-26 per editorial call. Source audio + bed only.
    return None


def measure_tts_duration(slug):
    return _lib_measure_tts_duration(
        slug, cache_dir=TTS_CACHE, cache_prefix=TTS_PREFIX)


def sidechain_duck(bed, voice, threshold=0.025, ratio=0.30,
                   attack_ms=20.0, release_ms=180.0):
    return cvs_audio.sidechain_duck(
        bed, voice, sr=SR, threshold=threshold, ratio=ratio,
        attack_ms=attack_ms, release_ms=release_ms,
    )


def vo_duck_envelope(voice, threshold=0.02, low_gain=0.5,
                     attack_ms=10.0, release_ms=200.0):
    return cvs_audio.vo_duck_envelope(
        voice, total_n=N, sr=SR, threshold=threshold, low_gain=low_gain,
        attack_ms=attack_ms, release_ms=release_ms,
    )


def to_int16_stereo(mono):
    return cvs_audio.to_int16_stereo(mono)


# --------------------------------------------------------------------------- #
# Footage compositor (delegates to cvs_lib.moviepy_helpers)
# --------------------------------------------------------------------------- #

def _rotation_baked_path(path):
    from cvs_lib.moviepy_helpers import rotation_baked_path
    return rotation_baked_path(path, cache_dir=_ROT_CACHE_DIR)


def _spec_well(spec):
    return _lib_spec_well(spec, default_top=WELL_TOP, default_h=WELL_H)


def build_beat_clip(slug, chip_label, footage_spec, duration,
                    is_cta, fadein=0.0, fadeout=0.0):
    if is_cta:
        chrome_rgba = render_cta_chrome(well_transparent=True)
    else:
        chrome_rgba = render_beat_chrome(slug, chip_label, well_transparent=True)
    well_top, well_h = _spec_well(footage_spec)
    return _lib_build_beat_clip(
        chrome_rgba=chrome_rgba,
        footage_spec=footage_spec,
        duration=duration,
        W=W, H=H,
        well_top=well_top, well_h=well_h,
        rotation_cache_dir=_ROT_CACHE_DIR,
        fadein=fadein, fadeout=fadeout,
    )


# --------------------------------------------------------------------------- #
# Audio mix
# --------------------------------------------------------------------------- #

def _shot_audio_range(shot):
    return float(shot.get("audio_in", shot["in_t"])), \
           float(shot.get("audio_out", shot["out_t"]))


def extract_audio_segment(path, t0, t1):
    return cvs_audio.extract_audio_segment(path, t0, t1, sr=SR)


def build_source_audio_track():
    track = np.zeros(N, dtype=np.float32)
    fade_n = int(0.05 * SR)
    for slug, _dur, _chord, _label, spec in BEATS:
        if spec is None:
            continue
        a0, a1 = _shot_audio_range(spec)
        seg = extract_audio_segment(_rotation_baked_path(spec["path"]), a0, a1)
        if seg is None:
            continue
        gain = float(spec.get("audio_gain", 1.0))
        if len(seg) > 2 * fade_n:
            seg[:fade_n] *= np.linspace(0, 1, fade_n)
            seg[-fade_n:] *= np.linspace(1, 0, fade_n)
        place_t = _scene_start(slug)
        i0 = int(place_t * SR)
        i1 = min(N, i0 + len(seg))
        track[i0:i1] += seg[: i1 - i0] * gain
        print(f"[audio/{slug}] +{Path(spec['path']).name} a={a0:.2f}..{a1:.2f}s "
              f"@ t={place_t:.2f}s gain={gain}")
    return track


def build_audio():
    print("[audio] harmonic hum...")
    bed = harmonic_hum()
    print("[audio] synth VO (CTA only)...")
    voice = synthesize_narration(load_env())
    if voice is None:
        voice = np.zeros(N, dtype=np.float32)
    print("[audio] source-audio track...")
    source = build_source_audio_track()

    source = source * vo_duck_envelope(voice, low_gain=0.45)

    speech = voice + source
    if float(np.max(np.abs(speech))) > 1e-4:
        bed = sidechain_duck(bed, speech)

    mix = bed * 0.5 + voice * 1.0 + source * 1.0
    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.9
    return mix


def write_wav(mono, path=AUDIO_PATH):
    cvs_audio.write_wav(mono, path, sr=SR)
    print(f"[audio] wrote {path}")


# --------------------------------------------------------------------------- #
# Captions — Whisper segments (intersection mode) + synth VO timing for CTA.
# Phase 6 will standardize all scripts on cvs_lib.captions auto-fill
# (midpoint-mode); for now this preserves byte-identity for frame
# regression.
# --------------------------------------------------------------------------- #

def _load_whisper_segments(path):
    """Load segments from `mpc/index/clips/<stem>.json`. Returns list of
    (start, end, text) in CLIP-LOCAL time."""
    stem = Path(path).stem
    p = ROOT / "index" / "clips" / f"{stem}.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return [(s["start"], s["end"], s["text"]) for s in
                d.get("transcript", {}).get("segments", [])]
    except Exception:
        return []


def build_caption_events():
    """For each non-CTA beat, take its source clip's Whisper segments, clip
    them to in_t..out_t, offset to scene-timeline. CTA caption uses the
    synth-VO line at its measured TTS duration."""
    events = []
    for slug, dur, _chord, _label, spec in BEATS:
        if spec is None:
            continue
        scene_t0 = _scene_start(slug)
        if slug == "cta":
            for line in NARRATION_LINES:
                if line["slug"] != "cta":
                    continue
                vo_dur = measure_tts_duration("cta")
                if vo_dur > 0.0:
                    start = scene_t0 + line["start_in_beat"]
                    events.append({"start": start,
                                   "end":   min(scene_t0 + dur, start + vo_dur),
                                   "text":  line["text"]})
            continue
        in_t = float(spec["in_t"])
        out_t = float(spec["out_t"])
        for s_start, s_end, text in _load_whisper_segments(spec["path"]):
            seg_start = max(s_start, in_t)
            seg_end = min(s_end, out_t)
            if seg_end - seg_start < 0.25:
                continue
            events.append({"start": scene_t0 + (seg_start - in_t),
                           "end":   scene_t0 + (seg_end - in_t),
                           "text":  text.strip()})
    events.sort(key=lambda e: e["start"])
    return events


def make_caption_clips(events):
    from cvs_lib.captions import make_caption_clips as _lib_make_caption_clips
    return _lib_make_caption_clips(
        events, width=W, caption_bottom=CAPTION_BOTTOM,
        font_path=FONT_HEADLINE,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def _chrome_for_preview(slug, chip_label, spec):
    if slug == "cta":
        return render_cta_chrome(well_transparent=True)
    return render_beat_chrome(slug, chip_label, well_transparent=True)


def _spec_well_for_preview(spec):
    return _spec_well(spec) if spec else (WELL_TOP, WELL_H)


def main():
    print("Building MPC We Don't Back Down (30s reel)...")

    if "--preview" in sys.argv:
        out = OUTPUT_DIR / "_preview" / "we_dont_back_down"
        _render_beat_stills(
            beats=BEATS, out_dir=out,
            chrome_for=_chrome_for_preview, spec_well=_spec_well_for_preview,
            W=W, H=H, rotation_cache_dir=_ROT_CACHE_DIR,
        )
        return

    _preflight(BEATS, DURATION, rotation_cache_dir=_ROT_CACHE_DIR,
               reel_slug="we_dont_back_down")

    print("\n[pre-warm] generating any missing TTS...")
    synthesize_narration(load_env())

    clips = []
    for idx, (slug, dur, chord, chip_label, spec) in enumerate(BEATS):
        is_first = idx == 0
        is_last = idx == len(BEATS) - 1
        is_cta = slug == "cta"
        fadein = 0.0 if is_first else 0.25
        fadeout = 0.4 if is_last else 0.0
        print(f"[video/{slug}] {Path(spec['path']).name} "
              f"t={spec['in_t']}..{spec['out_t']}  chip={chip_label!r}")
        clips.append(build_beat_clip(slug, chip_label, spec, dur, is_cta,
                                     fadein=fadein, fadeout=fadeout))
    video = concatenate_videoclips(clips, method="compose").set_duration(DURATION)

    print("\n[captions] building events...")
    events = build_caption_events()
    for ev in events:
        print(f"  {ev['start']:5.2f}-{ev['end']:5.2f}  {ev['text'][:80]}")
    cc = make_caption_clips(events)
    if cc:
        video = CompositeVideoClip([video, *cc], size=(W, H)).set_duration(DURATION)

    mix = build_audio()
    write_wav(mix)
    audio_clip = AudioFileClip(str(AUDIO_PATH)).set_duration(DURATION)
    video = video.set_audio(audio_clip)

    print("\n[main] rendering final video...")
    video.write_videofile(
        str(OUTPUT_PATH),
        fps=FPS,
        codec="libx264",
        preset="medium",
        bitrate="8M",
        audio_codec="aac",
        audio_bitrate="192k",
        threads=4,
    )
    print(f"\nDone. Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
