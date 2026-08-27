"""What a slot is worth, inferred from days it ran against days it did not.

The link-based scheme this replaced needed the product to store a `ref` at
signup. That is a change to the auth path, and the auth path is the one piece of
code that must never break for a growth experiment's convenience. So nothing is
recorded at signup. Attribution is inferred instead, from two things that
already exist.

**The pipeline is irregular, and that irregularity is a natural experiment.**
`headlinne status` reports reels going out on 7 of 30 days and carousels on 22.
Nobody designed that as a trial, but it is one: there are days with a reel and
days without, and the difference between the signups on each is an estimate of
what a reel is worth. The committed content folder already records which slots
fired on which day, so the whole experiment is sitting in git waiting to be
read.

**It measures Instagram.** That is the reason to prefer it over any tagging
scheme, not a consolation. Three of the four things this pipeline makes go to
surfaces with no clickable link, so no tag would ever have measured them. A
signup timestamp does not care whether the reader could tap anything.

What it costs is certainty, and the cost is real:

  - **It is correlational.** A slot that only runs on days with a big story
    will look excellent, because the story drove the signups. Nothing here can
    tell those apart, and `Estimate.caveat` says so on every row.
  - **Slots that always run together cannot be separated.** If a reel and a
    carousel publish on the same days, their effects are one effect wearing two
    names. `confounded_with` detects that and refuses to report either as if it
    stood alone.
  - **It needs contrast.** A slot that ran every single day has no days without,
    so it has no comparison and no estimate - only an honest "cannot tell".

Everything this module produces is an **estimate**, and the word is carried
through to the report rather than dropped once it becomes inconvenient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..logging_setup import get_logger
from . import attribution

log = get_logger("cmo.lift")

# Days a slot must have both run and not run before the comparison means
# anything. Below this the two means are each an average of a handful of days
# and the difference is weather.
MIN_CONTRAST_DAYS = 7

# Total signups across the whole window, below which no split of them is worth
# reading. At ten signups a fortnight, every slot looks decisive and none is.
MIN_SIGNUPS = 40

# A rough screen, not a p-value. Two standard errors is the conventional line
# and it is used here only to sort "worth acting on" from "noise", which is the
# only decision this feeds.
MIN_T = 2.0

# Two slots whose publish patterns agree on this share of days are, for this
# purpose, the same slot. Their effects cannot be told apart by any amount of
# data of this kind.
CONFOUND_AGREEMENT = 0.90


@dataclass
class Estimate:
    """One slot, and what the days it ran are worth against the days it did not."""

    slot: str
    days_with: int
    days_without: int
    mean_with: float
    mean_without: float
    t: float = 0.0
    confounded_with: list[str] = field(default_factory=list)
    reason: str = ""              # why there is no estimate, when there is none

    @property
    def lift(self) -> float | None:
        """Estimated extra signups on a day this slot runs. None when unusable."""
        if self.reason:
            return None
        return self.mean_with - self.mean_without

    @property
    def usable(self) -> bool:
        """Worth allocating on: a real contrast, above the noise, and separable.

        `confounded_with` is part of the test and it is the one that bites. Two
        slots that always run together each measure the *same* effect, so
        without this check both are usable, both carry the full lift, and
        `by_channel` adds them together - crediting one reel's worth of signups
        twice and moving the day's slots onto the double-counted channel.
        """
        return (self.lift is not None and abs(self.t) >= MIN_T
                and not self.confounded_with)

    @property
    def confidence(self) -> str:
        if self.reason:
            return "none"
        if self.confounded_with:
            return "confounded"
        return "usable" if abs(self.t) >= MIN_T else "weak"

    @property
    def caveat(self) -> str:
        if self.reason:
            return self.reason
        if self.confounded_with:
            return (f"runs on nearly the same days as "
                    f"{', '.join(self.confounded_with)}, so their effects "
                    f"cannot be told apart")
        if abs(self.t) < MIN_T:
            return ("the difference is inside the noise of these volumes")
        return ("an association, not a cause: a slot that runs on big-news days "
                "inherits the news")


# --------------------------------------------------------------------------- #
# Turning hourly buckets into days
# --------------------------------------------------------------------------- #
def daily_signups(buckets, *, tz=None) -> dict[date, int]:
    """Roll hourly buckets up into IST days, because the schedule is IST.

    Rolling up in UTC would put the 21:30 IST story card on the previous day for
    half the year, which is precisely the slot whose effect this is trying to
    read.
    """
    from ..config import TIMEZONE

    tz = tz or TIMEZONE
    out: dict[date, int] = {}
    for bucket in buckets:
        when = bucket.hour
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        day = when.astimezone(tz).date()
        out[day] = out.get(day, 0) + int(bucket.signups)
    return out


def published_by_day(days: int = 90, **kwargs) -> dict[date, set[str]]:
    """Which slots actually went out on each day, from the committed record."""
    from .. import health

    report = health.scan(days=days, **kwargs)
    return {record.day: set(record.published) for record in report.days}


# --------------------------------------------------------------------------- #
# The comparison
# --------------------------------------------------------------------------- #
def _mean_and_var(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    return mean, sum((v - mean) ** 2 for v in values) / (n - 1)


def _welch_t(a: list[float], b: list[float]) -> float:
    """Welch's t. The two groups have different sizes and different spread, and
    pooling their variance would understate the error on the smaller one -
    which is always the group we care about, because it is the slot that ran
    rarely enough to be worth measuring."""
    mean_a, var_a = _mean_and_var(a)
    mean_b, var_b = _mean_and_var(b)
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 0.0
    se = (var_a / n_a + var_b / n_b) ** 0.5
    if se == 0:
        return 0.0
    return (mean_a - mean_b) / se


def _agreement(days: list[date], a: set[date], b: set[date]) -> float:
    """Share of days on which two slots made the same choice to run or not."""
    if not days:
        return 0.0
    same = sum(1 for d in days if (d in a) == (d in b))
    return same / len(days)


def estimate(signups: dict[date, int], published: dict[date, set[str]],
             *, slots=None) -> dict[str, Estimate]:
    """Estimate every slot's daily lift. Honest about what it cannot say."""
    days = sorted(d for d in published if d in signups)
    slots = list(slots or attribution.SURFACES)

    if not days:
        return {s: Estimate(s, 0, 0, 0.0, 0.0,
                            reason="no day has both a signup reading and a "
                                   "published record") for s in slots}

    total = sum(signups[d] for d in days)
    ran_on = {s: {d for d in days if s in published[d]} for s in slots}

    out: dict[str, Estimate] = {}
    for slot in slots:
        with_days = sorted(ran_on[slot])
        without_days = [d for d in days if d not in ran_on[slot]]
        a = [float(signups[d]) for d in with_days]
        b = [float(signups[d]) for d in without_days]
        mean_a, _ = _mean_and_var(a)
        mean_b, _ = _mean_and_var(b)

        reason = ""
        if total < MIN_SIGNUPS:
            reason = (f"only {total} signups across {len(days)} days. Any split "
                      f"of that is noise")
        elif len(a) < MIN_CONTRAST_DAYS or len(b) < MIN_CONTRAST_DAYS:
            if not a:
                reason = f"never published in the last {len(days)} days"
            elif not b:
                reason = (f"published on all {len(days)} days, so there is no "
                          f"day without it to compare against")
            else:
                reason = (f"{len(a)} days with and {len(b)} without; "
                          f"{MIN_CONTRAST_DAYS} of each are needed")

        confounded = []
        if not reason:
            for other in slots:
                if other == slot or not ran_on[other]:
                    continue
                if _agreement(days, ran_on[slot], ran_on[other]) >= CONFOUND_AGREEMENT:
                    confounded.append(other)

        out[slot] = Estimate(
            slot=slot, days_with=len(a), days_without=len(b),
            mean_with=round(mean_a, 3), mean_without=round(mean_b, 3),
            t=round(_welch_t(a, b), 3), confounded_with=sorted(confounded),
            reason=reason)
    return out


