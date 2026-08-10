"""Animated explanatory graphics for reels.

An explainer that is only text on photos is a slideshow with ambition. What
makes a short video feel *authored* is that the idea gets its own picture: a
comparison drawn as two bars, a mechanism drawn as a chain, a contrast drawn as
a split screen. That is what this module provides.

Each device is a pure function of progress, so it composes with the rest of the
motion engine and can be dropped into any beat. They are drawn from the same
palette and furniture as everything else, so a graphic reads as part of the
brand rather than as a chart pasted onto it.

Design rule that matters: a device either prints a number or it does not.
`flow`, `split` and `timeline` are label-only and can carry any idea safely.
`bars` and `counter` print figures, so the generator only ever feeds them
numbers it has verified against the source material (see generate/reel.py).
Bar *heights* are a separate, softer claim about relative size, which is why a
bar can show direction without printing a statistic.
"""

from __future__ import annotations

import re

from PIL import Image, ImageDraw

from . import fonts, theme
from .motion import (clamp01, ease_out_back, ease_out_cubic, ease_out_quint,
                     window)

# The five devices the generator may choose from.
DEVICES = ("bars", "counter", "flow", "timeline", "split")

# Devices that never print a figure, so they are always safe for material with
# no verifiable numbers in it.
LABEL_ONLY_DEVICES = ("flow", "split", "timeline")

_NUMBER = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _dims(area: tuple[int, int, int, int]) -> tuple[int, int, int, int, int, int]:
    x0, y0, x1, y1 = area
    return x0, y0, x1, y1, x1 - x0, y1 - y0


def _dim_accent(accent, amount: float = 0.55):
    """A quieter version of the accent, for the side of a comparison that is not
    the point being made."""
    return theme.mix(accent, theme.hex_to_rgb(theme.INK_SOFT), amount)


def animate_number(label: str, progress: float) -> str:
    """Count the first number in `label` up to its final value.

    Formatting is preserved, so "$2.4B" counts through "$1.7B" and "47%" through
    "31%". A label with no number in it is returned untouched.
    """
    match = _NUMBER.search(label or "")
    if not match:
        return label
    raw = match.group(1)
    try:
        target = float(raw.replace(",", ""))
    except ValueError:  # pragma: no cover - regex already constrains this
        return label
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    grouped = "," in raw
    current = target * clamp01(progress)
    shown = (f"{current:,.{decimals}f}" if grouped else f"{current:.{decimals}f}")
    return label[:match.start(1)] + shown + label[match.end(1):]


