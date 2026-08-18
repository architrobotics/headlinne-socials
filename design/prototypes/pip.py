"""Pip - the Headlinne pixel pigeon.

Named for the BBC pips that have announced the news on the hour since 1924,
and for the 45 carrier pigeons Paul Reuter flew across the Aachen-Brussels
telegraph gap in 1850. Pip carries verified news and nothing else.

Consistency rules, enforced across every pose:
  * 26x24 canvas, front-facing, bilaterally symmetric unless a prop breaks it
  * the body block is byte-identical in every pose; only head and props change
  * cream head, terracotta body, marigold beak and feet - never recoloured
  * eyes are a 2x2 ink block with one white highlight pixel, top-right
  * one-pixel ink outline on exterior edges only, never on interior detail
"""
import base64, io, pathlib
from PIL import Image

W = 26

PAL = {
    '.': None,
    'K': (26, 20, 16),      # ink outline
    'T': (196, 86, 47),     # terracotta body
    'H': (232, 118, 63),    # wing highlight
    'C': (246, 241, 234),   # cream head
    'B': (255, 180, 61),    # beak / feet
    'O': (208, 138, 36),    # beak shadow
    'W': (255, 255, 255),   # eye highlight
    'N': (26, 20, 16),      # pupil
    'M': (63, 221, 156),    # mint - verified
    'P': (247, 241, 230),   # paper
    'S': (188, 176, 160),   # paper rule
    'R': (255, 107, 74),    # coral - alert
}

# The body is identical in every pose. Written once, reused, never edited per-pose.
BODY = """
.....KKKKTTTTTTTTKKKK.....
....KTTHHTTTTTTTTTTHHK....
...KTTHHHTTTTTTTTTTHHHK...
...KTHHHHTTTTTTTTTTHHHK...
...KTHHHHTTTTTTTTTTHHHK...
...KTTHHHTTTTTTTTTTHHTK...
....KTTHTTTTTTTTTTTTHK....
.....KKTTTTTTTTTTTTKK.....
.......KKKKKKKKKKKK.......
........BB......BB........
.......BBBB....BBBB.......
"""

HEAD_OPEN = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCNWCCCCCCNWCCK.....
.....KCCNNCCCCCCNNCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

HEAD_SHUT = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCKKCCCCCCKKCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

