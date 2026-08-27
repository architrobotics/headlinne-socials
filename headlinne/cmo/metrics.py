"""The scoreboard, read from Supabase. Four integers, and nothing else.

This is the only part of the system that can see the product, and it is
deliberately the narrowest thing that could work.

**It reads one view.** Not the users table, not auth.users, not events - one
view named `cmo_metrics` that returns a single row of aggregates. The SQL that
creates it is in `SETUP_SQL` below, and it is worth reading before granting
anything, because it is the actual boundary. A view that selects four counts
cannot leak an email address no matter what this module does with it, and that
is a much stronger guarantee than a promise in a docstring that we only ever
SELECT count(*). If the view is the grant, the grant is the aggregate.

**It cannot write.** Three separate reasons, because one would be a comment and
three are a design:

  1. Only GET is ever issued. There is no code path here that builds any other
     verb, so a bug cannot become a mutation.
  2. The URL is assembled from a constant view name. A caller cannot pass a
     path, so this cannot be pointed at another table by a config mistake or by
     a model that decided to be helpful.
  3. A `service_role` key is refused outright. That key bypasses row-level
     security and would make points 1 and 2 the only things standing between an
     autonomous marketing agent and the user table. `anon` is what belongs here,
     with SELECT granted on this one view and nothing else.

**A missing configuration is not an error.** The rest of the CMO has to keep
working when the product is unreachable - reporting "we cannot see the number"
is a legitimate and important state, and it is not the same as crashing. What
must never happen is that an unreadable scoreboard is quietly reported as zero
users, so `read()` returns None and the caller has to handle it.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ..config import SUPABASE_TIMEOUT, SUPABASE_URL, SECRETS
from ..logging_setup import get_logger

log = get_logger("cmo.metrics")

# The views this module may read. An allowlist, not a parameter: the public
# functions below take no view argument at all, so there is nothing a caller
# could pass to reach a third one.
VIEW = "cmo_metrics"
HOURLY_VIEW = "cmo_signups_hourly"
VIEWS = frozenset({VIEW, HOURLY_VIEW})

# Run this in the Supabase SQL editor. It is the whole grant.
#
# Note what is not here: no email, no id, no name, no row from any user table.
# `security_invoker = off` is deliberate - it lets the view aggregate tables the
# anon role cannot otherwise touch, which is what makes it possible to grant the
# aggregate without granting the source.
SETUP_SQL = """\
-- Headlinne CMO: the entire read surface. Four integers, one row.
create or replace view public.cmo_metrics
with (security_invoker = off) as
select
  (select count(*) from auth.users)                                  as users,
  (select count(*) from auth.users
     where last_sign_in_at > now() - interval '1 day')               as dau,
  (select count(*) from auth.users
     where last_sign_in_at > now() - interval '30 days')             as mau,
  (select count(*) from auth.users
     where created_at > now() - interval '1 day')                    as new_today,
  now()                                                              as as_of;

revoke all on public.cmo_metrics from anon, authenticated;
grant select on public.cmo_metrics to anon;
"""


# The second grant: when signups happened. Nothing else.
#
# This replaced a view that read a `ref` the signup flow was supposed to store,
# which would have meant changing the product's auth path. It does not, and it
# should not: the growth layer is not worth a change to the one code path that
# must never break.
#
# So attribution here is inferred rather than recorded. The pipeline does not
# publish every slot every day - `headlinne status` shows reels going out on 7
# of 30 days - and that irregularity is a natural experiment already sitting in
# the committed record. Signups per hour, joined to which slots actually
# published on which day, gives a contrast: what a day looks like with a reel
# against what it looks like without one.
#
# It buys something the link-based scheme could never have: **Instagram**. Three
# of the four things this pipeline makes go to surfaces with no clickable link,
# so no tag on earth would have measured them. A timestamp measures them all
# equally, because it does not care whether the reader could tap anything.
#
# What it costs is certainty. See `cmo/lift.py` - this is an estimate, it is
# correlational, and every number derived from it is labelled as one.
SETUP_SQL_HOURLY = """-- Headlinne CMO: when signups happened. A timestamp bucket and a count.
create or replace view public.cmo_signups_hourly
with (security_invoker = off) as
select
  date_trunc('hour', created_at) as hour,
  count(*)                       as signups
from auth.users
where created_at > now() - interval '180 days'
group by 1;

