"""Generate the day's X (Twitter) posts.

News days: two posts, ideally in two different categories.
Promo days (every second day): one Headlinne feature post.
"""

from __future__ import annotations

from datetime import date

from ..config import CATEGORY_LABELS
from ..gemini.client import GeminiClient
from ..gemini.prompts import (STYLE_GUIDE, twitter_news_prompt,
                              twitter_promo_prompt)
from ..logging_setup import get_logger
from ..models import NewsDigest, Story, TwitterPost
from ..quality.sanitize import sanitize
from ..scheduling import slot_iso
from .common import (PROMO_FEATURES, assemble_news_post, fit_simple)

log = get_logger("generate.twitter")


def _news_post(client: GeminiClient, category: str, stories: list[Story],
               slot: str, day: date) -> TwitterPost:
    label = CATEGORY_LABELS[category]
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=twitter_news_prompt(label, stories[:3]),
    )
    lead = data.get("lead", f"Top stories in {label} today")
    items = [it.get("text", "") for it in data.get("items", [])]
    hashtags = data.get("hashtags", [label])
    post_text = assemble_news_post(lead, items, hashtags)
    # Clean structured pieces kept for the branded card graphic.
    card_lead = sanitize(lead).strip().rstrip(":")
    card_items = [sanitize(it).strip().rstrip(".") for it in items if it and it.strip()][:3]
    log.info("X news [%s] %d chars", label, len(post_text))
    return TwitterPost(
        category=label,
        post=post_text,
        hashtags=[str(h).lstrip("#") for h in hashtags[:2]],
        scheduled_time=slot_iso(day, slot),
        kind="news",
        lead=card_lead,
        items=card_items,
    )


def generate_news(client: GeminiClient, digest: NewsDigest,
                  categories: list[str], day: date) -> list[TwitterPost]:
    """Two news posts, one per chosen category (slots x_1 and x_2)."""
    posts: list[TwitterPost] = []
    slots = ["x_1", "x_2"]
    for cat, slot in zip(categories, slots):
        stories = digest.by_category.get(cat, [])
        if not stories:
            continue
        posts.append(_news_post(client, cat, stories, slot, day))
    return posts


def generate_promo(client: GeminiClient, day: date) -> list[TwitterPost]:
    """One feature-focused promo post (slot x_1)."""
    feature = PROMO_FEATURES[day.toordinal() % len(PROMO_FEATURES)]
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=twitter_promo_prompt(feature),
    )
    body = sanitize(data.get("post", ""))
    hashtags = data.get("hashtags", ["News"])
    post_text = fit_simple(body, hashtags)
    # The card shows a short statement rather than the full tweet body.
    card_lead = _card_statement(sanitize(data.get("headline", "")) or body)
    log.info("X promo (%s) %d chars", feature[:30], len(post_text))
    return [
        TwitterPost(
            category="Promo",
            post=post_text,
            hashtags=[str(h).lstrip("#") for h in hashtags[:2]],
            scheduled_time=slot_iso(day, "x_1"),
            kind="promo",
            lead=card_lead,
        )
    ]


def _card_statement(text: str, max_chars: int = 90) -> str:
    """First sentence (or a trimmed clause) of the promo body for the card."""
    text = text.strip()
    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    text = text.rstrip(".!? ")
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip(",.:;- ")
    return text
