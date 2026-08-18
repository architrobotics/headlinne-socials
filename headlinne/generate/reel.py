"""Build the day's two reels: one news explainer, one educational explainer.

The two exist for different reasons. The news reel is timely and rides whatever
interest the day's biggest story already has. The educational reel is evergreen,
teaches one mechanism, and is the thing that gets saved, sent to a friend and
still picked up by the algorithm three weeks later. A news account that only
posts news has nothing that compounds.

Both are assembled the same way: the model writes beats, and this module enforces
everything that has to hold every single time. Two guarantees matter most.

**Lengths.** On-screen text is drawn into a fixed frame, so captions and details
are clamped here rather than trusted to the prompt.

**Figures.** A graphic that prints a number is making a factual claim in a form
people screenshot. So numbers printed by `counter` and `bars` are checked
character by character against the source material, and anything that does not
appear there is removed. Educational reels lose printed figures entirely, since
their examples are openly hypothetical and a hypothetical number rendered as a
chart stops looking hypothetical.
"""

from __future__ import annotations

from datetime import date

from ..config import (BRAND, CATEGORY_LABELS, EDUCATION_TOPICS, EducationTopic)
from ..gemini.client import GeminiClient
from ..gemini.prompts import (STYLE_GUIDE, reel_daily_prompt,
                              reel_education_prompt,
                              reel_news_prompt, stories_block)
from ..logging_setup import get_logger
from ..models import NewsDigest, Reel, ReelBeat, Story
from ..news.images import best_story_image
from ..quality.sanitize import sanitize
from ..render.graphics import DEVICES, LABEL_ONLY_DEVICES
from ..scheduling import slot_iso
from ..render import receipt as receipt_mod
from . import hooks
from .common import clamp_words


def source_line(story: Story) -> str:
    """The attribution line printed under the reel's tick strip.

    Drawn from the agreement record rather than from the raw corroborating list,
    so a syndicated wire carried by six outlets is named once.
    """
    return receipt_mod.named(story, limit=4)

log = get_logger("generate.reel")

# Hard limits for burned-in text. These are set by reading speed, not by the
# space available, and that is the stricter constraint.
#
# A 28 second reel across six beats leaves roughly four seconds a cut. The big
# caption is display type taken in at a glance, call it a second, which leaves
# about three seconds for the supporting line. Comfortable silent reading of a
# line you also have to think about is around 20 characters a second, so the
# detail line has to fit in about 75. Anything longer is text the viewer sees
# but does not finish, which is worse than not writing it.
HOOK_CHARS = 46
HOOK_DETAIL_CHARS = 76
CAPTION_CHARS = 48
DETAIL_CHARS = 76
PAYOFF_CHARS = 50

# Spoken lines are capped by runtime, not by the frame. A synthetic voice reads
# at roughly 13 to 15 characters a second, so 76 characters is about five
# seconds, and seven of those plus their air lands a narrated reel in the high
# thirties.
#
# That is longer than the silent version and it is meant to be. You cannot
# explain a mechanism in twenty seconds with a voice, and a narrated explainer
# holds attention differently from a muted one. But the drop-off past about
# forty-five seconds is real, which is what this number is defending.
NARRATION_CHARS = 76

# Body beats after the hook: what happened, the mechanism, a graphic, why it
# matters. Five would fit the runtime but leaves each beat too short to land.
NEWS_BEATS = 4
EDUCATION_BEATS = 4

# Where the news reel puts photography. The rest of the beats are designed
# panels, which gives the edit a rhythm instead of six photos in a row.
_NEWS_PHOTO_BEATS = (0, 3)

_BASE_TAGS = {
    "Technology": ["TechNews", "AI", "Tech"],
    "Finance": ["Finance", "Markets", "Economy"],
    "Geopolitics": ["WorldNews", "Geopolitics", "GlobalNews"],
}


# --------------------------------------------------------------------------- #
# Number verification
# --------------------------------------------------------------------------- #
def _digits(text: str) -> list[str]:
    """Every run of digits in a string, with separators removed.

    "$2,400 by 2026" -> ["2400", "2026"]. Comparing digit runs rather than whole
    strings means "$2.4bn" still matches source text that wrote "2.4 billion".
    """
    runs: list[str] = []
    current = ""
    for ch in str(text or ""):
        if ch.isdigit():
            current += ch
        elif ch in ",. " and current:
            # Keep going: separators inside a number are not the end of it.
            continue
        elif current:
            runs.append(current)
            current = ""
    if current:
        runs.append(current)
    return runs


