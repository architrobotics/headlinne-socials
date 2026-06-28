"""Fetch raw stories from the configured RSS feeds.

Uses feedparser. Individual feed failures are logged and skipped so one dead
source never takes down the run.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ..config import FEEDS, MAX_STORY_AGE_HOURS, Feed
from ..logging_setup import get_logger
from ..models import Story
from .images import image_from_entry

log = get_logger("news.feeds")

# Be a polite, identifiable client.
_UA = "HeadlinneBot/1.0 (+https://headlinne.com; news aggregation)"
feedparser.USER_AGENT = _UA


def _entry_datetime(entry) -> datetime | None:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if not val:
            continue
        try:
            dt = parsedate_to_datetime(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    # Fall back to the parsed struct_time feedparser provides.
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
    return None


def _clean(text: str | None) -> str:
    if not text:
        return ""
    # feedparser already strips most HTML for titles; summaries can carry tags.
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(feed: Feed, *, fetch_images: bool = True) -> list[Story]:
    """Parse one feed into Story objects, dropping anything too old."""
    stories: list[Story] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_STORY_AGE_HOURS)
    try:
        parsed = feedparser.parse(feed.url)
    except Exception as exc:  # pragma: no cover - network
        log.warning("feed failed %s: %s", feed.name, exc)
        return stories

    if parsed.bozo and not parsed.entries:
        log.warning("feed unreadable %s (%s)", feed.name, getattr(parsed, "bozo_exception", ""))
        return stories

    for entry in parsed.entries:
        dt = _entry_datetime(entry)
        if dt is None or dt < cutoff:
            continue
        title = _clean(entry.get("title"))
        if not title:
            continue
        story = Story(
            title=title,
            summary=_clean(entry.get("summary") or entry.get("description"))[:600],
            url=entry.get("link", ""),
            category=feed.category,
            source=feed.name,
            tier=feed.tier,
            published_iso=dt.astimezone(timezone.utc).isoformat(),
            image_url=image_from_entry(entry) if fetch_images else None,
        )
        stories.append(story)

    log.info("  %-18s %3d recent stories", feed.name, len(stories))
    return stories


def fetch_all(*, feeds: tuple[Feed, ...] = FEEDS, fetch_images: bool = True) -> list[Story]:
    """Fetch every configured feed and return a flat list of fresh stories."""
    log.info("Fetching %d feeds...", len(feeds))
    out: list[Story] = []
    for feed in feeds:
        out.extend(fetch_feed(feed, fetch_images=fetch_images))
    log.info("Collected %d fresh stories total", len(out))
    return out
