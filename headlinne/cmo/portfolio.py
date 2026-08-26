"""Where the next unit of effort goes.

With no budget, the currency is not money, it is **slots**: the finite number of
things that can be made and published in a day. Allocating them is the CMO's one
genuinely strategic act, and it is the act most likely to go wrong quietly,
because the obvious rule - spend where the returns are - has two failure modes
that both look like diligence.

**Spending only where returns are measured means never leaving the surfaces you
can see.** Three of the four things this pipeline makes go to Instagram, where
`attribution` shows there is no clickable link and therefore no observable
return at all. A returns-maximising allocator reads that as zero, retires the
channel that carries most of the audience, and is confidently wrong. So an
unmeasured channel is never treated as a failed one: it gets exploration slots
and is reported as unmeasured, which is a different claim from unsuccessful.

**Spending where returns are highest means never building anything.** Every
compounding asset - a listing that stays up, an article that keeps ranking, an
archive page - returns nothing on the day it is made, so a portfolio judged
daily will always defund it in favour of another post. That is how a four month
sprint arrives in January with nothing that outlives it. `COMPOUNDING_FLOOR`
reserves slots that the daily arithmetic is not allowed to reach.

Everything here allocates. Nothing here publishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..logging_setup import get_logger
from . import attribution

log = get_logger("cmo.portfolio")

# The day's shape, as the pipeline currently runs it. Slots, not posts: a slot
# is one thing made and published on one surface.
DEFAULT_SLOTS = ("reel_1", "instagram_1", "story_card", "x_1", "x_2", "linkedin")

# Channels that keep earning after the day they were made. The floor is a
# minimum number of slots a day that must go to one of these, whatever the
# measured returns say, because their returns arrive after the deadline the
# measurement is optimising for.
#
# These are **source** names from `attribution.SURFACES`, not slot names. The
# distinction has bitten this module twice: a channel called "listing" looks
# right and is wrong, because the slot is `listing` while the source it reports
# under is `directory` - so it matched nothing, reported blind, and would have
# been funded as an unmeasurable channel forever. `test_cmo_portfolio` asserts
# every name here is a real source, which is the guard rather than this comment.
#
# "archive" is deliberately absent. The story archive does not exist yet, and a
# floor reserved for a channel that cannot be published to is a slot thrown away
# every day rather than an investment.
COMPOUNDING = ("directory", "devto", "hashnode")
COMPOUNDING_FLOOR = 1

# A channel with no measurement gets this many slots before anyone is entitled
# to an opinion about it. Below this, "it did not work" means "we did not look".
EXPLORATION_SLOTS = 1

# How many posts a channel needs before its measured rate is used for anything.
# Under this it is still exploring, however good the early numbers look.
CONFIDENCE_POSTS = 10


@dataclass
class Channel:
    """One surface, and what is actually known about it."""

    name: str
    posts: int = 0                  # posts made, from the ledger
    signups: int | None = None      # signups attributed. None means unmeasured

    @property
    def measurable(self) -> bool:
        """Can this channel's contribution be observed at all?

        Matched on the *source*, not the slot. A channel here is "instagram" or
        "x", while `attribution.SURFACES` is keyed by slot - `x_1`, `reel_1`.
        Looking it up by slot name silently returns None for every channel, and
        None reads as unmeasurable, so every channel would have been reported
        blind and the whole allocation would have collapsed into exploration.
        """
        return any(s.link is attribution.Link.CLICKABLE
                   for s in attribution.SURFACES.values()
                   if s.source == self.name)

    @property
    def measured(self) -> bool:
        """Enough posts, a reading, and a surface a reading could come from.

        `measurable` is part of the test and not a redundant one. An
        unmeasurable channel is absent from the attribution view by
        construction, so without this it reads as a measured zero, earns a rate
        of 0.00, and joins the performance allocation as the worst earner - the
        precise conclusion this module exists to refuse.
        """
        return (self.measurable and self.signups is not None
                and self.posts >= CONFIDENCE_POSTS)

    @property
    def rate(self) -> float | None:
        """Signups per post. None when there is nothing honest to divide."""
        if not self.measured or not self.posts:
            return None
        return self.signups / self.posts

    @property
    def compounding(self) -> bool:
        return self.name in COMPOUNDING

    def status(self) -> str:
        if not self.measurable:
            return "blind"          # no link surface. Cannot ever be measured
        if not self.measured:
            return "exploring"      # measurable, not yet enough data
        return "measured"


@dataclass
class Allocation:
    slots: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.slots.values())

    def explain(self) -> list[str]:
        return [f"{name}: {self.slots[name]} - {self.reasons.get(name, '')}"
                for name in sorted(self.slots, key=lambda n: -self.slots[n])]


def allocate(channels: list[Channel], *, slots: int = len(DEFAULT_SLOTS),
             floor: int = COMPOUNDING_FLOOR) -> Allocation:
    """Divide the day's slots. Returns where known, exploration where not.

    The order is deliberate and it is the argument: the compounding floor is
    taken off the top before any measured channel can bid for it, then blind and
    exploring channels take their minimum, and only what is left is allocated on
    performance. A rule that let the best measured channel bid first would take
    everything, every day, and be right about today every time.
    """
    out = Allocation()
    remaining = slots

    # 1. The floor, first, before any arithmetic can reach it.
    compounding = [c for c in channels if c.compounding]
    if compounding and floor > 0 and remaining > 0:
        take = min(floor, remaining)
        # Spread across the compounding channels rather than concentrating.
        for i in range(take):
            channel = compounding[i % len(compounding)]
            out.slots[channel.name] = out.slots.get(channel.name, 0) + 1
            out.reasons[channel.name] = (
                "reserved: it still earns after January, and a portfolio judged "
                "daily would never fund it")
        remaining -= take

    # 2. Channels nobody can measure. They keep a minimum, because "no data" is
    #    not "no result" - and on this account they carry most of the audience.
    for channel in channels:
        if channel.compounding or remaining <= 0:
            continue
        if not channel.measurable:
            out.slots[channel.name] = out.slots.get(channel.name, 0) + 1
            out.reasons[channel.name] = (
                "unmeasurable, not unsuccessful: no clickable link exists on "
                "this surface, so its contribution cannot be observed")
            remaining -= 1

    # 3. Measurable channels that have not been looked at long enough yet.
    for channel in channels:
        if channel.compounding or remaining <= 0:
            continue
        if channel.measurable and not channel.measured:
            take = min(EXPLORATION_SLOTS, remaining)
            out.slots[channel.name] = out.slots.get(channel.name, 0) + take
            out.reasons[channel.name] = (
                f"exploring: {channel.posts} posts so far, "
                f"{CONFIDENCE_POSTS} needed before its rate means anything")
            remaining -= take

    # 4. What is left goes on measured performance, in proportion to it.
    #
    # Proportion, not a round robin. Handing the earners one slot each in turn
    # produces an even split however far apart their rates are, which is not an
    # allocation - it is the standing mix with a performance-flavoured comment
    # attached, and it would have read as working.
    #
    # Every measured channel still keeps one slot while there are slots to keep.
    # A channel cut to zero stops producing evidence, so its rate freezes at
    # whatever it was on the day it fell out of favour and nothing can ever
    # argue for its return. That is a self-fulfilling prophecy, not a decision.
    earners = sorted((c for c in channels if c.measured and not c.compounding),
                     key=lambda c: c.rate or 0, reverse=True)
    if earners and remaining > 0:
        def note(channel):
            return (f"measured at {channel.rate:.2f} signups a post across "
                    f"{channel.posts} posts")

        keep = min(len(earners), remaining)
        for channel in earners[:keep]:
            out.slots[channel.name] = out.slots.get(channel.name, 0) + 1
            out.reasons[channel.name] = note(channel)
        remaining -= keep

        total_rate = sum(c.rate or 0 for c in earners)
        if remaining > 0 and total_rate > 0:
            # Largest remainder, so proportions do not lose slots to rounding.
            exact = [(c, remaining * (c.rate or 0) / total_rate) for c in earners]
            for channel, want in exact:
                take = int(want)
                if take:
                    out.slots[channel.name] = out.slots.get(channel.name, 0) + take
                    out.reasons[channel.name] = note(channel)
                    remaining -= take
            for channel, want in sorted(exact, key=lambda cw: cw[1] % 1,
                                        reverse=True):
                if remaining <= 0:
                    break
                out.slots[channel.name] = out.slots.get(channel.name, 0) + 1
                out.reasons[channel.name] = note(channel)
                remaining -= 1

    # 5. Nothing measured and nothing left to explore: keep the day as it runs.
    #    This cycles rather than making one pass. A single pass hands out at
    #    most one slot per channel and silently drops the rest, so a day with
    #    more slots than channels would allocate seven of ten and report a total
    #    that does not match the day it was asked to fill.
    spare = [c for c in channels if not c.compounding] or channels
    while remaining > 0 and spare:
        for channel in spare:
            if remaining <= 0:
                break
            out.slots[channel.name] = out.slots.get(channel.name, 0) + 1
            out.reasons.setdefault(
                channel.name, "held at the standing mix: nothing measured yet "
                              "argues for moving it")
            remaining -= 1

    return out


def posts_by_channel(days: int = 30, **kwargs) -> dict[str, int]:
    """How many posts each channel actually carried, from the committed record.

    This half of the rate comes from us, not from the product. `content/<date>/
    published/*.json` is what the pipeline wrote when a slot went out, so it is
    the same evidence `headlinne status` reports distribution from, and it stays
    correct when the product is unreachable.

    Counting posts from the product's side would be the obvious alternative and
    it is not available: the attribution view knows how many people arrived from
    a ref, not how many times we published to that surface. Dividing signups by
    a post count we did not observe would be dividing by an assumption.
    """
    from .. import health

    report = health.scan(days=days, **kwargs)
    counts: dict[str, int] = {}
    for slot, n in report.coverage().items():
        surface = attribution.SURFACES.get(slot)
        name = surface.source if surface else slot
        counts[name] = counts.get(name, 0) + n
    return counts


def from_history(slots=DEFAULT_SLOTS, sources: dict[str, dict] | None = None,
                 *, days: int = 30, posts: dict[str, int] | None = None,
                 ledger_path=None, today=None) -> list[Channel]:
    """Build the channel list by joining what we published to what arrived.

    Posts come from the committed content folder; signups come from the
    attribution ledger. Either half can be missing and the result is still
    honest - a channel with posts and no signup reading is *unmeasured*, not a
    channel that produced nothing.

    `sources` overrides the ledger, which is what the tests use and what a
    caller with a fresher reading in hand should pass.
    """
    from . import ledger

    if sources is None:
        sources = ledger.signups_by_channel(path=ledger_path, today=today)
    measured = sources is not None
    sources = sources or {}
    if posts is None:
        try:
            posts = posts_by_channel(days=days)
        except Exception as exc:  # noqa: BLE001 - an unreadable folder is unknown
            log.warning("could not count published posts: %s", exc)
            posts = {}

    names: list[str] = []
    for slot in slots:
        surface = attribution.SURFACES.get(slot)
        name = surface.source if surface else slot
        if name not in names:
            names.append(name)
    for name in COMPOUNDING:
        if name not in names:
            names.append(name)

    out = []
    for name in names:
        row = sources.get(name) or {}
        # A reading exists and this channel is not in it: that is a measured
        # zero, not an unknown. A reading that has never been taken leaves every
        # channel at None.
        channel = Channel(name=name,
                          posts=int(row.get("posts") or posts.get(name, 0)))
        if "signups" in row:
            channel.signups = int(row["signups"])
        elif measured and channel.measurable:
            # A reading exists and this channel is not in it: the view returns a
            # row per ref that has signups, so absence really is zero.
            #
            # Only for a channel a ref could have come from. An unmeasurable one
            # is absent from every reading that will ever be taken, and calling
            # that zero would turn "we cannot see it" into "it produced
            # nothing" - which is the sentence that retires the surface carrying
            # most of the audience.
            channel.signups = 0
        out.append(channel)
    return out


def report(channels: list[Channel], allocation: Allocation) -> str:
    """What was decided and, more usefully, what could not be."""
    lines = ["Channel          status      posts  signups  slots"]
    by_name = {c.name: c for c in channels}
    for name in sorted(allocation.slots, key=lambda n: -allocation.slots[n]):
        c = by_name.get(name) or Channel(name)
        signups = "-" if c.signups is None else f"{c.signups}"
        lines.append(f"  {name:14} {c.status():10} {c.posts:5}  {signups:>7}  "
                     f"{allocation.slots[name]:5}")
    blind = [c.name for c in channels if not c.measurable]
    if blind:
        lines.append("")
        lines.append(f"{len(blind)} channel(s) cannot be measured at all "
                     f"({', '.join(blind)}). No allocation on this account is "
                     f"evidence-based until a link surface exists there.")
    return "\n".join(lines)
