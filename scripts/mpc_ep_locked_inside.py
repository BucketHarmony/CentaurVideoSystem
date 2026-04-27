"""
MPC "Locked Inside" — 12s vertical song reel (verse 2 only).

Karaoke-style overlay of the rally song's second verse:

    "This is for our neighbors who are locked inside.
     Together we'll abolish ICE."

(Verse 1 — "We're gonna love and protect our neighbors / Abolish ICE
right now" — lives in 170137 and is currently saved for a longer cut.
This reel is the answer-shaped half: the *who* and the *why*.)

Source: 20260425_170245.mp4, subclipped 7.5-19.5s.
MPC top chrome (banner + chip) over the singer; karaoke text in the
lower-third. Source vocal stands alone; no AI VO, no chord bed.

Word timings: mpc/index/clips/_song_170245_words.json
(faster-whisper word_timestamps=True, large-v3 verified).

Output: E:/AI/CVS/ComfyUI/output/mpc/locked_inside.mp4

Run:
    python E:/AI/CVS/scripts/mpc_ep_locked_inside.py
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    VideoFileClip,
)

from cvs_lib import audio as cvs_audio
from cvs_lib.captions import make_karaoke_lines
from cvs_lib.mpc_chrome import ChromeRenderer, Layout, load_palette
from cvs_lib.moviepy_helpers import make_chrome_clip, rotation_baked_path

# --------------------------------------------------------------------------- #
# Paths + brand
# --------------------------------------------------------------------------- #

W, H = 1080, 1920
FPS = 30

# Source subclip window. V2 starts at 7.64s in source; 7.5s gives a
# 0.14s lead-in of crowd ambience so the cut doesn't slam.
SUB_T0 = 7.5
SUB_T1 = 19.5
DURATION = SUB_T1 - SUB_T0  # = 12.0s

LAYOUT = Layout(
    BANNER_H=140, WELL_TOP=140, WELL_H=1750 - 140,
    CAPTION_BOTTOM=1620, CHIP_Y=168,
    CTA_CHROME_BOTTOM=720, CTA_WELL_TOP=720,
)

ROOT = Path("E:/AI/CVS/mpc")
BRAND = ROOT / "brand"
OUTPUT_DIR = Path("E:/AI/CVS/ComfyUI/output/mpc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "locked_inside.mp4"
AUDIO_PATH = OUTPUT_DIR / "locked_inside_audio.wav"
_ROT_CACHE_DIR = OUTPUT_DIR / "_rot_cache"

SOURCE = Path("E:/AI/CVS/raw/MPC/Ice Out Romulus/20260425_170245.mp4")

PALETTE = load_palette(BRAND / "palette.json")
C = {name: tuple(meta["rgb"]) for name, meta in PALETTE["colors"].items()}
LOGO_PATH = str(BRAND / "logo_wide_alpha.png")
FONT_HEADLINE = PALETTE["fonts"]["headline"]["path"]

CHROME = ChromeRenderer(
    palette=PALETTE,
    font_headline=PALETTE["fonts"]["headline"]["path"],
    font_body=PALETTE["fonts"]["body"]["path"],
    logo_path=LOGO_PATH,
    layout=LAYOUT,
)

CHIP_LABEL = "OUR NEIGHBORS"
CHIP_COLOR = C["deep_magenta"]

SR = 44100
N = int(SR * DURATION)

# --------------------------------------------------------------------------- #
# Karaoke lines (timings shifted by -SUB_T0 to clip-relative)
# --------------------------------------------------------------------------- #
#
# Verse 2 = two on-screen lines: the long "neighbors who are locked
# inside" sentence split at the breath (after "neighbors"), then the
# refrain. Final "ICE." capitalized for visual punch.

_RAW_LINES = [
    {
        "line_start": 8.18, "line_end": 9.96,
        "words": [
            {"start": 8.18, "end": 8.48, "text": "This"},
            {"start": 8.48, "end": 8.76, "text": "is"},
            {"start": 8.76, "end": 9.18, "text": "for"},
            {"start": 9.18, "end": 9.54, "text": "our"},
            {"start": 9.54, "end": 9.96, "text": "neighbors"},
        ],
    },
    {
        "line_start": 9.96, "line_end": 12.80,
        "words": [
            {"start": 9.96, "end": 10.50, "text": "who"},
            {"start": 10.50, "end": 10.74, "text": "are"},
            {"start": 10.74, "end": 11.14, "text": "locked"},
            {"start": 11.14, "end": 12.38, "text": "inside."},
        ],
    },
    {
        "line_start": 13.14, "line_end": 19.30,
        "words": [
            {"start": 13.14, "end": 13.70, "text": "Together"},
            {"start": 13.70, "end": 14.92, "text": "we'll"},
            {"start": 15.60, "end": 16.94, "text": "abolish"},
            {"start": 16.94, "end": 17.38, "text": "ICE."},
        ],
    },
]


def _shift(line, dt):
    return {
        "line_start": line["line_start"] - dt,
        "line_end":   min(DURATION, line["line_end"] - dt),
        "words": [
            {**w, "start": w["start"] - dt, "end": w["end"] - dt}
            for w in line["words"]
        ],
    }


KARAOKE_LINES = [_shift(l, SUB_T0) for l in _RAW_LINES]


# --------------------------------------------------------------------------- #
# Footage
# --------------------------------------------------------------------------- #

def build_video_clip():
    """Subclip + portrait load.

    Source has rotation=-90; `rotation_baked_path` pre-rotates via
    ffmpeg into a 1080x1920 native portrait copy. We subclip to the
    verse-2 window before resize so the loaded sample is short.
    """
    src = rotation_baked_path(SOURCE, cache_dir=_ROT_CACHE_DIR)
    clip = VideoFileClip(str(src)).subclip(SUB_T0, SUB_T1).without_audio()
    if (clip.w, clip.h) == (W, H):
        return clip
    if clip.w / clip.h >= W / H:
        scaled = clip.resize(height=H)
        return scaled.crop(x_center=scaled.w / 2, width=W, height=H)
    scaled = clip.resize(width=W)
    return scaled.crop(y_center=scaled.h / 2, width=W, height=H)


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #

def build_audio():
    """Source vocal at full presence, no bed, no AI VO."""
    print("[audio] extracting source vocal track...")
    src_path = rotation_baked_path(SOURCE, cache_dir=_ROT_CACHE_DIR)
    src = cvs_audio.extract_audio_segment(src_path, SUB_T0, SUB_T1, sr=SR)
    if src is None or len(src) == 0:
        raise RuntimeError(f"No audio extracted from {SOURCE}")
    if len(src) < N:
        src = np.pad(src, (0, N - len(src)))
    else:
        src = src[:N]

    # Long fade-in (0.45s) buries the reverb tail of the prior verse's
    # "abolish ICE." that bleeds into the first 0.14s of the subclip.
    # "This" doesn't land until clip t=0.68s, so 0.45s is fully clear by
    # the time the new verse starts. Outro fade is short — last sung
    # "ICE." ends well before the cut.
    fade_in = int(0.45 * SR)
    fade_out = int(0.10 * SR)
    src[:fade_in] *= np.linspace(0, 1, fade_in)
    src[-fade_out:] *= np.linspace(1, 0, fade_out)

    mix = src * 1.4

    peak = float(np.max(np.abs(mix)))
    if peak > 0:
        mix = mix / peak * 0.92

    return mix


def write_wav(mono):
    cvs_audio.write_wav(mono, AUDIO_PATH, sr=SR)
    print(f"[audio] wrote {AUDIO_PATH}")


# --------------------------------------------------------------------------- #
# Karaoke
# --------------------------------------------------------------------------- #

def build_karaoke_clips():
    """Lower-third stenciled lyrics."""
    return make_karaoke_lines(
        KARAOKE_LINES,
        width=W,
        font_path=FONT_HEADLINE,
        y_anchor=1500,
        size=80,
        word_spacing=18,
        fill=(255, 255, 255, 255),
        stroke_fill=tuple(C["deep_magenta"]) + (255,),
        stroke_w=6,
        fade_in=0.10,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print(f"Building MPC Locked Inside ({DURATION:.1f}s verse-2 reel)...")

    print("[video] vertical crop of source footage...")
    base = build_video_clip().set_duration(DURATION)

    print("[chrome] rendering MPC banner...")
    chrome_rgba = CHROME.render_beat(
        chip_label=CHIP_LABEL,
        chip_color=CHIP_COLOR,
        well_transparent=True,
    )
    chrome_clip = make_chrome_clip(chrome_rgba, DURATION)

    print("[karaoke] building word clips...")
    karaoke = build_karaoke_clips()
    print(f"  {len(karaoke)} word clips across {len(KARAOKE_LINES)} lines")

    video = CompositeVideoClip(
        [base, chrome_clip, *karaoke], size=(W, H),
    ).set_duration(DURATION)

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
