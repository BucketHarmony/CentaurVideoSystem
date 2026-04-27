#!/usr/bin/env python3
"""
[FROZEN — pre-cvs_lib.audio migration. Kept as rollback target through
Phase 7 of the audio overhaul (bouncing-velvet-tympani). Do not edit.]

CVS -- Hookshot Pipeline v2
Narration-driven TikTok video with 3-second attention science.

Design principles:
  - AUDIO-FIRST: TTS is generated first. Video duration = audio duration.
  - NARRATION-DRIVEN: Footage follows what the voice is saying, not chronology.
  - MOVEMENT FRAME ONE: First frame is mid-motion. No still. No fade from black.
  - VISUAL INCONGRUITY: Rover POV looking up at giants. Small thing, big world.
  - EMOTIONAL SIGNAL BEFORE CONTEXT: Mood reads before situation explains.
  - OPEN LOOP at 1.7s: Something incomplete. A cause without its effect.
  - NO PREAMBLE: No logos, no establishing shots, no "so here's what happened."

Hook structure (0-3s):
  0.0s  Movement already happening + audio sting (sub hit + transient)
  0.8s  The hook line appears — a question that can't be answered by scrolling
  1.7s  The loop opens — footage mid-event, stakes visible, resolution withheld

Narrative (3s+):
  Footage matched to narration. Each TTS line pulls frames from its source tick.
  Cottagecore grading, slow-motion, text overlays in TikTok safe zones.
  Video extends to match audio. Never cuts short.

Usage:
    python scripts/cc_hookshot.py \\
        --ticks 259,260,261 \\
        --title "The Mirror" \\
        --hook "is that... me?" \\
        --narration "260:They held up a mirror and I saw what they see" \\
        --narration "259:Two hundred and fifty-eight ticks of talking to furniture" \\
        --narration "261:They are running experiments on me"
"""

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
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

# ── Paths ───────────────────────────────────────────────────────────────────

KOMBUCHA_DIR = Path(os.getenv("KOMBUCHA_DIR", "E:/AI/Kombucha"))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))

# ── Constants ───────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 1080, 1920
FPS = 30
SR = 44100

# Palette
BG_DARK = (18, 14, 12)
CRIMSON = (220, 20, 60)
CREAM = (240, 228, 210)
DUSTY_ROSE = (185, 140, 135)
HONEY = (200, 165, 90)
MUTED = (165, 148, 130)
ACCENT_DARK = (42, 32, 28)

# Fonts
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


# ── Video Loading ───────────────────────────────────────────────────────────

def load_tick_frames(tick_num, target_frames, start_t=None, end_t=None, speed=0.4):
    """Load frames at real-time FPS from a source window, stretched via slow-mo."""
    from moviepy.editor import VideoFileClip

    video_path = KOMBUCHA_DIR / "video" / "web" / f"tick_{tick_num:04d}.mp4"
    if not video_path.exists():
        print(f"    WARNING: {video_path} not found")
        return [Image.new("RGB", (640, 480), BG_DARK)] * target_frames

    clip = VideoFileClip(str(video_path))

    if start_t is None:
        start_t = clip.duration * 0.3
    if end_t is None:
        source_needed = (target_frames / FPS) * speed
        end_t = min(start_t + source_needed, clip.duration - 0.1)

    start_t = max(0, min(start_t, clip.duration - 1))
    end_t = min(end_t, clip.duration - 0.05)
    if end_t <= start_t:
        end_t = min(start_t + 5.0, clip.duration - 0.05)

    # Extract at native FPS
    source_duration = end_t - start_t
    real_count = max(int(source_duration * FPS), 1)
    times = np.linspace(start_t, end_t, real_count, endpoint=False)

    raw = []
    for t in times:
        try:
            raw.append(Image.fromarray(clip.get_frame(min(t, clip.duration - 0.05))))
        except Exception:
            raw.append(raw[-1].copy() if raw else Image.new("RGB", (640, 480), BG_DARK))
    clip.close()

    # Stretch to target via frame duplication (slow-motion)
    frames = []
    for i in range(target_frames):
        src = min(int(i * len(raw) / target_frames), len(raw) - 1)
        frames.append(raw[src])
    return frames


