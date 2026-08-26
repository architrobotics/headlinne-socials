"""The second view: where the signups came from.

Two properties carry this file.

**A ref that cannot be decoded is not guessed at.** `direct`, a stray referrer,
a truncated string - all land in `unattributed` rather than being distributed
across the channels. A wrong attribution is worse than an absent one, because
the wrong one is the one that gets acted on: it makes a channel look like it is
working and moves the day's slots onto it.

**An unreadable view is not an empty one.** `read_attribution` returns None when
it cannot be read, and None has to stay distinguishable from a reading in which
every channel happened to produce nothing. An empty list is the claim "every
channel failed", which is the conclusion that retires a working channel.
"""

from __future__ import annotations

import json
from datetime import date

from headlinne.cmo import attribution, ledger, metrics, portfolio
from headlinne.cmo.attribution import parse_ref
from tests.test_cmo_metrics import ROW, _Configured, _Session, _key

TODAY = date(2026, 10, 27)


# --------------------------------------------------------------------------- #
# The grant is still an aggregate
# --------------------------------------------------------------------------- #
def test_the_second_view_grants_select_and_exposes_no_person():
    sql = metrics.SETUP_SQL_ATTRIBUTION.lower()
    assert "grant select on public.cmo_attribution to anon" in sql
    assert "revoke all" in sql
    for forbidden in ("grant insert", "grant update", "grant delete", "grant all"):
        assert forbidden not in sql
    # A ref string and two counts. No id, no email, no per-person timestamp.
    for leak in ("email", "phone", "encrypted_password", "users.id"):
        assert leak not in sql
    assert "group by" in sql          # aggregated, not a row per user


def test_the_view_names_are_an_allowlist_not_a_parameter():
    assert metrics.VIEWS == {"cmo_metrics", "cmo_attribution"}
    try:
        metrics._get("auth.users")
    except metrics.MetricsError as exc:
        assert "not one of the granted views" in str(exc)
    else:
        raise AssertionError("an arbitrary relation was requested")


def test_neither_reader_exposes_the_view_it_reads():
    import inspect

    for func in (metrics.read, metrics.read_attribution):
        assert set(inspect.signature(func).parameters) == {"day", "session"}


def test_reading_attribution_issues_only_a_get():
    session = _Session([{"ref": "x1-0914", "signups": 3, "active": 2}])
    with _Configured():
        metrics.read_attribution(TODAY, session=session)
    assert [c[0] for c in session.calls] == ["GET"]
    assert session.calls[0][1].endswith("/rest/v1/cmo_attribution")


def test_the_read_is_bounded_so_a_redefined_view_cannot_become_a_large_read():
    session = _Session([{"ref": "x1-0914", "signups": 1}])
    with _Configured():
        metrics.read_attribution(TODAY, session=session)
    assert session.calls[0][2]["headers"]["Range"] == f"0-{metrics.MAX_REFS - 1}"


# --------------------------------------------------------------------------- #
# Unreadable is not empty
# --------------------------------------------------------------------------- #
def test_an_unconfigured_project_reads_as_unknown():
    with _Configured(key="", url=""):
        assert metrics.read_attribution(TODAY) is None


def test_a_failing_request_reads_as_unknown_rather_than_as_no_signups():
    class _Broken:
        def get(self, *a, **k):
            raise ConnectionError("no route to host")

    with _Configured():
        assert metrics.read_attribution(TODAY, session=_Broken()) is None


def test_a_project_without_the_second_view_still_reads_the_first():
    """The two grants are separate and so are their failures. A pace report has
    to keep working for someone who has only run the first block of SQL."""
    class _OnlyMetrics:
        def get(self, url, **kwargs):
            if url.endswith("cmo_attribution"):
                raise RuntimeError("relation does not exist")
            return _Session([ROW]).get(url, **kwargs)

    with _Configured():
        assert metrics.read(TODAY, session=_OnlyMetrics()) is not None
        assert metrics.read_attribution(TODAY, session=_OnlyMetrics()) is None


