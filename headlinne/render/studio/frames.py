"""Render any frame of a studio reel.

Same interface as render.reel.ReelFrames - `render(t)`, `trace`, `duration`,
`beat_at` - so the geometry gate, the cover and the encoder are unchanged.

A frame is built in three passes:

  1. The set, in set space: the beat's diorama, a graphic on its board if the
     beat has one, Pip in his pose and hat, and whatever stands in front of
     him. The set for a beat is built once; per frame only Pip and the board
     are drawn.
  2. The camera: a slow push and drift through the set, and a whip pan on
     every chapter change. Then the finish - warm grade, vignette, a touch of
     chromatic fringe and film grain - which is most of what makes a Pillow
     render read as footage rather than a slide.
  3. The furniture, in frame space, never moving with the camera: title strip,
     stat card, source tag, lower third, stamp, word chips, comment box. Every
     piece is traced for quality.visual's overlap and safe-zone replay.

Word chips follow the voice. The narration is one request split into beats by
word count (render/voice.py), so inside a beat the words are spaced evenly by
the same measure, and the chips page through them one to three at a time.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from ...config import REEL_H, REEL_MAX_SECONDS, REEL_MIN_SECONDS, REEL_VOICE_LEAD_IN, REEL_W
from ...logging_setup import get_logger
from ...models import Reel, ReelBeat
from .. import graphics, theme
from . import direction, overlay, paper, sets, voxel

log = get_logger("render.studio")

MARGIN = theme.MARGIN

# Frame-space layout. Measured against the reference reels and moved up where
# theirs sat inside Instagram's caption block: everything traced ends above
# theme.REEL_SAFE_BOTTOM (1450).
TITLE_TOP = 228
STAT_POS = (44, 404)
SOURCE_TOP = 430
LOWER_THIRD_TOP = 1104
CHIPS_TOP = 1316
STAMP_CENTRE = (720, 880)
COMMENT_TOP = 556

# How long the chapter change whips, and how far.
WHIP_SECONDS = 0.22
WHIP_PX = 180

# When things arrive inside a beat, as fractions of it.
STAT_AT = 0.06
LOWER_THIRD_AT = 0.30
STAMP_AT = 0.55
GRAPHIC_FROM, GRAPHIC_TO = 0.08, 0.62
COMMENT_FROM, COMMENT_TO = 0.30, 0.75

# A group of chips: at most this many words, and this many characters.
GROUP_WORDS = 3
GROUP_CHARS = 20
CHIP_SIZES = (66, 58, 50)

_PUNCT_END = re.compile(r"[.,!?;:]$")
_STRIP = re.compile(r"^[\"'“‘(\[]+|[\"'”’)\].,!?;:]+$")


def words_of(text: str) -> list[str]:
    """Spoken words as chips show them: no surrounding punctuation, no markup."""
    out = []
    for raw in (text or "").replace("*", "").split():
        word = _STRIP.sub("", raw)
        if word:
            out.append((word, bool(_PUNCT_END.search(raw))))
    return out


def group_words(text: str) -> list[list[str]]:
    """Page a line into chip groups, breaking at punctuation as speech does."""
    groups: list[list[str]] = []
    current: list[str] = []
    for word, ends in words_of(text):
        if current and (len(current) >= GROUP_WORDS
                        or sum(len(w) for w in current) + len(word) > GROUP_CHARS):
            groups.append(current)
            current = []
        current.append(word)
        if ends:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _put(frame: Image.Image, img: Image.Image, x: int, y: int) -> None:
    """Lay an RGBA piece on the RGB frame, through its own alpha."""
    frame.paste(img, (int(x), int(y)), img)


_GRADE: list = []


@lru_cache(maxsize=4)
def _sheet(w: int, h: int) -> Image.Image:
    return paper.rect(w, h, (246, 242, 232), key=("sheet", w, h))


def _grade_layer() -> Image.Image:
    """Warm tint and vignette, merged once into a single RGBA layer."""
    if not _GRADE:
        layer = Image.new("RGBA", (REEL_W, REEL_H), (255, 176, 110, 20))
        layer.alpha_composite(paper.vignette(REEL_W, REEL_H))
        _GRADE.append(layer)
    return _GRADE[0]


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


class StudioFrames:
    """Renders any frame of a reel in the studio style, and traces it."""

    def __init__(self, reel: Reel, story=None, *, loader=None,
                 day_ordinal: int = 0, **_ignored):
        self.reel = reel
        self.story = story
        self.loader = loader
        self.day_ordinal = day_ordinal
        self.trace: list[tuple[str, int, int, int, int]] = []
        self.duration = max(REEL_MIN_SECONDS,
                            min(REEL_MAX_SECONDS,
                                sum(b.seconds for b in reel.beats) or 30.0))
        self._starts = self._beat_starts()
        self.looks = direction.plan(reel, story, day_ordinal)
        self._titles = direction.chapters(reel)
        self.sensitive = bool(getattr(story, "sensitive", False))
        self._groups = [self._timed_groups(i) for i in range(len(reel.beats))]
        self._cycles: dict[str, list[str]] = {}

    # ---- timing ----------------------------------------------------------- #
    def _beat_starts(self) -> list[float]:
        starts, t = [], 0.0
        for beat in self.reel.beats:
            starts.append(t)
            t += max(0.4, beat.seconds)
        return starts

    def _beat_span(self, index: int) -> tuple[float, float]:
        start = self._starts[index]
        end = (self._starts[index + 1] if index + 1 < len(self._starts)
               else self.duration)
        return start, end

    def beat_at(self, t: float) -> tuple[int, ReelBeat, float]:
        index = 0
        for i, start in enumerate(self._starts):
            if t >= start:
                index = i
        beat = self.reel.beats[index]
        start, end = self._beat_span(index)
        local = (t - start) / max(end - start, 0.001)
        return index, beat, max(0.0, min(1.0, local))

    def _timed_groups(self, index: int) -> list[tuple[float, list[str]]]:
        """(start time, words) for each chip group of a beat, in reel time."""
        beat = self.reel.beats[index]
        # With a voice, the chips are the words being said. Without one (the
        # narration failed, or REEL_VOICEOVER is off) the beat is paced for
        # reading, and the shorter on-screen caption is what fits that pace -
        # twenty spoken words paged in silence read at nearly 300 wpm.
        if self.reel.has_voiceover and beat.narration:
            text = beat.narration
        else:
            text = beat.caption or beat.narration
        groups = group_words(text)
        if not groups:
            return []
        start, end = self._beat_span(index)
        lead = REEL_VOICE_LEAD_IN if index == 0 else 0.0
        speak = max(0.4, (end - start) - lead - 0.25)
        total = sum(len(g) for g in groups)
        out, done = [], 0
        for g in groups:
            out.append((start + lead + speak * done / total, g))
            done += len(g)
        return out

    # ---- assets ----------------------------------------------------------- #
    def _cycle(self, name: str) -> list[str]:
        if name not in self._cycles:
            builder = theme.CYCLES.get(name, theme.CYCLES["idle"])
            self._cycles[name] = builder()
        return self._cycles[name]

    def _note(self, label: str, x0, y0, x1, y1) -> None:
        self.trace.append((label, int(x0), int(y0), int(x1), int(y1)))

    # ---- the frame -------------------------------------------------------- #
    def render(self, t: float) -> Image.Image:
        self.trace.clear()
        index, beat, local = self.beat_at(t)
        look = self.looks[index]
        start, end = self._beat_span(index)
        seconds_in = t - start

        built = sets.build(look.spec)
        scene = built.back.copy()
        board_box = self._draw_board(scene, built, beat, local)
        self._blink(scene, built, t)
        self._draw_pip(scene, built, look, t)
        if built.front is not None and board_box is None:
            # A board beat drops the foreground props: the board is the
            # subject, and a desk in front of it is clutter.
            scene.alpha_composite(built.front, built.front_at)

        frame, cam = self._camera(scene.convert("RGB"), look, local, seconds_in, index)
        self._finish(frame, t)
        if board_box is not None:
            self._note(f"graphic-{beat.graphic}", *self._to_frame(board_box, cam))

        self._draw_title(frame, index, beat, seconds_in)
        has_stat = self._draw_stat(frame, index, beat, local)
        self._draw_source(frame, index, has_stat)
        self._draw_lower_third(frame, beat, local, end - start)
        self._draw_stamp(frame, beat, local, end - start, board_box is not None)
        self._draw_chips(frame, index, t)
        if index == len(self.reel.beats) - 1 and beat.role in ("outro", "payoff") \
                or (index == len(self.reel.beats) - 1 and "headlinne" in
                    (beat.narration + beat.caption).lower()):
            self._draw_comment(frame, beat, local)
        return frame.convert("RGB")

    # ---- set space -------------------------------------------------------- #
    def _draw_board(self, scene, built, beat, local):
        device = (beat.graphic or "").strip().lower()
        if built.board is None or not device or device == "counter":
            return None
        x0, y0, x1, y1 = built.board
        dark = built.board_dark
        if dark and device not in graphics._DARK_AWARE:
            # A device that only knows how to draw on paper gets a sheet of
            # paper pinned to the board, rather than ink on a blackboard.
            scene.alpha_composite(_sheet(x1 - x0, y1 - y0), (x0, y0))
            dark = False
        accent = theme.safe_fill(self.looks[0].spec.accent, theme.DISPLAY_ONLY_MIN_PX)
        progress = _ease((local - GRAPHIC_FROM) / (GRAPHIC_TO - GRAPHIC_FROM))
        graphics.draw_device(scene, device, progress, area=(x0, y0, x1, y1),
                             data=beat.data or {}, accent=accent, dark=dark)
        return (x0, y0, x1, y1)

    def _blink(self, scene, built, t) -> None:
        if not built.lights:
            return
        d = ImageDraw.Draw(scene)
        for k, (x, y, r) in enumerate(built.lights):
            if int(t * 3 + k * 7) % 5 == 0:
                d.ellipse([x - r, y - r, x + r, y + r], fill=(30, 40, 50))

    def _draw_pip(self, scene, built, look, t) -> None:
        if not look.pose or self.sensitive:
            return
        grid = theme.pip_frame(self._cycle(look.pose), t)
        fig = voxel.figure(grid, cell=look.cell, hat=look.hat)
        fx, fy = built.pip
        if look.cell == direction.PIP_CELL_BOARD:
            # Under the board's corner, presenting it rather than blocking it.
            fx, fy = sets.SET_W - 250, sets.FLOOR_MARK + 30
        bob = int(3 * math.sin(t * 2.4))
        shadow = voxel.contact_shadow(int(fig.width * 0.72))
        scene.alpha_composite(shadow, (fx - shadow.width // 2, fy - shadow.height // 2))
        # The figure's own padding sits under his feet; lift him by it.
        pad = int(look.cell * 0.6)
        scene.alpha_composite(fig, (fx - fig.width // 2, fy - fig.height + pad + bob))

    # ---- camera ----------------------------------------------------------- #
    def _camera(self, scene, look, local, seconds_in, index):
        z0, z1 = look.zoom
        z = z0 + (z1 - z0) * _ease_in_out(local)
        # z=1.0 shows the whole set; z=1.1 shows exactly 1080x1920 of it at 1:1.
        cw, ch = sets.SET_W / z, sets.SET_H / z
        px, py = look.pan
        cx = sets.SET_W / 2 + px * _ease_in_out(local)
        cy = sets.SET_H / 2 + py * _ease_in_out(local)
        # A breath of handheld drift, so the frame is never perfectly still.
        cx += 2.0 * math.sin(seconds_in * 1.3 + index)
        cy += 1.5 * math.cos(seconds_in * 1.1 + index)
        whip = 0.0
        if look.chapter_start and index > 0 and seconds_in < WHIP_SECONDS:
            whip = 1 - _ease(seconds_in / WHIP_SECONDS)
            cx += WHIP_PX * whip
        x0 = max(0.0, min(sets.SET_W - cw, cx - cw / 2))
        y0 = max(0.0, min(sets.SET_H - ch, cy - ch / 2))
        sx, sy = cw / REEL_W, ch / REEL_H
        frame = scene.transform((REEL_W, REEL_H), Image.AFFINE,
                                (sx, 0, x0, 0, sy, y0), resample=Image.BILINEAR)
        if whip > 0.05:
            # Motion blur along the whip: squash the width and stretch it back.
            k = 1 + 10 * whip
            frame = frame.resize((max(8, int(REEL_W / k)), REEL_H), Image.BILINEAR) \
                .resize((REEL_W, REEL_H), Image.BILINEAR)
        return frame, (x0, y0, sx, sy)

    @staticmethod
    def _to_frame(box, cam):
        x0, y0, sx, sy = cam
        bx0, by0, bx1, by1 = box
        return ((bx0 - x0) / sx, (by0 - y0) / sy, (bx1 - x0) / sx, (by1 - y0) / sy)

    def _finish(self, frame: Image.Image, t: float) -> None:
        # Warm grade and vignette in one cached layer, then a red/blue fringe
        # and grain. Pasted through masks: the frame is RGB from here on.
        grade = _grade_layer()
        frame.paste(grade, (0, 0), grade)
        r, g, b = frame.split()
        frame.paste(Image.merge("RGB", (ImageChops.offset(r, 2, 0), g,
                                        ImageChops.offset(b, -2, 0))))
        grains = paper.grain_frames(REEL_W, REEL_H)
        grain = grains[int(t * 12) % len(grains)]
        frame.paste(grain, (0, 0), grain)

    # ---- frame space ------------------------------------------------------ #
    def _chapter_text(self, index: int, beat: ReelBeat) -> str:
        return self._titles[index]

    def _chapter_age(self, index: int, seconds_in: float) -> float:
        """Seconds since the current chapter's title went up."""
        age = seconds_in
        j = index
        while j > 0 and self._titles[j - 1] == self._titles[index]:
            j -= 1
            s, e = self._beat_span(j)
            age += e - s
        return age

    def _draw_title(self, frame, index, beat, seconds_in) -> None:
        text = self._chapter_text(index, beat)
        if not text:
            return
        img = overlay.title(text, max_w=REEL_W - 2 * MARGIN + 40)
        age = self._chapter_age(index, seconds_in)
        e = _ease(age / 0.22)
        x = (REEL_W - img.width) // 2
        y = TITLE_TOP - int((1 - e) * 36)
        if e < 1:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(lambda a: int(a * e)))
        _put(frame, img, x, y)
        # Traced as the paper strip, not the tape scraps or the shadow.
        self._note("title", x + 40, y + 30, x + img.width - 40, y + img.height - 26)

    def _stat_for(self, index: int) -> dict:
        beat = self.reel.beats[index]
        stat = beat.stat or {}
        if not stat.get("value") and beat.graphic == "counter" and beat.data:
            # The paper style's counter device is the stat card here. Its
            # figure was verified in generate/reel.py like any other.
            value = beat.data.get("value_label") or beat.data.get("value")
            if value:
                stat = {"value": str(value), "label": str(beat.data.get("caption", ""))}
        if not stat.get("value"):
            return {}
        return stat

    def _draw_stat(self, frame, index, beat, local) -> bool:
        stat = self._stat_for(index)
        if not stat or (beat.graphic and beat.graphic != "counter"):
            return False
        same_as_before = index > 0 and self._stat_for(index - 1) == stat
        p = 1.0 if same_as_before else _ease((local - STAT_AT) / 0.35)
        if p <= 0:
            return True
        count = 1.0 if same_as_before else _ease((local - STAT_AT) / 0.55)
        img = overlay.stat_card(str(stat["value"]), str(stat.get("label", "")),
                                progress=count)
        x = STAT_POS[0] - int((1 - p) * 420)
        y = STAT_POS[1]
        _put(frame, img, x, y)
        pad = paper.pad_for((5, 10), 10)
        self._note("stat", max(x + pad, MARGIN - 30), y + pad,
                   x + img.width - pad, y + img.height - pad)
        return True

    def _draw_source(self, frame, index, has_stat) -> None:
        if not self.reel.sources or index not in (0, len(self.reel.beats) - 1):
            return
        img = overlay.source_tag(self.reel.sources, max_w=420)
        x = REEL_W - MARGIN - img.width + 20
        y = SOURCE_TOP
        pad = paper.pad_for((3, 6), 6)
        box = (x + pad, y + pad, x + img.width - pad, y + img.height - pad)
        if has_stat:
            stat_box = next((b for b in self.trace if b[0] == "stat"), None)
            if stat_box and stat_box[3] > box[0] - 12:
                return              # no room beside a wide figure: skip it
        _put(frame, img, x, y)
        self._note("source", *box)

    def _draw_lower_third(self, frame, beat, local, seconds) -> None:
        if not beat.fact:
            return
        p = _ease((local - LOWER_THIRD_AT) / (0.25 / max(seconds, 0.5)))
        if p <= 0:
            return
        img = overlay.lower_third(beat.fact)
        pad = paper.pad_for((4, 10), 10)
        x = -pad - int((1 - p) * img.width)
        _put(frame, img, x, LOWER_THIRD_TOP)
        # Named as a bleed: it is meant to run off the left edge of the frame.
        self._note("bleed-lowerthird", max(0, x + pad), LOWER_THIRD_TOP + pad,
                   x + img.width - pad, LOWER_THIRD_TOP + img.height - pad)

    def _draw_stamp(self, frame, beat, local, seconds, has_board) -> None:
        if not beat.stamp or self.sensitive or has_board:
            return
        age = (local - STAMP_AT) * seconds
        s = overlay.slam_scale(age)
        if s <= 0:
            return
        img = overlay.stamp(beat.stamp, beat.stamp_tone or "neutral")
        if abs(s - 1) > 0.01:
            img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))),
                             Image.BILINEAR)
        cx, cy = STAMP_CENTRE
        cx = min(cx, REEL_W - MARGIN - img.width // 2 + 20)
        x, y = cx - img.width // 2, cy - img.height // 2
        _put(frame, img, x, y)
        if s == 1.0:
            self._note("stamp", x, y, x + img.width, y + img.height)

    def _draw_chips(self, frame, index, t) -> None:
        groups = self._groups[index]
        current = None
        for start, words in groups:
            if t >= start:
                current = (start, words)
        if current is None:
            return
        start, words = current
        age = t - start
        seed = sum(map(ord, "".join(words))) % 997
        for size in CHIP_SIZES:
            width = overlay.chip_row_width(words, seed, size)
            if width <= REEL_W - 2 * MARGIN + 40:
                break
        pad = paper.pad_for((3, 6), 5)
        x = (REEL_W - width) // 2
        offsets = overlay.chip_offsets(words, seed)
        top, bottom, left, right = 10 ** 6, 0, 10 ** 6, 0
        for i, word in enumerate(words):
            img = overlay.chip(word, seed + i, size)
            w = img.width - 2 * pad
            s = overlay.pop_scale(age - i * 0.07)
            if s > 0:
                shown = img if abs(s - 1) < 0.01 else img.resize(
                    (max(1, int(img.width * s)), max(1, int(img.height * s))),
                    Image.BILINEAR)
                cx = x + w // 2
                cy = CHIPS_TOP + offsets[i] + img.height // 2 - pad
                _put(frame, shown, cx - shown.width // 2, cy - shown.height // 2)
                top = min(top, cy - img.height // 2 + pad)
                bottom = max(bottom, cy + img.height // 2 - pad)
                left = min(left, x)
                right = max(right, x + w)
            x += w + overlay.CHIP_GAP
        if right > left:
            self._note("chips", left, top, right, bottom)

    def _draw_comment(self, frame, beat, local) -> None:
        question = ""
        caption = self.reel.caption or ""
        for line in caption.splitlines():
            if line.strip().endswith("?"):
                question = line.strip()
                break
        text = question if 0 < len(question) <= 30 else "headlinne.com"
        typed = _ease((local - COMMENT_FROM) / (COMMENT_TO - COMMENT_FROM))
        img = overlay.comment_box(text, typed)
        x = (REEL_W - img.width) // 2
        _put(frame, img, x, COMMENT_TOP)
        pad = paper.pad_for((0, 10), 14)
        self._note("comment", x + pad, COMMENT_TOP + pad, x + img.width - pad,
                   COMMENT_TOP + img.height - pad)
