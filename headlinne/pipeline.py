"""The orchestrator: generate everything for a day, and publish a single slot.

generate():
  fetch news -> rank -> drop recently-used stories -> pick categories ->
  generate X / LinkedIn / Instagram text -> render carousels -> quality check ->
  save everything under content/<date>/ -> update the rolling history. If
  BUFFER_SCHEDULING_MODE == "scheduled" it also schedules the X and LinkedIn posts
  into Buffer with their slot times.

publish(target):
  read the committed content for today and publish one slot. Instagram is posted
  at call time through Buffer (its rendered images are committed by the morning
  generate run, so they are publicly reachable by the time a slot trigger fires).
  X and LinkedIn are only posted here when BUFFER_SCHEDULING_MODE == "trigger"
  (otherwise they were already scheduled into Buffer during generation).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from . import storage
from .config import BUFFER_SCHEDULING_MODE, CATEGORIES, SECRETS
from .gemini.client import GeminiClient
from .generate import instagram as gen_instagram
from .generate import linkedin as gen_linkedin
from .generate import twitter as gen_twitter
from .logging_setup import get_logger
from .models import DayPlan, NewsDigest
from .news import fetch_all, rank, strongest_categories
from .quality import (History, check_instagram, check_linkedin, check_twitter)
from .quality.dedup import History as _History  # noqa: F401  (re-export friendliness)
from .render import render_carousel
from .scheduling import is_friday, is_promo_day, today_ist, upcoming_slot_passed

log = get_logger("pipeline")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_buffer_utc(iso_ist: str) -> str:
    """Convert an IST ISO timestamp to Buffer's UTC '...000Z' format."""
    dt = datetime.fromisoformat(iso_ist)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _drop_seen(digest: NewsDigest, history: History) -> None:
    """Remove stories already used in recent days from each category in place."""
    for cat in CATEGORIES:
        kept = [s for s in digest.by_category.get(cat, [])
                if not history.story_seen(s.url, s.title)]
        digest.by_category[cat] = kept


def _twitter_categories(digest: NewsDigest) -> list[str]:
    """Two different categories for the day's two news posts, breaking first."""
    order = strongest_categories(digest, n=len(CATEGORIES))
    if digest.breaking and digest.breaking.category in order:
        order.remove(digest.breaking.category)
        order.insert(0, digest.breaking.category)
    # keep only categories that actually have stories
    order = [c for c in order if digest.by_category.get(c)]
    return order[:2]


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def generate(day: date | None = None, *, render: bool = True,
             schedule_buffer: bool | None = None) -> DayPlan:
    """Produce and persist all of the day's content. Returns the DayPlan."""
    day = day or today_ist()
    log.info("=== GENERATE for %s ===", day.isoformat())

    history = History.load()
    history.prune(day)

    # 1. Gather and rank the news.
    stories = fetch_all()
    digest = rank(stories)
    _drop_seen(digest, history)
    storage.save_digest(day, digest)

    promo = is_promo_day(day)
    friday = is_friday(day)
    log.info("promo_day=%s friday=%s dominant=%s", promo, friday, digest.dominant_category)

    client = GeminiClient()

    # 2. X (Twitter)
    if promo:
        twitter_posts = gen_twitter.generate_promo(client, day)
    else:
        cats = _twitter_categories(digest)
        twitter_posts = gen_twitter.generate_news(client, digest, cats, day)

    # 3. LinkedIn
    week_stories = storage.recent_week_stories(day) if friday else []
    linkedin_post = gen_linkedin.generate(client, digest, day, friday, week_stories)

    # 4. Instagram (two strongest categories)
    ig_cats = strongest_categories(digest, n=2)
    carousels = gen_instagram.generate(client, digest, ig_cats, day)

    # 5. Render carousel images.
    if render:
        for carousel in carousels:
            out_dir = storage.carousel_dir(day, carousel.slot)
            render_carousel(carousel, out_dir)

    # 6. Quality gate (drop broken X posts, log everything).
    twitter_posts = _quality_filter_twitter(twitter_posts)
    _quality_check_linkedin(linkedin_post)
    _quality_check_instagram(carousels)

    plan = DayPlan(
        day=day.isoformat(),
        is_promo_day=promo,
        is_friday=friday,
        twitter=twitter_posts,
        linkedin=linkedin_post,
        instagram=carousels,
    )
    storage.save_day_plan(day, plan)

    # 7. Record history so tomorrow does not repeat today.
    used_urls, used_titles, used_texts = [], [], []
    for cat in ig_cats:
        for s in digest.by_category.get(cat, [])[:5]:
            used_urls.append(s.url)
            used_titles.append(s.title)
    for p in twitter_posts:
        used_texts.append(p.post)
    used_texts.append(linkedin_post.body)
    for c in carousels:
        used_texts.append(c.caption)
    history.record(day, story_urls=used_urls, story_titles=used_titles,
                   post_texts=used_texts)
    history.save()

    # 8. Optionally schedule X + LinkedIn into Buffer now.
    if schedule_buffer is None:
        schedule_buffer = BUFFER_SCHEDULING_MODE == "scheduled"
    if schedule_buffer:
        _schedule_buffer(day, plan)

    log.info("=== GENERATE done: %d X, 1 LinkedIn, %d carousels ===",
             len(twitter_posts), len(carousels))
    return plan


