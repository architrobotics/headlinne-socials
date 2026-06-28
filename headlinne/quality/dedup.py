"""Keep output fresh across days.

We persist a small rolling history (committed to state/history.json by the
generate workflow) of the stories and post text we have already used. Before
choosing stories we skip ones seen recently, and after generating we check that
new copy is not a near-repeat of recent copy.

Similarity uses word 3-gram (shingle) Jaccard - cheap and dependency-free.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from ..config import STATE_DIR
from ..logging_setup import get_logger

log = get_logger("quality.dedup")

HISTORY_PATH = STATE_DIR / "history.json"
HISTORY_DAYS = 10
_STORY_SIM_THRESHOLD = 0.6
_TEXT_SIM_THRESHOLD = 0.55


def _shingles(text: str, n: int = 3) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class History:
    """Loaded rolling history with helpers for the current run."""

    def __init__(self, days: dict[str, dict]):
        self.days = days

    # ---- loading / saving ----
    @classmethod
    def load(cls) -> "History":
        if HISTORY_PATH.exists():
            try:
                data = json.loads(HISTORY_PATH.read_text())
                return cls(data.get("days", {}))
            except Exception as exc:  # pragma: no cover
                log.warning("history unreadable, starting fresh: %s", exc)
        return cls({})

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps({"days": self.days}, indent=2))

    def prune(self, today: date) -> None:
        cutoff = today - timedelta(days=HISTORY_DAYS)
        self.days = {
            d: v for d, v in self.days.items()
            if _safe_date(d) and _safe_date(d) >= cutoff
        }

    # ---- queries against recent history ----
    def _recent(self, key: str) -> list:
        out = []
        for v in self.days.values():
            out.extend(v.get(key, []))
        return out

    def story_seen(self, url: str, title: str) -> bool:
        if url:
            for u in self._recent("story_urls"):
                if u and u == url:
                    return True
        title_sh = _shingles(title)
        for past in self._recent("story_titles"):
            if _jaccard(title_sh, _shingles(past)) >= _STORY_SIM_THRESHOLD:
                return True
        return False

    def text_repeats(self, text: str) -> bool:
        sh = _shingles(text)
        for past in self._recent("post_texts"):
            if _jaccard(sh, _shingles(past)) >= _TEXT_SIM_THRESHOLD:
                return True
        return False

    # ---- recording this run ----
    def record(self, today: date, *, story_urls: list[str],
               story_titles: list[str], post_texts: list[str]) -> None:
        bucket = self.days.setdefault(today.isoformat(), {})
        bucket.setdefault("story_urls", []).extend(u for u in story_urls if u)
        bucket.setdefault("story_titles", []).extend(story_titles)
        bucket.setdefault("post_texts", []).extend(post_texts)


def _safe_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None
