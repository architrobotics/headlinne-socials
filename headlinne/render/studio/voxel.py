"""Pip as a papercraft figure: his pixel grid, extruded into blocks.

The mascot in the reference reels is pixel art built in 3D - each colour region
is a solid block with a lit top and a shaded side, standing in the set rather
than printed over it. Pip is pixel art too, so the same construction applies
directly, and every pose, head and prop in render/pip.py carries over without
being redrawn.

Three decisions make it read as a built object rather than a big sprite:

  * The ink outline goes. It is what makes a 26px sprite legible on a flat
    ground, but extruded it becomes a black cage around him. Outline cells
    take the colour of the region they bound, so the silhouette keeps its size
    and the edges come from the lighting instead.
  * Same-colour neighbours are one block. Seams are drawn only where the
    colour changes, so his body is one slab of terracotta paper, not a grid of
    cubes.
  * Light comes from the upper left. Tops are lifted, right-hand sides are
    dropped, and the whole front is graded top to bottom, which is what puts
    him in the same room as the set's key light.

Hats are props, not recolours: pip.py's consistency rules forbid changing his
palette, and a hat is drawn above the crown in its own colours.
"""

from __future__ import annotations

import zlib
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .. import pip as _pip

# Hat colours. Pip's own palette is fixed (see pip.py); these belong to props.
HAT_PAL = {
    "D": (52, 58, 70),       # felt grey-navy
    "d": (36, 40, 50),       # its band
    "Y": (242, 184, 48),     # hard-hat yellow
    "y": (206, 148, 30),     # its brim shade
    "G": (232, 186, 72),     # gold
    "g": (190, 140, 40),     # gold shade
    "J": (30, 30, 34),       # black
    "j": (198, 60, 48),      # a red band
    "U": (46, 92, 168),      # cap blue
    "u": (34, 70, 132),      # its peak
    "Q": (250, 247, 240),    # card white
    "V": (120, 60, 140),     # beanie plum
    "v": (96, 46, 112),
}

# Each hat is drawn on a 26-wide canvas and placed so its last row sits on
# Pip's crown row. Rows above the crown are added as needed.
HATS = {
    "press": """
.........DDDDDDDD.........
........DDDDDDDDDD........
........DDDDDDQQDD........
.......ddddddddddddd......
....DDDDDDDDDDDDDDDDDD....
""",
    "hardhat": """
..........YYYYYY..........
........YYYYYYYYYY........
.......YYYYYYYYYYYY.......
......YYYYYYYYYYYYYY......
....yyyyyyyyyyyyyyyyyy....
""",
    "cap": """
.........UUUUUUUU.........
........UUUUUUUUUU........
.......UUUUUUUUUUUU.......
.......UUUUUUUUUUUUuuuuu..
""",
    "grad": """
...........G..............
.....JJJJJJJJJJJJJJJJ.....
...JJJJJJJJJJJJJJJJJJJJ...
.....JJJJJJJJJJJJJJJJ.G...
........JJJJJJJJJJ....G...
""",
    "crown": """
.......G...G....G...G.....
.......GG.GGG..GGG.GG.....
.......GGGGGGGGGGGGGG.....
.......ggggggggggggggg....
""",
    "tophat": """
.........JJJJJJJJ.........
.........JJJJJJJJ.........
.........JJJJJJJJ.........
.........jjjjjjjj.........
.......JJJJJJJJJJJJ.......
""",
    "beanie": """
...........VVVV...........
.........VVVVVVVV.........
........VVVVVVVVVV........
.......vvvvvvvvvvvv.......
""",
}
HAT_NAMES = tuple(HATS)

# The extrusion, as a fraction of a cell. The camera sits a little above and to
# the left of him, so his tops and right-hand sides are what show.
DEPTH_X = 0.34
DEPTH_Y = -0.30

_TOP_LIFT = 1.16
_SIDE_DROP = 0.70
_SEAM_DROP = 0.80


