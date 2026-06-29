"""Generate the day's two Instagram carousels (content only, not images).

For each of the two strongest categories we:
  1. decide whether the carousel covers the top 3 or top 5 stories, based on how
     strong the lower-ranked stories are,
  2. ask the model for punchy per-slide text and a caption,
  3. assemble Slide objects (cover + one per story + a final CTA slide),
  4. attach the article image URLs that the renderer will use as backgrounds.

The actual PNGs are produced later by headlinne.render.carousel.
"""

from __future__ import annotations

from datetime import date

from ..config import (BRAND, CATEGORY_LABELS, INSTAGRAM_MAX_HASHTAGS, WEBSITE)
from ..gemini.client import GeminiClient
from ..gemini.prompts import STYLE_GUIDE, instagram_prompt
from ..logging_setup import get_logger
from ..models import InstagramCarousel, NewsDigest, Slide, Story
from ..news.images import best_story_image
from ..quality.sanitize import sanitize
from ..scheduling import slot_iso

log = get_logger("generate.instagram")

# CTA slide copy (kept simple and clean per the brief).
CTA_PRIMARY = f"Stay ahead with {WEBSITE}"

# Default hashtags blended in per category so posts stay on-brand.
_BASE_TAGS = {
    "Technology": ["Tech", "TechNews", "AI"],
    "Finance": ["Finance", "Markets", "Business"],
    "Geopolitics": ["WorldNews", "Geopolitics", "Politics"],
}


def _decide_num_stories(stories: list[Story]) -> int:
    """Pick 3 or 5 stories depending on how strong the deeper stories are.

    If we have at least five stories and the fifth is still reasonably strong
    relative to the top story, a five-story carousel is justified. Otherwise we
    keep it tight at three. Falls back gracefully when fewer are available.
    """
    available = len(stories)
    if available < 3:
        return max(1, available)
    if available >= 5:
        top = stories[0].score or 1.0
        fifth = stories[4].score
        if top > 0 and fifth >= 0.5 * top:
            return 5
    return 3


def _cover_title(category: str, n: int) -> str:
    """Cover headline. Keeps the word 'Geopolitics' intact so the renderer can
    apply the flag styling to the 'Geo' part."""
    label = CATEGORY_LABELS[category]
    if category == "Technology":
        return f"Top {n} Things In Tech Today"
    if category == "Finance":
        return f"Top {n} Finance Stories Today"
    # Geopolitics
    return f"Top {n} Geopolitics Headlines"


def _hashtags(category: str, model_tags: list[str]) -> list[str]:
    base = _BASE_TAGS.get(category, [])
    seen: set[str] = set()
    out: list[str] = []
    for tag in [*base, *model_tags, BRAND]:
        clean = str(tag).lstrip("#").replace(" ", "")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:INSTAGRAM_MAX_HASHTAGS]


def _carousel_for(client: GeminiClient, category: str, stories: list[Story],
                  slot: str, day: date) -> InstagramCarousel:
    n = _decide_num_stories(stories)
    chosen = stories[:n]
    label = CATEGORY_LABELS[category]

    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=instagram_prompt(label, chosen, n),
    )
    slide_data = data.get("slides", []) or []
    caption = sanitize(data.get("caption", ""))
    hashtags = _hashtags(category, data.get("hashtags", []))

    # Resolve the best available image for each chosen story once (this may fetch
    # the article hero for stories whose feed image is small or missing), then
    # reuse it for both the cover and the story slide.
    story_images = [best_story_image(s) for s in chosen]

    # Cover slide: title over the top story's featured image.
    cover_image = next((img for img in story_images if img), None)
    title = _cover_title(category, n)
    slides: list[Slide] = [
        Slide(role="cover", headline=title, explanation="", image_url=cover_image)
    ]

    # One slide per story. Use the model's text where present, else a safe
    # fallback drawn from the story itself.
    for i, story in enumerate(chosen):
        sd = slide_data[i] if i < len(slide_data) else {}
        headline = sanitize(sd.get("headline", "")) or sanitize(story.title)
        explanation = sanitize(sd.get("explanation", "")) or sanitize(story.summary)
        slides.append(
            Slide(
                role="story",
                headline=headline,
                explanation=explanation,
                image_url=story_images[i],
            )
        )

    # Final CTA slide (black background + logo, rendered later).
    slides.append(Slide(role="cta", headline=CTA_PRIMARY, explanation=""))

    # Caption fallback and website mention.
    if not caption:
        caption = f"Today's biggest {label} stories, in one quick scroll."
    if WEBSITE.lower() not in caption.lower():
        caption = f"{caption} Read more on {WEBSITE}."

    carousel = InstagramCarousel(
        slot=slot,
        category=category,
        num_slides=len(slides),
        title=title,
        slides=slides,
        caption=caption,
        hashtags=hashtags,
        scheduled_time=slot_iso(day, slot),
    )
    log.info("IG carousel [%s] %d slides (%d stories)", label, len(slides), n)
    return carousel


def generate(client: GeminiClient, digest: NewsDigest, categories: list[str],
             day: date) -> list[InstagramCarousel]:
    """Two carousels: one per chosen category, in slots instagram_1 / _2."""
    carousels: list[InstagramCarousel] = []
    slots = ["instagram_1", "instagram_2"]
    for cat, slot in zip(categories, slots):
        stories = digest.by_category.get(cat, [])
        if not stories:
            log.warning("No stories for %s, skipping its carousel.", cat)
            continue
        carousels.append(_carousel_for(client, cat, stories, slot, day))
    return carousels
