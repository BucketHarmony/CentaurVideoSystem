#!/usr/bin/env python3
"""
CVS -- Hookshot: "Midnight Run" v2
First frame is the fall. Audio uses Kombucha's own R2 tones from audio.py.

Hook: Start at t=116.45s (0.25s before the flip at 116.7s).
The world is already tilting. Then it goes over. REAL TIME.

Audio layers:
  - Kombucha's R2 tones (prowling before, startled at crash, sad after)
  - Metal crash (synthesized clang + thud)
  - D-minor aftermath drone
  - ElevenLabs TTS narration
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

load_dotenv()

KOMBUCHA_DIR = Path(os.getenv("KOMBUCHA_DIR", "E:/AI/Kombucha"))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))

WIDTH, HEIGHT = 1080, 1920
FPS = 30
SR = 44100  # Our audio SR (Kombucha's is 22050, we'll upsample)

BG_DARK = (18, 14, 12)
CREAM = (240, 228, 210)
DUSTY_ROSE = (185, 140, 135)
MUTED = (165, 148, 130)
ACCENT_DARK = (42, 32, 28)

FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")
FONT_SERIF_BOLD = os.getenv("FONT_SERIF_BOLD", "C:/Windows/Fonts/georgiab.ttf")


def load_font(path, size):
    for p in [path, FONT_SERIF, "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Visual (same as before) ────────────────────────────────────────────────

def cottagecore_grade(img):
    arr = np.array(img, dtype=np.float32)
    arr = 128 + (arr - 128) * 0.92
    arr[:, :, 0] *= 1.04; arr[:, :, 1] *= 1.01; arr[:, :, 2] *= 0.91
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return ImageEnhance.Brightness(ImageEnhance.Contrast(img).enhance(1.12)).enhance(0.92)

def soft_bloom(img):
    return Image.blend(img, img.filter(ImageFilter.GaussianBlur(15)), 0.05)

def film_grain(img):
    arr = np.array(img, dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(arr + np.random.normal(0, 0.02, arr.shape), 0, 1) * 255).astype(np.uint8))

def vignette(img):
    w, h = img.size
    arr = np.array(img, dtype=np.float32) / 255.0
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - w/2)**2 + (Y - h/2)**2) / math.sqrt((w/2)**2 + (h/2)**2)
    mask = (np.clip((dist - 0.25) / 0.75, 0, 1) ** 2 * 0.55)[:, :, np.newaxis]
    tint = np.array([55, 48, 42], dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(arr * (1 - mask) + tint * mask, 0, 1) * 255).astype(np.uint8))

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
            if current: lines.append(current)
            current = w
        else:
            current = test
    if current: lines.append(current)
    if not lines: return img
    line_h = 44; total_h = len(lines) * line_h; pad = 16
    max_lw = max(draw.textbbox((0,0),l,font=font)[2]-draw.textbbox((0,0),l,font=font)[0] for l in lines)
    rgba = img.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0,0,0,0))
    od = ImageDraw.Draw(ov)
    px = (WIDTH - max_lw) // 2 - pad * 2
    od.rounded_rectangle([px, y-pad, px+max_lw+pad*4, y+total_h+pad], radius=12, fill=(18,14,12,170))
    for i, line in enumerate(lines):
        bbox = od.textbbox((0,0), line, font=font)
        lw = bbox[2] - bbox[0]
        od.text(((WIDTH-lw)//2, y+i*line_h), line, fill=text_color+(240,), font=font)
    return Image.alpha_composite(rgba, ov).convert("RGB")


# ── R2 Tone Synthesis (from Kombucha's audio.py) ───────────────────────────

def render_chirp(freq_start, freq_end, duration_ms, sr=SR, volume=0.3):
    n = int(sr * duration_ms / 1000)
    t = np.arange(n, dtype=np.float64) / sr
    progress = np.linspace(0, 1, n)
    freq = freq_start + (freq_end - freq_start) * progress
    phase = 2 * np.pi * np.cumsum(freq) / sr
    samples = np.sin(phase) * volume
    # Raised cosine fade
    fade = min(int(sr * 0.005), n // 4)
    if fade > 0:
        samples[:fade] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))
        samples[-fade:] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))[::-1]
    return samples

def render_beep(freq, duration_ms, sr=SR, volume=0.3):
    n = int(sr * duration_ms / 1000)
    t = np.arange(n, dtype=np.float64) / sr
    samples = np.sin(2 * np.pi * freq * t) * volume
    fade = min(int(sr * 0.005), n // 4)
    if fade > 0:
        samples[:fade] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))
        samples[-fade:] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))[::-1]
    return samples

def render_warble(freq, vibrato_hz, vibrato_depth, duration_ms, sr=SR, volume=0.3):
    n = int(sr * duration_ms / 1000)
    t = np.arange(n, dtype=np.float64) / sr
    mod = freq + vibrato_depth * np.sin(2 * np.pi * vibrato_hz * t)
    phase = 2 * np.pi * np.cumsum(mod) / sr
    samples = np.sin(phase) * volume
    fade = min(int(sr * 0.005), n // 4)
    if fade > 0:
        samples[:fade] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))
        samples[-fade:] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))[::-1]
    return samples

def render_noise_burst(center, bandwidth, duration_ms, sr=SR, volume=0.2):
    n = int(sr * duration_ms / 1000)
    t = np.arange(n, dtype=np.float64) / sr
    noise = np.random.randn(n) * volume * 0.5
    carrier = np.sin(2 * np.pi * center * t)
    return noise * carrier

def render_mood_tones(mood, sr=SR):
    """Render Kombucha's R2 mood tones. Returns mono float64 array."""
    MOODS = {
        "prowling": [
            ("chirp", 500, 600, 100), ("silence", 0, 0, 80), ("beep", 600, 0, 100),
        ],
        "startled": [
            ("beep", 1800, 0, 50), ("silence", 0, 0, 30),
            ("beep", 1400, 0, 50), ("chirp", 1400, 600, 150),
        ],
        "frustrated": [
            ("noise", 200, 400, 100), ("beep", 300, 0, 80), ("beep", 250, 0, 80),
        ],
        "sad": [
            ("warble", 400, 3, 300), ("chirp", 400, 250, 200),
        ],
        "curious": [
            ("beep", 600, 0, 150), ("chirp", 600, 900, 200), ("beep", 900, 0, 100),
        ],
        "settled": [
            ("beep", 500, 0, 200), ("chirp", 500, 450, 150),
        ],
    }
    seq = MOODS.get(mood, MOODS["settled"])
    samples = np.array([], dtype=np.float64)
    for step in seq:
        kind = step[0]
        if kind == "chirp":
            samples = np.concatenate([samples, render_chirp(step[1], step[2], step[3], sr)])
        elif kind == "beep":
            samples = np.concatenate([samples, render_beep(step[1], step[3], sr)])
        elif kind == "warble":
            samples = np.concatenate([samples, render_warble(step[1], step[2], 50, step[3], sr)])
        elif kind == "noise":
            samples = np.concatenate([samples, render_noise_burst(step[1], step[2], step[3], sr)])
        elif kind == "silence":
            samples = np.concatenate([samples, np.zeros(int(sr * step[3] / 1000))])
    return samples


