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
class Conflict:
    """One outlet's differing account of the claim under comparison."""

    outlet: str
    value: str                      # what this outlet said, verbatim-ish

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Agreement:
    """How many outlets agree on a story's central claim, and which ones.

    The denominator is the whole design of this component, and getting it wrong
    is the difference between a trust signal and a lie by framing.

    Three counts, and they are not interchangeable:

      reported   outlets that covered the event at all, after syndication
                 collapse. Never the number of feeds we read: the outlets that
                 never wrote about this story did not disagree with it, and
                 counting their silence as absent agreement invents a dispute
                 that never happened.
      agree      outlets whose account of the claim matches.
      conflict   outlets that reported a materially different value for it.

    `agree + conflict` is the *eligible* set - the outlets that took a position
    we can actually compare. An outlet that covered the event but never
    mentioned the figure is silent, not dissenting, so it is in `reported` and
    in neither of the other two. Silence never draws a hollow tick, because a
    hollow tick reads as "this outlet disagrees" and that would be false.

    That distinction is what lets the label be honest in all three shapes the
    design system draws:

      "8 of 8 outlets agree"   every outlet that reported it took a position,
                               and they matched
      "4 sources agree"        four agreed, the rest were silent on the claim -
                               a count, because a fraction here would imply a
                               dissenting remainder we never measured
      "3 of 7 outlets agree"   seven took a position and four of them differ
    """

    reported: int = 0
    agree: int = 0
    conflict: int = 0
    claim: str = ""                             # the originating outlet's value
    # What is being counted, e.g. "jobs" or "km/h". Kept apart from the value so
    # the compare card can print the number large and the unit small, rather
    # than having to parse one back out of the other.
    claim_unit: str = ""
    outlets: list[str] = field(default_factory=list)      # named, best first
    conflicts: list[Conflict] = field(default_factory=list)

    # ---- derived ---------------------------------------------------------- #
    @property
    def eligible(self) -> int:
        """Outlets that took a comparable position on the claim."""
        return self.agree + self.conflict

    @property
    def silent(self) -> int:
        """Covered the event, said nothing about the claim. Not dissent."""
        return max(0, self.reported - self.eligible)

    @property
    def state(self) -> str:
        """`single` | `unanimous` | `developing` | `disputed`.

        Drives the eyebrow, the masthead rule colour and Pip's pose, so a
        regular reader learns the shape of a story before reading a word.
        """
        if self.reported <= 1:
            return "single"
        if self.conflict:
            return "disputed"
        if self.silent:
            return "developing"
        return "unanimous"

    @property
    def publishable(self) -> bool:
        """Two independent outlets is the bar. A gate, not a penalty."""
        return self.reported >= 2

    def label(self) -> str:
        """The line printed under the tick strip."""
        if self.reported <= 1:
            return "Single source · not yet corroborated"
        if self.state == "unanimous":
            return f"{self.agree} of {self.reported} outlets agree"
        if self.state == "developing":
            # A fraction would imply the silent outlets dissented. They did not.
            return f"{self.agree} sources agree"
        return f"{self.agree} of {self.eligible} outlets agree"

    def ticks(self) -> tuple[int, int]:
        """(filled, hollow) marks to draw. Silent outlets draw nothing."""
        if self.reported <= 1:
            return 0, 1
        return self.agree, self.conflict

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Agreement":
        if not d:
            return cls()
        d = dict(d)
        d["conflicts"] = [Conflict(**c) for c in d.get("conflicts", [])]
        # `eligible`, `silent`, `state` and `publishable` are properties, so a
        # dict written by an older build that inlined them round-trips cleanly.
        known = {"reported", "agree", "conflict", "claim", "claim_unit",
                 "outlets", "conflicts"}
        return cls(**{k: v for k, v in d.items() if k in known})


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
    # property of the story and never a ranking term: being widely covered is not
    # the same as being worth reading.
    verified: bool = False
    # Death and disaster. Renderers must drop the mascot, the speech bubble and
    # any wonder framing when this is set. Carried on the story rather than
    # recomputed at render time so the flag survives the trip through
    # content/<date>/news_digest.json to the publish stage.
    sensitive: bool = False
    # Who reported this and whether they agree. Filled by news.corroborate.
    agreement: Agreement = field(default_factory=Agreement)

    @property
    def source_count(self) -> int:
        return 1 + len(self.corroborating_sources)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Story":
        d = dict(d)
        d["agreement"] = Agreement.from_dict(d.get("agreement"))
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
    """One carousel slide.

    `role` is the job the slide does in the argument, not a layout name:
    cover -> scale -> twist -> sources -> cta. The renderer picks a layout from
    it, and quality.visual rejects a carousel whose roles are out of order,
    because the order *is* the argument.
    """

    role: str                       # "cover" | "scale" | "twist" | "sources" | "cta"
    headline: str
    explanation: str = ""           # body text (what happened + why it matters)
    image_url: Optional[str] = None # source-article image, framed as a plate
    image_file: Optional[str] = None  # rendered slide PNG, relative to day folder

    # Richer furniture used by the renderer.
    subtitle: str = ""              # cover hook line / CTA sub-line
    sources: str = ""               # attribution line, e.g. "Reuters, BBC +2"
    index: int = 0                  # 1-based position in the set
    kicker: str = ""                # the small uppercase label above the headline
    # What Pip does and says on this slide. `pose` is None-able rather than
    # defaulted so a sensitive story can carry no mascot at all: an empty string
    # means "draw nothing", not "draw the neutral one".
    pose: str = ""
    say: str = ""
    # The scale slide's single enormous figure, kept apart from the prose so the
    # renderer never has to parse a number back out of a sentence.
    figure: str = ""
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstagramCarousel:
    """One day's carousel: one story, argued across five slides."""

    slot: str                       # "instagram_1"
    category: str
    num_slides: int
    title: str                      # cover title
    slides: list[Slide]
    caption: str
    hashtags: list[str]
    scheduled_time: str
    # The long tail of hashtags, posted as the first comment so the visible
    # caption stays readable (see config.INSTAGRAM_CAPTION_HASHTAGS).
    first_comment: str = ""
    # The story being argued. Carried whole rather than flattened into strings
    # because every slide's furniture - the receipt, the tone, Pip's pose - is
    # derived from its agreement record, and the publish stage reads this file
    # hours after the generate stage wrote it.
    story: Optional[Story] = None
    story_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InstagramCarousel":
        d = dict(d)
        slides = [Slide(**s) for s in d.pop("slides")]
        story = d.pop("story", None)
        return cls(slides=slides,
                   story=Story.from_dict(story) if story else None, **d)


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

    # The two-word label above the line, e.g. "WHERE", "HOW FAST". It tells a
    # viewer what question this beat answers before they have read the answer,
    # which is what keeps someone watching through a cut.
    chapter: str = ""
    # Which pose Pip holds. "cta" defers to the day's rotation; an empty string
    # means no mascot at all, which is what a sensitive story renders as.
    pose: str = ""
    say: str = ""                   # speech bubble, or empty for none
    # Plate slots to fill on this beat. One centres, two spread and shrink.
    plates: list[str] = field(default_factory=list)
    # Override the tone this beat takes. Empty means "derive it from the role",
    # which is what gives the reel its colour rhythm without authoring one.
    tone: str = ""

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
    dateline: str = ""              # "WED 5 AUG", printed in the masthead
    # The story this reel is about, carried whole so the renderer can draw its
    # source strip and the publish stage can read it back hours later. None for
    # an educational reel, which teaches an evergreen idea and has no article
    # behind it - and therefore renders without a strip rather than an invented
    # one.
    story: Optional[Story] = None
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
        story = d.pop("story", None)
        return cls(beats=beats,
                   story=Story.from_dict(story) if story else None, **d)


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
    image_url: Optional[str] = None   # article photo, framed as a plate
    image_file: Optional[str] = None  # rendered PNG, relative to the day folder
    story: Optional[Story] = None     # for the source strip and Pip's pose

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StoryCard":
        d = dict(d)
        steps = [StoryStep(**s) for s in d.pop("steps", [])]
        story = d.pop("story", None)
        return cls(steps=steps,
                   story=Story.from_dict(story) if story else None, **d)


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