def _rows(grid: str) -> list[str]:
    return [r.ljust(_pip.W, ".")[:_pip.W] for r in _pip._rows(grid)]


def _colour(ch: str):
    if ch in HAT_PAL:
        return HAT_PAL[ch]
    return _pip.PAL.get(ch)


def with_hat(grid: str, hat: str) -> str:
    """Pip wearing `hat`, its last row resting on his crown."""
    art = HATS.get(hat or "")
    rows = _rows(grid)
    if not art:
        return "\n".join(rows)
    hat_rows = [r.ljust(_pip.W, ".")[:_pip.W] for r in _pip._rows(art)]
    # The crown is the row above the first row of cream head. Found from the
    # head rather than from the outline, because a squash frame drops the
    # crown's outline row and confetti can overwrite it.
    first_cream = next((i for i, r in enumerate(rows) if "C" in r), None)
    if first_cream is None:
        return "\n".join(rows)
    crown = first_cream - 1
    # The hat's bottom row replaces the crown's outline row, so it sits on his
    # head rather than floating a row above it.
    top = crown - len(hat_rows) + 1
    if top < 0:
        rows = ["." * _pip.W] * (-top) + rows
        crown -= top
        top = 0
    out = [list(r) for r in rows]
    for dy, line in enumerate(hat_rows):
        for x, ch in enumerate(line):
            if ch != ".":
                out[top + dy][x] = ch
    return "\n".join("".join(r) for r in out)


