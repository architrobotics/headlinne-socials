"""Render what the new ranker actually picks, from archived days.

`python -m headlinne preview` renders one hand-written mock story, so it shows
the design and tells you nothing about selection. This runs the real selectors
over real archived digests and renders the stories they choose.

What is real here: the ranking, the pick, the category, the agreement state, the
kicker, Pip's pose, the source strip, and every pixel of layout.

What is stand-in: the sentences. Gemini writes those in a live run and there is
no key here, so the slide copy is assembled from the article's own headline and
summary. Judge the story choice and the furniture, not the prose.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

# Run as `python scripts/sample_picks.py ...` from the repo root, so the package
# has to be put on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from headlinne.generate import instagram as GI
from headlinne.generate import story_card as GS
from headlinne.models import (InstagramCarousel, NewsDigest, Slide, Story,
                              StoryCard, StoryStep)
from headlinne.news import interest as I
from headlinne.news import ranking as R
from headlinne.render import receipt as RC
from headlinne.render import render_carousel, render_story_card, theme

logging.disable(logging.WARNING)

FIGURE = re.compile(
    r"(\d[\d,.]*)\s*(billion|million|trillion|tonnes?|km/h|km|kg|percent|%|"
    r"years?|light[- ]years|metres|meters|miles|degrees)", re.I)


def _clip(text: str, limit: int) -> str:
    """Truncate on a word boundary. A mid-word cut is my bug, not the layout's."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "."


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text or "") if p.strip()]
    return [p for p in parts if len(p) > 25]


def _figure(story: Story) -> tuple[str, str]:
    m = FIGURE.search(f"{story.title} {story.summary}")
    return (m.group(1), m.group(2).lower()) if m else ("", "")


def _load(day: str) -> NewsDigest:
    j = json.load(open(f"content/{day}/news_digest.json", encoding="utf-8"))
    by_cat = {c: [Story.from_dict(d) for d in v] for c, v in j["by_category"].items()}
    for stories in by_cat.values():
        for s in stories:
            s.sensitive = I.is_sensitive(s.title, s.summary)
            s.score = round(R._score(s), 3)
        stories.sort(key=lambda s: -s.score)
    return NewsDigest(day=j["day"], category_weights=j["category_weights"],
                      dominant_category=j["dominant_category"], by_category=by_cat)


def build_carousel(story: Story, day: str) -> InstagramCarousel:
    sents = _sentences(story.summary)
    fig, unit = _figure(story)
    kicker = RC.eyebrow(story)
    pose = lambda kind: theme.pose_for_story(story, kind) or ""

    slides = [
        Slide(role="cover", index=1, headline=story.title,
              subtitle=_clip(sents[0], 90) if sents else "",
              kicker=kicker, pose=pose("cover"),
              say="Here is today's one." if not story.sensitive else "",
              image_url=story.image_url),
        Slide(role="scale", index=2, headline="", kicker="HOW BIG",
              figure=fig, unit=unit,
              explanation=(sents[1] if len(sents) > 1 else
                           "The number that gives this story its size."),
              image_url=story.image_url),
        Slide(role="twist", index=3,
              headline=(_clip(sents[1], 70) if len(sents) > 1 else _clip(story.title, 70)),
              kicker="WHAT YOU DID NOT KNOW", pose=pose("twist"),
              say="Here is the bit I like." if not story.sensitive else "",
              explanation=(sents[2] if len(sents) > 2 else
                           "The detail the headline leaves out.")),
        Slide(role="sources", index=4, headline="", kicker="SOURCES",
              pose=pose("sources"),
              say=RC.agreement_of(story).label() if not story.sensitive else "",
              explanation=("Headlinne reads every outlet covering a story and "
                           "shows you where they agree, and where they do not.")),
        Slide(role="cta", index=5, headline="", kicker="READ THE FULL STORY",
              pose="carry", say="Come and read it." if not story.sensitive else "",
              subtitle="Every source on this story, side by side."),
    ]
    return InstagramCarousel(
        slot="instagram_1", category=story.category, num_slides=len(slides),
        title=story.title, slides=slides,
        caption="One story, explained.", hashtags=[story.category],
        scheduled_time=f"{day}T16:00:00+05:30", story=story, story_url=story.url)


def build_card(story: Story, day: str) -> StoryCard:
    sents = _sentences(story.summary)
    labels = ("What happened", "How we got here", "Why it matters", "What to watch")
    filler = ("The reporting so far.", "The context behind it.",
              "What it changes for a reader.", "The next thing to look for.")
    steps = [StoryStep(label=lab, text=(sents[i] if i < len(sents) else filler[i]))
             for i, lab in enumerate(labels)]
    return StoryCard(
        slot="story_card", category=story.category, headline=story.title,
        standfirst=(_clip(sents[0], 96) if sents else ""), steps=steps,
        caption="The full story.", hashtags=[story.category],
        scheduled_time=f"{day}T21:30:00+05:30",
        sources=" · ".join(RC.outlets(story)[:4]),
        story=story, story_url=story.url, image_url=story.image_url)


def main(days: list[str], out_root: Path) -> None:
    for day in days:
        digest = _load(day)
        carousel_story = GI.pick_story(digest)
        card_story = GS.pick_story(digest, exclude_urls={carousel_story.url},
                                   prefer_other_than=carousel_story.category,
                                   exclude_stories=[carousel_story])
        out = out_root / day
        print(f"\n{day}")
        print(f"  carousel   [{carousel_story.category}] {carousel_story.title[:66]}")
        print(f"             state={RC.state(carousel_story)} "
              f"outlets={len(RC.outlets(carousel_story))} "
              f"sensitive={carousel_story.sensitive} "
              f"pose={theme.pose_for_story(carousel_story, 'cover')}")
        render_carousel(build_carousel(carousel_story, day), out / "carousel")
        if card_story:
            print(f"  story card [{card_story.category}] {card_story.title[:66]}")
            print(f"             state={RC.state(card_story)} "
                  f"outlets={len(RC.outlets(card_story))} "
                  f"sensitive={card_story.sensitive}")
            render_story_card(build_card(card_story, day),
                              out / "story_card" / "story_card.png",
                              story=card_story)
    print(f"\nwritten to {out_root}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python scripts/sample_picks.py <out-dir> [YYYY-MM-DD ...]"
            "\n       days default to the most recent archived digest")
    out_root = Path(sys.argv[1])
    days = sys.argv[2:]
    if not days:
        archived = sorted(p.parent.name for p in
                          Path("content").glob("*/news_digest.json"))
        if not archived:
            raise SystemExit("no archived digests under content/")
        days = archived[-1:]
    main(days, out_root)
