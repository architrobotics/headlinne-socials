"""Generate the day's carousel: one story, argued across five slides.

The old generator produced a listicle - a cover, three or five unrelated stories
under identical layouts, then a sign-off. A list has no reason to be swiped past
its second entry. An argument does, because each slide answers the question the
previous one raised, and that is what carries a reader to the last slide where
the call to action lives.

Selection is the other half. The carousel gets one story a day and it has to be
worth five slides, so the choice is made against the ranker's interest score
*and* the sourcing: an uncorroborated story never gets the format, because four
of its five slides would be making claims the source strip cannot back.

The renderer draws everything. The model only produces the text that fills the
template, and every figure it returns is checked against the story before it is
allowed onto a slide.
"""

from __future__ import annotations

import re
from datetime import date

from ..config import BRAND, CATEGORY_LABELS, INSTAGRAM_MAX_HASHTAGS
from ..gemini.client import GeminiClient
from ..gemini.prompts import STYLE_GUIDE, carousel_prompt, stories_block
from ..logging_setup import get_logger
from ..models import InstagramCarousel, NewsDigest, Slide, Story
from ..news.images import best_story_image
from ..quality.sanitize import sanitize
from ..render import receipt as receipt_mod
from ..scheduling import slot_iso
from . import hooks
from .common import clamp_words

log = get_logger("generate.instagram")

_BASE_TAGS = {
    "Technology": ["Tech", "TechNews", "AI", "Innovation"],
    "Finance": ["Finance", "Markets", "Business", "Economy"],
    "Geopolitics": ["WorldNews", "Geopolitics", "GlobalNews", "Politics"],
    "Science": ["Science", "Space", "Discovery", "Research"],
}

# A story needs this many independent outlets before it earns the carousel.
# Higher than the two-source publishing bar on purpose: five slides is the
# biggest claim the account makes in a day, and it should rest on more than the
# minimum.
MIN_SOURCES_FOR_CAROUSEL = 3


def agreement_line(story: Story) -> str:
    """How the sourcing is described to the model, in words it can reuse."""
    record = receipt_mod.agreement_of(story)
    names = ", ".join(receipt_mod.outlets(story)[:6])
    if record.state == "disputed":
        conflicts = "; ".join(f"{c.outlet} says {c.value}"
                              for c in record.conflicts[:3])
        return (f"{record.agree} of {record.eligible} outlets agree on "
                f"{record.claim or 'the central claim'}. They disagree: "
                f"{conflicts}. Outlets: {names}.")
    return f"{record.label()}. Outlets: {names}."


def pick_story(digest: NewsDigest, *, exclude_urls: set[str] | None = None
               ) -> Story | None:
    """The one story worth five slides today.

    Ranked by score, but gated on corroboration first: the carousel's fourth
    slide is the source strip in full, and a story with one outlet behind it
    turns that slide into an admission rather than a proof.
    """
    exclude = exclude_urls or set()
    candidates = [s for stories in digest.by_category.values() for s in stories
                  if s.url not in exclude]
    candidates.sort(key=lambda s: s.score, reverse=True)

    for story in candidates:
        if len(receipt_mod.outlets(story)) >= MIN_SOURCES_FOR_CAROUSEL:
            return story
    # Nothing well-sourced enough. Fall back to the best verified story rather
    # than the best story outright, so the format's premise still holds.
    for story in candidates:
        if getattr(story, "verified", False):
            log.info("carousel: no story reached %d outlets, using the best "
                     "verified one", MIN_SOURCES_FOR_CAROUSEL)
            return story
    log.warning("carousel: no corroborated story today, skipping the format")
    return None


def _hashtags(category: str, model_tags: list[str]) -> list[str]:
    base = _BASE_TAGS.get(category, [])
    seen: set[str] = set()
    out: list[str] = []
    for tag in [*base, *model_tags, BRAND]:
        clean = str(tag).lstrip("#").replace(" ", "")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:INSTAGRAM_MAX_HASHTAGS]


_DIGITS = re.compile(r"\d[\d,.]*")


def verified_figure(figure: str, story: Story) -> str:
    """A figure only survives if it appears in the story text.

    The scale slide sets one number at 280px. A number that large is a factual
    claim in the most screenshot-able form this account produces, so it is
    checked character by character against the source rather than trusted.
    """
    if not figure:
        return ""
    digits = _DIGITS.findall(f"{story.title} {story.summary}")
    normalised = {d.replace(",", "").rstrip(".") for d in digits}
    candidate = figure.replace(",", "").strip().rstrip(".")
    if candidate in normalised:
        return figure
    # Spelled-out small numbers are common and safe ("four tonnes").
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
             "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
    if candidate.lower() in words and words[candidate.lower()] in normalised:
        return figure
    log.warning("carousel: dropped unverified figure %r, not found in the story",
                figure)
    return ""


