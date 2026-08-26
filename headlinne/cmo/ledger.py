"""The append-only record. Every number the CMO ever quotes comes from here.

One line of JSON per reading, in `state/cmo/ledger.jsonl`, committed to git like
everything else in this repository. That choice does most of the work: the
history is diffable, it survives the pipeline being broken, and a number that
changed can be traced to the commit that changed it.

**Append-only, and it means it.** A reading is never edited and never deleted.
Re-reading a day appends a second line, and the later line wins when the ledger
is collapsed into a series. The superseded line stays, which is the difference
between a record and a whiteboard. It costs a few bytes a day and it is the only
reason anyone can check, in December, what the September number actually said
rather than what it says now.

**Why this exists at all**, when Supabase already holds the truth: because the
truth it holds is *current*. `count(*)` answers "how many users are there", and
it cannot answer "how many were there on 14 September", which is the question
every pace calculation is made of. A product that never stored its own history
still has one here, from the first day this ran.

The one rule the rest of the CMO depends on: **no number reaches a report
without passing through this file.** A model can propose a strategy; it cannot
propose a measurement.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import STATE_DIR
from ..logging_setup import get_logger
from .metrics import Snapshot

log = get_logger("cmo.ledger")

LEDGER_DIR = STATE_DIR / "cmo"
LEDGER_PATH = LEDGER_DIR / "ledger.jsonl"


def append(snapshot: Snapshot, *, path: Path | None = None) -> Path:
    """Record one reading. Never rewrites, never reorders."""
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    row = snapshot.to_dict()
    row["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    log.info("ledger += %s users on %s", snapshot.users, snapshot.day)
    return path


def read_all(*, path: Path | None = None) -> list[dict]:
    """Every line, in the order written. Unreadable lines are skipped loudly.

    A corrupt line must not take the file down with it: a half-written row from
    a runner that was killed mid-append is a recoverable event, and losing four
    months of history to it would not be.
    """
    path = path or LEDGER_PATH
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("ledger line %d is not valid JSON; skipping it.", n)
    return rows


def series(*, path: Path | None = None) -> list[dict]:
    """One row per day, latest reading wins, oldest first."""
    by_day: dict[str, dict] = {}
    for row in read_all(path=path):
        day = row.get("day")
        if day:
            by_day[day] = row       # a later line for the same day supersedes
    return [by_day[d] for d in sorted(by_day)]


def latest(*, path: Path | None = None) -> dict | None:
    rows = series(path=path)
    return rows[-1] if rows else None


def baseline(*, path: Path | None = None) -> dict | None:
    """The first reading ever taken. The zero the whole plan is measured from.

    Deliberately the first *recorded* day rather than the campaign's start date.
    If measurement began late, the honest baseline is the first number anyone
    actually saw, and pretending otherwise would credit the campaign with users
    it did not bring.
    """
    rows = series(path=path)
    return rows[0] if rows else None


def gained_per_day(days: int = 7, *, path: Path | None = None) -> float | None:
    """Measured signups per day across the last `days` **days** of readings.

    Days, not readings. Those coincide when the scheduled job runs daily, which
    is the normal case and therefore the case where the difference is invisible.
    They come apart the moment a run is missed or a backfill lands: slicing the
    last eight *rows* off a weekly ledger silently reports the average over two
    months and calls it a trailing week, which flatters a bad week and buries a
    good one.

    The window is anchored on the newest reading rather than on today, so a
    stale ledger reports the pace it actually measured instead of dividing real
    growth by days it never saw.

    Returns None rather than 0.0 when there are not two readings far enough
    apart to divide by. Zero is a claim about the product; None is a claim about
    the ledger, and the report says different things about each.
    """
    rows = []
    for row in series(path=path):
        try:
            rows.append((date.fromisoformat(row["day"]), row["users"]))
        except (KeyError, ValueError, TypeError):
            continue
    if len(rows) < 2:
        return None

    cutoff = rows[-1][0] - timedelta(days=days)
    window = [r for r in rows if r[0] >= cutoff]
    if len(window) < 2:
        # Nothing else inside the window: fall back to the reading immediately
        # before it, so a weekly ledger still yields a rate rather than None.
        window = rows[-2:]

    (first_day, first_users), (last_day, last_users) = window[0], window[-1]
    span = (last_day - first_day).days
    if span <= 0:
        return None
    return (last_users - first_users) / span


# --------------------------------------------------------------------------- #
# Where the signups came from
# --------------------------------------------------------------------------- #
ATTRIBUTION_PATH = LEDGER_DIR / "attribution.jsonl"


def append_attribution(refs, day: date, *, path: Path | None = None) -> Path:
    """Record one reading of the attribution view. Append-only, like the rest.

    One line holds the whole reading rather than one line per ref. The view
    returns cumulative counts, so a reading only means anything as a set: half
    of Tuesday's refs and half of Wednesday's is not a picture of either day.
    """
    path = path or ATTRIBUTION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "day": day.isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "refs": [r.to_dict() for r in refs],
        "source": "supabase",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    log.info("attribution += %d refs on %s", len(row["refs"]), day)
    return path


def attribution_series(*, path: Path | None = None) -> list[dict]:
    """One reading per day, latest wins, oldest first."""
    by_day: dict[str, dict] = {}
    for row in read_all(path=path or ATTRIBUTION_PATH):
        day = row.get("day")
        if day and isinstance(row.get("refs"), list):
            by_day[day] = row
    return [by_day[d] for d in sorted(by_day)]


def latest_attribution(*, path: Path | None = None) -> list[dict] | None:
    """The most recent reading's refs, or None when there has never been one.

    None rather than an empty list, and the distinction is the whole point: an
    empty list is the claim that every channel produced nothing, which is the
    conclusion that retires a working channel.
    """
    rows = attribution_series(path=path)
    return rows[-1]["refs"] if rows else None


def signups_by_channel(*, path: Path | None = None,
                       today: date | None = None) -> dict[str, dict] | None:
    """Signups and active users per channel, from the latest reading.

    Refs we never minted - `direct`, a stray referrer, a truncated string - are
    collected under `unattributed` rather than distributed across the channels.
    Guessing which channel an unreadable ref belongs to would produce a number
    that looks measured and is invented, and the invented one gets acted on.
    """
    from . import attribution as attr

    refs = latest_attribution(path=path)
    if refs is None:
        return None

    out: dict[str, dict] = {}
    for row in refs:
        parsed = attr.parse_ref(str(row.get("ref", "")), today=today)
        name = parsed.channel or "unattributed"
        bucket = out.setdefault(name, {"signups": 0, "active": 0})
        bucket["signups"] += int(row.get("signups") or 0)
        bucket["active"] += int(row.get("active") or 0)
    return out