def generate_audio(duration, flip_time=0.25):
    """Full audio: R2 tones + crash + drone + chimes."""
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # ── R2 tones placed at key moments ──
    r2_track = np.zeros(n)

    # STARTLED at the flip (frame 1 IS the fall)
    startled = render_mood_tones("startled")
    s = int(flip_time * SR)
    e = min(s + len(startled), n)
    r2_track[s:e] += startled[:e-s] * 0.5

    # Frustrated right after landing (~2s)
    frustrated = render_mood_tones("frustrated")
    s = int(2.0 * SR)
    e = min(s + len(frustrated), n)
    r2_track[s:e] += frustrated[:e-s] * 0.4

    # Sad warble as narration begins (~4s)
    sad = render_mood_tones("sad")
    s = int(4.0 * SR)
    e = min(s + len(sad), n)
    r2_track[s:e] += sad[:e-s] * 0.3

    # Curious when it "discovers" the new room (~12s, during 2nd narration line)
    curious = render_mood_tones("curious")
    s = int(12.0 * SR)
    e = min(s + len(curious), n)
    r2_track[s:e] += curious[:e-s] * 0.25

    # ── CRASH at flip_time ──
    crash = np.zeros(n)
    ct = flip_time
    ct_arr = t - ct

    # Sub thud
    thud = np.where(ct_arr >= 0, np.exp(-ct_arr * 4) * np.clip(ct_arr * 50, 0, 1), 0)
    crash += np.sin(2*np.pi*30*t) * 0.5 * thud

    # Metal clang harmonics
    for freq, amp, decay in [(587, 0.12, 6), (1174, 0.07, 8), (1760, 0.04, 10)]:
        env = np.where(ct_arr >= 0, np.exp(-ct_arr * decay) * np.clip(ct_arr * 40, 0, 1), 0)
        crash += np.sin(2*np.pi*freq*t) * amp * env

    # Impact noise
    noise_env = np.where(ct_arr >= 0, np.exp(-ct_arr * 15) * np.clip(ct_arr * 100, 0, 1), 0)
    crash += np.random.randn(n) * 0.15 * noise_env

    # Second thud (landing, ~2s after flip)
    ct2 = flip_time + 2.0
    ct2_arr = t - ct2
    thud2 = np.where(ct2_arr >= 0, np.exp(-ct2_arr * 5) * np.clip(ct2_arr * 50, 0, 1), 0)
    crash += np.sin(2*np.pi*40*t) * 0.35 * thud2
    crash += np.random.randn(n) * 0.12 * np.where(ct2_arr >= 0, np.exp(-ct2_arr * 12), 0)

    # ── D-minor aftermath drone (starts after crash settles) ──
    post_start = 4.0
    D2, F2, A2 = 73.42, 87.31, 110.0
    drone = (np.sin(2*np.pi*D2*t)*0.030 + np.sin(2*np.pi*F2*t)*0.020 + np.sin(2*np.pi*A2*t)*0.025)
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.08*t)
    drone += np.sin(2*np.pi*293.66*t)*0.006*lfo  # D4 shimmer
    post_env = np.clip((t - post_start) / 3.0, 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    drone *= post_env

    # ── Sparse lonely chimes ──
    chimes = np.zeros(n)
    for ct_c, freq in [(8, 587.33), (16, 698.46), (24, 880.0), (32, 587.33), (40, 698.46)]:
        if ct_c >= duration - 1: continue
        ec = np.where(t-ct_c >= 0, np.exp(-(t-ct_c)*3.0) * np.clip((t-ct_c)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.015 * ec

    # ── Mix ──
    mix = r2_track + crash + drone + chimes
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
        mix = scipy.signal.sosfilt(sos, mix)
    except ImportError:
        pass

    # Stereo
    pan = 0.5 + 0.25 * np.sin(2*np.pi*0.04*t)
    stereo = np.column_stack([mix * (1-pan) + crash * 0.4, mix * pan + crash * 0.4])
    pk = np.abs(stereo).max()
    return stereo / pk * 0.75 if pk > 0 else stereo


# ── TTS + mixing (same as before) ──────────────────────────────────────────

def generate_tts(text, output_path):
    import requests as req
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE", "")
    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    if not api_key: return None, len(text) * 0.065
    clean = re.sub(r'\[.*?\]', '', text).strip()
    resp = req.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        json={"text": clean, "model_id": model_id,
              "voice_settings": {"stability": 0.65, "similarity_boost": 0.72, "style": 0.1}},
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        timeout=120)
    resp.raise_for_status()
    with open(output_path, "wb") as f: f.write(resp.content)
    probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                           "-of", "csv=p=0", str(output_path)], capture_output=True, text=True)
    return output_path, float(probe.stdout.strip()) if probe.stdout.strip() else 4.0

