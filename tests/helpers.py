"""Small helpers shared across test modules."""

from __future__ import annotations

from datetime import datetime, timezone

from headlinne.models import Story


def make_story(
    title: str,
    *,
    category: str = "Technology",
    source: str = "BBC",
    tier: float = 1.2,
    summary: str = "",
    url: str | None = None,
    image_url: str | None = None,
    age_hours: float = 2.0,
    corroborating: list[str] | None = None,
    score: float = 0.0,
) -> Story:
    """Build a Story with sensible defaults for tests.

    `age_hours` is converted into a published_iso timestamp relative to now so
    recency-sensitive code (ranking, breaking detection) behaves predictably.
    """
    published = datetime.now(timezone.utc).timestamp() - age_hours * 3600
    published_iso = datetime.fromtimestamp(published, tz=timezone.utc).isoformat()
    return Story(
        title=title,
        summary=summary or title,
        url=url or f"https://example.com/{abs(hash(title)) % 100000}",
        category=category,
        source=source,
        tier=tier,
        published_iso=published_iso,
        image_url=image_url,
        corroborating_sources=list(corroborating or []),
        score=score,
    )
