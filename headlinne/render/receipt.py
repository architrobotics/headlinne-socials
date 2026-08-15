"""The source strip: how many outlets reported this, drawn honestly.

One number decides whether this component builds trust or destroys it, and it is
the denominator.

"4 of 32" would be a lie by framing. Thirty-two is how many feeds we read, not
how many covered the story - the other twenty-eight never wrote about it, so
counting them as absent agreement invents a disagreement that never happened. It
also reads as weak coverage for a story that four independent outlets confirmed.

The denominator is therefore always the number of outlets that reported this
event. When all of them agree, and agreement is all this pipeline can currently
detect, the honest statement is "5 outlets reported this" - stated as a count
rather than a fraction, because a fraction implies a dissenting remainder that
we have not measured.

The strip is never padded to look stronger. A single-source story renders as one
outlined tick and says so, and we publish it that way; the moment a thin bar is
dressed up as a thick one, every thick bar stops meaning anything.
"""

from __future__ import annotations

from ..models import Story

# Above this the ticks stop being countable at a glance and become texture, so
# the overflow is stated in words instead.
MAX_TICKS = 8


def outlets(story: Story) -> list[str]:
    """Every outlet that reported this event, the original first."""
    names = [story.source]
    names.extend(n for n in story.corroborating_sources if n and n != story.source)
    seen, unique = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def label(story: Story) -> str:
    """The line printed under the strip.

    A count, never a fraction against the size of our feed list.
    """
    n = len(outlets(story))
    if n <= 1:
        return "Single source · not yet corroborated"
    return f"{n} outlets reported this"


def named(story: Story, limit: int = 3) -> str:
    """The outlets to print, most authoritative first, with an honest overflow."""
    names = outlets(story)
    if len(names) <= limit:
        return " · ".join(names)
    return " · ".join(names[:limit]) + f" +{len(names) - limit}"


def ticks(story: Story) -> tuple[int, int]:
    """(filled, outlined) marks to draw.

    A corroborated story fills one tick per outlet. A single-source story draws
    exactly one outlined tick - visibly thin, which is the point.
    """
    n = len(outlets(story))
    if n <= 1:
        return 0, 1
    return min(n, MAX_TICKS), 0


def overflow(story: Story) -> int:
    """Outlets beyond what the strip can show, for the "+N" suffix."""
    return max(0, len(outlets(story)) - MAX_TICKS)
