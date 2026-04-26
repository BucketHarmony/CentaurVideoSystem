"""MPC brand chrome rendering (PIL only, no MoviePy).

A `ChromeRenderer` holds the palette + layout + font paths and renders
the per-beat chrome (banner + proof chip) and CTA card to RGBA numpy
arrays. Per-call arguments are content (chip label, headline, etc.) so
the renderer is reused across all 8 reels.

Layout constants live in `Layout`. Defaults match the canonical 1080x1920
layout used by the MPC reel suite.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PathLike = Union[str, Path]
RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]


@dataclass(frozen=True)
class Layout:
    W: int = 1080
    H: int = 1920
    BANNER_H: int = 140
    WELL_TOP: int = 140
    WELL_H: int = 1610
    CAPTION_BOTTOM: int = 1620
    CHIP_Y: int = 168
    CTA_CHROME_BOTTOM: int = 720
    CTA_WELL_TOP: int = 720

    @property
    def CTA_WELL_H(self) -> int:
        return self.H - self.CTA_WELL_TOP


def load_palette(palette_path: PathLike) -> dict:
    """Read mpc/brand/palette.json and return the parsed dict."""
    return json.loads(Path(palette_path).read_text(encoding="utf-8"))


def palette_colors(palette: dict) -> dict:
    """Extract `{name: (r,g,b)}` from the palette dict."""
    return {name: tuple(meta["rgb"]) for name, meta in palette["colors"].items()}


# --------------------------------------------------------------------------- #
# PIL helpers — exposed because callers (caption strip, custom chrome)
# need them too.
# --------------------------------------------------------------------------- #

def font(font_path: PathLike, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path), size)


def text_size(draw: ImageDraw.ImageDraw, txt: str, fnt) -> Tuple[int, int]:
    l, t, r, b = draw.textbbox((0, 0), txt, font=fnt)
    return r - l, b - t


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if text_size(draw, trial, fnt)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def gradient_bg(c1: RGB, c2: RGB, *, W: int, H: int, angle_deg: float = 135.0) -> np.ndarray:
    """Linear gradient between two RGB endpoints, returned as (H, W, 3) uint8."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    proj = xx * dx + yy * dy
    proj = (proj - proj.min()) / (proj.max() - proj.min())
    img = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(3):
        img[..., i] = (c1[i] * (1 - proj) + c2[i] * proj).astype(np.uint8)
    return img


def measure_text_bbox(draw, text, fnt, x_center, top):
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    w, h = r - l, b - t
    draw_x = x_center - w // 2 - l
    draw_y = top - t
    return (draw_x + l, draw_y + t, draw_x + r, draw_y + b), draw_x, draw_y


def draw_centered_text(draw, text, fnt, x_center, top, fill,
                       shadow_offset=None, shadow_color=(0, 0, 0, 200)):
    bbox, dx, dy = measure_text_bbox(draw, text, fnt, x_center, top)
    if shadow_offset:
        sx, sy = shadow_offset
        draw.text((dx + sx, dy + sy), text, font=fnt, fill=shadow_color)
        bbox = (bbox[0], bbox[1], bbox[2] + max(sx, 0), bbox[3] + max(sy, 0))
    draw.text((dx, dy), text, font=fnt, fill=fill)
    return bbox


# --------------------------------------------------------------------------- #
# Chrome renderer
# --------------------------------------------------------------------------- #

