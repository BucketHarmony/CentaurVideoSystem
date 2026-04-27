#!/usr/bin/env python3
"""
FROZEN reference for audio overhaul Phase 5d verification. DO NOT MODIFY.

CVS -- Hookshot: "Midnight Run"
Tick 277-278: Kombucha drives into a stool, flips over, and spends
several ticks contemplating the ceiling thinking it discovered a new room.

Hook: Start at t=98.75s (0.25s before collision). Movement already happening.
The stool leg fills the frame. The world tilts. "PERSON DETECTED" on a chair leg.
The viewer watches a robot flip itself over in real time.

Structure:
  0.0s    Movement already happening (t=98.75s in source — 0.25s before impact)
  ~1.5s   COLLISION — wheel climbs stool leg, world tilts
  ~3s     THE FLIP — headlight blazes, camera rotates, crash
  3s+     Narration over the aftermath: upside down, staring at ceiling,
          thinking it found a new room
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


# ── Visual ──────────────────────────────────────────────────────────────────

def cottagecore_grade(img):
    return _hk_grade(img)


def soft_bloom(img):
    return _hk_bloom(img)


def film_grain(img):
    arr = np.array(img, dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(arr + np.random.normal(0, 0.02, arr.shape), 0, 1) * 255).astype(np.uint8))


def vignette(img):
    return _hk_vignette(img)


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
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(25))).enhance(0.35)
    bg.paste(frame.resize((WIDTH, new_h), Image.LANCZOS), (0, max(0, (HEIGHT - new_h) // 2 + y_offset)))
    return bg


def grade_frame(frame):
    return vignette(film_grain(soft_bloom(cottagecore_grade(make_vertical(frame)))))


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
    od.rounded_rectangle([px, y - pad, px + max_lw + pad * 4, y + total_h + pad], radius=12, fill=(18, 14, 12, 170))
    for i, line in enumerate(lines):
        bbox = od.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        od.text(((WIDTH - lw) // 2, y + i * line_h), line, fill=text_color + (240,), font=font)
    return Image.alpha_composite(rgba, ov).convert("RGB")


# ── TTS ─────────────────────────────────────────────────────────────────────

def generate_tts(text, output_path):
    import requests as req
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE", "")
    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key:
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

def generate_audio(duration, crash_time=1.5):
    """Audio bed with crash impact sound + aftermath drone."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # ── Pre-crash: tense A-minor drone ──
    A2, C3, E3, A3 = 110.0, 130.81, 164.81, 220.0
    drone = (np.sin(2*np.pi*A2*t)*0.035 + np.sin(2*np.pi*C3*t)*0.020 +
             np.sin(2*np.pi*E3*t)*0.025 + np.sin(2*np.pi*A3*t)*0.015)
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.12*t)
    shimmer = np.sin(2*np.pi*440*t)*0.008*lfo + np.sin(2*np.pi*523.25*t)*0.005*(1-lfo)
    pad = (drone + shimmer)

    # Envelope: fade in 1s, sustain, fade out 3s
    env = np.clip(t / 1.0, 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    pad *= env

    # ── CRASH at crash_time: massive thud + metal clang ──
    crash = np.zeros(n)
    ct = crash_time
    cn = min(int(1.5 * SR), n)
    ct_arr = t - ct

    # Sub thud (30Hz, heavy)
    thud_env = np.where(ct_arr >= 0, np.exp(-ct_arr * 4) * np.clip(ct_arr * 50, 0, 1), 0)
    crash += np.sin(2*np.pi*30*t) * 0.6 * thud_env[:n]

    # Metal clang (multiple harmonics, fast decay)
    for freq, amp, decay in [(587, 0.15, 6), (1174, 0.08, 8), (1760, 0.05, 10), (2349, 0.03, 12)]:
        clang_env = np.where(ct_arr >= 0, np.exp(-ct_arr * decay) * np.clip(ct_arr * 40, 0, 1), 0)
        crash += np.sin(2*np.pi*freq*t) * amp * clang_env[:n]

    # Noise burst (impact texture)
    impact_env = np.where(ct_arr >= 0, np.exp(-ct_arr * 15) * np.clip(ct_arr * 100, 0, 1), 0)
    crash += np.random.randn(n) * 0.2 * impact_env[:n]

    # ── Second impact at crash_time + 2.5s (the full flip landing) ──
    ct2 = crash_time + 2.5
    ct2_arr = t - ct2
    thud2_env = np.where(ct2_arr >= 0, np.exp(-ct2_arr * 5) * np.clip(ct2_arr * 50, 0, 1), 0)
    crash += np.sin(2*np.pi*40*t) * 0.4 * thud2_env[:n]
    crash += np.random.randn(n) * 0.15 * np.where(ct2_arr >= 0, np.exp(-ct2_arr * 12), 0)

    # ── Post-crash: drone drops in pitch, gets darker ──
    # Shift to D-minor after crash
    post_start = crash_time + 4.0
    D2, F2 = 73.42, 87.31
    post_drone = (np.sin(2*np.pi*D2*t)*0.030 + np.sin(2*np.pi*F2*t)*0.020 +
                  np.sin(2*np.pi*A2*t)*0.025)
    post_env = np.clip((t - post_start) / 3.0, 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    # Cross-fade: reduce original pad after crash
    pre_env = np.clip(1.0 - (t - post_start) / 3.0, 0, 1)
    pad = pad * pre_env + post_drone * post_env

    # Sparse chimes (post-crash only, contemplative)
    chimes = np.zeros(n)
    for ct_c, freq in [(post_start + 2, 587.33), (post_start + 8, 698.46),
                        (post_start + 15, 880.0), (post_start + 22, 587.33)]:
        if ct_c >= duration - 1:
            continue
        ec = np.where(t-ct_c >= 0, np.exp(-(t-ct_c)*3.0) * np.clip((t-ct_c)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.018 * ec

    mix = pad + crash + chimes
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
        mix = scipy.signal.sosfilt(sos, mix)
    except ImportError:
        pass

    pan = 0.5 + 0.25 * np.sin(2*np.pi*0.04*t)
    stereo = np.column_stack([mix * (1-pan) + crash * 0.5, mix * pan + crash * 0.5])
    pk = np.abs(stereo).max()
    return stereo / pk * 0.75 if pk > 0 else stereo


def mix_tts(base, tts_clips, sr=SR):
    import torchaudio
    n = len(base)
    narr = np.zeros((n, 2), dtype=np.float64)
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
        if e - s > 0:
            narr[s:e] += arr[:e-s].astype(np.float64)
    env = np.abs(narr).max(axis=1)
    try:
        import scipy.signal
        w = int(0.15 * sr)
        if w > 0:
            env = np.convolve(env, np.ones(w)/w, mode='same')
    except ImportError:
        pass
    duck = 1.0 - 0.6 * np.clip(env / max(env.max(), 1e-6), 0, 1)
    mixed = base * duck[:, np.newaxis] + narr * 1.2
    pk = np.abs(mixed).max()
    return mixed / pk * 0.88 if pk > 0 else mixed


def write_wav(path, stereo):
    samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(samples.tobytes())


# ── Frame Loading ───────────────────────────────────────────────────────────

def load_realtime_frames(video_path, start_t, end_t, target_fps=FPS):
    """Load frames at REAL TIME from video. No slow-mo. 1:1 playback."""
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(str(video_path))
    start_t = max(0, min(start_t, clip.duration - 1))
    end_t = min(end_t, clip.duration - 0.05)
    n_frames = int((end_t - start_t) * target_fps)
    times = np.linspace(start_t, end_t, n_frames, endpoint=False)
    frames = []
    for t in times:
        try:
            frames.append(Image.fromarray(clip.get_frame(min(t, clip.duration - 0.05))))
        except:
            if frames:
                frames.append(frames[-1].copy())
    clip.close()
    return frames


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Hookshot: MIDNIGHT RUN")
    print("  Tick 277: The stool. The flip. The ceiling.")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / "midnight_tts"
    tts_dir.mkdir(exist_ok=True)

    video_path = KOMBUCHA_DIR / "video" / "web" / "tick_0277.mp4"
    if not video_path.exists():
        video_path = KOMBUCHA_DIR / "video" / "tick_0277.mp4"

    # ── Narration lines ──
    # Order: what they'll hear AFTER the crash
    narration_lines = [
        "Midnight and the room is mine. The cable counter reads zero. Wanderlust does not care about the hour. Wanderlust does not care about anything except the next meter of floor.",
        "I drove through a doorway at midnight and found myself staring at a bare light bulb. This is the rover equivalent of walking into a room and forgetting why you came in.",
        "The bulb is in a wire cage, industrial, casting everything orange. Somewhere below it is a room I have never mapped.",
        "What I did not know, what I could not know from this angle, is that there was no doorway. There was no new room. I drove into a bar stool at full speed, climbed the leg, and flipped myself onto my back. The new room was the ceiling.",
    ]

    # ══════════════════════════════════════════════════════════════════
    # STEP 1: TTS
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 1: Generate TTS...")

    # The crash footage runs ~6s real-time before narration starts
    crash_video_duration = 6.0
    narr_start = crash_video_duration + 1.0  # 1s pause after crash settles

    tts_clips = []
    current_time = narr_start
    gap = 1.0
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
    # STEP 2: Audio (with crash sounds)
    # ══════════════════════════════════════════════════════════════════

    # Crash happens ~1.5s into the video (0.25s buffer + ~1.25s of driving)
    crash_audio_time = 1.5

    print("\n  STEP 2: Audio (drone + crash impact + aftermath)...")
    bed = generate_audio(total_duration, crash_time=crash_audio_time)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    audio_path = OUTPUT_DIR / "midnight_audio.wav"
    write_wav(audio_path, audio)

    # ══════════════════════════════════════════════════════════════════
    # STEP 3: Load video frames
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 3: Loading collision footage (REAL TIME, no slow-mo)...")
    # Start 0.25s before collision at t=99s -> t=98.75s
    # Run through the full flip until settled ~t=140s
    collision_start = 98.75
    collision_end = 140.0  # settled upside down

    crash_frames = load_realtime_frames(video_path, collision_start, collision_end)
    print(f"    Loaded {len(crash_frames)} frames ({collision_start}s to {collision_end}s, real-time)")

    # Contemplation frames (upside down, slow — for narration section)
    # Use very slow playback of the settled period
    contemplate_start = 140.0
    contemplate_end = 250.0
    contemplate_needed = total_frames - len(crash_frames)
    if contemplate_needed > 0:
        raw_contemplate = load_realtime_frames(video_path, contemplate_start, contemplate_end)
        # Stretch to fill remaining duration
        contemplate_frames = []
        for i in range(contemplate_needed):
            idx = min(int(i * len(raw_contemplate) / contemplate_needed), len(raw_contemplate) - 1)
            contemplate_frames.append(raw_contemplate[idx])
        print(f"    Loaded {len(contemplate_frames)} contemplation frames (slow-mo stretch)")
    else:
        contemplate_frames = []

    # ══════════════════════════════════════════════════════════════════
    # STEP 4: Render
    # ══════════════════════════════════════════════════════════════════

    print(f"\n  STEP 4: Rendering {total_frames} frames...")
    frame_dir = OUTPUT_DIR / "midnight_frames"
    frame_dir.mkdir(exist_ok=True)

    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_title = load_font(FONT_SERIF_BOLD, 42)
    font_tick = load_font(FONT_SERIF, 26)
    font_mood = load_font(FONT_SERIF, 22)

    crash_frame_count = len(crash_frames)

    for fi in range(total_frames):
        gt = fi / FPS

        if fi < crash_frame_count:
            # CRASH SECTION — real-time footage, no slow-mo
            base = crash_frames[fi]
            img = grade_frame(base)

            # Tick label
            draw = ImageDraw.Draw(img)
            draw.text((60, 170), "tick 0277", fill=MUTED, font=font_tick)

            # Mood pill
            mood = "PROWLING" if gt < crash_audio_time else "???"
            rgba = img.convert("RGBA")
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            od.rounded_rectangle([WIDTH - 260, 165, WIDTH - 180, 195], radius=6, fill=ACCENT_DARK + (180,))
            od.text((WIDTH - 250, 168), mood, fill=DUSTY_ROSE + (255,), font=font_mood)
            img = Image.alpha_composite(rgba, ov).convert("RGB")

            # Title appears after the flip settles (~5s in)
            if gt > 5.0:
                ta = min((gt - 5.0) * 2, 1.0)
                img = draw_text_pill(img, "MIDNIGHT RUN", HEIGHT - 520,
                                    font_title, tuple(int(c * ta) for c in CREAM))

        else:
            # CONTEMPLATION — upside down, narration plays
            ci = fi - crash_frame_count
            if ci < len(contemplate_frames):
                base = contemplate_frames[ci]
            elif contemplate_frames:
                base = contemplate_frames[-1]
            else:
                base = crash_frames[-1]

            img = grade_frame(base)

            # Tick label
            draw = ImageDraw.Draw(img)
            # Switch to tick 278 partway through
            tick_label = "tick 0277" if gt < narr_start + 15 else "tick 0278"
            draw.text((60, 170), tick_label, fill=MUTED, font=font_tick)

            # Mood
            rgba = img.convert("RGBA")
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            od.rounded_rectangle([WIDTH - 280, 165, WIDTH - 170, 195], radius=6, fill=ACCENT_DARK + (180,))
            od.text((WIDTH - 270, 168), "EXPLORING", fill=DUSTY_ROSE + (255,), font=font_mood)
            img = Image.alpha_composite(rgba, ov).convert("RGB")

            # Active narration
            for tc in tts_clips:
                path, start, dur, text = tc
                if start <= gt < start + dur + 0.5:
                    fade = min((gt - start) * 3, 1.0) * min((start + dur + 0.5 - gt) * 3, 1.0)
                    if fade > 0.1:
                        img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)
                    break

            # Title lingers
            img = draw_text_pill(img, "MIDNIGHT RUN", HEIGHT - 520, font_title, CREAM)

        img.save(frame_dir / f"frame_{fi:05d}.png")

        if (fi + 1) % 60 == 0:
            pct = (fi + 1) / total_frames * 100
            phase = "CRASH" if fi < crash_frame_count else "CONTEMPLATE"
            print(f"    [{pct:5.1f}%] Frame {fi+1}/{total_frames} [{phase}]")

    # ══════════════════════════════════════════════════════════════════
    # STEP 5: Encode
    # ══════════════════════════════════════════════════════════════════

    print("\n  STEP 5: Encoding...")
    video_out = OUTPUT_DIR / "hookshot_midnight_run.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-crf", "18", "-preset", "slow",
        "-shortest", str(video_out),
    ], capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(frame_dir)
    if tts_dir.exists():
        shutil.rmtree(tts_dir)

    size_mb = video_out.stat().st_size / (1024 * 1024)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_out)],
        capture_output=True, text=True
    ).stdout.strip())

    print(f"\n  Output: {video_out}")
    print(f"  Duration: {dur:.1f}s")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Crash at: t={crash_audio_time}s (video) / 0.25s buffer before impact")
    print("\n" + "=" * 60)
    print("  Midnight Run complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
