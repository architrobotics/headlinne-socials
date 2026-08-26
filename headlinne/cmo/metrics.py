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
ATTRIBUTION_VIEW = "cmo_attribution"
VIEWS = frozenset({VIEW, ATTRIBUTION_VIEW})

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


# The second grant: where signups came from, and nothing about who they are.
#
# This is what turns "the number moved" into "the number moved because of that
# post". It needs one thing from the product that the first view did not: the
# signup flow has to keep the `r` or `utm_source` value off the landing URL and
# store it on the row. In Supabase auth the natural home is user metadata, set
# at signup with `options.data`, and the view below reads it from there - adapt
# the first expression to wherever your flow actually puts it.
#
# Note what is still absent. No id, no email, no timestamp per person: a ref
# string and two counts. Somebody who arrived from x_1 on 14 September is a `+1`
# on one row and cannot be picked back out of it.
SETUP_SQL_ATTRIBUTION = """-- Headlinne CMO: where signups came from. Ref strings and counts, no people.
create or replace view public.cmo_attribution
with (security_invoker = off) as
select
  coalesce(nullif(trim(raw_user_meta_data->>'ref'), ''), 'direct')  as ref,
  count(*)                                                          as signups,
  count(*) filter (
    where last_sign_in_at > now() - interval '30 days')             as active
from auth.users
group by 1;

revoke all on public.cmo_attribution from anon, authenticated;
grant select on public.cmo_attribution to anon;
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
# Where the signups came from
# --------------------------------------------------------------------------- #
# The attribution view can grow a row per ref, and a campaign mints one ref per
# post per day. Four months of that is a few hundred rows, which is fine - but
# the ceiling is here so a misconfigured view cannot turn a daily job into a
# large read of something nobody inspected.
MAX_REFS = 2000


@dataclass(frozen=True)
class RefCount:
    """One ref string and what it brought. Not a person, and cannot become one."""

    ref: str
    signups: int
    active: int = 0

    def to_dict(self) -> dict:
        return {"ref": self.ref, "signups": self.signups, "active": self.active}


def read_attribution(day: date | None = None, *,
                     session=None) -> list[RefCount] | None:
    """Signups grouped by the ref they arrived with. None when unreadable.

    None again means unknown, and it matters more here than anywhere else: an
    empty list is the claim "every channel produced nothing", which is the exact
    conclusion that would retire a working channel. A view that cannot be read
    has to be distinguishable from one that returns zeros.
    """
    rows = _get(ATTRIBUTION_VIEW, session=session, limit=MAX_REFS)
    if rows is None:
        return None

    out: list[RefCount] = []
    for row in rows:
        try:
            ref = str(row["ref"]).strip()
            if not ref:
                continue
            out.append(RefCount(ref=ref,
                                signups=int(row["signups"]),
                                active=int(row.get("active") or 0)))
        except (KeyError, TypeError, ValueError):
            log.warning("skipping an unusable attribution row: %r", row)
    if not out:
        return None
    log.info("attribution: %d refs, %d signups",
             len(out), sum(r.signups for r in out))
    return out
