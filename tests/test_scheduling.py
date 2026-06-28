"""Calendar and slot maths. These guard the rotation rules (promo every second
day, LinkedIn roundup on Fridays) and the exact UTC format Buffer's dueAt wants."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from headlinne.config import PROMO_ANCHOR_DATE, SCHEDULE_IST
from headlinne.scheduling import (
    is_friday,
    is_promo_day,
    slot_datetime,
    slot_iso,
    slot_utc_iso,
)


def test_promo_day_alternates():
    anchor = PROMO_ANCHOR_DATE
    assert is_promo_day(anchor) is True            # day 0 -> promo
    assert is_promo_day(date(anchor.year, anchor.month, anchor.day + 1)) is False
    assert is_promo_day(date(anchor.year, anchor.month, anchor.day + 2)) is True


def test_promo_day_is_strictly_every_other_day():
    seen = [is_promo_day(date(2026, 3, d)) for d in range(1, 11)]
    # Must perfectly alternate.
    for i in range(1, len(seen)):
        assert seen[i] != seen[i - 1]


def test_is_friday():
    # 2026-06-26 is a Friday.
    assert is_friday(date(2026, 6, 26)) is True
    assert is_friday(date(2026, 6, 27)) is False   # Saturday


def test_slot_datetime_uses_ist_schedule():
    d = date(2026, 6, 28)
    dt = slot_datetime(d, "x_1")
    hour, minute = SCHEDULE_IST["x_1"]
    assert (dt.hour, dt.minute) == (hour, minute)
    # IST is UTC+05:30.
    assert dt.utcoffset().total_seconds() == 5.5 * 3600


def test_slot_iso_has_ist_offset():
    iso = slot_iso(date(2026, 6, 28), "linkedin")
    assert iso.endswith("+05:30")


def test_slot_utc_iso_format_matches_buffer():
    # Buffer wants e.g. 2026-06-28T12:30:00.000Z (millis + trailing Z).
    iso = slot_utc_iso(date(2026, 6, 28), "linkedin")  # 18:00 IST -> 12:30 UTC
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z", iso)
    assert iso == "2026-06-28T12:30:00.000Z"


def test_slot_utc_iso_is_actually_utc():
    iso = slot_utc_iso(date(2026, 6, 28), "x_1")       # 13:00 IST -> 07:30 UTC
    parsed = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
    assert (parsed.hour, parsed.minute) == (7, 30)


def test_all_slots_resolve():
    for slot in SCHEDULE_IST:
        assert slot_utc_iso(date(2026, 6, 28), slot).endswith("Z")
