"""Guards for the distribution health report.

The report exists because the pipeline's contained-failure behaviour is right
for one bad format on one day and wrong as a way of finding out that a fortnight
went by with no reel. These tests pin the two things it has to get right: it
must notice silence, and it must not count a busy owned surface as reach.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from headlinne import health


def _day(root, day: date, *, generated=True, published=()):
    """Write a day of content the way the pipeline would leave it."""
    folder = root / day.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    if generated:
        (folder / "plan.json").write_text(json.dumps({"day": day.isoformat()}))
    if published:
        pub = folder / "published"
        pub.mkdir(exist_ok=True)
        for slot in published:
            (pub / f"{slot}.json").write_text("{}")


def test_a_silent_run_of_days_is_reported_and_is_a_problem(tmp_path):
    today = date(2026, 8, 22)
    _day(tmp_path, date(2026, 8, 18), published=["reel_1", "x_1"])
    report = health.scan(days=10, today=today, root=tmp_path)
    assert report.last_generated == date(2026, 8, 18)
    assert report.silent_days == 4
    assert any("no content generated for 4 days" in p for p in report.problems())


def test_a_day_generated_today_is_not_silence(tmp_path):
    today = date(2026, 8, 22)
    for back in range(5):
        d = today - timedelta(days=back)
        _day(tmp_path, d, published=["reel_1", "instagram_1", "story_card"])
    report = health.scan(days=5, today=today, root=tmp_path)
    assert report.silent_days == 0
    assert report.problems() == []


def test_a_busy_owned_surface_does_not_count_as_reach(tmp_path):
    """The failure this whole module was written for.

    Every day publishes, every job exits zero, every owned slot is green - and
    the account reaches nobody new, because no reel ever went out. A report that
    counted posts published would call this healthy.
    """
    today = date(2026, 8, 22)
    for back in range(20):
        _day(tmp_path, today - timedelta(days=back),
             published=["instagram_1", "instagram_2", "x_1", "x_2", "linkedin",
                        "story_card"])
    report = health.scan(days=20, today=today, root=tmp_path)
    assert report.silent_days == 0
    assert report.coverage()["instagram_1"] == 20      # busy
    assert report.discovery_days == 0                  # and invisible
    assert report.discovery_share == 0.0
    problems = report.problems()
    assert len(problems) == 1
    assert "reaches people who do not already follow" in problems[0]


def test_a_reel_every_day_clears_the_floor(tmp_path):
    today = date(2026, 8, 22)
    for back in range(20):
        _day(tmp_path, today - timedelta(days=back),
             published=["reel_1", "instagram_1", "story_card"])
    report = health.scan(days=20, today=today, root=tmp_path)
    assert report.discovery_share == 1.0
    assert report.problems() == []


def test_either_reel_slot_counts_as_discovery(tmp_path):
    """The second reel is opt-in, and a day carried by it alone still reached."""
    today = date(2026, 8, 22)
    for back in range(10):
        _day(tmp_path, today - timedelta(days=back), published=["reel_2"])
    report = health.scan(days=10, today=today, root=tmp_path)
    assert report.discovery_days == 10


def test_the_floor_is_a_floor_and_not_a_target(tmp_path):
    """Just under the floor is a problem; just over it is not. Pinned so the
    threshold cannot drift without a test saying so."""
    today = date(2026, 8, 22)
    reel_days = round(health.DISCOVERY_FLOOR * 10)
    owned = ["instagram_1", "story_card"]     # so only the reel share varies
    for back in range(10):
        slots = owned + (["reel_1"] if back < reel_days else [])
        _day(tmp_path, today - timedelta(days=back), published=slots)
    assert health.scan(days=10, today=today, root=tmp_path).problems() == []

    # one fewer reel day, same window
    other = tmp_path / "less"
    for back in range(10):
        slots = owned + (["reel_1"] if back < reel_days - 1 else [])
        _day(other, today - timedelta(days=back), published=slots)
    assert health.scan(days=10, today=today, root=other).problems()


def test_every_slot_the_scheduler_knows_has_a_declared_surface():
    """A slot with no surface silently vanishes from the report, which would
    make the discovery share wrong rather than merely incomplete."""
    from headlinne.config import SCHEDULE_IST

    assert set(SCHEDULE_IST) == set(health.SURFACE)


def test_the_json_form_carries_the_same_verdict(tmp_path):
    today = date(2026, 8, 22)
    _day(tmp_path, date(2026, 8, 18), published=["x_1"])
    report = health.scan(days=10, today=today, root=tmp_path)
    payload = json.loads(health.as_json(report))
    assert payload["silent_days"] == 4
    assert payload["last_generated"] == "2026-08-18"
    assert payload["problems"] == report.problems()
    assert payload["coverage"]["x_1"] == 1


def test_a_folder_with_no_content_at_all_reports_rather_than_crashes(tmp_path):
    report = health.scan(days=7, today=date(2026, 8, 22), root=tmp_path)
    assert report.last_generated is None
    assert report.silent_days == 7
    assert report.discovery_share == 0.0
    assert len(report.problems()) == 2
    # and it still formats
    assert "never" in health.format_report(report)


# --------------------------------------------------------------------------- #
# A single format going dark
# --------------------------------------------------------------------------- #
# The aggregate numbers above are both healthy while one format is completely
# dead: the days are generated, so silence is zero, and the reel still goes out,
# so discovery share is fine. That is the exact shape the carousel outage had -
# seventeen days, every threshold green, no error anywhere. These pin the check
# that would have caught it on day four.
def test_a_format_that_stops_publishing_is_a_problem(tmp_path):
    today = date(2026, 9, 7)
    for back in range(10):
        day = today - timedelta(days=back)
        slots = ["reel_1", "story_card"]
        if back >= 6:                      # the carousel stops six days ago
            slots.append("instagram_1")
        _day(tmp_path, day, published=slots)

    report = health.scan(days=10, today=today, root=tmp_path)

    assert report.silent_days == 0, "the days were all generated"
    assert report.discovery_share == 1.0, "the reel never missed"
    assert report.dark_slots() == [("instagram_1", 6)]
    assert any("instagram_1 is switched on but has published nothing"
               in p for p in report.problems())


def test_one_missed_day_is_not_an_outage(tmp_path):
    """A format is allowed to lose a day. Contained failure is the design."""
    today = date(2026, 9, 7)
    for back in range(10):
        day = today - timedelta(days=back)
        slots = ["reel_1", "story_card"]
        if back != 2:
            slots.append("instagram_1")
        _day(tmp_path, day, published=slots)

    assert health.scan(days=10, today=today, root=tmp_path).dark_slots() == []


def test_a_format_that_is_switched_off_is_not_reported_as_broken(tmp_path,
                                                                monkeypatch):
    from headlinne import config

    monkeypatch.setattr(config, "CAROUSEL_ENABLED", False)
    today = date(2026, 9, 7)
    for back in range(10):
        _day(tmp_path, today - timedelta(days=back),
             published=["reel_1", "story_card"])

    assert health.scan(days=10, today=today, root=tmp_path).dark_slots() == []


def test_days_that_never_generated_are_reported_as_silence_not_dead_formats(tmp_path):
    """Otherwise one outage is reported four times: once as silence and once
    per format that could not publish on a day that does not exist."""
    today = date(2026, 9, 7)
    for back in range(6, 10):
        _day(tmp_path, today - timedelta(days=back),
             published=["reel_1", "instagram_1", "story_card"])

    report = health.scan(days=10, today=today, root=tmp_path)

    assert report.silent_days == 6
    assert report.dark_slots() == []