HEAD_WIDE = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCNWWCCCCCCNWWCK.....
.....KCNNNCCCCCCNNNCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCRRRRCCCCK.....
......KCCCCCORROCCCK......
.......KKCCCCCCCCKK.......
"""

HEAD_GLANCE = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCCCNWCCCCCCNWK.....
.....KCCCCNNCCCCCCNNK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""


def compose(head: str, body: str = BODY) -> str:
    return "\n".join(_rows(head) + _rows(body))


def _rows(grid: str) -> list[str]:
    return [r for r in grid.strip("\n").split("\n") if r.strip("\n")]


def overlay(grid: str, art: str, ox: int, oy: int) -> str:
    """Stamp a prop onto a composed sprite at (ox, oy). '.' in the prop is transparent."""
    rows = [list(r.ljust(W, ".")) for r in _rows(grid)]
    for y, line in enumerate(_rows(art)):
        for x, ch in enumerate(line):
            if ch != "." and 0 <= oy + y < len(rows) and 0 <= ox + x < W:
                rows[oy + y][ox + x] = ch
    return "\n".join("".join(r) for r in rows)


CHECK = """
......MM
.....MM.
....MM..
.MM.MM..
..MMM...
...M....
"""

QMARK = """
.BBB.
B...B
....B
..BB.
..B..
.....
..B..
"""

BANNER = """
KKKKKKKKKKKKKK
KPPPPPPPPPPPPK
KPSSSPPPSSSSPK
KPPPPPPPPPPPPK
KKKKKKKKKKKKKK
"""

BROADSHEET = """
KKKKKKKKKKKKKKKKKKKK
KPPPPPPPPPPPPPPPPPPK
KPSSSSSSPPPSSSSSSPPK
KPPPPPPPPPPPPPPPPPPK
KPSSSSPPPPSSSSSPPPPK
KPPPPPPPPPPPPPPPPPPK
KKKKKKKKKKKKKKKKKKKK
"""

# The Headlinne "h", pixelated onto Pip's chest. Props cover it in some poses,
# which is fine - it reads as a jersey mark, not a logo lockup.
EMBLEM = """
CC....
CC....
CCCCC.
CC..CC
CC..CC
"""

WING_UP_L = """
KH.
HHK
HHH
.KK
"""

WING_UP_R = """
.HK
KHH
HHH
KK.
"""

def badged(head: str) -> str:
    """Pip with the Headlinne h on his chest. Props stamped after this cover it."""
    return overlay(compose(head), EMBLEM, 10, 14)


SPRITES = {
    "idle":     badged(HEAD_OPEN),
    "carry":    overlay(badged(HEAD_OPEN), BANNER, 6, 15),
    "alert":    overlay(overlay(badged(HEAD_WIDE), WING_UP_L, 1, 10),
                        WING_UP_R, 22, 10),
    "read":     overlay(badged(HEAD_SHUT), BROADSHEET, 3, 14),
    "verified": overlay(badged(HEAD_OPEN), CHECK, 18, 12),
    "puzzled":  overlay(badged(HEAD_GLANCE), QMARK, 20, 1),
}


def render(grid: str, scale: int = 1) -> Image.Image:
    rows = _rows(grid)
    img = Image.new("RGBA", (W, len(rows)), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row.ljust(W, ".")[:W]):
            c = PAL.get(ch)
            if c:
                px[x, y] = (*c, 255)
    return img.resize((W * scale, len(rows) * scale), Image.NEAREST) if scale > 1 else img


if __name__ == "__main__":
    out = pathlib.Path(".")
    for name, grid in SPRITES.items():                      # width guard
        for i, r in enumerate(_rows(grid)):
            assert len(r) == W, f"{name} row {i} is {len(r)}px, expected {W}"

    tiles = []
    for name, grid in SPRITES.items():
        render(grid, 6).save(out / f"pip_{name}.png")
        b = io.BytesIO()
        render(grid, 8).save(b, "PNG", optimize=True)
        (out / f"sprite_{name}.b64").write_text(base64.b64encode(b.getvalue()).decode())
        tiles.append(render(grid, 5))

    gap = 16
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles)
    sheet = Image.new("RGBA", (len(tiles) * (tw + gap) + gap, th + gap * 2), (20, 16, 32, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, (gap + i * (tw + gap), gap), t)
    sheet.save(out / "pip_sheet.png")

    # does the character survive a 26px profile avatar?
    small = Image.new("RGBA", (len(tiles) * 34 + 12, 42), (20, 16, 32, 255))
    for i, grid in enumerate(SPRITES.values()):
        s = render(grid, 1)
        small.paste(s, (12 + i * 34, 9), s)
    small.resize((small.width * 3, small.height * 3), Image.NEAREST).save(out / "pip_small.png")
    print("rendered:", ", ".join(SPRITES))


# --------------------------------------------------------------------------- #
# Animation. Mario-style: a short cycle, big readable steps, no easing.
# --------------------------------------------------------------------------- #
LEGS_MID = """
........BB......BB........
.......BBBB....BBBB.......
"""
LEGS_L = """
......BB..........BB......
.....BBBB........BBBB.....
"""
LEGS_R = """
.........BB....BB.........
........BBBB..BBBB........
"""

HEAD_TALK = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCNWCCCCCCNWCCK.....
.....KCCNNCCCCCCNNCCK.....
.....KCCCCCCBBBBCCCCK.....
.....KCCCCCBKKKKBCCCK.....
......KCCCCBOOOOBCCK......
.......KKCCCCCCCCKK.......
"""


LEGS_TUCK = """
.......BBBB....BBBB.......
..........................
"""
LEGS_LAND = """
.......BBBB....BBBB.......
......BB..BB..BB..BB......
"""

