"""Allocation, and the two ways a sensible-looking rule gets it wrong.

Both failure modes look like diligence, which is why they need tests rather than
comments. Spending only where returns are measured retires the channel carrying
most of the audience, because that channel has no link surface and therefore no
observable return. Spending where returns are highest defunds every compounding
asset, because none of them return anything on the day they are made.
"""

from __future__ import annotations

from headlinne.cmo import portfolio
from headlinne.cmo.portfolio import Channel


def test_every_compounding_name_is_a_real_channel_source():
    """Source names, not slot names. `listing` is the slot; `directory` is what
    it reports under, and a compounding entry matching no surface never
    resolves against anything on either side of the join."""
    from headlinne.cmo import attribution

    sources = {s.source for s in attribution.SURFACES.values()}
    for name in portfolio.COMPOUNDING:
        assert name in sources, name


def test_no_slot_name_is_mistaken_for_a_channel_name():
    """The class of bug, not the instance. Channels are named by source, and a
    slot name here silently matches nothing."""
    from headlinne.cmo import attribution

    slots = set(attribution.SURFACES)
    sources = {s.source for s in attribution.SURFACES.values()}
    for channel in portfolio.from_history():
        if channel.name in slots and channel.name not in sources:
            raise AssertionError(
                f"{channel.name} is a slot name being used as a channel name")


def _channels(**kwargs) -> list[Channel]:
    """instagram is unmeasurable, x and linkedin are clickable."""
    out = []
    for name in ("instagram", "x", "linkedin", "directory"):
        spec = kwargs.get(name, {})
        out.append(Channel(name=name, posts=spec.get("posts", 0),
                           signups=spec.get("signups")))
    return out


# --------------------------------------------------------------------------- #
# What a channel actually knows about itself
# --------------------------------------------------------------------------- #
def test_a_channel_with_no_link_surface_is_measurable_now():
    """It was not under the tag scheme, and that asymmetry was the whole
    problem: Instagram could never produce evidence, so it had to be specially
    protected from being scored zero. The day-contrast estimator reads signup
    timestamps, so a surface with no clickable link produces exactly the same
    kind of evidence as one with a link, and the special case is gone."""
    assert Channel("instagram").clickable is False        # still no link
    channel = Channel("instagram", posts=60, signups=48.0, estimated=True)
    assert channel.measured is True                       # measured anyway
    assert channel.status() == "estimated"
    assert channel.rate == 0.8


def test_a_channel_without_enough_posts_is_exploring_not_failing():
    channel = Channel("x", posts=3, signups=0.0)
    assert channel.measured is False
    assert channel.status() == "exploring"
    assert channel.rate is None            # not 0.0: we have not looked enough


def test_a_channel_becomes_measured_only_after_enough_posts():
    channel = Channel("x", posts=portfolio.CONFIDENCE_POSTS, signups=20)
    assert channel.measured is True
    assert channel.rate == 2.0


def test_an_unmeasured_channel_has_no_rate_even_with_flattering_early_numbers():
    """Three posts and nine signups is a rate of three. It is also noise."""
    assert Channel("x", posts=3, signups=9).rate is None


# --------------------------------------------------------------------------- #
# The blind channel is not a failed channel
# --------------------------------------------------------------------------- #
def test_a_channel_with_no_estimate_yet_is_never_retired_for_it():
    """The failure mode outlives the change of method. A returns-maximising
    allocator reads "no figure" as zero and defunds the surface carrying most
    of the audience. The reason is now "not enough contrast" rather than "no
    link", and it still must not be treated as failure."""
    channels = _channels(
        instagram={"posts": 90},                       # no estimate yet
        x={"posts": 60, "signups": 120},
        linkedin={"posts": 60, "signups": 30})
    allocation = portfolio.allocate(channels, slots=6)

    assert allocation.slots.get("instagram", 0) >= 1
    assert "exploring" in allocation.reasons["instagram"]


def test_the_best_measured_channel_does_not_take_the_whole_day():
    channels = _channels(
        instagram={"posts": 90},
        x={"posts": 60, "signups": 600},
        linkedin={"posts": 60, "signups": 6})
    allocation = portfolio.allocate(channels, slots=6)
    assert allocation.slots["x"] < 6
    assert allocation.slots.get("instagram", 0) >= 1


