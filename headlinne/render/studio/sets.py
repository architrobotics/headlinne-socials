"""The sets: a full-bleed cut-paper diorama behind every beat.

The reference reels never show an empty frame. Every beat is a place - a
study at night, a game-show stage, a courtroom - with the mascot standing in
it and the light coming from somewhere. That is most of the difference between
them and a slideshow, and it is what the old flat paper style was missing.

Each set is built once per beat at a little over frame size (OVERSCAN), so the
camera can push in and drift without ever showing an edge, and returns two
layers: everything behind Pip, and the few things in front of him (a desk, a
podium, the near edge of a crowd). Pip is composited between them every frame.

Coordinates below are in set space, SET_W x SET_H. The frame sees all of it at
zoom 1.0 and the central 1080x1920 at full push-in.

Nothing on a set prints a number, a quote or a name. Set dressing is scenery;
facts belong to the overlays, where generate/reel.py verifies them first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from . import paper
from .paper import Rng, mix, shade

SET_W, SET_H = 1188, 2112
CX = SET_W // 2
HORIZON = 1180          # where the back wall meets the floor
EYE = 640               # the vanishing height: the camera looks down a little
FLOOR_MARK = 1395       # where Pip's feet land
BOARD_BOX = (120, 600, SET_W - 120, 1120)

SETS = ("newsroom", "parliament", "courtroom", "street", "skyline", "trading",
        "harbour", "lab", "server", "maproom", "space", "home", "board")

# One sober set for stories about death and disaster: no playful dressing, a
# low key light, nothing that reads as a joke beside a casualty figure.
SOBER_SETS = ("maproom", "newsroom", "skyline")

NIGHT_SKY = ((14, 22, 48), (44, 52, 96))
DUSK_SKY = ((46, 40, 92), (232, 132, 92))
DAY_SKY = ((116, 170, 222), (214, 232, 240))

WOOD = (146, 88, 50)
WOOD_DARK = (104, 60, 34)
CREAM = (244, 236, 220)
INK = (26, 20, 16)


@dataclass(frozen=True)
class SetSpec:
    """Everything that decides how one beat's set looks."""

    name: str = "newsroom"
    time: str = "night"                  # day | dusk | night
    accent: tuple = (196, 86, 47)        # the story's tone, used sparingly
    trend: str = ""                      # up | down, for the trading wall
    board: bool = False                  # a graphic beat: put a board up
    variant: int = 0                     # per-reel seed for small variations
    sober: bool = False


@dataclass
class Built:
    back: Image.Image
    front: Image.Image | None = None
    pip: tuple[int, int] = (CX, FLOOR_MARK)     # Pip's feet, centre x
    board: tuple[int, int, int, int] | None = None
    board_dark: bool = False
    lights: list = field(default_factory=list)  # (x, y, r) blinking lamps
    front_at: tuple[int, int] = (0, 0)          # where the cropped front sits


# --------------------------------------------------------------------------- #
# Shared construction
# --------------------------------------------------------------------------- #
def _sky(time: str):
    return {"day": DAY_SKY, "dusk": DUSK_SKY}.get(time, NIGHT_SKY)


def _canvas() -> Image.Image:
    return Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 255))


def _wall(c: Image.Image, rgb, *, key, top: int = 0, bottom: int = HORIZON,
          pattern: str = "plain", trim=None) -> None:
    h = bottom - top
    wall = paper.textured(SET_W, h, rgb, key=("wall", key), mottle=0.7)
    d = ImageDraw.Draw(wall)
    if pattern == "panels":
        pw = 198
        for x in range(-20, SET_W, pw):
            d.rectangle([x + 14, h * 0.52, x + pw - 14, h - 40],
                        outline=shade(rgb, 0.78), width=6)
            d.rectangle([x + 14, 60, x + pw - 14, h * 0.47],
                        outline=shade(rgb, 0.82), width=5)
    elif pattern == "brick":
        bh, bw = 54, 128
        for row, y in enumerate(range(0, h, bh)):
            off = (row % 2) * bw // 2
            for x in range(-bw, SET_W + bw, bw):
                tone = shade(rgb, 0.92 + ((x * 7 + y * 3) % 17) / 100)
                d.rectangle([x + off + 3, y + 3, x + off + bw - 3, y + bh - 3],
                            fill=tone)
    elif pattern == "stripes":
        for x in range(0, SET_W, 66):
            d.rectangle([x, 0, x + 26, h], fill=shade(rgb, 0.93))
    elif pattern == "tiles":
        for y in range(0, h, 92):
            d.line([(0, y), (SET_W, y)], fill=shade(rgb, 0.86), width=4)
        for x in range(0, SET_W, 92):
            d.line([(x, 0), (x, h)], fill=shade(rgb, 0.86), width=4)
    # Light falls off towards the ceiling, which is what makes it a room.
    fall = Image.linear_gradient("L").rotate(180).resize((SET_W, h)) \
        .point(lambda v: int(v * 0.42))
    dark = Image.new("RGBA", (SET_W, h), (10, 6, 4, 0))
    dark.putalpha(fall)
    wall.alpha_composite(dark)
    c.alpha_composite(wall, (0, top))
    if trim:
        skirting = paper.textured(SET_W, 46, trim, key=("trim", key))
        paper.lay(c, skirting, 0, bottom - 46, offset=(0, -6), blur=8, strength=0.5)


def _floor(c: Image.Image, kind: str, rgb, *, key, rug=None) -> None:
    h = SET_H - HORIZON
    floor = paper.textured(SET_W, h, rgb, key=("floor", key), mottle=0.6)
    d = ImageDraw.Draw(floor)
    vp = (CX, EYE - HORIZON)                          # in floor-local coords
    if kind == "planks":
        for i in range(-14, 15):
            bx = CX + i * 120
            # A line from the bottom edge towards the vanishing point.
            t = (0 - vp[1]) / (h - vp[1])
            tx = vp[0] + (bx - vp[0]) * t
            d.line([(tx, 0), (bx, h)], fill=shade(rgb, 0.80), width=3)
        for k in range(1, 9):
            y = h * (k / 9) ** 1.7
            d.line([(0, y), (SET_W, y)], fill=shade(rgb, 0.86), width=2)
    elif kind == "tiles":
        for i in range(-12, 13):
            bx = CX + i * 150
            t = (0 - vp[1]) / (h - vp[1])
            tx = vp[0] + (bx - vp[0]) * t
            d.line([(tx, 0), (bx, h)], fill=shade(rgb, 0.84), width=4)
        for k in range(1, 10):
            y = h * (k / 10) ** 1.6
            d.line([(0, y), (SET_W, y)], fill=shade(rgb, 0.84), width=4)
    # Darker into the distance, so the floor recedes.
    ramp = Image.linear_gradient("L").rotate(180).resize((SET_W, h)) \
        .point(lambda v: int(v * 0.35))
    shadow = Image.new("RGBA", (SET_W, h), (8, 4, 2, 0))
    shadow.putalpha(ramp)
    floor.alpha_composite(shadow)
    c.alpha_composite(floor, (0, HORIZON))
    if rug:
        _rug(c, rug, key=key)


