"""
MPC "Abolish ICE — From Congress to the Curb" — 30s vertical reel.

Power-ladder reel: a sitting member of Congress names the law (legislation
to abolish ICE), names the official to be held to account (Kristi Noem
will be prosecuted), and the crowd answers with the chant. Authority
ladder: Rep -> AG accountability -> street.

NOTE on profanity: Tlaib's HOOK contains "the f---ing ICE." Audio is
left intact (TikTok policy permits). Captions sanitize as "f---ing".

Beats (30s):
  0:00-0:09  HOOK      — Am — Tlaib: "I was the member of Congress..."  ...
                         (161357 8.57-17.57)
  0:09-0:19  ESCALATE  — Dm — Tlaib: "Kristi Noem will be prosecuted"  ...
                         (161528 13.0-23.0)
  0:19-0:24  CHANT     — A  — crowd: "Abolish ICE!"  .....................
                         (170030 0.0-5.0)
  0:24-0:30  CTA       — A  — chant b-roll + tagline + synth VO ..........
                         "Abolish ICE. Chip in. Link in bio."

Output: E:/AI/CVS/ComfyUI/output/mpc/abolish_ice_congress.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_abolish_ice_congress.py
"""

from __future__ import annotations

import json
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
OUTPUT_PATH = OUTPUT_DIR / "abolish_ice_congress.mp4"
AUDIO_PATH = OUTPUT_DIR / "abolish_ice_congress_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
TTS_PREFIX = "aic"
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
# Beats
# --------------------------------------------------------------------------- #

TLAIB_A = RAW_DIR / "20260425_161357.mp4"
TLAIB_B = RAW_DIR / "20260425_161528.mp4"
CHANT = RAW_DIR / "20260425_170030.mp4"

BEATS = [
    ("hook", 9.0, "minor", "REP. TLAIB  •  CONGRESS",
     {"path": TLAIB_A, "in_t": 8.57, "out_t": 17.57,
      "audio_gain": 1.2,
      "caption_lines": [
          (0.0, 8.5, "I was the member of Congress to bring legislation to abolish the f---ing ICE."),
      ]}),
    ("escalate", 10.0, "grief", "KRISTI NOEM  •  WILL BE PROSECUTED",
     {"path": TLAIB_B, "in_t": 13.0, "out_t": 23.0,
      "audio_gain": 1.2,
      "caption_lines": [
          (0.5, 5.0, "Kristi Noem — she is fired, but her crimes are still there."),
          (5.2, 9.5, "She will be prosecuted for her crimes. Kristi Noem will be prosecuted."),
      ]}),
    ("chant", 5.0, "resolve", "ABOLISH ICE",
     {"path": CHANT, "in_t": 0.0, "out_t": 5.0,
      "audio_gain": 1.15,
      "caption_lines": [
          (0.0, 5.0, "Abolish ICE!  Abolish ICE!"),
      ]}),
    ("cta", 6.0, "resolve", "ABOLISH ICE",
     {"path": CHANT, "in_t": 5.0, "out_t": 11.0,
      "audio_gain": 0.55,
      "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H}),
]
# Sanity: 9+10+5+6 = 30 ✓

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
    {"slug": "cta", "start_in_beat": 0.4,
     "text": "Abolish ICE. Chip in. Link in bio."},
]

CTA_RALLY = "ice_out_romulus"
_CTA_CFG = json.loads((ROOT / "cta.json").read_text(encoding="utf-8"))
_CTA_DEFAULTS = _CTA_CFG.get("defaults", {})
_CTA_RALLY_CFG = _CTA_CFG["rallies"][CTA_RALLY]
CTA_URL = _CTA_RALLY_CFG.get("url", _CTA_DEFAULTS.get("url", ""))
CTA_HANDLE_LINE = _CTA_RALLY_CFG.get(
    "handle_line", _CTA_DEFAULTS.get("handle_line", ""))
CTA_HEADLINE = "ABOLISH ICE"
CTA_SUBHEAD = "CHIP IN"
CTA_SUBHEAD_SIZE = 48

# --------------------------------------------------------------------------- #
# Brand chrome (delegates to cvs_lib.mpc_chrome.ChromeRenderer)
# --------------------------------------------------------------------------- #

# Authority-ladder reel: sky on the institutional voice (Rep, the chant
# answering), magenta on the prosecutorial pivot + CTA.
CHIP_COLORS = {
    "hook":     C["sky_blue"],
    "escalate": C["deep_magenta"],
    "chant":    C["sky_blue"],
    "cta":      C["deep_magenta"],
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
    return _lib_synthesize_narration(
        env, NARRATION_LINES,
        cache_dir=TTS_CACHE, cache_prefix=TTS_PREFIX,
        duration=DURATION, scene_start=_scene_start, sr=SR,
    )


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
# Captions (delegates to cvs_lib.captions)
# --------------------------------------------------------------------------- #

def build_caption_events():
    from cvs_lib.captions import events_from_beats
    return events_from_beats(
        BEATS,
        cta_slug="cta",
        narration_lines=NARRATION_LINES,
        measure_tts_duration=measure_tts_duration,
    )


def make_caption_clips(events):
    from cvs_lib.captions import make_caption_clips as _lib_make_caption_clips
    return _lib_make_caption_clips(
        events, width=W, caption_bottom=CAPTION_BOTTOM,
        font_path=FONT_HEADLINE,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print("Building MPC Abolish ICE Congress (30s authority reel)...")

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
