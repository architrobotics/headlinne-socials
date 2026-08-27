"""The weekly review, and the escalation that arrives in September rather than
in December.

Every number in the text this module produces is read from the ledger, the
decisions log or the experiment register. There is no code path here that
accepts a figure from anywhere else, which is what makes the review a report
rather than a narration. A marketer that can generate its own progress numbers
will generate good ones - not through malice, but because a fluent summary of an
ambiguous week is always available and always reads better than the ambiguity.

The escalation is the reason the whole layer exists. A plan that misses is not
the failure; a plan that misses *and only says so in the last week* is, because
by then none of the levers have time to work. `escalation()` fires on the pace
verdict, on hollow growth, and on the thing easiest to miss: a campaign running
for weeks against surfaces where nothing can be observed at all. The third one
never announces itself, because a blind channel produces no bad numbers - it
produces no numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..logging_setup import get_logger
from . import (attribution, brief as brief_mod, experiments, ledger, lift,
               policy, portfolio, report)
from .goal import required_weekly_growth

log = get_logger("cmo.review")

# A campaign that has been running this long with slots nothing can separate is
# not learning anything. Three weeks is roughly the point at which "we are still
# setting up" stops being true.
BLIND_PATIENCE_DAYS = 21


@dataclass
class Review:
    today: date
    reading: report.Reading
    week: list[dict]
    decisions: list[dict]
    coverage: attribution.Coverage
    estimates: dict
    due: list
    tampered: list

    @property
    def pace(self):
        return self.reading.pace


def build(today: date | None = None, *, ledger_path: Path | None = None,
          experiments_path: Path | None = None,
          decisions_path: Path | None = None) -> Review:
    from .. import scheduling

    today = today or scheduling.today_ist()
    reading = report.build(today, path=ledger_path, fetch=False)
    since = today - timedelta(days=7)
    rows = [r for r in ledger.series(path=ledger_path)
            if r.get("day", "") >= since.isoformat()]
    return Review(
        today=today,
        reading=reading,
        week=rows,
        decisions=policy.decisions(since, path=decisions_path),
        coverage=attribution.coverage(portfolio.DEFAULT_SLOTS),
        estimates=_estimates(ledger_path),
        due=experiments.due(today, path=experiments_path),
        tampered=experiments.load(path=experiments_path).tampered(),
    )


def _estimates(ledger_path) -> dict:
    """What each slot looks worth, or an empty map when nothing can be read."""
    signups = ledger.signups_by_day(path=ledger_path)
    if not signups:
        return {}
    return lift.estimate(signups, lift.published_by_day(days=90),
                         slots=portfolio.DEFAULT_SLOTS)


def escalation(review: Review) -> list[str]:
    """What a person has to be told now, not at the end.

    Empty is a real answer and it is the common one. An escalation that fires
    every week trains the reader to close it, and then the one that mattered
    arrives into a habit of not looking.
    """
    out: list[str] = []
    pace = review.pace

    if pace is None:
        out.append(
            "the scoreboard has never been read, so nothing in this campaign is "
            "measured. Every allocation so far is a guess wearing a number.")
        return out

    out.extend(pace.problems())

    # The failure that never announces itself.
    #
    # A slot published every single day has no day without it, so it can never
    # be estimated - and it produces no bad numbers to notice, because it
    # produces none at all. The pace just looks disappointing and the cause
    # stays invisible. The fix is cheap and counter-intuitive enough that
    # nobody arrives at it unprompted: skip the slot sometimes. A week of
    # deliberate absence buys a measurement that no amount of further posting
    # ever will.
    if review.reading.readings:
        first = date.fromisoformat(review.reading.first_day)
        running = (review.today - first).days
        stuck = sorted(slot for slot, est in review.estimates.items()
                       if "no day without it" in est.caveat)
        if running >= BLIND_PATIENCE_DAYS and stuck:
            out.append(
                f"{running} days in and {', '.join(stuck)} have published every "
                f"single day, so there is no day without them to compare "
                f"against and their contribution cannot be estimated at all. "
                f"Skipping one for a week would buy a measurement that no "
                f"amount of further posting will.")

        confounded = sorted(slot for slot, est in review.estimates.items()
                            if est.confounded_with)
        if running >= BLIND_PATIENCE_DAYS and confounded:
            out.append(
                f"{', '.join(confounded)} publish on nearly the same days, so "
                f"their effects are one effect wearing several names. Varying "
                f"their schedules independently is the only thing that "
                f"separates them.")

    if review.tampered:
        names = ", ".join(e.id for e in review.tampered)
        out.append(
            f"the stop rule was edited after registration on: {names}. Those "
            f"results will not be called, because a stop rule chosen after the "
            f"numbers arrived is not a stop rule.")

    return out


def format_review(review: Review) -> str:
    pace = review.pace
    lines = [f"CMO review        week to {review.today}", ""]

    if pace is None:
        lines += ["No reading has ever been taken.", "",
                  review.reading.reason]
        return "\n".join(lines)

    goal = pace.goal
    gained_this_week = 0
    if len(review.week) >= 2:
        gained_this_week = review.week[-1]["users"] - review.week[0]["users"]

    lines += [
        f"Users             {pace.users:,} of {goal.target:,}   "
        f"({pace.users / goal.target:.1%})",
        f"This week         {gained_this_week:+,}",
        f"Against the line  {pace.user_gap:+,.0f}",
        f"Days left         {pace.days_remaining}",
        "",
        f"Needed per day    {pace.required_per_day:,.1f}   "
        f"(strain {pace.strain:.2f}x)",
    ]
    if review.reading.readings > 1:
        lines.append(f"Measured per day  {pace.actual_per_day:,.1f}")
        lines.append(f"Lands at          {pace.projected():,.0f}")
    growth = required_weekly_growth(pace)
    if growth is not None:
        lines.append(f"Needed growth     {growth:.0%} a week for "
                     f"{pace.days_remaining // 7} weeks")
    lines += ["", f"Verdict           {pace.verdict.replace('_', ' ').upper()}", ""]

    usable = {s: e for s, e in review.estimates.items() if e.usable}
    if usable:
        lines.append("What each slot looks worth (estimated, not measured)")
        for slot, est in sorted(usable.items(), key=lambda kv: -kv[1].lift):
            lines.append(f"  {slot:15} {est.lift:+.2f} signups a day it runs "
                         f"({est.days_with} on, {est.days_without} off)")
    else:
        lines.append("What each slot looks worth")
        lines.append("  nothing separable yet. `cmo lift` shows why.")
    lines.append("")

    if review.decisions:
        lines.append(f"Acted, and telling you now ({len(review.decisions)})")
        for row in review.decisions[-8:]:
            lines.append(f"  {row.get('day', '?')}  {row.get('action', '?')}"
                         + (f"  {row['detail']}" if row.get("detail") else ""))
        lines.append("")

    if review.due:
        lines.append(f"Experiments ready to call ({len(review.due)})")
        for exp in review.due:
            lines.append(f"  {exp.id:16} {exp.hypothesis}")
        lines.append("")

    problems = escalation(review)
    if problems:
        lines.append(f"ESCALATE ({len(problems)})")
        for item in problems:
            lines.append(f"  * {item}")
    else:
        lines.append("Nothing to escalate. The plan is recoverable from here.")
    return "\n".join(lines)
