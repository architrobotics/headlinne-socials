"""Layout regressions from the October 2026 design pass.

Each of these was visible on a rendered post: a subtitle printed over the
receipt, a photo hanging off the bottom of a slide, a reel cover that was a
grey sentence on blank paper, an X card that said "Today's science news in a
nutshell" and nothing else.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image

from headlinne.config import SLIDE_H
from headlinne.generate.common import clamp_sentences
from headlinne.models import Agreement, InstagramCarousel, Reel, ReelBeat, Slide, Story, TwitterPost
from headlinne.quality import visual
from headlinne.render import carousel as carousel_render
from headlinne.render import plate as plate_mod
from headlinne.render import theme
from headlinne.render.card import choose_layout
from headlinne.render.reel import ReelFrames, cover_offset_ms

RED = (255, 0, 0, 255)


def _story(title="Leucine helps your cells make more energy", *, category="Science",
           summary="", outlets=1):
    names = ["ScienceDaily"] + [f"Outlet{i}" for i in range(1, outlets)]
    return Story(title=title, summary=summary, url="https://x.test/a",
                 category=category, source=names[0], tier=1.0,
                 published_iso="2026-10-04T06:00:00+00:00", image_url="photo",
                 agreement=Agreement(reported=outlets, agree=outlets, outlets=names))


def _carousel(story, slides):
    return InstagramCarousel(slot="instagram_1", category=story.category,
                             num_slides=len(slides), title="t", slides=slides,
                             caption="c", hashtags=[],
                             scheduled_time="2026-10-04T16:00:00+05:30",
                             story=story, story_url=story.url)


def test_a_long_cover_fits_above_the_receipt():
    story = _story()
    headline = "Leucine helps your cells make a great deal more energy than thought"
    subtitle = "It protects mitochondria proteins from being destroyed, researchers say."
    bottom = SLIDE_H - carousel_render.RECEIPT_FROM_BOTTOM - 28
    size, sub_lines = carousel_render._fit_headline_and_sub(
        headline, subtitle, top=carousel_render.HEADLINE_Y, bottom=bottom, start=92)
    from headlinne.render import fonts
    width = carousel_render.SLIDE_W - 2 * carousel_render.MARGIN
    lines = fonts.wrap_text(fonts.title_font(size, 800), headline, width)
    end = (carousel_render.HEADLINE_Y + len(lines) * int(size * 1.14)
           + int(size * carousel_render.DESCENDER_GAP) + sub_lines * int(42 * 1.3))
    assert end <= bottom
    assert len(lines) <= 3


def test_the_scale_photo_never_crosses_the_footer(tmp_path):
    story = _story()
    long_text = ("It happens inside the mitochondria, which are the tiny power plants "
                 "found in almost every cell in your body. There are hundreds in each "
                 "one, and they never stop.")
    slide = Slide(role="scale", headline="", kicker="THE SCALE", figure="", unit="",
                  explanation=long_text, index=2)
    red = Image.new("RGBA", (900, 600), RED)
    img = carousel_render._render_scale(slide, _carousel(story, [slide]), story,
                                        theme.hex_to_rgb(theme.BRAND_TERRACOTTA),
                                        lambda _src: red)
    px = img.convert("RGB").load()
    footer = SLIDE_H - theme.FOOTER_RULE_FROM_BOTTOM
    reds = [y for y in range(0, SLIDE_H, 4) for x in range(0, img.width, 8)
            if px[x, y][0] > 230 and px[x, y][1] < 40 and px[x, y][2] < 40]
    assert reds, "the photo should still be drawn when there is room"
    assert max(reds) < footer


def test_a_science_story_that_is_not_about_space_gets_no_moon():
    plankton = _story("Marine biologists discover new plankton off Oregon coast")
    _img, rung = plate_mod.for_story(plankton, lambda _src: None)
    assert rung == "none"
    planet = _story("Astronomers discover a backward planet orbiting its star")
    _img, rung = plate_mod.for_story(planet, lambda _src: None)
    assert rung == "scene"


def test_phys_org_thumbnails_are_upgraded_to_the_original():
    url = "https://scx1.b-cdn.net/csz/news/tmb/2026/a-person.jpg"
    assert carousel_render._upgrade_candidates(url)[0] == \
        "https://scx1.b-cdn.net/csz/news/800a/2026/a-person.jpg"


def test_a_paragraph_is_clamped_to_a_whole_sentence():
    text = ("Mitochondria power almost every cell in your body. They are the cell's "
            "power plants. Think of them as small engines that never stop running.")
    out = clamp_sentences(text, 100)
    assert out.endswith("power plants.")
    assert clamp_sentences("short.", 100) == "short."
    assert clamp_sentences("no full stop anywhere in this one at all", 20).endswith("…")


def _reel(caption, detail=""):
    beats = [ReelBeat(role="hook", caption=caption, detail=detail, seconds=3.7),
             ReelBeat(role="point", caption="Then this happened.", pose="point",
                      seconds=4.0),
             ReelBeat(role="outro", caption="Read it on headlinne.com", pose="cta",
                      seconds=3.0)]
    return Reel(slot="reel_1", kind="news", category="Science", title=caption,
                hook=caption, beats=beats, caption="", hashtags=[],
                scheduled_time="2026-10-05T09:30:00+05:30", dateline="MON 5 OCT")


def test_the_reel_cover_is_a_title_card_and_passes_the_gate():
    reel = _reel("Hidden X-ray flash revealed in a collision of two dead stars")
    frames = ReelFrames(reel, _story(), loader=lambda _s: None)
    frames.render(cover_offset_ms(reel) / 1000)
    labels = {t[0] for t in frames.trace}
    assert "pip" in labels, "the opening beat has Pip on stage"
    report = visual.check_reel_frames(frames, sample_every=15, story=_story())
    assert report.ok, report.errors[:3]


def test_a_title_length_hook_with_a_detail_does_not_overlap_it():
    # A hook falls back to the article title, which can be 90 characters. At
    # the old fixed 58px it ran into the detail line and failed the gate.
    reel = _reel("A strange circle on satellite maps turned out to be a "
                 "390-million-year-old impact", detail="Geologists confirmed it with drill cores.")
    frames = ReelFrames(reel, _story(), loader=lambda _s: None)
    report = visual.check_reel_frames(frames, sample_every=15, story=_story())
    assert report.ok, report.errors[:3]


def test_a_news_post_with_a_story_earns_a_story_card_not_the_promo():
    post = TwitterPost(category="Science", post="x", hashtags=[],
                       scheduled_time="", kind="news", lead="Today's science news")
    assert choose_layout(post, None) == "promo"
    assert choose_layout(post, _story()) != "promo"


def test_a_post_s_story_survives_the_round_trip():
    post = TwitterPost(category="Science", post="x", hashtags=[], scheduled_time="",
                       story=_story(outlets=3))
    back = TwitterPost.from_dict(post.to_dict())
    assert back.story is not None and back.story.agreement.reported == 3


def test_a_single_source_carousel_publishes_with_a_warning_not_a_drop(tmp_path):
    # The gate's hard "two outlets" check outlived the decision that made
    # corroboration a preference, and dropped the carousel on 25 of 35 days.
    story = _story(outlets=1)
    slides = [Slide(role=r, headline="h", kicker="k", index=i)
              for i, r in enumerate(carousel_render.SLIDE_ORDER, 1)]
    car = _carousel(story, slides)
    paths = carousel_render.render_carousel(car, tmp_path, image_loader=lambda _s: None)
    report = visual.check_carousel(car, [Image.open(p) for p in paths])
    assert report.ok, report.errors
    assert any("two independent outlets" in w for w in report.warnings)
