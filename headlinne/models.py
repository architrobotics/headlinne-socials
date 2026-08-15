"""Typed data structures passed between pipeline stages.

Plain dataclasses with dict (de)serialisation so everything round-trips cleanly
to the JSON files we commit under content/<date>/.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #
@dataclass
class Story:
    """A single news story, possibly corroborated by several sources."""

    title: str
    summary: str
    url: str
    category: str
    source: str
    tier: float
    published_iso: str
    image_url: Optional[str] = None

    # Filled in by the ranker.
    corroborating_sources: list[str] = field(default_factory=list)
    score: float = 0.0
    # Two independent outlets is the bar for calling a story verified. This is a
    # property of the story, never a ranking term: being widely covered is not
    # the same as being worth reading. Single-source stories still publish - the
    # source strip renders honestly thin, and we are willing to post that.
    verified: bool = False
    # Death and disaster. Renderers must drop the mascot, the speech bubble and
    # any wonder framing when this is set.
    sensitive: bool = False

    @property
    def source_count(self) -> int:
        return 1 + len(self.corroborating_sources)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Story":
        return cls(**d)


@dataclass
class NewsDigest:
    """The ranked picture of the day, grouped by category."""

    day: str
    by_category: dict[str, list[Story]]
    category_weights: dict[str, float]
    dominant_category: str
    breaking: Optional[Story] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "category_weights": self.category_weights,
            "dominant_category": self.dominant_category,
            "breaking": self.breaking.to_dict() if self.breaking else None,
            "by_category": {
                cat: [s.to_dict() for s in stories]
                for cat, stories in self.by_category.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NewsDigest":
        return cls(
            day=d["day"],
            category_weights=d["category_weights"],
            dominant_category=d["dominant_category"],
            breaking=Story.from_dict(d["breaking"]) if d.get("breaking") else None,
            by_category={
                cat: [Story.from_dict(s) for s in stories]
                for cat, stories in d["by_category"].items()
            },
        )

    def top(self, category: str, n: int) -> list[Story]:
        return self.by_category.get(category, [])[:n]


# --------------------------------------------------------------------------- #
# Generated content
# --------------------------------------------------------------------------- #
@dataclass
class TwitterPost:
    category: str            # "Tech" / "Finance" / "Geopolitics" / "Promo"
    post: str                # full text including the tail (URL + hashtags)
    hashtags: list[str]
    scheduled_time: str      # ISO 8601, IST offset
    kind: str = "news"       # "news" | "promo"

    # Structured pieces kept so the branded X card can be rendered from the same
    # content the tweet text was assembled from (the flattened `post` is hard to
    # lay out as a graphic, these are not).
    lead: str = ""                          # headline / lead line for the card
    items: list[str] = field(default_factory=list)  # story lines (news cards)
    image_file: Optional[str] = None        # rendered card PNG, relative to day folder

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LinkedInPost:
    title: str
    body: str
    cta: str
    scheduled_time: str
    kind: str = "product"    # "product" | "weekly_roundup"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Slide:
    """One Instagram slide's text content (images are rendered separately)."""

    role: str                       # "cover" | "story" | "cta"
    headline: str
    explanation: str = ""           # body text (what happened + why it matters)
    image_url: Optional[str] = None # source-article image used as background
    image_file: Optional[str] = None  # rendered slide PNG, relative to day folder

    # Richer furniture used by the renderer.
    subtitle: str = ""              # cover hook line / CTA sub-line
    sources: str = ""               # attribution line, e.g. "Reuters, BBC +2"
    index: int = 0                  # 1-based story number for the "01" device

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstagramCarousel:
    slot: str                       # "instagram_1" | "instagram_2"
    category: str                   # "Technology" / "Finance" / "Geopolitics"
    num_slides: int
    title: str                      # cover title, e.g. "AI just moved onto your phone"
    slides: list[Slide]
    caption: str
    hashtags: list[str]
    scheduled_time: str
    # The long tail of hashtags, posted as the first comment so the visible
    # caption stays readable (see config.INSTAGRAM_CAPTION_HASHTAGS).
    first_comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InstagramCarousel":
        slides = [Slide(**s) for s in d.pop("slides")]
        return cls(slides=slides, **d)


