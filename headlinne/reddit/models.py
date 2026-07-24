"""Typed data for the Reddit opportunity finder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class RedditThread:
    """A candidate thread pulled from a target subreddit."""

    id: str
    subreddit: str
    title: str
    selftext: str
    permalink: str            # path under reddit.com
    score: int
    num_comments: int
    created_utc: float
    category: str = ""        # from the RedditTarget it came from
    allow_promo: bool = False # whether that subreddit permits disclosed promo
    over_18: bool = False
    locked: bool = False

    @property
    def url(self) -> str:
        return f"https://www.reddit.com{self.permalink}"

    @property
    def fullname(self) -> str:
        # Reddit "thing" id for a link is t3_<id>; comments reply to this.
        return f"t3_{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RedditThread":
        known = {f: d.get(f) for f in cls.__annotations__ if f in d}
        return cls(**known)


@dataclass
class Opportunity:
    """A drafted, human-reviewable engagement suggestion for one thread."""

    thread: RedditThread
    topic_score: float
    reply: str                      # the genuinely-helpful draft reply
    mentions_headlinne: bool = False
    promo_appropriate: bool = False
    rationale: str = ""             # why this thread, and the promo call
    disclosure: str = ""            # disclosure line included when promoting
    status: str = "draft"           # "draft" | "posted" | "skipped"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["thread"] = self.thread.to_dict()
        return d
