"""The orchestrator: generate everything for a day, and publish a single slot.

generate():
  fetch news -> rank -> drop recently-used stories -> pick categories ->
  generate X / LinkedIn / Instagram / reel / story card text -> render carousels,
  reels and the story card -> quality check -> save everything under
  content/<date>/ -> update the rolling history -> prune old media. If
  BUFFER_SCHEDULING_MODE == "scheduled" it also schedules the X and LinkedIn posts
  into Buffer with their slot times.

  Every Instagram format is generated independently and failures are contained:
  a reel that cannot be written, or a story card the model returned half empty,
  is dropped from the day rather than allowed to fail the run. The formats that
  did work still go out.

publish(target):
  read the committed content for today and publish one slot. Instagram (feed
  posts, reels and the story card) is posted at call time through Buffer, since
  its rendered media is committed by the morning generate run and is therefore
  publicly reachable by the time a slot trigger fires. X and LinkedIn are only
  posted here when BUFFER_SCHEDULING_MODE == "trigger" (otherwise they were
  already scheduled into Buffer during generation).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from . import storage
from .config import (BUFFER_SCHEDULING_MODE, CAROUSEL_WEEKDAYS, CATEGORIES,
                     IG_SECOND_CAROUSEL, REELS_ENABLED, SECRETS,
                     STORY_CARD_ENABLED)
from .gemini.client import GeminiClient
from .generate import instagram as gen_instagram
from .generate import linkedin as gen_linkedin
from .generate import reel as gen_reel
from .generate import story_card as gen_story_card
from .generate import twitter as gen_twitter
from .logging_setup import get_logger
from .models import DayPlan, NewsDigest
from .news import fetch_all, rank, strongest_categories
from .quality import (History, check_instagram, check_linkedin, check_reel,
                      check_story_card, check_twitter)
from .quality.dedup import History as _History  # noqa: F401  (re-export friendliness)
from .render import (render_carousel, render_reel, render_story_card,
                     render_twitter_card)
from .scheduling import is_friday, is_promo_day, today_ist, upcoming_slot_passed

log = get_logger("pipeline")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_buffer_utc(iso_ist: str) -> str:
    """Convert an IST ISO timestamp to Buffer's UTC '...000Z' format."""
    dt = datetime.fromisoformat(iso_ist)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _x_card_urls(day: date, slot: str) -> list[str] | None:
    """Public URL(s) for a slot's rendered X card, or None when disabled or the
    card was not rendered. Kept best-effort so a missing card never blocks a post."""
    from .config import X_ATTACH_CARD

    if not X_ATTACH_CARD:
        return None
    path = storage.x_card_path(day, slot)
    if not path.exists():
        return None
    try:
        from .publish import get_image_host

        return [get_image_host().url_for(path)]
    except Exception as exc:  # pragma: no cover - host misconfig should not block text post
        log.warning("could not build X card URL for %s: %s", slot, exc)
        return None


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

    # 4. Instagram carousels (the strongest categories). Five slides of argument
    #    is a weekly artefact rather than a daily one, so the carousel runs only
    #    on CAROUSEL_WEEKDAYS; the other days carry the reels and the story card.
    if day.weekday() in CAROUSEL_WEEKDAYS:
        ig_cats = strongest_categories(digest, n=2 if IG_SECOND_CAROUSEL else 1)
        carousels = gen_instagram.generate(client, digest, ig_cats, day)
    else:
        carousels = []
        log.info("no carousel today: weekday %d is not in %s",
                 day.weekday(), list(CAROUSEL_WEEKDAYS))

    # 5. Reels: one news explainer, one educational explainer.
    reels = _generate_reels(client, digest, day)

    # 6. The daily story card. Generated after the reels so it can be given a
    #    different story from the news reel, rather than the day spending two of
    #    its formats on the same event.
    story_card = _generate_story_card(client, digest, day, reels)

    # 7. Render everything.
    if render:
        for carousel in carousels:
            render_carousel(carousel, storage.carousel_dir(day, carousel.slot))
        reels = _render_reels(day, reels)
        if story_card:
            try:
                render_story_card(story_card, storage.story_card_path(day))
            except Exception as exc:  # pragma: no cover - never fail the whole run
                log.error("story card render failed: %s", exc, exc_info=True)
                story_card = None

    # 8. Quality gate (drop broken X posts, log everything).
    twitter_posts = _quality_filter_twitter(twitter_posts)
    _quality_check_linkedin(linkedin_post)
    _quality_check_instagram(carousels)
    reels = _quality_filter_reels(reels, require_media=render)
    story_card = _quality_check_story_card(story_card, require_media=render)

    # 8b. Render the branded X cards for the surviving posts.
    if render:
        for i, post in enumerate(twitter_posts):
            slot = "x_1" if i == 0 else "x_2"
            try:
                render_twitter_card(post, storage.x_card_path(day, slot))
            except Exception as exc:  # pragma: no cover - never fail the run on a card
                log.warning("X card render failed for %s: %s", slot, exc)

    plan = DayPlan(
        day=day.isoformat(),
        is_promo_day=promo,
        is_friday=friday,
        twitter=twitter_posts,
        linkedin=linkedin_post,
        instagram=carousels,
        reels=reels,
        story_card=story_card,
    )
    storage.save_day_plan(day, plan)

    # 9. Record history so tomorrow does not repeat today.
    used_urls, used_titles, used_texts = [], [], []
    for cat in ig_cats:
        for s in digest.by_category.get(cat, [])[:5]:
            used_urls.append(s.url)
            used_titles.append(s.title)
    for r in reels:
        if r.story_url:
            used_urls.append(r.story_url)
        used_texts.append(r.caption)
    if story_card:
        if story_card.story_url:
            used_urls.append(story_card.story_url)
        used_texts.append(story_card.caption)
    for p in twitter_posts:
        used_texts.append(p.post)
    used_texts.append(linkedin_post.body)
    for c in carousels:
        used_texts.append(c.caption)
    history.record(day, story_urls=used_urls, story_titles=used_titles,
                   post_texts=used_texts)
    history.save()

    # 10. Drop old rendered binaries. Reels are megabytes each and are committed
    #     so they can be fetched publicly, so without this the repo grows without
    #     bound. The JSON record of every day is kept.
    storage.prune_media(day)

    # 11. Optionally schedule X + LinkedIn into Buffer now.
    if schedule_buffer is None:
        schedule_buffer = BUFFER_SCHEDULING_MODE == "scheduled"
    if schedule_buffer:
        _schedule_buffer(day, plan)

    log.info("=== GENERATE done: %d X, 1 LinkedIn, %d carousels, %d reels, "
             "story card: %s ===", len(twitter_posts), len(carousels), len(reels),
             "yes" if story_card else "no")
    return plan