revoke all on public.cmo_signups_hourly from anon, authenticated;
grant select on public.cmo_signups_hourly to anon;
"""


class MetricsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    """One reading. `day` is the IST day it was taken on, so it lines up with
    everything else in this repository, which is scheduled in IST."""

    day: date
    users: int
    dau: int
    mau: int
    new_today: int = 0
    as_of: str = ""

    @property
    def activation(self) -> float | None:
        return self.mau / self.users if self.users and self.mau else None

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "users": self.users,
            "dau": self.dau,
            "mau": self.mau,
            "new_today": self.new_today,
            "as_of": self.as_of,
            "source": "supabase",
        }


def _jwt_role(key: str) -> str | None:
    """The `role` claim inside a Supabase key, without verifying the signature.

    We are not authenticating anything here, we are refusing to *use* a key that
    is too powerful. Reading the claim is enough for that, and verifying it would
    need a secret we deliberately do not have.
    """
    parts = key.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)      # base64url needs its padding back
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    role = claims.get("role")
    return role if isinstance(role, str) else None


def check_key(key: str) -> None:
    """Raise unless this key is safe to hand to an autonomous marketing agent."""
    role = _jwt_role(key)
    if role == "service_role":
        raise MetricsError(
            "SUPABASE_KEY is a service_role key. That key bypasses row-level "
            "security and can read and write every table in the project, which "
            "is not something this system should hold. Use the anon key and "
            "grant it SELECT on the cmo_metrics view only "
            "(headlinne.cmo.metrics.SETUP_SQL creates it).")


def configured() -> bool:
    return bool(SUPABASE_URL and SECRETS.supabase_key)


def _get(view: str, *, session=None, limit: int = 1) -> list[dict] | None:
    """GET one allowlisted view. The only request this module ever makes.

    `view` is checked against VIEWS rather than trusted, because this is the one
    place a string reaches a URL. Neither public reader exposes the argument, so
    the check guards against a future call site rather than a caller - which is
    exactly the kind of guard worth keeping, since the future call site is the
    one nobody reviews with this file open.
    """
    if view not in VIEWS:
        raise MetricsError(
            f"{view!r} is not one of the granted views ({sorted(VIEWS)}). "
            f"This module reads aggregates and cannot be pointed at a table.")
    if not configured():
        log.info("Supabase is not configured; the scoreboard is unreadable.")
        return None

    key = SECRETS.supabase_key
    check_key(key)

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{view}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        # Bounded on purpose. A view later redefined to return many rows cannot
        # turn this into a large read.
        "Range": f"0-{max(0, limit - 1)}",
    }
    try:
        if session is None:
            import requests

            session = requests
        # GET, always and only. Nothing in this module constructs another verb.
        resp = session.get(url, headers=headers, params={"select": "*"},
                           timeout=SUPABASE_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # noqa: BLE001 - an unreadable scoreboard is a state
        log.warning("could not read %s: %s", view, exc)
        return None

    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        log.warning("the %s view returned no rows.", view)
        return None
    return rows


def read(day: date | None = None, *, session=None) -> Snapshot | None:
    """Read the scoreboard. Returns None when it cannot be read.

    None is a real answer and callers must render it as "unknown", never as
    zero. A marketing report that prints 0 users because a token expired is
    worse than one that prints nothing, because somebody will act on it.
    """
    from .. import scheduling

    day = day or scheduling.today_ist()
    rows = _get(VIEW, session=session)
    if rows is None:
        return None

    row = rows[0]
    try:
        snapshot = Snapshot(
            day=day,
            users=int(row["users"]),
            dau=int(row.get("dau") or 0),
            mau=int(row.get("mau") or 0),
            new_today=int(row.get("new_today") or 0),
            as_of=str(row.get("as_of") or datetime.now(timezone.utc).isoformat()),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("the cmo_metrics view returned an unusable row: %s", exc)
        return None

    log.info("scoreboard: %s users, %s DAU, %s MAU",
             snapshot.users, snapshot.dau, snapshot.mau)
    return snapshot


# --------------------------------------------------------------------------- #
# When the signups happened
# --------------------------------------------------------------------------- #
# 180 days of hourly buckets is 4,320 rows at the absolute ceiling, and in
# practice far fewer because an hour with no signups produces no row at all.
# The cap is here so a view later redefined to return something else cannot
# turn a daily job into a large read.
MAX_BUCKETS = 6000


@dataclass(frozen=True)
class Bucket:
    """One hour, and how many people signed up in it."""

    hour: datetime
    signups: int

    def to_dict(self) -> dict:
        return {"hour": self.hour.isoformat(), "signups": self.signups}


def read_hourly(session=None) -> list[Bucket] | None:
    """Signups per hour. None when the view cannot be read.

    None again means unknown rather than none, and it matters here for the same
    reason as everywhere else: an empty list is the claim that nobody signed up,
    which is a claim about the product rather than about the reading.
    """
    rows = _get(HOURLY_VIEW, session=session, limit=MAX_BUCKETS)
    if rows is None:
        return None

    out: list[Bucket] = []
    for row in rows:
        try:
            raw = str(row["hour"]).replace("Z", "+00:00")
            when = datetime.fromisoformat(raw)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            out.append(Bucket(hour=when, signups=int(row["signups"])))
        except (KeyError, TypeError, ValueError):
            log.warning("skipping an unusable hourly row: %r", row)
    if not out:
        return None
    out.sort(key=lambda b: b.hour)
    log.info("hourly: %d buckets, %d signups",
             len(out), sum(b.signups for b in out))
    return out