def _figure_is_supported(label: str, source_digits: set[str]) -> bool:
    """Whether every number in `label` appears in the source material."""
    runs = _digits(label)
    if not runs:
        return True  # nothing numeric to verify
    return all(run in source_digits for run in runs)


def verify_graphic(device: str, data: dict, source_text: str,
                   *, allow_figures: bool) -> tuple[str, dict]:
    """Strip any printed figure the source material does not support.

    Returns the device and data to actually render. A device may be downgraded
    (a `counter` with an unverifiable number is dropped entirely, since a counter
    with no number is nothing) or quietly cleaned (a `bars` payload keeps its
    shape and loses only the labels that failed).
    """
    device = (device or "").strip().lower()
    if device not in DEVICES:
        return "", {}
    data = dict(data or {})

    if device in LABEL_ONLY_DEVICES:
        return device, data

    source_digits = set(_digits(source_text))

    if device == "counter":
        label = str(data.get("value_label") or "").strip()
        if not label:
            return "", {}
        if not allow_figures or not _figure_is_supported(label, source_digits):
            log.info("dropping counter %r: figure not supported by the source", label)
            return "", {}
        return device, data

    # bars
    bars = [b for b in (data.get("bars") or []) if isinstance(b, dict)][:3]
    if not bars:
        return "", {}
    cleaned = []
    for bar in bars:
        bar = dict(bar)
        label = str(bar.get("value_label") or "").strip()
        if label and (not allow_figures
                      or not _figure_is_supported(label, source_digits)):
            log.info("dropping bar figure %r: not supported by the source", label)
            bar.pop("value_label", None)
        cleaned.append(bar)
    return device, {"bars": cleaned}


# --------------------------------------------------------------------------- #
# Shared assembly
# --------------------------------------------------------------------------- #
def _hashtags(category: str, model_tags: list[str], *, extra: list[str] | None = None,
              limit: int = 16) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in [*(extra or []), *_BASE_TAGS.get(category, []), *model_tags, BRAND]:
        clean = str(tag).lstrip("#").replace(" ", "")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:limit]


def _beats_from(data: dict, *, source_text: str, allow_figures: bool,
                forced_device: str = "") -> list[ReelBeat]:
    """Turn the model's beat list into clamped, verified ReelBeats."""
    beats: list[ReelBeat] = []
    for raw in (data.get("beats") or []):
        if not isinstance(raw, dict):
            continue
        caption = clamp_words(sanitize(raw.get("caption", "")), CAPTION_CHARS)
        if not caption:
            continue
        detail = clamp_words(sanitize(raw.get("detail", "")), DETAIL_CHARS)
        narration = clamp_words(sanitize(raw.get("narration", "")), NARRATION_CHARS)

        chosen = str(raw.get("graphic") or "").strip().lower()
        device, payload = "", {}
        if chosen:
            # An education topic declares its own device, so the model's choice
            # only signals *which* beat carries the graphic. If the payload does
            # not fit the declared device we fall back to what the model
            # actually wrote, rather than dropping the picture entirely.
            for candidate in ([forced_device, chosen] if forced_device else [chosen]):
                device, payload = verify_graphic(candidate, raw.get("data") or {},
                                                 source_text,
                                                 allow_figures=allow_figures)
                if device:
                    break
        beats.append(ReelBeat(role="graphic" if device else "point",
                              caption=caption, detail=detail,
                              narration=narration, graphic=device, data=payload))
    return beats


def _assemble(*, slot: str, kind: str, category: str, title: str, data: dict,
              beats: list[ReelBeat], day: date, sources: str = "",
              story_url: str = "", extra_tags: list[str] | None = None) -> Reel:
    hook = clamp_words(sanitize(data.get("hook", "")), HOOK_CHARS) or title
    hook_detail = clamp_words(sanitize(data.get("hook_detail", "")),
                              HOOK_DETAIL_CHARS)
    payoff = clamp_words(sanitize(data.get("payoff", "")), PAYOFF_CHARS)

    ordered = [ReelBeat(
        role="hook", caption=hook, detail=hook_detail,
        narration=clamp_words(sanitize(data.get("hook_narration", "")),
                              NARRATION_CHARS))]
    ordered.extend(beats)
    if payoff:
        ordered.append(ReelBeat(
            role="payoff", caption=payoff,
            narration=clamp_words(sanitize(data.get("payoff_narration", "")),
                                  NARRATION_CHARS)))

    hashtags = _hashtags(category, data.get("hashtags", []) or [], extra=extra_tags)
    caption, first_comment = hooks.build_caption(
        opener=sanitize(data.get("caption_opener", "")) or hook,
        body=sanitize(data.get("caption_body", "")),
        question=sanitize(data.get("question", "")),
        hashtags=hashtags,
    )

    reel = Reel(
        slot=slot, kind=kind, category=category, title=title, hook=hook,
        beats=ordered, caption=caption, hashtags=hashtags,
        first_comment=first_comment, sources=sources, story_url=story_url,
        scheduled_time=slot_iso(day, slot),
    )
    log.info("reel [%s/%s] %d beats, hook=%r", slot, kind, len(ordered), hook)
    return reel


