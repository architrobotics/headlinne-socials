"""The CMO capability: one goal, measured, with a hand on the wheel.

Ten thousand users by 1 January 2027. The package is a layer *on top of* the
content factory rather than a change to it: it measures, decides and instructs,
and the one thing it writes into the factory's path is an optional daily brief.
Delete the layer and the pipeline runs exactly as it did before.

Read in this order, because each is worthless without the one before it:

    metrics.py      what is the number?         Supabase, read-only, aggregates
    ledger.py       what was it yesterday?      append-only, committed to git
    goal.py         what does that leave?       arithmetic, never a status field
    attribution.py  where did it come from?     and where that cannot be known
    portfolio.py    where does effort go?       returns where measured, else explore
    experiments.py  what are we testing?        stop rules fixed before the test
    policy.py       what may it do alone?       green, amber, red - and no flag
    brief.py        today's instruction         the hand on the wheel
    review.py       who needs telling, now?     the September escalation
    backlinks/      listings                    tailor, submit, verify

Two rules hold the whole thing together.

**The model may propose a strategy; it may never propose a measurement.** Every
figure in every report is read from the ledger. There is no code path by which a
generated number becomes a reported one, because a marketer that can narrate its
own progress will narrate success.

**Unknown is never zero.** An unreadable scoreboard, an unmeasurable channel and
an experiment short of its sample all report as unknown rather than as failure.
Zero is a claim about the world; unknown is a claim about what we looked at, and
the difference is most of what an honest growth report has to say.
"""

from .goal import Goal, Pace, required_weekly_growth
from .metrics import Snapshot
from .policy import Denied, Rung

__all__ = ["Denied", "Goal", "Pace", "Rung", "Snapshot",
           "required_weekly_growth"]