def _rug(c: Image.Image, colours, *, key) -> None:
    outer, ring = colours
    w, h = 980, 330
    cy = FLOOR_MARK + 10
    m = paper.mask_of(w, h, lambda d: d.ellipse([0, 0, w - 1, h - 1], fill=255))
    rug = paper.cut(m, outer, key=("rug", key))
    ImageDraw.Draw(rug).ellipse([70, 26, w - 70, h - 26], outline=ring, width=14)
    paper.lay(c, rug, CX - w // 2, cy - h // 2, offset=(0, 6), blur=6, strength=0.35)


def _window(c: Image.Image, x: int, y: int, w: int, h: int, *, time: str,
            key, arched: bool = False, city: bool = False, frame=CREAM) -> None:
    top, bottom = _sky(time)
    view = paper.gradient(w, h, top, bottom)
    vd = ImageDraw.Draw(view)
    rng = Rng("window", key, x)
    if time == "night":
        for _ in range(26):
            sx, sy = rng.uniform(0, w), rng.uniform(0, h * 0.7)
            r = rng.uniform(1.5, 3.5)
            vd.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(250, 240, 210))
        mx, my = w * 0.7, h * 0.22
        vd.ellipse([mx - 34, my - 34, mx + 34, my + 34], fill=(250, 238, 200))
    elif time == "day":
        for _ in range(3):
            cx, cy = rng.uniform(0, w), rng.uniform(h * 0.1, h * 0.5)
            for k in range(3):
                r = rng.uniform(22, 40)
                vd.ellipse([cx + k * 30 - r, cy - r, cx + k * 30 + r, cy + r],
                           fill=(250, 252, 255))
    if city:
        _skyline_into(view, key=("win", key), lit=time != "day", base=h)
    mask = paper.mask_of(w, h, (lambda d: (d.rounded_rectangle(
        [0, w // 2 - 2, w - 1, h - 1], radius=4, fill=255),
        d.pieslice([0, 0, w - 1, w], 180, 360, fill=255))) if arched else
        (lambda d: d.rectangle([0, 0, w - 1, h - 1], fill=255)))
    view.putalpha(mask)
    c.alpha_composite(view, (x, y))
    # The frame and mullions, as card laid over the glass.
    fr = Image.new("RGBA", (w + 36, h + 36), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fr)
    if arched:
        fd.rounded_rectangle([0, w // 2 + 16, w + 35, h + 35], radius=6,
                             outline=frame, width=18)
        fd.arc([0, 0, w + 35, w + 35], 180, 360, fill=frame, width=18)
    else:
        fd.rectangle([0, 0, w + 35, h + 35], outline=frame, width=18)
    fd.line([(w // 2 + 18, 10), (w // 2 + 18, h + 26)], fill=frame, width=10)
    fd.line([(10, h * 0.55 + 18), (w + 26, h * 0.55 + 18)], fill=frame, width=10)
    tex = paper.textured(fr.width, fr.height, frame, key=("frame", key, x))
    tex.putalpha(fr.getchannel("A"))
    paper.lay(c, tex, x - 18, y - 18, offset=(5, 8), blur=6, strength=0.4)
    sill = paper.rect(w + 70, 26, shade(frame, 0.95), key=("sill", key, x))
    paper.lay(c, sill, x - 35, y + h + 14, offset=(0, 8), blur=8)


def _skyline_into(img: Image.Image, *, key, lit: bool, base: int,
                  layers: int = 3) -> None:
    w = img.width
    rng = Rng("skyline", key)
    for layer in range(layers):
        depth = layer / max(1, layers - 1)
        col = mix((48, 50, 86), (22, 22, 40), depth) if lit else \
            mix((150, 170, 196), (96, 114, 140), depth)
        x = -rng.uniform(0, 60)
        while x < w:
            bw = rng.uniform(60, 130) * (1 + depth * 0.3)
            bh = rng.uniform(0.18, 0.45 + 0.15 * depth) * base
            top = base - bh
            d = ImageDraw.Draw(img)
            d.rectangle([x, top, x + bw, base], fill=col)
            if lit and layer == layers - 1:
                for wy in range(int(top + 14), int(base - 10), 26):
                    for wx in range(int(x + 10), int(x + bw - 14), 22):
                        if rng.random() < 0.45:
                            d.rectangle([wx, wy, wx + 9, wy + 12],
                                        fill=(255, 214, 128))
            x += bw + rng.uniform(4, 18)


def _frame_on_wall(c, x, y, w, h, *, key, inner=None) -> None:
    pic = paper.rect(w, h, (238, 226, 200), key=("pic", key, x))
    d = ImageDraw.Draw(pic)
    d.rectangle([0, 0, w - 1, h - 1], outline=(120, 82, 46), width=12)
    if inner:
        d.rectangle([24, 24, w - 25, h - 25], fill=inner)
        d.polygon([(24, h - 25), (w * 0.45, h * 0.45), (w - 25, h - 25)],
                  fill=shade(inner, 0.7))
    paper.lay(c, pic, x, y, offset=(6, 9), blur=7)


def _flag(c, x, y, colour, *, key, h=260) -> None:
    """A plain banner with a gold star: official, and no country's in particular.

    National flags are deliberately not drawn. A stripe order that is nearly
    right is somebody else's flag - green, yellow and blue bars read as Gabon,
    not Brazil - and a wrong flag in a news reel is a factual error.
    """
    pole = paper.rect(14, h + 300, (196, 160, 90), key=("pole", key))
    paper.lay(c, pole, x, y, offset=(6, 6), blur=6)
    fw, fh = 220, 150
    flag = paper.rect(fw, fh, tuple(colour), key=("banner", key))
    s_img, sx, sy = paper.poly(paper.star(fw / 2, fh / 2, 40, 17), (232, 196, 100),
                               key=("bannerstar", key))
    flag.alpha_composite(s_img, (sx, sy))
    # A ripple, by shifting columns: cloth rather than a card.
    rippled = Image.new("RGBA", (fw, fh + 24), (0, 0, 0, 0))
    for cx in range(0, fw, 4):
        dy = int(8 * math.sin(cx / 34.0))
        rippled.alpha_composite(flag.crop((cx, 0, cx + 4, fh)), (cx, 12 + dy))
    paper.lay(c, rippled, x + 14, y + 16, offset=(8, 10), blur=8)
    knob = paper.ellipse(30, 30, (220, 180, 90), key=("knob", key))
    paper.lay(c, knob, x - 8, y - 22, offset=(3, 4), blur=4)


def _desk(w, h, rgb, *, key, stripe=None, logo: bool = False) -> Image.Image:
    desk = paper.rect(w, h, rgb, key=("desk", key), radius=10)
    d = ImageDraw.Draw(desk)
    top = paper.rect(w + 40, 34, shade(rgb, 1.25), key=("desktop", key), radius=6)
    out = Image.new("RGBA", (w + 40, h + 30), (0, 0, 0, 0))
    out.alpha_composite(desk, (20, 30))
    if stripe:
        sd = ImageDraw.Draw(out)
        sd.rectangle([20, 30 + h * 0.22, 20 + w, 30 + h * 0.22 + 18], fill=stripe)
    out.alpha_composite(top, (0, 0))
    del d
    return out


def _lamp_glow(c, x, y, r, rgb=(255, 196, 120), strength=0.55) -> None:
    paper.glow(c, x, y, r, rgb, strength)


# --------------------------------------------------------------------------- #
# The board a graphic beat is drawn on
# --------------------------------------------------------------------------- #
def _board(c: Image.Image, *, style: str, key) -> tuple[tuple, bool]:
    x0, y0, x1, y1 = BOARD_BOX
    w, h = x1 - x0, y1 - y0
    if style == "chalk":
        face, frame, dark = (40, 62, 52), (132, 88, 50), True
    elif style == "screen":
        face, frame, dark = (24, 30, 52), (30, 30, 36), True
    else:
        face, frame, dark = (246, 242, 232), (184, 188, 196), False
    board = paper.rect(w, h, frame, key=("boardframe", key), radius=8)
    inner = paper.rect(w - 44, h - 44, face, key=("boardface", key), radius=4,
                       mottle=0.9 if dark else 0.4)
    board.alpha_composite(inner, (22, 22))
    paper.lay(c, board, x0, y0, offset=(8, 14), blur=12, strength=0.5)
    if style == "chalk":
        tray = paper.rect(w - 80, 20, shade(frame, 0.9), key=("tray", key))
        paper.lay(c, tray, x0 + 40, y1 - 6, offset=(0, 8), blur=6)
    return (x0 + 46, y0 + 40, x1 - 46, y1 - 40), dark


# --------------------------------------------------------------------------- #
# Interiors
# --------------------------------------------------------------------------- #
def _newsroom(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (34, 44, 74), key=key, pattern="panels", trim=(24, 30, 52))
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="screen", key=key)
    else:
        # A wall of screens, each glowing in the story's tone or a cool blue.
        sw, sh, gap = 300, 190, 26
        cols, rows = 3, 3
        ox = CX - (cols * sw + (cols - 1) * gap) // 2
        oy = 380
        for r in range(rows):
            for k in range(cols):
                x, y = ox + k * (sw + gap), oy + r * (sh + gap)
                tint = spec.accent if (r + k + spec.variant) % 3 == 0 else (64, 110, 190)
                face = paper.gradient(sw - 24, sh - 24, shade(tint, 1.15), shade(tint, 0.55))
                fd = ImageDraw.Draw(face)
                for line in range(3):
                    ly = 36 + line * 34
                    fd.rectangle([20, ly, 20 + (sw - 90) * (0.9 - line * 0.25),
                                  ly + 14], fill=(255, 255, 255, 120))
                scr = paper.rect(sw, sh, (20, 20, 26), key=("scr", key, r, k), radius=8)
                scr.alpha_composite(face, (12, 12))
                paper.lay(c, scr, x, y, offset=(6, 10), blur=10, strength=0.55)
        live = paper.rect(120, 52, (206, 52, 40), key=("live", key), radius=6)
        from .. import fonts
        ImageDraw.Draw(live).text((60, 26), "LIVE", font=fonts.label_font(30, 800),
                                  fill=(255, 250, 240), anchor="mm")
        paper.lay(c, live, ox + 20, oy + 20, offset=(3, 5), blur=4)
        _lamp_glow(c, CX, oy + 300, 520, (110, 150, 255), 0.30)
    _floor(c, "planks", (60, 44, 40), key=key)
    # Pip anchors behind the desk, which is what makes this a newsroom.
    desk = _desk(860, 250, (30, 38, 66), key=key, stripe=spec.accent)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    paper.lay(front, desk, CX - desk.width // 2, FLOOR_MARK - 150,
              offset=(0, 18), blur=16, strength=0.5)
    b.front = front
    b.pip = (CX, FLOOR_MARK - 40)
    return b


def _parliament(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (92, 40, 44), key=key, pattern="panels", trim=WOOD_DARK)
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    else:
        _window(c, 130, 420, 230, 520, time=spec.time, key=(key, 1), arched=True,
                frame=(226, 206, 160))
        _window(c, SET_W - 360, 420, 230, 520, time=spec.time, key=(key, 2),
                arched=True, frame=(226, 206, 160))
        # The seal: concentric card discs and a star.
        for r, col in ((150, (214, 172, 86)), (124, (122, 44, 40)), (96, (232, 200, 120))):
            disc = paper.ellipse(2 * r, 2 * r, col, key=("seal", r))
            paper.lay(c, disc, CX - r, 600 - r, offset=(5, 8), blur=8)
        s_img, sx, sy = paper.poly(paper.star(CX, 600, 70, 30), (122, 44, 40),
                                   key=("sealstar",))
        paper.lay(c, s_img, sx, sy, offset=(3, 4), blur=3)
        _flag(c, 420, 760, (40, 64, 130), key=(key, "f1"))
        _flag(c, SET_W - 640, 760, shade(spec.accent, 0.85), key=(key, "f2"))
    _floor(c, "planks", (118, 46, 46), key=key, rug=((150, 40, 44), (214, 172, 86)))
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    podium = paper.rect(420, 330, WOOD, key=("podium", key), radius=8)
    pd = ImageDraw.Draw(podium)
    pd.rectangle([30, 40, 390, 300], outline=WOOD_DARK, width=8)
    top = paper.rect(480, 40, shade(WOOD, 1.2), key=("podtop", key), radius=6)
    pod = Image.new("RGBA", (480, 380), (0, 0, 0, 0))
    pod.alpha_composite(podium, (30, 40))
    pod.alpha_composite(top, (0, 10))
    disc = paper.ellipse(110, 110, (214, 172, 86), key=("podseal",))
    pod.alpha_composite(disc, (185, 150))
    paper.lay(front, pod, CX + 40, FLOOR_MARK - 250, offset=(6, 16), blur=14)
    mic = paper.rect(12, 120, (40, 40, 44), key=("mic",))
    paper.lay(front, mic, CX + 120, FLOOR_MARK - 360, offset=(4, 4), blur=4)
    head = paper.ellipse(34, 44, (30, 30, 34), key=("michead",))
    paper.lay(front, head, CX + 109, FLOOR_MARK - 392, offset=(3, 3), blur=3)
    b.front = front
    b.pip = (CX - 170, FLOOR_MARK)
    _lamp_glow(c, CX, 560, 560, (255, 200, 140), 0.30)
    return b


def _courtroom(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (110, 76, 52), key=key, pattern="panels", trim=WOOD_DARK)
    b = Built(back=c)
    for x in (70, SET_W - 170):
        col = paper.rect(100, HORIZON - 300, (226, 214, 190), key=("column", x))
        cd = ImageDraw.Draw(col)
        for fx in range(16, 100, 22):
            cd.line([(fx, 0), (fx, col.height)], fill=(196, 182, 156), width=5)
        paper.lay(c, col, x, 300, offset=(8, 0), blur=10)
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    else:
        # Scales of justice, as card.
        sx, sy = CX, 470
        beam = paper.rect(360, 16, (214, 172, 86), key=("beam",))
        paper.lay(c, beam, sx - 180, sy, offset=(4, 6), blur=5)
        post = paper.rect(18, 220, (214, 172, 86), key=("post",))
        paper.lay(c, post, sx - 9, sy, offset=(4, 6), blur=5)
        for px in (sx - 170, sx + 110):
            pan = paper.ellipse(120, 36, (214, 172, 86), key=("pan", px))
            d = ImageDraw.Draw(c)
            d.line([(px + 10, sy + 8), (px + 60, sy + 120)], fill=(170, 130, 60), width=4)
            d.line([(px + 110, sy + 8), (px + 60, sy + 120)], fill=(170, 130, 60), width=4)
            paper.lay(c, pan, px, sy + 110, offset=(4, 6), blur=5)
        # The bench.
        bench = paper.rect(SET_W - 260, 250, WOOD_DARK, key=("bench", key), radius=6)
        bd = ImageDraw.Draw(bench)
        for px in range(30, bench.width - 30, 180):
            bd.rectangle([px, 40, px + 150, 210], outline=shade(WOOD_DARK, 0.8), width=6)
        paper.lay(c, bench, 130, HORIZON - 260, offset=(0, 10), blur=10)
        gavel = paper.rect(130, 36, (90, 52, 30), key=("gavel",), radius=10)
        paper.lay(c, paper.rotated(gavel, 18), CX + 150, HORIZON - 320,
                  offset=(5, 8), blur=6)
    _floor(c, "planks", (128, 46, 44), key=key)
    b.pip = (CX - 60, FLOOR_MARK)
    _lamp_glow(c, CX, 420, 540, (255, 214, 160), 0.30)
    return b


def _trading(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (22, 30, 52), key=key, pattern="plain", trim=(14, 18, 34))
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="screen", key=key)
    else:
        up = spec.trend != "down"
        line_col = (64, 200, 132) if up else (232, 84, 64)
        board = paper.rect(940, 560, (16, 20, 36), key=("chartboard", key), radius=10)
        d = ImageDraw.Draw(board)
        for gy in range(60, 560, 80):
            d.line([(30, gy), (910, gy)], fill=(40, 48, 76), width=2)
        rng = Rng("chart", key)
        pts, y = [], (430 if up else 140)
        for i in range(13):
            x = 40 + i * 72
            y += (-1 if up else 1) * rng.uniform(5, 45) + rng.uniform(-30, 30)
            y = max(70, min(500, y))
            pts.append((x, y))
        for i, (x, yy) in enumerate(pts):
            bar_h = 40 + rng.uniform(0, 80)
            d.rectangle([x - 14, 530 - bar_h, x + 14, 530], fill=(46, 58, 96))
        d.line(pts, fill=line_col, width=12, joint="curve")
        ex, ey = pts[-1]
        d.polygon([(ex + 30, ey), (ex - 10, ey - 30), (ex - 10, ey + 30)],
                  fill=line_col)
        paper.lay(c, board, CX - 470, 420, offset=(8, 14), blur=14, strength=0.6)
        _lamp_glow(c, CX, 700, 520, line_col, 0.28)
        # Ticker strip: blocks, not symbols. No invented prices on screen.
        strip = paper.rect(SET_W, 60, (12, 14, 24), key=("ticker", key))
        sd = ImageDraw.Draw(strip)
        for x in range(10, SET_W, 110):
            colr = (64, 200, 132) if (x // 110 + spec.variant) % 3 else (232, 84, 64)
            sd.rectangle([x, 22, x + 60, 38], fill=(200, 204, 214))
            sd.polygon([(x + 72, 38), (x + 84, 22), (x + 96, 38)], fill=colr)
        paper.lay(c, strip, 0, 1040, offset=(0, 8), blur=8)
    _floor(c, "tiles", (44, 44, 56), key=key)
    desk = _desk(700, 200, (40, 44, 60), key=key, stripe=spec.accent)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    paper.lay(front, desk, CX - 350 + 160, FLOOR_MARK - 110, offset=(0, 16), blur=14)
    b.front = front
    b.pip = (CX - 200, FLOOR_MARK)
    return b


def _lab(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (196, 222, 210), key=key, pattern="tiles", trim=(120, 150, 140))
    b = Built(back=c)
    b.board, b.board_dark = _board(c, style="chalk", key=key)
    if not spec.board:
        # Doodles on the chalkboard: curves and arrows, never fake equations.
        bx0, by0, bx1, by1 = b.board
        d = ImageDraw.Draw(c)
        chalk = (226, 232, 220)
        d.arc([bx0 + 40, by0 + 40, bx0 + 300, by0 + 260], 200, 340, fill=chalk, width=6)
        d.line([(bx0 + 360, by1 - 60), (bx0 + 360, by0 + 40), (bx1 - 60, by0 + 40)],
               fill=chalk, width=5)
        pts = [(bx0 + 380 + i * 40, by1 - 80 - (i ** 1.6) * 9) for i in range(10)]
        d.line(pts, fill=(250, 214, 120), width=7)
        for i in range(3):
            d.ellipse([bx0 + 80 + i * 70, by1 - 120, bx0 + 120 + i * 70, by1 - 80],
                      outline=chalk, width=5)
        b.board = None
    _floor(c, "tiles", (210, 214, 206), key=key)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    table = _desk(560, 170, (236, 238, 232), key=("labtable", key))
    paper.lay(front, table, CX + 40, FLOOR_MARK - 120, offset=(0, 14), blur=12)
    rng = Rng("flasks", key)
    for i in range(3):
        col = rng.choice(((86, 196, 150), (232, 120, 90), (120, 140, 232), (240, 196, 80)))
        fx = CX + 110 + i * 150
        body, x0, y0 = paper.poly([(fx, FLOOR_MARK - 290), (fx + 30, FLOOR_MARK - 290),
                                   (fx + 30, FLOOR_MARK - 230), (fx + 80, FLOOR_MARK - 140),
                                   (fx - 50, FLOOR_MARK - 140), (fx, FLOOR_MARK - 230)],
                                  (220, 236, 240), key=("flask", i))
        paper.lay(front, body, x0, y0, offset=(4, 6), blur=5)
        liquid, lx, ly = paper.poly([(fx - 30, FLOOR_MARK - 180), (fx + 60, FLOOR_MARK - 180),
                                     (fx + 80, FLOOR_MARK - 142), (fx - 50, FLOOR_MARK - 142)],
                                    col, key=("liquid", i))
        front.alpha_composite(liquid, (lx, ly))
    b.front = front
    b.pip = (CX - 220, FLOOR_MARK)
    _lamp_glow(c, CX, 300, 600, (255, 255, 240), 0.25)
    return b


def _server(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (20, 24, 34), key=key, pattern="plain", trim=(12, 14, 20))
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="screen", key=key)
    else:
        rng = Rng("racks", key)
        for i, x in enumerate((60, 330, 600, 870)):
            rack = paper.rect(250, 760, (38, 42, 54), key=("rack", i), radius=6)
            rd = ImageDraw.Draw(rack)
            for row in range(16):
                y = 30 + row * 44
                rd.rectangle([20, y, 230, y + 34], fill=(26, 28, 38))
                for led in range(4):
                    on = rng.random() < 0.6
                    col = (86, 230, 160) if on else (60, 70, 90)
                    if on and rng.random() < 0.18:
                        col = (255, 170, 60)
                    rd.ellipse([150 + led * 18, y + 12, 160 + led * 18, y + 22], fill=col)
                    if on:
                        b.lights.append((x + 155 + led * 18, 420 + y + 17, 6))
            paper.lay(c, rack, x, 420, offset=(10, 14), blur=12, strength=0.6)
        _lamp_glow(c, CX, 820, 560, (80, 200, 255), 0.30)
    _floor(c, "tiles", (34, 38, 50), key=key)
    b.pip = (CX, FLOOR_MARK)
    return b


def _maproom(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (66, 52, 44), key=key, pattern="panels", trim=WOOD_DARK)
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    else:
        mw, mh = 960, 560
        sea = (190, 206, 196) if not spec.sober else (170, 176, 172)
        land = (226, 206, 160) if not spec.sober else (206, 196, 176)
        m = paper.rect(mw, mh, sea, key=("map", key), radius=4)
        md = ImageDraw.Draw(m)
        for gx in range(0, mw, 80):
            md.line([(gx, 0), (gx, mh)], fill=shade(sea, 0.92), width=2)
        for gy in range(0, mh, 80):
            md.line([(0, gy), (mw, gy)], fill=shade(sea, 0.92), width=2)
        for shape in _CONTINENTS:
            pts = [(x * mw, y * mh) for x, y in shape]
            md.polygon(pts, fill=land)
        if not spec.sober:
            rng = Rng("pins", key)
            pins = [(rng.uniform(0.2, 0.8) * mw, rng.uniform(0.25, 0.7) * mh)
                    for _ in range(4)]
            md.line(pins, fill=(196, 52, 40), width=4)
            for px, py in pins:
                md.ellipse([px - 14, py - 14, px + 14, py + 14], fill=(206, 52, 40))
        frame = paper.rect(mw + 40, mh + 40, (120, 82, 46), key=("mapframe", key))
        frame.alpha_composite(m, (20, 20))
        paper.lay(c, frame, CX - (mw + 40) // 2, 400, offset=(8, 14), blur=12)
    _floor(c, "planks", WOOD_DARK, key=key)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    if not spec.sober:
        # A globe on a stand at the right.
        gx, gy = SET_W - 230, FLOOR_MARK - 330
        stand = paper.rect(26, 250, (150, 110, 60), key=("gstand",))
        paper.lay(front, stand, gx + 87, gy + 150, offset=(5, 6), blur=5)
        foot = paper.ellipse(150, 40, (150, 110, 60), key=("gfoot",))
        paper.lay(front, foot, gx + 25, gy + 390, offset=(0, 6), blur=6)
        globe = paper.ellipse(200, 200, (110, 160, 200), key=("globe",))
        gd = ImageDraw.Draw(globe)
        gd.polygon([(40, 60), (110, 40), (120, 100), (70, 140), (50, 110)], fill=(140, 180, 110))
        gd.polygon([(130, 120), (170, 110), (160, 170), (130, 160)], fill=(140, 180, 110))
        paper.lay(front, globe, gx, gy, offset=(6, 10), blur=8)
    b.front = front
    b.pip = (CX - 130, FLOOR_MARK)
    _lamp_glow(c, CX, 650, 600, (255, 210, 150), 0.22 if spec.sober else 0.32)
    return b


def _home(spec: SetSpec, key) -> Built:
    c = _canvas()
    _wall(c, (214, 176, 140), key=key, pattern="stripes", trim=(240, 232, 216))
    b = Built(back=c)
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    else:
        _window(c, 150, 430, 380, 470, time=spec.time, key=(key, "w"), city=True)
        _frame_on_wall(c, SET_W - 400, 470, 230, 290, key=key, inner=(120, 160, 140))
        _lamp_glow(c, 340, 620, 420, (255, 230, 180), 0.35)
    _floor(c, "planks", (168, 112, 70), key=key, rug=((76, 112, 150), (232, 196, 110)))
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    sofa = paper.rect(520, 220, (96, 128, 112), key=("sofa", key), radius=30)
    arm = paper.rect(90, 260, shade((96, 128, 112), 0.9), key=("arm", key), radius=30)
    s = Image.new("RGBA", (700, 300), (0, 0, 0, 0))
    s.alpha_composite(sofa, (90, 60))
    s.alpha_composite(arm, (0, 30))
    s.alpha_composite(arm, (610, 30))
    paper.lay(c, s, SET_W - 640, HORIZON - 120, offset=(0, 12), blur=12)
    lamp_pole = paper.rect(16, 520, (60, 50, 44), key=("lamp",))
    paper.lay(c, lamp_pole, 120, HORIZON - 360, offset=(4, 6), blur=5)
    shade_img, sx, sy = paper.poly([(70, HORIZON - 420), (190, HORIZON - 420),
                                    (220, HORIZON - 330), (40, HORIZON - 330)],
                                   (246, 214, 150), key=("lampshade",))
    paper.lay(c, shade_img, sx, sy, offset=(5, 8), blur=6)
    _lamp_glow(c, 130, HORIZON - 300, 300, (255, 210, 140), 0.45)
    b.front = front
    b.pip = (CX - 60, FLOOR_MARK)
    return b


def _skyline_office(spec: SetSpec, key) -> Built:
    c = _canvas()
    time = spec.time if spec.time in ("dusk", "night") else "dusk"
    top, bottom = _sky(time)
    c.alpha_composite(paper.gradient(SET_W, HORIZON, top, bottom))
    city = Image.new("RGBA", (SET_W, HORIZON), (0, 0, 0, 0))
    _skyline_into(city, key=key, lit=True, base=HORIZON - 40)
    city = city.filter(ImageFilter.GaussianBlur(1.2))
    c.alpha_composite(city)
    b = Built(back=c)
    # The glass wall: mullions over the view.
    d = ImageDraw.Draw(c)
    for x in range(0, SET_W, 297):
        d.rectangle([x - 9, 0, x + 9, HORIZON], fill=(30, 30, 38))
    d.rectangle([0, 360, SET_W, 376], fill=(30, 30, 38))
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    _floor(c, "tiles", (58, 52, 60), key=key)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    desk = _desk(620, 190, (64, 52, 46), key=("office", key))
    paper.lay(front, desk, CX + 10, FLOOR_MARK - 120, offset=(0, 16), blur=14)
    laptop = paper.rect(220, 140, (200, 204, 214), key=("laptop",), radius=8)
    ImageDraw.Draw(laptop).rectangle([14, 14, 206, 126], fill=(60, 90, 160))
    paper.lay(front, laptop, CX + 220, FLOOR_MARK - 250, offset=(5, 8), blur=6)
    plant_pot = paper.rect(90, 100, (196, 104, 70), key=("pot",), radius=10)
    paper.lay(front, plant_pot, CX + 480, FLOOR_MARK - 220, offset=(4, 6), blur=5)
    for i, ang in enumerate((-40, -10, 20, 45)):
        leaf = paper.ellipse(50, 150, (70, 140, 90), key=("leaf", i))
        paper.lay(front, paper.rotated(leaf, ang), CX + 470 + i * 12,
                  FLOOR_MARK - 360, offset=(3, 5), blur=4)
    b.front = front
    b.pip = (CX - 190, FLOOR_MARK)
    return b


# --------------------------------------------------------------------------- #
# Exteriors
# --------------------------------------------------------------------------- #
def _street(spec: SetSpec, key) -> Built:
    c = _canvas()
    top, bottom = _sky(spec.time)
    c.alpha_composite(paper.gradient(SET_W, HORIZON, top, bottom))
    rng = Rng("street", key)
    x = -40
    palette = ((200, 120, 90), (226, 196, 150), (120, 140, 170), (170, 96, 80),
               (214, 168, 110), (110, 120, 110))
    while x < SET_W:
        bw = rng.uniform(220, 320)
        bh = rng.uniform(520, 820)
        col = rng.choice(palette)
        bld = paper.rect(int(bw), int(bh), col, key=("bld", x))
        bd = ImageDraw.Draw(bld)
        lit = spec.time != "day"
        for wy in range(60, int(bh) - 120, 110):
            for wx in range(30, int(bw) - 60, 80):
                win = (255, 214, 130) if (lit and rng.random() < 0.6) else shade(col, 0.6)
                bd.rectangle([wx, wy, wx + 44, wy + 64], fill=win)
        paper.lay(c, bld, x, HORIZON - bh + 40, offset=(10, 0), blur=10)
        x += bw + rng.uniform(-10, 10)
    b = Built(back=c)
    # Pavement and road in perspective: two kerbs and a dashed centre line,
    # all running to the vanishing point.
    road = paper.textured(SET_W, SET_H - HORIZON, (84, 80, 86), key=("road", key))
    rd = ImageDraw.Draw(road)
    rd.rectangle([0, 0, SET_W, 60], fill=(156, 150, 152))
    vx, vy = CX, EYE - HORIZON
    rh = road.height

    def toward(bx, y):
        t = (y - vy) / (rh - vy)
        return vx + (bx - vx) * t

    for bx in (-700, SET_W + 700):
        rd.line([(toward(bx, 60), 60), (bx, rh)], fill=(196, 190, 186), width=10)
    for k in range(12):
        y0 = 70 + (rh - 70) * (k / 12) ** 1.5
        y1 = 70 + (rh - 70) * ((k + 0.5) / 12) ** 1.5
        w0, w1 = 3 + 14 * (y0 / rh), 3 + 14 * (y1 / rh)
        rd.polygon([(toward(CX, y0) - w0, y0), (toward(CX, y0) + w0, y0),
                    (toward(CX, y1) + w1, y1), (toward(CX, y1) - w1, y1)],
                   fill=(236, 214, 140))
    c.alpha_composite(road, (0, HORIZON))
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    for lx in (90, SET_W - 120):
        pole = paper.rect(18, 560, (40, 44, 52), key=("lamp", lx))
        paper.lay(c, pole, lx, HORIZON - 480, offset=(5, 6), blur=5)
        bulb = paper.ellipse(60, 40, (255, 226, 160), key=("bulb", lx))
        paper.lay(c, bulb, lx - 20, HORIZON - 500, offset=(2, 3), blur=3)
        if spec.time != "day":
            _lamp_glow(c, lx + 9, HORIZON - 480, 260, (255, 200, 120), 0.5)
    # The crowd: blocky paper people with placards, in front of the buildings.
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    if not spec.sober:
        for row, (y, scale) in enumerate(((HORIZON + 40, 0.75), (HORIZON + 160, 0.9))):
            for i in range(7):
                px = 40 + i * 170 + row * 70 + rng.uniform(-20, 20)
                if abs(px - CX) < 180 and row == 1:
                    continue
                _person(c, px, y, scale, rng, sign=rng.random() < 0.55)
    b.front = front
    b.pip = (CX, FLOOR_MARK)
    return b


def _person(c, x, y, s, rng, sign: bool) -> None:
    body = rng.choice(((60, 90, 150), (170, 60, 60), (70, 120, 90), (200, 150, 60),
                       (90, 80, 120)))
    skin = rng.choice(((236, 196, 160), (196, 140, 100), (140, 96, 66), (250, 214, 180)))
    w, h = int(90 * s), int(120 * s)
    torso = paper.rect(w, h, body, key=("torso", x, y), radius=6)
    head = paper.rect(int(70 * s), int(70 * s), skin, key=("head", x, y), radius=6)
    hd = ImageDraw.Draw(head)
    e = int(8 * s)
    hd.rectangle([int(18 * s), int(26 * s), int(18 * s) + e, int(26 * s) + e * 2], fill=INK)
    hd.rectangle([int(44 * s), int(26 * s), int(44 * s) + e, int(26 * s) + e * 2], fill=INK)
    paper.lay(c, torso, x, y - h, offset=(5, 6), blur=5)
    paper.lay(c, head, x + int(10 * s), y - h - int(66 * s), offset=(4, 5), blur=4)
    if sign:
        stick = paper.rect(int(10 * s), int(170 * s), (150, 110, 70), key=("stick", x))
        paper.lay(c, stick, x + w - int(6 * s), y - h - int(150 * s), offset=(3, 4), blur=3)
        card = paper.rect(int(130 * s), int(90 * s), (244, 238, 222), key=("card", x, y))
        cd = ImageDraw.Draw(card)
        for k in range(2):
            cd.rectangle([int(16 * s), int((22 + k * 30) * s), int((110 - k * 30) * s),
                          int((36 + k * 30) * s)], fill=(196, 70, 50))
        paper.lay(c, paper.rotated(card, rng.uniform(-8, 8)), x + w - int(70 * s),
                  y - h - int(230 * s), offset=(4, 6), blur=5)


def _harbour(spec: SetSpec, key) -> Built:
    c = _canvas()
    top, bottom = _sky(spec.time)
    c.alpha_composite(paper.gradient(SET_W, HORIZON, top, bottom))
    rng = Rng("harbour", key)
    b = Built(back=c)
    # Cranes against the sky.
    d = ImageDraw.Draw(c)
    for cx in (160, SET_W - 260):
        d.rectangle([cx, 560, cx + 26, HORIZON - 40], fill=(214, 110, 60))
        d.rectangle([cx - 140, 560, cx + 260, 586], fill=(214, 110, 60))
        d.line([(cx + 13, 480), (cx - 140, 572)], fill=(214, 110, 60), width=6)
        d.line([(cx + 13, 480), (cx + 260, 572)], fill=(214, 110, 60), width=6)
    # Sea.
    sea_top = HORIZON - 150
    for i, col in enumerate(((40, 84, 130), (34, 72, 116), (28, 60, 100))):
        y = sea_top + i * 120
        wave = Image.new("RGBA", (SET_W, SET_H - y), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wave)
        pts = [(0, 30)]
        for x in range(0, SET_W + 60, 60):
            pts.append((x, 30 + 14 * math.sin(x / 50 + i)))
        pts += [(SET_W, SET_H - y), (0, SET_H - y)]
        wd.polygon(pts, fill=col)
        if i == 0:
            # The ship sits between the first and second swell.
            paper.lay(c, wave.crop((0, 0, SET_W, 200)), 0, y, shadow=False)
            _ship(c, CX + 60, y + 40, rng, key)
        else:
            tex = paper.textured(wave.width, wave.height, col, key=("sea", i))
            tex.putalpha(wave.getchannel("A"))
            paper.lay(c, tex, 0, y, offset=(0, -6), blur=8, strength=0.3)
    # The dock in front, planks, with barrels.
    dock = paper.textured(SET_W, SET_H - (HORIZON + 140), (130, 96, 64), key=("dock", key))
    dd = ImageDraw.Draw(dock)
    for y in range(0, dock.height, 70):
        dd.line([(0, y), (SET_W, y)], fill=(96, 70, 46), width=4)
    paper.lay(c, dock, 0, HORIZON + 140, offset=(0, -10), blur=10)
    if spec.board:
        b.board, b.board_dark = _board(c, style="white", key=key)
    front = Image.new("RGBA", (SET_W, SET_H), (0, 0, 0, 0))
    for i, bx in enumerate((SET_W - 330, SET_W - 200, SET_W - 270)):
        by = FLOOR_MARK - 220 - (100 if i == 2 else 0)
        barrel = paper.rect(120, 170, (40, 70, 120) if i != 1 else (200, 70, 50),
                            key=("barrel", i), radius=14)
        bd = ImageDraw.Draw(barrel)
        bd.rectangle([0, 40, 120, 52], fill=(30, 30, 36))
        bd.rectangle([0, 118, 120, 130], fill=(30, 30, 36))
        paper.lay(front, barrel, bx, by, offset=(6, 10), blur=8)
    b.front = front
    b.pip = (CX - 160, FLOOR_MARK)
    return b


def _ship(c, x, y, rng, key) -> None:
    hull, hx, hy = paper.poly([(x - 380, y - 60), (x + 380, y - 60), (x + 330, y + 40),
                               (x - 340, y + 40)], (60, 64, 78), key=("hull", key))
    colours = ((206, 86, 60), (46, 110, 170), (230, 180, 70), (70, 140, 100))
    for row in range(3):
        for k in range(9):
            if row == 2 and k in (0, 8):
                continue
            box = paper.rect(76, 46, rng.choice(colours), key=("box", row, k))
            paper.lay(c, box, x - 340 + k * 78, y - 110 - row * 48, offset=(3, 4), blur=3)
    paper.lay(c, hull, hx, hy, offset=(4, 6), blur=6)
    bridge = paper.rect(90, 120, (236, 232, 222), key=("bridge", key))
    paper.lay(c, bridge, x + 260, y - 220, offset=(4, 6), blur=5)


def _space(spec: SetSpec, key) -> Built:
    c = _canvas()
    c.alpha_composite(paper.gradient(SET_W, SET_H, (8, 10, 30), (30, 26, 64)))
    rng = Rng("space", key)
    d = ImageDraw.Draw(c)
    for _ in range(160):
        sx, sy = rng.uniform(0, SET_W), rng.uniform(0, HORIZON)
        r = rng.uniform(1, 3.4)
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(250, 244, 220))
    planet = paper.ellipse(420, 420, (214, 120, 90), key=("planet", key))
    pd = ImageDraw.Draw(planet)
    for k in range(4):
        pd.ellipse([20, 100 + k * 60, 400, 140 + k * 60], fill=(196, 104, 80))
    paper.lay(c, planet, SET_W - 420, 340, offset=(10, 14), blur=14)
    ring = Image.new("RGBA", (620, 160), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, 619, 159], outline=(240, 214, 160), width=14)
    paper.lay(c, paper.rotated(ring, -12), SET_W - 540, 480, offset=(6, 8), blur=6)
    paper.glow(c, SET_W - 210, 550, 420, (255, 160, 120), 0.25)
    b = Built(back=c)
    ground = paper.textured(SET_W, SET_H - HORIZON + 60, (150, 148, 160), key=("moon", key))
    gd = ImageDraw.Draw(ground)
    for _ in range(14):
        cx, cy = rng.uniform(0, SET_W), rng.uniform(60, ground.height)
        rw = rng.uniform(40, 140) * (0.4 + cy / ground.height)
        gd.ellipse([cx - rw, cy - rw * 0.3, cx + rw, cy + rw * 0.3], fill=(124, 122, 136))
        gd.ellipse([cx - rw * 0.8, cy - rw * 0.2, cx + rw * 0.8, cy + rw * 0.26],
                   fill=(140, 138, 152))
    mask = paper.mask_of(SET_W, ground.height, lambda md: md.polygon(
        [(0, 60)] + [(x, 40 + 24 * math.sin(x / 140)) for x in range(0, SET_W + 40, 40)]
        + [(SET_W, ground.height), (0, ground.height)], fill=255))
    ground.putalpha(mask)
    paper.lay(c, ground, 0, HORIZON - 60, offset=(0, -8), blur=10)
    if spec.board:
        b.board, b.board_dark = _board(c, style="screen", key=key)
    else:
        rocket, rx, ry = paper.poly([(240, 520), (300, 640), (300, 1000), (180, 1000),
                                     (180, 640)], (236, 232, 222), key=("rocket",))
        paper.lay(c, rocket, rx, ry + 60, offset=(8, 10), blur=8)
        fin, fx, fy = paper.poly([(180, 900), (130, 1060), (180, 1000)], (206, 70, 50), key=("fin1",))
        paper.lay(c, fin, fx, fy + 60, offset=(4, 6), blur=5)
        fin2, fx, fy = paper.poly([(300, 900), (350, 1060), (300, 1000)], (206, 70, 50), key=("fin2",))
        paper.lay(c, fin2, fx, fy + 60, offset=(4, 6), blur=5)
        win = paper.ellipse(60, 60, (80, 150, 220), key=("porthole",))
        paper.lay(c, win, 210, 760, offset=(3, 4), blur=3)
    b.pip = (CX + 120, FLOOR_MARK)
    return b


def _board_set(spec: SetSpec, key) -> Built:
    """The flat set: a felt board with cut-outs pinned to it."""
    c = _canvas()
    felt = (48, 96, 72) if spec.variant % 2 == 0 else (150, 110, 70)
    c.alpha_composite(paper.textured(SET_W, SET_H, felt, key=("felt", key), mottle=1.0))
    b = Built(back=c)
    b.board, b.board_dark = _board(c, style="white", key=key)
    if not spec.board:
        b.board = None
    b.pip = (CX, FLOOR_MARK + 80)
    return b


# Very rough continents, in map-relative coordinates, enough to read as a map.
_CONTINENTS = (
    ((0.08, 0.18), (0.28, 0.12), (0.32, 0.30), (0.24, 0.44), (0.18, 0.40), (0.10, 0.30)),
    ((0.24, 0.50), (0.32, 0.52), (0.30, 0.78), (0.25, 0.86), (0.22, 0.66)),
    ((0.44, 0.16), (0.56, 0.14), (0.58, 0.26), (0.48, 0.30), (0.44, 0.24)),
    ((0.46, 0.34), (0.58, 0.34), (0.60, 0.56), (0.52, 0.74), (0.47, 0.54)),
    ((0.58, 0.14), (0.86, 0.14), (0.90, 0.32), (0.76, 0.44), (0.64, 0.40), (0.58, 0.26)),
    ((0.78, 0.62), (0.90, 0.60), (0.92, 0.74), (0.80, 0.76)),
)


_BUILDERS = {
    "newsroom": _newsroom, "parliament": _parliament, "courtroom": _courtroom,
    "street": _street, "skyline": _skyline_office, "trading": _trading,
    "harbour": _harbour, "lab": _lab, "server": _server, "maproom": _maproom,
    "space": _space, "home": _home, "board": _board_set,
}


@lru_cache(maxsize=12)
def build(spec: SetSpec) -> Built:
    """The set for `spec`, built once and shared by every frame of its beats."""
    builder = _BUILDERS.get(spec.name, _newsroom)
    key = (spec.name, spec.variant)
    built = builder(spec, key)
    # Depth of field: the back of the set is a touch soft, so Pip, who is in
    # focus, reads as standing in front of it rather than printed on it.
    built.back = built.back.filter(ImageFilter.GaussianBlur(1.4))
    # The front layer is mostly empty; keep only what is drawn, so compositing
    # it each frame costs the desk, not the whole set.
    if built.front is not None:
        box = built.front.getbbox()
        if box is None:
            built.front = None
        else:
            built.front_at = (box[0], box[1])
            built.front = built.front.crop(box)
    return built