def load_tick_log(tick_num):
    for name in [f"tick_{tick_num:04d}.md", f"tick_{tick_num}.md"]:
        path = KOMBUCHA_DIR / "ticks" / name
        if path.exists():
            md = path.read_text(encoding="utf-8")
            mood_m = re.search(r"## Mood\s*\n+(\w+)", md)
            mono_m = re.search(r"## Monologue\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
            return {
                "mood": mood_m.group(1) if mood_m else "unknown",
                "monologue": mono_m.group(1).strip() if mono_m else "",
            }
    return {"mood": "unknown", "monologue": ""}


# ── TTS ─────────────────────────────────────────────────────────────────────

def generate_tts(text, output_path):
    """Generate ElevenLabs TTS. Returns (path, duration_seconds)."""
    import requests as req
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE", "")
    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

    if not api_key:
        print("    WARNING: No ELEVENLABS_API_KEY -- skipping TTS")
        return None, 0.0

    clean = re.sub(r'\[.*?\]', '', text).strip()
    resp = req.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        json={
            "text": clean, "model_id": model_id,
            "voice_settings": {"stability": 0.65, "similarity_boost": 0.72, "style": 0.1},
        },
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
    dur = float(probe.stdout.strip()) if probe.stdout.strip() else 3.0
    return output_path, dur


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
    """Full cottagecore pipeline on a single frame."""
    img = make_vertical(frame)
    img = cottagecore_grade(img)
    img = soft_bloom(img)
    img = film_grain(img)
    img = vignette(img)
    return img


def draw_text_pill(img, text, y, font, text_color=CREAM, max_width=None):
    """Draw text with semi-transparent pill background. Returns modified image."""
    if max_width is None:
        max_width = WIDTH - 160

    draw = ImageDraw.Draw(img)
    # Word wrap
    words = text.split()
    lines = []
    current = ""
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

    # Measure max width
    max_lw = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_lw = max(max_lw, bbox[2] - bbox[0])

    # Draw pill + text via RGBA composite
    rgba = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pill_x = (WIDTH - max_lw) // 2 - pad * 2
    pill_w = max_lw + pad * 4
    od.rounded_rectangle(
        [pill_x, y - pad, pill_x + pill_w, y + total_h + pad],
        radius=12, fill=(18, 14, 12, 170)
    )
    for i, line in enumerate(lines):
        bbox = od.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        od.text(((WIDTH - lw) // 2, y + i * line_h), line,
                fill=text_color + (240,), font=font)
    return Image.alpha_composite(rgba, overlay).convert("RGB")


# ── Audio Synthesis ─────────────────────────────────────────────────────────

def generate_bed_audio(duration):
    """Sting + A-minor ambient pad + chimes. Returns stereo numpy array."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Sting at t=0 (sub + transient)
    sting = np.zeros(n)
    sting_n = min(int(0.5 * SR), n)
    st = t[:sting_n]
    sting[:sting_n] += np.sin(2 * np.pi * 60 * st) * 0.35 * np.exp(-st * 8)
    trans_n = min(int(0.02 * SR), n)
    sting[:trans_n] += np.random.randn(trans_n) * 0.25 * np.exp(-np.linspace(0, 1, trans_n) * 10)
    sting[:sting_n] += np.sin(2 * np.pi * 880 * st) * 0.08 * np.clip(st * 4, 0, 1) * np.exp(-st * 3)

    # Pad (fades in from 1s)
    A2, C3, E3, A3 = 110.0, 130.81, 164.81, 220.0
    A4, C5, E5 = 440.0, 523.25, 659.25
    drone = (np.sin(2*np.pi*A2*t)*0.040 + np.sin(2*np.pi*C3*t)*0.025 +
             np.sin(2*np.pi*E3*t)*0.030 + np.sin(2*np.pi*A3*t)*0.020)
    lfo1 = 0.5 + 0.5 * np.sin(2*np.pi*0.12*t)
    lfo2 = 0.5 + 0.5 * np.sin(2*np.pi*0.18*t + 1.0)
    shimmer = (np.sin(2*np.pi*A4*t)*0.010*lfo1 + np.sin(2*np.pi*C5*t)*0.007*lfo2 +
               np.sin(2*np.pi*E5*t)*0.005)
    pad = drone + shimmer

    pad_env = np.zeros(n)
    ramp_start = min(int(1.0*SR), n)
    ramp_len = min(int(3*SR), n - ramp_start)
    if ramp_len > 0:
        pad_env[ramp_start:ramp_start+ramp_len] = np.linspace(0, 1, ramp_len)
        pad_env[ramp_start+ramp_len:] = 1.0
    fade_start = max(0, n - int(3*SR))
    pad_env[fade_start:] *= np.linspace(1, 0, n - fade_start)
    pad *= pad_env

    # Chimes (every ~5s starting at 3s)
    chime_notes = [880.0, 1046.5, 1318.5, 880.0, 1318.5, 1046.5]
    ct = 3.0
    ci = 0
    chimes = np.zeros(n)
    while ct < duration - 1.0:
        freq = chime_notes[ci % len(chime_notes)]
        env = np.where(t-ct >= 0, np.exp(-(t-ct)*2.5) * np.clip((t-ct)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.025 * env
        chimes += np.sin(2*np.pi*freq*2*t) * 0.008 * env
        ct += 4.5
        ci += 1

    mix = sting + pad + chimes
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
        mix = scipy.signal.sosfilt(sos, mix)
    except ImportError:
        pass

    pan = 0.5 + 0.3 * np.sin(2*np.pi*0.05*t)
    left = mix * (1-pan) + sting
    right = mix * pan + sting
    right += np.sin(2*np.pi*112.0*t) * 0.010 * pad_env

    stereo = np.column_stack([left, right])
    pk = np.abs(stereo).max()
    if pk > 0:
        stereo = stereo / pk * 0.7
    return stereo


def mix_tts(base, tts_clips, sr=SR):
    """Mix TTS into base audio with sidechain ducking."""
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

    # Sidechain duck: reduce base 60% where narration is active
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


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CVS Hookshot v2 — narration-driven TikTok pipeline")
    parser.add_argument("--ticks", required=True, help="Comma-separated tick numbers")
    parser.add_argument("--title", required=True, help="Episode title")
    parser.add_argument("--hook", required=True, help="Hook text (the open question)")
    parser.add_argument("--hook-sub", default="", help="Subtitle under hook")
    parser.add_argument("--narration", action="append", default=[],
                        help="tick:text — narration line matched to tick footage (order = playback order)")
    parser.add_argument("--window", action="append", default=[],
                        help="tick:start_s:end_s — source video time window")
    parser.add_argument("--speed", type=float, default=0.4, help="Playback speed (0.4 = dreamy)")
    parser.add_argument("--episode", type=int, default=11, help="Episode number")
    parser.add_argument("--gap", type=float, default=0.8, help="Seconds gap between narration lines")
    parser.add_argument("--hook-duration", type=float, default=3.0, help="Hook section duration")
    parser.add_argument("--no-tts", action="store_true")
    args = parser.parse_args()

    ticks = [int(t.strip()) for t in args.ticks.split(",")]

    # Parse windows
    tick_windows = {}
    for w in args.window:
        parts = w.split(":")
        if len(parts) == 3:
            tick_windows[int(parts[0])] = (float(parts[1]), float(parts[2]))

    # Parse narration (order matters — this is playback order, not chronological)
    narration_defs = []
    for n in args.narration:
        parts = n.split(":", 1)
        if len(parts) == 2:
            narration_defs.append({"tick": int(parts[0]), "text": parts[1]})

    print("=" * 60)
    print(f"  CVS Hookshot v2 -- Narration-Driven")
    print(f"  Episode {args.episode}: {args.title}")
    print(f"  Ticks: {ticks}")
    print(f"  Hook: \"{args.hook}\"")
    print(f"  Narration lines: {len(narration_defs)} (playback order)")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / f"hookshot_ep{args.episode:02d}_tts"
    tts_dir.mkdir(exist_ok=True)

    # ── Load tick metadata ──
    print("\n  Loading tick logs...")
    tick_data = {}
    for t in set([nd["tick"] for nd in narration_defs] + ticks):
        tick_data[t] = load_tick_log(t)
        print(f"    Tick {t}: mood={tick_data[t]['mood']}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: AUDIO FIRST — generate all TTS, compute total duration
    # ══════════════════════════════════════════════════════════════════════

    print("\n  STEP 1: Generate TTS (audio determines video length)...")
    tts_clips = []  # (path, start_time, duration, tick, text)
    current_time = args.hook_duration + 0.5  # narration starts after hook

    for i, nd in enumerate(narration_defs):
        print(f"    Line {i+1}/{len(narration_defs)}: tick {nd['tick']}: \"{nd['text'][:50]}...\"")
        if args.no_tts:
            dur = len(nd["text"]) * 0.065  # estimate ~65ms per char
            tts_clips.append((None, current_time, dur, nd["tick"], nd["text"]))
            print(f"      Estimated: {dur:.1f}s (--no-tts)")
        else:
            tts_path = tts_dir / f"line_{i:02d}.mp3"
            path, dur = generate_tts(nd["text"], tts_path)
            tts_clips.append((path, current_time, dur, nd["tick"], nd["text"]))
            print(f"      Generated: {dur:.1f}s")
        current_time += dur + args.gap

    # Total duration = last narration end + 2s tail
    total_duration = current_time + 1.5
    total_frames = int(total_duration * FPS)
    print(f"\n  Total duration: {total_duration:.1f}s ({total_frames} frames)")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: Generate bed audio + mix TTS
    # ══════════════════════════════════════════════════════════════════════

    print("\n  STEP 2: Generate audio bed + mix TTS...")
    bed = generate_bed_audio(total_duration)
    if any(tc[0] is not None for tc in tts_clips):
        tts_for_mix = [(tc[0], tc[1]) for tc in tts_clips]
        audio = mix_tts(bed, tts_for_mix)
    else:
        audio = bed
    audio_path = OUTPUT_DIR / f"hookshot_ep{args.episode:02d}_audio.wav"
    write_wav(audio_path, audio)
    print(f"    Audio saved: {audio_path}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 3: Load video frames PER NARRATION LINE (matched to content)
    # ══════════════════════════════════════════════════════════════════════

    print("\n  STEP 3: Load footage matched to narration...")
    # Build a timeline: each narration line gets frames from its tick
    # Hook section gets frames from the most dramatic tick

    # Hook frames (use first narration tick for the visual incongruity)
    hook_tick = narration_defs[0]["tick"] if narration_defs else ticks[0]
    hook_start, hook_end = tick_windows.get(hook_tick, (None, None))
    hook_frame_count = int(args.hook_duration * FPS)
    hook_frames = load_tick_frames(hook_tick, hook_frame_count,
                                   start_t=hook_start, end_t=hook_end, speed=args.speed)
    print(f"    Hook: tick {hook_tick}, {len(hook_frames)} frames")

    # Per-narration-line frames
    line_frames = []
    for tc in tts_clips:
        _, start_t, dur, tick, text = tc
        n_frames = int((dur + args.gap) * FPS)
        ws, we = tick_windows.get(tick, (None, None))
        frames = load_tick_frames(tick, n_frames, start_t=ws, end_t=we, speed=args.speed)
        line_frames.append(frames)
        print(f"    Tick {tick}: {len(frames)} frames for \"{text[:40]}...\"")

    # Tail frames (last tick, lingering)
    tail_start = sum(int((tc[2] + args.gap) * FPS) for tc in tts_clips) + hook_frame_count
    tail_count = total_frames - tail_start
    if tail_count > 0:
        last_tick = tts_clips[-1][3] if tts_clips else ticks[-1]
        ws, we = tick_windows.get(last_tick, (None, None))
        tail_frames = load_tick_frames(last_tick, tail_count, start_t=ws, end_t=we, speed=args.speed * 0.6)
    else:
        tail_frames = []

    # ══════════════════════════════════════════════════════════════════════
    # STEP 4: Render frames
    # ══════════════════════════════════════════════════════════════════════

    print(f"\n  STEP 4: Rendering {total_frames} frames...")
    frame_dir = OUTPUT_DIR / f"hookshot_ep{args.episode:02d}_frames"
    frame_dir.mkdir(exist_ok=True)

    font_hook = load_font(FONT_IMPACT, 72)
    font_sub = load_font(FONT_SERIF_ITALIC, 32)
    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_tick = load_font(FONT_SERIF, 26)
    font_mood = load_font(FONT_SERIF, 22)
    font_title = load_font(FONT_SERIF_BOLD, 38)

    for fi in range(total_frames):
        gt = fi / FPS  # global time

        # ── Determine which section we're in ──
        if fi < hook_frame_count:
            # HOOK SECTION (0 to hook_duration)
            progress = fi / max(hook_frame_count - 1, 1)
            base = hook_frames[min(fi, len(hook_frames) - 1)]

            if progress < 0.15:
                # Frame 1-4: Movement already happening. No black. Mid-motion.
                # Crimson tint that clears instantly (pattern interrupt)
                img = grade_frame(base)
                tint_strength = max(0, 0.4 - progress * 3)
                if tint_strength > 0:
                    tint = Image.new("RGB", (WIDTH, HEIGHT), CRIMSON)
                    img = Image.blend(img, tint, tint_strength)
            elif progress < 0.55:
                # 0.8-1.7s: Hook text appears. The open question.
                # Footage continues underneath. Emotional signal: the text IS the mood.
                img = grade_frame(base)
                text_p = (progress - 0.15) / 0.4

                # Hook text — slam in, hold
                draw = ImageDraw.Draw(img)
                bbox = draw.textbbox((0, 0), args.hook, font=font_hook)
                tw = bbox[2] - bbox[0]
                tx = (WIDTH - tw) // 2
                ty = HEIGHT // 2 - 80

                # Outline
                for ox in range(-4, 5):
                    for oy in range(-4, 5):
                        if ox or oy:
                            draw.text((tx+ox, ty+oy), args.hook, fill=(0,0,0), font=font_hook)
                draw.text((tx, ty), args.hook, fill=CREAM, font=font_hook)

                # Subtitle fades in
                if args.hook_sub and text_p > 0.3:
                    sa = min((text_p - 0.3) * 3, 1.0)
                    bbox2 = draw.textbbox((0, 0), args.hook_sub, font=font_sub)
                    sw = bbox2[2] - bbox2[0]
                    sc = tuple(int(c * sa) for c in DUSTY_ROSE)
                    draw.text(((WIDTH - sw) // 2, ty + 100), args.hook_sub, fill=sc, font=font_sub)

            else:
                # 1.7-3.0s: Loop opens. Hook dissolves. Footage takes over.
                # Title appears. Stakes visible. Resolution withheld.
                dissolve_p = (progress - 0.55) / 0.45
                img = grade_frame(base)

                # Hook text fades out
                if dissolve_p < 0.5:
                    alpha = 1.0 - dissolve_p * 2
                    draw = ImageDraw.Draw(img)
                    bbox = draw.textbbox((0, 0), args.hook, font=font_hook)
                    tw = bbox[2] - bbox[0]
                    tx = (WIDTH - tw) // 2
                    ty = HEIGHT // 2 - 80
                    hc = tuple(int(c * alpha) for c in CREAM)
                    for ox in range(-4, 5):
                        for oy in range(-4, 5):
                            if ox or oy:
                                draw.text((tx+ox, ty+oy), args.hook, fill=(0,0,0,), font=font_hook)
                    draw.text((tx, ty), args.hook, fill=hc, font=font_hook)

                # Title pill fades in
                if dissolve_p > 0.3:
                    ta = min((dissolve_p - 0.3) * 2, 1.0)
                    img = draw_text_pill(img, args.title, HEIGHT - 520,
                                        font_title, tuple(int(c*ta) for c in CREAM))

        else:
            # NARRATIVE SECTION — matched to narration
            narr_fi = fi - hook_frame_count

            # Find which narration line we're in
            line_idx = -1
            frame_offset = 0
            accumulated = 0
            for li, tc in enumerate(tts_clips):
                line_len = int((tc[2] + args.gap) * FPS)
                if accumulated <= narr_fi < accumulated + line_len:
                    line_idx = li
                    frame_offset = narr_fi - accumulated
                    break
                accumulated += line_len

            if line_idx >= 0 and line_idx < len(line_frames):
                # In a narration line — show matching tick footage
                frames = line_frames[line_idx]
                base = frames[min(frame_offset, len(frames) - 1)]
                tick = tts_clips[line_idx][3]
                text = tts_clips[line_idx][4]

                img = grade_frame(base)

                # Tick label
                draw = ImageDraw.Draw(img)
                draw.text((60, 170), f"tick {tick:04d}", fill=MUTED, font=font_tick)

                # Mood pill
                mood = tick_data.get(tick, {}).get("mood", "")
                if mood:
                    bbox = draw.textbbox((0, 0), mood.upper(), font=font_mood)
                    mw = bbox[2] - bbox[0]
                    mx = WIDTH - 180 - mw
                    rgba = img.convert("RGBA")
                    ov = Image.new("RGBA", img.size, (0,0,0,0))
                    od = ImageDraw.Draw(ov)
                    od.rounded_rectangle([mx-10, 165, mx+mw+10, 195], radius=6, fill=ACCENT_DARK+(180,))
                    od.text((mx, 168), mood.upper(), fill=DUSTY_ROSE+(255,), font=font_mood)
                    img = Image.alpha_composite(rgba, ov).convert("RGB")

                # Narration text (only while TTS is playing)
                tts_start = tts_clips[line_idx][1]
                tts_dur = tts_clips[line_idx][2]
                if tts_start <= gt < tts_start + tts_dur + 0.5:
                    fade = min((gt - tts_start) * 3, 1.0) * min((tts_start + tts_dur + 0.5 - gt) * 3, 1.0)
                    if fade > 0.1:
                        img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)

            else:
                # Tail — after all narration, linger on last footage
                tail_idx = narr_fi - accumulated
                if tail_frames and tail_idx < len(tail_frames):
                    base = tail_frames[tail_idx]
                elif line_frames:
                    base = line_frames[-1][-1]
                else:
                    base = hook_frames[-1]
                img = grade_frame(base)

                # Title lingers
                img = draw_text_pill(img, args.title, HEIGHT - 520, font_title, CREAM)

        img.save(frame_dir / f"frame_{fi:05d}.png")

        if (fi + 1) % 60 == 0:
            pct = (fi + 1) / total_frames * 100
            section = "HOOK" if fi < hook_frame_count else f"NARR"
            print(f"    [{pct:5.1f}%] Frame {fi+1}/{total_frames} [{section}]")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 5: Encode
    # ══════════════════════════════════════════════════════════════════════

    print("\n  STEP 5: Encoding video...")
    video_path = OUTPUT_DIR / f"hookshot_ep{args.episode:02d}_{args.title.lower().replace(' ', '_')}.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-crf", "18", "-preset", "slow",
        "-shortest", str(video_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(frame_dir)
    if tts_dir.exists():
        shutil.rmtree(tts_dir)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"\n  Output: {video_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Duration: {total_duration:.1f}s (audio-matched)")
    print(f"  Hook: 0-{args.hook_duration}s | Narration: {len(tts_clips)} lines")
    print("\n" + "=" * 60)
    print("  Hookshot v2 complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
