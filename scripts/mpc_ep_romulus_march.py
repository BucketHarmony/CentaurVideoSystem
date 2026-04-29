"""
MPC "We March" — 18s vertical reel built entirely around IMG_0841.MOV.

The other Romulus cuts (rapid_response, ten_weeks) intercut multiple
sources. This one stays on a single piece of footage — the column of
marchers carrying signs down Cogswell — so the visual is one continuous
breath. Chant audio carries the soundtrack; AI VO is disabled. Stencil
callouts surface the chant for muted viewers.

Beats:
  0:00-0:15   MARCH — A minor — IMG_0841 1.0-16.0
                       chant audio at full presence; soft synth bed
                       underneath. Stencil callouts every ~2s.
  0:15-0:18   CTA   — A major — last-frame freeze + gradient chrome
                       "WE MARCH FOR OUR NEIGHBORS" + URL.

IMG_0841.MOV is iPhone HDR (HLG/BT.2020); a one-time ffmpeg pass
tone-maps to SDR BT.709 (cached at output/mpc/_hdr_cache/) so MoviePy
sees a normal yuv420p file.

Output: E:/AI/CVS/ComfyUI/output/mpc/romulus_march.mp4
Run:    python E:/AI/CVS/scripts/mpc_ep_romulus_march.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

from cvs_lib import audio as cvs_audio
from cvs_lib.mpc_chrome import ChromeRenderer, Layout, load_palette
from cvs_lib.moviepy_helpers import build_beat_clip as _lib_build_beat_clip
from cvs_lib.moviepy_helpers import spec_well as _lib_spec_well

# --------------------------------------------------------------------------- #
# Paths + brand
# --------------------------------------------------------------------------- #

FPS = 30
DURATION = 18.0
MARCH_DUR = 15.0
CTA_DUR = DURATION - MARCH_DUR  # 3.0s

LAYOUT = Layout(
    BANNER_H=140, WELL_TOP=140, WELL_H=1750 - 140,
    CAPTION_BOTTOM=1620, CHIP_Y=168,
    CTA_CHROME_BOTTOM=720, CTA_WELL_TOP=720,
)
W, H = LAYOUT.W, LAYOUT.H

ROOT = Path("E:/AI/CVS/mpc")
BRAND = ROOT / "brand"
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "romulus_march.mp4"
AUDIO_PATH = OUTPUT_DIR / "romulus_march_audio.wav"
HDR_CACHE = OUTPUT_DIR / "_hdr_cache"
HDR_CACHE.mkdir(parents=True, exist_ok=True)
_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"

RAW_DIR = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus")
SOURCE_HDR = RAW_DIR / "IMG_0841.MOV"

PALETTE = load_palette(BRAND / "palette.json")
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]

CHROME = ChromeRenderer(
    palette=PALETTE,
    font_headline=FONT_HEADLINE,
    font_body=PALETTE["fonts"]["body"]["path"],
    logo_path=LOGO_PATH,
    layout=LAYOUT,
)

CTA_RALLY = "ice_out_romulus"
_CTA_CFG = json.loads((ROOT / "cta.json").read_text(encoding="utf-8"))
_CTA_DEFAULTS = _CTA_CFG.get("defaults", {})
_CTA_RALLY_CFG = _CTA_CFG["rallies"][CTA_RALLY]
CTA_URL = _CTA_RALLY_CFG.get("url", _CTA_DEFAULTS.get("url", ""))
CTA_HANDLE_LINE = _CTA_RALLY_CFG.get(
    "handle_line", _CTA_DEFAULTS.get("handle_line", ""))
CTA_HEADLINE = "WE MARCH"
CTA_SUBHEAD = "FOR OUR NEIGHBORS"

# --------------------------------------------------------------------------- #
# HDR → SDR bake (one-time, cached)
# --------------------------------------------------------------------------- #

def ensure_sdr_baked(src: Path, *, cache_dir: Path = HDR_CACHE) -> Path:
    """iPhone HDR (HLG/BT.2020) -> SDR BT.709 + color grade in a single
    ffmpeg pass. Cached by mtime + recipe hash.

    Grade matches mpc_ep_romulus.py (curves+sat+warm-highlight colorbalance);
    rainy-day footage was reading flat without it. Filename embeds an 8-char
    hash of the vf chain so recipe edits invalidate cache automatically.
    """
    vf = (
        "zscale=t=linear:npl=100,format=gbrpf32le,"
        "zscale=p=bt709,tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
        "curves=preset=medium_contrast,"
        "eq=saturation=1.20:gamma=0.96:contrast=1.03,"
        "colorbalance=rh=0.04:gh=0.01:bh=-0.03"
    )
    import hashlib
    key = hashlib.sha1(vf.encode("utf-8")).hexdigest()[:8]
    out = cache_dir / f"{src.stem}_sdrg{key}.mp4"
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    print(f"[hdr+grade] baking {src.name} -> {out.name}")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


# --------------------------------------------------------------------------- #
# Beats
# --------------------------------------------------------------------------- #

SOURCE_SDR = ensure_sdr_baked(SOURCE_HDR)

# Single source. The MARCH beat uses 1.0-16.0 (15s) — skips the first
# second of approach so the column is already mid-frame on entry. The
# CTA beat freezes on a tail moment of the same clip (15.0-15.1) and
# floats brand chrome on top.
BEATS = [
    ("march", MARCH_DUR, "minor", "ICE OUT ROMULUS",
     {"path": SOURCE_SDR, "in_t": 1.0, "out_t": 16.0,
      "audio_gain": 1.1,
      "crop_x_frac": 0.55,                # bias slightly right of center
                                          # — chanter is at frame center
                                          # but signs read better with a
                                          # touch of right pan
      }),
    ("cta", CTA_DUR, "resolve", None,
     {"path": SOURCE_SDR, "in_t": 15.0, "out_t": 15.0 + CTA_DUR,
      "audio_gain": 0.55,
      "well_top": LAYOUT.CTA_WELL_TOP,
      "well_h": LAYOUT.CTA_WELL_H}),
]

def _scenes_from_beats():
    out, t = [], 0.0
    for slug, dur, *_ in BEATS:
        out.append((t, t + dur, slug))
        t += dur
    return out

SCENES = _scenes_from_beats()

# --------------------------------------------------------------------------- #
# Chant callouts (stencil overlays per chant_callouts.md)
# --------------------------------------------------------------------------- #

CALLOUT_FONT = "C:/Windows/Fonts/STENCIL.TTF"
CALLOUTS = [
    # Pre-roll silence ~1.5s lets the viewer register the column before
    # the first overlay punches in. Cadence ~2.5s/phrase fits the
    # "ABOLISH ICE / RIGHT NOW" call-and-response cycle.
    {"start": 1.6,  "end": 3.4,  "text": "ABOLISH ICE"},
    {"start": 3.9,  "end": 5.6,  "text": "RIGHT NOW"},
    {"start": 6.6,  "end": 8.4,  "text": "ABOLISH ICE"},
    {"start": 8.9,  "end": 10.6, "text": "RIGHT NOW"},
    {"start": 11.6, "end": 13.4, "text": "ICE OUT ROMULUS"},
    # 13.4-15.0: footage breathes for chrome to land cleanly.
]

# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #

SR = 44100
N = int(SR * DURATION)

# A-minor stoic root + 5th + octave for the march beat; A major sus2
# on the CTA tail. Single-pad bed sits well below the chant audio.
SCENE_CHORDS = {
    "minor":   [110.00, 164.81, 220.00],
    "resolve": [110.00, 164.81, 246.94, 277.18],
}

BPM = 96.0
BEATS_PER_SCENE = int(MARCH_DUR / (60.0 / BPM))  # 24 beats over 15s @ 96 BPM


def _scene_start(slug):
    return next(s[0] for s in SCENES if s[2] == slug)


def harmonic_bed():
    """Thin single-channel chord pad. Returned as (L, R) where L == R —
    chant is the only width-bearing element on this reel."""
    bed = cvs_audio.harmonic_hum(
        SCENES, BEATS, SCENE_CHORDS,
        duration=DURATION, sr=SR,
    )
    return bed.astype(np.float32), bed.astype(np.float32)


def extract_audio_segment(path, t0, t1):
    return cvs_audio.extract_audio_segment(path, t0, t1, sr=SR)


def build_source_audio_track():
    track = np.zeros(N, dtype=np.float32)
    fade_n = int(0.05 * SR)
    for slug, _dur, _chord, _label, spec in BEATS:
        if spec is None:
            continue
        a0 = float(spec.get("audio_in", spec["in_t"]))
        a1 = float(spec.get("audio_out", spec["out_t"]))
        seg = extract_audio_segment(spec["path"], a0, a1)
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
        print(f"[audio/{slug}] +{Path(spec['path']).name} "
              f"a={a0:.2f}..{a1:.2f}s @ t={place_t:.2f}s gain={gain}")
    return track


def build_audio():
    print("[audio] thin harmonic bed (A minor -> A sus2)...")
    bed_l, bed_r = harmonic_bed()
    print("[audio] native source track (chant)...")
    source = build_source_audio_track()

    # Bed sits low; chant carries. No VO ducking needed (no VO).
    mix_l = bed_l * 0.18 + source * 1.0
    mix_r = bed_r * 0.18 + source * 1.0

    peak = max(float(np.max(np.abs(mix_l))), float(np.max(np.abs(mix_r))))
    if peak > 0:
        mix_l = mix_l / peak * 0.9
        mix_r = mix_r / peak * 0.9
    return mix_l, mix_r


def write_wav(stereo, path=AUDIO_PATH):
    L, R = stereo
    cvs_audio.write_wav_stereo(L, R, path, sr=SR)
    print(f"[audio] wrote {path}")


# --------------------------------------------------------------------------- #
# Video composition
# --------------------------------------------------------------------------- #

def _spec_well(spec):
    return _lib_spec_well(spec, default_top=LAYOUT.WELL_TOP, default_h=LAYOUT.WELL_H)


def render_beat_chrome(slug, chip_label):
    return CHROME.render_beat(
        chip_label=chip_label,
        chip_color=C["deep_magenta"],
        well_transparent=True,
    )


def render_cta_chrome():
    return CHROME.render_cta(
        headline=CTA_HEADLINE, subhead=CTA_SUBHEAD,
        url=CTA_URL, handle_line=CTA_HANDLE_LINE,
        well_transparent=True,
        gradient_angle=300.0,
        subhead_size=44,
    )


def build_beat_clip(slug, chip_label, footage_spec, duration, is_cta,
                    fadein=0.0, fadeout=0.0):
    chrome_rgba = render_cta_chrome() if is_cta else render_beat_chrome(slug, chip_label)
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


def make_callout_clips():
    from cvs_lib.captions import make_callout_clips as _lib_make_callout_clips
    return _lib_make_callout_clips(
        CALLOUTS, width=W, font_path=CALLOUT_FONT,
        y_anchor=1320,
        size=160,
        fill=(255, 255, 255, 255),
        stroke_fill=tuple(C["deep_magenta"]) + (255,),
        stroke_w=10,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print("Building MPC Romulus March (18s single-clip reel)...")

    clips = []
    for idx, (slug, dur, _chord, chip_label, spec) in enumerate(BEATS):
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

    # Callouts intentionally disabled — march footage carries the chant
    # without text overlay. CALLOUTS data kept above for reference only.

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
