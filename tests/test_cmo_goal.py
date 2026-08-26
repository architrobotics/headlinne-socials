"""The arithmetic behind 10,000 users by 1 January 2027.

These pin the two properties that make the pace report an alarm rather than a
wall poster: the required pace has to *climb* when the plan falls behind, and
growth in the headline number has to be called hollow when the people being
counted stop coming back. Both are easy to write in a way that quietly always
reads "fine", which is the failure mode worth testing for.
"""

from __future__ import annotations

from datetime import date

from headlinne.cmo.goal import (DEADLINE, START, TARGET, Goal, Pace,
                                required_weekly_growth)


def _pace(day, users, *, baseline=0, mau=0, baseline_activation=None,
          recent=None) -> Pace:
    return Pace(goal=Goal(), today=day, users=users, baseline=baseline,
                mau=mau, baseline_activation=baseline_activation,
                recent_per_day=recent)


# --------------------------------------------------------------------------- #
# The clock
# --------------------------------------------------------------------------- #
def test_the_window_is_september_to_january():
    goal = Goal()
    assert (goal.start, goal.deadline, goal.target) == (START, DEADLINE, TARGET)
    assert goal.total_days == 122


def test_the_clock_does_not_run_before_the_start_or_past_the_deadline():
    goal = Goal()
    assert goal.days_elapsed(date(2026, 8, 15)) == 0      # before the window
    assert goal.days_elapsed(date(2027, 3, 1)) == 122     # clamped at the end
    assert goal.days_remaining(date(2027, 3, 1)) == 0     # never negative


# --------------------------------------------------------------------------- #
# The pace has to climb when you fall behind
# --------------------------------------------------------------------------- #
def test_day_one_needs_the_flat_rate():
    p = _pace(START, users=0)
    assert round(p.required_per_day, 1) == round(10000 / 122, 1) == 82.0
    assert round(p.strain, 3) == 1.0


def test_falling_behind_raises_what_every_remaining_day_must_deliver():
    """Half the window gone, a tenth of the target reached."""
    p = _pace(date(2026, 11, 1), users=1000)
    assert p.days_remaining == 61
    assert round(p.required_per_day) == 148          # 9,000 over 61 days
    assert round(p.strain, 2) == 1.80                # every day works 80% harder
    assert p.user_gap < 0
    assert p.verdict == "behind"


def test_the_verdict_escalates_only_when_the_day_has_to_work_twice_as_hard():
    """Being behind is normal and must not escalate; an alarm that fires every
    week is an alarm nobody reads."""
    behind = _pace(date(2026, 11, 1), users=1000)
    assert behind.verdict == "behind"
    assert behind.escalate is False

    off = _pace(date(2026, 12, 1), users=1000)
    assert off.strain >= 2.0
    assert off.verdict == "off_track"
    assert off.escalate is True
    assert off.problems()


def test_slightly_behind_is_never_reported_as_on_track():
    """30 days in and 559 users short. The required pace has barely moved, so
    this is recoverable - but "on track" is a sentence somebody would quote in
    an update, and it would not be true."""
    p = _pace(date(2026, 10, 1), users=1900)
    assert p.user_gap < -500
    assert round(p.strain, 2) == 1.07
    assert p.verdict == "slipping"
    assert p.escalate is False


def test_being_ahead_says_so():
    p = _pace(date(2026, 10, 1), users=4000)
    assert p.user_gap > 0
    assert p.verdict == "ahead"
    assert p.escalate is False
    assert p.problems() == []


def test_reaching_the_target_ends_the_arithmetic_cleanly():
    p = _pace(date(2026, 11, 1), users=10_500)
    assert p.still_needed == 0
    assert p.required_per_day == 0.0
    assert p.verdict == "met"
    assert p.escalate is False


def test_a_missed_deadline_is_not_reported_as_nothing_left_to_do():
    """The trap: still_needed / days_remaining with days_remaining == 0. Zero
    would render as 'needs 0 a day', which reads as success on the one day it
    matters most."""
    p = _pace(date(2027, 1, 2), users=3000)
    assert p.days_remaining == 0
    assert p.required_per_day == float("inf")
    assert p.verdict == "missed"
    assert p.escalate is True


def test_the_projection_uses_the_measured_pace_and_does_not_flatter_it():
    p = _pace(date(2026, 10, 1), users=1000, recent=10)
    assert p.days_remaining == 92
    assert round(p.projected()) == 1920              # nowhere near 10,000
    assert p.projected() < p.goal.target


# --------------------------------------------------------------------------- #
# Growth that is not really growth
# --------------------------------------------------------------------------- #
def test_growth_with_collapsing_engagement_is_called_hollow():
    p = _pace(date(2026, 11, 1), users=5000, baseline=500, mau=1000,
              baseline_activation=0.60)
    assert round(p.activation, 2) == 0.20            # was 60%, now 20%
    assert p.hollow is True
    assert p.escalate is True
    assert any("without the product moving" in x for x in p.problems())


def test_growth_that_holds_its_engagement_is_not_hollow():
    p = _pace(date(2026, 11, 1), users=5000, baseline=500, mau=2900,
              baseline_activation=0.60)
    assert p.hollow is False


def test_ordinary_noise_in_the_ratio_does_not_trip_the_alarm():
    """A young product's activation moves around. The guard is for a change of
    character, not for a bad fortnight."""
    p = _pace(date(2026, 11, 1), users=5000, baseline=500, mau=2600,
              baseline_activation=0.55)
    assert 0.44 < p.activation < 0.53
    assert p.hollow is False


def test_hollow_needs_a_baseline_and_says_nothing_without_one():
    p = _pace(date(2026, 11, 1), users=5000, baseline=500, mau=10)
    assert p.baseline_activation is None
    assert p.hollow is False                          # unknown is not an alarm


def test_activation_is_unknown_rather_than_zero_when_mau_is_missing():
    p = _pace(date(2026, 11, 1), users=5000, baseline=500)
    assert p.activation is None


# --------------------------------------------------------------------------- #
# The compounding rate
# --------------------------------------------------------------------------- #
def test_the_required_weekly_growth_is_solved_not_guessed():
    p = _pace(START, users=0, recent=3)
    rate = required_weekly_growth(p)
    assert rate is not None
    # Seventeen whole weeks from a base of 3/day is a punishing rate, and the
    # number being large is the point of reporting it at all.
    assert 0.25 < rate < 0.45

    # Verify by replaying the compounding it claims to solve.
    total, per_day = 0.0, 3.0
    for _ in range(p.days_remaining // 7):
        total += 7 * per_day
        per_day *= 1 + rate
    assert abs(total - 10_000) < 50


def test_a_pace_fast_enough_already_needs_no_growth():
    p = _pace(START, users=0, recent=200)
    assert required_weekly_growth(p) == 0.0


def test_growth_is_unanswerable_from_a_standing_start():
    """Zero times any rate is still zero. Returning a number here would turn an
    unanswerable question into a confident wrong answer."""
    p = _pace(START, users=0, recent=0)
    assert required_weekly_growth(p) is None
