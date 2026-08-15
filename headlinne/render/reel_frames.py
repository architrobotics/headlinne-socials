"""The reel, ported from design/prototypes/draft.py.

An informational reel rather than an announcing one: a chapter label so the
viewer knows which part of the explanation they are in, the line revealed word
by word so the eye moves at the pace of the voice, emphasis carried by weight
rather than colour alone, and Pip walking the width of the frame across the
thirty seconds so the progress is legible without reading the bar.

Everything is expressed against a 1080x1920 frame through `S()`, so the same
code renders a half-size draft and a full-size post.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image, ImageDraw

from ..config import FFMPEG_BINARY, INK, SURFACE, SURFACE_DEEP, TEXT_SECONDARY
from ..logging_setup import get_logger
from . import fonts, pip as _pip, plate as _plate, theme

log = get_logger("render.reel_frames")

BASE_W, BASE_H = 1080, 1920
BASE_M = 84
FPS = 24

GUIDE_GREY = (196, 184, 168)
RAISED = (255, 253, 248)


@dataclass
class Beat:
    """One beat of the reel. `line` may mark emphasis with *asterisks*."""

    start: float
    chapter: str
    pose: str                       # walk | talk | jump | point | present
    line: str
    detail: str
    accent: tuple[int, int, int]
    say: str | None = None          # speech bubble
    counter: str | None = None      # a number that rolls up
    plates: list[str] = field(default_factory=list)


@dataclass
class ReelDesign:
    """Everything the frame renderer needs that is not a single beat."""

    beats: Sequence[Beat]
    duration: float = 30.0
    dateline: str = ""
    sources: str = ""
    agree: int = 0
    outlets: int = 0
    plates: dict = field(default_factory=dict)   # key -> (maker, angle, caption)


_CYCLES: dict[str, Callable[[], list[str]]] = {
    "walk": _pip.walk_cycle, "talk": _pip.talk_cycle, "jump": _pip.jump_cycle,
    "point": _pip.point_cycle, "present": _pip.present_cycle,
}

# The sign-off pose rotates, the same way the hooks do: code owns the variety so
# a month of reels never collapses into one look.
CTA_POSES = ("jump", "present", "point", "walk", "talk")


def cta_pose(day: int = 0) -> str:
    return CTA_POSES[day % len(CTA_POSES)]


def _rgb(value: str) -> tuple[int, int, int]:
    return theme.hex_to_rgb(value)


def tokens(text: str) -> list[tuple[str, bool]]:
    """Split into (word, emphasised) pairs, honouring *starred* runs.

    Punctuation that follows an emphasised run is pulled back onto it, so a
    full stop never appears orphaned in the body weight.
    """
    out: list[list] = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        hero = part.startswith("*") and part.endswith("*") and len(part) > 2
        body = part[1:-1] if hero else part
        if not hero and out:
            m = re.match(r"^([,.;:!?)\]—]+)", body)
            if m:
                out[-1][0] += m.group(1)
                body = body[m.end():]
        for word in body.split():
            out.append([word, hero])
    return [(w, h) for w, h in out]


class FrameRenderer:
    """Renders one frame of a reel at a given time."""

    def __init__(self, design: ReelDesign, *, scale: float = 1.0,
                 guides: bool = False):
        self.design = design
        self.scale = scale
        self.guides = guides
        self.W, self.H = int(BASE_W * scale), int(BASE_H * scale)
        self.M = int(BASE_M * scale)
        self._fonts: dict = {}
        self._plates: dict = {}
        self._sprites: dict = {}
        self._cycles = {name: fn() for name, fn in _CYCLES.items()}

    # -- helpers ---------------------------------------------------------- #
    def S(self, v: float) -> int:
        return int(v * self.scale)

    def font(self, px: int, weight: int = 800):
        key = (self.S(px), weight)
        if key not in self._fonts:
            self._fonts[key] = fonts.label_font(max(8, key[0]), weight)
        return self._fonts[key]

    def sprite(self, grid: str, scale: int):
        key = (id(grid), scale)
        if key not in self._sprites:
            self._sprites[key] = _pip.render(grid, scale)
        return self._sprites[key]

    def plate(self, key: str, maxw: int):
        ck = (key, maxw)
        if ck not in self._plates:
            maker, angle, caption = self.design.plates[key]
            tile = _plate.tilted(maker(), angle=angle, caption=caption,
                                 font=self.font(22, 600))
            tile.thumbnail((self.S(maxw), self.S(392)), Image.LANCZOS)
            self._plates[ck] = tile
        return self._plates[ck]

    def rich(self, draw, text: str, x: int, y: int, max_w: int, size: int,
             accent, reveal: float = 1.0) -> int:
        """The line, wrapped, with emphasis in accent and a heavier weight."""
        toks = tokens(text)
        show = max(1, int(len(toks) * reveal + 0.999)) if reveal < 1 else len(toks)
        ink = _rgb(INK)
        space = draw.textlength(" ", font=self.font(size, 450))
        lines, cur, curw = [], [], 0.0
        for i, (word, hero) in enumerate(toks):
            f = self.font(int(size * 1.08), 800) if hero else self.font(size, 450)
            tw = draw.textlength(word, font=f)
            if curw + tw > max_w and cur:
                lines.append(cur)
                cur, curw = [], 0.0
            cur.append((word, hero, f, tw, i))
            curw += tw + space
        if cur:
            lines.append(cur)
        lh = int(self.S(size) * 1.16)
        for ln in lines:
            cx = x
            for word, hero, f, tw, i in ln:
                if i < show:
                    draw.text((cx, y), word, font=f,
                              fill=accent if hero else ink)
                cx += tw + space
            y += lh
        return y

    def beat_at(self, t: float) -> tuple[int, Beat]:
        idx = 0
        for i, b in enumerate(self.design.beats):
            if t >= b.start:
                idx = i
        return idx, self.design.beats[idx]

    # -- the frame -------------------------------------------------------- #
    def frame(self, t: float, day: int = 0) -> Image.Image:
        d_ = self.design
        S, M, W, H = self.S, self.M, self.W, self.H
        i, beat = self.beat_at(t)
        pose = beat.pose or cta_pose(day)
        end = d_.beats[i + 1].start if i + 1 < len(d_.beats) else d_.duration
        local = (t - beat.start) / max(end - beat.start, .001)
        accent = beat.accent
        ink, soft, deep = _rgb(INK), _rgb(TEXT_SECONDARY), _rgb(SURFACE_DEEP)

        im = Image.new("RGB", (W, H), _rgb(SURFACE))
        d = ImageDraw.Draw(im)

        # masthead + progress
        d.text((M, S(70)), "HEADLINNE", font=self.font(34, 800), fill=ink)
        d.text((W - M, S(74)), d_.dateline.upper(), font=self.font(26, 600),
               fill=soft, anchor="ra")
        d.rectangle([M, S(126), W - M, S(132)], fill=deep)
        d.rectangle([M, S(126), M + int((W - 2 * M) * (t / d_.duration)), S(132)],
                    fill=accent)

        # chapter
        d.text((M, S(160)), f"{i + 1:02d} · {beat.chapter.upper()}",
               font=self.font(24, 700), fill=accent)

        # plates, scattered and sliding in
        if beat.plates:
            n = len(beat.plates)
            gutter = S(20)
            for j, key in enumerate(beat.plates):
                tile = self.plate(key, 520 if n == 1 else 430)
                ease = min(1.0, local / .28)
                ease = 1 - (1 - ease) ** 3
                left, right = M - gutter, W - M + gutter
                if n == 1:
                    px = (W - tile.width) // 2
                    py = S(214) + int((1 - ease) * S(40))
                else:
                    span = max(0, (right - left) - tile.width)
                    px = left + (j * span) // (n - 1)
                    py = S(206) + (j % 2) * S(46) + int((1 - ease) * S(40))
                px = max(left, min(px, right - tile.width))
                ph = Image.new("RGBA", tile.size, (0, 0, 0, 0))
                ph.paste(tile, (0, 0), tile)
                ph.putalpha(ph.getchannel("A").point(lambda a: int(a * ease)))
                im.paste(ph, (px, py), ph)
            ground_y = S(944)
        else:
            ground_y = S(838)

        # ground + Pip, walking the width of the frame across the reel
        d.rectangle([0, ground_y, W, ground_y + S(5)], fill=deep)
        cycle = self._cycles[pose]
        fi = int((t * 7) % len(cycle)) if len(cycle) > 2 else int((t * 3) % len(cycle))
        sp = self.sprite(cycle[fi], max(1, S(12 if beat.plates else 14)))
        travel = int((t / d_.duration) * (W - 2 * M - sp.width))
        pip_x = M - S(30) + travel
        im.paste(sp, (pip_x, ground_y - sp.height + S(4)), sp)

        if beat.say and local < .74:
            self._bubble(d, beat.say, pip_x, sp.width, sp.height, ground_y)

        # the line, revealed word by word over the first third of the beat
        y = S(966)
        if beat.counter:
            roll = min(1.0, local / .42)
            target = int(re.sub(r"[^\d]", "", beat.counter) or 0)
            val = int(target * (1 - (1 - roll) ** 3))
            cf = self.font(140, 800)
            text = f"{val:,}"
            d.text((M, y), text, font=cf, fill=accent)
            y = d.textbbox((M, y), text, font=cf)[3] + S(16)
        y = self.rich(d, beat.line, M, y, W - 2 * M, 58, accent,
                      reveal=min(1.0, local / .34))

        # the detail sits below wherever the line actually ended, never on a
        # fixed y - that is what produced the overlap on the counter beat.
        df = self.font(30, 450)
        dy = y + S(26)
        box = d.textbbox((M, dy), beat.detail, font=df)
        if box[3] > S(1246):
            dy = S(1246) - (box[3] - box[1])
        d.text((M, dy), beat.detail, font=df, fill=soft)

        # persistent source strip
        d.rectangle([M, S(1264), W - M, S(1267)], fill=deep)
        good = theme.accent_for("Finance")
        for k in range(d_.outlets):
            bx = M + k * S(20)
            d.rectangle([bx, S(1290), bx + S(11), S(1326)], fill=good)
        if d_.outlets:
            d.text((M + S(190), S(1292)), f"{d_.agree} of {d_.outlets} agree",
                   font=self.font(26, 700), fill=ink)
        d.text((M, S(1342)), d_.sources, font=self.font(22, 500), fill=soft)

        if self.guides:
            d.rectangle([M, S(1400), W - M, S(1403)], fill=deep)
            d.text((M, S(1416)), "SAFE ZONE ENDS 1450 · IG UI COVERS BELOW",
                   font=self.font(20, 600), fill=GUIDE_GREY)
        return im

    def _bubble(self, d, say: str, pip_x: int, pip_w: int, pip_h: int,
                ground_y: int) -> None:
        """Sits on whichever side of Pip has room, and mirrors its tail to match."""
        S, M, W = self.S, self.M, self.W
        ink = _rgb(INK)
        f = self.font(34, 650)
        bw, bh = int(d.textlength(say, font=f)) + S(44), S(84)
        gap = S(14)
        room_right = (W - M) - (pip_x + pip_w + gap)
        room_left = (pip_x - gap) - M
        on_left = room_right < bw and room_left >= bw
        bx = pip_x - gap - bw if on_left else pip_x + pip_w + gap
        bx = max(M, min(bx, W - M - bw))
        by = ground_y - pip_h - S(84)

        d.rectangle([bx, by, bx + bw, by + bh], fill=RAISED)
        d.rectangle([bx, by, bx + bw, by + bh], outline=ink, width=max(2, S(4)))
        d.text((bx + S(22), by + S(20)), say, font=f, fill=ink)

        s, b = S(11), by + bh
        if on_left:
            tx = bx + bw - S(30) - 3 * s
            pts = [(tx, b), (tx + 3 * s, b), (tx + 3 * s, b + 3 * s),
                   (tx + 2 * s, b + 3 * s), (tx + 2 * s, b + 2 * s),
                   (tx + s, b + 2 * s), (tx + s, b + s), (tx, b + s)]
        else:
            tx = bx + S(26)
            pts = [(tx, b), (tx + 3 * s, b)]
            for k in range(3):
                pts += [(tx + (3 - k) * s, b + (k + 1) * s),
                        (tx + (2 - k) * s, b + (k + 1) * s)]
        d.polygon(pts, fill=RAISED)
        d.line(pts[1:] + [pts[0]], fill=ink, width=max(2, S(4)), joint="curve")
        d.rectangle([tx + 2, b - 3, tx + 3 * s - 2, b + 2], fill=RAISED)


def encode(design: ReelDesign, out_path: Path, *, scale: float = 1.0,
           guides: bool = False, day: int = 0, crf: int = 20) -> Path:
    """Render every frame and pipe it into ffmpeg."""
    renderer = FrameRenderer(design, scale=scale, guides=guides)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = int(design.duration * FPS)
    cmd = [FFMPEG_BINARY or "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
           "-s", f"{renderer.W}x{renderer.H}", "-pix_fmt", "rgb24",
           "-r", str(FPS), "-i", "-", "-an", "-vcodec", "libx264",
           "-pix_fmt", "yuv420p", "-crf", str(crf), str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        for k in range(n):
            proc.stdin.write(renderer.frame(k / FPS, day=day).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed:\n" + err[-1500:])
    log.info("rendered reel (%d frames, %.0fs) -> %s", n, design.duration,
             out_path.name)
    return out_path
