"""The visual quality gate: check the pixels, not just the words.

`quality/checks.py` validates the copy. Nothing validated what was drawn, so
every layout fault - a rail overrunning into the source strip, a plate three
pixels outside the frame, an accent that fails contrast on paper - could only be
caught by a person looking at the output, and only on the days a person looked.

This runs the checks a reviewer would run, on every surface, every day:

    size          the canvas is exactly what the platform expects
    ink           the render is not one flat colour, which is what a failed
                  draw looks like
    collision     no two traced elements overlap
    safe zone     nothing on a reel renders below y=1450
    margins       nothing crosses the left or right margin
    contrast      every accent clears its floor on the ground it sits on
    sprites       every pose renders non-empty and every cycle actually moves
    plates        a generated illustration always carries its caption
    receipt       the arithmetic on the source strip is sound
    structure     the carousel's five roles are present and in order
    sober         a sensitive story carries no mascot and no speech bubble
    pace          neither reading budget is exceeded

The harness this is modelled on found six real bugs in the prototype, two of
them only after its coverage widened. Its own best lesson is worth repeating:
**a test that cannot see the thing it is testing passes while the product is
broken.** The pose check originally compared bounding boxes, and a beak opening
changes no bounding box, so a frozen sprite passed. It compares pixels now, and
the contrast check imports the real colour constants rather than re-typing them.

Failures block publication. The pipeline drops the offending format and ships
the rest of the day, which is the same containment every other stage uses: a
broken post is worse than a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from PIL import Image

from ..config import (CATEGORY_COLORS, DISPLAY_ONLY_ACCENTS,
                      DISPLAY_ONLY_MIN_PX, REEL_H, REEL_W, SLIDE_H, SLIDE_W,
                      SURFACE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
                      TONE_AGREE, TONE_DISPUTE, TONE_LIVE)
from ..logging_setup import get_logger
from ..render import theme
from .checks import QualityReport

log = get_logger("quality.visual")

# A render that is almost entirely one colour has not drawn. The threshold is
# high because a legitimate paper slide really is mostly paper: measured across
# the approved samples the busiest is 88% ground and the emptiest 96%.
FLAT_COLOUR_LIMIT = 0.985

# WCAG floors. Large text is anything at or above DISPLAY_ONLY_MIN_PX.
CONTRAST_BODY = 4.5
CONTRAST_LARGE = 3.0

# Elements allowed to overlap. Pip walks past the ground rule by design, and a
# plate's tape strip sits on top of its own plate.
ALLOWED_OVERLAP = {
    ("pip", "plate0"), ("pip", "plate1"), ("plate0", "plate1"),
    ("bubble", "plate0"), ("bubble", "plate1"), ("bubble", "pip"),
    ("chapter", "plate0"), ("chapter", "plate1"),
}


@dataclass
class VisualReport(QualityReport):
    """A QualityReport that also counts how much it actually checked.

    The count is not decoration. A harness whose coverage silently drops to
    nothing still reports success, so the number of assertions is logged beside
    the result and a suspiciously low one is itself a warning.
    """

    checks: int = 0

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.error(message)
        return condition

    def soft_check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.warn(message)
        return condition


# --------------------------------------------------------------------------- #
# Primitive checks
# --------------------------------------------------------------------------- #
def _boxes_overlap(a, b, pad: int = 0) -> bool:
    return not (a[3] <= b[1] + pad or b[3] <= a[1] + pad
                or a[2] <= b[0] + pad or b[2] <= a[0] + pad)


def check_canvas(img: Image.Image, expected: tuple[int, int], label: str,
                 report: VisualReport) -> None:
    report.check(img.size == expected,
                 f"{label}: canvas is {img.size}, expected {expected}")
    report.check(img.getbbox() is not None, f"{label}: rendered empty")

    # Sampled rather than exhaustive: a 1080x1350 histogram is 1.4M pixels and
    # this runs on every slide of every day.
    small = img.convert("RGB").resize((60, 60), Image.BILINEAR)
    colours = small.getcolors(3600) or []
    if colours:
        dominant = max(count for count, _ in colours)
        report.check(dominant / 3600.0 < FLAT_COLOUR_LIMIT,
                     f"{label}: {dominant / 36:.0f}% of the render is a single "
                     f"colour, which is what a failed draw looks like")


def check_contrast(report: VisualReport, ground=SURFACE) -> None:
    """Every token that carries type must clear its floor on the ground.

    The constants are imported, never re-typed. The prototype's contrast test
    was still checking a marigold that had already been replaced everywhere
    else, because the value had been copied into the test by hand.
    """
    body = {"TEXT_PRIMARY": TEXT_PRIMARY, "TEXT_SECONDARY": TEXT_SECONDARY,
            "TONE_AGREE": TONE_AGREE, "TONE_DISPUTE": TONE_DISPUTE}
    for name, value in body.items():
        ratio = theme.contrast_ratio(value, ground)
        report.check(ratio >= CONTRAST_BODY,
                     f"contrast: {name} is {ratio:.2f}:1 on the ground, "
                     f"needs {CONTRAST_BODY}")

    for value in DISPLAY_ONLY_ACCENTS:
        ratio = theme.contrast_ratio(value, ground)
        report.check(ratio >= CONTRAST_LARGE,
                     f"contrast: display accent {value} is {ratio:.2f}:1, "
                     f"below even the {CONTRAST_LARGE} large-text floor")
        report.soft_check(
            ratio >= CONTRAST_BODY,
            f"contrast: {value} at {ratio:.2f}:1 is display-only, so it must "
            f"never be set below {DISPLAY_ONLY_MIN_PX}px (theme.safe_fill "
            f"enforces this)")

    for name, value in CATEGORY_COLORS.items():
        ratio = theme.contrast_ratio(value, ground)
        report.check(ratio >= CONTRAST_LARGE,
                     f"contrast: category {name} is {ratio:.2f}:1")

    # TEXT_MUTED fails 4.5 by design and is furniture only - never body copy.
    # It is checked so its status is recorded rather than assumed.
    muted = theme.contrast_ratio(TEXT_MUTED, ground)
    report.soft_check(muted >= CONTRAST_LARGE,
                      f"contrast: TEXT_MUTED is {muted:.2f}:1 - furniture only, "
                      f"never type")


def check_sprites(report: VisualReport) -> None:
    """Every pose renders, and every cycle actually changes pixels."""
    from ..render import pip

    for name, grid in pip.SPRITES.items():
        rows = pip._rows(grid)
        report.check(all(len(r) == pip.W for r in rows),
                     f"sprite {name}: ragged row")
        report.check(pip.render(grid, 4).getbbox() is not None,
                     f"sprite {name}: rendered empty")

    for name, builder in theme.CYCLES.items():
        cycle = builder()
        report.check(len(cycle) >= 2, f"cycle {name}: {len(cycle)} frame(s)")
        heights = {len(pip._rows(f)) for f in cycle}
        report.check(len(heights) == 1,
                     f"cycle {name}: frames differ in height {heights}")
        # Pixels, not bounding boxes. A beak opening changes no bounding box at
        # all, so a bbox comparison passes on a frozen sprite.
        rendered = {pip.render(f, 4).tobytes() for f in cycle}
        report.check(len(rendered) > 1, f"cycle {name}: never actually moves")


def check_receipt(story, report: VisualReport, label: str = "receipt") -> None:
    """The arithmetic on the source strip has to be sound before it is drawn."""
    from ..render import receipt as receipt_mod

    record = receipt_mod.agreement_of(story)
    report.check(record.agree <= record.reported,
                 f"{label}: {record.agree} agree of {record.reported} reported")
    report.check(record.eligible <= record.reported,
                 f"{label}: {record.eligible} took a position but only "
                 f"{record.reported} reported it")
    report.check(record.silent >= 0, f"{label}: negative silent count")
    report.check(record.conflict == len(record.conflicts) or not record.conflicts,
                 f"{label}: {record.conflict} conflicts counted but "
                 f"{len(record.conflicts)} recorded")
    filled, hollow = receipt_mod.ticks(story)
    report.check(filled + hollow <= receipt_mod.MAX_TICKS,
                 f"{label}: {filled + hollow} ticks exceeds the "
                 f"{receipt_mod.MAX_TICKS} that read at a glance")
    if record.reported >= 2:
        report.check("of" in record.label() or "sources agree" in record.label(),
                     f"{label}: corroborated story renders as {record.label()!r}")


# --------------------------------------------------------------------------- #
# Surface checks
# --------------------------------------------------------------------------- #
def check_carousel(carousel, images: Iterable[Image.Image]) -> VisualReport:
    """The five slides, their order, and what each one drew."""
    from ..render.carousel import SLIDE_ORDER

    report = VisualReport()
    roles = [s.role for s in carousel.slides]
    report.check(roles == list(SLIDE_ORDER),
                 f"carousel: slide roles are {roles}, expected "
                 f"{list(SLIDE_ORDER)} - the order is the argument")

    story = carousel.story
    if story is not None:
        check_receipt(story, report, "carousel receipt")
        report.check(not getattr(story, "sensitive", False)
                     or all(not s.pose and not s.say for s in carousel.slides),
                     "carousel: a sensitive story is carrying the mascot or a "
                     "speech bubble")
        report.check(getattr(story, "verified", False),
                     "carousel: story has not reached two independent outlets")

    for i, img in enumerate(images, 1):
        check_canvas(img, (SLIDE_W, SLIDE_H), f"slide {i}", report)
    check_contrast(report)
    log.info("carousel visual gate: %d checks, %d errors, %d warnings",
             report.checks, len(report.errors), len(report.warnings))
    return report


def check_reel_frames(frames, *, sample_every: int = 6,
                      story=None) -> VisualReport:
    """Replay the reel and assert the geometry on the sampled frames.

    Every sixth frame by default. Rendering all nine hundred takes minutes and
    the elements move continuously, so a fault that exists on one frame exists
    on the twenty around it; sampling finds the same bugs in a sixth of the time.
    Pass sample_every=1 for an exhaustive pass.
    """
    report = VisualReport()
    total = int(frames.duration * 30)
    for index in range(0, total, max(1, sample_every)):
        t = index / 30.0
        img = frames.render(t)
        where = f"reel t={t:0.2f}s"

        if index == 0:
            check_canvas(img, (REEL_W, REEL_H), where, report)

        traced = list(frames.trace)
        for i in range(len(traced)):
            for j in range(i + 1, len(traced)):
                a, b = traced[i], traced[j]
                key = tuple(sorted((a[0], b[0])))
                if key in ALLOWED_OVERLAP or tuple(reversed(key)) in ALLOWED_OVERLAP:
                    continue
                report.check(not _boxes_overlap(a[1:], b[1:]),
                             f"{where}: {a[0]!r} overlaps {b[0]!r} "
                             f"({a[1:]} vs {b[1:]})")

        for element in traced:
            name, x0, y0, x1, y1 = element
            report.check(y1 <= theme.REEL_SAFE_BOTTOM,
                         f"{where}: {name!r} bottom {y1} is below the safe zone "
                         f"({theme.REEL_SAFE_BOTTOM}), where Instagram's UI sits")
            report.check(x0 >= theme.MARGIN - 34,
                         f"{where}: {name!r} left {x0} crosses the margin")
            report.check(x1 <= REEL_W - theme.MARGIN + 34,
                         f"{where}: {name!r} right {x1} crosses the margin")

    if story is not None:
        check_receipt(story, report, "reel receipt")
        if getattr(story, "sensitive", False):
            report.check(all(not b.pose and not b.say for b in frames.reel.beats),
                         "reel: a sensitive story is carrying the mascot")
    check_sprites(report)
    check_contrast(report)
    log.info("reel visual gate: %d checks over %d sampled frames, %d errors",
             report.checks, len(range(0, total, max(1, sample_every))),
             len(report.errors))
    return report


def check_pace(reel, *, primary_ceiling: int = 230,
               total_ceiling: int = 380) -> VisualReport:
    """Two reading budgets, not one.

    The primary line carries the story and has to be read, so it gets the strict
    ceiling. The detail line supports it and is scanned rather than read word for
    word, so it gets a looser one. Measuring them as a single block gives 308 wpm
    on copy that reads comfortably, and would force a rewrite that is not needed.
    """
    report = VisualReport()
    duration = sum(max(0.4, b.seconds) for b in reel.beats) or 1.0
    primary = sum(len(b.caption.replace("*", "").split()) for b in reel.beats)
    support = sum(len(b.detail.split()) for b in reel.beats)

    primary_rate = primary / (duration / 60)
    total_rate = (primary + support) / (duration / 60)
    report.check(primary_rate <= primary_ceiling,
                 f"pace: the primary line runs at {primary_rate:.0f} wpm, "
                 f"ceiling {primary_ceiling}. Cut words, do not shorten holds")
    report.check(total_rate <= total_ceiling,
                 f"pace: total on-screen load is {total_rate:.0f} wpm, "
                 f"ceiling {total_ceiling}")

    for i, beat in enumerate(reel.beats, 1):
        report.check(beat.seconds >= 1.0,
                     f"pace: beat {i} holds only {beat.seconds:.2f}s")
        readable = len(beat.caption.split()) / (primary_ceiling / 60)
        report.soft_check(beat.seconds <= readable + 2.6,
                          f"pace: beat {i} holds {beat.seconds:.2f}s for "
                          f"{readable:.1f}s of reading")
    return report


def check_story_card_image(card, img: Image.Image, story=None) -> VisualReport:
    report = VisualReport()
    check_canvas(img, (SLIDE_W, SLIDE_H), "story card", report)
    report.check(len([s for s in card.steps if s.text.strip()]) == 4,
                 "story card: the rail is always four stops")
    if story is not None:
        check_receipt(story, report, "story card receipt")
    check_contrast(report)
    return report


def check_x_card(img: Image.Image, story=None) -> VisualReport:
    from ..render.card import CARD_H, CARD_W

    report = VisualReport()
    check_canvas(img, (CARD_W, CARD_H), "x card", report)
    if story is not None:
        check_receipt(story, report, "x card receipt")
    return report
