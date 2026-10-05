"""The collage layer on reels: tape, torn chips, the sticker, and what they
must not cost.

Every reel test in test_reels.py already runs through the collage path, because
REEL_COLLAGE is on by default. These pin down the guarantees particular to it.
"""

from PIL import Image, ImageDraw

from headlinne.models import Reel, ReelBeat
from headlinne.quality import visual
from headlinne.render import collage, fonts, theme
from headlinne.render import reel as reel_render
from headlinne.render.reel import ReelFrames
from headlinne.render.theme import _chip_split


def _reel(chapter="What happened", graphic="", caption=None):
    data = {"steps": ["One", "Two", "Three"]} if graphic == "flow" else {}
    return Reel(
        slot="reel_1", kind="news", category="Science", title="t", hook="h",
        beats=[
            ReelBeat(role="hook", chapter=chapter, pose="walk", seconds=3.0,
                     caption=caption or "On Tuesday a *four-tonne* rocket "
                                        "stage struck the Moon.",
                     detail="A Falcon 9 second stage."),
            ReelBeat(role="graphic", chapter=chapter, pose="talk", seconds=3.0,
                     graphic=graphic, data=data,
                     caption="Solar activity had been *dragging* it for years.",
                     detail="Seven years off course."),
        ],
        caption="c", hashtags=[], scheduled_time="", dateline="TUE 18 AUG")


def test_a_chip_tears_the_same_way_on_every_frame():
    font = fonts.label_font(58, 800)
    fill = theme.accent_for("Finance")
    a, _ = collage.chip("dragging", font, fill, seed=3)
    b, _ = collage.chip("dragging", font, fill, seed=3)
    assert a.tobytes() == b.tobytes()


def test_punctuation_stays_on_the_paper_and_off_the_chip():
    assert _chip_split("course.") == ("course", ".")
    assert _chip_split("headlinne.com.") == ("headlinne.com", ".")
    assert _chip_split("Crater,") == ("Crater", ",")
    assert _chip_split("SpaceX") == ("SpaceX", "")


def test_a_long_chapter_on_tape_stays_above_the_stage():
    frames = ReelFrames(_reel(chapter="How it got there and why it matters",
                              graphic="flow"), None, loader=lambda _s: None,
                        collage_style=True)
    frames.render(4.0)
    (_name, _x0, y0, _x1, y1) = [b for b in frames.trace if b[0] == "chapter"][0]
    assert y1 < reel_render.GRAPHIC_TOP
    assert y0 > reel_render.PROGRESS_Y


def test_the_sticker_border_never_crosses_the_margin_at_either_end():
    frames = ReelFrames(_reel(), None, loader=lambda _s: None,
                        collage_style=True)
    for t in (0.0, frames.duration - 0.01):
        frames.render(t)
        (pip,) = [b for b in frames.trace if b[0] == "pip"]
        assert pip[1] >= theme.MARGIN - 34
        assert pip[3] <= 1080 - theme.MARGIN + 34


def test_chips_do_not_cost_the_cover_a_size_step():
    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    reel = _reel()
    hook = reel.beats[0]
    tone = theme.accent_for("Science")
    flat = ReelFrames(reel, None, collage_style=False)._hook_size(
        scratch, hook, reel_render.LINE_Y, tone)
    torn = ReelFrames(reel, None, collage_style=True)._hook_size(
        scratch, hook, reel_render.LINE_Y, tone)
    assert torn == flat


def test_every_chip_tone_is_legible():
    report = visual.VisualReport()
    visual.check_contrast(report)
    assert not [e for e in report.errors if "chip" in e]


def test_both_styles_pass_the_geometry_gate():
    for style in (True, False):
        frames = ReelFrames(_reel(graphic="flow"), None, loader=lambda _s: None,
                            collage_style=style)
        report = visual.check_reel_frames(frames, sample_every=15)
        assert report.ok, (style, report.errors[:3])
