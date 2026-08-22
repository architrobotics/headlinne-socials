"""Is the account actually reaching anyone, and did it post at all?

This module exists because nothing in the system noticed when it stopped. The
pipeline is careful about contained failures - a reel that will not encode is
dropped so the rest of the day still goes out - and that is the right behaviour
for one bad format on one day. Repeated over weeks it is also how an account
quietly turns into a feed-only account without a single error being raised, and
how four days pass with no content at all and nothing says so.

Two numbers matter, and neither of them is "did the job exit zero".

**Silence.** The gap in days between the last generated day and today. Nothing
can be published on a day that was never generated, so this is the first thing
to look at when the impressions are zero.

**Discovery share.** The fraction of days that published a reel. Reels are the
only Instagram surface served to people who do not already follow the account;
feed posts are shown almost entirely to existing followers. On a day with no
reel, an account with a small following is not reaching anybody new, no matter
how good the carousel was. A carousel published to 97 followers and a carousel
published to nobody are nearly the same number of impressions, which is why
counting posts published is not a measure of distribution and counting reel days
is.

`python -m headlinne status` prints the report and exits non-zero when something
is actually wrong, so it can be a CI step rather than something a person has to
remember to look at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .config import CONTENT_DIR
from .scheduling import today_ist

# The surface each slot actually reaches. "discovery" is served to people who do
# not follow the account; "owned" is shown to people who already do. The split
# is the whole point of the report: an account can be busy on every owned
# surface and still be invisible.
SURFACE = {
    "reel_1": "discovery",
    "reel_2": "discovery",
    "instagram_1": "owned",
    "instagram_2": "owned",
    "story_card": "owned",
    "x_1": "owned",
    "x_2": "owned",
    "linkedin": "owned",
}

# Below this share of days carrying a reel, the account is not really being
# distributed - it is being archived. Not a hard target, a floor.
DISCOVERY_FLOOR = 0.8

# A day with no generated content at all. One is a miss; two in a row is an
# outage, because the backup cron should have caught the first.
SILENCE_ALARM_DAYS = 2


@dataclass
class DayRecord:
    day: date
    generated: bool
    published: set[str] = field(default_factory=set)

    @property
    def discovery(self) -> set[str]:
        return {s for s in self.published if SURFACE.get(s) == "discovery"}


@dataclass
class Report:
    days: list[DayRecord]
    today: date

    # -- silence ----------------------------------------------------------- #
    @property
    def last_generated(self) -> date | None:
        days = [d.day for d in self.days if d.generated]
        return max(days) if days else None

    @property
    def silent_days(self) -> int:
        """Days since the last generated day. 0 when today has content."""
        last = self.last_generated
        return (self.today - last).days if last else len(self.days)

    # -- distribution ------------------------------------------------------ #
    @property
    def window(self) -> int:
        return len(self.days)

    @property
    def discovery_days(self) -> int:
        return sum(1 for d in self.days if d.discovery)

    @property
    def discovery_share(self) -> float:
        return self.discovery_days / self.window if self.window else 0.0

    def coverage(self) -> dict[str, int]:
        counts = {slot: 0 for slot in SURFACE}
        for d in self.days:
            for slot in d.published:
                if slot in counts:
                    counts[slot] += 1
        return counts

    # -- verdict ----------------------------------------------------------- #
    def problems(self) -> list[str]:
        """Everything wrong enough to be worth failing a build over."""
        out = []
        if self.silent_days >= SILENCE_ALARM_DAYS:
            last = self.last_generated
            out.append(
                f"no content generated for {self.silent_days} days "
                f"(last was {last.isoformat() if last else 'never'}). Nothing "
                f"can publish on a day that was never generated.")
        if self.window and self.discovery_share < DISCOVERY_FLOOR:
            out.append(
                f"a reel published on {self.discovery_days} of the last "
                f"{self.window} days ({self.discovery_share:.0%}). Reels are the "
                f"only surface that reaches people who do not already follow, so "
                f"the other {self.window - self.discovery_days} days reached "
                f"almost nobody new.")
        return out


def scan(days: int = 30, today: date | None = None,
         root: Path | None = None) -> Report:
    """Read the committed content folder and report on the last `days` days."""
    today = today or today_ist()
    root = root or CONTENT_DIR
    records = []
    for back in range(days):
        day = today - timedelta(days=back)
        folder = Path(root) / day.isoformat()
        published = set()
        pub_dir = folder / "published"
        if pub_dir.is_dir():
            published = {p.stem for p in pub_dir.glob("*.json")}
        records.append(DayRecord(day=day,
                                 generated=(folder / "plan.json").exists(),
                                 published=published))
    records.reverse()
    return Report(days=records, today=today)


def format_report(report: Report) -> str:
    """The human-readable version. Kept separate so scan() stays testable."""
    lines = []
    last = report.last_generated
    lines.append(f"Window            last {report.window} days, to {report.today}")
    lines.append(f"Last generated    {last.isoformat() if last else 'never'}"
                 + (f"  ({report.silent_days} days ago)" if report.silent_days else "  (today)"))
    lines.append("")
    lines.append(f"Discovery         a reel went out on {report.discovery_days} of "
                 f"{report.window} days  ({report.discovery_share:.0%})")
    lines.append("")
    lines.append("Slot              days published")
    cov = report.coverage()
    for slot in SURFACE:
        n = cov[slot]
        share = n / report.window if report.window else 0
        bar = "#" * round(share * 24)
        lines.append(f"  {slot:15} {n:3}/{report.window}  "
                     f"{share:4.0%} {bar}  [{SURFACE[slot]}]")
    problems = report.problems()
    lines.append("")
    if problems:
        lines.append(f"PROBLEMS ({len(problems)})")
        for p in problems:
            lines.append(f"  * {p}")
    else:
        lines.append("No problems. The account is generating and reaching.")
    return "\n".join(lines)


def as_json(report: Report) -> str:
    return json.dumps({
        "today": report.today.isoformat(),
        "window_days": report.window,
        "last_generated": (report.last_generated.isoformat()
                           if report.last_generated else None),
        "silent_days": report.silent_days,
        "discovery_days": report.discovery_days,
        "discovery_share": round(report.discovery_share, 4),
        "coverage": report.coverage(),
        "problems": report.problems(),
    }, indent=2)
