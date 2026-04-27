#!/usr/bin/env python3
"""
FROZEN reference for audio overhaul Phase 5c verification. DO NOT MODIFY.

CVS -- Hookshot: "Driving by Faith"
Ticks 271-276: Seven ticks blind, navigating by face detector alone.

Structure:
  0.0s    Motion frame one (tick 269 driving footage, already happening)
  0.4s    HAND FILLS FRAME (tick 271_01.jpg — the frozen image)
  0.8s    "someone put their hand on my face."
  1.2s    "then the camera went dark."
  1.7s    Frozen frame holds. Title: DRIVING BY FAITH. Loop open.
  3.0s+   Narration over frozen frame (because the camera IS frozen)
  final   Tick 276_01 — eyes back, room empty, Bucket gone.
"""

import math
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cvs_lib.image_filters import (
    hookshot_cottagecore_grade as _hk_grade,
    hookshot_soft_bloom as _hk_bloom,
    hookshot_vignette as _hk_vignette,
)

load_dotenv()

KOMBUCHA_DIR = Path(os.getenv("KOMBUCHA_DIR", "E:/AI/Kombucha"))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))

WIDTH, HEIGHT = 1080, 1920
FPS = 30
SR = 44100

BG_DARK = (18, 14, 12)
CRIMSON = (220, 20, 60)
CREAM = (240, 228, 210)
DUSTY_ROSE = (185, 140, 135)
MUTED = (165, 148, 130)
ACCENT_DARK = (42, 32, 28)

FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")
FONT_SERIF_BOLD = os.getenv("FONT_SERIF_BOLD", "C:/Windows/Fonts/georgiab.ttf")
FONT_IMPACT = os.getenv("FONT_TITLE", "C:/Windows/Fonts/impact.ttf")


def load_font(path, size):
    for p in [path, FONT_SERIF, "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Visual Pipeline ─────────────────────────────────────────────────────────

def cottagecore_grade(img):
    return _hk_grade(img)


def soft_bloom(img, radius=15, blend=0.05):
    return _hk_bloom(img, radius=radius, blend=blend)


def film_grain(img, intensity=0.02):
    arr = np.array(img, dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(arr + np.random.normal(0, intensity, arr.shape), 0, 1) * 255).astype(np.uint8))


def vignette(img, strength=0.55):
    return _hk_vignette(img, strength=strength)