def _strip_outline(rows: list[str]) -> list[list[str]]:
    """Replace the outline with the colour of what it bounds.

    The outline is every 'K' reachable from empty space through other 'K's,
    which catches the shoulder and chin runs that touch the head rather than
    the air. Interior ink - a closed eye, a mouth - is never reached, so it is
    kept: that is drawing, not outline.
    """
    h = len(rows)
    grid = [list(r) for r in rows]
    outline: set[tuple[int, int]] = set()
    frontier = [(x, y) for y in range(h) for x in range(_pip.W)
                if rows[y][x] == "K" and any(
                    not (0 <= x + dx < _pip.W and 0 <= y + dy < h)
                    or rows[y + dy][x + dx] == "."
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    while frontier:
        x, y = frontier.pop()
        if (x, y) in outline:
            continue
        outline.add((x, y))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < _pip.W and 0 <= ny < h and rows[ny][nx] == "K":
                frontier.append((nx, ny))

    for x, y in sorted(outline, key=lambda p: (p[1], p[0])):
        # Borrow the most common solid neighbour inside the shape.
        votes: dict[str, int] = {}
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0),
                       (1, 1), (-1, 1), (1, -1), (-1, -1),
                       (0, 2), (0, -2), (2, 0), (-2, 0)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < _pip.W and 0 <= ny < h:
                ch = rows[ny][nx]
                if ch not in ".KNW":
                    votes[ch] = votes.get(ch, 0) + 1
        grid[y][x] = max(votes, key=votes.get) if votes else "."
    return grid


def _jitter(rgb, seed: int, amount: float = 0.008):
    f = 1.0 + ((seed % 1000) / 1000.0 - 0.5) * 2 * amount
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def _shade(rgb, factor: float):
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


@lru_cache(maxsize=256)
def render(grid: str, cell: int = 20) -> Image.Image:
    """The grid as a lit papercraft figure, transparent around it.

    Cached by grid and size: a reel cycles through a handful of distinct
    frames, and each one is drawn once.
    """
    rows = _rows(grid)
    cells = _strip_outline(rows)
    h = len(cells)
    dx, dy = DEPTH_X * cell, DEPTH_Y * cell
    pad = int(cell * 0.6)
    width = int(_pip.W * cell + dx + 2 * pad)
    height = int(h * cell - dy + 2 * pad)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ox, oy = pad, pad - dy

    def solid(x, y):
        return 0 <= x < _pip.W and 0 <= y < h and cells[y][x] != "."

    def base(x, y):
        c = _colour(cells[y][x])
        return c if c else None

    # Sides first: front faces always cover them, so order among them only
    # matters where two sides meet, and bottom-up keeps the near ones on top.
    for y in range(h - 1, -1, -1):
        for x in range(_pip.W):
            c = base(x, y) if solid(x, y) else None
            if not c:
                continue
            x0, y0 = ox + x * cell, oy + y * cell
            x1, y1 = x0 + cell, y0 + cell
            if not solid(x + 1, y):
                draw.polygon([(x1, y0), (x1, y1), (x1 + dx, y1 + dy),
                              (x1 + dx, y0 + dy)], fill=_shade(c, _SIDE_DROP))
            if not solid(x, y - 1):
                draw.polygon([(x0, y0), (x1, y0), (x1 + dx, y0 + dy),
                              (x0 + dx, y0 + dy)],
                             fill=_shade(c, _TOP_LIFT))

    # Fronts, then the seams where one colour meets another.
    for y in range(h):
        for x in range(_pip.W):
            c = base(x, y) if solid(x, y) else None
            if not c:
                continue
            x0, y0 = ox + x * cell, oy + y * cell
            seed = zlib.crc32(f"{x},{y},{cells[y][x]}".encode())
            draw.rectangle([x0, y0, x0 + cell, y0 + cell], fill=_jitter(c, seed))
    seam = max(1, cell // 9)
    for y in range(h):
        for x in range(_pip.W):
            if not solid(x, y):
                continue
            ch = cells[y][x]
            c = base(x, y)
            x0, y0 = ox + x * cell, oy + y * cell
            if solid(x, y + 1) and cells[y + 1][x] != ch:
                draw.rectangle([x0, y0 + cell - seam, x0 + cell, y0 + cell],
                               fill=_shade(c, _SEAM_DROP))
            if solid(x + 1, y) and cells[y][x + 1] != ch:
                draw.rectangle([x0 + cell - seam, y0, x0 + cell, y0 + cell],
                               fill=_shade(c, _SEAM_DROP))

    return _light(img)


def _light(img: Image.Image) -> Image.Image:
    """Grade the figure from lit top-left to shadowed bottom, and add tooth."""
    w, h = img.size
    alpha = img.getchannel("A")
    ramp = Image.linear_gradient("L").resize((w, h))          # 0 top .. 255 bottom
    diag = Image.linear_gradient("L").rotate(90).resize((w, h))  # left .. right
    shade = Image.blend(ramp, diag, 0.3).point(lambda v: int(v * 0.30))
    dark = Image.new("RGBA", (w, h), (24, 14, 8, 0))
    dark.putalpha(Image.composite(shade, Image.new("L", (w, h), 0), alpha))
    out = Image.alpha_composite(img, dark)
    # Paper tooth, faint, so flat colour reads as card rather than plastic.
    noise = Image.effect_noise((w, h), 22).point(lambda v: int(abs(v - 128) * 0.5))
    tooth = Image.new("RGBA", (w, h), (255, 248, 236, 0))
    tooth.putalpha(Image.composite(noise, Image.new("L", (w, h), 0), alpha))
    out = Image.alpha_composite(out, tooth)
    return out


@lru_cache(maxsize=32)
def contact_shadow(width: int, *, strength: int = 120) -> Image.Image:
    """The soft dark ellipse that stands him on the floor."""
    w = max(8, width)
    h = max(6, int(w * 0.16))
    img = Image.new("L", (w + 40, h + 40), 0)
    ImageDraw.Draw(img).ellipse([20, 20, 20 + w, 20 + h], fill=strength)
    img = img.filter(ImageFilter.GaussianBlur(max(4, w // 18)))
    shadow = Image.new("RGBA", img.size, (20, 10, 4, 0))
    shadow.putalpha(img)
    return shadow


def figure(grid: str, *, cell: int = 20, hat: str = "") -> Image.Image:
    """Pip in a hat, ready to stand in a set."""
    return render(with_hat(grid, hat), cell)
