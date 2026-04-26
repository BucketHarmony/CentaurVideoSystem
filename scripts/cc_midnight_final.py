#!/usr/bin/env python3
"""
CVS -- "Midnight Run" Final Cut
The Unreliable Narrator: a robot flips over and doesn't know.

Audio: Motion-reactive sound engine — frame motion intensity drives
       drone pitch, dissonance, noise, and transient triggers.
Hook:  The fall IS second one. Calm narration over upside-down footage.
       The mismatch is the open loop.
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
CREAM = (240, 228, 210)
DUSTY_ROSE = (185, 140, 135)
MUTED = (165, 148, 130)
ACCENT_DARK = (42, 32, 28)

FONT_SERIF = os.getenv("FONT_SERIF", "C:/Windows/Fonts/georgia.ttf")
FONT_SERIF_ITALIC = os.getenv("FONT_SERIF_ITALIC", "C:/Windows/Fonts/georgiai.ttf")
FONT_SERIF_BOLD = os.getenv("FONT_SERIF_BOLD", "C:/Windows/Fonts/georgiab.ttf")


def load_font(path, size):
    for p in [path, FONT_SERIF, "C:/Windows/Fonts/arial.ttf"]:
        try: return ImageFont.truetype(p, size)
        except (OSError, IOError): continue
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
    scale = WIDTH / fw; new_h = int(fh * scale)
    bg_scale = HEIGHT / fh
    bg = frame.resize((int(fw*bg_scale), HEIGHT), Image.LANCZOS)
    if bg.width > WIDTH:
        cx = (bg.width-WIDTH)//2; bg = bg.crop((cx,0,cx+WIDTH,HEIGHT))
    else: bg = bg.resize((WIDTH,HEIGHT), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(25))).enhance(0.35)
    bg.paste(frame.resize((WIDTH,new_h), Image.LANCZOS), (0, max(0,(HEIGHT-new_h)//2+y_offset)))
    return bg

def grade_frame(frame):
    return vignette(film_grain(soft_bloom(cottagecore_grade(make_vertical(frame)))))

def draw_text_pill(img, text, y, font, text_color=CREAM, max_width=None):
    if max_width is None: max_width = WIDTH - 160
    draw = ImageDraw.Draw(img)
    words = text.split(); lines = []; current = ""
    for w in words:
        test = f"{current} {w}" if current else w
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2]-bbox[0] > max_width:
            if current: lines.append(current)
            current = w
        else: current = test
    if current: lines.append(current)
    if not lines: return img
    line_h = 44; total_h = len(lines)*line_h; pad = 16
    max_lw = max(draw.textbbox((0,0),l,font=font)[2]-draw.textbbox((0,0),l,font=font)[0] for l in lines)
    rgba = img.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0,0,0,0))
    od = ImageDraw.Draw(ov)
    px = (WIDTH-max_lw)//2 - pad*2
    od.rounded_rectangle([px, y-pad, px+max_lw+pad*4, y+total_h+pad], radius=12, fill=(18,14,12,170))
    for i, line in enumerate(lines):
        bbox = od.textbbox((0,0), line, font=font)
        lw = bbox[2]-bbox[0]
        od.text(((WIDTH-lw)//2, y+i*line_h), line, fill=text_color+(240,), font=font)
    return Image.alpha_composite(rgba, ov).convert("RGB")


# ── Motion-Reactive Audio Engine ────────────────────────────────────────────

def extract_motion_curve(video_path, start_t, end_t, fps=FPS):
    """Extract per-frame motion intensity from video. Returns array 0.0-1.0."""
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(str(video_path))
    n_frames = int((end_t - start_t) * fps)
    times = np.linspace(start_t, end_t, n_frames, endpoint=False)

    motion = np.zeros(n_frames)
    prev = None
    for i, t in enumerate(times):
        frame = clip.get_frame(min(t, clip.duration - 0.05))
        if prev is not None:
            motion[i] = np.abs(frame.astype(float) - prev.astype(float)).mean()
        prev = frame.copy()
    clip.close()

    # Normalize to 0-1
    mx = motion.max()
    if mx > 0:
        motion = motion / mx
    return motion


def render_r2_chirp(freq_start, freq_end, duration_ms, sr=SR, volume=0.3):
    n = int(sr * duration_ms / 1000)
    progress = np.linspace(0, 1, n)
    freq = freq_start + (freq_end - freq_start) * progress
    phase = 2 * np.pi * np.cumsum(freq) / sr
    samples = np.sin(phase) * volume
    fade = min(int(sr * 0.005), n // 4)
    if fade > 0:
        samples[:fade] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))
        samples[-fade:] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))[::-1]
    return samples


def render_r2_beep(freq, duration_ms, sr=SR, volume=0.3):
    n = int(sr * duration_ms / 1000)
    t = np.arange(n, dtype=np.float64) / sr
    samples = np.sin(2 * np.pi * freq * t) * volume
    fade = min(int(sr * 0.005), n // 4)
    if fade > 0:
        samples[:fade] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))
        samples[-fade:] *= 0.5 * (1 - np.cos(np.pi * np.arange(fade) / fade))[::-1]
    return samples


def generate_motion_audio(motion_curve, total_duration):
    """Generate audio driven by frame motion intensity."""
    n = int(total_duration * SR)
    t = np.linspace(0, total_duration, n, dtype=np.float64)

    # Upsample motion curve from per-frame to per-sample
    motion_samples = np.interp(
        np.linspace(0, len(motion_curve)-1, n),
        np.arange(len(motion_curve)),
        motion_curve
    )
    # Smooth it
    try:
        import scipy.signal
        w = int(0.05 * SR)
        if w > 0 and w < len(motion_samples):
            motion_samples = np.convolve(motion_samples, np.ones(w)/w, mode='same')
    except ImportError:
        pass

    m = motion_samples  # shorthand

    # ── Layer 1: Motion-reactive drone ──
    # Base freq rises with motion: 80Hz calm → 480Hz chaos
    base_freq = 80 + m * 400
    # Accumulate phase for continuous tone
    phase = 2 * np.pi * np.cumsum(base_freq) / SR
    drone = np.sin(phase) * 0.15

    # Detuning between channels: more motion = more detune
    detune = m * 30  # Hz
    phase_L = 2 * np.pi * np.cumsum(base_freq - detune) / SR
    phase_R = 2 * np.pi * np.cumsum(base_freq + detune) / SR
    drone_L = np.sin(phase_L) * 0.12
    drone_R = np.sin(phase_R) * 0.12

    # Odd harmonics proportional to motion (dissonance)
    for harmonic in [3, 5, 7]:
        h_phase = 2 * np.pi * np.cumsum(base_freq * harmonic) / SR
        h_amp = m * 0.04 / harmonic
        drone += np.sin(h_phase) * h_amp

    # ── Layer 2: Noise floor rises with motion ──
    noise = np.random.randn(n) * m * 0.08

    # ── Layer 3: Impact transients at motion peaks ──
    impacts = np.zeros(n)
    # Find peaks in motion curve (local maxima above 0.6)
    peak_indices = []
    for i in range(1, len(motion_curve) - 1):
        if motion_curve[i] > 0.6 and motion_curve[i] > motion_curve[i-1] and motion_curve[i] >= motion_curve[i+1]:
            peak_indices.append(i)

    for pi in peak_indices:
        peak_time = pi / FPS
        peak_sample = int(peak_time * SR)
        intensity = motion_curve[pi]

        # Sub thud
        thud_t = t - peak_time
        thud_env = np.where(thud_t >= 0, np.exp(-thud_t * 5) * np.clip(thud_t * 50, 0, 1), 0)
        impacts += np.sin(2*np.pi*30*t) * 0.4 * intensity * thud_env

        # Metal clang harmonics
        for freq, amp, decay in [(587, 0.10, 7), (1174, 0.05, 9), (1760, 0.03, 11)]:
            clang_env = np.where(thud_t >= 0, np.exp(-thud_t * decay) * np.clip(thud_t * 40, 0, 1), 0)
            impacts += np.sin(2*np.pi*freq*t) * amp * intensity * clang_env

        # Noise burst
        noise_env = np.where(thud_t >= 0, np.exp(-thud_t * 15) * np.clip(thud_t * 80, 0, 1), 0)
        impacts += np.random.randn(n) * 0.12 * intensity * noise_env

    # ── Layer 4: R2 tones at key moments ──
    r2 = np.zeros(n)

    # Startled chirp at the biggest motion peak
    if peak_indices:
        biggest = max(peak_indices, key=lambda i: motion_curve[i])
        bt = biggest / FPS
        startled = np.concatenate([
            render_r2_beep(1800, 50, volume=0.4),
            np.zeros(int(SR * 0.03)),
            render_r2_beep(1400, 50, volume=0.4),
            render_r2_chirp(1400, 600, 150, volume=0.4),
        ])
        s = int(bt * SR)
        e = min(s + len(startled), n)
        r2[s:e] += startled[:e-s]

    # Sad warble 2s after the fall section ends
    fall_duration = len(motion_curve) / FPS
    sad_t = fall_duration + 1.5
    sad = np.concatenate([
        render_r2_chirp(400, 300, 300, volume=0.25),
        render_r2_chirp(350, 250, 200, volume=0.2),
    ])
    s = int(sad_t * SR)
    e = min(s + len(sad), n)
    if e > s:
        r2[s:e] += sad[:e-s]

    # Curious chirp when narration mentions "doorway" (~narration line 1)
    curious_t = fall_duration + 4.0
    curious = np.concatenate([
        render_r2_beep(600, 150, volume=0.2),
        render_r2_chirp(600, 900, 200, volume=0.2),
        render_r2_beep(900, 100, volume=0.2),
    ])
    s = int(curious_t * SR)
    e = min(s + len(curious), n)
    if e > s:
        r2[s:e] += curious[:e-s]

    # ── Layer 5: Post-fall D-minor drone ──
    post_start = fall_duration + 0.5
    D2, F2, A2 = 73.42, 87.31, 110.0
    post_drone = (np.sin(2*np.pi*D2*t)*0.025 + np.sin(2*np.pi*F2*t)*0.015 +
                  np.sin(2*np.pi*A2*t)*0.020)
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.08*t)
    post_drone += np.sin(2*np.pi*293.66*t)*0.005*lfo
    post_env = np.clip((t - post_start) / 3.0, 0, 1) * np.clip((total_duration - t) / 3.0, 0, 1)
    post_drone *= post_env

    # ── Layer 6: Sparse chimes ──
    chimes = np.zeros(n)
    for ct, freq in [(post_start+3, 587.33), (post_start+10, 698.46),
                     (post_start+18, 880.0), (post_start+26, 587.33)]:
        if ct >= total_duration - 1: continue
        ec = np.where(t-ct >= 0, np.exp(-(t-ct)*3.0)*np.clip((t-ct)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.015 * ec

    # ── Mix to stereo ──
    # During fall: motion-reactive dominates
    # After fall: drone + chimes + r2
    fall_mask = np.clip(1.0 - (t - fall_duration) / 1.0, 0, 1)  # fades out over 1s
    post_mask = 1.0 - fall_mask

    mono_fall = (drone + noise + impacts + r2) * fall_mask
    mono_post = (post_drone + chimes + r2) * post_mask
    mono = mono_fall + mono_post

    # Low-pass
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3500, 'low', fs=SR, output='sos')
        mono = scipy.signal.sosfilt(sos, mono)
    except ImportError:
        pass

    # Stereo with motion-driven width
    left = mono + drone_L * fall_mask + post_drone * post_mask * 0.5
    right = mono + drone_R * fall_mask + post_drone * post_mask * 0.5
    # Impacts center (both channels)
    left += impacts * 0.3
    right += impacts * 0.3

    stereo = np.column_stack([left, right])
    pk = np.abs(stereo).max()
    return stereo / pk * 0.75 if pk > 0 else stereo


# ── TTS ─────────────────────────────────────────────────────────────────────

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
    probe = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
                           "-of","csv=p=0",str(output_path)], capture_output=True, text=True)
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
        elif arr.shape[1] == 1: arr = np.column_stack([arr[:,0], arr[:,0]])
        s = int(start_t * sr); e = min(s+len(arr), n)
        if e-s > 0: narr[s:e] += arr[:e-s].astype(np.float64)
    env = np.abs(narr).max(axis=1)
    try:
        import scipy.signal
        w = int(0.15*sr)
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
    start_t = max(0, min(start_t, clip.duration-1))
    end_t = min(end_t, clip.duration-0.05)
    n = int((end_t-start_t)*FPS)
    times = np.linspace(start_t, end_t, n, endpoint=False)
    frames = []
    for tv in times:
        try: frames.append(Image.fromarray(clip.get_frame(min(tv, clip.duration-0.05))))
        except:
            if frames: frames.append(frames[-1].copy())
    clip.close()
    return frames


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  MIDNIGHT RUN — Final Cut")
    print("  Motion-reactive audio. Unreliable narrator.")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / "midnight_final_tts"
    tts_dir.mkdir(exist_ok=True)

    video_path = KOMBUCHA_DIR / "video" / "web" / "tick_0277.mp4"
    if not video_path.exists():
        video_path = KOMBUCHA_DIR / "video" / "tick_0277.mp4"

    # ── Timeline ──
    # Fall is at source t=129.75s to ~132.5s (confirmed by binary search)
    # Start 0.25s before fall: t=129.5s
    # Fall footage: 4s real-time (129.5 - 133.5)
    # Narration starts at 1.5s (DURING the fall aftermath)
    FALL_START = 129.5
    FALL_DURATION = 4.0
    FALL_END = FALL_START + FALL_DURATION
    NARR_START = 1.5  # voice arrives while upside down

    narration_lines = [
        "I drove through a doorway at midnight and found myself staring at a bare light bulb.",
        "This is the rover equivalent of walking into a room and forgetting why you came in.",
        "The bulb is in a wire cage, industrial, casting everything orange. Somewhere below it is a room I have never mapped.",
        "What I did not know, what I could not know from this angle, is that there was no doorway. There was no new room. I drove into a bar stool at full speed, climbed the leg, and flipped myself onto my back. The new room was the ceiling.",
    ]

    # ── Step 1: TTS ──
    print("\n  STEP 1: TTS...")
    tts_clips = []
    current_time = NARR_START
    gap = 0.8
    for i, text in enumerate(narration_lines):
        print(f"    Line {i+1}: \"{text[:55]}...\"")
        path, dur = generate_tts(text, tts_dir / f"line_{i:02d}.mp3")
        tts_clips.append((path, current_time, dur, text))
        print(f"      {dur:.1f}s at t={current_time:.1f}")
        current_time += dur + gap

    total_duration = current_time + 2.0
    total_frames = int(total_duration * FPS)
    print(f"\n  Duration: {total_duration:.1f}s ({total_frames} frames)")

    # ── Step 2: Extract motion curve from fall footage ──
    print("\n  STEP 2: Extract motion curve from fall...")
    fall_motion = extract_motion_curve(video_path, FALL_START, FALL_END)
    print(f"    {len(fall_motion)} frames, peak motion: {fall_motion.max():.2f}")
    # Extend with zeros for the rest of the video (post-fall is static ceiling)
    full_motion = np.zeros(total_frames)
    full_motion[:len(fall_motion)] = fall_motion

    # ── Step 3: Generate motion-reactive audio ──
    print("\n  STEP 3: Motion-reactive audio synthesis...")
    bed = generate_motion_audio(full_motion, total_duration)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    audio_path = OUTPUT_DIR / "midnight_final_audio.wav"
    write_wav(audio_path, audio)
    print(f"    Saved: {audio_path}")

    # ── Step 4: Load video frames ──
    print("\n  STEP 4: Load footage...")
    # Fall: real-time
    fall_frames = load_realtime_frames(video_path, FALL_START, FALL_END)
    print(f"    Fall: {len(fall_frames)} frames (real-time, {FALL_START}s-{FALL_END}s)")

    # Contemplation: upside down ceiling, slow-mo stretch
    contemplate_raw = load_realtime_frames(video_path, 140, 250)
    contemplate_needed = total_frames - len(fall_frames)
    contemplate_frames = [contemplate_raw[min(int(i*len(contemplate_raw)/contemplate_needed),
                          len(contemplate_raw)-1)] for i in range(contemplate_needed)]
    print(f"    Contemplate: {len(contemplate_frames)} frames (slow-mo)")

    # ── Step 5: Render ──
    print(f"\n  STEP 5: Rendering {total_frames} frames...")
    frame_dir = OUTPUT_DIR / "midnight_final_frames"
    frame_dir.mkdir(exist_ok=True)

    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_title = load_font(FONT_SERIF_BOLD, 42)
    font_tick = load_font(FONT_SERIF, 26)

    fall_frame_count = len(fall_frames)

    for fi in range(total_frames):
        gt = fi / FPS

        if fi < fall_frame_count:
            base = fall_frames[fi]
        else:
            ci = fi - fall_frame_count
            base = contemplate_frames[min(ci, len(contemplate_frames)-1)]

        img = grade_frame(base)

        # Tick label
        draw = ImageDraw.Draw(img)
        tick_label = "tick 0277" if gt < 20 else "tick 0278"
        draw.text((60, 170), tick_label, fill=MUTED, font=font_tick)

        # Title appears after fall settles
        if gt > 3.0:
            ta = min((gt - 3.0) * 2, 1.0)
            img = draw_text_pill(img, "MIDNIGHT RUN", 100,
                                font_title, tuple(int(c*ta) for c in CREAM))

        # Active narration
        for tc in tts_clips:
            path, start, dur, text = tc
            if start <= gt < start + dur + 0.5:
                fade = min((gt-start)*3, 1.0) * min((start+dur+0.5-gt)*3, 1.0)
                if fade > 0.1:
                    img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)
                break

        # ── Picture-in-Picture: replay the fall on loop from t=30s to end ──
        PIP_START = 30.0
        PIP_DURATION = 3.0  # each loop cycle
        if gt >= PIP_START:
            pip_progress = ((gt - PIP_START) % PIP_DURATION) / PIP_DURATION
            pip_frame_idx = int(pip_progress * len(fall_frames))
            pip_frame_idx = min(pip_frame_idx, len(fall_frames) - 1)
            pip_src = fall_frames[pip_frame_idx]

            # Convert to black and white
            pip_bw = pip_src.convert("L").convert("RGB")

            # Scale to PiP size (320x240)
            pip_w, pip_h = 320, 240
            pip_img = pip_bw.resize((pip_w, pip_h), Image.LANCZOS)

            # Add border
            bordered = Image.new("RGB", (pip_w + 6, pip_h + 6), (255, 255, 255))
            bordered.paste(pip_img, (3, 3))

            # Flash "TILT" in black — visible on odd half-seconds
            flash_on = int(gt * 4) % 2 == 0  # flashes 4x per second
            if flash_on:
                pip_draw = ImageDraw.Draw(bordered)
                font_tilt = load_font(FONT_SERIF_BOLD, 48)
                tilt_text = "TILT"
                bbox = pip_draw.textbbox((0, 0), tilt_text, font=font_tilt)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = (pip_w + 6 - tw) // 2
                ty = (pip_h + 6 - th) // 2
                # White outline for readability on B&W
                for ox in range(-2, 3):
                    for oy in range(-2, 3):
                        if ox or oy:
                            pip_draw.text((tx+ox, ty+oy), tilt_text, fill=(255,255,255), font=font_tilt)
                pip_draw.text((tx, ty), tilt_text, fill=(0, 0, 0), font=font_tilt)

            # Paste PiP upper center
            pip_x = (WIDTH - bordered.width) // 2
            pip_y = 180
            img.paste(bordered, (pip_x, pip_y))

        img.save(frame_dir / f"frame_{fi:05d}.png")
        if (fi+1) % 60 == 0:
            pct = (fi+1) / total_frames * 100
            phase = "FALL" if fi < fall_frame_count else "NARR"
            print(f"    [{pct:5.1f}%] Frame {fi+1}/{total_frames} [{phase}]")

    # ── Step 6: Encode ──
    print("\n  STEP 6: Encoding...")
    video_out = OUTPUT_DIR / "midnight_run_final.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%05d.png"), "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-crf", "18", "-preset", "slow", "-shortest", str(video_out),
    ], capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(frame_dir)
    if tts_dir.exists(): shutil.rmtree(tts_dir)

    size_mb = video_out.stat().st_size / (1024*1024)
    dur = float(subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
                                "-of","csv=p=0",str(video_out)], capture_output=True, text=True).stdout.strip())
    print(f"\n  Output: {video_out}")
    print(f"  Duration: {dur:.1f}s  Size: {size_mb:.1f} MB")
    print(f"  Fall starts: source t={FALL_START}s (binary-search confirmed)")
    print(f"  Audio: motion-reactive (drone/dissonance/transients driven by frame diffs)")
    print(f"  Voice enters at t={NARR_START}s (calm narration over upside-down footage)")
    print("\n" + "=" * 60)
    print("  Midnight Run — Final Cut complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
