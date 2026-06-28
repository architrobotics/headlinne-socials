"""Best-effort extraction of a featured image URL for a story.

Order of preference:
  1. Media fields already present in the RSS entry (media:content, thumbnail,
     enclosure) - free, no extra request.
  2. The article page's og:image / twitter:image - one lightweight GET.

If nothing is found we return None and the renderer falls back to a generated
gradient background, so a missing image never breaks a carousel.
"""

from __future__ import annotations

import re
from functools import lru_cache

import requests

from ..logging_setup import get_logger

log = get_logger("news.images")

_UA = "HeadlinneBot/1.0 (+https://headlinne.com; news aggregation)"
_TIMEOUT = 8


def _looks_like_image(url: str | None) -> bool:
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    if any(low.split("?")[0].endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
        return True
    # Many CMS image URLs have no extension; accept https URLs that mention image.
    return "image" in low or "img" in low or "/photo" in low or "media" in low


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def image_from_entry(entry) -> str | None:
    """Pick the best featured-image URL the entry offers, preferring larger,
    full-size images over small thumbnails.

    This runs for every story, so it never makes an extra request when the feed
    already provides an image. The article hero (og:image) is fetched only as a
    last resort when the feed gives us nothing. The renderer upgrades whatever
    URL we pick to a higher-resolution variant at draw time.
    """
    # (source_rank, width, url) - higher rank = more likely a full-size image.
    candidates: list[tuple[int, int, str]] = []

    for it in entry.get("media_content") or []:
        if _looks_like_image(it.get("url")):
            candidates.append((3, _int(it.get("width")), it["url"]))

    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href")
        if _looks_like_image(href):
            is_img = str(enc.get("type", "")).startswith("image")
            candidates.append((3 if is_img else 2, _int(enc.get("width")), href))

    for it in entry.get("media_thumbnail") or []:
        if _looks_like_image(it.get("url")):
            candidates.append((1, _int(it.get("width")), it["url"]))

    # An <img> inside the summary/content HTML.
    html = entry.get("summary") or ""
    for blk in entry.get("content", []) or []:
        html += blk.get("value", "")
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html):
        if _looks_like_image(m.group(1)):
            candidates.append((1, 0, m.group(1)))

    # Prefer the more reliable source (full image over thumbnail), then the
    # largest known width within that.
    best = max(candidates, key=lambda c: (c[0], c[1]), default=None)
    if best is not None:
        return best[2]

    # Nothing in the feed: fall back to the article's og:image (one request).
    link = entry.get("link")
    if link:
        og = _og_image(link)
        if og:
            return og
    return None


@lru_cache(maxsize=512)
def _og_image(url: str) -> str | None:
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _UA},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        # Only need the <head>; cap the body we scan.
        html = resp.text[:120_000]
    except Exception:
        return None

    for prop in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']',
                html, re.IGNORECASE,
            )
        if m and _looks_like_image(m.group(1)):
            return m.group(1)
    return None