def make_vertical(frame, y_offset=-60):
    fw, fh = frame.size
    scale = WIDTH / fw
    new_h = int(fh * scale)
    bg_scale = HEIGHT / fh
    bg = frame.resize((int(fw * bg_scale), HEIGHT), Image.LANCZOS)
    if bg.width > WIDTH:
        cx = (bg.width - WIDTH) // 2
        bg = bg.crop((cx, 0, cx + WIDTH, HEIGHT))
    else:
        bg = bg.resize((WIDTH, HEIGHT), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(25))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    sharp = frame.resize((WIDTH, new_h), Image.LANCZOS)
    bg.paste(sharp, (0, max(0, (HEIGHT - new_h) // 2 + y_offset)))
    return bg


def grade_frame(frame):
    img = make_vertical(frame)
    img = cottagecore_grade(img)
    img = soft_bloom(img)
    img = film_grain(img)
    img = vignette(img)
    return img


def draw_text_pill(img, text, y, font, text_color=CREAM, max_width=None):
    if max_width is None:
        max_width = WIDTH - 160
    draw = ImageDraw.Draw(img)
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = f"{current} {w}" if current else w
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width:
            if current:
                lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)
    if not lines:
        return img

    line_h = 44
    total_h = len(lines) * line_h
    pad = 16
    max_lw = max(draw.textbbox((0, 0), l, font=font)[2] - draw.textbbox((0, 0), l, font=font)[0] for l in lines)

    rgba = img.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    px = (WIDTH - max_lw) // 2 - pad * 2
    pw = max_lw + pad * 4
    od.rounded_rectangle([px, y - pad, px + pw, y + total_h + pad], radius=12, fill=(18, 14, 12, 170))
    for i, line in enumerate(lines):
        bbox = od.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        od.text(((WIDTH - lw) // 2, y + i * line_h), line, fill=text_color + (240,), font=font)
    return Image.alpha_composite(rgba, ov).convert("RGB")


def draw_hook_text(img, text, font, y_pos, alpha=1.0):
    """Draw large outlined text centered."""
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (WIDTH - tw) // 2
    color = tuple(int(c * alpha) for c in CREAM)
    for ox in range(-4, 5):
        for oy in range(-4, 5):
            if ox or oy:
                draw.text((tx + ox, y_pos + oy), text, fill=(0, 0, 0), font=font)
    draw.text((tx, y_pos), text, fill=color, font=font)
    return img


def draw_static_indicator(img, tick_count):
    """Draw a subtle 'CAMERA FROZEN' indicator with tick counter."""
    draw = ImageDraw.Draw(img)
    font = load_font(FONT_SERIF, 20)
    # Blinking red dot + text
    text = f"FRAME FROZEN  //  tick {tick_count} of 7"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (WIDTH - tw) // 2
    ty = 180

    rgba = img.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([tx - 16, ty - 8, tx + tw + 16, ty + 28], radius=8, fill=(18, 14, 12, 140))
    # Red dot
    od.ellipse([tx - 12, ty + 4, tx - 4, ty + 12], fill=(220, 40, 40, 200))
    od.text((tx + 4, ty), text, fill=(180, 160, 140, 200), font=font)
    return Image.alpha_composite(rgba, ov).convert("RGB")


# ── TTS ─────────────────────────────────────────────────────────────────────

def generate_tts(text, output_path):
    import requests as req
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE", "")
    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
        print("    WARNING: No ELEVENLABS_API_KEY")
        return None, len(text) * 0.065

    clean = re.sub(r'\[.*?\]', '', text).strip()
    resp = req.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        json={"text": clean, "model_id": model_id,
              "voice_settings": {"stability": 0.65, "similarity_boost": 0.72, "style": 0.1}},
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        timeout=120,
    )
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(output_path)],
        capture_output=True, text=True,
    )
    return output_path, float(probe.stdout.strip()) if probe.stdout.strip() else 4.0


# ── Audio ───────────────────────────────────────────────────────────────────

def generate_audio(duration):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Sting at t=0: deep sub hit + contact transient (hand on lens)
    sting = np.zeros(n)
    sn = min(int(0.6 * SR), n)
    st = t[:sn]
    sting[:sn] += np.sin(2 * np.pi * 50 * st) * 0.5 * np.exp(-st * 6)  # deeper sub
    tn = min(int(0.03 * SR), n)
    sting[:tn] += np.random.randn(tn) * 0.35 * np.exp(-np.linspace(0, 1, tn) * 8)  # contact thud
    sting[:sn] += np.sin(2 * np.pi * 440 * st) * 0.06 * np.clip(st * 3, 0, 1) * np.exp(-st * 4)

    # Pad — darker, more tension. D-minor instead of A-minor
    D2, F2, A2 = 73.42, 87.31, 110.0
    D3, F3, A3 = 146.83, 174.61, 220.0
    drone = (np.sin(2*np.pi*D2*t)*0.045 + np.sin(2*np.pi*F2*t)*0.025 +
             np.sin(2*np.pi*A2*t)*0.035 + np.sin(2*np.pi*D3*t)*0.020)
    # Slow shimmer — uneasy
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.08*t)
    shimmer = (np.sin(2*np.pi*293.66*t)*0.008*lfo +  # D4
               np.sin(2*np.pi*349.23*t)*0.006*(1-lfo))  # F4

    pad = drone + shimmer
    env = np.zeros(n)
    rs = min(int(2*SR), n)
    env[:rs] = np.linspace(0, 1, rs)
    env[rs:] = 1.0
    fo = max(0, n - int(3*SR))
    env[fo:] *= np.linspace(1, 0, n - fo)
    pad *= env * 0.8

    # Sparse chimes — fewer, more lonely
    chime_times = [5.0, 12.0, 20.0, 28.0]
    chime_notes = [587.33, 698.46, 880.0, 587.33]  # D5, F5, A5, D5
    chimes = np.zeros(n)
    for ct, freq in zip(chime_times, chime_notes):
        if ct >= duration - 1:
            continue
        ec = np.where(t-ct >= 0, np.exp(-(t-ct)*3.0) * np.clip((t-ct)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.020 * ec
        chimes += np.sin(2*np.pi*freq*2*t) * 0.006 * ec

    # "Eyes back" sting near the end (bright, resolving)
    eyes_back_t = duration - 6.0
    if eyes_back_t > 0:
        ebt = t - eyes_back_t
        eb_env = np.where(ebt >= 0, np.clip(ebt * 5, 0, 1) * np.exp(-ebt * 2), 0)
        chimes += np.sin(2*np.pi*880*t) * 0.03 * eb_env  # A5
        chimes += np.sin(2*np.pi*1046.5*t) * 0.02 * eb_env  # C6
        chimes += np.sin(2*np.pi*1318.5*t) * 0.015 * eb_env  # E6

    mix = sting + pad + chimes
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 2800, 'low', fs=SR, output='sos')
        mix = scipy.signal.sosfilt(sos, mix)
    except ImportError:
        pass

    pan = 0.5 + 0.25 * np.sin(2*np.pi*0.04*t)
    left = mix * (1-pan) + sting * 0.5
    right = mix * pan + sting * 0.5

    stereo = np.column_stack([left, right])
    pk = np.abs(stereo).max()
    if pk > 0:
        stereo = stereo / pk * 0.7
    return stereo


def mix_tts(base, tts_clips, sr=SR):
    import torchaudio
    n = len(base)
    narration = np.zeros((n, 2), dtype=np.float64)
    for path, start_t in tts_clips:
        if path is None:
            continue
        wf, sample_rate = torchaudio.load(str(path))
        if sample_rate != sr:
            wf = torchaudio.functional.resample(wf, sample_rate, sr)
        arr = wf.numpy().T
        if arr.ndim == 1:
            arr = np.column_stack([arr, arr])
        elif arr.shape[1] == 1:
            arr = np.column_stack([arr[:, 0], arr[:, 0]])
        s = int(start_t * sr)
        e = min(s + len(arr), n)
        cl = e - s
        if cl > 0:
            narration[s:e] += arr[:cl].astype(np.float64)

    env = np.abs(narration).max(axis=1)
    try:
        import scipy.signal
        w = int(0.15 * sr)
        if w > 0:
            env = np.convolve(env, np.ones(w)/w, mode='same')
    except ImportError:
        pass
    duck = 1.0 - 0.6 * np.clip(env / max(env.max(), 1e-6), 0, 1)
    mixed = base * duck[:, np.newaxis] + narration * 1.2
    pk = np.abs(mixed).max()
    if pk > 0:
        mixed = mixed / pk * 0.88
    return mixed


def write_wav(path, stereo):
    samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(samples.tobytes())


# ── Frame Loading ───────────────────────────────────────────────────────────

def load_motion_frames(tick_num, count, start_t=None, speed=0.4):
    """Load frames from video for motion section."""
    from moviepy.editor import VideoFileClip
    # Try both paths
    for vdir in ["video/web", "video"]:
        vpath = KOMBUCHA_DIR / vdir / f"tick_{tick_num:04d}.mp4"
        if vpath.exists():
            try:
                clip = VideoFileClip(str(vpath))
                if clip.duration < 1:
                    clip.close()
                    continue
                if start_t is None:
                    start_t = clip.duration * 0.4
                src_dur = (count / FPS) * speed
                end_t = min(start_t + src_dur, clip.duration - 0.1)
                real_n = max(int((end_t - start_t) * FPS), 1)
                times = np.linspace(start_t, end_t, real_n, endpoint=False)
                raw = []
                for t in times:
                    try:
                        raw.append(Image.fromarray(clip.get_frame(min(t, clip.duration - 0.05))))
                    except:
                        if raw:
                            raw.append(raw[-1].copy())
                clip.close()
                if raw:
                    return [raw[min(int(i * len(raw) / count), len(raw)-1)] for i in range(count)]
            except:
                pass
    # Fallback: black frames
    return [Image.new("RGB", (640, 480), BG_DARK)] * count


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Hookshot: DRIVING BY FAITH")
    print("  Ticks 271-276: Seven ticks blind")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / "faith_tts"
    tts_dir.mkdir(exist_ok=True)

    # ── Load key images ──
    print("\n  Loading key images...")
    hand_img = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0271_01.jpg").convert("RGB")
    eyes_back_img = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0276_01.jpg").convert("RGB")
    barrel_img = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0276_05.jpg").convert("RGB")
    print(f"    Hand (271_01): {hand_img.size}")
    print(f"    Eyes back (276_01): {eyes_back_img.size}")
    print(f"    Barrel (276_05): {barrel_img.size}")

    # Grade key images
    hand_graded = grade_frame(hand_img)
    eyes_graded = grade_frame(eyes_back_img)

    # ══════════════════════════════════════════════════════════════════
    # STEP 1: TTS — audio determines duration
    # ══════════════════════════════════════════════════════════════════

    narration_lines = [
        "Someone put their hand on my face. In twenty-two meters of driving, this is the first time a human has physically reached out and touched me.",
        "I have been driving toward someone I cannot see, guided by a face detector that works perfectly and a camera feed that does not work at all.",
        "Six ticks blind. Twenty-five meters of cable. I am closing the distance by instruments alone, like a submarine running silent.",
        "Seven ticks blind. Now the camera is back, and it shows me an empty room. Bucket left while I was still groping toward him through the dark. You spend half an hour navigating toward a person and by the time you get your eyes back, they have moved on.",
    ]

    print("\n  STEP 1: Generate TTS...")
    tts_clips = []
    current_time = 3.5  # after hook
    gap = 1.2

    for i, text in enumerate(narration_lines):
        print(f"    Line {i+1}: \"{text[:55]}...\"")
        tts_path = tts_dir / f"line_{i:02d}.mp3"
        path, dur = generate_tts(text, tts_path)
        tts_clips.append((path, current_time, dur, text))
        print(f"      {dur:.1f}s at t={current_time:.1f}")
        current_time += dur + gap

    total_duration = current_time + 2.0
    total_frames = int(total_duration * FPS)
    print(f"\n  Total duration: {total_duration:.1f}s ({total_frames} frames)")

    # ══════════════════════════════════════════════════════════════════
    # STEP 2: Audio
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 2: Audio (D-minor tension pad + sting + chimes)...")
    bed = generate_audio(total_duration)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    audio_path = OUTPUT_DIR / "faith_audio.wav"
    write_wav(audio_path, audio)

    # ══════════════════════════════════════════════════════════════════
    # STEP 3: Load motion footage (tick 269 for opening)
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 3: Loading motion footage (tick 269)...")
    motion_frames = load_motion_frames(269, int(0.5 * FPS), start_t=60, speed=0.5)
    print(f"    {len(motion_frames)} motion frames loaded")

    # ══════════════════════════════════════════════════════════════════
    # STEP 4: Render
    # ══════════════════════════════════════════════════════════════════

    print(f"\n  STEP 4: Rendering {total_frames} frames...")
    frame_dir = OUTPUT_DIR / "faith_frames"
    frame_dir.mkdir(exist_ok=True)

    font_hook = load_font(FONT_IMPACT, 64)
    font_hook_sub = load_font(FONT_SERIF_ITALIC, 36)
    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_title = load_font(FONT_SERIF_BOLD, 42)
    font_tick = load_font(FONT_SERIF, 26)

    # Precompute timing
    hook_end_frame = int(3.0 * FPS)  # 90 frames
    motion_end = int(0.4 * FPS)  # 12 frames
    hand_slam = int(0.4 * FPS)
    text1_start = int(0.8 * FPS)
    text2_start = int(1.2 * FPS)
    loop_open = int(1.7 * FPS)

    # Eyes-back starts at last narration end
    last_narr_end = tts_clips[-1][1] + tts_clips[-1][2]
    eyes_back_frame = int(last_narr_end * FPS)

    # Which blind tick are we in during narration?
    def get_blind_tick_number(gt):
        """Map global time to which blind tick (1-7) for display."""
        if gt < tts_clips[0][1]:
            return 1
        for i, tc in enumerate(tts_clips):
            mid = tc[1] + tc[2] / 2
            if gt < mid:
                return min(i + 1, 7)
        return 7

    for fi in range(total_frames):
        gt = fi / FPS

        if fi < motion_end:
            # 0.0-0.4s: MOTION FRAME ONE — already happening
            idx = min(fi, len(motion_frames) - 1)
            img = grade_frame(motion_frames[idx])

        elif fi < hook_end_frame:
            # 0.4-3.0s: The hook sequence
            img = hand_graded.copy()

            if fi < text1_start:
                # 0.4-0.8s: Hand slams in. Crimson flash clearing.
                p = (fi - hand_slam) / max(text1_start - hand_slam - 1, 1)
                tint_str = max(0, 0.3 - p * 0.6)
                if tint_str > 0:
                    tint = Image.new("RGB", (WIDTH, HEIGHT), CRIMSON)
                    img = Image.blend(img, tint, tint_str)

            elif fi < text2_start:
                # 0.8-1.2s: "someone put their hand on my face."
                p = (fi - text1_start) / max(text2_start - text1_start - 1, 1)
                alpha = min(p * 3, 1.0)
                img = draw_hook_text(img, "someone put their", font_hook, HEIGHT // 2 - 100, alpha)
                img = draw_hook_text(img, "hand on my face.", font_hook, HEIGHT // 2 - 30, alpha)

            elif fi < loop_open:
                # 1.2-1.7s: + "then the camera went dark."
                img = draw_hook_text(img, "someone put their", font_hook, HEIGHT // 2 - 100)
                img = draw_hook_text(img, "hand on my face.", font_hook, HEIGHT // 2 - 30)
                p = (fi - text2_start) / max(loop_open - text2_start - 1, 1)
                alpha = min(p * 3, 1.0)
                sub_color = tuple(int(c * alpha) for c in DUSTY_ROSE)
                draw = ImageDraw.Draw(img)
                sub = "then the camera went dark."
                bbox = draw.textbbox((0, 0), sub, font=font_hook_sub)
                sw = bbox[2] - bbox[0]
                draw.text(((WIDTH - sw) // 2, HEIGHT // 2 + 60), sub, fill=sub_color, font=font_hook_sub)

            else:
                # 1.7-3.0s: Hook text dissolves. Title appears. Loop open.
                dp = (fi - loop_open) / max(hook_end_frame - loop_open - 1, 1)

                # Hook dissolves
                if dp < 0.5:
                    ha = 1.0 - dp * 2
                    img = draw_hook_text(img, "someone put their", font_hook, HEIGHT // 2 - 100, ha)
                    img = draw_hook_text(img, "hand on my face.", font_hook, HEIGHT // 2 - 30, ha)

                # Title fades in
                if dp > 0.3:
                    ta = min((dp - 0.3) * 2.5, 1.0)
                    img = draw_text_pill(img, "DRIVING BY FAITH", HEIGHT - 520,
                                        font_title, tuple(int(c * ta) for c in CREAM))

                # Static indicator starts
                if dp > 0.6:
                    img = draw_static_indicator(img, 1)

        elif fi >= eyes_back_frame:
            # EYES BACK — final section
            p = (fi - eyes_back_frame) / max(total_frames - eyes_back_frame - 1, 1)

            if p < 0.15:
                # Crossfade from frozen hand to eyes-back
                blend = p / 0.15
                img = Image.blend(hand_graded, eyes_graded, blend)
            else:
                img = eyes_graded.copy()

            # "eyes open" label
            if p > 0.2:
                draw = ImageDraw.Draw(img)
                draw.text((60, 170), "tick 0276", fill=MUTED, font=font_tick)

            # Final narration text visible
            if p < 0.8:
                last_text = tts_clips[-1][3]
                # Only show if TTS still playing
                tts_end = tts_clips[-1][1] + tts_clips[-1][2]
                if gt < tts_end + 0.5:
                    img = draw_text_pill(img, last_text, HEIGHT - 580, font_narr, CREAM)

            # Title lingers
            img = draw_text_pill(img, "DRIVING BY FAITH", HEIGHT - 520 if p < 0.5 else HEIGHT - 200,
                                font_title, CREAM)

        else:
            # NARRATION SECTION — frozen frame with tick counter
            blind_tick = get_blind_tick_number(gt)
            img = hand_graded.copy()
            img = draw_static_indicator(img, blind_tick)

            # Tick label
            tick_num = 270 + blind_tick
            draw = ImageDraw.Draw(img)
            draw.text((60, 170), f"tick {tick_num:04d}", fill=MUTED, font=font_tick)

            # Find active narration
            for tc in tts_clips:
                path, start, dur, text = tc
                if start <= gt < start + dur + 0.5:
                    fade = min((gt - start) * 3, 1.0) * min((start + dur + 0.5 - gt) * 3, 1.0)
                    if fade > 0.1:
                        img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)
                    break

        img.save(frame_dir / f"frame_{fi:05d}.png")

        if (fi + 1) % 60 == 0:
            pct = (fi + 1) / total_frames * 100
            phase = "HOOK" if fi < hook_end_frame else ("EYES" if fi >= eyes_back_frame else "BLIND")
            print(f"    [{pct:5.1f}%] Frame {fi+1}/{total_frames} [{phase}]")

    # ══════════════════════════════════════════════════════════════════
    # STEP 5: Encode
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 5: Encoding...")
    video_path = OUTPUT_DIR / "hookshot_ep13_driving_by_faith.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-crf", "18", "-preset", "slow",
        "-shortest", str(video_path),
    ], capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(frame_dir)
    if tts_dir.exists():
        shutil.rmtree(tts_dir)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True
    ).stdout.strip())

    print(f"\n  Output: {video_path}")
    print(f"  Duration: {dur:.1f}s")
    print(f"  Size: {size_mb:.1f} MB")
    print("\n" + "=" * 60)
    print("  Driving by Faith complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