# A wing held straight out, for pointing at whatever is on screen.
WING_OUT_R = """
KHHHK
HHHHH
KHHHK
"""
WING_OUT_L = """
KHHHK
HHHHH
KHHHK
"""


def _legs(grid: str, legs: str) -> str:
    """Swap the bottom two rows (the feet) for a different stride."""
    rows = _rows(grid)
    return "\n".join(rows[:-2] + _rows(legs))


def _bob(grid: str, up: int) -> str:
    """Lift the whole character by `up` pixels, keeping the canvas height."""
    rows = _rows(grid)
    return "\n".join(rows[up:] + ["." * W] * up)


def walk_cycle(head: str = HEAD_OPEN) -> list[str]:
    base = badged(head)
    return [
        _legs(base, LEGS_L),
        _bob(_legs(base, LEGS_MID), 1),
        _legs(base, LEGS_R),
        _bob(_legs(base, LEGS_MID), 1),
    ]


def talk_cycle() -> list[str]:
    return [badged(HEAD_OPEN), badged(HEAD_TALK),
            badged(HEAD_TALK), badged(HEAD_OPEN)]


def _headroom(grid: str, rows_above: int = 6) -> str:
    """Add blank rows on top so a jump has somewhere to go without clipping."""
    return "\n".join(["." * W] * rows_above + _rows(grid))


def jump_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Crouch, launch, hang, land. Four frames is all Mario ever needed."""
    base = badged(head)
    airborne = overlay(overlay(base, WING_UP_L, 1, 10), WING_UP_R, 22, 10)
    return [
        _headroom(_legs(base, LEGS_LAND)),
        _bob(_headroom(_legs(base, LEGS_TUCK)), 3),
        _bob(_headroom(_legs(airborne, LEGS_TUCK)), 6),
        _headroom(_legs(base, LEGS_LAND)),
    ]


def point_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Pip gesturing at the thing on screen. Two frames, small travel."""
    base = badged(head)
    return [overlay(base, WING_OUT_R, 20, 14),
            overlay(base, WING_OUT_R, 22, 11),
            overlay(base, WING_OUT_R, 21, 12)]


def present_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Both wings out - 'here is the thing'."""
    base = badged(head)
    return [overlay(overlay(base, WING_OUT_L, 1, 14), WING_OUT_R, 20, 14),
            overlay(overlay(base, WING_OUT_L, 0, 11), WING_OUT_R, 21, 11),
            overlay(overlay(base, WING_OUT_L, 1, 12), WING_OUT_R, 20, 12)]


def idle_cycle() -> list[str]:
    """A two-frame breath, for when Pip is just standing there."""
    base = badged(HEAD_OPEN)
    return [base, _bob(base, 1)]


def gif(frames: list[str], path, scale: int = 8, ms: int = 150,
        bg=(247, 241, 230)):
    ims = []
    for f in frames:
        layer = render(f, scale)
        flat = Image.new("RGB", layer.size, bg)
        flat.paste(layer, (0, 0), layer)
        ims.append(flat)
    ims[0].save(path, save_all=True, append_images=ims[1:],
                duration=ms, loop=0, optimize=True)
    return path


if __name__ == "__main__":
    gif(walk_cycle(), "pip_walk.gif", ms=140)
    gif(jump_cycle(), "pip_jump.gif", ms=130)
    gif(point_cycle(), "pip_point.gif", ms=320)
    gif(present_cycle(), "pip_present.gif", ms=320)
    gif(talk_cycle(), "pip_talk.gif", ms=180)
    gif(idle_cycle(), "pip_idle.gif", ms=420)
    strip = [render(f, 6) for f in
             (jump_cycle() + point_cycle() + present_cycle())]
    g = 12
    sh = Image.new("RGB", (len(strip) * (strip[0].width + g) + g,
                           strip[0].height + g * 2), (247, 241, 230))
    for i, t in enumerate(strip):
        sh.paste(t, (g + i * (strip[0].width + g), g), t)
    sh.save("pip_posestrip.png")
    print("animated: walk, talk, idle")
