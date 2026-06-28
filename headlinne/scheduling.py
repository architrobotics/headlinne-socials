"""Scheduling and calendar logic, all anchored to IST.

Decides slot datetimes, whether a day is "promo only" on X, and whether it is
Friday (LinkedIn weekly roundup day).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import PROMO_ANCHOR_DATE, SCHEDULE_IST, TIMEZONE


def today_ist() -> date:
    """Current calendar date in IST (not the runner's UTC date)."""
    return datetime.now(TIMEZONE).date()


def slot_datetime(day: date, slot: str) -> datetime:
    """Timezone-aware IST datetime for a named slot on a given day."""
    hour, minute = SCHEDULE_IST[slot]
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TIMEZONE)


def slot_iso(day: date, slot: str) -> str:
    """ISO 8601 string with IST offset, e.g. 2026-06-28T13:00:00+05:30."""
    return slot_datetime(day, slot).isoformat()


def slot_utc_iso(day: date, slot: str) -> str:
    """UTC ISO 8601 with millis and trailing Z, the format Buffer's dueAt wants."""
    from datetime import timezone

    utc = slot_datetime(day, slot).astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def is_promo_day(day: date) -> bool:
    """True on the 'every second day' Headlinne-promo rotation for X."""
    delta = (day - PROMO_ANCHOR_DATE).days
    return delta % 2 == 0


def is_friday(day: date) -> bool:
    return day.weekday() == 4  # Mon=0 .. Fri=4


def upcoming_slot_passed(day: date, slot: str, *, grace_minutes: int = 180) -> bool:
    """Whether a slot time is already (well) in the past for the given day.

    Used so a late publish trigger does not schedule a post in the past with
    Buffer. If the slot is more than `grace_minutes` behind, we post immediately.
    """
    now = datetime.now(TIMEZONE)
    return slot_datetime(day, slot) < now - timedelta(minutes=grace_minutes)