# --------------------------------------------------------------------------- #
# The compounding floor
# --------------------------------------------------------------------------- #
def test_compounding_work_is_funded_before_any_arithmetic_can_reach_it():
    """Every compounding asset returns nothing on the day it is made, so a
    portfolio judged daily always defunds it. The floor is taken off the top."""
    channels = _channels(x={"posts": 60, "signups": 6000})
    allocation = portfolio.allocate(channels, slots=6)
    assert allocation.slots.get("directory", 0) >= portfolio.COMPOUNDING_FLOOR
    assert "still earns after January" in allocation.reasons["directory"]


def test_the_floor_holds_even_when_everything_else_is_measured_and_winning():
    channels = [
        Channel("x", posts=100, signups=900),
        Channel("linkedin", posts=100, signups=800),
        Channel("directory", posts=0, signups=None),
    ]
    allocation = portfolio.allocate(channels, slots=4)
    assert allocation.slots.get("directory", 0) >= 1


def test_a_floor_of_zero_funds_nothing_compounding():
    """The floor is a policy, and turning it off has to actually turn it off."""
    channels = _channels(x={"posts": 60, "signups": 600})
    allocation = portfolio.allocate(channels, slots=4, floor=0)
    assert allocation.slots.get("directory", 0) == 0


# --------------------------------------------------------------------------- #
# The whole day is allocated
# --------------------------------------------------------------------------- #
def test_every_slot_is_given_to_something():
    for slots in (1, 3, 6, 10):
        allocation = portfolio.allocate(_channels(), slots=slots)
        assert allocation.total == slots, slots


def test_nothing_measured_holds_the_standing_mix():
    """Day one. No data anywhere, so the honest move is not to move anything."""
    allocation = portfolio.allocate(_channels(), slots=6)
    assert allocation.total == 6
    assert set(allocation.slots) <= {"instagram", "x", "linkedin", "directory"}


def test_measured_performance_orders_what_is_left_over():
    channels = [
        Channel("x", posts=50, signups=500),
        Channel("linkedin", posts=50, signups=50),
    ]
    allocation = portfolio.allocate(channels, slots=6, floor=0)
    assert allocation.slots["x"] > allocation.slots["linkedin"]
    assert "measured at" in allocation.reasons["x"]


# --------------------------------------------------------------------------- #
# Building the channel list from what was actually recorded
# --------------------------------------------------------------------------- #
def test_channels_are_unmeasured_until_a_source_breakdown_exists():
    """Attribution per channel needs a second read-only view the product does
    not serve yet. Until it does, every rate is None rather than invented."""
    channels = portfolio.from_history()
    assert channels
    assert all(c.signups is None for c in channels)
    assert all(not c.measured for c in channels)


def test_the_slots_collapse_into_the_channels_that_own_them():
    names = {c.name for c in portfolio.from_history()}
    assert "instagram" in names          # reel_1, instagram_1, story_card
    assert "x" in names                  # x_1, x_2
    assert "directory" in names          # the compounding floor needs a home


def test_an_estimate_is_used_when_one_arrives():
    channels = {c.name: c for c in portfolio.from_history(
        sources={"x": {"posts": 40, "estimated_signups": 80.0, "usable": 1}})}
    assert channels["x"].measured is True
    assert channels["x"].estimated is True
    assert channels["x"].rate == 2.0

    # A channel the estimator could not separate stays None, which reads as
    # exploring. It is never a zero: "we could not tell" and "it produced
    # nothing" are different claims and only one of them is evidence.
    assert channels["linkedin"].signups is None
    assert channels["linkedin"].status() == "exploring"


def test_an_unusable_estimate_is_not_credited():
    """`lift.by_channel` marks weak and confounded slots unusable. A row that
    arrives carrying a figure but no usable slot behind it must not become a
    rate the allocator then divides by."""
    channels = {c.name: c for c in portfolio.from_history(
        sources={"x": {"posts": 40, "estimated_signups": 900.0, "usable": 0}})}
    assert channels["x"].signups is None
    assert channels["x"].status() == "exploring"


def test_the_report_says_what_could_not_be_judged_yet():
    channels = portfolio.from_history()
    allocation = portfolio.allocate(channels)
    text = portfolio.report(channels, allocation)
    assert "Too little contrast to judge yet" in text
    assert "instagram" in text
