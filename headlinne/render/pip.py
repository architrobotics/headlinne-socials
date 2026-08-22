"""Pip - the Headlinne pixel pigeon.

Named for the BBC pips that have marked the news on the hour since 1924, and for
the 45 carrier pigeons Paul Reuter flew across the Aachen-Brussels telegraph gap
in 1850. That pigeon post became Reuters, which this pipeline still reads every
morning. Pip carries verified news and nothing else.

He exists because the account is automated and therefore cannot have a presenter.
A character is the only way a faceless brand gets a personality that scales to
every post at no cost per post - and it lets the sourcing read as a kindness
rather than a lecture.

Consistency rules, enforced in code rather than by eye:
  * 26px-wide canvas, front-facing, bilaterally symmetric unless a prop breaks it
  * the body block is byte-identical in every pose; only heads and props change
  * cream head, terracotta body, marigold beak and feet - never recoloured, not
    for categories and not for seasons
  * eyes are a 2x2 ink block with one white highlight; only the pupil moves
  * one-pixel ink outline on exterior edges only, never on interior detail
  * every pose must still read at 26px, which is profile-avatar size

Poses are metadata, which is the whole return on having a character. A regular
reader learns the shape of a story from the bird before reading a word:
`chart_up` and `chart_down` carry the direction of a market story, `nod` and
`shake` carry whether the outlets agreed, `investigate` carries a story only one
outlet is running so far. Sensitive stories carry no mascot at all - that rule
lives in the renderers and is not overridable from here.

The animation section is built out of the basic principles rather than out of
tweens: squash and stretch on impact, anticipation before a launch,
follow-through on the wings, and holds for timing. A fixed-rate player gets
non-uniform timing from repeated frames, which is why `hold()` exists instead of
a per-frame duration field - a cycle stays a plain `list[str]` and every
existing caller keeps working unchanged.

`tests/test_pip.py` asserts the width guard and that every animation cycle
actually changes pixels - a beak opening changes no bounding box, so comparing
bounding boxes silently passes a frozen sprite.
"""

from __future__ import annotations

import math

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

# --------------------------------------------------------------------------- #
# Heads. Eleven rows each, and rows 4-8 are `.....K` + 14 interior + `K.....`,
# so a new expression is a matter of editing the interior and nothing else. The
# crown, the jaw and the outline never move: that silhouette is the recognisable
# part, and an expression that redraws it stops being the same bird.
# --------------------------------------------------------------------------- #
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

# Closed arcs, not closed lids. A shut eye reads as asleep; an arc reads as
# pleased, and the difference is one pixel per eye.
HEAD_HAPPY = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCKKCCCCCCKKCCK.....
.....KCKCCKCCCCKCCKCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

HEAD_WINK = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCKKCCCCCCNWCCK.....
.....KCKCCKCCCCCNNCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

# A lid over a pupil rather than a fully shut eye. Half-mast is what reads as
# tired at this size; fully shut just reads as mid-blink.
HEAD_SLEEPY = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCKKCCCCCCKKCCK.....
.....KCCNNCCCCCCNNCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

# The whole eye moved up a row. Losing the lower half of the block is what sells
# an upward look - drawing the pupil higher inside a fixed eye does not.
HEAD_THINK = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCNWCCCCCCNWCCK.....
.....KCCNNCCCCCCNNCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
"""

# White all round a shrunken pupil. This is the one head that breaks the 2x2-eye
# rule, and it earns it: shock is the expression that has to survive being seen
# for a third of a second at thumbnail size.
HEAD_SHOCK = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCWWWCCCCCCWWWCK.....
.....KCWNWCCCCCCWNWCK.....
.....KCWWWCCCCCCWWWCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCRRRRCCCCK.....
......KCCCCCORROCCCK......
.......KKCCCCCCCCKK.......
"""

