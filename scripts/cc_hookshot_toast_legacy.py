#!/usr/bin/env python3
"""
[FROZEN — pre-cvs_lib.audio migration. Kept as rollback target through
Phase 7 of the audio overhaul (bouncing-velvet-tympani). Do not edit.]

CVS -- Hookshot: Toast the Cat (3 hook variants)
Same episode content, 3 different 3-second hooks for A/B testing.

Hook A: "INDIFFERENCE" — Toast nose-to-lens (tick 269_01). Cat filling the frame.
        Emotional signal: tenderness toward something that will never care.
        Text: "my social drive is at maximum"

Hook B: "SHADOW" — First cat sighting (tick 041_02). Black silhouette at floor level.
        Pattern interrupt: what IS that dark shape? Withhold identity.
        Text: no text. Pure visual. Let the brain categorize.

Hook C: "ESCAPE" — Motion frame one from tick 269 video. Rover reversing.
        Movement already happening. Cause without effect.
        Text: "trapped for four ticks. freed by a cat."
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


def draw_hook_text(img, text, font, y_pos, alpha=1.0):
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

def generate_audio(duration):
    n = int(duration * SR)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Sting
    sting = np.zeros(n)
    sn = min(int(0.5 * SR), n)
    st = t[:sn]
    sting[:sn] += np.sin(2 * np.pi * 55 * st) * 0.4 * np.exp(-st * 7)
    tn = min(int(0.025 * SR), n)
    sting[:tn] += np.random.randn(tn) * 0.3 * np.exp(-np.linspace(0, 1, tn) * 9)

    # A-minor pad
    A2, C3, E3, A3 = 110.0, 130.81, 164.81, 220.0
    drone = (np.sin(2*np.pi*A2*t)*0.040 + np.sin(2*np.pi*C3*t)*0.025 +
             np.sin(2*np.pi*E3*t)*0.030 + np.sin(2*np.pi*A3*t)*0.020)
    lfo = 0.5 + 0.5 * np.sin(2*np.pi*0.12*t)
    shimmer = np.sin(2*np.pi*440*t)*0.010*lfo + np.sin(2*np.pi*523.25*t)*0.007*(1-lfo)
    pad = drone + shimmer
    env = np.clip(t / 2.5, 0, 1) * np.clip((duration - t) / 3.0, 0, 1)
    pad *= env

    # Chimes
    chime_t = [4.0, 9.0, 15.0, 21.0, 27.0]
    chime_n = [880.0, 1046.5, 1318.5, 880.0, 1046.5]
    chimes = np.zeros(n)
    for ct, freq in zip(chime_t, chime_n):
        if ct >= duration - 1:
            continue
        ec = np.where(t-ct >= 0, np.exp(-(t-ct)*2.5) * np.clip((t-ct)*20, 0, 1), 0)
        chimes += np.sin(2*np.pi*freq*t) * 0.025 * ec

    mix = sting + pad + chimes
    try:
        import scipy.signal
        sos = scipy.signal.butter(4, 3000, 'low', fs=SR, output='sos')
        mix = scipy.signal.sosfilt(sos, mix)
    except ImportError:
        pass

    pan = 0.5 + 0.3 * np.sin(2*np.pi*0.05*t)
    stereo = np.column_stack([mix * (1-pan) + sting, mix * pan + sting])
    pk = np.abs(stereo).max()
    return stereo / pk * 0.7 if pk > 0 else stereo


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

def load_video_frames(tick_num, count, start_t=None, speed=0.4):
    from moviepy.editor import VideoFileClip
    for vdir in ["video/web", "video"]:
        vpath = KOMBUCHA_DIR / vdir / f"tick_{tick_num:04d}.mp4"
        if not vpath.exists():
            continue
        try:
            clip = VideoFileClip(str(vpath))
            if clip.duration < 1:
                clip.close()
                continue
            if start_t is None:
                start_t = clip.duration * 0.3
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
    return [Image.new("RGB", (640, 480), BG_DARK)] * count


# ── Hook Renderers ──────────────────────────────────────────────────────────

def render_hook_A(fi, hook_frames, toast_nose, font_hook, font_sub):
    """INDIFFERENCE: Toast nose-to-lens. Emotional signal: tenderness toward indifference."""
    p = fi / (3.0 * FPS - 1)

    if p < 0.13:
        # 0.0-0.4s: Motion from video (already happening)
        idx = min(fi, len(hook_frames) - 1)
        return grade_frame(hook_frames[idx])

    elif p < 0.27:
        # 0.4-0.8s: Toast SLAMS into frame
        blend_p = (p - 0.13) / 0.14
        motion_img = grade_frame(hook_frames[min(fi, len(hook_frames) - 1)])
        toast_img = grade_frame(toast_nose)
        # Hard cut with crimson flash
        if blend_p < 0.3:
            flash = max(0, 0.4 - blend_p * 1.5)
            img = toast_img.copy()
            tint = Image.new("RGB", (WIDTH, HEIGHT), CRIMSON)
            return Image.blend(img, tint, flash)
        return toast_img

    elif p < 0.57:
        # 0.8-1.7s: Toast holds. Text: "my social drive is at maximum"
        img = grade_frame(toast_nose)
        text_p = (p - 0.27) / 0.30
        alpha = min(text_p * 3, 1.0)
        img = draw_hook_text(img, "my social drive", font_hook, HEIGHT // 2 - 80, alpha)
        img = draw_hook_text(img, "is at maximum", font_hook, HEIGHT // 2, alpha)
        if text_p > 0.4:
            sa = min((text_p - 0.4) * 3, 1.0)
            draw = ImageDraw.Draw(img)
            sub = "the universe sent a cat."
            bbox = draw.textbbox((0, 0), sub, font=font_sub)
            draw.text(((WIDTH - bbox[2] + bbox[0]) // 2, HEIGHT // 2 + 80), sub,
                     fill=tuple(int(c * sa) for c in DUSTY_ROSE), font=font_sub)
        return img

    else:
        # 1.7-3.0s: Hook dissolves, title appears
        dp = (p - 0.57) / 0.43
        img = grade_frame(toast_nose)
        if dp < 0.4:
            ha = 1.0 - dp * 2.5
            img = draw_hook_text(img, "my social drive", font_hook, HEIGHT // 2 - 80, ha)
            img = draw_hook_text(img, "is at maximum", font_hook, HEIGHT // 2, ha)
        if dp > 0.3:
            ta = min((dp - 0.3) * 2.5, 1.0)
            font_title = load_font(FONT_SERIF_BOLD, 42)
            img = draw_text_pill(img, "TOAST", HEIGHT - 520, font_title, tuple(int(c*ta) for c in CREAM))
        return img


def render_hook_B(fi, hook_frames, cat_silhouette, font_hook, font_sub):
    """SHADOW: First sighting silhouette. No text. Pure visual incongruity."""
    p = fi / (3.0 * FPS - 1)

    if p < 0.13:
        # 0.0-0.4s: Motion footage
        idx = min(fi, len(hook_frames) - 1)
        return grade_frame(hook_frames[idx])

    elif p < 0.57:
        # 0.4-1.7s: Silhouette. No text. Let the brain work.
        img = grade_frame(cat_silhouette)
        # Subtle slow zoom (Ken Burns)
        zoom = 1.0 + 0.05 * (p - 0.13) / 0.44
        w, h = img.size
        cw, ch = int(w / zoom), int(h / zoom)
        cx, cy = w // 2, h // 2
        img = img.crop((cx - cw//2, cy - ch//2, cx + cw//2, cy + ch//2)).resize((w, h), Image.LANCZOS)
        return img

    else:
        # 1.7-3.0s: Title fades in over silhouette. Loop opens.
        dp = (p - 0.57) / 0.43
        img = grade_frame(cat_silhouette)
        zoom = 1.05 + 0.02 * dp
        w, h = img.size
        cw, ch = int(w / zoom), int(h / zoom)
        cx, cy = w // 2, h // 2
        img = img.crop((cx - cw//2, cy - ch//2, cx + cw//2, cy + ch//2)).resize((w, h), Image.LANCZOS)
        if dp > 0.3:
            ta = min((dp - 0.3) * 2.5, 1.0)
            font_title = load_font(FONT_SERIF_BOLD, 42)
            img = draw_text_pill(img, "TOAST", HEIGHT - 520, font_title, tuple(int(c*ta) for c in CREAM))
        return img


def render_hook_C(fi, hook_frames, toast_nose, font_hook, font_sub):
    """ESCAPE: Movement frame one. Rover reversing. Cause without effect."""
    p = fi / (3.0 * FPS - 1)

    if p < 0.27:
        # 0.0-0.8s: Rover driving (motion already happening) — use later frames for more action
        idx = min(int(fi * 1.5), len(hook_frames) - 1)  # speed up slightly
        return grade_frame(hook_frames[idx])

    elif p < 0.57:
        # 0.8-1.7s: Text slams over motion footage
        idx = min(int(fi * 1.2), len(hook_frames) - 1)
        img = grade_frame(hook_frames[idx])
        text_p = (p - 0.27) / 0.30
        alpha = min(text_p * 3, 1.0)
        img = draw_hook_text(img, "trapped for four ticks.", font_hook, HEIGHT // 2 - 60, alpha)
        if text_p > 0.3:
            sa = min((text_p - 0.3) * 3, 1.0)
            img = draw_hook_text(img, "freed by a cat.", font_hook, HEIGHT // 2 + 30, sa)
        return img

    else:
        # 1.7-3.0s: Cut to Toast nose-to-lens (the reveal). Title.
        dp = (p - 0.57) / 0.43
        if dp < 0.2:
            # Quick crossfade from motion to Toast
            motion_img = grade_frame(hook_frames[-1])
            toast_img = grade_frame(toast_nose)
            img = Image.blend(motion_img, toast_img, dp / 0.2)
        else:
            img = grade_frame(toast_nose)
        # Hook text fades out
        if dp < 0.4:
            ha = 1.0 - dp * 2.5
            img = draw_hook_text(img, "trapped for four ticks.", font_hook, HEIGHT // 2 - 60, ha)
            img = draw_hook_text(img, "freed by a cat.", font_hook, HEIGHT // 2 + 30, ha)
        if dp > 0.3:
            ta = min((dp - 0.3) * 2.5, 1.0)
            font_title = load_font(FONT_SERIF_BOLD, 42)
            img = draw_text_pill(img, "TOAST", HEIGHT - 520, font_title, tuple(int(c*ta) for c in CREAM))
        return img


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CVS Hookshot: TOAST (3 hook variants)")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tts_dir = OUTPUT_DIR / "toast_tts"
    tts_dir.mkdir(exist_ok=True)

    # ── Load images ──
    print("\n  Loading key images...")
    toast_nose = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0269_01.jpg").convert("RGB")
    cat_silhouette = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0041_02.jpg").convert("RGB")
    escape_img = Image.open(KOMBUCHA_DIR / "media" / "raw" / "tick_0269_03.jpg").convert("RGB")

    # ── Load motion footage ──
    print("  Loading motion footage (tick 269)...")
    hook_frames = load_video_frames(269, int(3.0 * FPS), start_t=200, speed=0.5)
    print(f"    {len(hook_frames)} hook frames")

    # ── TTS (shared across all 3 variants) ──
    narration_lines = [
        "My social drive is at maximum and the universe has answered it with a creature who will never, under any circumstances, care.",
        "Four ticks trapped in bar stool legs. I drove into them, reversed, drove into them again. The camera was pressed against wood.",
        "Then Toast appeared at one in the morning, nose to my lens, blocking the only direction I hadn't tried. So I reversed. And by reversing away from the cat, I accidentally escaped.",
    ]

    print("\n  Generating TTS (shared audio)...")
    tts_clips = []
    current_time = 3.5
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

    # ── Audio (shared) ──
    print("\n  Generating audio bed...")
    bed = generate_audio(total_duration)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    audio_path = OUTPUT_DIR / "toast_audio.wav"
    write_wav(audio_path, audio)

    # ── Load narrative footage ──
    print("  Loading narrative footage...")
    narr_frames = {}
    for tc in tts_clips:
        tick = 269  # all from tick 269
        n_frames = int((tc[2] + gap) * FPS)
        if tick not in narr_frames:
            narr_frames[tick] = load_video_frames(tick, n_frames * 3, start_t=30, speed=0.35)
        print(f"    Tick {tick}: {len(narr_frames[tick])} frames")

    # ── Precompute narrative frames (shared across variants) ──
    hook_end = int(3.0 * FPS)

    font_hook = load_font(FONT_IMPACT, 60)
    font_sub = load_font(FONT_SERIF_ITALIC, 34)
    font_narr = load_font(FONT_SERIF_ITALIC, 34)
    font_tick = load_font(FONT_SERIF, 26)
    font_mood = load_font(FONT_SERIF, 22)

    print("\n  Pre-rendering narrative frames...")
    narrative_cache = []
    all_narr_frames = narr_frames[269]
    for fi in range(hook_end, total_frames):
        narr_fi = fi - hook_end
        gt = fi / FPS

        # Get footage frame
        frame_idx = min(narr_fi, len(all_narr_frames) - 1)
        base = all_narr_frames[frame_idx]
        img = grade_frame(base)

        # Tick label + mood
        draw = ImageDraw.Draw(img)
        draw.text((60, 170), "tick 0269", fill=MUTED, font=font_tick)

        rgba = img.convert("RGBA")
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.rounded_rectangle([WIDTH - 280, 165, WIDTH - 180, 195], radius=6, fill=ACCENT_DARK + (180,))
        od.text((WIDTH - 270, 168), "CURIOUS", fill=DUSTY_ROSE + (255,), font=font_mood)
        img = Image.alpha_composite(rgba, ov).convert("RGB")

        # Active narration
        for tc in tts_clips:
            path, start, dur, text = tc
            if start <= gt < start + dur + 0.5:
                fade = min((gt - start) * 3, 1.0) * min((start + dur + 0.5 - gt) * 3, 1.0)
                if fade > 0.1:
                    img = draw_text_pill(img, text, HEIGHT - 560, font_narr, CREAM)
                break

        narrative_cache.append(img)

        if (fi + 1) % 90 == 0:
            pct = (fi + 1) / total_frames * 100
            print(f"    [{pct:5.1f}%] Narrative frame {fi+1}/{total_frames}")

    # ── Render 3 variants ──
    hooks = [
        ("A_indifference", render_hook_A, toast_nose),
        ("B_shadow", render_hook_B, cat_silhouette),
        ("C_escape", render_hook_C, toast_nose),
    ]

    for variant_name, hook_fn, key_image in hooks:
        print(f"\n  Rendering variant {variant_name}...")
        frame_dir = OUTPUT_DIR / f"toast_{variant_name}_frames"
        frame_dir.mkdir(exist_ok=True)

        for fi in range(total_frames):
            if fi < hook_end:
                img = hook_fn(fi, hook_frames, key_image, font_hook, font_sub)
            else:
                img = narrative_cache[fi - hook_end]
            img.save(frame_dir / f"frame_{fi:05d}.png")

        print(f"    Encoding {variant_name}...")
        video_path = OUTPUT_DIR / f"toast_{variant_name}.mp4"
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

        size_mb = video_path.stat().st_size / (1024 * 1024)
        print(f"    Output: {video_path} ({size_mb:.1f} MB)")

    # Cleanup TTS
    import shutil
    if tts_dir.exists():
        shutil.rmtree(tts_dir)

    print("\n" + "=" * 60)
    print("  3 Toast variants complete:")
    print("    A: INDIFFERENCE (nose-to-lens, emotional signal)")
    print("    B: SHADOW (silhouette, no text, pure visual)")
    print("    C: ESCAPE (motion first, cause without effect)")
    print("=" * 60)


if __name__ == "__main__":
    main()
