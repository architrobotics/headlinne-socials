"""Build the day's story card: one article, walked through start to finish.

The four stops are fixed in code and never change day to day. That is the whole
point of the format. A reader who has seen one of these knows exactly where the
"why does this affect me" line will be before they have finished reading the
headline, and a format someone can read at a glance is a format they save.

The model fills the stops. It does not get to choose them, reorder them, or add
a fifth, because that is how a recognisable daily format decays into a generic
one over a few weeks.
"""

from __future__ import annotations

from datetime import date

from ..config import BRAND, CATEGORY_LABELS
from ..gemini.client import GeminiClient
from ..gemini.prompts import STYLE_GUIDE, stories_block, story_card_prompt
from ..logging_setup import get_logger
from ..render import receipt
from ..models import NewsDigest, Story, StoryCard, StoryStep
from ..news.images import best_story_image
from ..quality.sanitize import sanitize
from ..scheduling import slot_iso
from . import hooks
from .common import clamp_words
from .instagram import source_line

log = get_logger("generate.story_card")

# The fixed rail. Order matters: it is the shape of an explanation, from the
# event, back to its cause, forward to its effect, then out to what is still
# undecided.

# Every card carries four steps, a headline and a standfirst inside one 1080x1350
# frame. These limits are what that space actually holds at a size someone reads
# on a phone, worked back from the layout in render/story_card.py. Longer text
# does not overflow (the renderer shrinks the whole rail to fit), it just arrives
# smaller than it should be, so the cut happens here instead.
HEADLINE_CHARS = 64
STANDFIRST_CHARS = 90

_BASE_TAGS = {
    "Technology": ["TechNews", "Tech", "AI"],
    "Finance": ["Finance", "Markets", "Economy"],
    "Geopolitics": ["WorldNews", "Geopolitics", "GlobalNews"],
}


def pick_story(digest: NewsDigest, *, exclude_urls: set[str] | None = None,
               prefer_other_than: str | None = None) -> Story | None:
    """Choose the article to walk through.

    Prefers a category other than the one the news reel already took, so the day
    does not spend two of its formats on the same story. Falls back to the
    strongest remaining story when there is nothing else to pick from.
    """
    exclude = exclude_urls or set()
    pool = [s for stories in digest.by_category.values() for s in stories
            if s.url not in exclude]
    if not pool:
        return None
    if prefer_other_than:
        elsewhere = [s for s in pool if s.category != prefer_other_than]
        if elsewhere:
            pool = elsewhere
    return max(pool, key=lambda s: (s.score, s.source_count))


def _hashtags(category: str, model_tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in [*_BASE_TAGS.get(category, []), *model_tags, "NewsExplained", BRAND]:
        clean = str(tag).lstrip("#").replace(" ", "")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:16]


def generate(client: GeminiClient, digest: NewsDigest, day: date,
             *, exclude_urls: set[str] | None = None,
             prefer_other_than: str | None = None) -> StoryCard | None:
    """Produce the day's story card, or None when there is nothing to cover."""
    story = pick_story(digest, exclude_urls=exclude_urls,
                       prefer_other_than=prefer_other_than)
    if story is None:
        log.warning("No story available for the story card.")
        return None

    label = CATEGORY_LABELS.get(story.category, story.category)
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=story_card_prompt(stories_block([story]), HEADLINE_CHARS, label),
    )

    headline = clamp_words(sanitize(data.get("headline", "")), HEADLINE_CHARS) \
        or clamp_words(sanitize(story.title), HEADLINE_CHARS)
    standfirst = clamp_words(sanitize(data.get("standfirst", "")), STANDFIRST_CHARS)

    # The receipt is the card's argument, so it comes from the corroboration the
    # ranker already did rather than from the model. Every outlet returned by
    # corroborate() reported the same event, so all of them agree; a card that
    # says otherwise needs a conflict detector we do not have yet.
    outlets = receipt.outlets(story)
    kind = "breaking" if getattr(story, "is_breaking", False) else "brief"

    # A card with nothing behind it is worse than no card: the receipt would be
    # a single outlined tick, which is an admission, not a post.
    if not headline:
        log.error("story card had no usable headline, skipping it today.")
        return None

    hashtags = _hashtags(story.category, data.get("hashtags", []) or [])
    caption, first_comment = hooks.build_caption(
        opener=sanitize(data.get("caption_opener", "")) or headline,
        body=sanitize(data.get("caption_body", "")),
        question=sanitize(data.get("question", "")),
        hashtags=hashtags,
        cta="Save this one. Follow for the daily card.",
    )

    card = StoryCard(
        slot="story_card",
        category=story.category,
        headline=headline,
        standfirst=standfirst,
        outlets=outlets,
        agree=len(outlets),
        kind=kind,
        steps=[],
        caption=caption,
        hashtags=hashtags,
        first_comment=first_comment,
        sources=source_line(story),
        story_url=story.url,
        image_url=best_story_image(story),
        scheduled_time=slot_iso(day, "story_card"),
    )
    log.info("story card [%s] %r (%d steps)", story.category, headline, len(filled))
    return card
