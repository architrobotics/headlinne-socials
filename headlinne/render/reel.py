"""Render the daily reel: 1080x1920, paper, animated, encoded to MP4.

One reel a day, on the day's strongest story. Reels are the only Instagram
surface that reliably reaches people who do not already follow the account, so
this is the post that does the finding while the carousel and the story card do
the converting.

The frame budget. Every number is measured from the top of a 1080x1920 canvas
and is the same one design/prototypes/draft.py rendered the approved stills from:

       0- 140   masthead, with the tone rule doubling as the progress bar
     150- 200   chapter marker
     210- 830   plate zone: one to three tilted photographs or generated scenes
     830-1010   Pip on the ground line, bubble above him
    1020-1210   the kinetic line, revealed word by word
    1215-1300   the supporting detail
    1310-1400   the persistent source strip
    1400-1450   the safe-zone rule
    1450+       dead. Instagram's caption block, handle, audio strip and action
                rail sit exactly there, and anything drawn into it is covered.

Three things carry the motion, and none of them is a transition effect:

  Pip walks. His x position is a function of elapsed time across the whole reel,
  so the character crosses the frame once over thirty seconds. The pose cycles
  underneath at its own rate, so he is animated whether or not he is moving.

  The line reveals word by word. The layout is computed for the finished line
  and only the *drawing* is withheld, so nothing re-wraps mid-beat - which is
  the difference between a reveal and a jitter.

  Plates slide in on a cubic ease-out and stay. A plate that animates on every
  frame competes with the text; a plate that arrives once and settles does not.

Anything the renderer draws is traced into `TRACE`, and quality.visual replays
the trace over every frame to assert that no two elements overlap and that
nothing crosses the safe zone. That harness has caught six real bugs, including
a second plate whose right edge sat three pixels outside a 540px frame for forty
consecutive frames.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from ..config import (REEL_FPS, REEL_H, REEL_MAX_SECONDS, REEL_MIN_SECONDS,
                      REEL_TARGET_SECONDS, REEL_W, WEBSITE)
from ..logging_setup import get_logger
from ..models import Reel, ReelBeat
from . import fonts, motion, plate as plate_mod, theme
from .carousel import default_image_loader

log = get_logger("render.reel")

MARGIN = theme.MARGIN

# The vertical grid.
MASTHEAD_Y = 70
PROGRESS_Y = 126
CHAPTER_Y = 160
PLATE_TOP = 214
GROUND_WITH_PLATE = 944
GROUND_BARE = 838
LINE_Y = 966
DETAIL_FLOOR = 1246
STRIP_RULE_Y = 1264
STRIP_TICKS_Y = 1290
STRIP_SOURCES_Y = 1342
SAFE_RULE_Y = 1400
SAFE_BOTTOM = theme.REEL_SAFE_BOTTOM

PLATE_MAX_W_SINGLE = 520
PLATE_MAX_W_PAIR = 430
PLATE_MAX_H = 392

# Pip is smaller when a plate is above him, so the two never fight for the eye.
PIP_SCALE_WITH_PLATE = 12
PIP_SCALE_BARE = 14

# The sign-off pose rotates by day. Same trick generate/hooks.py uses for the
# hook archetypes: the code owns the variety, so a month of reels never
# collapses into one look.
CTA_POSES = ("bounce", "present", "point", "cheer", "talk",
             "flap", "deliver", "walk", "nod", "peek", "jump")


def cta_pose(day_ordinal: int = 0) -> str:
    return CTA_POSES[day_ordinal % len(CTA_POSES)]


# The kinetic line finishes revealing this far through its beat. Named because
# the cover frame has to land after it - see cover_offset_ms.
LINE_REVEAL_FRACTION = 0.34


def cover_offset_ms(reel, default_ms: int = 1200) -> int:
    """Which frame becomes the cover, in milliseconds from the start.

    This frame is the reel's thumbnail in the Reels tab and in the profile
    grid, so it is the single most-seen frame of the whole video and it is
    permanent. It has to land after the opening line has finished revealing
    itself word by word, or the grid keeps a picture of a half-written
    sentence forever.

    A fixed 1200ms was right only by luck. It works out at 40% through a three
    second beat, comfortably past the reveal - but beats stretch to fit a
    spoken line when REEL_VOICEOVER is on, and on a six second opening beat the
    same 1200ms lands at 59% of the way through the reveal and freezes a
    part-drawn hook onto the profile grid. Deriving it from the beat removes
    the coincidence.
    """
    beats = getattr(reel, "beats", None)
    if not beats:
        return default_ms
    # The same floor _beat_starts applies, so this agrees with the timeline the
    # renderer actually walks.
    first = max(0.4, float(getattr(beats[0], "seconds", 0) or 0))
    revealed = LINE_REVEAL_FRACTION * first
    settled = revealed + 0.25          # a moment of air after the last word
    latest = first - 0.15              # and still inside the opening beat
    if settled > latest:
        settled = max(revealed, latest)
    return int(max(0.0, settled) * 1000)


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class ReelFrames:
    """Renders any frame of a reel on demand, and traces what it drew.

    Frames are produced lazily and piped straight into ffmpeg rather than held
    in memory: at 30fps a thirty second reel is 900 frames of 1080x1920, which
    is far too much to keep at once.
    """

    def __init__(self, reel: Reel, story=None, *, loader=None,
                 day_ordinal: int = 0, dark: bool = False):
        self.reel = reel
        self.story = story
        self.loader = loader
        self.day_ordinal = day_ordinal
        self.dark = dark
        self.trace: list[tuple[str, int, int, int, int]] = []
        self._plates: dict[str, Image.Image] = {}
        self._cycles: dict[str, list[str]] = {}
        self.duration = max(REEL_MIN_SECONDS,
                            min(REEL_MAX_SECONDS,
                                sum(b.seconds for b in reel.beats) or 30.0))
        self._starts = self._beat_starts()

    # ---- timing ----------------------------------------------------------- #
    def _beat_starts(self) -> list[float]:
        starts, t = [], 0.0
        for beat in self.reel.beats:
            starts.append(t)
            t += max(0.4, beat.seconds)
        return starts

    def beat_at(self, t: float) -> tuple[int, ReelBeat, float]:
        """(index, beat, progress-through-the-beat) at time `t`."""
        index = 0
        for i, start in enumerate(self._starts):
            if t >= start:
                index = i
        beat = self.reel.beats[index]
        start = self._starts[index]
        end = (self._starts[index + 1] if index + 1 < len(self._starts)
               else self.duration)
        local = (t - start) / max(end - start, 0.001)
        return index, beat, max(0.0, min(1.0, local))

    # ---- assets ----------------------------------------------------------- #
    def _cycle(self, name: str) -> list[str]:
        if name not in self._cycles:
            builder = theme.CYCLES.get(name, theme.CYCLES["idle"])
            self._cycles[name] = builder()
        return self._cycles[name]

    def _plate(self, key: str, max_w: int) -> Optional[Image.Image]:
        """A plate for this beat, built once and reused across every frame."""
        cache_key = f"{key}:{max_w}"
        if cache_key in self._plates:
            return self._plates[cache_key]
        img, _rung = plate_mod.for_story(self.story, self.loader,
                                         width=560, height=380)
        if img is not None:
            img = img.copy()
            img.thumbnail((max_w, PLATE_MAX_H), Image.LANCZOS)
        self._plates[cache_key] = img
        return img

    def _note(self, label: str, x0, y0, x1, y1) -> None:
        self.trace.append((label, int(x0), int(y0), int(x1), int(y1)))

    # ---- the frame -------------------------------------------------------- #
    def render(self, t: float) -> Image.Image:
        self.trace.clear()
        index, beat, local = self.beat_at(t)
        # A beat may name its own tone; otherwise its role picks one. Either way
        # a disputed or sensitive story overrides both inside tone_for, so the
        # disagree state is never dressed in a confident colour.
        tone = theme.tone_for(self.story, category=self.reel.category,
                              role=beat.tone or beat.role)

        canvas = theme.night(REEL_W, REEL_H) if self.dark else theme.paper(REEL_W, REEL_H)
        draw = ImageDraw.Draw(canvas)

        theme.draw_masthead(canvas, draw, tone=tone, date_text=self.reel.dateline,
                            y=MASTHEAD_Y, progress=t / max(self.duration, 0.001),
                            dark=self.dark)

        chapter = f"{index + 1:02d} · {(beat.chapter or beat.role).upper()}"
        draw.text((MARGIN, CHAPTER_Y), chapter, font=fonts.label_font(24, 700),
                  fill=theme.safe_fill(tone, 24))
        self._note("chapter", *draw.textbbox((MARGIN, CHAPTER_Y), chapter,
                                             font=fonts.label_font(24, 700)))

        ground = self._draw_plates(canvas, beat, local)
        pip_box = self._draw_pip(canvas, draw, beat, t, ground,
                                 has_plate=bool(beat.plates))
        if beat.say and local < 0.74 and pip_box is not None:
            self._draw_bubble(canvas, draw, beat.say, pip_box)

        y = self._draw_line(draw, beat, local, tone)
        self._draw_detail(draw, beat, y)
        self._draw_strip(canvas, draw)
        return canvas.convert("RGB")

    # ---- pieces ----------------------------------------------------------- #
    def _draw_plates(self, canvas: Image.Image, beat: ReelBeat,
                     local: float) -> int:
        # A sensitive story carries no plate, whatever the beat asks for. The
        # generator clears them too; this is the second lock, because a pixel
        # illustration beside a death toll is the tonal failure the sober
        # template exists to prevent.
        if not beat.plates or getattr(self.story, "sensitive", False):
            return GROUND_BARE
        count = len(beat.plates)
        gutter = 20
        left, right = MARGIN - gutter, REEL_W - MARGIN + gutter
        ease = _ease_out_cubic(local / 0.28)
        for j, key in enumerate(beat.plates):
            img = self._plate(key, PLATE_MAX_W_SINGLE if count == 1
                              else PLATE_MAX_W_PAIR)
            if img is None:
                continue
            if count == 1:
                px = (REEL_W - img.width) // 2
                py = PLATE_TOP + int((1 - ease) * 40)
            else:
                span = max(0, (right - left) - img.width)
                px = left + (j * span) // max(1, count - 1)
                py = PLATE_TOP - 8 + (j % 2) * 46 + int((1 - ease) * 40)
            # Never leave the frame. A second plate ran three pixels past the
            # right edge for forty consecutive frames before this clamp existed.
            px = max(left, min(px, right - img.width))
            faded = img.copy()
            faded.putalpha(faded.getchannel("A").point(lambda a: int(a * ease)))
            canvas.alpha_composite(faded, (px, py))
            self._note(f"plate{j}", px, py, px + img.width, py + img.height)
        return GROUND_WITH_PLATE

    def _draw_pip(self, canvas: Image.Image, draw: ImageDraw.ImageDraw,
                  beat: ReelBeat, t: float, ground: int,
                  has_plate: bool) -> Optional[tuple[int, int, int, int]]:
        rule = theme.hex_to_rgb("#3A3027") if self.dark else theme.hex_to_rgb(
            theme.SURFACE_DEEP)
        draw.rectangle([0, ground, REEL_W, ground + 5], fill=rule)

        pose = beat.pose
        if pose == "cta":
            pose = cta_pose(self.day_ordinal)
        if not pose or getattr(self.story, "sensitive", False):
            return None                     # sensitive stories carry no mascot

        cycle = self._cycle(pose)
        grid = theme.pip_frame(cycle, t)
        from . import pip as _pip

        scale = PIP_SCALE_WITH_PLATE if has_plate else PIP_SCALE_BARE
        sprite = _pip.render(grid, scale)
        # Eased rather than linear. The crossing takes the whole reel, and at
        # a constant rate he arrives at the right edge at exactly the speed he
        # left the left one, which reads as a conveyor belt. The endpoints are
        # unchanged, so the overlap and safe-zone harness sees the same bounds.
        travel = int(_pip.ease_in_out_sine(t / max(self.duration, 0.001))
                     * (REEL_W - 2 * MARGIN - sprite.width))
        x = MARGIN - 30 + travel
        y = ground - sprite.height + 4
        canvas.alpha_composite(sprite.convert("RGBA"), (x, y))
        box = (x, y, x + sprite.width, ground + 4)
        self._note("pip", *box)
        return box

    def _draw_bubble(self, canvas: Image.Image, draw: ImageDraw.ImageDraw,
                     say: str, pip_box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, _y1 = pip_box
        box = theme.bubble_beside(canvas, draw, say, pip_x=x0, pip_w=x1 - x0,
                                  pip_top=y0, width=REEL_W, margin=MARGIN,
                                  max_w=520)
        self._note("bubble", *box)

    def _draw_line(self, draw: ImageDraw.ImageDraw, beat: ReelBeat,
                   local: float, tone) -> int:
        y = LINE_Y
        if beat.graphic == "counter" and beat.data.get("value"):
            # The figure counts up. Every printed figure is verified against the
            # source article in generate/reel.py before it reaches this point.
            target = beat.data["value"]
            roll = _ease_out_cubic(min(1.0, local / 0.42))
            try:
                shown = f"{int(float(target) * roll):,}"
            except (TypeError, ValueError):
                shown = str(target)
            font = fonts.title_font(140, 800)
            draw.text((MARGIN, y), shown, font=font, fill=theme.safe_fill(tone, 140))
            box = draw.textbbox((MARGIN, y), shown, font=font)
            self._note("counter", *box)
            y = box[3] + 16

        top = y
        y = theme.draw_rich(draw, beat.caption, x=MARGIN, y=y,
                            max_w=REEL_W - 2 * MARGIN, size=58, tone=tone,
                            reveal=min(1.0, local / LINE_REVEAL_FRACTION),
                            base_fill=theme.hex_to_rgb(
                                theme.CREAM if self.dark else theme.TEXT_PRIMARY))
        if y > top:
            self._note("line", MARGIN, top, REEL_W - MARGIN, y)
        return y

    def _draw_detail(self, draw: ImageDraw.ImageDraw, beat: ReelBeat,
                     y: int) -> None:
        if not beat.detail:
            return
        font = fonts.body_font(30, 450)
        dy = y + 26
        box = draw.textbbox((MARGIN, dy), beat.detail, font=font)
        # Position from where the line actually ended, never from a fixed y:
        # that is what collided the detail with the main line on the counter
        # beat, where the figure makes the block taller than any other.
        if box[3] > DETAIL_FLOOR:
            dy = DETAIL_FLOOR - (box[3] - box[1])
        draw.text((MARGIN, dy), beat.detail, font=font,
                  fill=(168, 154, 137) if self.dark
                  else theme.hex_to_rgb(theme.TEXT_SECONDARY))
        self._note("detail", *draw.textbbox((MARGIN, dy), beat.detail, font=font))

    def _draw_strip(self, canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        rule = theme.hex_to_rgb("#3A3027") if self.dark else theme.hex_to_rgb(
            theme.SURFACE_DEEP)
        draw.rectangle([MARGIN, STRIP_RULE_Y, REEL_W - MARGIN,
                        STRIP_RULE_Y + 3], fill=rule)
        if self.story is not None:
            theme.draw_receipt_inline(draw, self.story, x=MARGIN,
                                      y=STRIP_TICKS_Y, dark=self.dark)
            self._note("strip", MARGIN, STRIP_TICKS_Y, REEL_W - MARGIN,
                       STRIP_TICKS_Y + 36)
        if self.reel.sources:
            font = fonts.label_font(22, 500)
            draw.text((MARGIN, STRIP_SOURCES_Y), self.reel.sources, font=font,
                      fill=(168, 154, 137) if self.dark
                      else theme.hex_to_rgb(theme.TEXT_SECONDARY))
            self._note("sources", *draw.textbbox((MARGIN, STRIP_SOURCES_Y),
                                                 self.reel.sources, font=font))
        draw.rectangle([MARGIN, SAFE_RULE_Y, REEL_W - MARGIN,
                        SAFE_RULE_Y + 3], fill=rule)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def plan_durations(reel: Reel, track=None) -> list[float]:
    """Set each beat's length, and return them.

    When there is a narration track *the narration drives the edit*: each cut
    lasts exactly as long as its spoken line plus a little air, rather than as
    long as the code guesses the text takes to read. That is the difference
    between a video with words over it and one that is actually cut to its
    voice.

    A track whose length does not match the beat list is ignored rather than
    trusted. A stale track - built for a different script, or truncated when one
    line failed to synthesise - would silently desync every cut after the point
    it diverges, and a reel that drifts out of sync is worse than one paced by
    reading speed.

    Without a track, lengths come from how much text each beat carries and are
    then scaled proportionally into the target window, which keeps the rhythm
    the copy asked for while guaranteeing a runtime that holds attention.
    """
    beats = reel.beats
    if track is not None:
        spoken = list(getattr(track, "beat_seconds", []) or [])
        outro = getattr(track, "outro_seconds", None)
        if outro is not None and len(spoken) == len(beats) - 1:
            spoken.append(outro)      # the outro arrives as its own measurement
        if len(spoken) == len(beats) and all(s > 0 for s in spoken):
            for beat, seconds in zip(beats, spoken):
                beat.seconds = float(seconds)
            return [b.seconds for b in beats]
        log.warning("narration track has %d lengths for %d beats, ignoring it "
                    "and pacing by reading speed instead", len(spoken), len(beats))

    # Reading speed: the on-screen line at roughly 200 wpm, plus air for the cut
    # to land, with a floor so a three-word beat still gets a moment.
    raw = [max(1.6, len(b.caption.split()) / (200 / 60) + 1.1) for b in beats]
    scaled = motion.normalise_durations(raw, target=REEL_TARGET_SECONDS,
                                        minimum=REEL_MIN_SECONDS,
                                        maximum=REEL_MAX_SECONDS)
    for beat, seconds in zip(beats, scaled):
        beat.seconds = round(seconds, 3)
    return [b.seconds for b in beats]


class _ContinuousScene(motion.Scene):
    """The whole reel as one scene.

    The reel is deliberately not cut into one scene per beat. Pip walks across
    the full thirty seconds and the progress bar fills across them, so both are
    functions of absolute time; splitting the render at beat boundaries would
    make every scene need to know where the previous one left him. One scene
    that owns the clock is simpler and is what the approved draft does.
    """

    def __init__(self, frames: "ReelFrames"):
        self.frames = frames
        self.duration = frames.duration

    def frame(self, t: float) -> Image.Image:
        return self.frames.render(t * self.duration)


def render_reel(reel: Reel, out_dir: Path, story=None, *,
                image_loader: Callable | None = None, day_ordinal: int = 0,
                audio_path: Path | None = None, voiceover: bool | None = None,
                tts_client=None) -> Path:
    """Encode the reel to MP4 and write its cover, returning the video path.

    When the voiceover is on, the narration is built first and the beat lengths
    come from it, because a cut should last as long as the voice needs rather
    than as long as the code guesses the text takes to read. One speech request
    covers the whole reel - see render/voice.py for why that trade is worth it.
    """
    from ..config import REEL_VOICEOVER

    out_dir.mkdir(parents=True, exist_ok=True)
    voiceover = REEL_VOICEOVER if voiceover is None else voiceover

    if voiceover and audio_path is None:
        from .voice import build_voice_track

        track = build_voice_track(reel, out_dir / f"{reel.slot}.wav",
                                  client=tts_client)
        if track is not None:
            plan_durations(reel, track)
            audio_path = track.path
            reel.has_voiceover = True
        else:
            plan_durations(reel)          # reading speed, and a silent track
    elif not reel.beats or not any(b.seconds for b in reel.beats):
        plan_durations(reel)

    frames = ReelFrames(reel, story, loader=image_loader or default_image_loader,
                        day_ordinal=day_ordinal)
    scene = _ContinuousScene(frames)

    video_path = out_dir / f"{reel.slot}.mp4"
    cover_path = out_dir / f"{reel.slot}_cover.png"

    # The cover is the frame the Reels tab shows before anyone presses play, so
    # it is taken from partway into the opening beat - by which point the line
    # has revealed and Pip has moved, and it looks like the reel rather than
    # like an empty first frame.
    motion.save_cover(scene, cover_path, t=min(0.12, 1.0))

    duration = motion.render_scenes([scene], video_path, size=(REEL_W, REEL_H),
                                    fps=REEL_FPS, audio_path=audio_path)
    reel.video_file = str(video_path)
    reel.cover_file = str(cover_path)
    reel.duration_seconds = round(duration, 2)
    log.info("rendered reel %s: %.1fs at %dfps", reel.slot, duration, REEL_FPS)
    return video_path
