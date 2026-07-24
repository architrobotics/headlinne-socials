"""The guardrails that keep engagement human-paced and rule-abiding.

This is the anti-spam core, and it is pure logic so it is fully tested:

  - a low daily cap on how many replies get surfaced / posted (hard-capped),
  - a per-subreddit cooldown so we never flood one community,
  - de-duplication so a thread is engaged at most once,
  - the 9:1 promo ratio, so at most ~10% of engagement is ever self-promotional
    and only in subreddits that permit disclosed promotion, never on sensitive
    threads.

State persists to state/reddit_state.json so the caps hold across runs.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import (REDDIT_ENGAGEMENT_CAP, REDDIT_ENGAGEMENT_HARD_MAX,
                      REDDIT_PROMO_RATIO, REDDIT_SUBREDDIT_COOLDOWN_HOURS,
                      STATE_DIR)
from ..logging_setup import get_logger

log = get_logger("reddit.policy")

STATE_PATH = STATE_DIR / "reddit_state.json"
_RETENTION_DAYS = 30


def effective_cap() -> int:
    """The per-run engagement cap, clamped to the hard maximum. The hard max is
    intentional: it is what stops the tool from becoming a spam cannon."""
    return max(0, min(REDDIT_ENGAGEMENT_CAP, REDDIT_ENGAGEMENT_HARD_MAX))


def promo_daily_cap() -> int:
    """Most disclosed self-promo mentions allowed in a day (the 9:1 rule). At
    least 1 so a genuinely welcome mention in a maker subreddit is possible,
    but never more than ~10% of the engagement cap."""
    return max(1, int(effective_cap() * REDDIT_PROMO_RATIO))


class EngagementState:
    """Rolling record of what we surfaced and what was actually posted."""

    def __init__(self, surfaced: dict | None = None, posted: list | None = None):
        self.surfaced: dict[str, str] = surfaced or {}   # thread_id -> iso
        self.posted: list[dict] = posted or []           # {thread_id, subreddit, promoted, iso}

    # ---- load / save ----
    @classmethod
    def load(cls) -> "EngagementState":
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text())
                return cls(data.get("surfaced", {}), data.get("posted", []))
            except Exception as exc:  # pragma: no cover
                log.warning("reddit state unreadable, starting fresh: %s", exc)
        return cls()

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(
            {"surfaced": self.surfaced, "posted": self.posted}, indent=2))

    def prune(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=_RETENTION_DAYS)
        self.surfaced = {k: v for k, v in self.surfaced.items()
                         if _safe_dt(v) and _safe_dt(v) >= cutoff}
        self.posted = [p for p in self.posted
                       if _safe_dt(p.get("iso")) and _safe_dt(p["iso"]) >= cutoff]

    # ---- queries ----
    def already_seen(self, thread_id: str) -> bool:
        return thread_id in self.surfaced or any(p["thread_id"] == thread_id for p in self.posted)

    def posted_today(self, now: datetime | None = None) -> int:
        d = (now or datetime.now(timezone.utc)).date()
        return sum(1 for p in self.posted if _safe_date(p.get("iso")) == d)

    def promoted_today(self, now: datetime | None = None) -> int:
        d = (now or datetime.now(timezone.utc)).date()
        return sum(1 for p in self.posted if _safe_date(p.get("iso")) == d and p.get("promoted"))

    def sub_on_cooldown(self, subreddit: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        window = timedelta(hours=REDDIT_SUBREDDIT_COOLDOWN_HOURS)
        for p in self.posted:
            if p.get("subreddit", "").lower() == subreddit.lower():
                dt = _safe_dt(p.get("iso"))
                if dt and (now - dt) < window:
                    return True
        return False

    # ---- decisions ----
    def can_post(self, thread, *, now: datetime | None = None) -> tuple[bool, str]:
        """Whether posting a reply to `thread` is allowed right now."""
        now = now or datetime.now(timezone.utc)
        if self.already_seen(thread.id) and thread.id not in self.surfaced:
            # (already posted, not merely surfaced)
            if any(p["thread_id"] == thread.id for p in self.posted):
                return False, "already engaged this thread"
        if self.posted_today(now) >= effective_cap():
            return False, f"daily cap reached ({effective_cap()})"
        if self.sub_on_cooldown(thread.subreddit, now):
            return False, f"r/{thread.subreddit} is on cooldown"
        return True, "ok"

    def can_promote(self, thread, *, sensitive: bool, promo_used: int | None = None,
                    now: datetime | None = None) -> tuple[bool, str]:
        """Whether a disclosed Headlinne mention is allowed on `thread`.

        `promo_used` lets a single planning run account for mentions it has
        already suggested this run (on top of what was posted today). When
        omitted it falls back to today's actually-posted promo count.
        """
        if not thread.allow_promo:
            return False, "subreddit does not allow self-promotion"
        if sensitive:
            return False, "sensitive topic, never promote here"
        now = now or datetime.now(timezone.utc)
        used = self.promoted_today(now) if promo_used is None else promo_used
        if used >= promo_daily_cap():
            return False, f"daily promo limit reached ({promo_daily_cap()}, 9:1 rule)"
        return True, "ok"

    # ---- recording ----
    def mark_surfaced(self, thread_id: str, now: datetime | None = None) -> None:
        self.surfaced[thread_id] = (now or datetime.now(timezone.utc)).isoformat()

    def record_posted(self, thread, promoted: bool, now: datetime | None = None) -> None:
        self.posted.append({
            "thread_id": thread.id,
            "subreddit": thread.subreddit,
            "promoted": bool(promoted),
            "iso": (now or datetime.now(timezone.utc)).isoformat(),
        })


def _safe_dt(s) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_date(s) -> date | None:
    dt = _safe_dt(s)
    return dt.date() if dt else None
