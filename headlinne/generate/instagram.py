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

from ..config import (BRAND, CATEGORY_LABELS, INSTAGRAM_HANDLE,
                      INSTAGRAM_MAX_HASHTAGS, WEBSITE)
from ..gemini.client import GeminiClient
from ..gemini.prompts import STYLE_GUIDE, instagram_prompt
from ..logging_setup import get_logger
from ..models import InstagramCarousel, NewsDigest, Slide, Story
from ..news.images import best_story_image
from ..quality.sanitize import sanitize
from ..scheduling import slot_iso

log = get_logger("generate.instagram")

# CTA slide copy.
CTA_HEADLINE = "That's your brief for today."
CTA_SUBTITLE = "Personalised news, minus the noise."

# Default hashtags blended in per category so posts stay on-brand. A short reach
# set plus a couple of niche tags; the model adds more topical ones on top.
_BASE_TAGS = {
    "Technology": ["Tech", "TechNews", "AI", "Innovation"],
    "Finance": ["Finance", "Markets", "Business", "Economy"],
    "Geopolitics": ["WorldNews", "Geopolitics", "GlobalNews", "Politics"],
}


def source_line(story: Story) -> str:
    """A compact attribution line for a story slide, e.g. 'Reuters, BBC +2'.

    This is the audience-facing trust signal that mirrors the cross-source
    verification the ranker already does. Shows up to two outlet names, then a
    '+N' for the rest, so a well-corroborated story visibly reads as verified.
    """
    names = [n for n in ([story.source] + list(story.corroborating_sources)) if n]
    if not names:
        return ""
    shown = names[:2]
    extra = len(names) - len(shown)
    line = ", ".join(shown)
    if extra > 0:
        line += f" +{extra}"
    return line


def _clamp_words(text: str, max_chars: int) -> str:
    """Trim to a word boundary under max_chars (keeps cover titles tidy)."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(",.:;- ").strip() or text[:max_chars]


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
    """Deterministic fallback cover headline, used only if the model does not
    return a usable title. Clean and on-brand across categories."""
    if category == "Technology":
        return f"The {n} tech stories that matter today"
    if category == "Finance":
        return f"The {n} money moves that matter today"
    # Geopolitics
    return f"The {n} world stories that matter today"


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

    # Cover title + hook (model-written, sanitised and length-clamped, with a
    # clean deterministic fallback so the cover is never empty or over-long).
    title = _clamp_words(sanitize(data.get("cover_title", "")), 52) or _cover_title(category, n)
    hook = _clamp_words(sanitize(data.get("cover_hook", "")), 96)

    # Resolve the best available image for each chosen story once (this may fetch
    # the article hero for stories whose feed image is small or missing), then
    # reuse it for both the cover and the story slide.
    story_images = [best_story_image(s) for s in chosen]

    # Cover slide: title + hook over the top story's featured image.
    cover_image = next((img for img in story_images if img), None)
    slides: list[Slide] = [
        Slide(role="cover", headline=title, subtitle=hook, image_url=cover_image)
    ]

    # One slide per story. Use the model's text where present, else a safe
    # fallback drawn from the story itself. Each slide carries its 1-based index
    # and a source-attribution line for the on-slide trust signal.
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
                sources=source_line(story),
                index=i + 1,
            )
        )

    # Final CTA slide (rendered later with the brand background + engagement).
    slides.append(Slide(role="cta", headline=CTA_HEADLINE, subtitle=CTA_SUBTITLE))

    # Caption fallback, engagement nudge and website mention.
    if not caption:
        caption = (f"Today's biggest {label} stories, in one quick scroll. "
                   f"Which one caught you off guard?")
    caption = f"{caption}\n\nFollow {INSTAGRAM_HANDLE} for a daily brief."
    if WEBSITE.lower() not in caption.lower():
        caption = f"{caption} More at {WEBSITE}."

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
