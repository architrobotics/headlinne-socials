"""Font loading and text-fitting helpers for the carousel renderer.

Titles and headlines use Anton (a free, condensed, Impact-like face). Body text
uses Inter as a variable font, where we set the optical-size and weight axes
explicitly. If a bundled font is missing for any reason we fall back to DejaVu
so rendering never hard-fails.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PIL import ImageDraw, ImageFont

from ..config import FONTS_DIR
from ..logging_setup import get_logger

log = get_logger("render.fonts")

ANTON_PATH = FONTS_DIR / "Anton-Regular.ttf"
INTER_PATH = FONTS_DIR / "Inter-Variable.ttf"

# System fallbacks (present on the GitHub Ubuntu runners and in this sandbox).
_DEJAVU_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

# Inter variable axis ranges (verified): opsz 14..32, wght 100..900.
_OPSZ_MIN, _OPSZ_MAX = 14.0, 32.0
_WGHT_MIN, _WGHT_MAX = 100.0, 900.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@lru_cache(maxsize=256)
def title_font(size: int) -> ImageFont.FreeTypeFont:
    """Anton at the given pixel size (falls back to DejaVu Bold)."""
    try:
        if ANTON_PATH.exists():
            return ImageFont.truetype(str(ANTON_PATH), size)
    except Exception as exc:  # pragma: no cover
        log.warning("Anton load failed (%s), using DejaVu Bold.", exc)
    return ImageFont.truetype(str(_DEJAVU_BOLD), size)


@lru_cache(maxsize=512)
def body_font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Inter variable at a given size and weight (falls back to DejaVu).

    The optical-size axis is set proportional to the pixel size but clamped to
    the face's supported range. Both axes must be provided together.
    """
    try:
        if INTER_PATH.exists():
            font = ImageFont.truetype(str(INTER_PATH), size)
            opsz = _clamp(float(size), _OPSZ_MIN, _OPSZ_MAX)
            wght = _clamp(float(weight), _WGHT_MIN, _WGHT_MAX)
            try:
                font.set_variation_by_axes([opsz, wght])
            except Exception as exc:  # pragma: no cover
                log.warning("Inter axis set failed (%s), using default instance.", exc)
            return font
    except Exception as exc:  # pragma: no cover
        log.warning("Inter load failed (%s), using DejaVu.", exc)
    return ImageFont.truetype(str(_DEJAVU), size)


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def line_height(font: ImageFont.FreeTypeFont) -> int:
    asc, desc = font.getmetrics()
    return asc + desc


def wrap_text(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> list[str]:
    """Greedy word wrap to a pixel width. Long single words are hard-split."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if text_width(font, trial) <= max_width or not current:
            # If a single word is itself too wide, break it by characters.
            if not current and text_width(font, word) > max_width:
                lines.extend(_hard_split(font, word, max_width))
                current = ""
                continue
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _hard_split(font: ImageFont.FreeTypeFont, word: str, max_width: int) -> list[str]:
    chunks: list[str] = []
    chunk = ""
    for ch in word:
        if text_width(font, chunk + ch) <= max_width or not chunk:
            chunk += ch
        else:
            chunks.append(chunk)
            chunk = ch
    if chunk:
        chunks.append(chunk)
    return chunks


def fit_block(
    loader,
    text: str,
    *,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
    weight: int | None = None,
    line_spacing: float = 1.12,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Shrink a font until wrapped `text` fits within max_width x max_height.

    `loader` is a callable taking a size (and optional weight) and returning a
    font. Returns the chosen font, the wrapped lines, and the total block height.
    """
    size = start_size
    while size >= min_size:
        font = loader(size, weight) if weight is not None else loader(size)
        lines = wrap_text(font, text, max_width)
        total = int(len(lines) * line_height(font) * line_spacing)
        if total <= max_height:
            return font, lines, total
        size -= 2
    font = loader(min_size, weight) if weight is not None else loader(min_size)
    lines = wrap_text(font, text, max_width)
    total = int(len(lines) * line_height(font) * line_spacing)
    return font, lines, total


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: Iterable[str],
    font: ImageFont.FreeTypeFont,
    *,
    x: int,
    y: int,
    fill,
    line_spacing: float = 1.12,
    align: str = "left",
    max_width: int | None = None,
) -> int:
    """Draw wrapped lines from a top y, returning the y after the last line."""
    lh = int(line_height(font) * line_spacing)
    cy = y
    for line in lines:
        lx = x
        if align in ("center", "right") and max_width is not None:
            w = text_width(font, line)
            if align == "center":
                lx = x + (max_width - w) // 2
            else:
                lx = x + (max_width - w)
        draw.text((lx, cy), line, font=font, fill=fill)
        cy += lh
    return cy