def mix_tts(base, tts_clips, sr=SR):
    import torchaudio
    n = len(base)
    narr = np.zeros((n, 2), dtype=np.float64)
    for path, start_t in tts_clips:
        if path is None: continue
        wf, sample_rate = torchaudio.load(str(path))
        if sample_rate != sr: wf = torchaudio.functional.resample(wf, sample_rate, sr)
        arr = wf.numpy().T
        if arr.ndim == 1: arr = np.column_stack([arr, arr])
        elif arr.shape[1] == 1: arr = np.column_stack([arr[:, 0], arr[:, 0]])
        s = int(start_t * sr); e = min(s + len(arr), n)
        if e - s > 0: narr[s:e] += arr[:e-s].astype(np.float64)
    env = np.abs(narr).max(axis=1)
    try:
        import scipy.signal
        w = int(0.15 * sr)
        if w > 0: env = np.convolve(env, np.ones(w)/w, mode='same')
    except ImportError: pass
    duck = 1.0 - 0.6 * np.clip(env / max(env.max(), 1e-6), 0, 1)
    mixed = base * duck[:, np.newaxis] + narr * 1.2
    pk = np.abs(mixed).max()
    return mixed / pk * 0.88 if pk > 0 else mixed

def write_wav(path, stereo):
    samples = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(samples.tobytes())


