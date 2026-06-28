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
    log.info("X news [%s] %d chars", label, len(post_text))
    return TwitterPost(
        category=label,
        post=post_text,
        hashtags=[str(h).lstrip("#") for h in hashtags[:2]],
        scheduled_time=slot_iso(day, slot),
        kind="news",
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
    log.info("X promo (%s) %d chars", feature[:30], len(post_text))
    return [
        TwitterPost(
            category="Promo",
            post=post_text,
            hashtags=[str(h).lstrip("#") for h in hashtags[:2]],
            scheduled_time=slot_iso(day, "x_1"),
            kind="promo",
        )
    ]