def test_unusable_rows_are_skipped_without_losing_the_readable_ones():
    session = _Session([{"ref": "x1-0914", "signups": 4},
                        {"ref": "broken"},                 # no signups
                        {"ref": "li-0914", "signups": "many"},
                        {"ref": "  ", "signups": 9}])       # empty ref
    with _Configured():
        refs = metrics.read_attribution(TODAY, session=session)
    assert [r.ref for r in refs] == ["x1-0914"]


# --------------------------------------------------------------------------- #
# Decoding a ref
# --------------------------------------------------------------------------- #
def test_the_compact_form_decodes_to_a_slot_a_channel_and_a_day():
    ref = parse_ref("x1-0914", today=TODAY)
    assert (ref.slot, ref.channel, ref.day) == ("x_1", "x", date(2026, 9, 14))
    assert ref.known is True


def test_the_utm_content_form_decodes_too():
    ref = parse_ref("2026-09-14-linkedin", today=TODAY)
    assert (ref.slot, ref.channel, ref.day) == ("linkedin", "linkedin",
                                                date(2026, 9, 14))


def test_a_bare_source_gives_a_channel_and_no_post():
    ref = parse_ref("linkedin", today=TODAY)
    assert ref.channel == "linkedin"
    assert ref.slot is None and ref.day is None
    assert ref.known is True


def test_an_experiment_arm_survives_the_round_trip():
    minted = attribution.ref_for(date(2026, 10, 27), "x_2", arm="b")
    ref = parse_ref(minted, today=TODAY)
    assert ref.arm == "b"
    assert ref.slot == "x_2"


def test_everything_we_mint_decodes_back_to_what_it_was_minted_for():
    """The round trip is the contract. A code added to SURFACES and forgotten in
    the decoder would land every signup from that surface in `unattributed`."""
    day = date(2026, 10, 27)
    for slot, surface in attribution.SURFACES.items():
        if surface.link is not attribution.Link.CLICKABLE:
            continue
        raw = (attribution.ref_for(day, slot) if surface.compact
               else attribution.content_for(day, slot))
        ref = parse_ref(raw, today=TODAY)
        assert ref.slot == slot, raw
        assert ref.channel == surface.source, raw
        assert ref.day == day, raw


def test_an_undecodable_ref_is_unknown_rather_than_guessed_at():
    for raw in ("direct", "", "nonsense-abc", "t.co/xyz", "x1"):
        assert parse_ref(raw, today=TODAY).known is False


def test_the_yearless_form_resolves_to_the_most_recent_past_date():
    """`0914` has no year. Resolved against today, which is unambiguous inside a
    twelve month window - and this campaign is four months long."""
    assert parse_ref("x1-0914", today=date(2026, 10, 1)).day == date(2026, 9, 14)
    # Read in January, a September ref still belongs to the year before.
    assert parse_ref("x1-0914", today=date(2027, 1, 5)).day == date(2026, 9, 14)
    # A January ref read in January is this year.
    assert parse_ref("x1-0102", today=date(2027, 1, 5)).day == date(2027, 1, 2)


def test_an_impossible_date_does_not_raise():
    assert parse_ref("x1-0230", today=TODAY).day is None
    assert parse_ref("x1-9999", today=TODAY).day is None


# --------------------------------------------------------------------------- #
# The ledger, and the join
# --------------------------------------------------------------------------- #
def _record(tmp_path, refs, day=TODAY):
    path = tmp_path / "attribution.jsonl"
    ledger.append_attribution(
        [metrics.RefCount(**r) for r in refs], day, path=path)
    return path


def test_a_reading_is_appended_whole_rather_than_row_by_row(tmp_path):
    """The view returns cumulative counts, so a reading only means anything as a
    set. Half of Tuesday's refs and half of Wednesday's is neither day."""
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 3},
                              {"ref": "direct", "signups": 40}])
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert len(json.loads(lines[0])["refs"]) == 2