# --------------------------------------------------------------------------- #
# News explainer
# --------------------------------------------------------------------------- #
def lead_story(digest: NewsDigest, *, exclude_urls: set[str] | None = None) -> Story | None:
    """The single most significant story of the day, across all categories.

    Breaking news wins when there is any, because a reel about the thing people
    are already searching for starts with an audience that a well-made reel about
    something else does not have.
    """
    exclude = exclude_urls or set()
    if digest.breaking and digest.breaking.url not in exclude:
        return digest.breaking
    candidates = [s for stories in digest.by_category.values() for s in stories
                  if s.url not in exclude]
    if not candidates:
        return None
    return max(candidates, key=lambda s: (s.score, s.source_count))


def generate_news(client: GeminiClient, digest: NewsDigest, day: date,
                  *, exclude_urls: set[str] | None = None) -> Reel | None:
    """A reel that walks through the day's biggest story."""
    story = lead_story(digest, exclude_urls=exclude_urls)
    if story is None:
        log.warning("No story available for the news reel.")
        return None

    label = CATEGORY_LABELS.get(story.category, story.category)
    source_text = f"{story.title} {story.summary}"

    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=reel_news_prompt(stories_block([story]),
                                hooks.hook_brief(day, "reel_1"),
                                NEWS_BEATS, label),
    )

    beats = _beats_from(data, source_text=source_text, allow_figures=True)

    # Photography goes on the hook and the "why it matters" beat. The middle of
    # the reel is designed panels, so the graphic beat lands as a change of pace.
    image = best_story_image(story)
    reel = _assemble(slot="reel_1", kind="news", category=story.category,
                     title=clamp_words(sanitize(story.title), 90), data=data,
                     beats=beats, day=day, sources=source_line(story),
                     story_url=story.url)
    if image:
        reel.beats[0].image_url = image
        for offset in _NEWS_PHOTO_BEATS:
            index = offset + 1  # the hook occupies index 0
            if index < len(reel.beats) and not reel.beats[index].graphic:
                reel.beats[index].image_url = image
    return reel


# --------------------------------------------------------------------------- #
# Educational explainer
# --------------------------------------------------------------------------- #
def topic_for(day: date) -> EducationTopic:
    """Rotate deterministically through the topic list, one per day."""
    return EDUCATION_TOPICS[day.toordinal() % len(EDUCATION_TOPICS)]


