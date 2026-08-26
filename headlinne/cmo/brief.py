"""The daily instruction to the content factory. This is the hand on the wheel.

Without this file the CMO is a dashboard: it can measure the pace, allocate
effort on paper and write a review nobody has to act on, while the pipeline
generates exactly what it generated yesterday from constants in `config.py`.
The brief is the one small, reversible interface that makes the difference
between observing and steering.

`brief.write()` produces `state/cmo/brief-<date>.json`; `pipeline.generate()`
reads it. Three properties keep that seam safe:

**A missing brief changes nothing.** `read()` returns None and every call site
falls back to the constant it used before, so the layer can be deleted, skipped
or fail entirely and the day still goes out exactly as it does today.

**A brief may only ask for things policy already permits.** Every instruction
goes through `policy.check` as it is assembled, and a refused one is dropped
with its reason recorded rather than written into the file for the pipeline to
discover it cannot do.

**Every instruction cites its evidence.** `reason` and `evidence` are not
decoration - they name the ledger rows that justify the change. An autonomous
decision that cannot be audited after the fact is indistinguishable from a
guess, and in four months nobody will remember which it was.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from ..config import STATE_DIR
from ..logging_setup import get_logger
from . import attribution, experiments, ledger, policy, portfolio, report

log = get_logger("cmo.brief")

BRIEF_DIR = STATE_DIR / "cmo"

# When the pace says the plan is off track, the day stops hedging across four
# formats and puts its production behind the one asset that travels. Which asset
# that is was decided by argument, not by measurement, and it is written down
# here so it can be argued with: the disagreement card is the only thing this
# product makes that is both a piece of content and a demonstration of the
# product's claim.
BEHIND_BIAS = "conflict"


@dataclass
class Brief:
    day: str
    campaign: str
    verdict: str
    required_per_day: float | None
    actual_per_day: float | None
    formats: list[str] = field(default_factory=list)
    story_bias: str = "interest"
    links: dict[str, str] = field(default_factory=dict)
    experiments: dict[str, str] = field(default_factory=dict)
    attribution_share: float = 0.0
    blind_slots: list[str] = field(default_factory=list)
    reason: str = ""
    evidence: str = ""
    refused: list[str] = field(default_factory=list)

    def link_for(self, slot: str) -> str | None:
        return self.links.get(slot)


def path_for(day: date, *, root: Path | None = None) -> Path:
    return (root or BRIEF_DIR) / f"brief-{day.isoformat()}.json"


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #
def build(day: date | None = None, *, ledger_path: Path | None = None,
          experiments_path: Path | None = None,
          attribution_path: Path | None = None,
          sources: dict[str, dict] | None = None) -> Brief:
    """Decide what today should make, and be able to say why."""
    from .. import scheduling

    day = day or scheduling.today_ist()
    reading = report.build(day, path=ledger_path, fetch=False)
    pace = reading.pace

    refused: list[str] = []

    def permitted(action: str) -> bool:
        decision = policy.check(action)
        if not decision.allowed:
            refused.append(f"{action}: {decision.why}")
            return False
        policy.record(decision, f"brief {day.isoformat()}")
        return True

    # 1. What to make. The allocator decides the shape of the day; policy
    #    decides whether the CMO is allowed to change it at all.
    channels = portfolio.from_history(sources=sources,
                                      ledger_path=attribution_path, today=day)
    allocation = portfolio.allocate(channels)
    formats = list(portfolio.DEFAULT_SLOTS)
    if not permitted("choose_format"):
        allocation = portfolio.Allocation()

    # 2. Which story leads. Falling behind is what earns the change of bias,
    #    and the threshold is the pace verdict rather than a feeling about it.
    bias = "interest"
    if pace is not None and pace.verdict in ("behind", "off_track"):
        bias = BEHIND_BIAS

    # 3. The links. Only where a link can actually be clicked.
    links: dict[str, str] = {}
    assignments: dict[str, str] = {}
    if permitted("mint_link"):
        for slot in formats:
            arm = ""
            if permitted("assign_experiment"):
                exp_id, arm = experiments.assign(day, slot, path=experiments_path)
                if exp_id:
                    assignments[slot] = f"{exp_id}:{arm}"
            url = attribution.for_slot(day, slot, arm=arm)
            if url:
                links[slot] = url

    coverage = attribution.coverage(formats)

    reason, evidence = _explain(pace, reading, bias, coverage, allocation)
    return Brief(
        day=day.isoformat(),
        campaign=attribution.campaign_for(day),
        verdict=pace.verdict if pace else "unreadable",
        required_per_day=(round(pace.required_per_day, 2)
                          if pace and pace.required_per_day != float("inf")
                          else None),
        actual_per_day=(round(pace.actual_per_day, 2)
                        if pace and reading.readings > 1 else None),
        formats=formats,
        story_bias=bias,
        links=links,
        experiments=assignments,
        attribution_share=round(coverage.share, 4),
        blind_slots=coverage.blind,
        reason=reason,
        evidence=evidence,
        refused=refused,
    )


def _explain(pace, reading, bias, coverage, allocation) -> tuple[str, str]:
    """The justification, built only from numbers that came out of the ledger."""
    if pace is None:
        return ("the scoreboard has never been read, so today is the standing "
                "mix. Nothing here is evidence-based yet.", "ledger://empty")

    parts = [
        f"{pace.users:,} users against {pace.on_track_users:,.0f} on the line "
        f"({pace.user_gap:+,.0f}); each remaining day needs "
        f"{pace.required_per_day:,.1f}, {pace.strain:.2f}x day one."
    ]
    if bias != "interest":
        parts.append(
            f"The pace reads {pace.verdict.replace('_', ' ')}, so the day leads "
            f"on {bias} rather than on interest.")
    if coverage.share < 1.0:
        summary = coverage.summary()
        parts.append(summary[:1].upper() + summary[1:])
    if pace.hollow:
        parts.append("Growth is arriving without engagement, so more of it is "
                     "not the answer today.")
    return " ".join(parts), f"ledger://{reading.first_day}..{pace.today}"


# --------------------------------------------------------------------------- #
# Writing and reading
# --------------------------------------------------------------------------- #
def write(brief: Brief, *, root: Path | None = None) -> Path:
    day = date.fromisoformat(brief.day)
    path = path_for(day, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(brief), indent=2, sort_keys=True),
                    encoding="utf-8")
    log.info("brief for %s: %s, bias=%s, %d links",
             brief.day, brief.verdict, brief.story_bias, len(brief.links))
    return path


def read(day: date | None = None, *, root: Path | None = None) -> Brief | None:
    """Today's brief, or None. None means "behave exactly as before".

    Every failure here returns None rather than raising. The pipeline's daily
    run must not be taken down by a malformed advisory file: the worst outcome
    of a broken brief is a day that publishes what it would have published
    anyway, and that is a very cheap worst case to guarantee.
    """
    from .. import scheduling

    day = day or scheduling.today_ist()
    path = path_for(day, root=root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Brief(**raw)
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        log.warning("brief for %s is unusable, running the standing mix: %s",
                    day, exc)
        return None


def format_brief(brief: Brief) -> str:
    lines = [
        f"Brief             {brief.day}   campaign {brief.campaign}",
        f"Pace              {brief.verdict.replace('_', ' ').upper()}"
        + (f"   needs {brief.required_per_day:,.1f}/day" if brief.required_per_day else "")
        + (f", measured {brief.actual_per_day:,.1f}" if brief.actual_per_day is not None else ""),
        "",
        f"Make              {', '.join(brief.formats)}",
        f"Lead on           {brief.story_bias}",
        "",
        f"Tagged links      {len(brief.links)} of {len(brief.formats)} slots "
        f"({brief.attribution_share:.0%})",
    ]
    if brief.blind_slots:
        lines.append(f"Cannot be tagged  {', '.join(brief.blind_slots)}  "
                     f"(no clickable link on those surfaces)")
    if brief.experiments:
        lines.append("")
        lines.append("Experiments")
        for slot, arm in sorted(brief.experiments.items()):
            lines.append(f"  {slot:15} {arm}")
    lines += ["", "Why", f"  {brief.reason}", f"  evidence: {brief.evidence}"]
    if brief.refused:
        lines += ["", f"REFUSED ({len(brief.refused)})"]
        lines += [f"  * {r}" for r in brief.refused]
    return "\n".join(lines)
