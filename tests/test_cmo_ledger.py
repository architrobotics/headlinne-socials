"""The ledger is append-only, and the report cannot outrun it.

The ledger is the reason a figure in a growth update can be checked in December
against what September actually said. That only holds if two things are true:
nothing is ever rewritten, and no report can quote a number the ledger does not
contain.

The second one is the load-bearing test in this file. An autonomous marketer
that can generate its own progress figures will generate good ones, so the
report has to be structurally incapable of it - `build()` reads the ledger and
only the ledger, and when the ledger is empty it says so instead of estimating.
"""

from __future__ import annotations

import json
from datetime import date

from headlinne.cmo import ledger, report
from headlinne.cmo.metrics import Snapshot


def _snap(day: str, users: int, *, dau=0, mau=0) -> Snapshot:
    return Snapshot(day=date.fromisoformat(day), users=users, dau=dau, mau=mau)


# --------------------------------------------------------------------------- #
# Append-only
# --------------------------------------------------------------------------- #
def test_a_reading_is_appended_and_nothing_before_it_moves(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    first = path.read_text(encoding="utf-8")
    ledger.append(_snap("2026-09-02", 140), path=path)
    after = path.read_text(encoding="utf-8")

    assert after.startswith(first)              # the first line is byte-identical
    assert len(after.splitlines()) == 2


def test_re_reading_a_day_supersedes_it_without_erasing_it(tmp_path):
    """A corrected number must not remove the number it corrected. That record
    is the whole reason for keeping a ledger rather than a current value."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    ledger.append(_snap("2026-09-01", 118), path=path)

    assert len(ledger.read_all(path=path)) == 2        # both survive on disk
    series = ledger.series(path=path)
    assert len(series) == 1 and series[0]["users"] == 118


def test_every_row_carries_when_it_was_recorded(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["recorded_at"] and row["source"] == "supabase"


def test_one_corrupt_line_does_not_take_the_history_with_it(tmp_path):
    """A runner killed mid-append leaves a half-written row. Losing four months
    of history to it would not be a recoverable event."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"day": "2026-09-02", "users": 12\n')      # truncated
    ledger.append(_snap("2026-09-03", 300), path=path)

    rows = ledger.series(path=path)
    assert [r["users"] for r in rows] == [100, 300]


def test_an_absent_ledger_is_empty_rather_than_an_error(tmp_path):
    path = tmp_path / "nothing.jsonl"
    assert ledger.read_all(path=path) == []
    assert ledger.latest(path=path) is None
    assert ledger.baseline(path=path) is None


# --------------------------------------------------------------------------- #
# The measured pace
# --------------------------------------------------------------------------- #
def test_the_baseline_is_the_first_number_anyone_actually_saw(tmp_path):
    """Not the campaign's start date. If measurement began late, crediting the
    campaign with the users that predate it would be inventing growth."""
    path = tmp_path / "ledger.jsonl"
    for day, users in [("2026-09-10", 400), ("2026-09-11", 430)]:
        ledger.append(_snap(day, users), path=path)
    assert ledger.baseline(path=path)["day"] == "2026-09-10"
    assert ledger.baseline(path=path)["users"] == 400


def test_the_pace_is_measured_across_the_days_between_readings(tmp_path):
    path = tmp_path / "ledger.jsonl"
    for i, users in enumerate([100, 120, 140, 160, 180]):
        ledger.append(_snap(f"2026-09-0{i + 1}", users), path=path)
    assert ledger.gained_per_day(7, path=path) == 20.0     # 80 users / 4 days


def test_gaps_in_the_readings_are_divided_by_days_not_by_readings(tmp_path):
    """Two readings a fortnight apart is 14 days of growth, not one."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    ledger.append(_snap("2026-09-15", 240), path=path)
    assert ledger.gained_per_day(30, path=path) == 10.0


def test_the_trailing_window_is_days_not_readings(tmp_path):
    """A ledger with a gap in it. Slicing the last N rows off would average
    across the whole history and call it a trailing week, which flatters a bad
    week and buries a good one."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)      # long before
    ledger.append(_snap("2026-10-20", 700), path=path)      # inside the window
    ledger.append(_snap("2026-10-27", 770), path=path)

    # 70 users over the 7 days in the window, not 670 over 56 days of history.
    assert ledger.gained_per_day(7, path=path) == 10.0
    # A wide enough window does take the whole history: 670 over 56 days.
    assert round(ledger.gained_per_day(90, path=path), 1) == 12.0


def test_a_window_with_one_reading_falls_back_to_the_reading_before_it(tmp_path):
    """A weekly ledger asked for a 7 day window has one row inside it. That has
    to yield a rate, not None - the readings are sparse, not absent."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    ledger.append(_snap("2026-09-15", 240), path=path)
    assert ledger.gained_per_day(3, path=path) == 10.0


def test_the_window_is_anchored_on_the_newest_reading_not_on_today(tmp_path):
    """A ledger that stopped updating must report the pace it measured, not
    real growth divided by days nobody looked."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    ledger.append(_snap("2026-09-08", 240), path=path)
    assert ledger.gained_per_day(7, path=path) == 20.0


def test_a_single_reading_gives_no_pace_rather_than_a_pace_of_zero(tmp_path):
    """Zero is a claim about the product. None is a claim about the ledger, and
    the report has to say different things about each."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 100), path=path)
    assert ledger.gained_per_day(7, path=path) is None


# --------------------------------------------------------------------------- #
# No report can outrun the ledger
# --------------------------------------------------------------------------- #
def test_an_empty_ledger_produces_no_pace_and_says_why(tmp_path):
    reading = report.build(date(2026, 10, 1),
                           path=tmp_path / "ledger.jsonl", fetch=False)
    assert reading.pace is None
    assert reading.readings == 0
    assert "never been read" in reading.reason
    text = report.format_report(reading)
    assert "unreadable" in text
    assert "0 users" not in text and "10,000 users" not in text


def test_the_json_form_of_an_empty_ledger_is_explicitly_unreadable(tmp_path):
    reading = report.build(date(2026, 10, 1),
                           path=tmp_path / "ledger.jsonl", fetch=False)
    data = json.loads(report.as_json(reading))
    assert data["readable"] is False
    assert "users" not in data           # no zero to be quoted by mistake


def test_the_report_reads_its_figures_from_the_ledger(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 200, mau=120), path=path)
    ledger.append(_snap("2026-09-08", 480, mau=280), path=path)

    reading = report.build(date(2026, 9, 8), path=path, fetch=False)
    p = reading.pace
    assert p.baseline == 200 and p.users == 480
    assert p.gained == 280
    assert p.actual_per_day == 40.0                  # 280 users over 7 days
    assert round(p.baseline_activation, 2) == 0.60
    assert reading.readings == 2

    text = report.format_report(reading)
    assert "480" in text and "SLIPPING" in text


def test_a_report_never_fetches_when_it_is_told_not_to(tmp_path):
    """The scheduled check runs without credentials. It must report from the
    committed ledger rather than reporting nothing."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(_snap("2026-09-01", 200), path=path)
    reading = report.build(date(2026, 9, 2), path=path, fetch=False)
    assert reading.snapshot is None                  # nothing was read
    assert reading.pace is not None and reading.pace.users == 200
