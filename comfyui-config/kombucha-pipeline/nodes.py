"""
Kombucha Pipeline v3 — TikTok-native vertical video production.

Changes from v2:
  - VerticalFrameComposite: blurred video fill instead of solid black
  - TextOverlay: TikTok safe zones, bold sans-serif font, center-placed quote
  - All text respects safe zones (top 150px, bottom 480px, right 120px)

Nodes:
  - ParseTickLog: Extracts monologue, mood, tick number; picks best quote
  - ElevenLabsTTS: Direct ElevenLabs API for text-to-speech
  - MotionClip: Removes static frames, keeps only motion segments
  - VerticalFrameComposite: Blurred background fill + sharp video centered
  - TextOverlay: Safe-zone-aware text with bold sans-serif font
"""

import re
import tempfile
from pathlib import Path

import numpy as np
import requests
import torch
import torchaudio
from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ── Parse Tick Log ──────────────────────────────────────────────────────────

class ParseTickLog:
    """Parse a Kombucha tick markdown file. Extracts full monologue for TTS
    and picks the best 1-2 sentence quote for on-screen display."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "log_path": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("title", "mood", "monologue", "best_quote", "tick_number", "goal", "intent")
    FUNCTION = "parse"
    CATEGORY = "Kombucha"

    def parse(self, log_path):
        path = Path(log_path)
        if not path.exists():
            return ("TICK ???", "unknown", "No log found.", "No log found.", "0", "", "")

        md = path.read_text(encoding="utf-8")

        tick_m = re.search(r"tick[_ ]?(\d+)", path.stem, re.IGNORECASE)
        tick_num = tick_m.group(1).lstrip("0") if tick_m else "0"
        title = f"TICK {tick_num}"

        mood_m = re.search(r"## Mood\s*\n+(\w+)", md)
        mood = mood_m.group(1) if mood_m else "unknown"

        mono_m = re.search(r"## Monologue\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
        if not mono_m:
            mono_m = re.search(r"## Thought\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
        if not mono_m:
            mono_m = re.search(r"## Observation\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
        monologue = mono_m.group(1).strip() if mono_m else "..."

        all_narrative = []
        for section in ["Monologue", "Thought", "Observation", "Perception",
                        "Orientation", "Decision"]:
            sec_m = re.search(rf"## {section}\s*\n+([\s\S]*?)(?=\n## |\Z)", md)
            if sec_m:
                all_narrative.append(sec_m.group(1).strip())
        combined_narrative = "\n\n".join(all_narrative) if all_narrative else monologue
        best_quote = self._pick_best_quote(combined_narrative)

        goal_m = re.search(r"\*\*Goal\*\*:\s*(.+)", md)
        goal = goal_m.group(1).strip() if goal_m else ""

        intent_m = re.search(r"\*\*Intent\*\*:\s*(.+)", md)
        intent = intent_m.group(1).strip() if intent_m else ""

        return (title, mood, monologue, best_quote, tick_num, goal, intent)

    def _pick_best_quote(self, text):
        if not text or text == "...":
            return text

        sentences = re.split(r'(?<=[.!?])\s+', text)
        if not sentences:
            return text[:120]

        scored = []
        for s in sentences:
            s = s.strip()
            if len(s) < 15:
                continue
            score = 0
            s_lower = s.lower()

            if 30 <= len(s) <= 120:
                score += 3
            elif len(s) <= 30:
                score += 1

            metaphor_patterns = [
                r'\bis a\b.*\b(moon|planet|star|obelisk|leash|lifeline|villain)',
                r'\blike a\b', r'\bas if\b', r'\bthe way a\b',
                r"'s (way|planet|moon)", r'\bis the\b',
                r'\bnot .* but\b', r'\binstead of\b',
            ]
            for pat in metaphor_patterns:
                if re.search(pat, s_lower):
                    score += 3
                    break

            if s.endswith('!'):
                score += 2
            if '\u2014' in s or ' -- ' in s:
                score += 2

            figurative = ['never', 'always', 'every', 'perhaps',
                          'apparently', 'unfortunately', 'the fundamental',
                          'the indignity', 'promising', 'the revolution']
            for f in figurative:
                if f in s_lower:
                    score += 2

            if s.startswith('I ') or ' I ' in s:
                score += 1
            if s == sentences[-1].strip():
                score += 1
            if re.search(r'\d{2,}[=%]|POST |odom|battery|\d+\.\d+%|T:\d+|L=\d|R=\d', s):
                score -= 4
            if len(s) > 160:
                score -= 3
            if s_lower.startswith(('the open floor', 'the floor is', 'i should',
                                   'if i ', 'i will ', 'i need to')):
                score -= 2

            scored.append((score, s))

        if not scored:
            return text[:120]

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]

        if len(best) < 80 and len(scored) > 1:
            second = scored[1][1]
            combined = f"{best} {second}"
            if len(combined) <= 160:
                best = combined

        return best


# ── ElevenLabs TTS (Direct API) ────────────────────────────────────────────

class ElevenLabsTTS:
    """Call ElevenLabs TTS API directly. Returns AUDIO tensor."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "forceInput": True}),
                "api_key": ("STRING", {"default": ""}),
                "voice_id": ("STRING", {"default": "pNInz6obpgDQGcFmaJgB"}),
                "model_id": (["eleven_multilingual_v2", "eleven_monolingual_v1",
                              "eleven_turbo_v2_5", "eleven_turbo_v2"],
                             {"default": "eleven_multilingual_v2"}),
                "stability": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
                "similarity_boost": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "generate"
    CATEGORY = "Kombucha"

    def generate(self, text, api_key, voice_id, model_id, stability, similarity_boost):
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
        if not text.strip():
            raise ValueError("Text cannot be empty")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        waveform, sample_rate = torchaudio.load(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)

        if waveform.dim() == 2:
            waveform = waveform.unsqueeze(0)

        return ({"waveform": waveform, "sample_rate": sample_rate},)