class ChromeRenderer:
    """Per-reel chrome renderer.

    Stateless except for palette/layout/font/logo paths.
    """

    def __init__(
        self, *,
        palette: dict,
        font_headline: PathLike,
        font_body: PathLike,
        logo_path: PathLike,
        layout: Layout = Layout(),
    ):
        self.palette = palette
        self.colors = palette_colors(palette)
        self.font_headline = str(font_headline)
        self.font_body = str(font_body)
        self.logo_path = str(logo_path)
        self.layout = layout

    # ----- font helper ----- #

    def font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        return font(self.font_headline if bold else self.font_body, size)

    # ----- primitives ----- #

    def draw_top_banner(self, img: Image.Image, *, banner_h: Optional[int] = None,
                        target_w: int = 560) -> None:
        L = self.layout
        banner_h = L.BANNER_H if banner_h is None else banner_h
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rectangle((0, 0, L.W, banner_h), fill=(*self.colors["white"], 255))
        logo = Image.open(self.logo_path).convert("RGBA")
        ratio = target_w / logo.width
        new_h = int(logo.height * ratio)
        logo = logo.resize((target_w, new_h), Image.LANCZOS)
        img.paste(logo, ((L.W - target_w) // 2, (banner_h - new_h) // 2), logo)

    def draw_proof_chip(self, img: Image.Image, label: str,
                        chip_color: Optional[RGB] = None) -> None:
        L = self.layout
        if chip_color is None:
            chip_color = self.colors["deep_magenta"]
        draw = ImageDraw.Draw(img, "RGBA")
        fnt = self.font(38, bold=True)
        l, t, r, b = draw.textbbox((0, 0), label, font=fnt)
        tw, th = r - l, b - t
        pad_x, pad_y = 32, 16
        pill_w, pill_h = tw + pad_x * 2, th + pad_y * 2
        x = (L.W - pill_w) // 2
        y = L.CHIP_Y
        draw.rounded_rectangle((x, y, x + pill_w, y + pill_h),
                               radius=pill_h // 2, fill=(*chip_color, 240))
        draw.text((x + pad_x - l, y + pad_y - t),
                  label, font=fnt, fill=(*self.colors["white"], 255))

    def draw_well(self, img: Image.Image, *,
                  well_top: Optional[int] = None,
                  well_h: Optional[int] = None,
                  transparent: bool = True,
                  c_top: RGB = (40, 30, 50),
                  c_bot: RGB = (15, 10, 20)) -> None:
        L = self.layout
        well_top = L.WELL_TOP if well_top is None else well_top
        well_h = L.WELL_H if well_h is None else well_h
        if transparent:
            well = np.zeros((well_h, L.W, 4), dtype=np.uint8)
            img.paste(Image.fromarray(well, "RGBA"), (0, well_top))
            return
        well = np.zeros((well_h, L.W, 4), dtype=np.uint8)
        for i in range(well_h):
            t = i / max(1, well_h - 1)
            well[i, :, 0] = int(c_top[0] * (1 - t) + c_bot[0] * t)
            well[i, :, 1] = int(c_top[1] * (1 - t) + c_bot[1] * t)
            well[i, :, 2] = int(c_top[2] * (1 - t) + c_bot[2] * t)
            well[i, :, 3] = 255
        img.paste(Image.fromarray(well, "RGBA"), (0, well_top))

    # ----- composed renders ----- #

    def render_beat(self, *, chip_label: Optional[str] = None,
                    chip_color: Optional[RGB] = None,
                    well_transparent: bool = True) -> np.ndarray:
        """Standard beat chrome: dark BG + transparent well + top banner +
        optional proof chip. Returns (H, W, 4) uint8."""
        L = self.layout
        img = Image.new("RGBA", (L.W, L.H), (*self.colors["near_black"], 255))
        self.draw_well(img, transparent=well_transparent)
        self.draw_top_banner(img)
        if chip_label:
            self.draw_proof_chip(img, chip_label, chip_color=chip_color)
        return np.array(img)

    def render_cta(self, *,
                   headline: str,
                   subhead: str,
                   url: str,
                   handle_line: str = "Link in bio  •  @michiganprogressive",
                   well_transparent: bool = True,
                   gradient_angle: float = 300.0,
                   headline_size: int = 96,
                   subhead_size: int = 44,
                   url_size: int = 28,
                   handle_size: int = 32) -> np.ndarray:
        """CTA chrome: gradient top half + logo bar + headline/subhead/URL +
        handle. Bottom half is the well (transparent or tinted)."""
        L = self.layout
        bg_full = gradient_bg(self.colors["sky_blue"], self.colors["soft_pink"],
                              W=L.W, H=L.H, angle_deg=gradient_angle)
        bg_full[L.CTA_CHROME_BOTTOM:, :, :] = 0
        img = Image.fromarray(bg_full).convert("RGBA")

        if well_transparent:
            bot = np.zeros((L.CTA_WELL_H, L.W, 4), dtype=np.uint8)
            img.paste(Image.fromarray(bot, "RGBA"), (0, L.CTA_WELL_TOP))
        else:
            tint = np.zeros((L.CTA_WELL_H, L.W, 4), dtype=np.uint8)
            tint[..., :3] = (40, 30, 50)
            tint[..., 3] = 255
            img.paste(Image.fromarray(tint, "RGBA"), (0, L.CTA_WELL_TOP))

        draw = ImageDraw.Draw(img, "RGBA")

        logo = Image.open(self.logo_path).convert("RGBA")
        target_w = 720
        ratio = target_w / logo.width
        new_h = int(logo.height * ratio)
        logo = logo.resize((target_w, new_h), Image.LANCZOS)
        bar_y = 60
        pad = 36
        bar_top = bar_y - pad
        bar_bot = bar_y + new_h + pad
        bar = Image.new("RGBA", (L.W, new_h + pad * 2), (*self.colors["white"], 255))
        img.paste(bar, (0, bar_top), bar)
        img.paste(logo, ((L.W - target_w) // 2, bar_y), logo)

        tag_top = bar_bot + 22
        tag_bbox = draw_centered_text(
            draw, headline, self.font(headline_size, bold=True), L.W // 2, tag_top,
            fill=(*self.colors["white"], 255),
            shadow_offset=(4, 4),
            shadow_color=(*self.colors["deep_magenta"], 240))

        sub_top = tag_bbox[3] + 16
        sub_bbox = draw_centered_text(
            draw, subhead, self.font(subhead_size, bold=True), L.W // 2, sub_top,
            fill=(*self.colors["white"], 255))

        url_fnt = self.font(url_size, bold=True)
        ul, ut, ur, ub = draw.textbbox((0, 0), url, font=url_fnt)
        url_tw, url_th = ur - ul, ub - ut
        plate_w = url_tw + 70
        plate_h = url_th + 40
        plate_x = (L.W - plate_w) // 2
        plate_y = sub_bbox[3] + 18
        draw.rounded_rectangle((plate_x, plate_y, plate_x + plate_w, plate_y + plate_h),
                               radius=20, fill=(*self.colors["white"], 250))
        draw.text((plate_x + 35 - ul, plate_y + 20 - ut),
                  url, font=url_fnt, fill=(*self.colors["deep_magenta"], 255))

        handle_top = plate_y + plate_h + 18
        draw_centered_text(
            draw, handle_line,
            self.font(handle_size, bold=False), L.W // 2, handle_top,
            fill=(*self.colors["white"], 255))

        return np.array(img)
