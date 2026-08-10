"""Reel layouts: turn a `Reel` into a 9:16 MP4.

The structure of every reel is the same, because the structure is what works:

    hook  ->  what happened  ->  the mechanism  ->  a graphic  ->  why it
    matters  ->  sign-off

The hook owns the first two seconds and decides whether anything else is ever
seen. The graphic beat exists to break the rhythm of talking-head text. The
sign-off deliberately echoes the hook's look, so a reel that loops does not feel
like it restarted by accident.

Three constraints shape the layouts, all of them about how reels are actually
watched:

  - Muted. Every word is burned into the frame, never spoken.
  - Held in one hand. Type is large, lines are short, and nothing important sits
    in the bottom ~320 pixels or the right ~180, where Instagram draws its own
    caption and action rail.
  - Scrolled fast. Something moves in every frame, and a progress bar across the
    top tells the viewer how much is left.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

from ..config import (BRAND_TERRACOTTA, INSTAGRAM_HANDLE, REEL_FPS, REEL_H,
                      REEL_MAX_SECONDS, REEL_MIN_SECONDS, REEL_TARGET_SECONDS,
                      REEL_W, WEBSITE)
from ..logging_setup import get_logger
from ..models import Reel
from . import fonts, graphics, motion, theme
from .carousel import default_image_loader

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from .voice import VoiceTrack

log = get_logger("render.reel")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

# --------------------------------------------------------------------------- #
# Layout (canvas is 1080 x 1920)
# --------------------------------------------------------------------------- #
MARGIN = theme.MARGIN
PROGRESS_Y = 62                 # the completion bar, above everything
BAR_Y = 118                     # brand bar baseline
BAND_TOP = 300                  # nothing meaningful above this
BAND_BOTTOM = 1400              # nothing meaningful below this
FOOTER_Y = 1500                 # handle / sources line
TEXT_WIDTH = 880                # narrower than the margins allow, to clear the
                                # action rail Instagram draws down the right


# --------------------------------------------------------------------------- #
# Backgrounds
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def _reel_scrim(strength: float = 1.0) -> Image.Image:
    """A 9:16 scrim: firm at the bottom where the type sits, softer at the top.

    Heavier than the carousel's because reel type is bigger and moves, and
    moving type over a busy photo is the fastest way to make something
    unreadable.
    """
    ink = theme.hex_to_rgb(theme.INK)
    overlay = Image.new("RGBA", (REEL_W, REEL_H), theme.rgba(ink, 0))

    bottom = theme.alpha_ramp(REEL_H, [(0.0, 0), (0.24, 30), (0.44, 110),
                                       (0.62, 190), (0.82, 234), (1.0, 250)])
    layer = Image.new("RGBA", (REEL_W, REEL_H), theme.rgba(ink, 255))
    layer.putalpha(bottom.resize((REEL_W, REEL_H)))
    overlay = Image.alpha_composite(overlay, layer)

    top = theme.alpha_ramp(REEL_H, [(0.0, 190), (0.11, 80), (0.20, 0), (1.0, 0)])
    layer2 = Image.new("RGBA", (REEL_W, REEL_H), theme.rgba(ink, 255))
    layer2.putalpha(top.resize((REEL_W, REEL_H)))
    overlay = Image.alpha_composite(overlay, layer2)

    overlay = Image.alpha_composite(
        overlay, Image.new("RGBA", (REEL_W, REEL_H),
                           theme.rgba(ink, int(58 * strength))))
    return overlay


def _panel_plate(category: str, seed: str) -> Image.Image:
    """The designed background used when a beat has no photo.

    Seeded per beat so consecutive beats get visibly different glows. Without
    that, an education reel is five identical gradients in a row, which reads as
    a template even when the words are good.
    """
    return theme.brand_fallback(REEL_W, REEL_H, category, seed)


def _photo_plate(image: Image.Image | None, category: str,
                 seed: str) -> tuple[Image.Image, bool]:
    """Return (plate, is_photo). Falls back to the designed panel."""
    if image is not None and min(image.size) >= 320:
        return image, True
    return _panel_plate(category, seed), False


# --------------------------------------------------------------------------- #
# Shared furniture
# --------------------------------------------------------------------------- #
class _ReelScene(motion.Scene):
    """Base scene: owns the brand furniture every cut carries."""

    def __init__(self, *, category: str, duration: float,
                 progress_from: float, progress_to: float,
                 pill_text: str | None = None, pill_accent=None,
                 footer: str = "", show_pill: bool = True):
        self.category = category
        self.accent = theme.accent_for(category)
        self.duration = max(1.0, duration)
        self.progress_from = progress_from
        self.progress_to = progress_to
        self.pill_text = pill_text
        self.pill_accent = pill_accent
        self.footer = footer
        self.show_pill = show_pill
        self._plate: Image.Image | None = None

    # -- plate -------------------------------------------------------------- #
    def build_plate(self) -> Image.Image:  # pragma: no cover - interface
        raise NotImplementedError

    def prepare(self) -> None:
        if self._plate is None:
            self._plate = self.build_plate()

    def base_frame(self, t: float) -> Image.Image:
        assert self._plate is not None
        return self._plate.copy()

    # -- furniture ---------------------------------------------------------- #
    def draw_furniture(self, canvas: Image.Image, draw: ImageDraw.ImageDraw,
                       t: float) -> None:
        motion.draw_progress_bar(
            draw, width=REEL_W, y=PROGRESS_Y, accent=self.accent,
            progress=self.progress_from + (self.progress_to - self.progress_from) * t,
            margin=MARGIN)
        theme.draw_top_bar(canvas, draw, self.category, width=REEL_W, y=BAR_Y,
                           scale_up=1.25, show_pill=self.show_pill,
                           pill_text=self.pill_text, pill_accent=self.pill_accent)
        if self.footer:
            ffont = fonts.label_font(28, weight=600)
            draw.text((MARGIN, FOOTER_Y), self.footer, font=ffont,
                      fill=theme.rgba(theme.TEXT_MUTED))

    def frame(self, t: float) -> Image.Image:
        canvas = self.base_frame(t)
        draw = ImageDraw.Draw(canvas)
        self.draw_content(canvas, draw, t)
        self.draw_furniture(canvas, draw, t)
        return canvas

    def draw_content(self, canvas: Image.Image, draw: ImageDraw.ImageDraw,
                     t: float) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class _PhotoScene(_ReelScene):
    """A scene backed by a photo with a slow push on it."""

    def __init__(self, *, image: Image.Image | None, seed: str,
                 drift: tuple[float, float] = (0.0, -0.5), **kwargs):
        super().__init__(**kwargs)
        self._source = image
        self._seed = seed
        self._drift = drift
        self._kb: motion.KenBurns | None = None

    def build_plate(self) -> Image.Image:
        source, is_photo = _photo_plate(self._source, self.category, self._seed)
        # A photo needs a much heavier scrim than a designed panel does, because
        # the panel was built to have type on it and the photo was not.
        self._scrim = _reel_scrim(1.0 if is_photo else 0.35)
        # A designed panel drifts too, just less, so no beat is ever a still.
        zoom_to = 1.13 if is_photo else 1.06
        self._kb = motion.KenBurns(source, (REEL_W, REEL_H),
                                   zoom_from=1.0 if not is_photo else 1.03,
                                   zoom_to=zoom_to, drift=self._drift)
        # The cached plate is only what the base class would hand back; the real
        # frames come from the Ken Burns crop, so build it from the same plate
        # rather than cover-fitting the source a second time.
        return self.base_frame(0.0)

    def base_frame(self, t: float) -> Image.Image:
        if self._kb is None:  # pragma: no cover - prepare() always sets it
            return super().base_frame(t)
        frame = self._kb.at(t)
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")
        frame.alpha_composite(self._scrim)
        return frame


# --------------------------------------------------------------------------- #
# Scenes
# --------------------------------------------------------------------------- #
class HookScene(_PhotoScene):
    """The opening two to four seconds. Everything depends on this cut."""

    def __init__(self, *, hook: str, detail: str, **kwargs):
        super().__init__(**kwargs)
        self.hook = hook
        self.detail = detail
        self._fitted = None

    def prepare(self) -> None:
        super().prepare()
        if self._fitted is None:
            hook_font, hook_lines, hook_h = motion.fit_caption(
                self.hook, max_width=TEXT_WIDTH, max_height=520,
                start_size=132, min_size=76)
            detail_font, detail_lines, detail_h = motion.fit_detail(
                self.detail, max_width=TEXT_WIDTH, max_height=200,
                start_size=50, min_size=34) if self.detail else (None, [], 0)
            self._fitted = (hook_font, hook_lines, hook_h,
                            detail_font, detail_lines, detail_h)

    def draw_content(self, canvas, draw, t) -> None:
        hook_font, hook_lines, hook_h, detail_font, detail_lines, detail_h = self._fitted
        rule_h, rule_gap, detail_gap = 9, 34, 34

        block_h = rule_h + rule_gap + hook_h + (detail_gap + detail_h if detail_lines else 0)
        y = BAND_BOTTOM - block_h

        motion.draw_wipe_rule(draw, MARGIN, y, self.accent,
                              t=motion.window(t, 0.0, 0.28), width=150,
                              thickness=rule_h)
        y += rule_h + rule_gap

        y = motion.draw_rising_lines(
            canvas, hook_lines, hook_font, x=MARGIN, y=y,
            t=motion.window(t, 0.04, 1.0), fill=theme.hex_to_rgb(theme.TEXT_PRIMARY),
            line_spacing=1.04, stagger=0.07, rise=44, duration=0.34)

        if detail_lines:
            motion.draw_rising_lines(
                canvas, detail_lines, detail_font, x=MARGIN, y=y + detail_gap,
                t=motion.window(t, 0.30, 1.0),
                fill=theme.hex_to_rgb(theme.TEXT_SECONDARY),
                line_spacing=1.2, stagger=0.06, rise=26, duration=0.34)


class PointScene(_PhotoScene):
    """A body beat: one idea, big line, supporting line."""

    def __init__(self, *, caption: str, detail: str, index: int, **kwargs):
        super().__init__(**kwargs)
        self.caption = caption
        self.detail = detail
        self.index = index
        self._fitted = None
        self._ghost: Image.Image | None = None
        self._ghost_at: tuple[int, int] = (0, 0)

    def prepare(self) -> None:
        super().prepare()
        if self._fitted is None:
            cap_font, cap_lines, cap_h = motion.fit_caption(
                self.caption, max_width=TEXT_WIDTH, max_height=430,
                start_size=112, min_size=64)
            det_font, det_lines, det_h = motion.fit_detail(
                self.detail, max_width=TEXT_WIDTH, max_height=250,
                start_size=46, min_size=32) if self.detail else (None, [], 0)
            self._fitted = (cap_font, cap_lines, cap_h, det_font, det_lines, det_h)
        if self._ghost is None and self.index > 0:
            self._ghost, self._ghost_at = self._build_ghost()

    def _build_ghost(self) -> tuple[Image.Image, tuple[int, int]]:
        """Pre-render the index number into a small tile.

        Drawing 340px type onto a full 1080x1920 layer and compositing it cost
        more per frame than the photo move did. As a tile it is a fraction of
        the pixels and the only per-frame work left is scaling its alpha.
        """
        font = fonts.title_font(340)
        label = f"{self.index:02d}"
        bbox = font.getbbox(label)
        w = max(1, bbox[2] - bbox[0]) + 8
        h = max(1, bbox[3] - bbox[1]) + 8
        tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((4 - bbox[0], 4 - bbox[1]), label, font=font,
                                  fill=theme.rgba(self.accent, 52))
        return tile, (REEL_W - MARGIN - w, 470)

    def draw_content(self, canvas, draw, t) -> None:
        cap_font, cap_lines, cap_h, det_font, det_lines, det_h = self._fitted
        self._draw_ghost_index(canvas, t)

        rule_h, rule_gap, det_gap = 8, 30, 30
        block_h = rule_h + rule_gap + cap_h + (det_gap + det_h if det_lines else 0)
        y = BAND_BOTTOM - block_h

        motion.draw_wipe_rule(draw, MARGIN, y, self.accent,
                              t=motion.window(t, 0.0, 0.24), width=118,
                              thickness=rule_h)
        y += rule_h + rule_gap

        y = motion.draw_rising_lines(
            canvas, cap_lines, cap_font, x=MARGIN, y=y,
            t=motion.window(t, 0.02, 1.0), fill=theme.hex_to_rgb(theme.TEXT_PRIMARY),
            line_spacing=1.04, stagger=0.06, rise=38, duration=0.32)

        if det_lines:
            motion.draw_rising_lines(
                canvas, det_lines, det_font, x=MARGIN, y=y + det_gap,
                t=motion.window(t, 0.24, 1.0),
                fill=theme.hex_to_rgb(theme.TEXT_SECONDARY),
                line_spacing=1.2, stagger=0.05, rise=22, duration=0.32)

    def _draw_ghost_index(self, canvas: Image.Image, t: float) -> None:
        """The oversized beat number, the same editorial device the carousel
        uses, so the two formats read as one system."""
        if self._ghost is None:
            return
        settle = motion.ease_out_cubic(motion.window(t, 0.0, 0.5))
        if settle <= 0.02:
            return
        x, y = self._ghost_at
        y += int(30 * (1.0 - settle))
        tile = self._ghost
        if settle < 0.995:
            # Only the fade-in needs a fresh tile. Once it has settled (which is
            # most of the beat) the cached one is composited as-is.
            tile = tile.copy()
            tile.putalpha(tile.getchannel("A").point(
                lambda v, s=settle: int(v * s)))
        canvas.alpha_composite(tile, (x, y))


class GraphicScene(_ReelScene):
    """The beat that carries an explanatory device instead of a photo."""

    def __init__(self, *, caption: str, device: str, data: dict, seed: str,
                 **kwargs):
        super().__init__(**kwargs)
        self.caption = caption
        self.device = device
        self.data = data or {}
        self._seed = seed
        self._fitted = None

    def build_plate(self) -> Image.Image:
        # Deliberately no photo: the device needs a calm field to sit on, and
        # cutting from photography to a flat panel is what makes this beat feel
        # like a change of gear rather than another slide.
        plate = _panel_plate(self.category, self._seed)
        return Image.alpha_composite(plate, _reel_scrim(0.25))

    def prepare(self) -> None:
        super().prepare()
        if self._fitted is None:
            self._fitted = motion.fit_caption(
                self.caption, max_width=TEXT_WIDTH, max_height=300,
                start_size=88, min_size=54)

    def draw_content(self, canvas, draw, t) -> None:
        cap_font, cap_lines, cap_h = self._fitted
        y = BAND_TOP
        motion.draw_wipe_rule(draw, MARGIN, y, self.accent,
                              t=motion.window(t, 0.0, 0.22), width=118, thickness=8)
        y += 8 + 28
        y = motion.draw_rising_lines(
            canvas, cap_lines, cap_font, x=MARGIN, y=y,
            t=motion.window(t, 0.02, 1.0), fill=theme.hex_to_rgb(theme.TEXT_PRIMARY),
            line_spacing=1.04, stagger=0.06, rise=32, duration=0.3)

        # The device finishes animating well before the cut. Everything after
        # that point is the only part of the beat a viewer can actually read the
        # graphic in, so the reveal is front-loaded rather than spread across
        # the whole slot.
        area = (MARGIN, y + 70, REEL_W - MARGIN, BAND_BOTTOM + 40)
        drawn = graphics.draw_device(canvas, self.device,
                                     motion.window(t, 0.08, 0.62),
                                     area=area, accent=self.accent, data=self.data)
        if not drawn:
            # A missing or malformed device leaves the caption standing on its
            # own, which is a worse beat but still a valid one.
            log.info("graphic device %r produced nothing, caption stands alone",
                     self.device)


class PayoffScene(_ReelScene):
    """The closing idea, centred on a calm panel."""

    def __init__(self, *, line: str, sources: str = "", **kwargs):
        super().__init__(**kwargs)
        self.line = line
        self.sources = sources
        self._fitted = None

    def build_plate(self) -> Image.Image:
        plate = theme.panel_gradient(REEL_W, REEL_H, theme.INK)
        glow_mask = Image.new("L", (REEL_W, REEL_H), 0)
        cx, cy, r = REEL_W // 2, int(REEL_H * 0.42), int(REEL_W * 0.72)
        ImageDraw.Draw(glow_mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=120)
        glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(180))
        glow = Image.new("RGBA", (REEL_W, REEL_H),
                         theme.rgba(theme.mix(theme.hex_to_rgb(theme.INK),
                                              self.accent, 0.5)))
        glow.putalpha(glow_mask)
        return Image.alpha_composite(plate, glow)

    def prepare(self) -> None:
        super().prepare()
        if self._fitted is None:
            self._fitted = motion.fit_caption(
                self.line, max_width=TEXT_WIDTH, max_height=620,
                start_size=124, min_size=68)

    def draw_content(self, canvas, draw, t) -> None:
        font, lines, height = self._fitted
        y = (REEL_H - height) // 2 - 120
        motion.draw_rising_lines(
            canvas, lines, font, x=MARGIN, y=y, t=motion.window(t, 0.0, 1.0),
            fill=theme.hex_to_rgb(theme.TEXT_PRIMARY), line_spacing=1.05,
            stagger=0.07, rise=40, duration=0.36, max_width=TEXT_WIDTH)

        if self.sources:
            fade = motion.ease_out_cubic(motion.window(t, 0.45, 0.82))
            if fade > 0.02:
                alpha = int(255 * fade)
                label_font = fonts.label_font(28, weight=800)
                name_font = fonts.label_font(30, weight=600)
                sy = y + height + 64
                fonts.draw_tracked(draw, (MARGIN, sy), "SOURCES", label_font,
                                   fill=theme.rgba(self.accent, alpha), tracking=1.8)
                sx = MARGIN + fonts.tracked_width(label_font, "SOURCES", 1.8) + 20
                draw.text((sx, sy - 2), self.sources, font=name_font,
                          fill=theme.rgba(theme.TEXT_SECONDARY, alpha))


class OutroScene(_ReelScene):
    """The sign-off. Asks for the follow, then hands back to the loop."""

    def __init__(self, *, headline: str = "", **kwargs):
        super().__init__(**kwargs)
        self.headline = headline or "Your daily brief, minus the noise."
        self._fitted = None

    def prepare(self) -> None:
        super().prepare()
        if self._fitted is None:
            self._fitted = motion.fit_caption(
                self.headline, max_width=TEXT_WIDTH, max_height=340,
                start_size=86, min_size=52)

    def build_plate(self) -> Image.Image:
        plate = theme.panel_gradient(REEL_W, REEL_H, theme.INK)
        glow_mask = Image.new("L", (REEL_W, REEL_H), 0)
        cx, cy, r = REEL_W // 2, int(REEL_H * 0.36), int(REEL_W * 0.68)
        ImageDraw.Draw(glow_mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=132)
        glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(170))
        glow = Image.new("RGBA", (REEL_W, REEL_H),
                         theme.rgba(theme.mix(theme.hex_to_rgb(theme.INK),
                                              theme.hex_to_rgb(BRAND_TERRACOTTA), 0.62)))
        glow.putalpha(glow_mask)
        return Image.alpha_composite(plate, glow)

    def draw_content(self, canvas, draw, t) -> None:
        terra = theme.hex_to_rgb(BRAND_TERRACOTTA)

        mark = theme.logo_mark(240)
        if mark is not None:
            appear = motion.ease_out_back(motion.window(t, 0.0, 0.4))
            if appear > 0.02:
                size = max(8, int(240 * min(1.0, appear)))
                shrunk = mark.resize((size, size), Image.LANCZOS)
                canvas.alpha_composite(shrunk, ((REEL_W - size) // 2,
                                                560 + (240 - size) // 2))

        font, lines, height = self._fitted
        motion.draw_rising_lines(
            canvas, lines, font, x=MARGIN, y=880, t=motion.window(t, 0.18, 1.0),
            fill=theme.hex_to_rgb(theme.TEXT_PRIMARY), line_spacing=1.06,
            stagger=0.07, rise=30, duration=0.34, align="center",
            max_width=TEXT_WIDTH)

        # Follow pill, then the website below it. Each is placed against the
        # previous block's real height, because the sign-off line wraps to one
        # or two lines depending on the words and a fixed y collides on one of
        # the two.
        pill_y = 880 + height + 64
        pill_t = motion.ease_out_back(motion.window(t, 0.38, 0.78))
        pill_h = self._follow_pill_height()
        if pill_t > 0.02:
            self._draw_follow_pill(draw, y=pill_y,
                                   alpha=int(255 * min(1.0, pill_t)))

        web_t = motion.ease_out_cubic(motion.window(t, 0.55, 0.9))
        if web_t > 0.02:
            web_font = fonts.title_font(76)
            width = fonts.text_width(web_font, WEBSITE)
            draw.text(((REEL_W - width) // 2, pill_y + pill_h + 52), WEBSITE,
                      font=web_font, fill=theme.rgba(terra, int(255 * web_t)))

    @staticmethod
    def _follow_pill_font():
        return fonts.label_font(34, weight=800)

    def _follow_pill_height(self) -> int:
        return fonts.line_height(self._follow_pill_font()) + 52

    def _draw_follow_pill(self, draw: ImageDraw.ImageDraw, *, y: int,
                          alpha: int) -> None:
        label = f"FOLLOW {INSTAGRAM_HANDLE}"
        font = self._follow_pill_font()
        tracking = 1.6
        text_w = fonts.tracked_width(font, label, tracking)
        pad_x, pad_y = 44, 26
        w = text_w + pad_x * 2
        h = fonts.line_height(font) + pad_y * 2
        x0 = (REEL_W - w) // 2
        draw.rounded_rectangle([x0, y, x0 + w, y + h], radius=h // 2,
                               fill=theme.rgba(theme.hex_to_rgb(BRAND_TERRACOTTA), alpha))
        ty = y + pad_y - font.getbbox(label)[1]
        fonts.draw_tracked(draw, (x0 + pad_x, ty), label, font,
                           fill=theme.rgba(theme.INK, alpha), tracking=tracking)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def plan_durations(reel: Reel) -> list[float]:
    """Beat lengths from the text they carry, scaled into the target runtime.

    Graphic beats are the exception and get a much longer floor. Their caption
    is short, so measuring them by text alone hands them the briefest cut in the
    reel, which is precisely backwards: the device spends the first half of the
    beat animating in, and only the time after that is time anyone can read it.
    """
    raw = [motion.seconds_for_text(b.caption, b.detail, base=4.6, cap=7.5)
           if b.graphic else motion.seconds_for_text(b.caption, b.detail)
           for b in reel.beats]
    return motion.normalise_durations(
        raw, target=REEL_TARGET_SECONDS - 2.6,   # the outro is added separately
        minimum=REEL_MIN_SECONDS - 2.6,
        maximum=REEL_MAX_SECONDS - 2.6)


def build_scenes(reel: Reel, loader: ImageLoader | None = None,
                 track: "VoiceTrack | None" = None) -> list[motion.Scene]:
    """Turn a Reel into the ordered scenes the encoder will render.

    With a narration track the cuts come from how long each line actually takes
    to say. Without one they come from how long the text takes to read, which is
    an estimate, so the voiced path is the one that stays in sync.
    """
    loader = loader or default_image_loader
    if track is not None and len(track.beat_seconds) == len(reel.beats):
        durations = list(track.beat_seconds)
        outro_seconds = track.outro_seconds
    else:
        durations = plan_durations(reel)
        outro_seconds = 2.6
    total = sum(durations) + outro_seconds

    # Photos are fetched once per distinct URL: a news reel usually points every
    # beat at the same article image, and refetching it per beat would be five
    # network round trips for one picture.
    cache: dict[str, Image.Image | None] = {}

    def photo_for(url: str | None) -> Image.Image | None:
        if not url:
            return None
        if url not in cache:
            cache[url] = loader(url)
        return cache[url]

    scenes: list[motion.Scene] = []
    elapsed = 0.0
    point_index = 0

    for i, (beat, seconds) in enumerate(zip(reel.beats, durations)):
        start, end = elapsed / total, (elapsed + seconds) / total
        elapsed += seconds
        common = dict(category=reel.category, duration=seconds,
                      progress_from=start, progress_to=end)

        if beat.role == "hook":
            scenes.append(HookScene(
                hook=beat.caption, detail=beat.detail,
                image=photo_for(beat.image_url), seed=f"hook:{reel.title}",
                drift=(0.0, -0.6), footer=reel.sources, **common))
        elif beat.graphic:
            scenes.append(GraphicScene(
                caption=beat.caption, device=beat.graphic, data=beat.data,
                seed=f"graphic:{beat.caption}", **common))
        elif beat.role == "payoff":
            scenes.append(PayoffScene(line=beat.caption, sources=reel.sources,
                                      **common))
        else:
            point_index += 1
            # Alternate the drift direction so consecutive photo beats do not
            # push the same way, which is what makes a sequence feel mechanical.
            drift = (0.0, -0.55) if point_index % 2 else (0.35, 0.2)
            scenes.append(PointScene(
                caption=beat.caption, detail=beat.detail, index=point_index,
                image=photo_for(beat.image_url), seed=f"beat{i}:{beat.caption}",
                drift=drift, **common))

    # No category pill on the sign-off: the wordmark is already on the bar, and
    # a "HEADLINNE" pill next to it just says the same word twice.
    scenes.append(OutroScene(
        category=reel.category, duration=outro_seconds,
        progress_from=elapsed / total, progress_to=1.0,
        headline="Your daily brief, minus the noise.", show_pill=False))
    return scenes


def render_reel(reel: Reel, out_dir: Path,
                image_loader: ImageLoader | None = None,
                *, voiceover: bool | None = None,
                tts_client=None) -> tuple[Path, Path]:
    """Render a reel to `<out_dir>/<slot>.mp4` plus its cover PNG.

    Returns (video_path, cover_path) and stamps the paths, the duration and
    whether it ended up narrated onto the Reel.

    The narration is built first, because its per-line lengths are what the cuts
    are laid out against. If it cannot be produced the reel is still rendered,
    timed from reading speed and carrying a silent track.
    """
    from ..config import REEL_VOICEOVER
    from .voice import build_voice_track

    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / f"{reel.slot}.mp4"
    cover_path = out_dir / f"{reel.slot}_cover.png"
    audio_path = out_dir / f"{reel.slot}_voice.wav"

    track = None
    want_voice = REEL_VOICEOVER if voiceover is None else voiceover
    if want_voice:
        try:
            track = build_voice_track(reel, audio_path, client=tts_client)
        except Exception as exc:  # noqa: BLE001 - never lose the reel over audio
            log.error("voiceover failed for %s, continuing silent: %s",
                      reel.slot, exc, exc_info=True)
    if track is None:
        log.info("reel %s will be silent (captions still carry the content).",
                 reel.slot)

    scenes = build_scenes(reel, image_loader, track)

    # The cover is the hook beat held partway through its reveal, so the Reels
    # tab and the profile grid both show a legible, fully-formed frame.
    motion.save_cover(scenes[0], cover_path)
    duration = motion.render_scenes(scenes, video_path, size=(REEL_W, REEL_H),
                                    fps=REEL_FPS,
                                    audio_path=track.path if track else None)

    reel.video_file = str(video_path)
    reel.cover_file = str(cover_path)
    reel.audio_file = str(track.path) if track else None
    reel.has_voiceover = track is not None
    reel.duration_seconds = duration
    log.info("reel [%s] %s rendered: %.1fs across %d scenes, %s",
             reel.slot, reel.kind, duration, len(scenes),
             "narrated" if track else "silent")
    return video_path, cover_path
