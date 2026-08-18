"""The source strip: how many outlets reported this, and whether they agree.

One number decides whether this component builds trust or destroys it, and it is
the denominator.

"4 of 32" would be a lie by framing. Thirty-two is how many feeds we read, not
how many covered the story - the other twenty-eight never wrote about it, so
counting them as absent agreement invents a disagreement that never happened.

The arithmetic lives on models.Agreement, which news.corroborate fills in. This
module is only its presentation: which outlets to name, how many ticks to draw,
and which of the four states the strip is in. See models.Agreement for why
silence is never drawn as dissent.

The strip is never padded to look stronger. A single-source story renders as one
outlined tick and says so, and we do not publish it; the moment a thin bar is
dressed up as a thick one, every thick bar stops meaning anything.
"""

from __future__ import annotations

from ..models import Agreement, Story

# Above this the ticks stop being countable at a glance and become texture, so
# the overflow is stated in words instead.
MAX_TICKS = 8

# What the kicker says, per state. These are the words in the approved samples.
EYEBROW = {
    "unanimous": "YOUR BRIEF",
    "developing": "DEVELOPING",
    "disputed": "SOURCES DISAGREE",
    "single": "SINGLE SOURCE",
}

# Which semantic tone the masthead rule takes. A reader learns the shape of a
# story from the colour of the rule before reading a word of it.
TONE = {
    "unanimous": "TONE_LIVE",
    "developing": "BRAND_TERRACOTTA",
    "disputed": "TONE_DISPUTE",
    "single": "TONE_DISPUTE",
}

# And which pose Pip takes. Sensitive stories override all of this with None -
# see theme.pose_for.
POSE = {
    "unanimous": "verified",
    "developing": "read",
    "disputed": "puzzled",
    "single": "puzzled",
}


def agreement_of(story: Story) -> Agreement:
    """The story's agreement record, or an honest empty one.

    A story that never went through corroboration reports as single-source
    rather than as unanimous, because "we did not check" and "everyone agrees"
    must never render the same way.
    """
    record = getattr(story, "agreement", None)
    if record is None or record.reported == 0:
        return Agreement(reported=1, agree=1, outlets=[story.source])
    return record


def outlets(story: Story) -> list[str]:
    """Every independent outlet that reported this event, the original first."""
    record = agreement_of(story)
    if record.outlets:
        return list(record.outlets)
    names = [story.source]
    names.extend(n for n in story.corroborating_sources if n and n != story.source)
    seen, unique = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def label(story: Story) -> str:
    """The line printed under the strip."""
    return agreement_of(story).label()


def short_label(story: Story) -> str:
    """The reel's tighter form. Vertical video has less room for furniture."""
    record = agreement_of(story)
    if record.reported <= 1:
        return "Single source"
    if record.state == "developing":
        return f"{record.agree} sources agree"
    denominator = record.reported if record.state == "unanimous" else record.eligible
    return f"{record.agree} of {denominator} agree"


def named(story: Story, limit: int = 3) -> str:
    """The outlets to print, most authoritative first, with an honest overflow."""
    names = outlets(story)
    if not names:
        return ""
    if len(names) <= limit:
        return " · ".join(names)
    return " · ".join(names[:limit]) + f" +{len(names) - limit}"


def ticks(story: Story) -> tuple[int, int]:
    """(filled, outlined) marks to draw, clamped to what reads at a glance."""
    filled, hollow = agreement_of(story).ticks()
    if filled + hollow <= MAX_TICKS:
        return filled, hollow
    # Preserve the proportion rather than truncating the hollow ones away: the
    # disagreement is the part a reader most needs to see.
    total = filled + hollow
    kept_filled = max(1, round(MAX_TICKS * filled / total))
    return kept_filled, MAX_TICKS - kept_filled


def overflow(story: Story) -> int:
    """Outlets beyond what the strip can show, for the "+N" suffix."""
    return max(0, len(outlets(story)) - MAX_TICKS)


def state(story: Story) -> str:
    return agreement_of(story).state


def eyebrow(story: Story) -> str:
    return EYEBROW[state(story)]


def publishable(story: Story) -> bool:
    """Two independent outlets is the bar. A gate, not a penalty."""
    return agreement_of(story).publishable
