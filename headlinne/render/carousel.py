"""Render Instagram carousel slides to PNG files with Pillow.

Three slide kinds:
  - cover: article image background, dark gradient rising from the bottom, a big
    Anton title in the category colour. For Geopolitics the word "Geo" is painted
    with a US-flag pattern and the rest stays white.
  - story: article image background, gradient up the lower part, a bold headline
    and a shorter explanation.
  - cta: black background, the Headlinne logo, and a large call to action.

Backgrounds come from the article image URL when available. If an image cannot be
loaded we fall back to a clean branded gradient so a slide is never empty.
"""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

from ..config import (CATEGORY_COLORS, LOGO_PATH, SLIDE_H, SLIDE_W, WEBSITE)
from ..logging_setup import get_logger
from ..models import InstagramCarousel, Slide
from . import fonts
from .flag_text import render_flag_text

log = get_logger("render.carousel")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

MARGIN = 72
BOTTOM_MARGIN = 96
BRAND_TERRACOTTA = (199, 106, 68)
WHITE = (255, 255, 255, 255)


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _scale(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Image loading
# --------------------------------------------------------------------------- #
# A featured image whose smaller side is under this many pixels would look
# blurry blown up to a full slide, so we use a clean gradient instead.
_MIN_SOURCE_PX = 360

# When fetching a remote background, ask the CDN for one of these widths in
# order (largest first). Different hosts support different sizes, so trying a
# ladder lands the biggest one a given host actually serves instead of 404ing on
# a single guess. The original URL is the final fallback.
_UPGRADE_WIDTHS = (2048, 1536, 1024)


def _upgrade_candidates(url: str) -> list[str]:
    """Ordered higher-resolution variants of a thumbnail URL, largest first.

    Handles WordPress-style dimension suffixes, BBC ichef width segments, and
    common width / resize query parameters. Returns only URLs that actually
    differ from the original; the loader tries each and falls back to the
    original, so an over-eager rewrite can never lose an image.
    """
    if not url:
        return []
    candidates: list[str] = []
    # WordPress / many CMSs: "photo-1024x576.jpg" -> "photo.jpg" (the original,
    # full-resolution file). Worth trying first when present.
    stripped = re.sub(r"-\d{2,4}x\d{2,4}(?=\.(?:jpg|jpeg|png|webp)\b)", "", url, flags=re.I)
    if stripped != url:
        candidates.append(stripped)

    for target in _UPGRADE_WIDTHS:
        u = url
        # BBC ichef: ".../news/240/cpsprodpb/..." -> bump the width segment.
        u = re.sub(r"(/)(\d{2,4})(/cpsprodpb/)",
                   lambda m, t=target: m.group(1) + str(max(int(m.group(2)), t)) + m.group(3), u)
        # Query width hints: width=, w=, maxwidth=
        u = re.sub(r"(?i)([?&](?:width|w|maxwidth)=)(\d{2,4})",
                   lambda m, t=target: m.group(1) + str(max(int(m.group(2)), t)), u)

        # resize=W,H or fit=W,H -> scale up keeping the aspect ratio.
        def _pair(m, t=target):
            w_, h_ = int(m.group(2)), int(m.group(3))
            if w_ >= t:
                return m.group(0)
            return f"{m.group(1)}{t},{int(h_ * t / w_)}"

        u = re.sub(r"(?i)([?&](?:resize|fit)=)(\d{2,4}),(\d{2,4})", _pair, u)
        if u != url and u not in candidates:
            candidates.append(u)
    return candidates


def _fetch_image(url: str) -> Optional[Image.Image]:
    try:
        if url.startswith("http://") or url.startswith("https://"):
            import requests  # local import so tests do not need network

            resp = requests.get(url, timeout=12, headers={"User-Agent": "Headlinne/1.0"})
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGBA")
        path = Path(url)
        if path.exists():
            return Image.open(path).convert("RGBA")
    except Exception as exc:  # pragma: no cover - network/IO best-effort
        log.warning("Background load failed for %s: %s", str(url)[:80], exc)
    return None


def default_image_loader(src: Optional[str]) -> Optional[Image.Image]:
    """Load a background from an http(s) URL or a local file path.

    For remote images it tries progressively-sized higher-resolution variants of
    the URL (largest first) and falls back to the original, so backgrounds come
    out as sharp as the source host allows.
    """
    if not src:
        return None
    if src.startswith("http://") or src.startswith("https://"):
        for candidate in _upgrade_candidates(src):
            img = _fetch_image(candidate)
            if img is not None:
                return img
        return _fetch_image(src)
    return _fetch_image(src)


# --------------------------------------------------------------------------- #
# Background builders
# --------------------------------------------------------------------------- #
def _cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale and centre-crop an image to exactly w x h (cover fit), then sharpen
    to counteract softness from scaling. Upscaled images get a firmer pass."""
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    img = img.resize(new, Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    img = img.crop((left, top, left + w, top + h))
    if scale > 1.05:  # had to enlarge: sharpen harder to recover crispness
        img = img.filter(ImageFilter.UnsharpMask(radius=2.2, percent=135, threshold=2))
    else:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=75, threshold=3))
    return img.convert("RGBA")


def _vertical_gradient(w: int, h: int, top_rgb, bottom_rgb) -> Image.Image:
    """A full-size vertical gradient between two RGB colours."""
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_rgb[0] + (bottom_rgb[0] - top_rgb[0]) * t)
        g = int(top_rgb[1] + (bottom_rgb[1] - top_rgb[1]) * t)
        b = int(top_rgb[2] + (bottom_rgb[2] - top_rgb[2]) * t)
        col.putpixel((0, y), (r, g, b))
    return col.resize((w, h)).convert("RGBA")


def _fallback_bg(category: str, seed: str) -> Image.Image:
    """A branded gradient used when no article image is available."""
    base = _hex_to_rgb(CATEGORY_COLORS.get(category, "#333333"))
    if category == "Geopolitics":  # white category colour, pick a neutral slate
        base = (70, 84, 110)
    # Slight per-slide variation so consecutive fallbacks are not identical.
    jitter = (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 16) - 8
    top = _scale(base, 0.42)
    top = tuple(max(0, min(255, c + jitter)) for c in top)
    bottom = _scale(base, 0.12)
    return _vertical_gradient(SLIDE_W, SLIDE_H, top, bottom)


def _bottom_gradient(w: int, h: int, band_frac: float, max_alpha: int) -> Image.Image:
    """Black overlay whose alpha ramps from max_alpha at the bottom to 0 at the
    top of a band covering `band_frac` of the height."""
    band = max(1, int(h * band_frac))
    alpha = Image.new("L", (1, h), 0)
    for y in range(h):
        dist_from_bottom = h - 1 - y
        if dist_from_bottom <= band:
            a = int(max_alpha * (1 - dist_from_bottom / band))
        else:
            a = 0
        alpha.putpixel((0, y), a)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    overlay.putalpha(alpha.resize((w, h)))
    return overlay


def _background_for(slide: Slide, category: str, loader: ImageLoader) -> Image.Image:
    img = loader(slide.image_url)
    if img is not None and min(img.size) >= _MIN_SOURCE_PX:
        try:
            return _cover_fit(img, SLIDE_W, SLIDE_H)
        except Exception as exc:  # pragma: no cover
            log.warning("cover-fit failed: %s", exc)
    elif img is not None:
        log.info("background %dx%d too small for a sharp slide, using gradient",
                 img.size[0], img.size[1])
    return _fallback_bg(category, slide.headline or category)


# --------------------------------------------------------------------------- #
# Slide renderers
# --------------------------------------------------------------------------- #
def _render_cover(slide: Slide, category: str, loader: ImageLoader) -> Image.Image:
    canvas = _background_for(slide, category, loader)
    canvas.alpha_composite(_bottom_gradient(SLIDE_W, SLIDE_H, 0.62, 238))
    draw = ImageDraw.Draw(canvas)

    max_w = SLIDE_W - 2 * MARGIN
    max_h = int(SLIDE_H * 0.42)
    font, lines, total_h = fonts.fit_block(
        fonts.title_font, slide.headline,
        max_width=max_w, max_height=max_h, start_size=128, min_size=64,
    )

    colour = _hex_to_rgb(CATEGORY_COLORS.get(category, "#FFFFFF"))
    is_geo = category == "Geopolitics"
    y = SLIDE_H - BOTTOM_MARGIN - total_h
    lh = int(fonts.line_height(font) * 1.12)

    for line in lines:
        if is_geo and "Geo" in line:
            _draw_geo_line(canvas, draw, line, font, MARGIN, y)
        else:
            draw.text((MARGIN, y), line, font=font, fill=colour + (255,))
        y += lh
    return canvas


def _draw_geo_line(canvas: Image.Image, draw: ImageDraw.ImageDraw, line: str,
                   font, x: int, y: int) -> None:
    """Draw a cover line where the substring 'Geo' is flag-filled and the rest
    is white."""
    # Whole line white first.
    draw.text((x, y), line, font=font, fill=WHITE)
    idx = line.find("Geo")
    if idx < 0:
        return
    prefix = line[:idx]
    x_geo = x + fonts.text_width(font, prefix) if prefix else x
    geo_bbox = font.getbbox("Geo")
    flag_img = render_flag_text("Geo", font, pad=6)
    paste_x = int(x_geo + geo_bbox[0] - 6)
    paste_y = int(y + geo_bbox[1] - 6)
    canvas.alpha_composite(flag_img, (max(0, paste_x), max(0, paste_y)))


def _render_story(slide: Slide, category: str, loader: ImageLoader) -> Image.Image:
    canvas = _background_for(slide, category, loader)
    canvas.alpha_composite(_bottom_gradient(SLIDE_W, SLIDE_H, 0.58, 242))
    draw = ImageDraw.Draw(canvas)

    max_w = SLIDE_W - 2 * MARGIN
    accent = _hex_to_rgb(CATEGORY_COLORS.get(category, "#FFFFFF"))

    head_font, head_lines, head_h = fonts.fit_block(
        fonts.title_font, slide.headline,
        max_width=max_w, max_height=int(SLIDE_H * 0.30), start_size=96, min_size=52,
    )
    exp_font, exp_lines, exp_h = fonts.fit_block(
        fonts.body_font, slide.explanation or "",
        max_width=max_w, max_height=int(SLIDE_H * 0.24),
        start_size=46, min_size=30, weight=400,
    )

    gap = 26
    accent_h = 8
    accent_gap = 22
    total = accent_h + accent_gap + head_h + (gap + exp_h if exp_lines and exp_lines != [""] else 0)
    start_y = SLIDE_H - BOTTOM_MARGIN - total

    # Category accent bar.
    if category == "Geopolitics":
        accent = (220, 60, 60)  # readable bar instead of white-on-light
    draw.rectangle([MARGIN, start_y, MARGIN + 84, start_y + accent_h], fill=accent + (255,))
    y = start_y + accent_h + accent_gap

    y = fonts.draw_lines(draw, head_lines, head_font, x=MARGIN, y=y, fill=WHITE,
                         line_spacing=1.08)
    if exp_lines and exp_lines != [""]:
        y += gap - int(fonts.line_height(head_font) * 0.0)
        fonts.draw_lines(draw, exp_lines, exp_font, x=MARGIN, y=y,
                         fill=(235, 235, 235, 255), line_spacing=1.16)
    return canvas


def _render_cta(slide: Slide) -> Image.Image:
    canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)

    # Logo, centred in the upper-middle.
    logo_bottom = int(SLIDE_H * 0.46)
    try:
        if LOGO_PATH.exists():
            logo = Image.open(LOGO_PATH).convert("RGBA")
            target = 360
            logo = logo.resize((target, target), Image.LANCZOS)
            lx = (SLIDE_W - target) // 2
            ly = int(SLIDE_H * 0.20)
            canvas.alpha_composite(logo, (lx, ly))
            logo_bottom = ly + target
    except Exception as exc:  # pragma: no cover
        log.warning("logo render failed: %s", exc)

    # CTA text, centred below the logo.
    text = slide.headline or f"Stay ahead with {WEBSITE}"
    max_w = SLIDE_W - 2 * MARGIN
    font, lines, total_h = fonts.fit_block(
        fonts.title_font, text,
        max_width=max_w, max_height=int(SLIDE_H * 0.26), start_size=92, min_size=52,
    )
    y = logo_bottom + 90
    lh = int(fonts.line_height(font) * 1.1)
    for line in lines:
        # Colour the website part in brand terracotta where it appears.
        _draw_centered_with_brand(draw, line, font, y, max_w)
        y += lh
    return canvas


def _draw_centered_with_brand(draw: ImageDraw.ImageDraw, line: str, font, y: int,
                              max_w: int) -> None:
    """Centre a line, painting any occurrence of the website in brand colour."""
    full_w = fonts.text_width(font, line)
    x = MARGIN + (max_w - full_w) // 2
    token = WEBSITE
    if token in line:
        before, after = line.split(token, 1)
        draw.text((x, y), before, font=font, fill=WHITE)
        x += fonts.text_width(font, before)
        draw.text((x, y), token, font=font, fill=BRAND_TERRACOTTA + (255,))
        x += fonts.text_width(font, token)
        draw.text((x, y), after, font=font, fill=WHITE)
    else:
        draw.text((x, y), line, font=font, fill=WHITE)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render_carousel(carousel: InstagramCarousel, out_dir: Path,
                    image_loader: ImageLoader | None = None) -> list[Path]:
    """Render every slide to a PNG, returning the file paths in order.

    `out_dir` is created if needed. File names are slide_1.png, slide_2.png, ...
    and each slide's `image_file` is set to the path relative to the day folder's
    parent (so it can be committed and later turned into a public URL).
    """
    loader = image_loader or default_image_loader
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    category = carousel.category

    for i, slide in enumerate(carousel.slides, 1):
        if slide.role == "cover":
            img = _render_cover(slide, category, loader)
        elif slide.role == "cta":
            img = _render_cta(slide)
        else:
            img = _render_story(slide, category, loader)

        path = out_dir / f"slide_{i}.png"
        img.convert("RGB").save(path, "PNG")
        slide.image_file = str(path)
        paths.append(path)
        log.info("rendered %s", path.name)

    return paths
