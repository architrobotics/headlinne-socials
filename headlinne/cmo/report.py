"""The pace report: where the number is, where it should be, and what it needs.

`python -m headlinne cmo pace` prints this, and exits non-zero when the plan
needs a human, so it can be a scheduled check rather than something somebody
remembers to look at. That is the same bargain `headlinne status` makes, and for
the same reason: a report nobody runs measures nothing.

The two reports do not overlap. `status` answers "did it publish, and did it
reach", from the committed content folder, with no network and no key. This one
answers "did any of that produce users", from the ledger. Distribution is the
question that can be answered without the product; users is the one that cannot.

One presentation rule, and it is load-bearing: **an unknown is printed as
unknown.** When the scoreboard cannot be read there is no fallback to zero and
no carrying-forward of yesterday's figure, because both would be a number a
person could act on, and neither would be true.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from ..logging_setup import get_logger
from . import ledger, metrics
from .goal import Goal, Pace, required_weekly_growth

log = get_logger("cmo.report")


@dataclass
class Reading:
    """A pace, plus everything needed to explain where it came from."""

    pace: Pace | None
    snapshot: metrics.Snapshot | None
    readings: int
    reason: str = ""            # why there is no pace, when there is none
    # Carried rather than looked up again at render time. Rendering used to
    # re-read the default ledger path, which meant a report built from one file
    # could print a date from another - fine in production where there is only
    # one, and wrong in every test and every dry run.
    first_day: str = "?"
    attribution_path: object = None

    def problems(self) -> list[str]:
        if self.pace is None:
            return [self.reason] if self.reason else []
        return self.pace.problems()


def build(today: date | None = None, *, path=None, fetch: bool = True,
          attribution_path=None) -> Reading:
    """Read the scoreboard, record it, and work out where that leaves the plan.

    `fetch=False` reports from the ledger alone, which is what a check running
    without credentials should do rather than reporting nothing.
    """
    from .. import scheduling

    today = today or scheduling.today_ist()

    snapshot = metrics.read(today) if fetch else None
    if snapshot is not None:
        ledger.append(snapshot, path=path)

    # The second view, read in the same breath. It is a separate grant and a
    # separate failure: a project that has created cmo_metrics but not
    # cmo_attribution still gets a working pace report, and simply cannot say
    # where the users came from.
    if fetch:
        refs = metrics.read_attribution(today)
        if refs is not None:
            ledger.append_attribution(refs, today, path=attribution_path)

    rows = ledger.series(path=path)
    if not rows:
        return Reading(
            pace=None, snapshot=snapshot, readings=0,
            reason="the scoreboard has never been read, so there is no number "
                   "to report. Set SUPABASE_URL and SUPABASE_KEY, then run "
                   "`python -m headlinne cmo pace` (the SQL that creates the "
                   "view is in `python -m headlinne cmo setup`).")

    first, last = rows[0], rows[-1]
    base_users = int(first.get("users") or 0)
    base_mau = int(first.get("mau") or 0)
    pace = Pace(
        goal=Goal(),
        today=today,
        users=int(last.get("users") or 0),
        baseline=base_users,
        dau=int(last.get("dau") or 0),
        mau=int(last.get("mau") or 0),
        baseline_activation=(base_mau / base_users) if base_users and base_mau else None,
        recent_per_day=ledger.gained_per_day(7, path=path),
    )
    return Reading(pace=pace, snapshot=snapshot, readings=len(rows),
                   first_day=str(first.get("day", "?")),
                   attribution_path=attribution_path)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _bar(share: float, width: int = 28) -> str:
    filled = max(0, min(width, round(share * width)))
    return "#" * filled + "." * (width - filled)


def format_report(reading: Reading) -> str:
    lines: list[str] = []
    p = reading.pace

    if p is None:
        lines.append("Scoreboard        unreadable")
        lines.append("")
        lines.append(reading.reason)
        return "\n".join(lines)

    goal = p.goal
    lines.append(f"Target            {goal.target:,} users by {goal.deadline}")
    lines.append(f"Window            {goal.start} to {goal.deadline}  "
                 f"({goal.total_days} days)")
    lines.append(f"Today             {p.today}  "
                 f"(day {p.days_elapsed} of {goal.total_days}, "
                 f"{p.days_remaining} left)")
    lines.append("")

    share = p.users / goal.target if goal.target else 0
    lines.append(f"Users             {p.users:,}  [{_bar(share)}]  {share:>5.1%}")
    lines.append(f"                  {p.gained:+,} since the first reading "
                 f"({reading.first_day})")
    lines.append(f"On track today    {p.on_track_users:,.0f}   "
                 f"gap {p.user_gap:+,.0f}")
    lines.append("")

    lines.append(f"Needed per day    {p.required_per_day:,.1f}   "
                 f"(day one needed {p.required_at_start:,.1f}, "
                 f"strain {p.strain:.2f}x)")
    measured = (f"{p.actual_per_day:,.1f}" if reading.readings > 1
                else "not yet measurable (one reading)")
    lines.append(f"Measured per day  {measured}")
    growth = required_weekly_growth(p)
    if growth is None:
        lines.append("Needed growth     not computable from a pace of zero")
    else:
        lines.append(f"Needed growth     {growth:.0%} week on week, "
                     f"for {p.days_remaining // 7} weeks")
    if reading.readings > 1:
        lines.append(f"Lands at          {p.projected():,.0f} on {goal.deadline} "
                     f"at the measured pace")
    lines.append("")

    act = p.activation
    lines.append(f"DAU / MAU         {p.dau:,} / {p.mau:,}"
                 + (f"   stickiness {p.stickiness:.0%}" if p.stickiness else ""))
    if act is None:
        lines.append("Activation        unknown")
    else:
        base = (f"  (baseline {p.baseline_activation:.0%})"
                if p.baseline_activation else "")
        lines.append(f"Activation        {act:.0%} of users active in 30 days{base}")
    lines.append("")

    lines.extend(_channel_lines(reading))
    lines.append(f"VERDICT           {p.verdict.replace('_', ' ').upper()}")
    problems = p.problems()
    if problems:
        lines.append("")
        lines.append(f"PROBLEMS ({len(problems)})")
        for item in problems:
            lines.append(f"  * {item}")
    return "\n".join(lines)


def _channel_lines(reading: Reading) -> list[str]:
    """Where the signups came from, when that can be answered at all."""
    from . import ledger as _ledger
    from . import portfolio

    channels = portfolio.from_history(ledger_path=reading.attribution_path)
    if all(c.signups is None for c in channels):
        return ["Channels          no attribution reading yet. "
                "`cmo setup` prints the SQL for the second view.", ""]

    lines = ["Channel          status      posts  signups   per post"]
    for c in sorted(channels, key=lambda c: -(c.signups or 0)):
        if not c.posts and not c.signups:
            continue
        rate = f"{c.rate:.2f}" if c.rate is not None else "-"
        signups = "-" if c.signups is None else f"{c.signups:,}"
        lines.append(f"  {c.name:14} {c.status():10} {c.posts:5}  "
                     f"{signups:>7}  {rate:>9}")
    unattributed = (_ledger.signups_by_channel(path=reading.attribution_path)
                    or {}).get("unattributed")
    if unattributed:
        lines.append(f"  {'unattributed':14} {'':10} {'':5}  "
                     f"{unattributed['signups']:>7}  {'-':>9}")
    lines.append("")
    return lines


def as_json(reading: Reading) -> str:
    p = reading.pace
    if p is None:
        return json.dumps({"readable": False, "reason": reading.reason}, indent=2)
    growth = required_weekly_growth(p)
    return json.dumps({
        "readable": True,
        "today": p.today.isoformat(),
        "first_reading": reading.first_day,
        "target": p.goal.target,
        "deadline": p.goal.deadline.isoformat(),
        "days_remaining": p.days_remaining,
        "users": p.users,
        "baseline": p.baseline,
        "gained": p.gained,
        "on_track_users": round(p.on_track_users, 1),
        "user_gap": round(p.user_gap, 1),
        "required_per_day": round(p.required_per_day, 2),
        "required_at_start": round(p.required_at_start, 2),
        "actual_per_day": (round(p.actual_per_day, 2)
                           if reading.readings > 1 else None),
        "strain": round(p.strain, 3),
        "required_weekly_growth": (round(growth, 4) if growth is not None else None),
        "projected": (round(p.projected(), 1) if reading.readings > 1 else None),
        "dau": p.dau,
        "mau": p.mau,
        "activation": (round(p.activation, 4) if p.activation else None),
        "hollow": p.hollow,
        "verdict": p.verdict,
        "escalate": p.escalate,
        "readings": reading.readings,
        "problems": p.problems(),
    }, indent=2)