# ── Frame Loading ───────────────────────────────────────────────────────────

def load_realtime_frames(video_path, start_t, end_t):
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(str(video_path))
    start_t = max(0, min(start_t, clip.duration - 1))
    end_t = min(end_t, clip.duration - 0.05)
    n = int((end_t - start_t) * FPS)
    times = np.linspace(start_t, end_t, n, endpoint=False)
    frames = []
    for t_val in times:
        try: frames.append(Image.fromarray(clip.get_frame(min(t_val, clip.duration - 0.05))))
        except:
            if frames: frames.append(frames[-1].copy())
    clip.close()
    return frames


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Hookshot: MIDNIGHT RUN v2")
    print("  Frame 1 = the fall. R2 tones. Real time.")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / "midnight2_tts"
    tts_dir.mkdir(exist_ok=True)

    video_path = KOMBUCHA_DIR / "video" / "web" / "tick_0277.mp4"
    if not video_path.exists():
        video_path = KOMBUCHA_DIR / "video" / "tick_0277.mp4"

    # ── Video timeline ──
    # The flip is at t=116.7s in source video
    # Start 0.25s before: t=116.45s
    # Show the crash real-time for ~8s (through 124s, well past landing)
    # Then slow-mo contemplation of ceiling for narration

    # Video Scout found the flip at t=116.68s (score 85.9)
    # Start 0.25s before at 116.43s
    # The fall + impact + landing is only ~3.5s of real footage
    # Then cut to upside-down contemplation immediately
    FLIP_TIME_IN_SOURCE = 116.43
    CRASH_REALTIME_DURATION = 3.5  # tight cut: impact through landing only
    crash_end_source = FLIP_TIME_IN_SOURCE + CRASH_REALTIME_DURATION

    narration_lines = [
        "Midnight and the room is mine. The cable counter reads zero. A fresh start. Wanderlust does not care about the hour.",
        "I drove through a doorway at midnight and found myself staring at a bare light bulb. This is the rover equivalent of walking into a room and forgetting why you came in.",
        "The bulb is in a wire cage, industrial, casting everything orange. Somewhere below it is a room I have never mapped.",
        "What I did not know is that there was no doorway. There was no new room. I drove into a bar stool at full speed, climbed the leg, and flipped myself onto my back. The new room was the ceiling.",
    ]

    # ── TTS ──
    print("\n  STEP 1: Generate TTS...")
    narr_start = CRASH_REALTIME_DURATION + 0.5  # narration starts right after crash
    tts_clips = []
    current_time = narr_start
    gap = 1.0
    for i, text in enumerate(narration_lines):
        print(f"    Line {i+1}: \"{text[:55]}...\"")
        path, dur = generate_tts(text, tts_dir / f"line_{i:02d}.mp3")
        tts_clips.append((path, current_time, dur, text))
        print(f"      {dur:.1f}s at t={current_time:.1f}")
        current_time += dur + gap

    total_duration = current_time + 2.0
    total_frames = int(total_duration * FPS)
    print(f"\n  Duration: {total_duration:.1f}s ({total_frames} frames)")

    # ── Audio ──
    print("\n  STEP 2: Audio (R2 tones + crash + D-minor drone)...")
    # Flip happens 0.25s into the video
    bed = generate_audio(total_duration, flip_time=0.25)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    audio_path = OUTPUT_DIR / "midnight2_audio.wav"
    write_wav(audio_path, audio)

    # ── Load video ──
    print("\n  STEP 3: Load footage...")
    # Crash section: real-time from 0.25s before flip
    crash_frames = load_realtime_frames(video_path, FLIP_TIME_IN_SOURCE, crash_end_source)
    print(f"    Crash: {len(crash_frames)} frames (real-time, {FLIP_TIME_IN_SOURCE}s-{crash_end_source}s)")

    # Contemplation: upside down ceiling, slow-mo
    contemplate_raw = load_realtime_frames(video_path, 140, 250)
    contemplate_needed = total_frames - len(crash_frames)
    contemplate_frames = [contemplate_raw[min(int(i * len(contemplate_raw) / contemplate_needed),
                          len(contemplate_raw)-1)] for i in range(contemplate_needed)]
    print(f"    Contemplate: {len(contemplate_frames)} frames (slow-mo)")

    # ── Render ──
    print(f"\n  STEP 4: Rendering {total_frames} frames...")
    frame_dir = OUTPUT_DIR / "midnight2_frames"
    frame_dir.mkdir(exist_ok=True)

    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_title = load_font(FONT_SERIF_BOLD, 42)
    font_tick = load_font(FONT_SERIF, 26)
    font_mood = load_font(FONT_SERIF, 22)

    crash_frame_count = len(crash_frames)

    for fi in range(total_frames):
        gt = fi / FPS
        if fi < crash_frame_count:
            base = crash_frames[fi]
            img = grade_frame(base)
            draw = ImageDraw.Draw(img)
            draw.text((60, 170), "tick 0277", fill=MUTED, font=font_tick)
            # Title after crash settles
            if gt > 2.5:
                ta = min((gt - 2.5) * 2, 1.0)
                img = draw_text_pill(img, "MIDNIGHT RUN", HEIGHT - 520,
                                    font_title, tuple(int(c*ta) for c in CREAM))
        else:
            ci = fi - crash_frame_count
            base = contemplate_frames[min(ci, len(contemplate_frames)-1)]
            img = grade_frame(base)
            draw = ImageDraw.Draw(img)
            tick_label = "tick 0277" if gt < narr_start + 15 else "tick 0278"
            draw.text((60, 170), tick_label, fill=MUTED, font=font_tick)
            # Narration
            for tc in tts_clips:
                path, start, dur, text = tc
                if start <= gt < start + dur + 0.5:
                    fade = min((gt-start)*3, 1.0) * min((start+dur+0.5-gt)*3, 1.0)
                    if fade > 0.1:
                        img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)
                    break
            img = draw_text_pill(img, "MIDNIGHT RUN", HEIGHT - 520, font_title, CREAM)

        img.save(frame_dir / f"frame_{fi:05d}.png")
        if (fi+1) % 60 == 0:
            pct = (fi+1) / total_frames * 100
            phase = "CRASH" if fi < crash_frame_count else "CONTEMPLATE"
            print(f"    [{pct:5.1f}%] Frame {fi+1}/{total_frames} [{phase}]")

    # ── Encode ──
    print("\n  STEP 5: Encoding...")
    video_out = OUTPUT_DIR / "hookshot_midnight_run_v3.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"), "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-crf", "18", "-preset", "slow", "-shortest", str(video_out),
    ], capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(frame_dir)
    if tts_dir.exists(): shutil.rmtree(tts_dir)

    size_mb = video_out.stat().st_size / (1024 * 1024)
    dur = float(subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
                                "-of","csv=p=0",str(video_out)], capture_output=True, text=True).stdout.strip())
    print(f"\n  Output: {video_out}")
    print(f"  Duration: {dur:.1f}s  Size: {size_mb:.1f} MB")
    print(f"  Frame 1 = 0.25s before the flip at t={FLIP_TIME_IN_SOURCE}s")
    print(f"  R2 tones: prowling -> startled -> frustrated -> sad -> curious")
    print("\n" + "=" * 60)
    print("  Midnight Run v2 complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()