def test_a_later_reading_supersedes_the_day_without_erasing_it(tmp_path):
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 3}])
    _record(tmp_path, [{"ref": "x1-0914", "signups": 5}])
    assert len(ledger.read_all(path=path)) == 2          # both on disk
    assert ledger.latest_attribution(path=path)[0]["signups"] == 5


def test_no_reading_is_none_rather_than_no_signups(tmp_path):
    assert ledger.latest_attribution(path=tmp_path / "nothing.jsonl") is None
    assert ledger.signups_by_channel(path=tmp_path / "nothing.jsonl") is None


def test_refs_collapse_into_channels(tmp_path):
    path = _record(tmp_path, [
        {"ref": "x1-0914", "signups": 3, "active": 2},
        {"ref": "x2-0915", "signups": 4, "active": 1},
        {"ref": "li-0914", "signups": 6, "active": 5},
    ])
    channels = ledger.signups_by_channel(path=path, today=TODAY)
    assert channels["x"] == {"signups": 7, "active": 3}
    assert channels["linkedin"] == {"signups": 6, "active": 5}


def test_undecodable_refs_are_pooled_rather_than_spread_across_channels(tmp_path):
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 3},
                              {"ref": "direct", "signups": 90},
                              {"ref": "some-referrer", "signups": 5}])
    channels = ledger.signups_by_channel(path=path, today=TODAY)
    assert channels["x"]["signups"] == 3
    assert channels["unattributed"]["signups"] == 95
    assert "direct" not in channels


def test_the_portfolio_joins_our_posts_to_their_signups(tmp_path):
    """Posts come from the committed content folder; signups come from the
    product. Neither side can supply the other's half."""
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 40}])
    channels = {c.name: c for c in portfolio.from_history(
        posts={"x": 20, "instagram": 60}, ledger_path=path, today=TODAY)}
    assert channels["x"].posts == 20
    assert channels["x"].signups == 40
    assert channels["x"].rate == 2.0
    assert channels["x"].status() == "measured"


def test_a_channel_absent_from_a_real_reading_is_a_measured_zero(tmp_path):
    """Once a reading exists, silence about a channel means it produced nothing.
    Before any reading exists, the same silence means nobody looked."""
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 40}])
    with_reading = {c.name: c for c in portfolio.from_history(
        posts={"linkedin": 30}, ledger_path=path, today=TODAY)}
    assert with_reading["linkedin"].signups == 0
    assert with_reading["linkedin"].status() == "measured"

    without = {c.name: c for c in portfolio.from_history(
        posts={"linkedin": 30}, ledger_path=tmp_path / "none.jsonl")}
    assert without["linkedin"].signups is None
    assert without["linkedin"].status() == "exploring"


def test_an_unmeasurable_channel_is_never_scored_a_zero(tmp_path):
    """Instagram is absent from every reading that will ever be taken, because
    no ref can be minted for it. Reading that absence as zero would give it a
    rate of 0.00, enter it in the performance allocation as the worst earner,
    and retire the surface carrying most of the audience."""
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 40}])
    channels = {c.name: c for c in portfolio.from_history(
        posts={"instagram": 90, "x": 20}, ledger_path=path, today=TODAY)}

    instagram = channels["instagram"]
    assert instagram.signups is None          # not 0
    assert instagram.rate is None             # not 0.00
    assert instagram.measured is False
    assert instagram.status() == "blind"


def test_a_blind_channel_cannot_join_the_performance_allocation(tmp_path):
    path = _record(tmp_path, [{"ref": "x1-0914", "signups": 40}])
    channels = portfolio.from_history(
        posts={"instagram": 90, "x": 20}, ledger_path=path, today=TODAY)
    earners = [c for c in channels if c.measured]
    assert all(c.measurable for c in earners)
    assert "instagram" not in {c.name for c in earners}


def test_posts_are_counted_from_the_committed_record():
    """The same evidence `headlinne status` reports distribution from, so it
    stays correct when the product is unreachable."""
    counts = portfolio.posts_by_channel(days=30)
    assert set(counts) <= {s.source for s in attribution.SURFACES.values()}
    assert all(isinstance(n, int) and n >= 0 for n in counts.values())
