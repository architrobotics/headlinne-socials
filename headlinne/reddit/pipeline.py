"""Orchestrates the Reddit opportunity finder.

`find_opportunities` is read-only: it discovers relevant threads, drafts helpful
replies, decides (conservatively) whether a disclosed Headlinne mention is even
appropriate, and writes a review queue (JSON + a readable Markdown report) for a
human to approve. It never posts.

`post_one` posts a single, human-approved draft. It re-checks every guardrail
(daily cap, subreddit cooldown, de-dup, promo ratio) and refuses without an
explicit confirm. There is intentionally no bulk / autonomous posting path.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from ..config import REDDIT_KEYWORDS, REDDIT_TARGETS, STATE_DIR
from ..gemini.client import GeminiClient
from ..logging_setup import get_logger
from . import relevance
from .drafts import draft_reply
from .models import Opportunity, RedditThread
from .policy import EngagementState, effective_cap

log = get_logger("reddit.pipeline")

QUEUE_DIR = STATE_DIR / "reddit_queue"


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _keyword_subset(now: datetime) -> list[str]:
    """A small rotating slice of the keywords, so runs vary and API use stays low."""
    k = list(REDDIT_KEYWORDS)
    start = (now.timetuple().tm_yday * 3) % len(k)
    return [k[(start + i) % len(k)] for i in range(4)]


def _to_thread(data: dict, target) -> RedditThread | None:
    if not data.get("id") or not data.get("title"):
        return None
    return RedditThread(
        id=data["id"],
        subreddit=data.get("subreddit", target.name),
        title=data.get("title", ""),
        selftext=data.get("selftext", "") or "",
        permalink=data.get("permalink", ""),
        score=int(data.get("score", 0) or 0),
        num_comments=int(data.get("num_comments", 0) or 0),
        created_utc=float(data.get("created_utc", 0) or 0),
        category=target.category,
        allow_promo=target.allow_promo,
        over_18=bool(data.get("over_18")),
        locked=bool(data.get("locked") or data.get("removed_by_category")),
    )


def _discover(client, now: datetime) -> list[RedditThread]:
    """Search each target subreddit for a rotating keyword subset."""
    subset = _keyword_subset(now)
    query = " OR ".join(f'"{k}"' for k in subset)
    seen: set[str] = set()
    threads: list[RedditThread] = []
    for target in REDDIT_TARGETS:
        try:
            raw = client.search_subreddit(target.name, query, limit=12)
        except Exception as exc:  # pragma: no cover - network best-effort
            log.warning("search failed for r/%s: %s", target.name, exc)
            continue
        for data in raw:
            t = _to_thread(data, target)
            if t and t.id not in seen:
                seen.add(t.id)
                threads.append(t)
    log.info("discovered %d candidate threads across %d subreddits",
             len(threads), len(REDDIT_TARGETS))
    return threads


# --------------------------------------------------------------------------- #
# Build the review queue
# --------------------------------------------------------------------------- #
def find_opportunities(*, client=None, gemini: GeminiClient | None = None,
                       now: datetime | None = None, limit: int | None = None,
                       ) -> list[Opportunity]:
    """Discover, filter, draft and save a review queue. Read-only (never posts)."""
    now = now or datetime.now(timezone.utc)
    cap = min(limit or effective_cap(), effective_cap())

    if client is None:
        from .client import RedditClient
        client = RedditClient()
    gemini = gemini or GeminiClient()

    state = EngagementState.load()
    state.prune(now)

    threads = _discover(client, now)

    # Keep engageable, unseen threads, best topical fit first.
    scored: list[tuple[float, RedditThread]] = []
    for t in threads:
        if state.already_seen(t.id):
            continue
        ok, reason = relevance.thread_is_engageable(t, now)
        if not ok:
            log.debug("skip r/%s %s: %s", t.subreddit, t.id, reason)
            continue
        scored.append((relevance.topic_relevance(t.title, t.selftext), t))
    scored.sort(key=lambda p: p[0], reverse=True)

    opportunities: list[Opportunity] = []
    promo_used = state.promoted_today(now)   # count promos already posted today
    for topic_score, thread in scored[:cap]:
        sensitive = relevance.is_sensitive(thread.title, thread.selftext)
        promo_ok, promo_reason = state.can_promote(
            thread, sensitive=sensitive, promo_used=promo_used, now=now)
        draft = draft_reply(gemini, thread, allow_promo_mention=promo_ok)
        if not draft["reply"]:
            continue
        if promo_ok and draft["mentions_headlinne"]:
            promo_used += 1   # this run has now suggested one more disclosed mention
        opp = Opportunity(
            thread=thread,
            topic_score=round(topic_score, 3),
            reply=draft["reply"],
            mentions_headlinne=draft["mentions_headlinne"],
            promo_appropriate=promo_ok,
            disclosure=draft["disclosure"],
            rationale=draft["rationale"] or ("help-only: " + promo_reason if not promo_ok else "promo permitted here"),
        )
        opportunities.append(opp)
        state.mark_surfaced(thread.id, now)

    _save_queue(now.date(), opportunities)
    state.save()
    log.info("surfaced %d opportunities (%d suggest a disclosed mention)",
             len(opportunities), sum(1 for o in opportunities if o.mentions_headlinne))
    return opportunities


# --------------------------------------------------------------------------- #
# Guarded manual post
# --------------------------------------------------------------------------- #
def post_one(thread_id: str, *, confirm: bool = False, client=None,
             now: datetime | None = None) -> str:
    """Post one reviewed draft from today's queue. Refuses without confirm and
    re-checks every guardrail. Returns a human-readable result string."""
    now = now or datetime.now(timezone.utc)
    opp = _load_opportunity(now.date(), thread_id)
    if not opp:
        return f"no queued draft found for thread {thread_id} today"
    if not confirm:
        return ("refusing to post without explicit confirmation. Review the draft, "
                "then pass confirm=True (CLI: --confirm).")

    state = EngagementState.load()
    state.prune(now)
    can, reason = state.can_post(opp.thread, now=now)
    if not can:
        return f"blocked by guardrail: {reason}"
    if opp.mentions_headlinne:
        sensitive = relevance.is_sensitive(opp.thread.title, opp.thread.selftext)
        ok, why = state.can_promote(opp.thread, sensitive=sensitive, now=now)
        if not ok:
            return f"blocked: promotional reply not allowed here ({why})"

    if client is None:
        from .client import RedditClient
        client = RedditClient()
    client.submit_comment(opp.thread.fullname, opp.reply)
    state.record_posted(opp.thread, promoted=opp.mentions_headlinne, now=now)
    state.save()
    _update_queue_status(now.date(), thread_id, "posted")
    return f"posted reply to r/{opp.thread.subreddit} ({opp.thread.url})"


# --------------------------------------------------------------------------- #
# Queue persistence (JSON for tooling + Markdown for humans)
# --------------------------------------------------------------------------- #
def _queue_path(day: date) -> Path:
    return QUEUE_DIR / f"{day.isoformat()}.json"


def _save_queue(day: date, opportunities: list[Opportunity]) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    _queue_path(day).write_text(json.dumps(
        [o.to_dict() for o in opportunities], indent=2, ensure_ascii=False))
    _write_markdown(day, opportunities)


def _load_opportunity(day: date, thread_id: str) -> Opportunity | None:
    path = _queue_path(day)
    if not path.exists():
        return None
    for d in json.loads(path.read_text()):
        if d.get("thread", {}).get("id") == thread_id:
            thread = RedditThread.from_dict(d["thread"])
            return Opportunity(
                thread=thread, topic_score=d.get("topic_score", 0.0),
                reply=d.get("reply", ""), mentions_headlinne=d.get("mentions_headlinne", False),
                promo_appropriate=d.get("promo_appropriate", False),
                disclosure=d.get("disclosure", ""), rationale=d.get("rationale", ""),
                status=d.get("status", "draft"),
            )
    return None


def _update_queue_status(day: date, thread_id: str, status: str) -> None:
    path = _queue_path(day)
    if not path.exists():
        return
    data = json.loads(path.read_text())
    for d in data:
        if d.get("thread", {}).get("id") == thread_id:
            d["status"] = status
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _write_markdown(day: date, opportunities: list[Opportunity]) -> None:
    lines = [f"# Reddit review queue - {day.isoformat()}", ""]
    lines.append(f"{len(opportunities)} drafts. Review each one, then post the good "
                 f"ones yourself or with: `python -m headlinne reddit post --id <ID> --confirm`")
    lines.append("")
    for o in opportunities:
        t = o.thread
        tag = "PROMO (disclosed)" if o.mentions_headlinne else "help only"
        lines += [
            f"## r/{t.subreddit} - {t.title}",
            f"- Link: {t.url}",
            f"- Fit: {o.topic_score} | {tag} | {t.num_comments} comments | id `{t.id}`",
            f"- Why: {o.rationale}",
            "",
            "> " + o.reply.replace("\n", "\n> "),
            "",
        ]
        if o.disclosure:
            lines += [f"_Disclosure used: {o.disclosure}_", ""]
    (QUEUE_DIR / f"{day.isoformat()}.md").write_text("\n".join(lines), encoding="utf-8")