# --------------------------------------------------------------------------- #
# Reels and the story card
# --------------------------------------------------------------------------- #
def _generate_reels(client: GeminiClient, digest: NewsDigest, day: date) -> list:
    """The day's news explainer and educational explainer.

    Each is attempted independently: a failure in one is logged and skipped
    rather than taking the other (or the rest of the day) down with it.
    """
    if not REELS_ENABLED:
        log.info("reels disabled (REELS_ENABLED), skipping.")
        return []

    reels = []
    try:
        news_reel = gen_reel.generate_news(client, digest, day)
        if news_reel:
            reels.append(news_reel)
    except Exception as exc:  # noqa: BLE001 - one format must not sink the run
        log.error("news reel generation failed: %s", exc, exc_info=True)

    try:
        reels.append(gen_reel.generate_education(client, day))
    except Exception as exc:  # noqa: BLE001
        log.error("education reel generation failed: %s", exc, exc_info=True)
    return reels


def _generate_story_card(client: GeminiClient, digest: NewsDigest, day: date,
                         reels: list):
    if not STORY_CARD_ENABLED:
        log.info("story card disabled (STORY_CARD_ENABLED), skipping.")
        return None
    news_reel = next((r for r in reels if r.kind == "news"), None)
    try:
        return gen_story_card.generate(
            client, digest, day,
            exclude_urls={news_reel.story_url} if news_reel and news_reel.story_url else set(),
            prefer_other_than=news_reel.category if news_reel else None,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("story card generation failed: %s", exc, exc_info=True)
        return None


def _render_reels(day: date, reels: list) -> list:
    """Render each reel to MP4, keeping only the ones that produced a file.

    Video is the one part of this pipeline with an external dependency (ffmpeg)
    and a real chance of failing on a given machine, so an unrenderable reel is
    dropped from the plan rather than scheduled as a post with no video.
    """
    from .render.motion import ffmpeg_available

    if reels and not ffmpeg_available():
        log.error("ffmpeg is not available, so no reels can be rendered. "
                  "Install ffmpeg or `pip install imageio-ffmpeg`.")
        return []

    rendered = []
    for reel in reels:
        try:
            render_reel(reel, storage.reel_dir(day))
            rendered.append(reel)
        except Exception as exc:  # noqa: BLE001
            log.error("reel render failed for %s: %s", reel.slot, exc, exc_info=True)
    return rendered


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


def _quality_filter_reels(reels, *, require_media: bool = True):
    kept = []
    for r in reels:
        report = check_reel(r, require_media=require_media)
        for w in report.warnings:
            log.warning("quality: %s", w)
        if report.ok:
            kept.append(r)
        else:
            for e in report.errors:
                log.error("dropping reel %s: %s", r.slot, e)
    return kept


def _quality_check_story_card(card, *, require_media: bool = True):
    if card is None:
        return None
    report = check_story_card(card, require_media=require_media)
    for w in report.warnings:
        log.warning("quality: %s", w)
    if report.ok:
        return card
    for e in report.errors:
        log.error("dropping story card: %s", e)
    return None


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
        images = _x_card_urls(day, slot)
        try:
            res = buffer.post_twitter(post.post, due_at_utc=due, image_urls=images)
            storage.mark_published(day, f"x_{i+1}", {"buffer": res, "scheduled": bool(due),
                                                     "images": images})
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
PUBLISH_TARGETS = ("x_1", "x_2", "linkedin", "instagram_1", "instagram_2",
                   "reel_1", "reel_2", "story_card")


def publish(target: str, day: date | None = None) -> None:
    """Publish a single slot for today.

    target: x-1 | x-2 | linkedin | instagram-1 | instagram-2 | reel-1 | reel-2 |
    story-card.
    """
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
    elif target in ("reel_1", "reel_2"):
        _publish_reel(day, target)
    elif target == "story_card":
        _publish_story_card(day)
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
    images = _x_card_urls(day, target)
    res = BufferClient().post_twitter(post.post, image_urls=images)  # mode now
    storage.mark_published(day, target, {"buffer": res, "images": images})


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
    from .publish import (BufferClient, apply_first_comment_policy,
                          get_image_host)

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

    # The caption already carries its own short hashtag block (see
    # generate.hooks), so nothing more is appended here. The long tail goes to
    # the first comment instead.
    caption, first_comment = apply_first_comment_policy(
        carousel.caption, carousel.first_comment)
    res = BufferClient().post_instagram(image_urls, caption,
                                        first_comment=first_comment)
    storage.mark_published(day, target, {"buffer": res, "images": image_urls})


def _publish_reel(day: date, target: str) -> None:
    """Publish one of the day's reels from its committed MP4."""
    from .publish import (BufferClient, apply_first_comment_policy,
                          get_image_host)

    reels = storage.load_reels(day)
    reel = next((r for r in reels if r.slot == target), None)
    if not reel:
        log.warning("No reel for slot %s today.", target)
        return

    video_path = storage.reel_video_path(day, target)
    if not video_path.exists():
        log.error("Reel video %s is missing, nothing to publish.", video_path)
        return

    video_url = get_image_host().url_for(video_path)
    caption, first_comment = apply_first_comment_policy(
        reel.caption, reel.first_comment)
    res = BufferClient().post_instagram_reel(video_url, caption,
                                             first_comment=first_comment)
    storage.mark_published(day, target, {"buffer": res, "video": video_url,
                                         "duration": reel.duration_seconds})


def _publish_story_card(day: date) -> None:
    """Publish the daily story card as a single-image feed post."""
    from .publish import (BufferClient, apply_first_comment_policy,
                          get_image_host)

    card = storage.load_story_card(day)
    if not card:
        log.warning("No story card today.")
        return

    path = storage.story_card_path(day)
    if not path.exists():
        log.error("Story card image %s is missing, nothing to publish.", path)
        return

    image_url = get_image_host().url_for(path)
    caption, first_comment = apply_first_comment_policy(
        card.caption, card.first_comment)
    res = BufferClient().post_instagram([image_url], caption,
                                        first_comment=first_comment)
    storage.mark_published(day, "story_card", {"buffer": res,
                                               "images": [image_url]})