# Eyes dropped a row, for anything Pip is looking down at - a broadsheet, a
# chart, the ground in front of him.
HEAD_DOWN = """
..........................
.........KKKKKKKK.........
.......KKCCCCCCCCKK.......
......KCCCCCCCCCCCCK......
.....KCCCCCCCCCCCCCCK.....
.....KCCCCCCCCCCCCCCK.....
.....KCCNWCCCCCCNWCCK.....
.....KCCNNCCCCCCNNCCK.....
.....KCCCCCCBBBBCCCCK.....
......KCCCCCOBBOCCCK......
.......KKCCCCCCCCKK.......
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

# Every head, so the guards can walk the set rather than a hand-kept sample.
HEADS = {
    "open": HEAD_OPEN, "shut": HEAD_SHUT, "wide": HEAD_WIDE,
    "glance": HEAD_GLANCE, "happy": HEAD_HAPPY, "wink": HEAD_WINK,
    "sleepy": HEAD_SLEEPY, "think": HEAD_THINK, "shock": HEAD_SHOCK,
    "down": HEAD_DOWN, "talk": HEAD_TALK,
}


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


# --------------------------------------------------------------------------- #
# Props. Any size - overlay() clips them to the canvas.
# --------------------------------------------------------------------------- #
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

# Direction of travel on a market story. Mint rises and coral falls - the same
# two colours the source strip already uses, so a reader learns one vocabulary
# rather than two.
ARROW_UP = """
..M..
.MMM.
MM.MM
..M..
..M..
"""

ARROW_DOWN = """
..R..
..R..
RR.RR
.RRR.
..R..
"""

COIN = """
.KKK.
KBOBK
KBOBK
KBOBK
.KKK.
"""

# A stick mic, for anything breaking.
MIC = """
.KKK.
KWWWK
KWWWK
KWWWK
.KKK.
..K..
.KKK.
"""

# A magnifier, for a story only one outlet is carrying so far.
GLASS = """
.KKKK.
K.WW.K
K.WW.K
.KKKK.
....KK
.....K
"""

BULB = """
.KBK.
KBWBK
KBWBK
.KBK.
..K..
.KKK.
"""

CLOCK = """
.KKK.
KCKCK
KCKCK
KCCCK
.KKK.
"""

ENVELOPE = """
KKKKKKKK
KPPPPPPK
KPSPPSPK
KPPSSPPK
KKKKKKKK
"""

ZZZ = """
..KKK
...K.
..K..
.KKK.
KK...
K....
KK...
"""

BOLT = """
..BB
.BB.
BBBB
.BB.
.B..
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

# Mid-downstroke, so a flap has three positions rather than two. Two positions
# read as a toggle; three read as a wing.
WING_MID_L = """
KHK
HHH
.KK
"""
WING_MID_R = """
KHK
HHH
KK.
"""

# Confetti in three phases. The particles advance and thin out rather than
# blinking on and off in place, which is the difference between a celebration
# and a strobe.
CONFETTI_A = """
.M...R...B
..........
....M.....
"""
CONFETTI_B = """
..........
.M...R...B
....M.....
"""
CONFETTI_C = """
..........
....R.....
.M.......B
"""

# The still version of the burst. The cycle below has blank rows added on top to
# throw confetti into; a single pose does not, so this one sits in the top-right
# corner, which is the only reliably empty part of the canvas.
BURST = """
M.R.B
.....
..M..
"""


def badged(head: str) -> str:
    """Pip with the Headlinne h on his chest. Props stamped after this cover it."""
    return overlay(compose(head), EMBLEM, 10, 14)


def _wings(grid: str, left: str = WING_UP_L, right: str = WING_UP_R,
           y: int = 10, dx: int = 0) -> str:
    """Both wings at a matched height. dx spreads them further from the body."""
    return overlay(overlay(grid, left, 1 - dx, y), right, 22 + dx, y)