# ── Motion Clip ─────────────────────────────────────────────────────────────

class MotionClip:
    """Detect motion in video frames and return only frames with movement."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "sensitivity": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1}),
                "min_segment_frames": ("INT", {"default": 5, "min": 1, "max": 60}),
                "merge_gap_frames": ("INT", {"default": 15, "min": 1, "max": 60}),
                "pad_frames": ("INT", {"default": 8, "min": 0, "max": 30}),
                "max_output_frames": ("INT", {"default": 600, "min": 10, "max": 3000}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("images", "frame_count")
    FUNCTION = "clip_motion"
    CATEGORY = "Kombucha"

    def clip_motion(self, images, sensitivity, min_segment_frames,
                    merge_gap_frames, pad_frames, max_output_frames):
        B, H, W, C = images.shape

        if B <= 2:
            return (images, B)

        frames_np = images.numpy()
        diffs = np.zeros(B - 1)
        for i in range(B - 1):
            diffs[i] = np.abs(
                frames_np[i + 1].astype(np.float32) - frames_np[i].astype(np.float32)
            ).mean()

        median_diff = np.median(diffs)
        threshold = median_diff * sensitivity
        motion_mask = diffs > threshold

        segments = []
        in_motion = False
        start = 0
        for i, m in enumerate(motion_mask):
            if m and not in_motion:
                start = i
                in_motion = True
            elif not m and in_motion:
                segments.append([start, i])
                in_motion = False
        if in_motion:
            segments.append([start, len(motion_mask)])

        segments = [s for s in segments if (s[1] - s[0]) >= min_segment_frames]

        if not segments:
            indices = np.linspace(0, B - 1, min(max_output_frames, B), dtype=int)
            return (images[indices], len(indices))

        merged = [segments[0]]
        for seg in segments[1:]:
            if seg[0] - merged[-1][1] <= merge_gap_frames:
                merged[-1][1] = seg[1]
            else:
                merged.append(seg)

        padded = []
        for s, e in merged:
            padded.append((max(0, s - pad_frames), min(B, e + pad_frames)))

        final = [padded[0]]
        for seg in padded[1:]:
            if seg[0] <= final[-1][1]:
                final[-1] = (final[-1][0], max(final[-1][1], seg[1]))
            else:
                final.append(seg)

        indices = []
        for s, e in final:
            indices.extend(range(s, e))

        if len(indices) > max_output_frames:
            step = len(indices) / max_output_frames
            indices = [indices[int(i * step)] for i in range(max_output_frames)]

        return (images[torch.tensor(indices, dtype=torch.long)], len(indices))


# ── Vertical Frame Composite v3 ────────────────────────────────────────────

class VerticalFrameComposite:
    """Place horizontal video into vertical 1080x1920 canvas with blurred
    video fill behind the sharp original. No more black bars."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "canvas_width": ("INT", {"default": 1080, "min": 100, "max": 4096}),
                "canvas_height": ("INT", {"default": 1920, "min": 100, "max": 4096}),
                "blur_radius": ("INT", {"default": 25, "min": 0, "max": 80, "step": 5}),
                "blur_darken": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.05}),
                "video_y_offset": ("INT", {"default": -60, "min": -500, "max": 500, "step": 10}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("images", "top_zone_height", "bottom_zone_start")
    FUNCTION = "composite"
    CATEGORY = "Kombucha"

    def composite(self, images, canvas_width, canvas_height,
                  blur_radius, blur_darken, video_y_offset):
        B, H, W, C = images.shape

        # Calculate sharp video placement
        scale = canvas_width / W
        new_w = canvas_width
        new_h = int(H * scale)
        y_pos = (canvas_height - new_h) // 2 + video_y_offset

        # Resize sharp video
        frames_chw = images.permute(0, 3, 1, 2)  # B,C,H,W
        sharp = torch.nn.functional.interpolate(
            frames_chw, size=(new_h, new_w), mode="bilinear", align_corners=False)

        # Create blurred background: scale to fill full canvas height
        bg_scale = canvas_height / H
        bg_w = int(W * bg_scale)
        blurred_full = torch.nn.functional.interpolate(
            frames_chw, size=(canvas_height, bg_w), mode="bilinear", align_corners=False)

        # Center-crop to canvas width
        if bg_w >= canvas_width:
            crop_x = (bg_w - canvas_width) // 2
            blurred_full = blurred_full[:, :, :, crop_x:crop_x + canvas_width]
        else:
            # If not wide enough, stretch to fill
            blurred_full = torch.nn.functional.interpolate(
                blurred_full, size=(canvas_height, canvas_width),
                mode="bilinear", align_corners=False)

        # Apply blur frame by frame via PIL (gaussian blur on GPU tensor is tricky)
        canvas_list = []
        for i in range(B):
            # Convert to PIL for blur
            bg_np = (blurred_full[i].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            bg_pil = Image.fromarray(bg_np)
            if blur_radius > 0:
                bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            # Darken the blurred background
            bg_arr = np.array(bg_pil).astype(np.float32) / 255.0
            bg_arr *= blur_darken

            # Paste sharp video on top
            paste_y = max(0, y_pos)
            paste_end_y = min(canvas_height, y_pos + new_h)
            src_start_y = paste_y - y_pos
            src_end_y = src_start_y + (paste_end_y - paste_y)

            sharp_np = sharp[i].permute(1, 2, 0).numpy()
            bg_arr[paste_y:paste_end_y, :, :] = sharp_np[src_start_y:src_end_y, :, :]

            canvas_list.append(torch.from_numpy(bg_arr))

        result = torch.stack(canvas_list)

        top_zone_height = y_pos
        bottom_zone_start = y_pos + new_h

        return (result, top_zone_height, bottom_zone_start)


# ── Text Overlay v3 ────────────────────────────────────────────────────────

class TextOverlay:
    """Burn text overlays onto video frames.
    v3: TikTok safe zones, bold sans-serif, center-placed quote.

    Safe zones:
      - Top 150px: unsafe (app tabs)
      - Bottom 480px: unsafe (caption bar)
      - Right 120px: unsafe (engagement icons)
      - Safe area: 840x1350px centered
    """

    # Default fonts: bold sans-serif for TikTok readability
    FONT_TITLE = "C:/Windows/Fonts/impact.ttf"
    FONT_BODY = "C:/Windows/Fonts/arialbd.ttf"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "title_text": ("STRING", {"default": "TICK 001", "forceInput": True}),
                "subtitle_text": ("STRING", {"default": "curious", "forceInput": True}),
                "body_text": ("STRING", {"default": "", "multiline": True, "forceInput": True}),
                "title_y": ("INT", {"default": 160, "min": 0, "max": 1920}),
                "body_y": ("INT", {"default": 1400, "min": 0, "max": 1920}),
                "font_size_title": ("INT", {"default": 96, "min": 8, "max": 300}),
                "font_size_subtitle": ("INT", {"default": 40, "min": 8, "max": 200}),
                "font_size_body": ("INT", {"default": 40, "min": 8, "max": 200}),
                "title_color": ("STRING", {"default": "#ffffff"}),
                "subtitle_color": ("STRING", {"default": "#d4922a"}),
                "body_color": ("STRING", {"default": "#ffffff"}),
                "accent_color": ("STRING", {"default": "#e8a830"}),
                "max_body_chars_per_line": ("INT", {"default": 28, "min": 10, "max": 100}),
                "max_body_lines": ("INT", {"default": 4, "min": 1, "max": 30}),
            },
            "optional": {
                "font_path_title": ("STRING", {"default": "C:/Windows/Fonts/impact.ttf"}),
                "font_path_body": ("STRING", {"default": "C:/Windows/Fonts/arialbd.ttf"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "overlay"
    CATEGORY = "Kombucha"

    def overlay(self, images, title_text, subtitle_text, body_text,
                title_y, body_y, font_size_title, font_size_subtitle, font_size_body,
                title_color, subtitle_color, body_color, accent_color,
                max_body_chars_per_line, max_body_lines,
                font_path_title="C:/Windows/Fonts/impact.ttf",
                font_path_body="C:/Windows/Fonts/arialbd.ttf"):

        B, H, W, C = images.shape

        # Load fonts
        def load_font(path, size, fallback_path=None):
            for p in [path, fallback_path, "C:/Windows/Fonts/arialbd.ttf",
                       "C:/Windows/Fonts/arial.ttf"]:
                if p:
                    try:
                        return ImageFont.truetype(p, size)
                    except (OSError, IOError):
                        continue
            return ImageFont.load_default()

        font_title = load_font(font_path_title, font_size_title)
        font_sub = load_font(font_path_body, font_size_subtitle)
        font_body = load_font(font_path_body, font_size_body)

        wrapped = self._wrap_text(body_text, max_body_chars_per_line, max_body_lines)

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Safe zone boundaries
        safe_left = 44
        safe_right = W - 120
        safe_center_x = (safe_left + safe_right) // 2

        # ── Title (inside safe top zone) ──
        if title_text:
            bbox = draw.textbbox((0, 0), title_text, font=font_title)
            tw = bbox[2] - bbox[0]
            tx = safe_center_x - tw // 2
            # Heavy outline for readability over video
            outline_r = 3
            for ox in range(-outline_r, outline_r + 1):
                for oy in range(-outline_r, outline_r + 1):
                    if ox == 0 and oy == 0:
                        continue
                    draw.text((tx + ox, title_y + oy), title_text,
                              fill="#000000", font=font_title)
            draw.text((tx, title_y), title_text, fill=title_color, font=font_title)

        # ── Mood badge (below title) ──
        if subtitle_text:
            sub_y = title_y + font_size_title + 12
            badge_text = subtitle_text.upper()
            bbox = draw.textbbox((0, 0), badge_text, font=font_sub)
            sw = bbox[2] - bbox[0]
            sh = bbox[3] - bbox[1]
            sx = safe_center_x - sw // 2
            pad_x, pad_y = 20, 10
            draw.rounded_rectangle(
                [sx - pad_x, sub_y - pad_y, sx + sw + pad_x, sub_y + sh + pad_y],
                radius=10, fill=subtitle_color
            )
            draw.text((sx, sub_y), badge_text, fill="#0a0a0f", font=font_sub)

        # ── Body quote (below video, in lower blurred zone) ──
        if wrapped:
            line_height = font_size_body + 10
            block_height = len(wrapped) * line_height
            block_top = body_y

            cur_y = block_top
            for line in wrapped:
                bbox = draw.textbbox((0, 0), line, font=font_body)
                lw = bbox[2] - bbox[0]
                lx = safe_center_x - lw // 2
                # Heavy outline for readability over blurred background
                for ox in range(-2, 3):
                    for oy in range(-2, 3):
                        if ox == 0 and oy == 0:
                            continue
                        draw.text((lx + ox, cur_y + oy), line,
                                  fill="#000000", font=font_body)
                draw.text((lx, cur_y), line, fill=body_color, font=font_body)
                cur_y += line_height

        # Composite overlay onto all frames
        overlay_np = np.array(overlay).astype(np.float32) / 255.0
        alpha = overlay_np[:, :, 3:4]
        rgb = overlay_np[:, :, :3]

        rgb_t = torch.from_numpy(rgb).unsqueeze(0).expand(B, -1, -1, -1)
        alpha_t = torch.from_numpy(alpha).unsqueeze(0).expand(B, -1, -1, -1)

        result = images * (1.0 - alpha_t) + rgb_t * alpha_t

        return (result,)

    def _wrap_text(self, text, max_chars, max_lines):
        if not text:
            return []
        words = text.split()
        lines = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 > max_chars:
                lines.append(current)
                current = w
            else:
                current = f"{current} {w}" if current else w
        if current:
            lines.append(current)
        return lines[:max_lines]


# ── Pad To Audio ────────────────────────────────────────────────────────────

class PadToAudio:
    """Ensure video frame count covers the full audio duration.

    Strategy:
    1. If video is already long enough, pass through.
    2. If slowing to min_speed (default 0.8x) covers the audio, duplicate
       frames evenly to stretch the video (smooth slow-mo effect).
    3. If slow-mo alone isn't enough, slow to min_speed AND add held frames
       distributed 40% at the start (hold first frame) and 60% at the end
       (hold last frame).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "audio": ("AUDIO",),
                "frame_rate": ("INT", {"default": 10, "min": 1, "max": 60}),
                "buffer_seconds": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.5}),
                "min_speed": ("FLOAT", {"default": 0.8, "min": 0.3, "max": 1.0, "step": 0.05}),
                "pad_start_ratio": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "pad"
    CATEGORY = "Kombucha"

    def pad(self, images, audio, frame_rate, buffer_seconds, min_speed, pad_start_ratio):
        B, H, W, C = images.shape

        waveform = audio["waveform"]
        sample_rate = audio["sample_rate"]
        audio_duration = waveform.shape[-1] / sample_rate
        required_frames = int((audio_duration + buffer_seconds) * frame_rate)

        if B >= required_frames:
            return (images, audio)

        # How many frames can slow-mo give us?
        max_slowmo_frames = int(B / min_speed)

        if max_slowmo_frames >= required_frames:
            # Slow-mo alone is enough — stretch frames evenly
            result = self._stretch_frames(images, required_frames)
            return (result, audio)

        # Slow-mo to max, then pad the remainder
        stretched = self._stretch_frames(images, max_slowmo_frames)
        remaining = required_frames - max_slowmo_frames

        # Distribute held frames: 40% at start, 60% at end
        pad_start = int(remaining * pad_start_ratio)
        pad_end = remaining - pad_start

        parts = []
        if pad_start > 0:
            parts.append(stretched[:1].expand(pad_start, -1, -1, -1))
        parts.append(stretched)
        if pad_end > 0:
            parts.append(stretched[-1:].expand(pad_end, -1, -1, -1))

        result = torch.cat(parts, dim=0)
        return (result, audio)

    def _stretch_frames(self, images, target_count):
        """Evenly duplicate frames to reach target_count.

        Uses nearest-neighbor sampling from the original frame indices
        to create a smooth slow-motion effect.
        """
        B = images.shape[0]
        if target_count <= B:
            return images[:target_count]

        # Map each output frame to the nearest source frame
        indices = torch.linspace(0, B - 1, target_count).long()
        return images[indices]


# ── Cosy Motes ─────────────────────────────────────────────────────────────

class CosyMotes:
    """Ethereal depth-aware effects for the Kombucha robot videos.

    Features:
      1. Real depth tilt-shift (Depth Anything V2)
      2. Warm bloom on highlights
      3. God rays from brightest light source
      4. Soft vignette
      5. Lifted / hazy shadows (no true blacks)
      6. Depth-aware atmospheric haze
      7. Falling dust motes with escalating wiggle + drift trails
         - Only visible during calm/static scenes
         - Gently fall toward the floor
         - Wiggle increases the longer they exist, starting at 20%
         - Faint directional trail behind each mote
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "tiltshift_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "focus_near": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05}),
                "focus_far": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.05}),
                "bloom_strength": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05}),
                "ray_strength": ("FLOAT", {"default": 120.0, "min": 0.0, "max": 300.0, "step": 10.0}),
                "vignette_strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05}),
                "haze_strength": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.5, "step": 0.02}),
                "shadow_lift": ("FLOAT", {"default": 0.06, "min": 0.0, "max": 0.2, "step": 0.01}),
                "warmth": ("FLOAT", {"default": 1.05, "min": 0.8, "max": 1.3, "step": 0.01}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2**31}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply"
    CATEGORY = "Kombucha"

    @staticmethod
    def _compute_depth(frames_np):
        """Use Depth Anything V2 for real monocular depth."""
        from transformers import pipeline as tf_pipeline
        avg_frame = frames_np.mean(axis=0).astype(np.uint8)
        img = Image.fromarray(avg_frame)
        h, w = avg_frame.shape[:2]
        pipe = tf_pipeline("depth-estimation",
                           model="depth-anything/Depth-Anything-V2-Small-hf",
                           device=0)
        result = pipe(img)
        depth_img = result["depth"].resize((w, h))
        return np.array(depth_img, dtype=np.float32) / 255.0

    @staticmethod
    def _find_interest_points(depth, avg_frame, num_points=6):
        """Find interesting areas at different depths using edge density.
        Returns list of (depth_value, center_x, center_y, interest_score)."""
        from PIL import ImageFilter as IF
        H, W = depth.shape

        # Edge map from average frame
        gray = (0.299 * avg_frame[:, :, 0] + 0.587 * avg_frame[:, :, 1]
                + 0.114 * avg_frame[:, :, 2])
        gray_pil = Image.fromarray(gray.astype(np.uint8))
        edges = np.array(gray_pil.filter(IF.FIND_EDGES), dtype=np.float32)

        # Divide depth into bins, find most interesting region in each
        depth_bins = np.linspace(0, 1, num_points + 2)[1:-1]  # skip extremes
        points = []

        for d_center in depth_bins:
            # Mask for this depth band
            band = 0.12
            mask = ((depth > d_center - band) & (depth < d_center + band)).astype(np.float32)
            if mask.sum() < 100:
                continue

            # Weight edges by depth mask
            weighted = edges * mask

            # Find peak interest region (blur to get smooth peak)
            weighted_pil = Image.fromarray(np.clip(weighted, 0, 255).astype(np.uint8))
            smooth = np.array(weighted_pil.filter(IF.GaussianBlur(radius=20)), dtype=np.float32)

            # Find centroid of top 5% interest
            thresh = np.percentile(smooth[smooth > 0], 95) if (smooth > 0).any() else 1
            hot = smooth >= max(thresh, 1)
            if not hot.any():
                continue

            ys, xs = np.where(hot)
            cy, cx = int(ys.mean()), int(xs.mean())

            # Reject points in the outer 20% edges of the frame
            margin_x = int(W * 0.2)
            margin_y = int(H * 0.2)
            if cx < margin_x or cx > W - margin_x or cy < margin_y or cy > H - margin_y:
                continue

            score = float(smooth[cy, cx])
            actual_depth = float(depth[cy, cx])

            points.append((actual_depth, cx, cy, score))

        # Sort by score descending, keep top points
        points.sort(key=lambda p: p[3], reverse=True)

        # Ensure depth diversity: don't pick two points at similar depths
        filtered = []
        for p in points:
            if not any(abs(p[0] - f[0]) < 0.1 for f in filtered):
                filtered.append(p)
            if len(filtered) >= num_points:
                break

        # Sort by depth (near to far) for nice sweep order
        filtered.sort(key=lambda p: p[0], reverse=True)
        return filtered

    @staticmethod
    def _motion_map(prev, cur, blur_r=15):
        diff = np.abs(cur.astype(np.float32) - prev.astype(np.float32)).mean(axis=2)
        diff_img = Image.fromarray((np.clip(diff * 4, 0, 255)).astype(np.uint8))
        diff_img = diff_img.filter(ImageFilter.GaussianBlur(radius=blur_r))
        return np.array(diff_img, dtype=np.float32) / 255.0

    @staticmethod
    def _find_light_source(luminance):
        col_brightness = np.mean(luminance, axis=0)
        lx = int(np.argmax(col_brightness))
        col_slice = luminance[:, max(0, lx - 20):min(luminance.shape[1], lx + 20)]
        ly = int(np.argmax(np.mean(col_slice, axis=1)))
        return lx, ly

    @staticmethod
    def _make_vignette(H, W, strength):
        """Radial darkening from edges."""
        cy, cx = H / 2, W / 2
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        dist = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)
        dist = dist / dist.max()
        vignette = 1.0 - strength * (dist ** 1.5)
        return np.clip(vignette, 0, 1)

    def apply(self, images, tiltshift_strength, focus_near, focus_far,
              bloom_strength, ray_strength, vignette_strength,
              haze_strength, shadow_lift, warmth, seed):
        import random as _random
        rng = _random.Random(seed)

        B, H, W, C = images.shape
        frames_np = (images.numpy() * 255).clip(0, 255).astype(np.uint8)

        # ── real depth map (once for whole clip) ──────────────────────────
        print("  CosyMotes: computing depth map...")
        depth = self._compute_depth(frames_np)
        focus_width = 0.12

        avg_frame = frames_np.mean(axis=0)
        luminance = (0.299 * avg_frame[:, :, 0]
                     + 0.587 * avg_frame[:, :, 1]
                     + 0.114 * avg_frame[:, :, 2])
        bright_mask = np.clip((luminance - 170) / 70, 0, 1)

        # ── precompute god rays ───────────────────────────────────────────
        ray_layer = np.zeros((H, W), dtype=np.float32)
        if ray_strength > 0:
            lx, ly = self._find_light_source(luminance)
            source_img = np.zeros((H, W), dtype=np.float32)
            ry, rx = min(40, H // 4), min(15, W // 8)
            for dy in range(-ry, ry + 1):
                for dx in range(-rx, rx + 1):
                    ny, nx = ly + dy, lx + dx
                    if 0 <= ny < H and 0 <= nx < W:
                        d = ((dy / max(ry, 1)) ** 2 + (dx / max(rx, 1)) ** 2) ** 0.5
                        if d < 1:
                            source_img[ny, nx] = (1 - d) * bright_mask[ny, nx]
            ray_accum = np.zeros((H, W), dtype=np.float32)
            yy, xx = np.mgrid[0:H, 0:W]
            for step in range(60):
                sc = 1.0 + step * 0.025
                sy = np.clip((ly + (yy - ly) / sc).astype(int), 0, H - 1)
                sx = np.clip((lx + (xx - lx) / sc).astype(int), 0, W - 1)
                ray_accum += source_img[sy, sx] / 60.0
            mx = ray_accum.max()
            if mx > 1e-6:
                ray_accum /= mx
            ray_accum = ray_accum ** 0.6
            ray_pil = Image.fromarray((np.clip(ray_accum, 0, 1) * 255).astype(np.uint8))
            ray_pil = ray_pil.filter(ImageFilter.GaussianBlur(radius=max(1, int(8 * H / 480))))
            ray_layer = np.array(ray_pil, dtype=np.float32) / 255.0

        # ── precompute vignette ───────────────────────────────────────────
        vignette = self._make_vignette(H, W, vignette_strength) if vignette_strength > 0 else None

        # ── precompute haze layer (stronger in background) ────────────────
        haze_layer = None
        if haze_strength > 0:
            # Haze color: warm amber fog
            haze_intensity = (1.0 - depth)  # far = more haze
            haze_intensity = haze_intensity ** 0.7  # soften falloff
            haze_layer = haze_intensity * haze_strength

        # ── find interest points for focus hopping ─────────────────────────
        interest_pts = self._find_interest_points(depth, avg_frame, num_points=6)
        if not interest_pts:
            interest_pts = [(0.5, W // 2, H // 2, 1.0)]
        print(f"  CosyMotes: {len(interest_pts)} focus targets found")
        for ip in interest_pts:
            print(f"    depth={ip[0]:.2f} pos=({ip[1]},{ip[2]}) score={ip[3]:.0f}")

        # Start: wide focus centered (depth 0.5, center of frame)
        # Then hop to interest points with rapid 3-frame sweeps
        total_per_point = max(B // max(len(interest_pts), 1), 10)
        sweep_frames = 8  # rapid sweep
        dwell_frames = total_per_point - sweep_frames

        focus_schedule = []  # (focus_depth, target_x, target_y) per frame
        # Start centered
        current_depth = 0.5
        current_x, current_y = W // 2, H // 2
        pt_idx = 0

        # Initial dwell at center for first ~15% of clip
        center_dwell = max(int(B * 0.15), 8)
        for _ in range(min(center_dwell, B)):
            focus_schedule.append((current_depth, current_x, current_y))

        # Then hop between interest points
        while len(focus_schedule) < B:
            target = interest_pts[pt_idx % len(interest_pts)]
            t_depth, t_x, t_y = target[0], target[1], target[2]

            # Rapid sweep (3 frames)
            for sf in range(sweep_frames):
                if len(focus_schedule) >= B:
                    break
                t = 0.5 - 0.5 * np.cos((sf / max(sweep_frames - 1, 1)) * np.pi)
                fd = current_depth + (t_depth - current_depth) * t
                fx = current_x + (t_x - current_x) * t
                fy = current_y + (t_y - current_y) * t
                focus_schedule.append((fd, int(fx), int(fy)))

            # Dwell
            for _ in range(dwell_frames):
                if len(focus_schedule) >= B:
                    break
                focus_schedule.append((t_depth, t_x, t_y))

            current_depth, current_x, current_y = t_depth, t_x, t_y
            pt_idx += 1

        # ── per-frame processing ──────────────────────────────────────────
        result_frames = []
        prev_frame = None
        print(f"  CosyMotes: processing {B} frames...")

        for fi in range(B):
            frame = frames_np[fi].copy().astype(np.float32)

            # Get focus target for this frame
            focus_depth, focus_x, focus_y = focus_schedule[fi]

            # ── 1. tilt-shift with real depth (75% focus band) ─────────────
            if tiltshift_strength > 0:
                dist_focus = np.abs(depth - focus_depth)
                # 75% of depth range stays sharp: band = 0.375 each side
                bmask = np.clip((dist_focus - 0.375) / 0.2, 0, 1) * tiltshift_strength
                frame_pil = Image.fromarray(frame.astype(np.uint8))
                blur_lvls = []
                for r in [1, 3, 7, 12]:
                    blur_lvls.append(np.array(
                        frame_pil.filter(ImageFilter.GaussianBlur(radius=r)),
                        dtype=np.float32))
                blurred = frame.copy()
                for i, th in enumerate([0.15, 0.35, 0.6, 0.85]):
                    m3 = np.expand_dims(np.clip((bmask - th) / 0.2, 0, 1), 2)
                    blurred = blurred * (1 - m3) + blur_lvls[i] * m3
                frame = blurred

            # ── 2. bloom ──────────────────────────────────────────────────
            if bloom_strength > 0:
                f_lum = (0.299 * frame[:, :, 0] + 0.587 * frame[:, :, 1]
                         + 0.114 * frame[:, :, 2])
                bm = np.clip((f_lum - 170) / 70, 0, 1)
                bl = frame * np.expand_dims(bm, 2)
                bl_img = Image.fromarray(bl.astype(np.uint8)).filter(
                    ImageFilter.GaussianBlur(radius=max(1, int(25 * H / 480))))
                bl_arr = np.array(bl_img, dtype=np.float32)
                bl_arr[:, :, 0] *= 1.08
                bl_arr[:, :, 2] *= 0.9
                frame = np.clip(frame + bl_arr * bloom_strength, 0, 255)

            # ── 3. god rays ───────────────────────────────────────────────
            if ray_strength > 0:
                for c, mult in enumerate([1.2, 0.9, 0.45]):
                    frame[:, :, c] = np.clip(
                        frame[:, :, c] + ray_layer * ray_strength * mult, 0, 255)

            # ── 4. vignette ───────────────────────────────────────────────
            if vignette is not None:
                frame *= np.expand_dims(vignette, 2)

            # ── 5. shadow lift (no true blacks) ───────────────────────────
            if shadow_lift > 0:
                lift_val = shadow_lift * 255
                # Warm lift: more red/amber in the shadows
                frame[:, :, 0] = np.clip(frame[:, :, 0] + lift_val * 1.2, 0, 255)
                frame[:, :, 1] = np.clip(frame[:, :, 1] + lift_val * 0.9, 0, 255)
                frame[:, :, 2] = np.clip(frame[:, :, 2] + lift_val * 0.6, 0, 255)

            # ── 6. depth haze ─────────────────────────────────────────────
            if haze_layer is not None:
                haze_color = np.array([220, 190, 150], dtype=np.float32)
                for c in range(3):
                    frame[:, :, c] = frame[:, :, c] * (1 - haze_layer) + haze_color[c] * haze_layer

            # ── motion detection ──────────────────────────────────────────
            cur_small = frames_np[fi]
            if prev_frame is not None:
                mmap = self._motion_map(prev_frame, cur_small)
                global_motion = float(mmap.mean())
            else:
                mmap = np.zeros((H, W), dtype=np.float32)
                global_motion = 0.0
            prev_frame = cur_small

            # Overlay visibility: fades with motion
            overlay_visibility = np.clip(1.0 - (global_motion - 0.03) / 0.09, 0, 1)

            # ── warm grade ────────────────────────────────────────────────
            if warmth != 1.0:
                frame[:, :, 0] = np.clip(frame[:, :, 0] * warmth, 0, 255)
                frame[:, :, 2] = np.clip(frame[:, :, 2] * (2 - warmth), 0, 255)

            # ── 8. focus reticle: 1 circle + crosshair, 20% alpha ─────────
            if overlay_visibility > 0.01:
                depth_at_focus = depth[
                    min(max(focus_y, 0), H - 1),
                    min(max(focus_x, 0), W - 1)]
                size_scale = 0.3 + 0.7 * depth_at_focus
                ring_r = max(16, int(H * 0.12 * size_scale))

                # Pulse: sinusoidal between 10% and 30%, ~1.5s cycle
                pulse = 0.5 + 0.5 * np.sin(fi * 2 * np.pi / 22)  # ~22 frames per cycle at 15fps
                alpha = (0.10 + 0.20 * pulse) * overlay_visibility
                green = np.array([0, 255, 0], dtype=np.float32)

                # Single 1px circle
                num_pts = max(40, int(ring_r * 5))
                for step in range(num_pts):
                    a = step / num_pts * 2 * np.pi
                    rx = int(focus_x + ring_r * np.cos(a))
                    ry = int(focus_y + ring_r * np.sin(a))
                    if 0 <= rx < W and 0 <= ry < H:
                        for c in range(3):
                            frame[ry, rx, c] = (
                                frame[ry, rx, c] * (1 - alpha)
                                + green[c] * alpha)

                # 1px crosshair spanning the circle
                for dx in range(-ring_r, ring_r + 1):
                    px = focus_x + dx
                    if 0 <= px < W and 0 <= focus_y < H:
                        for c in range(3):
                            frame[focus_y, px, c] = (
                                frame[focus_y, px, c] * (1 - alpha)
                                + green[c] * alpha)
                for dy in range(-ring_r, ring_r + 1):
                    py = focus_y + dy
                    if 0 <= py < H and 0 <= focus_x < W:
                        for c in range(3):
                            frame[py, focus_x, c] = (
                                frame[py, focus_x, c] * (1 - alpha)
                                + green[c] * alpha)

            result_frames.append(torch.from_numpy(
                np.clip(frame, 0, 255) / 255.0).float())

        return (torch.stack(result_frames),)


# ── Node Registration ──────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "ParseTickLog": ParseTickLog,
    "ElevenLabsTTS": ElevenLabsTTS,
    "MotionClip": MotionClip,
    "VerticalFrameComposite": VerticalFrameComposite,
    "CosyMotes": CosyMotes,
    "TextOverlay": TextOverlay,
    "PadToAudio": PadToAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ParseTickLog": "Parse Tick Log (Kombucha)",
    "ElevenLabsTTS": "ElevenLabs TTS (Direct)",
    "MotionClip": "Motion Clip (Kombucha)",
    "VerticalFrameComposite": "Vertical Frame Composite",
    "CosyMotes": "Cosy Motes (Kombucha)",
    "TextOverlay": "Text Overlay (Kombucha)",
    "PadToAudio": "Pad Video to Audio (Kombucha)",
}
