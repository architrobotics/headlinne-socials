"""The target, the clock, and the arithmetic that says whether it is reachable.

Ten thousand users by 1 January 2027, counted from 1 September 2026. That is
122 days, and the pace it implies is the first thing anyone should see.

Two rules shape this module, and both exist to stop it from being comforting.

**The required pace is recomputed from where you actually are, not from where
you planned to be.** A plan that says "82 a day" on day one and still says 82 a
day in November is not a plan, it is a wall poster. Every user you did not get
yesterday is redistributed across the days that remain, so the number climbs
when you fall behind. That climb is the alarm, and it is why this is arithmetic
rather than a status field somebody updates.

**A user who never comes back is not a user.** The goal is stated in total
signups because that is what a founder says out loud, but the honest reading is
the activation ratio - what share of the people counted were active in the last
month. A campaign that doubles signups and halves that ratio has moved the
headline number and nothing else. `Pace.hollow` says so, in the report, in the
same breath as the good news. Without it the target is a metric to be gamed, and
an autonomous marketer with a deadline is exactly the thing that would game it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# --------------------------------------------------------------------------- #
# The commitment
# --------------------------------------------------------------------------- #
TARGET = 10_000
START = date(2026, 9, 1)
DEADLINE = date(2027, 1, 1)

# How far the activation ratio may fall from its own baseline before growth is
# called hollow. Not an absolute floor: a young product's ratio moves around a
# lot, and what matters is the direction it moves while the headline number
# climbs. A fifth of the baseline is a wide band, deliberately - this should
# fire on a real change of character, not on ordinary weekly noise.
ACTIVATION_DROP = 0.20

# Strain is the required daily pace divided by what it was on day one. At 1.0
# the plan is exactly on schedule. Above these the report escalates, because
# the whole point of measuring in September is to be told in September.
STRAIN_BEHIND = 1.25
STRAIN_OFF_TRACK = 2.00


@dataclass(frozen=True)
class Goal:
    target: int = TARGET
    start: date = START
    deadline: date = DEADLINE

    @property
    def total_days(self) -> int:
        return (self.deadline - self.start).days

    def days_elapsed(self, today: date) -> int:
        return max(0, min(self.total_days, (today - self.start).days))

    def days_remaining(self, today: date) -> int:
        return max(0, (self.deadline - today).days)


@dataclass
class Pace:
    """One reading of the scoreboard. Every field here is derived, never set."""

    goal: Goal
    today: date
    users: int                                 # total signups, as the product reports them
    baseline: int                              # total signups on the first measured day
    dau: int = 0
    mau: int = 0
    baseline_activation: float | None = None   # mau/users when measurement began
    recent_per_day: float | None = None        # measured signups/day, trailing window

    # -- the clock --------------------------------------------------------- #
    @property
    def days_elapsed(self) -> int:
        return self.goal.days_elapsed(self.today)

    @property
    def days_remaining(self) -> int:
        return self.goal.days_remaining(self.today)

    # -- the pace ---------------------------------------------------------- #
    @property
    def gained(self) -> int:
        """Users added since measurement began. The only number we earned."""
        return self.users - self.baseline

    @property
    def still_needed(self) -> int:
        return max(0, self.goal.target - self.users)

    @property
    def required_per_day(self) -> float:
        """What each remaining day must deliver, from where we are now.

        Returns infinity when the deadline has passed with the target unmet,
        rather than dividing by zero or quietly reporting 0.0 - which would
        read as "nothing left to do" on the one day that matters most.
        """
        if not self.still_needed:
            return 0.0
        if self.days_remaining <= 0:
            return float("inf")
        return self.still_needed / self.days_remaining

    @property
    def required_at_start(self) -> float:
        """The pace this needed on day one, before anything had happened."""
        span = self.goal.total_days
        return (self.goal.target - self.baseline) / span if span else float("inf")

    @property
    def actual_per_day(self) -> float:
        """Measured pace: the trailing window when there is one, otherwise the
        average since measurement began."""
        if self.recent_per_day is not None:
            return self.recent_per_day
        return self.gained / self.days_elapsed if self.days_elapsed else 0.0

    @property
    def on_track_users(self) -> float:
        """Where the total would be today on a straight line to the target."""
        span = self.goal.total_days
        if not span:
            return float(self.goal.target)
        share = self.days_elapsed / span
        return self.baseline + (self.goal.target - self.baseline) * share

    @property
    def user_gap(self) -> float:
        """Negative means behind. This is the number to put in an update."""
        return self.users - self.on_track_users

    @property
    def strain(self) -> float:
        """How much harder each remaining day has to work than day one did."""
        base = self.required_at_start
        if not base or base == float("inf"):
            return 1.0
        return self.required_per_day / base

    def projected(self) -> float:
        """Where the current measured pace lands on the deadline. No optimism."""
        return self.users + self.actual_per_day * self.days_remaining

    # -- is the growth real? ------------------------------------------------ #
    @property
    def activation(self) -> float | None:
        """Share of counted users who were active in the last month."""
        if not self.users or not self.mau:
            return None
        return self.mau / self.users

    @property
    def stickiness(self) -> float | None:
        """DAU over MAU. How many days a month an active user shows up."""
        if not self.mau or not self.dau:
            return None
        return self.dau / self.mau

    @property
    def hollow(self) -> bool:
        """True when the headline number is climbing and engagement is not.

        This is the anti-Goodhart guard. Total signups is a gameable number and
        the CMO is being judged on it, so the one check that has to be automatic
        is whether the people being counted ever came back.
        """
        now, was = self.activation, self.baseline_activation
        if now is None or not was:
            return False
        return self.gained > 0 and now < was * (1 - ACTIVATION_DROP)

    # -- the verdict -------------------------------------------------------- #
    @property
    def verdict(self) -> str:
        if not self.still_needed:
            return "met"
        if self.days_remaining <= 0:
            return "missed"
        s = self.strain
        if s >= STRAIN_OFF_TRACK:
            return "off_track"
        if s >= STRAIN_BEHIND:
            return "behind"
        if self.user_gap >= 0:
            return "ahead"
        # Below the line, but each remaining day needs less than a quarter more
        # than day one did. That is recoverable, and it is emphatically not
        # "on track" - a report that says on track while the gap is hundreds of
        # users is the exact sentence that gets quoted in an update and turns
        # out to have been false.
        return "slipping"

    @property
    def escalate(self) -> bool:
        """Worth interrupting a human for. Deliberately not the same as "behind":
        being behind is normal and recoverable, and an alarm that fires every
        week is an alarm nobody reads."""
        return self.verdict in ("off_track", "missed") or self.hollow

    def problems(self) -> list[str]:
        """Everything wrong enough to fail a scheduled check over."""
        out: list[str] = []
        if self.verdict == "missed":
            out.append(
                f"the deadline passed with {self.users:,} of "
                f"{self.goal.target:,} users.")
        elif self.verdict == "off_track":
            out.append(
                f"each remaining day now needs {self.required_per_day:,.0f} "
                f"signups, {self.strain:.1f}x the {self.required_at_start:,.0f} "
                f"it needed on day one. The measured pace is "
                f"{self.actual_per_day:,.1f} a day, which lands at "
                f"{self.projected():,.0f} on {self.goal.deadline}.")
        if self.hollow:
            out.append(
                f"signups are growing but engagement is not: "
                f"{self.activation:.0%} of users were active in the last month, "
                f"against {self.baseline_activation:.0%} at baseline. The "
                f"headline number is moving without the product moving.")
        return out


def required_weekly_growth(pace: Pace) -> float | None:
    """The compounding rate that closes the gap, given where the pace is now.

    The flat number (`required_per_day`) is the friendly reading and it is the
    one everybody quotes. Growth compounds, so the shape that actually has to
    happen is a curve, and stating it as a weekly rate is the only form in which
    it can be compared to anything - a healthy consumer product grows 5 to 7% a
    week, and knowing that the plan needs 30% is worth more than knowing it
    needs 82 signups a day.

    Returns None when there is no measured pace to compound from: zero times any
    growth rate is still zero, and inventing a starting point would turn an
    unanswerable question into a confident wrong answer.
    """
    weeks = pace.days_remaining // 7
    need = pace.still_needed
    if not need:
        return 0.0
    start = pace.actual_per_day
    if weeks <= 0 or start <= 0:
        return None

    def total(rate: float) -> float:
        out, per_day = 0.0, start
        for _ in range(weeks):
            out += 7 * per_day
            per_day *= 1 + rate
        return out

    if total(0.0) >= need:          # already fast enough without compounding
        return 0.0
    lo, hi = 0.0, 5.0
    if total(hi) < need:            # not reachable by growth alone at any sane rate
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if total(mid) < need:
            lo = mid
        else:
            hi = mid
    return hi
