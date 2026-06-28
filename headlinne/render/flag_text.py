"""Render a short piece of text filled with a simplified US-flag pattern.

Used for the word "Geo" on the Geopolitics carousel cover. The flag is a faithful
but lightweight rendering: 13 red/white stripes, a blue canton, and small white
star dots. The pattern is masked by the glyph shapes so the flag only shows
inside the letters.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

# Official-ish US flag colours.
OLD_GLORY_RED = (178, 34, 52, 255)
OLD_GLORY_BLUE = (60, 59, 110, 255)
WHITE = (255, 255, 255, 255)


def _flag_pattern(width: int, height: int) -> Image.Image:
    """Build an RGBA flag pattern sized to fill the given box."""
    flag = Image.new("RGBA", (width, height), OLD_GLORY_RED)
    draw = ImageDraw.Draw(flag)

    # 13 stripes, alternating starting with red (red already the base).
    stripes = 13
    stripe_h = height / stripes
    for i in range(stripes):
        if i % 2 == 1:  # white stripes
            y0 = int(round(i * stripe_h))
            y1 = int(round((i + 1) * stripe_h))
            draw.rectangle([0, y0, width, y1], fill=WHITE)

    # Canton: top-left, ~40% width and the height of the top 7 stripes.
    canton_w = int(width * 0.42)
    canton_h = int(round(7 * stripe_h))
    draw.rectangle([0, 0, canton_w, canton_h], fill=OLD_GLORY_BLUE)

    # Simplified stars as a small grid of white dots inside the canton.
    cols, rows = 5, 4
    if canton_w > 12 and canton_h > 12:
        margin_x = canton_w / (cols + 1)
        margin_y = canton_h / (rows + 1)
        r = max(1, int(min(margin_x, margin_y) * 0.22))
        for row in range(rows):
            for col in range(cols):
                cx = int(margin_x * (col + 1))
                cy = int(margin_y * (row + 1))
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)

    return flag


def render_flag_text(text: str, font: ImageFont.FreeTypeFont,
                     pad: int = 6) -> Image.Image:
    """Return an RGBA image of `text` painted with the flag pattern.

    The image is tightly sized to the glyphs (plus a small pad so nothing clips).
    Transparent everywhere outside the letters.
    """
    # Measure the glyphs.
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    img_w = text_w + pad * 2
    img_h = text_h + pad * 2

    # Build the alpha mask by drawing the text in solid white on an L canvas.
    mask = Image.new("L", (img_w, img_h), 0)
    mdraw = ImageDraw.Draw(mask)
    # Offset so the glyph's own bbox origin lands at (pad, pad).
    mdraw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=255)

    # Paint the flag and apply the glyph mask.
    pattern = _flag_pattern(img_w, img_h)
    out = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    out.paste(pattern, (0, 0), mask)
    return out
