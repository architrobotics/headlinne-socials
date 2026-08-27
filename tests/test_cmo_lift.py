"""Estimating what a slot is worth, without recording anything at signup.

The scheme this replaced needed the product to store a `ref` when a user signed
up, which is a change to the auth path - the one piece of code that must not be
touched for a growth experiment's convenience. Nothing is recorded now. The
estimate comes from two things that already exist: signup timestamps, and the
committed record of which slots published on which day.

Three properties matter, and two of them are refusals.

**It finds a real effect.** A slot genuinely worth six signups a day should come
back at roughly six, or the whole thing is decoration.

**It refuses when it cannot tell.** A slot that ran every single day has no
comparison. A slot whose schedule matches another's has an effect that is one
effect wearing two names. Volumes too small to split are noise. Each of those
returns no estimate rather than a number with a caveat nobody will read.

**It never loses the word "estimate".** This is correlational: a slot that runs
on big-news days inherits the news. The word has to survive all the way to the
report, because dropping it is how an association becomes a fact.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from headlinne.cmo import lift, portfolio
from headlinne.cmo.lift import Estimate

START = date(2026, 9, 1)


def _world(days: int = 90, *, effects: dict[str, float],
           schedule, base: float = 10.0, noise: float = 2.0, seed: int = 7):
    """Build a synthetic campaign with known per-slot effects."""
    random.seed(seed)
    signups: dict[date, int] = {}
    published: dict[date, set[str]] = {}
    for i in range(days):
        day = START + timedelta(days=i)
        slots = schedule(i)
        published[day] = set(slots)
        value = base + random.gauss(0, noise)
        value += sum(effects.get(s, 0.0) for s in slots)
        signups[day] = max(0, round(value))
    return signups, published


# --------------------------------------------------------------------------- #
# It finds a real effect
# --------------------------------------------------------------------------- #
def test_a_real_effect_is_recovered():
    signups, published = _world(
        effects={"reel_1": 6.0},
        schedule=lambda i: ({"reel_1"} if i % 3 == 0 else set()) | {"x_1"})
    est = lift.estimate(signups, published, slots=["reel_1"])["reel_1"]

    assert est.confidence == "usable"
    assert 4.5 < est.lift < 7.5           # true effect is 6
    assert est.days_with > 0 and est.days_without > 0


def test_a_slot_worth_nothing_is_not_reported_as_worth_something():
    signups, published = _world(
        effects={},                        # story_card does nothing at all
        schedule=lambda i: {"story_card"} if i % 2 == 0 else set())
    est = lift.estimate(signups, published, slots=["story_card"])["story_card"]
    assert est.usable is False
    assert est.confidence == "weak"


def test_instagram_is_measured_despite_carrying_no_clickable_link():
    """The reason to prefer this over any tagging scheme. Three of the four
    things this pipeline makes go to surfaces where no tag could ever resolve;
    a signup timestamp does not care whether the reader could tap anything."""
    from headlinne.cmo import attribution

    assert attribution.for_slot(START, "reel_1") is None      # untaggable
    signups, published = _world(
        effects={"reel_1": 7.0},
        schedule=lambda i: {"reel_1"} if i % 3 == 0 else set())
    est = lift.estimate(signups, published, slots=["reel_1"])["reel_1"]
    assert est.usable is True


# --------------------------------------------------------------------------- #
# It refuses when it cannot tell
# --------------------------------------------------------------------------- #
def test_a_slot_that_runs_every_day_has_nothing_to_compare_against():
    signups, published = _world(effects={}, schedule=lambda i: {"x_1"})
    est = lift.estimate(signups, published, slots=["x_1"])["x_1"]
    assert est.lift is None
    assert est.confidence == "none"
    assert "no day without it" in est.caveat


def test_a_slot_that_never_ran_is_reported_as_never_ran():
    signups, published = _world(effects={}, schedule=lambda i: {"x_1"})
    est = lift.estimate(signups, published, slots=["reel_2"])["reel_2"]
    assert est.lift is None
    assert "never published" in est.caveat


def test_too_few_days_of_contrast_gives_no_estimate():
    signups, published = _world(
        days=40, effects={"reel_1": 9.0},
        schedule=lambda i: {"reel_1"} if i < 3 else set())    # 3 days only
    est = lift.estimate(signups, published, slots=["reel_1"])["reel_1"]
    assert est.lift is None
    assert f"{lift.MIN_CONTRAST_DAYS} of each" in est.caveat


def test_too_few_signups_makes_every_split_noise():
    """At ten signups a fortnight every slot looks decisive and none is."""
    signups, published = _world(
        days=30, effects={"reel_1": 1.0}, base=0.3, noise=0.2,
        schedule=lambda i: {"reel_1"} if i % 2 == 0 else set())
    est = lift.estimate(signups, published, slots=["reel_1"])["reel_1"]
    assert est.lift is None
    assert "noise" in est.caveat


def test_slots_that_always_run_together_cannot_be_separated():
    """Their effect is one effect wearing two names, and no amount of data of
    this kind can split it."""
    signups, published = _world(
        effects={"reel_1": 7.0},
        schedule=lambda i: {"reel_1", "instagram_1"} if i % 3 == 0 else set())
    est = lift.estimate(signups, published, slots=["reel_1", "instagram_1"])

    assert est["reel_1"].confidence == "confounded"
    assert est["instagram_1"].confidence == "confounded"
    assert est["reel_1"].confounded_with == ["instagram_1"]
    assert est["reel_1"].usable is False
    assert "cannot be told apart" in est["reel_1"].caveat


def test_slots_on_genuinely_different_schedules_are_not_called_confounded():
    signups, published = _world(
        effects={"reel_1": 6.0},
        schedule=lambda i: ({"reel_1"} if i % 3 == 0 else set())
                           | ({"instagram_1"} if i % 2 == 0 else set()))
    est = lift.estimate(signups, published, slots=["reel_1", "instagram_1"])
    assert est["reel_1"].confounded_with == []


def test_no_overlapping_days_gives_no_estimate_at_all():
    est = lift.estimate({}, {}, slots=["reel_1"])["reel_1"]
    assert est.lift is None
    assert "no day has both" in est.caveat


# --------------------------------------------------------------------------- #
# The word "estimate" survives
# --------------------------------------------------------------------------- #
def test_a_usable_estimate_still_says_it_is_not_a_cause():
    signups, published = _world(
        effects={"reel_1": 8.0},
        schedule=lambda i: {"reel_1"} if i % 3 == 0 else set())
    est = lift.estimate(signups, published, slots=["reel_1"])["reel_1"]
    assert est.usable
    assert "not a cause" in est.caveat
    assert "inherits the news" in est.caveat


def test_the_printed_table_labels_everything_as_an_estimate():
    signups, published = _world(
        effects={"reel_1": 8.0},
        schedule=lambda i: {"reel_1"} if i % 3 == 0 else set())
    text = lift.format_estimates(
        lift.estimate(signups, published, slots=["reel_1", "x_1"]))
    assert "estimate" in text.lower()
    assert "association, not a cause" in text


def test_only_usable_estimates_reach_the_portfolio():
    """A weak or confounded slot contributes nothing rather than a number with
    a shrug attached, because the allocator divides by these."""
    signups, published = _world(
        effects={"reel_1": 8.0},
        schedule=lambda i: {"reel_1", "instagram_1"} if i % 3 == 0 else set())
    rolled = lift.by_channel(
        lift.estimate(signups, published, slots=["reel_1", "instagram_1"]))
    assert rolled["instagram"]["estimated_signups"] == 0.0
    assert rolled["instagram"]["usable"] == 0


def test_a_channel_carrying_a_usable_estimate_is_marked_estimated():
    signups, published = _world(
        effects={"x_1": 8.0},
        schedule=lambda i: ({"x_1"} if i % 3 == 0 else set()) | {"linkedin"})
    rolled = lift.by_channel(lift.estimate(signups, published,
                                           slots=["x_1", "linkedin"]))
    channels = {c.name: c for c in portfolio.from_history(
        sources=rolled, posts={"x": 30, "linkedin": 90})}

    assert channels["x"].estimated is True
    assert channels["x"].status() == "estimated"
    assert channels["linkedin"].signups is None        # no contrast to judge
    assert channels["linkedin"].status() == "exploring"


def test_the_channel_report_says_which_figures_are_estimates():
    signups, published = _world(
        effects={"x_1": 8.0},
        schedule=lambda i: ({"x_1"} if i % 3 == 0 else set()) | {"linkedin"})
    rolled = lift.by_channel(lift.estimate(signups, published,
                                           slots=["x_1", "linkedin"]))
    channels = portfolio.from_history(sources=rolled,
                                      posts={"x": 30, "linkedin": 90})
    text = portfolio.report(channels, portfolio.allocate(channels))
    assert "Estimated, not measured" in text
    assert "association, not a cause" in text


# --------------------------------------------------------------------------- #
# Hours roll up in IST, because the schedule is IST
# --------------------------------------------------------------------------- #
def test_hours_are_bucketed_into_ist_days():
    """The story card fires at 21:30 IST, which is 16:00 UTC. Rolling up in UTC
    would put its whole effect on the right day and the late-evening tail on the
    wrong one - and that slot is exactly what this is trying to read."""
    class _B:
        def __init__(self, iso, n):
            self.hour, self.signups = datetime.fromisoformat(iso), n

    days = lift.daily_signups([
        _B("2026-09-14T16:00:00+00:00", 3),   # 21:30 IST on the 14th
        _B("2026-09-14T19:00:00+00:00", 5),   # 00:30 IST on the 15th
        _B("2026-09-14T05:00:00+00:00", 2),   # 10:30 IST on the 14th
    ])
    assert days[date(2026, 9, 14)] == 5
    assert days[date(2026, 9, 15)] == 5


def test_a_naive_timestamp_is_treated_as_utc_rather_than_local():
    class _B:
        def __init__(self, iso, n):
            self.hour, self.signups = datetime.fromisoformat(iso), n

    days = lift.daily_signups([_B("2026-09-14T19:00:00", 4)])
    assert days == {date(2026, 9, 15): 4}


def test_published_days_come_from_the_committed_record():
    by_day = lift.published_by_day(days=30)
    assert by_day
    assert all(isinstance(v, set) for v in by_day.values())
