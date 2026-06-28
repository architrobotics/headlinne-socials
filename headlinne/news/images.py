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


def image_from_entry(entry) -> str | None:
    # media_content / media_thumbnail (feedparser normalises these).
    for key in ("media_content", "media_thumbnail"):
        items = entry.get(key) or []
        for it in items:
            url = it.get("url")
            if _looks_like_image(url):
                return url

    # enclosures
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and _looks_like_image(enc.get("href")):
            return enc.get("href")
        if _looks_like_image(enc.get("href")):
            return enc.get("href")

    # An <img> inside the summary/content HTML.
    html = entry.get("summary") or ""
    for blk in entry.get("content", []) or []:
        html += blk.get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    if m and _looks_like_image(m.group(1)):
        return m.group(1)

    # Last resort: scrape the article's og:image.
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