def by_channel(estimates: dict[str, Estimate]) -> dict[str, dict]:
    """Roll slot estimates up into the channels the portfolio allocates across.

    Only usable estimates contribute. A weak or confounded slot adds nothing
    rather than adding a number with a shrug attached, because the allocator
    divides by these and cannot carry a shrug.
    """
    out: dict[str, dict] = {}
    for slot, est in estimates.items():
        surface = attribution.SURFACES.get(slot)
        if surface is None:
            continue
        bucket = out.setdefault(surface.source,
                                {"estimated_signups": 0.0, "slots": [],
                                 "usable": 0})
        bucket["slots"].append(slot)
        if est.usable and est.lift and est.lift > 0:
            bucket["estimated_signups"] += est.lift * est.days_with
            bucket["usable"] += 1
    return out


def format_estimates(estimates: dict[str, Estimate]) -> str:
    lines = ["Slot             days on  days off   with   without    lift  confidence"]
    for slot, est in sorted(estimates.items(),
                            key=lambda kv: -(kv[1].lift or -999)):
        lift = f"{est.lift:+.2f}" if est.lift is not None else "     -"
        lines.append(f"  {slot:14} {est.days_with:7} {est.days_without:9} "
                     f"{est.mean_with:6.2f} {est.mean_without:9.2f} "
                     f"{lift:>7}  {est.confidence}")
    lines.append("")
    for slot, est in sorted(estimates.items()):
        if est.confidence != "usable":
            lines.append(f"  {slot}: {est.caveat}")
    usable = [e for e in estimates.values() if e.usable]
    if usable:
        lines.append("")
        lines.append("Every figure above is an estimate from days a slot ran "
                     "against days it did not.")
        lines.append("It is an association, not a cause.")
    return "\n".join(lines)