def _quality_filter_twitter(posts):
    kept = []
    for p in posts:
        report = check_twitter(p)
        for w in report.warnings:
            log.warning("quality: %s", w)
        if report.ok:
            kept.append(p)
        else:
            for e in report.errors:
                log.error("dropping X post: %s", e)
    return kept


def _quality_check_linkedin(post):
    report = check_linkedin(post)
    for w in report.warnings:
        log.warning("quality: %s", w)
    for e in report.errors:
        log.error("LinkedIn quality issue: %s", e)


def _quality_check_instagram(carousels):
    for c in carousels:
        report = check_instagram(c)
        for w in report.warnings:
            log.warning("quality: %s", w)
        for e in report.errors:
            log.error("Instagram quality issue (%s): %s", c.slot, e)


def _schedule_buffer(day: date, plan: DayPlan) -> None:
    """Schedule X and LinkedIn posts into Buffer at their slot times."""
    from .publish import BufferClient, BufferError

    try:
        buffer = BufferClient()
    except Exception as exc:  # pragma: no cover
        log.warning("Buffer not configured, skipping scheduling: %s", exc)
        return

    # X posts
    for i, post in enumerate(plan.twitter):
        slot = "x_1" if i == 0 else "x_2"
        due = None if upcoming_slot_passed(day, slot) else _to_buffer_utc(post.scheduled_time)
        try:
            res = buffer.post_twitter(post.post, due_at_utc=due)
            storage.mark_published(day, f"x_{i+1}", {"buffer": res, "scheduled": bool(due)})
        except BufferError as exc:
            log.error("Failed to schedule X post %d: %s", i + 1, exc)

    # LinkedIn
    li = plan.linkedin
    li_text = _linkedin_text(li)
    due = None if upcoming_slot_passed(day, "linkedin") else _to_buffer_utc(li.scheduled_time)
    try:
        res = buffer.post_linkedin(li_text, due_at_utc=due)
        storage.mark_published(day, "linkedin", {"buffer": res, "scheduled": bool(due)})
    except BufferError as exc:
        log.error("Failed to schedule LinkedIn post: %s", exc)


def _linkedin_text(post) -> str:
    """Assemble the final LinkedIn text from its parts."""
    parts = [post.title.strip(), post.body.strip(), post.cta.strip()]
    return "\n\n".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
def publish(target: str, day: date | None = None) -> None:
    """Publish a single slot for today. target: x-1 | x-2 | linkedin |
    instagram-1 | instagram-2."""
    day = day or today_ist()
    target = target.replace("-", "_").lower()
    log.info("=== PUBLISH %s for %s ===", target, day.isoformat())

    if storage.is_published(day, target):
        log.info("%s already published today, skipping (idempotent).", target)
        return

    if target in ("x_1", "x_2"):
        _publish_twitter(day, target)
    elif target == "linkedin":
        _publish_linkedin(day)
    elif target in ("instagram_1", "instagram_2"):
        _publish_instagram(day, target)
    else:
        raise ValueError(f"unknown target: {target}")


def _publish_twitter(day: date, target: str) -> None:
    if BUFFER_SCHEDULING_MODE == "scheduled":
        log.info("scheduled mode: X was scheduled at generation, nothing to do.")
        return
    from .publish import BufferClient

    posts = storage.load_twitter(day)
    idx = 0 if target == "x_1" else 1
    if idx >= len(posts):
        log.warning("No X post for slot %s today.", target)
        return
    post = posts[idx]
    res = BufferClient().post_twitter(post.post)  # mode now
    storage.mark_published(day, target, {"buffer": res})


def _publish_linkedin(day: date) -> None:
    if BUFFER_SCHEDULING_MODE == "scheduled":
        log.info("scheduled mode: LinkedIn was scheduled at generation, nothing to do.")
        return
    from .publish import BufferClient

    post = storage.load_linkedin(day)
    if not post:
        log.warning("No LinkedIn post today.")
        return
    res = BufferClient().post_linkedin(_linkedin_text(post))
    storage.mark_published(day, "linkedin", {"buffer": res})


def _publish_instagram(day: date, target: str) -> None:
    from .publish import BufferClient, build_caption, get_image_host

    carousels = storage.load_instagram(day)
    carousel = next((c for c in carousels if c.slot == target), None)
    if not carousel:
        log.warning("No Instagram carousel for slot %s today.", target)
        return

    # Build the public image URLs from the canonical slide layout so they are
    # always correct for the current checkout, regardless of where the images
    # were rendered. Slides are named slide_1.png, slide_2.png, ... in order.
    host = get_image_host()
    slot_dir = storage.carousel_dir(day, carousel.slot)
    image_urls = [host.url_for(slot_dir / f"slide_{i}.png")
                  for i in range(1, len(carousel.slides) + 1)]

    caption = build_caption(carousel.caption, carousel.hashtags)
    res = BufferClient().post_instagram(image_urls, caption)  # mode now
    storage.mark_published(day, target, {"buffer": res, "images": image_urls})