# --------------------------------------------------------------------------- #
# Reels
# --------------------------------------------------------------------------- #
@dataclass
class ReelBeat:
    """One cut of a reel: a short burned-in caption, optionally carried by a
    graphic device or a background photo.

    Reels are edited in beats rather than written as a script because the cut
    itself is what holds attention. Each beat owns its own on-screen text, so the
    renderer never has to break a paragraph across a cut.
    """

    role: str                       # "hook" | "point" | "graphic" | "payoff" | "outro"
    caption: str                    # the big on-screen line (keep it very short)
    detail: str = ""                # optional supporting line under the caption
    # What this beat says out loud. Deliberately separate from the on-screen
    # text: a line written to be read at a glance and a line written to be
    # spoken are rarely the same sentence.
    narration: str = ""
    seconds: float = 3.0
    graphic: str = ""               # "" | bars | counter | flow | timeline | split
    data: dict[str, Any] = field(default_factory=dict)  # payload for the graphic
    image_url: Optional[str] = None  # background photo for this beat

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Reel:
    """A rendered vertical video post."""

    slot: str                       # "reel_1" | "reel_2"
    kind: str                       # "news" | "education"
    category: str
    title: str                      # the idea in one line (internal / cover use)
    hook: str                       # the first thing on screen, decides everything
    beats: list[ReelBeat]
    caption: str
    hashtags: list[str]
    scheduled_time: str
    first_comment: str = ""
    sources: str = ""               # attribution line for news explainers
    story_url: str = ""
    duration_seconds: float = 0.0
    video_file: Optional[str] = None   # rendered MP4, relative to the day folder
    cover_file: Optional[str] = None   # rendered cover PNG for the Reels tab
    audio_file: Optional[str] = None   # narration WAV, kept for debugging
    has_voiceover: bool = False        # False means the MP4 carries silence

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Reel":
        d = dict(d)
        beats = [ReelBeat(**b) for b in d.pop("beats", [])]
        return cls(beats=beats, **d)


# --------------------------------------------------------------------------- #
# Story card
# --------------------------------------------------------------------------- #
@dataclass
class StoryStep:
    """One stop on the story card's rail, e.g. 'WHAT HAPPENED'."""

    label: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoryCard:
    """One article, walked through start to finish on a single image.

    This is the deliberate counterweight to the carousel: a carousel asks for
    swipes, this asks for a save. Everything a reader needs is on one frame, so
    the natural action is to keep it rather than to page through it.
    """

    slot: str                       # "story_card"
    category: str
    headline: str
    standfirst: str                 # one line of context under the headline
    steps: list[StoryStep]
    caption: str
    hashtags: list[str]
    scheduled_time: str
    first_comment: str = ""
    sources: str = ""
    story_url: str = ""
    image_url: Optional[str] = None   # article photo, used as a dimmed texture
    image_file: Optional[str] = None  # rendered PNG, relative to the day folder

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StoryCard":
        d = dict(d)
        steps = [StoryStep(**s) for s in d.pop("steps", [])]
        return cls(steps=steps, **d)


@dataclass
class DayPlan:
    """The full set of content produced for one day."""

    day: str
    is_promo_day: bool
    is_friday: bool
    twitter: list[TwitterPost]
    linkedin: LinkedInPost
    instagram: list[InstagramCarousel]
    reels: list[Reel] = field(default_factory=list)
    story_card: Optional[StoryCard] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "is_promo_day": self.is_promo_day,
            "is_friday": self.is_friday,
            "twitter": [t.to_dict() for t in self.twitter],
            "linkedin": self.linkedin.to_dict(),
            "instagram": [c.to_dict() for c in self.instagram],
            "reels": [r.to_dict() for r in self.reels],
            "story_card": self.story_card.to_dict() if self.story_card else None,
        }
