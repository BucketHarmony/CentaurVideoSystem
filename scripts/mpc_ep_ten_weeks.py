"""
MPC "Ten Weeks" — 40s vertical reel, the endurance angle.

Different lever from the other reels in the suite: neither rapid response
(Romulus / We Don't Back Down) nor receipts (Follow the Money) nor
identity (Detroit Knows) nor authority (Abolish ICE Congress) nor raw
energy (People Power). This one names *why we keep showing up*: ten
weeks of organized protest as proof of staying power.

Beats (40s, four 10s scenes = 16 beats each at 96 BPM):
  0:00-0:10  HOOK     — Am — "this is our tenth week protesting"  ........
                        (154736 11.0-21.0; phrase 12.34-18.34)
  0:10-0:20  STAKES   — Dm — "Our democracy is at test right now"  ......
                        (165207 5.5-15.5; three Hassan phrases)
  0:20-0:30  ANSWER   — C  — "build power elected officials can't ignore"
                        (154736 0.5-10.5; full sentence ends 10.34)
  0:30-0:40  CTA      — A  — chrome + chant b-roll ......................
                        "Ten weeks. Still here." (no AI VO)

Audio uses `cvs_lib.audio.song_bed` (chord pad + sub + kick on downbeats),
so each scene is a complete 16-beat 4/4 phrase rather than a chord drone.

Output: E:/AI/CVS/ComfyUI/output/mpc/ten_weeks.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_ten_weeks.py
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
DURATION = 40.0
BPM = 96.0
BEATS_PER_SCENE = 16
SCENE_DUR = (60.0 / BPM) * BEATS_PER_SCENE  # = 10.0s at 96 BPM
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
OUTPUT_PATH = OUTPUT_DIR / "ten_weeks.mp4"
AUDIO_PATH = OUTPUT_DIR / "ten_weeks_audio.wav"
TTS_CACHE = OUTPUT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
TTS_PREFIX = "tnw"
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

NDCM = RAW_DIR / "20260425_154736.mp4"
HASSAN = RAW_DIR / "20260425_165207.mp4"
CHANT = RAW_DIR / "20260425_170030.mp4"

BEATS = [
    # HOOK — "tenth week" is the strongest evidence we have for staying
    # power. Transcript phrase: 12.34-18.34. Window 11.0-21.0 gives the
    # phrase 1.34s of pre-roll crowd and 2.66s of tail so the cut lands
    # inside ambient rally noise on both sides.
    ("hook", SCENE_DUR, "minor", "WEEK 10  •  STILL SHOWING UP",
     {"path": NDCM, "in_t": 11.0, "out_t": 21.0,
      "audio_gain": 1.2,
      "caption_lines": [
          (1.34, 7.34,
           "We've been out here for — this is our tenth week protesting the coup out of town."),
      ]}),
    # STAKES — three Hassan phrases. Transcript: 6.10-7.32, 8.67-10.95,
    # 11.77-14.94. Window 5.5-15.5 keeps the speech intact through
    # "Our democracy is at test right now" with 0.56s breathing tail.
    ("stakes", SCENE_DUR, "grief", "WHY WE STAY",
     {"path": HASSAN, "in_t": 5.5, "out_t": 15.5,
      "audio_gain": 1.2,
      "caption_lines": [
          (0.60, 1.82, "I'm not going to take much time."),
          (3.17, 5.45, "I am very fearful of what's going around."),
          (6.27, 9.44, "Our democracy is at test right now."),
      ]}),
    # ANSWER — full sentence: "...we have to build the power that elected
    # officials, local officials cannot ignore." Transcript 0.34-10.34.
    # Window 0.5-10.5 keeps the entire clause; only "of Romulus engaged,"
    # at the very head is trimmed (already established by HOOK chip).
    ("answer", SCENE_DUR, "build", "BUILD THE POWER",
     {"path": NDCM, "in_t": 0.5, "out_t": 10.5,
      "audio_gain": 1.2,
      "caption_lines": [
          (0.0, 9.84,
           "We have to build the power that elected officials — local officials — cannot ignore."),
      ]}),
    # CTA — brand chrome top + chant b-roll bottom. AI VO disabled; the
    # chant carries the close. Window 8.0-18.0 = 10s of "Abolish ICE!"
    # so the song bed resolves on a full measure.
    ("cta", SCENE_DUR, "resolve", "STILL HERE",
     {"path": CHANT, "in_t": 8.0, "out_t": 18.0,
      "audio_gain": 0.6,
      "well_top": CTA_WELL_TOP, "well_h": CTA_WELL_H}),
]
# Sanity: 4 × 10.0 = 40.0 ✓

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

# Voice-led chord voicings. Each chord shares ≥1 pitch with the next
# so transitions feel like one continuous breath rather than four
# separate beds. Notes:
#   minor (Am open, hook):   A2  E3  A3        — stoic root + perfect 5th
#   grief (Dm + min7, stakes): D2  A2  D3  F3   — keeps A from minor;
#                                                  F3 = minor 3rd weight
#   build (C major, answer):   C3  G3  C4  E4   — A→G drop, F→E drop
#                                                  (gentle voice leading)
#   resolve (Asus2, cta):    A2  E3  B3  C#4   — C→B half-step down,
#                                                  E→C# resolves into
#                                                  major-feel without
#                                                  fully landing
SCENE_CHORDS = {
    "minor":   [110.00, 164.81, 220.00],
    "grief":   [73.42,  110.00, 146.83, 174.61],
    "build":   [130.81, 196.00, 261.63, 329.63],
    "resolve": [110.00, 164.81, 246.94, 277.18],
}

# Sub-audible binaural-beat carrier per emotional beat. Headphones
# strongly recommended on playback — these signals only fuse into a
# perceived pulse inside the head when L/R reach the ears separately.
#   minor/hook   → 220Hz + 10Hz alpha       (focused, present-tense)
#   grief/stakes → 200Hz + 6Hz theta        (emotional access)
#   build/answer → 250Hz + 12Hz alpha-beta  (alert, ready to act)
#   resolve/cta  → 220Hz + 14Hz low beta    (settled determination)
BINAURAL_CARRIERS = {
    "minor":   (220.0, 10.0),
    "grief":   (200.0,  6.0),
    "build":   (250.0, 12.0),
    "resolve": (220.0, 14.0),
}

# AI VO disabled 2026-04-26 — chrome headline + chant carry the close, so
# no on-screen narration caption either. Kept as empty list so the captions
# module's narration_lines pathway has nothing to emit.
NARRATION_LINES = []

# Stylized callouts during the chant. Stencil font + magenta-outlined
# white fill leans into the protest-graffiti aesthetic. Three beats
# spaced across the chant cycle:
#   0.4-2.2s : ABOLISH ICE  (call)
#   2.6-4.4s : RIGHT NOW    (response)
#   4.8-6.6s : RIGHT NOW    (escalation)
# Last 3.4s of the CTA scene clears for the brand chrome to land alone.
_CTA_T0 = 30.0  # scene start (3 × 10.0s scenes before CTA)
CALLOUT_FONT = "C:/Windows/Fonts/STENCIL.TTF"
CALLOUTS = [
    {"start": _CTA_T0 + 0.4, "end": _CTA_T0 + 2.2, "text": "ABOLISH ICE"},
    {"start": _CTA_T0 + 2.6, "end": _CTA_T0 + 4.4, "text": "RIGHT NOW"},
    {"start": _CTA_T0 + 4.8, "end": _CTA_T0 + 6.6, "text": "RIGHT NOW"},
]

CTA_RALLY = "ice_out_romulus"
_CTA_CFG = json.loads((ROOT / "cta.json").read_text(encoding="utf-8"))
_CTA_DEFAULTS = _CTA_CFG.get("defaults", {})
_CTA_RALLY_CFG = _CTA_CFG["rallies"][CTA_RALLY]
CTA_URL = _CTA_RALLY_CFG.get("url", _CTA_DEFAULTS.get("url", ""))
CTA_HANDLE_LINE = _CTA_RALLY_CFG.get(
    "handle_line", _CTA_DEFAULTS.get("handle_line", ""))
CTA_HEADLINE = "STILL HERE"
CTA_SUBHEAD = "WEEK 10  •  STAND WITH US"
CTA_SUBHEAD_SIZE = 40

# --------------------------------------------------------------------------- #
# Brand chrome (delegates to cvs_lib.mpc_chrome.ChromeRenderer)
# --------------------------------------------------------------------------- #

# Endurance reel: sky on duration ("week 10" — institutional fact),
# magenta on stakes (emotional weight), sky on the strategic answer
# (forward-looking), magenta on CTA.
CHIP_COLORS = {
    "hook":   C["sky_blue"],
    "stakes": C["deep_magenta"],
    "answer": C["sky_blue"],
    "cta":    C["deep_magenta"],
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


def spatial_bed():
    """Stereo bed with binaural width + sub-audible per-scene carrier.
    Returns (L, R) float32 mono arrays at length N. Gains tuned down
    from library defaults — speech is the only foreground element; the
    bed should be "presence" not "music."
    """
    return cvs_audio.spatial_bed(
        SCENES, BEATS, SCENE_CHORDS,
        duration=DURATION, sr=SR,
        bpm=BPM, beats_per_scene=BEATS_PER_SCENE,
        pad_gain=0.16,        # was 0.30 default
        sub_gain=0.10,        # was 0.18 default
        kick_gain=0.08,       # was 0.20 default — kick was loudest
        binaural_gain=0.025,  # was 0.04 default — carrier in deep background
        binaural_carriers=BINAURAL_CARRIERS,
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
    print("[audio] spatial bed (binaural width + sub-audible carrier)...")
    bed_l, bed_r = spatial_bed()
    print("[audio] synth VO (disabled — chant carries close)...")
    voice = synthesize_narration(load_env())
    if voice is None:
        voice = np.zeros(N, dtype=np.float32)
    print("[audio] source-audio track (mono center)...")
    source = build_source_audio_track()

    source = source * vo_duck_envelope(voice, low_gain=0.45)

    speech = voice + source
    if float(np.max(np.abs(speech))) > 1e-4:
        bed_l = sidechain_duck(bed_l, speech)
        bed_r = sidechain_duck(bed_r, speech)

    # Voice + source are mono (speaker is on-camera, central). Bed is
    # stereo, kept deep underneath — speech is the only foreground.
    mix_l = bed_l * 0.35 + voice * 1.0 + source * 1.0
    mix_r = bed_r * 0.35 + voice * 1.0 + source * 1.0

    peak = max(float(np.max(np.abs(mix_l))), float(np.max(np.abs(mix_r))))
    if peak > 0:
        mix_l = mix_l / peak * 0.9
        mix_r = mix_r / peak * 0.9
    return mix_l, mix_r


def write_wav(stereo, path=AUDIO_PATH):
    """`stereo` is a (L, R) tuple of float32 mono arrays."""
    L, R = stereo
    cvs_audio.write_wav_stereo(L, R, path, sr=SR)
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


def make_callout_clips():
    from cvs_lib.captions import make_callout_clips as _lib_make_callout_clips
    return _lib_make_callout_clips(
        CALLOUTS, width=W, font_path=CALLOUT_FONT,
        y_anchor=1320,                       # over chant footage, mid-low
        size=165,                            # fits 1080w with 10px stroke
        fill=(255, 255, 255, 255),           # white fill
        stroke_fill=tuple(C["deep_magenta"]) + (255,),  # brand magenta outline
        stroke_w=10,
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
    print("Building MPC Ten Weeks (30s endurance reel)...")

    if "--preview" in sys.argv:
        out = OUTPUT_DIR / "_preview" / "ten_weeks"
        _render_beat_stills(
            beats=BEATS, out_dir=out,
            chrome_for=_chrome_for_preview, spec_well=_spec_well_for_preview,
            W=W, H=H, rotation_cache_dir=_ROT_CACHE_DIR,
        )
        return

    _preflight(BEATS, DURATION, rotation_cache_dir=_ROT_CACHE_DIR,
               reel_slug="ten_weeks")

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

    print("\n[callouts] building chant overlays...")
    co = make_callout_clips()
    for c in CALLOUTS:
        print(f"  {c['start']:5.2f}-{c['end']:5.2f}  {c['text']}")
    if co:
        video = CompositeVideoClip([video, *co], size=(W, H)).set_duration(DURATION)

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