def _centered(draw: ImageDraw.ImageDraw, text: str, font, *, cx: int, y: int,
              fill) -> None:
    width = fonts.text_width(font, text)
    draw.text((cx - width // 2, y), text, font=font, fill=fill)


def _fitted_label(text: str, max_width: int, *, start: int, minimum: int,
                  weight: int = 700):
    """Shrink a single-line label until it fits, so long words never overflow a
    chip or a bar."""
    size = start
    while size > minimum:
        font = fonts.label_font(size, weight=weight)
        if fonts.text_width(font, text) <= max_width:
            return font
        size -= 2
    return fonts.label_font(minimum, weight=weight)


# --------------------------------------------------------------------------- #
# bars: two or three quantities compared by height
# --------------------------------------------------------------------------- #
def draw_bars(canvas: Image.Image, t: float, *, area, accent, data: dict) -> None:
    """Labelled bars that grow from a baseline, staggered.

    The tallest bar keeps the full accent and the rest are dimmed, so the eye is
    pulled to the comparison being made rather than having to work it out.
    """
    bars = [b for b in (data.get("bars") or []) if isinstance(b, dict)][:3]
    if not bars:
        return
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1, w, h = _dims(area)

    label_band = 96
    value_band = 76
    baseline = y1 - label_band
    max_bar_h = max(60, baseline - y0 - value_band)

    count = len(bars)
    gap = int(w * 0.09)
    bar_w = max(90, (w - gap * (count - 1)) // count)
    total_w = bar_w * count + gap * (count - 1)
    left = x0 + (w - total_w) // 2

    weights = []
    for bar in bars:
        try:
            weights.append(clamp01(float(bar.get("weight", 0.5))))
        except (TypeError, ValueError):
            weights.append(0.5)
    peak = max(weights) or 1.0

    for i, (bar, weight) in enumerate(zip(bars, weights)):
        progress = ease_out_cubic(window(t, 0.10 + i * 0.13, 0.62 + i * 0.13))
        bx = left + i * (bar_w + gap)
        full_h = int(max_bar_h * (weight / peak))
        bar_h = int(full_h * progress)
        is_peak = weight >= peak - 1e-6
        colour = accent if is_peak else _dim_accent(accent)

        if bar_h > 6:
            top = baseline - bar_h
            radius = min(22, bar_w // 3)
            draw.rounded_rectangle([bx, top, bx + bar_w, baseline],
                                   radius=radius, fill=theme.rgba(colour))
            # Square off the bottom corners so bars sit on the baseline rather
            # than floating above it.
            draw.rectangle([bx, baseline - radius, bx + bar_w, baseline],
                           fill=theme.rgba(colour))

            value_label = str(bar.get("value_label") or "").strip()
            if value_label:
                vfont = _fitted_label(value_label, bar_w + gap // 2, start=52,
                                      minimum=30, weight=800)
                shown = animate_number(value_label, progress)
                _centered(draw, shown, vfont, cx=bx + bar_w // 2,
                          y=top - fonts.line_height(vfont) - 14,
                          fill=theme.rgba(theme.TEXT_PRIMARY,
                                          int(255 * progress)))

        # Baseline rule under every bar, always visible so the chart has a floor.
        draw.rectangle([bx, baseline, bx + bar_w, baseline + 4],
                       fill=theme.rgba(theme.TEXT_MUTED, 120))

        label = str(bar.get("label") or "").strip()
        if label:
            lfont = _fitted_label(label, bar_w + gap, start=34, minimum=22,
                                  weight=700)
            lines = fonts.wrap_text(lfont, label, bar_w + gap)[:2]
            ly = baseline + 26
            alpha = int(255 * ease_out_cubic(window(t, 0.16 + i * 0.13,
                                                    0.58 + i * 0.13)))
            for line in lines:
                _centered(draw, line, lfont, cx=bx + bar_w // 2, y=ly,
                          fill=theme.rgba(theme.TEXT_SECONDARY, alpha))
                ly += int(fonts.line_height(lfont) * 1.1)


# --------------------------------------------------------------------------- #
# counter: one figure, counted up
# --------------------------------------------------------------------------- #
def draw_counter(canvas: Image.Image, t: float, *, area, accent,
                 data: dict) -> None:
    """One big number that counts up, with a short line under it."""
    value_label = str(data.get("value_label") or "").strip()
    if not value_label:
        return
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1, w, h = _dims(area)
    cx = x0 + w // 2

    progress = ease_out_quint(window(t, 0.08, 0.68))
    shown = animate_number(value_label, progress)

    # Size to the *final* string so the number does not jump around as digits
    # appear while it counts.
    size = 240
    while size > 90 and fonts.text_width(fonts.title_font(size), value_label) > w:
        size -= 8
    font = fonts.title_font(size)

    y = y0 + max(0, (h - fonts.line_height(font)) // 2 - 80)
    # A soft accent disc behind the number, so it reads as a designed device
    # rather than as loose type in the middle of the frame.
    radius = int(min(w, h) * 0.42 * ease_out_back(window(t, 0.0, 0.5)))
    if radius > 10:
        disc = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(disc).ellipse(
            [cx - radius, y0 + h // 2 - radius - 70,
             cx + radius, y0 + h // 2 + radius - 70],
            fill=theme.rgba(_dim_accent(accent, 0.72), 150))
        canvas.alpha_composite(disc)
        draw = ImageDraw.Draw(canvas)

    _centered(draw, shown, font, cx=cx, y=y,
              fill=theme.rgba(theme.TEXT_PRIMARY, int(255 * min(1.0, progress * 1.4))))

    caption = str(data.get("caption") or "").strip()
    if caption:
        cfont = fonts.body_font(44, weight=600)
        alpha = int(255 * ease_out_cubic(window(t, 0.45, 0.85)))
        cy = y + fonts.line_height(font) + 26
        for line in fonts.wrap_text(cfont, caption, int(w * 0.86))[:2]:
            _centered(draw, line, cfont, cx=cx, y=cy,
                      fill=theme.rgba(accent, alpha))
            cy += int(fonts.line_height(cfont) * 1.2)


# --------------------------------------------------------------------------- #
# flow: a cause and effect chain
# --------------------------------------------------------------------------- #
def draw_flow(canvas: Image.Image, t: float, *, area, accent, data: dict) -> None:
    """Stacked chips joined by arrows, revealed one link at a time.

    This is the workhorse for explaining mechanisms, and it prints no figures,
    so it is always safe for material that has none.
    """
    steps = [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:3]
    if not steps:
        return
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1, w, h = _dims(area)

    count = len(steps)
    arrow_h = 76
    chip_h = min(190, max(120, (h - arrow_h * (count - 1)) // count))
    block_h = chip_h * count + arrow_h * (count - 1)
    y = y0 + max(0, (h - block_h) // 2)

    chip_w = int(w * 0.9)
    cx = x0 + w // 2
    left = cx - chip_w // 2

    # Each link gets an equal share of the beat, with a little of the last share
    # left over so the final chip is fully settled before the cut.
    share = 0.86 / count

    for i, step in enumerate(steps):
        start = i * share
        progress = ease_out_back(window(t, start, start + share * 0.85))
        chip_top = y + i * (chip_h + arrow_h)
        if progress > 0.001:
            alpha = int(255 * clamp01(progress * 1.3))
            slide = int(46 * (1.0 - clamp01(progress)))
            top = chip_top + slide
            is_last = i == count - 1
            # The final chip is filled: it is the consequence, and filling it is
            # how the graphic says "this is the bit that matters".
            if is_last:
                draw.rounded_rectangle([left, top, left + chip_w, top + chip_h],
                                       radius=chip_h // 2,
                                       fill=theme.rgba(accent, alpha))
                text_fill = theme.rgba(theme.INK, alpha)
            else:
                draw.rounded_rectangle([left, top, left + chip_w, top + chip_h],
                                       radius=chip_h // 2,
                                       fill=theme.rgba(theme.INK_SOFT,
                                                       int(alpha * 0.82)),
                                       outline=theme.rgba(accent, alpha), width=4)
                text_fill = theme.rgba(theme.TEXT_PRIMARY, alpha)

            font = _fitted_label(step, chip_w - 80, start=52, minimum=30, weight=800)
            lines = fonts.wrap_text(font, step, chip_w - 80)[:2]
            lh = int(fonts.line_height(font) * 1.1)
            ty = top + (chip_h - len(lines) * lh) // 2
            for line in lines:
                _centered(draw, line, font, cx=cx, y=ty, fill=text_fill)
                ty += lh

        if i < count - 1:
            arrow_progress = ease_out_cubic(
                window(t, start + share * 0.5, start + share * 1.1))
            _draw_down_arrow(draw, cx=cx, top=chip_top + chip_h,
                             height=arrow_h, accent=accent,
                             progress=arrow_progress)


def _draw_down_arrow(draw: ImageDraw.ImageDraw, *, cx: int, top: int,
                     height: int, accent, progress: float) -> None:
    """A short vertical connector that grows downward into an arrow head."""
    if progress <= 0.02:
        return
    alpha = int(255 * progress)
    stem_h = int((height - 22) * progress)
    if stem_h > 4:
        draw.rounded_rectangle([cx - 3, top + 10, cx + 3, top + 10 + stem_h],
                               radius=3, fill=theme.rgba(accent, alpha))
    if progress > 0.72:
        head_alpha = int(255 * window(progress, 0.72, 1.0))
        tip = top + 10 + stem_h + 14
        draw.polygon([(cx - 16, tip - 16), (cx + 16, tip - 16), (cx, tip)],
                     fill=theme.rgba(accent, head_alpha))


# --------------------------------------------------------------------------- #
# timeline: what happens over time
# --------------------------------------------------------------------------- #
def draw_timeline(canvas: Image.Image, t: float, *, area, accent,
                  data: dict) -> None:
    """A vertical rail that fills through labelled stops.

    Vertical rather than horizontal because on a 9:16 canvas a horizontal
    timeline forces the labels down to a size nobody reads on a phone.
    """
    stops = [str(s).strip() for s in (data.get("stops") or []) if str(s).strip()][:4]
    if not stops:
        return
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1, w, h = _dims(area)

    note = str(data.get("note") or "").strip()
    note_band = 130 if note else 0
    rail_x = x0 + 46
    rail_top = y0 + 40
    rail_bottom = y1 - note_band - 40
    span = max(80, rail_bottom - rail_top)

    # The dim rail is always fully drawn, so the viewer can see how far there is
    # left to go. The bright one fills over it.
    draw.rounded_rectangle([rail_x - 4, rail_top, rail_x + 4, rail_bottom],
                           radius=4, fill=theme.rgba(theme.TEXT_MUTED, 90))
    filled = int(span * ease_out_cubic(window(t, 0.05, 0.8)))
    if filled > 8:
        draw.rounded_rectangle([rail_x - 4, rail_top, rail_x + 4, rail_top + filled],
                               radius=4, fill=theme.rgba(accent))

    count = len(stops)
    step = span / max(1, count - 1) if count > 1 else 0
    label_font = fonts.label_font(46, weight=800)
    for i, stop in enumerate(stops):
        cy = int(rail_top + step * i) if count > 1 else int(rail_top + span // 2)
        reached = cy - rail_top <= filled + 6
        progress = ease_out_back(window(t, 0.05 + i * 0.18, 0.45 + i * 0.18))
        if progress <= 0.02:
            continue
        alpha = int(255 * clamp01(progress))
        radius = int(19 * clamp01(progress))
        colour = accent if reached else theme.mix(theme.hex_to_rgb(theme.INK_SOFT),
                                                  accent, 0.4)
        draw.ellipse([rail_x - radius, cy - radius, rail_x + radius, cy + radius],
                     fill=theme.rgba(colour, alpha))
        draw.ellipse([rail_x - radius + 7, cy - radius + 7,
                      rail_x + radius - 7, cy + radius - 7],
                     fill=theme.rgba(theme.INK, alpha))

        tx = rail_x + 52
        lfont = _fitted_label(stop, x1 - tx, start=46, minimum=28, weight=800)
        draw.text((tx + int(20 * (1 - clamp01(progress))),
                   cy - fonts.line_height(lfont) // 2), stop, font=lfont,
                  fill=theme.rgba(theme.TEXT_PRIMARY, alpha))

    if note:
        nfont = fonts.body_font(40, weight=500)
        alpha = int(255 * ease_out_cubic(window(t, 0.62, 0.92)))
        ny = rail_bottom + 44
        for line in fonts.wrap_text(nfont, note, w - 40)[:2]:
            draw.text((x0 + 4, ny), line, font=nfont,
                      fill=theme.rgba(theme.TEXT_SECONDARY, alpha))
            ny += int(fonts.line_height(nfont) * 1.2)


# --------------------------------------------------------------------------- #
# split: a direct contrast
# --------------------------------------------------------------------------- #
def draw_split(canvas: Image.Image, t: float, *, area, accent,
               data: dict) -> None:
    """Two stacked panels that slide in from opposite sides.

    Stacked rather than side by side: on a 9:16 canvas two vertical columns give
    each side about 460 pixels of width, which is not enough for a readable
    sentence at reel type sizes.
    """
    left_title = str(data.get("left_title") or "").strip()
    right_title = str(data.get("right_title") or "").strip()
    if not (left_title or right_title):
        return
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1, w, h = _dims(area)

    left_text = str(data.get("left_text") or "").strip()
    right_text = str(data.get("right_text") or "").strip()

    # Measure both panels first and size each to its own content. Splitting the
    # area in half regardless leaves two mostly-empty boxes, which reads as a
    # layout that did not know what was going in it.
    divider_band = 92
    room = (h - divider_band) // 2
    left_layout = _measure_panel(left_title, left_text, w, room)
    right_layout = _measure_panel(right_title, right_text, w, room)

    block_h = left_layout["height"] + divider_band + right_layout["height"]
    top = y0 + max(0, (h - block_h) // 2)
    left_box = (x0, top, x1, top + left_layout["height"])
    right_top = top + left_layout["height"] + divider_band
    right_box = (x0, right_top, x1, right_top + right_layout["height"])

    _draw_split_panel(
        draw, t, box=left_box, layout=left_layout,
        accent=theme.mix(accent, theme.hex_to_rgb(theme.TEXT_MUTED), 0.45),
        from_left=True, delay=0.04)
    _draw_split_panel(
        draw, t, box=right_box, layout=right_layout, accent=accent,
        from_left=False, delay=0.24)

    # The pivot chip between the panels, which is what makes it read as one
    # comparison rather than two unrelated boxes.
    pivot_progress = ease_out_back(window(t, 0.20, 0.62))
    if pivot_progress > 0.02:
        cx = x0 + w // 2
        cy = top + left_layout["height"] + divider_band // 2
        radius = int(42 * clamp01(pivot_progress))
        alpha = int(255 * clamp01(pivot_progress))
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=theme.rgba(accent, alpha))
        vfont = fonts.label_font(32, weight=800)
        _centered(draw, "VS", vfont, cx=cx,
                  y=cy - fonts.line_height(vfont) // 2,
                  fill=theme.rgba(theme.INK, alpha))


_PANEL_PAD = 42


def _measure_panel(title: str, text: str, width: int, max_height: int) -> dict:
    """Wrap a panel's contents and work out the height the box needs."""
    inner_w = width - _PANEL_PAD * 2
    title_font = (_fitted_label(title.upper(), inner_w, start=40, minimum=26,
                                weight=800) if title else None)
    title_h = (fonts.line_height(title_font) + 18) if title_font else 0

    body_font = None
    lines: list[str] = []
    body_h = 0
    if text:
        for size in range(42, 27, -2):
            body_font = fonts.body_font(size, weight=500)
            lines = fonts.wrap_text(body_font, text, inner_w)[:3]
            body_h = int(len(lines) * fonts.line_height(body_font) * 1.2)
            if title_h + body_h + _PANEL_PAD * 2 <= max_height:
                break

    height = min(max_height, max(140, title_h + body_h + _PANEL_PAD * 2))
    return {"title": title, "title_font": title_font, "title_h": title_h,
            "lines": lines, "body_font": body_font, "height": height,
            "inner_w": inner_w}


def _draw_split_panel(draw: ImageDraw.ImageDraw, t: float, *, box, layout: dict,
                      accent, from_left: bool, delay: float) -> None:
    bx0, by0, bx1, by1 = box
    progress = ease_out_quint(window(t, delay, delay + 0.42))
    if progress <= 0.01:
        return
    alpha = int(255 * clamp01(progress))
    offset = int(90 * (1.0 - clamp01(progress))) * (-1 if from_left else 1)
    bx0 += offset
    bx1 += offset

    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=32,
                           fill=theme.rgba(theme.INK_SOFT, int(alpha * 0.86)),
                           outline=theme.rgba(accent, alpha), width=4)

    y = by0 + _PANEL_PAD
    if layout["title_font"] is not None:
        fonts.draw_tracked(draw, (bx0 + _PANEL_PAD, y), layout["title"].upper(),
                           layout["title_font"], fill=theme.rgba(accent, alpha),
                           tracking=2.0)
        y += layout["title_h"]

    if layout["body_font"] is not None:
        line_h = int(fonts.line_height(layout["body_font"]) * 1.2)
        for line in layout["lines"]:
            draw.text((bx0 + _PANEL_PAD, y), line, font=layout["body_font"],
                      fill=theme.rgba(theme.TEXT_PRIMARY, alpha))
            y += line_h


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
_RENDERERS = {
    "bars": draw_bars,
    "counter": draw_counter,
    "flow": draw_flow,
    "timeline": draw_timeline,
    "split": draw_split,
}


def draw_device(canvas: Image.Image, device: str, t: float, *, area, accent,
                data: dict) -> bool:
    """Draw one device by name. Returns False for an unknown or empty device.

    Failing soft matters here: a malformed graphic payload should cost the reel
    its picture, not the whole run.
    """
    renderer = _RENDERERS.get((device or "").strip().lower())
    if renderer is None:
        return False
    try:
        renderer(canvas, clamp01(t), area=area, accent=accent, data=data or {})
    except Exception as exc:  # noqa: BLE001 - a bad payload must not kill a run
        from ..logging_setup import get_logger

        get_logger("render.graphics").warning("device %r failed: %s", device, exc)
        return False
    return True