SPRITES = {
    "idle":     badged(HEAD_OPEN),
    "carry":    overlay(badged(HEAD_OPEN), BANNER, 6, 15),
    "alert":    _wings(badged(HEAD_WIDE)),
    "read":     overlay(badged(HEAD_DOWN), BROADSHEET, 3, 14),
    "verified": overlay(badged(HEAD_OPEN), CHECK, 18, 12),
    "puzzled":  overlay(badged(HEAD_GLANCE), QMARK, 20, 1),
    # Each added pose is a story shape, not a mood for its own sake.
    #
    # Held props go to the top-right corner, rows 0-6 and columns 20-25. That is
    # the only part of the canvas that is empty in every pose: the body spans
    # almost the full width from row 11 down, so a prop placed beside the chest
    # lands on top of him instead of next to him. QMARK has always been there;
    # the rest now follow it.
    "happy":       badged(HEAD_HAPPY),
    "wink":        badged(HEAD_WINK),
    "sleepy":      overlay(badged(HEAD_SLEEPY), ZZZ, 21, 0),
    "thinking":    overlay(badged(HEAD_THINK), BULB, 21, 0),
    "shocked":     _wings(badged(HEAD_SHOCK)),
    "chart_up":    overlay(badged(HEAD_HAPPY), ARROW_UP, 21, 1),
    "chart_down":  overlay(badged(HEAD_SHOCK), ARROW_DOWN, 21, 1),
    "money":       overlay(badged(HEAD_OPEN), COIN, 21, 1),
    "breaking":    overlay(badged(HEAD_WIDE), MIC, 21, 0),
    "investigate": overlay(badged(HEAD_GLANCE), GLASS, 20, 0),
    "deliver":     overlay(badged(HEAD_HAPPY), ENVELOPE, 9, 15),
    "waiting":     overlay(badged(HEAD_SLEEPY), CLOCK, 21, 1),
    "cheer":       overlay(_wings(badged(HEAD_HAPPY)), BURST, 21, 0),
    "urgent":      overlay(badged(HEAD_WIDE), BOLT, 21, 1),
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


# --------------------------------------------------------------------------- #
# Animation. Mario-style: a short cycle, big readable steps, no easing.
#
# "No easing" is about the drawing, not about the timing. Nothing is
# interpolated and nothing is blurred, because a pixel sprite that tweens stops
# looking like a pixel sprite. Timing is a separate question and it is shaped
# with holds - see hold() below.
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

LEGS_TUCK = """
.......BBBB....BBBB.......
..........................
"""
LEGS_LAND = """
.......BBBB....BBBB.......
......BB..BB..BB..BB......
"""
# Feet planted wide, for the frame that absorbs a landing.
LEGS_BRACE = """
......BBBB......BBBB......
.....BB..BB....BB..BB.....
"""


def _legs(grid: str, legs: str) -> str:
    """Swap the bottom two rows (the feet) for a different stride."""
    rows = _rows(grid)
    return "\n".join(rows[:-2] + _rows(legs))


def _bob(grid: str, up: int) -> str:
    """Lift the whole character by `up` pixels, keeping the canvas height."""
    rows = _rows(grid)
    return "\n".join(rows[up:] + ["." * W] * up)


def _sink(grid: str, down: int) -> str:
    """Push the character `down` rows off the bottom, keeping the height."""
    rows = _rows(grid)
    if down <= 0:
        return "\n".join(rows)
    return "\n".join(["." * W] * down + rows[:-down])


def _headroom(grid: str, rows_above: int = 6) -> str:
    """Add blank rows on top so a jump has somewhere to go without clipping.

    Apply this last. squash(), stretch() and head_shift() all read the head as
    the first eleven rows, so they must run before anything is added on top.
    """
    return "\n".join(["." * W] * rows_above + _rows(grid))


# --------------------------------------------------------------------------- #
# Timing, weight and secondary motion
# --------------------------------------------------------------------------- #
def hold(frame: str, n: int = 2) -> list[str]:
    """`n` copies of one frame.

    The player steps a cycle at a fixed rate, so the only way to give a cycle
    uneven timing is to repeat the frames that should last longer. Holding the
    apex of a jump for three ticks and the launch for one is what makes it read
    as weight rather than as a metronome, and it keeps a cycle a plain list of
    frames, so every existing caller is unaffected.
    """
    return [frame] * max(1, int(n))


def _split(grid: str) -> tuple[list[str], list[str]]:
    """(head rows, body rows). The head is always the first eleven."""
    rows = _rows(grid)
    return rows[:11], rows[11:]


def squash(grid: str, rows_out: int = 1) -> str:
    """Compress the body vertically, keeping the canvas height.

    Squash and stretch is the oldest principle there is and the one that makes
    a landing land. Only the body compresses: a head that deforms reads as the
    character being damaged rather than as weight arriving.
    """
    head, body = _split(grid)
    kept = body[:1] + body[1 + rows_out:]
    return "\n".join(["." * W] * rows_out + head + kept)


def stretch(grid: str, rows_in: int = 1) -> str:
    """Extend the body vertically, keeping the canvas height.

    The counterpart to squash, for the launch frame. The crown of the head is
    blank, so the extra rows are taken from there and the silhouette keeps its
    footing on the ground line.
    """
    head, body = _split(grid)
    body = body[:1] + [body[1]] * rows_in + body[1:]
    return "\n".join((head + body)[rows_in:])


def head_shift(grid: str, dx: int = 0, dy: int = 0) -> str:
    """Move the head relative to the body.

    This is how a nod and a shake are built. The body is a fixed mark in this
    design and never travels on its own, so the head does all the talking, and
    at 26px across, one pixel is already a large move.
    """
    rows = [list(r.ljust(W, ".")) for r in _rows(grid)]
    head = rows[:11]
    blank = ["."] * W
    out = []
    for y in range(11):
        src = y - dy
        if not 0 <= src < 11:
            out.append(blank[:])
            continue
        row = head[src]
        if dx:
            shifted = blank[:]
            for x, ch in enumerate(row):
                if ch != "." and 0 <= x + dx < W:
                    shifted[x + dx] = ch
            row = shifted
        out.append(row)
    return "\n".join("".join(r) for r in out + rows[11:])


def ease_out_cubic(p: float) -> float:
    """Decelerating travel, for anything arriving somewhere."""
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def ease_in_out_sine(p: float) -> float:
    """Travel that starts and stops gently, for a long crossing.

    Pip's walk across a reel runs the whole length of it. Linear travel over
    thirty seconds reads as a conveyor belt: the character arrives at the right
    edge at exactly the speed he left the left one, which nothing alive does.
    This costs one call and fixes it.
    """
    p = max(0.0, min(1.0, p))
    return -(math.cos(math.pi * p) - 1) / 2


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #
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


def jump_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Crouch, launch, hang, land. Four frames is all Mario ever needed."""
    base = badged(head)
    airborne = _wings(base)
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


def blink_cycle() -> list[str]:
    """The breath, with a blink that lands off the beat of it.

    A character who blinks on a short fixed loop looks nervous. This blink is
    two frames inside a twelve-frame breath, placed so the two never line up.
    """
    base = badged(HEAD_OPEN)
    up = _bob(base, 1)
    shut = badged(HEAD_SHUT)
    return (hold(base, 3) + hold(up, 3) + hold(base, 2)
            + [shut] + hold(up, 2) + [shut])


def bounce_cycle(head: str = HEAD_OPEN) -> list[str]:
    """A jump with the weight in it: anticipate, launch, hang, land, recover.

    jump_cycle above is the arcade version and stays exactly as it is. This is
    the same move with the principles applied - a crouch that squashes before
    the launch, a stretch on the way up, a hold at the apex where a real body
    spends most of its air time, and a landing that recovers over two frames
    instead of snapping back.
    """
    base = badged(head)
    ground = _headroom(_legs(base, LEGS_LAND))
    crouch = _headroom(squash(_legs(base, LEGS_BRACE), 1))
    launch = _headroom(stretch(_legs(base, LEGS_TUCK), 1))
    mid = _wings(base, WING_MID_L, WING_MID_R)
    rising = _bob(_headroom(_legs(mid, LEGS_TUCK)), 4)
    apex = _bob(_headroom(_legs(_wings(base), LEGS_TUCK)), 7)
    falling = _bob(_headroom(_legs(mid, LEGS_TUCK)), 3)
    land = _headroom(squash(_legs(base, LEGS_BRACE), 1))
    return (hold(ground, 2) + [crouch, launch, rising]
            + hold(apex, 3) + [falling] + hold(land, 2) + [ground])


def flap_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Wings through three positions, with a bob that lags them.

    The lift arrives a frame after the downstroke rather than on it. That lag
    is follow-through, and it is the whole difference between a bird flying and
    a sprite being moved up and down.
    """
    base = badged(head)
    down = _wings(base, WING_MID_L, WING_MID_R, y=13)
    mid = _wings(base, WING_MID_L, WING_MID_R, y=11)
    up = _wings(base, WING_UP_L, WING_UP_R, y=9)
    return [_legs(down, LEGS_TUCK),
            _bob(_legs(mid, LEGS_TUCK), 1),
            _bob(_legs(up, LEGS_TUCK), 3),
            _bob(_legs(mid, LEGS_TUCK), 2)]


def nod_cycle(head: str = HEAD_OPEN) -> list[str]:
    """Yes. The head drops into the shoulders and comes back, twice.

    Paired with shake_cycle this carries the agreement state of a story without
    a word of copy: the outlets agreed, so the bird nods.
    """
    base = badged(head)
    down = head_shift(base, dy=1)
    return hold(base, 2) + [down, down, base, down, down] + hold(base, 3)


def shake_cycle(head: str = HEAD_GLANCE) -> list[str]:
    """No, or not yet. One pixel each way is a large move at this size."""
    base = badged(head)
    return ([base, head_shift(base, dx=-1), head_shift(base, dx=-1),
             base, head_shift(base, dx=1), head_shift(base, dx=1), base]
            + hold(base, 3))


def cheer_cycle() -> list[str]:
    """Wings up, a hop, and confetti that actually falls.

    The particles advance every frame and thin out towards the end, so the
    burst has a direction. Three static overlays alternating would strobe.
    """
    base = _wings(badged(HEAD_HAPPY))
    hop = _bob(_legs(base, LEGS_TUCK), 2)
    return [
        overlay(_headroom(base, 3), CONFETTI_A, 8, 0),
        overlay(_headroom(hop, 3), CONFETTI_B, 8, 0),
        overlay(_headroom(hop, 3), CONFETTI_C, 8, 1),
        overlay(_headroom(base, 3), CONFETTI_B, 8, 2),
        _headroom(base, 3),
    ]


def peek_cycle(head: str = HEAD_GLANCE) -> list[str]:
    """Pip rises into frame from below, looks, and drops back.

    For the moment a card or a figure lands on screen. The rise is three uneven
    steps, because a constant rise reads as a lift rather than as a look.
    """
    tall = _headroom(badged(head), 8)
    return ([_sink(tall, 8), _sink(tall, 8), _sink(tall, 5), _sink(tall, 2)]
            + hold(_sink(tall, 0), 4)
            + [_sink(tall, 2), _sink(tall, 6)])


def think_cycle() -> list[str]:
    """Looking up, then the bulb arrives. The pause before it is the joke."""
    up = badged(HEAD_THINK)
    idea = overlay(badged(HEAD_HAPPY), BULB, 21, 0)
    dim = overlay(badged(HEAD_THINK), BULB, 21, 1)
    return hold(up, 4) + [dim, idea, idea, dim] + hold(idea, 3)


def scan_cycle() -> list[str]:
    """The magnifier sweeps, for a story only one outlet is carrying so far."""
    base = badged(HEAD_GLANCE)
    return [overlay(base, GLASS, 20, 0),
            overlay(base, GLASS, 20, 1),
            overlay(base, GLASS, 20, 2),
            overlay(base, GLASS, 20, 1)]


def deliver_cycle() -> list[str]:
    """The carrier-pigeon move: walk in with the envelope, then hand it over."""
    carry = overlay(badged(HEAD_HAPPY), ENVELOPE, 9, 15)
    return [_legs(carry, LEGS_L),
            _bob(_legs(carry, LEGS_MID), 1),
            _legs(carry, LEGS_R),
            _bob(_legs(carry, LEGS_MID), 1),
            overlay(badged(HEAD_HAPPY), ENVELOPE, 9, 13),
            overlay(badged(HEAD_HAPPY), ENVELOPE, 9, 12)]


def alarm_cycle() -> list[str]:
    """Wide eyes and a bolt that flickers off the beat. For anything breaking."""
    base = _wings(badged(HEAD_WIDE))
    lit = overlay(base, BOLT, 21, 1)
    return [lit, lit, base, lit, _bob(lit, 1), base]


def sleep_cycle() -> list[str]:
    """A slow breath with the Zs climbing. The slowest cycle in the set."""
    base = badged(HEAD_SLEEPY)
    return (hold(overlay(base, ZZZ, 21, 2), 3)
            + hold(_bob(overlay(base, ZZZ, 21, 1), 1), 3)
            + hold(overlay(base, ZZZ, 21, 0), 3)
            + hold(base, 2))


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


def contact_sheet(path="pip_posestrip.png", scale: int = 6, cols: int = 7,
                  gap: int = 14, bg=(247, 241, 230)):
    """Every pose on one sheet. It is the only way to see drift between them."""
    tiles = [render(grid, scale) for grid in SPRITES.values()]
    tw = max(t.width for t in tiles)
    th = max(t.height for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + gap) + gap,
                              rows * (th + gap) + gap), bg)
    for i, tile in enumerate(tiles):
        x = gap + (i % cols) * (tw + gap)
        y = gap + (i // cols) * (th + gap)
        sheet.paste(tile, (x, y + (th - tile.height)), tile)
    sheet.save(path)
    return path


CYCLE_DEMOS = (
    ("walk", walk_cycle, 140), ("jump", jump_cycle, 130),
    ("point", point_cycle, 320), ("present", present_cycle, 320),
    ("talk", talk_cycle, 180), ("idle", idle_cycle, 420),
    ("blink", blink_cycle, 160), ("bounce", bounce_cycle, 110),
    ("flap", flap_cycle, 110), ("nod", nod_cycle, 130),
    ("shake", shake_cycle, 110), ("cheer", cheer_cycle, 130),
    ("peek", peek_cycle, 150), ("think", think_cycle, 200),
    ("scan", scan_cycle, 200), ("deliver", deliver_cycle, 160),
    ("alarm", alarm_cycle, 120), ("sleep", sleep_cycle, 260),
)


if __name__ == "__main__":
    for name, builder, ms in CYCLE_DEMOS:
        gif(builder(), f"pip_{name}.gif", ms=ms)
    contact_sheet()
    print(f"{len(SPRITES)} poses, {len(CYCLE_DEMOS)} cycles")
