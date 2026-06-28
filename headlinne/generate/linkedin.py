"""Generate the day's LinkedIn post.

Most days: a product/credibility post on a rotating topic.
Every Friday: a "This Week in Finance & Tech" roundup of the week's biggest
developments, assembled from the stories we have gathered over recent days.
"""

from __future__ import annotations

from datetime import date

from ..config import WEBSITE
from ..gemini.client import GeminiClient
from ..gemini.prompts import (STYLE_GUIDE, linkedin_product_prompt,
                              linkedin_roundup_prompt)
from ..logging_setup import get_logger
from ..models import LinkedInPost, NewsDigest, Story
from ..quality.sanitize import sanitize
from ..scheduling import slot_iso
from .common import LINKEDIN_TOPICS

log = get_logger("generate.linkedin")


def _assemble(data: dict, day: date, kind: str) -> LinkedInPost:
    """Clean the model's fields and guarantee a sensible CTA toward the site."""
    title = sanitize(data.get("title", ""))
    body = sanitize(data.get("body", ""))
    cta = sanitize(data.get("cta", ""))

    # Make sure the closing line actually points to the website. If the model
    # forgot, add a quiet, non-salesy invite.
    if WEBSITE.lower() not in (cta + " " + body).lower():
        cta = f"If you like keeping up without the noise, take a look at {WEBSITE}."
    if not cta:
        cta = f"More of the day's news, made personal, over at {WEBSITE}."

    return LinkedInPost(
        title=title,
        body=body,
        cta=cta,
        scheduled_time=slot_iso(day, "linkedin"),
        kind=kind,
    )


def generate_product(client: GeminiClient, day: date) -> LinkedInPost:
    """A credibility-building product post on a rotating topic."""
    topic = LINKEDIN_TOPICS[day.toordinal() % len(LINKEDIN_TOPICS)]
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=linkedin_product_prompt(topic),
    )
    post = _assemble(data, day, kind="product")
    log.info("LinkedIn product post (%s) %d chars", topic[:32],
             len(post.title) + len(post.body) + len(post.cta))
    return post


def generate_roundup(client: GeminiClient, day: date,
                     week_stories: list[Story]) -> LinkedInPost:
    """The Friday "This Week in Finance & Tech" roundup."""
    stories = week_stories[:8]
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=linkedin_roundup_prompt(stories),
    )
    post = _assemble(data, day, kind="weekly_roundup")
    log.info("LinkedIn weekly roundup from %d stories, %d chars",
             len(stories), len(post.title) + len(post.body) + len(post.cta))
    return post


def _fallback_week_stories(digest: NewsDigest) -> list[Story]:
    """If we have no multi-day history yet, use today's tech + finance picks."""
    picks: list[Story] = []
    picks.extend(digest.top("Technology", 4))
    picks.extend(digest.top("Finance", 4))
    return picks


def generate(client: GeminiClient, digest: NewsDigest, day: date,
             is_friday: bool, week_stories: list[Story] | None = None) -> LinkedInPost:
    """Dispatch to the right LinkedIn post type for the day."""
    if is_friday:
        stories = list(week_stories or [])
        if not stories:
            stories = _fallback_week_stories(digest)
        if stories:
            return generate_roundup(client, day, stories)
        log.info("No stories for roundup, falling back to a product post.")
    return generate_product(client, day)
