"""Where the next unit of effort goes.

With no budget, the currency is not money, it is **slots**: the finite number of
things that can be made and published in a day. Allocating them is the CMO's one
genuinely strategic act, and it is the act most likely to go wrong quietly,
because the obvious rule - spend where the returns are - has two failure modes
that both look like diligence.

**Spending only where returns are measured means never leaving the surfaces you
can see.** This used to be acute: three of the four things the pipeline makes go
to Instagram, which carries no clickable link, so a tag-based scheme could never
have observed them and a returns-maximising allocator would have read that
silence as zero and retired the channel carrying most of the audience.
`cmo/lift.py` removed the trap at its source by reading signup timestamps
against the days a slot ran, which works the same whether or not a reader could
tap anything. What survives is the weaker version of the same rule: a channel
with too little contrast to judge is *exploring*, never *failed*, and it keeps a
minimum until there is enough evidence to say otherwise.

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
    posts: int = 0                  # posts made, from the committed record
    signups: float | None = None    # signups credited. None means we cannot tell
    # True when `signups` came from the day-contrast estimator rather than from
    # anything recorded at signup. Carried all the way to the report, because
    # "estimated" is the difference between a number worth allocating on and a
    # number worth quoting, and dropping the word is how the second becomes the
    # first.
    estimated: bool = False

    @property
    def clickable(self) -> bool:
        """Whether this channel can carry a tagged link at all.

        No longer gates measurement. When attribution depended on a tag, an
        Instagram channel was unmeasurable by construction and had to be
        protected from being scored zero. The day-contrast estimator does not
        care whether a reader could tap anything - it reads signup timestamps
        against the days a slot ran - so Instagram is now measured on the same
        footing as everything else. This survives only to explain a link in a
        post, which is a different question from what a channel is worth.

        Matched on the *source*, not the slot: a channel here is "instagram",
        while `attribution.SURFACES` is keyed by slot - `reel_1`.
        """
        return any(s.link is attribution.Link.CLICKABLE
                   for s in attribution.SURFACES.values()
                   if s.source == self.name)

    @property
    def measured(self) -> bool:
        """Enough posts, and a figure that came from somewhere.

        No longer conditioned on the channel being clickable. Under the tag
        scheme an Instagram channel was absent from every reading by
        construction, so it had to be excluded here or it read as a measured
        zero and joined the performance allocation as the worst earner. The
        day-contrast estimator removes that trap at the source: a channel with
        no link surface produces exactly the same kind of evidence as one with
        a link, so the special case is gone rather than merely handled.
        """
        return self.signups is not None and self.posts >= CONFIDENCE_POSTS

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
        if not self.measured:
            return "exploring"      # not enough contrast to tell yet
        return "estimated" if self.estimated else "measured"


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

    # 2. Channels there is not yet enough contrast to judge.
    #
    # This used to be two rules: one for channels no tag could ever reach, and
    # one for channels not yet posted to enough. The estimator collapsed them.
    # It reads signup timestamps against the days a slot ran, so a surface with
    # no clickable link is now judged on the same evidence as every other -
    # which is the whole reason for preferring it to a tagging scheme.
    for channel in channels:
        if channel.compounding or remaining <= 0:
            continue
        if not channel.measured:
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
    from . import ledger, lift

    if sources is None:
        signups = ledger.signups_by_day(path=ledger_path)
        if signups:
            sources = lift.by_channel(
                lift.estimate(signups, lift.published_by_day(days=days)))
        else:
            sources = None
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
        channel = Channel(name=name,
                          posts=int(row.get("posts") or posts.get(name, 0)))
        # An estimate arrives only for a channel the estimator could separate.
        # A channel it could not - too few days of contrast, or a schedule
        # identical to another slot's - is left at None, which reads as
        # "exploring" rather than as a zero. That distinction is the same one
        # the tag scheme needed and it is now earned by the evidence rather
        # than by a special case for surfaces without links.
        if "estimated_signups" in row and row.get("usable"):
            channel.signups = float(row["estimated_signups"])
            channel.estimated = True
        elif "signups" in row:
            channel.signups = float(row["signups"])
        out.append(channel)
    return out


def report(channels: list[Channel], allocation: Allocation) -> str:
    """What was decided, and how much of it rests on an estimate."""
    lines = ["Channel          status      posts  signups   per post  slots"]
    by_name = {c.name: c for c in channels}
    for name in sorted(allocation.slots, key=lambda n: -allocation.slots[n]):
        c = by_name.get(name) or Channel(name)
        signups = "-" if c.signups is None else f"{c.signups:,.0f}"
        rate = f"{c.rate:.2f}" if c.rate is not None else "-"
        lines.append(f"  {name:14} {c.status():10} {c.posts:5}  {signups:>7}  "
                     f"{rate:>9}  {allocation.slots[name]:5}")

    estimated = [c.name for c in channels if c.estimated and c.measured]
    exploring = [c.name for c in channels if not c.measured]
    lines.append("")
    if estimated:
        lines.append(
            f"Estimated, not measured ({', '.join(estimated)}): the figure is "
            f"the difference between days the slot ran and days it did not. "
            f"An association, not a cause - a slot that runs on big-news days "
            f"inherits the news.")
    if exploring:
        lines.append(
            f"Too little contrast to judge yet ({', '.join(exploring)}).")
    if not estimated and not exploring:
        lines.append("Nothing here is measured yet.")
    return "\n".join(lines)