def generate_education(client: GeminiClient, day: date) -> Reel:
    """A reel that teaches one evergreen idea with a worked example."""
    topic = topic_for(day)
    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=reel_education_prompt(topic.title, topic.angle, topic.graphic,
                                     hooks.hook_brief(day, "reel_2"),
                                     EDUCATION_BEATS),
    )

    # allow_figures=False: an educational reel's examples are hypothetical by
    # design, and a hypothetical number drawn as a chart reads as a real one.
    beats = _beats_from(data, source_text="", allow_figures=False,
                        forced_device=topic.graphic)

    # If the model did not mark a graphic beat, put the topic's device on the
    # middle beat rather than shipping a reel with no picture in it.
    if beats and not any(b.graphic for b in beats):
        middle = beats[len(beats) // 2]
        log.info("no graphic beat returned, applying %r to beat %d",
                 topic.graphic, len(beats) // 2 + 1)
        middle.graphic = topic.graphic if topic.graphic in LABEL_ONLY_DEVICES else ""
        middle.role = "graphic" if middle.graphic else "point"

    return _assemble(slot="reel_2", kind="education", category=topic.category,
                     title=topic.title, data=data, beats=beats, day=day,
                     extra_tags=["Explained", "LearnOnInstagram"])


# --------------------------------------------------------------------------- #
# The daily reel
# --------------------------------------------------------------------------- #
# One reel a day, on the day's strongest story. Two reels was more than the
# speech quota comfortably carried and more than a small account needs: each post
# competes with the others for the same initial test audience, and the reel is
# the one that has to win that competition because it is the only surface that
# reaches people who do not already follow.
DAILY_BEATS = 7

# Below this interest score the day has no story worth thirty seconds, and the
# reel teaches an evergreen idea instead. An explainer of why a rate rise reaches
# your loan keeps earning reach for as long as loans exist; a reel about a thin
# news day is worth one day and then nothing.
WEAK_DAY_SCORE = 6.0


def _daily_beats(data: dict, story: Story) -> list[ReelBeat]:
    """Turn the model's beats into renderable ones.

    Every figure a counter beat would print is checked against the story text
    first. Bar *heights* are a soft claim about relative size, but a number set
    at 140px is a hard one in the most screenshot-able form this account
    produces, so an unverified figure loses its beat rather than its accuracy.
    """
    source_text = f"{story.title} {story.summary}"
    digits = set(_digits(source_text))
    sensitive = bool(getattr(story, "sensitive", False))

    # Which pose each beat holds. Rotated by position rather than authored, so
    # the character is doing something different on every cut without the model
    # having to think about it.
    poses = ("walk", "point", "present", "jump", "talk", "point", "cta")

    beats: list[ReelBeat] = []
    raw = data.get("beats", []) or []
    for index, item in enumerate(raw[:DAILY_BEATS]):
        caption = clamp_words(sanitize(str(item.get("caption", ""))), 120)
        if not caption:
            continue
        counter = item.get("counter")
        graphic, payload = "", {}
        if counter not in (None, "", "null"):
            raw_value = str(counter).replace(",", "").strip()
            if raw_value in digits:
                graphic, payload = "counter", {"value": raw_value}
            else:
                log.warning("reel: dropped unverified counter %r", counter)

        role = "hook" if index == 0 else (
            "outro" if index == len(raw[:DAILY_BEATS]) - 1 else
            ("graphic" if graphic else "point"))
        beats.append(ReelBeat(
            role=role,
            chapter=clamp_words(sanitize(str(item.get("chapter", ""))), 26),
            caption=caption,
            detail=clamp_words(sanitize(str(item.get("detail", ""))), 70),
            narration=clamp_words(sanitize(str(item.get("narration", ""))), 150),
            graphic=graphic, data=payload,
            pose="" if sensitive else poses[index % len(poses)],
            say="", plates=[]))
    return beats


def _place_plates(beats: list[ReelBeat], story: Story) -> None:
    """Give the picture a beat of its own, roughly a third of the way in.

    Not the hook: the opening two seconds decide whether anyone watches, and a
    plate sliding in competes with the line that has to land there. Not the
    sign-off either, which needs the room for the domain.
    """
    if getattr(story, "sensitive", False):
        # Sober template. Clear rather than merely decline to add: a plate set
        # anywhere upstream must not survive into a story about a disaster, and
        # a rule this important should not depend on every caller remembering it.
        for beat in beats:
            beat.plates = []
        return
    candidates = [i for i, b in enumerate(beats)
                  if b.role not in ("hook", "outro") and not b.graphic]
    if not candidates:
        return
    beats[candidates[len(candidates) // 3]].plates = ["story"]


def generate_daily(client: GeminiClient, digest: NewsDigest, day: date, *,
                   exclude_urls: set[str] | None = None) -> Reel | None:
    """The day's reel: the top story, or an evergreen lesson on a thin day."""
    story = lead_story(digest, exclude_urls=exclude_urls)
    if story is None or story.score < WEAK_DAY_SCORE:
        if story is not None:
            log.info("reel: top story scores %.2f, below the %.1f bar - "
                     "teaching an evergreen idea instead", story.score,
                     WEAK_DAY_SCORE)
        reel = generate_education(client, day)
        reel.slot = "reel_1"
        reel.dateline = _dateline(day)
        return reel

    data = client.generate_json(
        system=STYLE_GUIDE,
        prompt=reel_daily_prompt(stories_block([story]),
                                 hooks.hook_brief(day, "reel_1"),
                                 _agreement_line(story), DAILY_BEATS),
    )
    beats = _daily_beats(data, story)
    if len(beats) < 3:
        log.error("reel: model returned %d usable beats, too thin to publish",
                  len(beats))
        return None
    _place_plates(beats, story)

    reel = _assemble(slot="reel_1", kind="news", category=story.category,
                     title=clamp_words(sanitize(story.title), 90), data=data,
                     beats=beats, day=day, sources=source_line(story),
                     story_url=story.url)
    reel.dateline = _dateline(day)
    return reel


def _dateline(day: date) -> str:
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}".upper()


def _agreement_line(story: Story) -> str:
    from .instagram import agreement_line

    return agreement_line(story)
