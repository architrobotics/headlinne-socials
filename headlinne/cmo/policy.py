"""What the CMO may do alone, what it may do and then confess to, and what it
may never do at all.

Autonomy is a function of reversibility, not of confidence. An agent that picks
today's story badly costs one day; an agent that creates an account, spends
money or gets the domain banned costs something that cannot be handed back. So
the ladder here is sorted by how hard the action is to undo, and nothing else.

    GREEN   reversible and self-contained. Acts, logs, does not ask.
    AMBER   reversible but consequential, or bounded by a cap. Acts, then writes
            what it did and why into the weekly review, where a human can revert
            it with one commit.
    RED     refused in code. Not a permission that can be granted later by
            setting a flag - there is no flag.

**Money is RED and the budget is zero.** The founder said no money, so `spend`
is not a capped amber action with a ceiling of nothing, it is a refusal. The
difference matters: a cap of zero invites someone to raise the cap, and a
refusal invites a conversation.

**The caps are the anti-spam core, and they are the same shape as the ones in
`reddit/policy.py`.** A configurable cap with a hard maximum above it that
configuration cannot raise. That pattern is already proven in this repository
and it is what stops an enthusiastic allocator from turning a channel into a
ban.

Every amber action is recorded in `state/cmo/decisions.jsonl`, append-only, for
the same reason the ledger is: "acts, then announces" is only true if the
announcement is written down at the moment of acting rather than reconstructed
later from what someone remembers deciding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

from ..config import STATE_DIR
from ..logging_setup import get_logger

log = get_logger("cmo.policy")

DECISIONS_PATH = STATE_DIR / "cmo" / "decisions.jsonl"


class Rung(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


@dataclass(frozen=True)
class Action:
    name: str
    rung: Rung
    why: str
    # Amber only. The most times this may happen in one day, whatever any
    # allocator thinks it wants.
    cap: int = 0


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #
ACTIONS: dict[str, Action] = {a.name: a for a in (
    # ---- green: undone by a revert, or by tomorrow ----
    Action("choose_story", Rung.GREEN,
           "one day's editorial call, superseded tomorrow"),
    Action("choose_format", Rung.GREEN,
           "which of the existing formats carries the day"),
    Action("choose_time", Rung.GREEN, "a posting slot inside the existing day"),
    Action("write_copy", Rung.GREEN,
           "the words, inside limits the code enforces afterwards"),
    Action("mint_link", Rung.GREEN, "a tagged URL. Costs nothing, breaks nothing"),
    Action("assign_experiment", Rung.GREEN,
           "which arm a post gets, inside a registered experiment"),
    Action("cross_post", Rung.GREEN,
           "an already-approved asset to an already-connected surface"),
    Action("reallocate_effort", Rung.GREEN,
           "moving slots between channels that are already running"),
    Action("write_review", Rung.GREEN, "words about numbers it did not choose"),
    Action("build_queue", Rung.GREEN, "drafting listing copy. Submits nothing"),

    # ---- amber: acts, then says so, and is capped ----
    Action("publish_new_surface", Rung.AMBER,
           "first post to a surface nobody has seen us on. Reversible by "
           "deleting it, and worth knowing about", cap=1),
    Action("change_cadence", Rung.AMBER,
           "changing how many posts a day go out. Cheap to revert and easy to "
           "drift, so it is announced", cap=1),
    Action("retire_channel", Rung.AMBER,
           "stopping a channel that has under-returned for weeks", cap=1),
    Action("submit_listing", Rung.AMBER,
           "an API submission to a directory that permits it", cap=3),

    # ---- red: refused, with no flag that changes it ----
    Action("spend", Rung.RED,
           "there is no budget. A cap of zero invites raising the cap; a "
           "refusal invites a conversation"),
    Action("create_account", Rung.RED, "identity, and it needs credentials"),
    Action("enter_credentials", Rung.RED,
           "never, on anyone's behalf, for any reason"),
    Action("speak_as_founder", Rung.RED,
           "a person's own voice is not a channel this can operate"),
    Action("direct_message", Rung.RED,
           "one-to-one outreach is a person writing to a person"),
    Action("change_positioning", Rung.RED,
           "what the product claims to be is not a growth lever to be tuned"),
    Action("automate_prohibited", Rung.RED,
           "platforms that ban by domain. The archive is the asset that would "
           "be lost, and it does not come back"),
    Action("buy_engagement", Rung.RED,
           "followers, votes, pods, churn. Would move the metric and nothing "
           "else, which is the definition of the thing this is built to avoid"),
    Action("incentivise_signup", Rung.RED,
           "a giveaway reaches 10,000 and produces nothing. Run one if you "
           "like, but it may not be counted, and this cannot run one"),
)}


class Denied(RuntimeError):
    """Raised when an action is refused. Carries the reason, not a code."""


@dataclass(frozen=True)
class Decision:
    action: str
    rung: Rung
    allowed: bool
    why: str
    announce: bool = False


def check(action: str, *, done_today: int = 0) -> Decision:
    """May this happen? Green yes, amber yes-and-tell, red no.

    An unknown action is refused. Defaulting to permitted would mean every new
    capability arrives with full autonomy by accident, which is exactly the
    failure this module exists to prevent.
    """
    known = ACTIONS.get(action)
    if known is None:
        return Decision(action, Rung.RED, False,
                        f"{action!r} is not in the policy. An action nobody has "
                        f"classified is refused rather than assumed harmless.")

    if known.rung is Rung.RED:
        return Decision(action, Rung.RED, False,
                        f"{action} is never done autonomously: {known.why}.")

    if known.rung is Rung.AMBER:
        if done_today >= known.cap:
            return Decision(action, Rung.AMBER, False,
                            f"{action} is capped at {known.cap} a day and has "
                            f"already happened {done_today} times today.")
        return Decision(action, Rung.AMBER, True, known.why, announce=True)

    return Decision(action, Rung.GREEN, True, known.why)


def require(action: str, *, done_today: int = 0) -> Decision:
    """check(), but raises. For call sites where refusal must stop the work."""
    decision = check(action, done_today=done_today)
    if not decision.allowed:
        raise Denied(decision.why)
    return decision


# --------------------------------------------------------------------------- #
# "Acts, then announces" only counts if the announcement is written down
# --------------------------------------------------------------------------- #
def record(decision: Decision, detail: str = "", *, day: date | None = None,
           path: Path | None = None) -> None:
    """Append an amber decision to the log the weekly review reads from.

    The day is IST, like every other date in this repository. `date.today()` is
    whatever the runner's clock says, and GitHub's runners are UTC - so an amber
    action taken during the IST evening lands on the previous day and drops out
    of the window the review asks for, which is how an announcement gets made
    and never read.
    """
    if not decision.announce:
        return
    day = day or _today()
    path = path or DECISIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "at": datetime.now(timezone.utc).isoformat(),
            "day": day.isoformat(),
            "action": decision.action,
            "rung": decision.rung.value,
            "why": decision.why,
            "detail": detail,
        }, sort_keys=True) + "\n")
    log.info("amber: %s (%s)", decision.action, detail or decision.why)


def decisions(since: date | None = None, *,
              path: Path | None = None) -> list[dict]:
    """Amber actions taken, for the review to report. Newest last."""
    path = path or DECISIONS_PATH
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and row.get("day", "") < since.isoformat():
            continue
        out.append(row)
    return out


def _today() -> date:
    """IST, matching the rest of the system. Falls back if scheduling moves."""
    try:
        from ..scheduling import today_ist

        return today_ist()
    except Exception:  # pragma: no cover - a clock is not worth failing over
        return date.today()


def count_today(action: str, today: date | None = None, *,
                path: Path | None = None) -> int:
    today = today or _today()
    return sum(1 for row in decisions(path=path)
               if row.get("action") == action and row.get("day") == today.isoformat())
