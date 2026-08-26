"""The read-only guarantee, and the refusal to invent a number.

Two properties are worth a test each, and neither is about correctness in the
ordinary sense. They are about what this module is permitted to do at all.

**It cannot write, and it cannot be pointed somewhere else.** Only GET is ever
issued, the path is built from a constant view name, and a service_role key is
refused outright. That last one matters most: an anon key with SELECT on one
aggregate view cannot read a user row even if every other line here were wrong,
while a service_role key would make the whole guarantee a matter of trust.

**An unreadable scoreboard is never reported as zero.** A marketing report that
prints "0 users" because a token expired is worse than one that prints nothing,
because somebody will act on it.
"""

from __future__ import annotations

import base64
import json
from datetime import date

from headlinne.cmo import metrics


# --------------------------------------------------------------------------- #
# A fake Supabase that records exactly how it was called
# --------------------------------------------------------------------------- #
class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    """Answers GET and records the call. Every other verb raises, because a
    mutation attempt should fail loudly in a test rather than be mocked away."""

    def __init__(self, payload, status=200):
        self.payload, self.status, self.calls = payload, status, []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _Response(self.payload, self.status)

    def _forbidden(self, *a, **k):
        raise AssertionError("cmo.metrics attempted a write")

    post = put = patch = delete = _forbidden


def _key(role: str = "anon") -> str:
    """A Supabase-shaped JWT. Only the payload matters; nothing verifies it."""
    def seg(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{seg({'alg': 'HS256'})}.{seg({'role': role, 'iss': 'supabase'})}.sig"


class _Configured:
    """Point the module at a fake project for the duration of a block."""

    def __init__(self, key=None, url="https://proj.supabase.co"):
        self.key, self.url = key if key is not None else _key("anon"), url

    def __enter__(self):
        from headlinne import config
        self.saved = (config.SUPABASE_URL, config.SECRETS.supabase_key)
        config.SUPABASE_URL = metrics.SUPABASE_URL = self.url
        object.__setattr__(config.SECRETS, "supabase_key", self.key)
        return self

    def __exit__(self, *exc):
        from headlinne import config
        config.SUPABASE_URL = metrics.SUPABASE_URL = self.saved[0]
        object.__setattr__(config.SECRETS, "supabase_key", self.saved[1])
        return False


ROW = {"users": 1234, "dau": 88, "mau": 460, "new_today": 17,
       "as_of": "2026-09-14T06:00:00+00:00"}


# --------------------------------------------------------------------------- #
# It cannot write, and it cannot be aimed anywhere else
# --------------------------------------------------------------------------- #
def test_only_get_is_ever_issued():
    session = _Session([ROW])
    with _Configured():
        metrics.read(date(2026, 9, 14), session=session)
    assert [c[0] for c in session.calls] == ["GET"]


def test_it_reads_one_view_and_the_name_is_not_a_parameter():
    session = _Session([ROW])
    with _Configured():
        metrics.read(date(2026, 9, 14), session=session)
    _, url, kwargs = session.calls[0]
    assert url == "https://proj.supabase.co/rest/v1/cmo_metrics"
    assert metrics.VIEW == "cmo_metrics"
    # One row is all the view holds, and asking for one anyway means a view
    # later redefined to return many cannot turn this into a large read.
    assert kwargs["headers"]["Range"] == "0-0"


def test_read_takes_no_argument_that_could_change_what_it_reads():
    """The guarantee is structural: there is no table, path, query or filter
    parameter to pass, so a caller cannot aim this at auth.users."""
    import inspect

    names = set(inspect.signature(metrics.read).parameters)
    assert names == {"day", "session"}


def test_a_service_role_key_is_refused():
    """That key bypasses row-level security and can read and write every table
    in the project. Holding it would make every other guarantee here a promise
    rather than a grant."""
    try:
        metrics.check_key(_key("service_role"))
    except metrics.MetricsError as exc:
        assert "service_role" in str(exc)
        assert "anon" in str(exc)
    else:
        raise AssertionError("a service_role key was accepted")


def test_an_anon_key_is_accepted():
    metrics.check_key(_key("anon"))          # must not raise


def test_a_key_that_is_not_a_jwt_is_not_mistaken_for_a_service_key():
    """Refusing has to be driven by a claim we actually read. An unparseable
    key is unknown, not privileged, and guessing either way would be wrong."""
    assert metrics._jwt_role("not-a-jwt") is None
    assert metrics._jwt_role("a.b.c") is None
    metrics.check_key("sb_publishable_abc123")   # newer key format, must not raise


def test_the_setup_sql_grants_select_on_the_view_and_nothing_else():
    sql = metrics.SETUP_SQL.lower()
    assert "grant select on public.cmo_metrics to anon" in sql
    assert "revoke all" in sql
    for forbidden in ("grant insert", "grant update", "grant delete", "grant all"):
        assert forbidden not in sql
    # The view exposes counts. If a column ever names a user, the grant stops
    # being an aggregate and this test is the thing that should notice.
    for leak in ("email", "raw_user_meta", "phone", "encrypted_password"):
        assert leak not in sql


# --------------------------------------------------------------------------- #
# Unknown is never zero
# --------------------------------------------------------------------------- #
def test_an_unconfigured_project_reads_as_unknown_not_as_zero_users():
    with _Configured(key="", url=""):
        assert metrics.configured() is False
        assert metrics.read(date(2026, 9, 14)) is None


def test_a_failing_request_reads_as_unknown():
    class _Broken:
        def get(self, *a, **k):
            raise ConnectionError("no route to host")

    with _Configured():
        assert metrics.read(date(2026, 9, 14), session=_Broken()) is None


def test_an_http_error_reads_as_unknown():
    with _Configured():
        assert metrics.read(date(2026, 9, 14),
                            session=_Session([], status=401)) is None


def test_an_empty_or_malformed_view_reads_as_unknown():
    with _Configured():
        assert metrics.read(date(2026, 9, 14), session=_Session([])) is None
        assert metrics.read(date(2026, 9, 14),
                            session=_Session([{"dau": 1}])) is None    # no users
        assert metrics.read(date(2026, 9, 14),
                            session=_Session([{"users": "many"}])) is None


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #
def test_a_good_row_becomes_a_snapshot():
    with _Configured():
        snap = metrics.read(date(2026, 9, 14), session=_Session([ROW]))
    assert (snap.users, snap.dau, snap.mau, snap.new_today) == (1234, 88, 460, 17)
    assert snap.day == date(2026, 9, 14)
    assert round(snap.activation, 4) == round(460 / 1234, 4)


def test_a_single_object_response_is_accepted_as_one_row():
    """PostgREST returns an object rather than a list when the client asks for
    a single row, and the view is a single row."""
    with _Configured():
        snap = metrics.read(date(2026, 9, 14), session=_Session(ROW))
    assert snap.users == 1234


def test_missing_optional_counts_default_to_zero_but_users_never_does():
    with _Configured():
        snap = metrics.read(date(2026, 9, 14), session=_Session([{"users": 5}]))
    assert (snap.users, snap.dau, snap.mau) == (5, 0, 0)
    assert snap.activation is None       # not 0.0: unknown engagement is unknown
