"""Read and write the per-day content artifacts under content/<date>/.

Layout for a day:
  content/2026-06-28/
    news_digest.json          the ranked picture of the day
    twitter.json              list of TwitterPost
    linkedin.json             one LinkedInPost
    instagram.json            list of InstagramCarousel (with slide image paths)
    instagram/instagram_1/slide_1.png ...   rendered carousel images
    instagram/instagram_2/slide_1.png ...
    published/<target>.json   marker written after a successful publish

Everything is plain JSON so the generate workflow can commit it and the publish
workflow can read it back.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import CONTENT_DIR, content_dir_for
from .logging_setup import get_logger
from .models import (DayPlan, InstagramCarousel, LinkedInPost, NewsDigest, Reel,
                     Story, StoryCard, TwitterPost)

log = get_logger("storage")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def _ensure(day: date) -> Path:
    d = content_dir_for(day)
    d.mkdir(parents=True, exist_ok=True)
    return d


def carousel_dir(day: date, slot: str) -> Path:
    """Folder for a carousel's rendered slides."""
    d = content_dir_for(day) / "instagram" / slot
    d.mkdir(parents=True, exist_ok=True)
    return d


def x_card_path(day: date, slot: str) -> Path:
    """Path for a rendered X (Twitter) card, e.g. content/<day>/x/x_1.png."""
    d = content_dir_for(day) / "x"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slot}.png"


def reel_dir(day: date) -> Path:
    """Folder for the day's rendered reels (MP4 plus cover PNG)."""
    d = content_dir_for(day) / "reels"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reel_video_path(day: date, slot: str) -> Path:
    return reel_dir(day) / f"{slot}.mp4"


def reel_cover_path(day: date, slot: str) -> Path:
    return reel_dir(day) / f"{slot}_cover.png"


def story_card_path(day: date) -> Path:
    """Path for the rendered daily story card."""
    d = content_dir_for(day) / "story_card"
    d.mkdir(parents=True, exist_ok=True)
    return d / "story_card.png"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# News digest
# --------------------------------------------------------------------------- #
def save_digest(day: date, digest: NewsDigest) -> None:
    _write_json(_ensure(day) / "news_digest.json", digest.to_dict())


def load_digest(day: date) -> NewsDigest | None:
    data = _read_json(content_dir_for(day) / "news_digest.json")
    return NewsDigest.from_dict(data) if data else None


# --------------------------------------------------------------------------- #
# Generated content
# --------------------------------------------------------------------------- #
def save_twitter(day: date, posts: list[TwitterPost]) -> None:
    _write_json(_ensure(day) / "twitter.json", [p.to_dict() for p in posts])


def load_twitter(day: date) -> list[TwitterPost]:
    data = _read_json(content_dir_for(day) / "twitter.json") or []
    return [TwitterPost(**p) for p in data]


def save_linkedin(day: date, post: LinkedInPost) -> None:
    _write_json(_ensure(day) / "linkedin.json", post.to_dict())


def load_linkedin(day: date) -> LinkedInPost | None:
    data = _read_json(content_dir_for(day) / "linkedin.json")
    return LinkedInPost(**data) if data else None


def save_instagram(day: date, carousels: list[InstagramCarousel]) -> None:
    _write_json(_ensure(day) / "instagram.json", [c.to_dict() for c in carousels])


def load_instagram(day: date) -> list[InstagramCarousel]:
    data = _read_json(content_dir_for(day) / "instagram.json") or []
    return [InstagramCarousel.from_dict(c) for c in data]


def save_reels(day: date, reels: list[Reel]) -> None:
    _write_json(_ensure(day) / "reels.json", [r.to_dict() for r in reels])


def load_reels(day: date) -> list[Reel]:
    data = _read_json(content_dir_for(day) / "reels.json") or []
    return [Reel.from_dict(r) for r in data]


def save_story_card(day: date, card: StoryCard | None) -> None:
    if card is None:
        return
    _write_json(_ensure(day) / "story_card.json", card.to_dict())


def load_story_card(day: date) -> StoryCard | None:
    data = _read_json(content_dir_for(day) / "story_card.json")
    return StoryCard.from_dict(data) if data else None


def save_day_plan(day: date, plan: DayPlan) -> None:
    """Convenience: write a single combined plan.json plus the per-platform files."""
    _write_json(_ensure(day) / "plan.json", plan.to_dict())
    save_twitter(day, plan.twitter)
    save_linkedin(day, plan.linkedin)
    save_instagram(day, plan.instagram)
    save_reels(day, plan.reels)
    save_story_card(day, plan.story_card)


# --------------------------------------------------------------------------- #
# Publish markers (so a re-trigger does not double-post)
# --------------------------------------------------------------------------- #
def mark_published(day: date, target: str, info: dict) -> None:
    _write_json(_ensure(day) / "published" / f"{target}.json", info)


def is_published(day: date, target: str) -> bool:
    return (content_dir_for(day) / "published" / f"{target}.json").exists()


# --------------------------------------------------------------------------- #
# Media retention
# --------------------------------------------------------------------------- #
# Rendered media is committed so it can be fetched over the public web, which
# means every day's output is permanent unless something removes it. Slides are
# small enough not to matter, but a daily pair of reels is several megabytes, and
# left alone that grows the repository by gigabytes a year.
MEDIA_KEEP_DAYS = 6

# The narration WAVs are the largest thing here and the only one nothing ever
# fetches: the speech is already muxed into the MP4, so they survive purely so a
# reel that sounds wrong can be diagnosed without regenerating it.
MEDIA_SUFFIXES = (".png", ".jpg", ".mp4", ".wav")


def prune_media(day: date, keep_days: int = MEDIA_KEEP_DAYS) -> int:
    """Delete rendered binaries older than `keep_days`, keeping the JSON.

    The JSON is the record of what was posted and costs nothing to keep. The
    binaries only need to outlive the day's last publish slot, and a few days of
    slack covers a retry or a late trigger. Returns the number of files removed.
    """
    removed = 0
    cutoff = day - timedelta(days=keep_days)
    if not CONTENT_DIR.exists():
        return 0
    for folder in CONTENT_DIR.iterdir():
        if not folder.is_dir():
            continue
        try:
            folder_day = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if folder_day >= cutoff:
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:  # pragma: no cover - best effort
                    log.warning("could not prune %s: %s", path, exc)
    if removed:
        log.info("pruned %d rendered file(s) older than %s", removed, cutoff)
    return removed


# --------------------------------------------------------------------------- #
# Week aggregation for the Friday LinkedIn roundup
# --------------------------------------------------------------------------- #
def recent_week_stories(day: date, days_back: int = 7,
                        categories: tuple[str, ...] = ("Technology", "Finance")) -> list[Story]:
    """Gather the strongest stories from the past week's digests for the roundup.

    De-duplicates by URL and similar titles, then sorts by score. Falls back to
    an empty list if no recent digests exist (the caller then uses today's data).
    """
    seen_urls: set[str] = set()
    collected: list[Story] = []
    for i in range(1, days_back + 1):
        d = day - timedelta(days=i)
        digest = load_digest(d)
        if not digest:
            continue
        for cat in categories:
            for s in digest.by_category.get(cat, [])[:4]:
                key = (s.url or s.title).strip().lower()
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                collected.append(s)
    collected.sort(key=lambda s: s.score, reverse=True)
    log.info("Collected %d stories from the past %d days for the roundup",
             len(collected), days_back)
    return collected