def _slides(data: dict, story: Story) -> list[Slide]:
    """Assemble the five slides, with a safe fallback for every field.

    Sensitive stories lose the mascot and the speech bubbles entirely - pose and
    say stay empty, which is what the renderer reads as "draw nothing".
    """
    sensitive = bool(getattr(story, "sensitive", False))
    state = receipt_mod.state(story)

    def pose(name: str) -> str:
        return "" if sensitive else name

    def say(key: str, limit: int = 34) -> str:
        return "" if sensitive else clamp_words(sanitize(data.get(key, "")), limit)

    figure = verified_figure(str(data.get("figure", "")).strip(), story)
    unit = clamp_words(sanitize(data.get("unit", "")), 18) if figure else ""

    cover_headline = (clamp_words(sanitize(data.get("cover_headline", "")), 70)
                      or sanitize(story.title))
    twist_headline = clamp_words(sanitize(data.get("twist_headline", "")), 90)

    return [
        Slide(role="cover", headline=cover_headline,
              subtitle=clamp_words(sanitize(data.get("cover_sub", "")), 90),
              kicker=receipt_mod.EYEBROW[state] if state != "unanimous"
              else (story.category or "").upper(),
              pose=pose("alert" if state != "disputed" else "puzzled"),
              say=say("cover_say"),
              image_url=story.image_url, index=1),
        Slide(role="scale", headline="", kicker="HOW BIG" if figure else "THE SCALE",
              figure=figure, unit=unit,
              explanation=clamp_words(sanitize(data.get("scale_text", "")), 190),
              image_url=story.image_url, index=2),
        Slide(role="twist",
              headline=twist_headline or "There is more to it than the headline.",
              kicker="WHAT YOU DID NOT KNOW",
              explanation=clamp_words(sanitize(data.get("twist_text", "")), 190),
              pose=pose("puzzled"), say=say("twist_say"), index=3),
        Slide(role="sources", headline="", kicker="SOURCES",
              explanation=clamp_words(sanitize(data.get("sources_text", "")), 190),
              pose=pose("verified" if state == "unanimous" else "puzzled"),
              say=say("sources_say") or ("" if sensitive else
                                         receipt_mod.short_label(story)),
              index=4),
        Slide(role="cta", headline="",
              subtitle=clamp_words(sanitize(data.get("cta_sub", "")), 120)
              or "Every source on this story, side by side.",
              kicker="READ THE FULL STORY",
              pose=pose("carry"), say=say("cta_say") or
              ("" if sensitive else "Come and read it."), index=5),
    ]


def generate(client: GeminiClient, digest: NewsDigest, day: date, *,
             exclude_urls: set[str] | None = None
             ) -> list[InstagramCarousel]:
    """The day's single carousel, or an empty list when nothing earns it."""
    story = pick_story(digest, exclude_urls=exclude_urls)
    if story is None:
        return []

    label = CATEGORY_LABELS.get(story.category, story.category)
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=carousel_prompt(stories_block([story]), label,
                               agreement_line(story)),
    )

    slides = _slides(data, story)
    caption = sanitize(data.get("caption", "")) or (
        f"One {label} story, explained. What did you make of it?")
    opener, _, remainder = caption.partition(". ")
    if remainder:
        opener += "."
    else:
        opener, remainder = caption, ""
    caption_text, first_comment = hooks.build_caption(
        opener=opener, body=remainder.strip(), question="",
        hashtags=_hashtags(story.category, data.get("hashtags", [])))

    # Resolve the article photograph once. The plate ladder in render/plate.py
    # decides whether it is usable and what to draw instead when it is not.
    story.image_url = best_story_image(story) or story.image_url

    carousel = InstagramCarousel(
        slot="instagram_1", category=story.category, num_slides=len(slides),
        title=slides[0].headline, slides=slides, caption=caption_text,
        hashtags=_hashtags(story.category, data.get("hashtags", [])),
        first_comment=first_comment, scheduled_time=slot_iso(day, "instagram_1"),
        story=story, story_url=story.url)
    log.info("carousel [%s] %s (%s)", label, story.title[:56],
             receipt_mod.label(story))
    return [carousel]
