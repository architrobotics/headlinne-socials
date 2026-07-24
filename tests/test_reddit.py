"""The Reddit tooling's job is to be helpful and never spammy. These tests pin
the guardrails that guarantee that: relevance and sensitivity filtering, the
engageability gates, and the policy caps (daily limit, per-subreddit cooldown,
de-duplication and the 9:1 helpful-to-promo ratio)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from headlinne.reddit.models import RedditThread
from headlinne.reddit.policy import (EngagementState, effective_cap,
                                     promo_daily_cap)
from headlinne.reddit.relevance import (is_sensitive, thread_is_engageable,
                                        topic_relevance)

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def _thread(**kw) -> RedditThread:
    base = dict(
        id=kw.pop("id", "abc"), subreddit=kw.pop("subreddit", "technology"),
        title=kw.pop("title", "A thread"), selftext=kw.pop("selftext", ""),
        permalink="/r/x/comments/abc/x/", score=kw.pop("score", 30),
        num_comments=kw.pop("num_comments", 25),
        created_utc=(NOW - timedelta(hours=kw.pop("age_h", 5))).timestamp(),
        category=kw.pop("category", "Technology"),
        allow_promo=kw.pop("allow_promo", False),
        over_18=kw.pop("over_18", False), locked=kw.pop("locked", False),
    )
    base.update(kw)
    return RedditThread(**base)


# ---- relevance ----
def test_topic_relevance_high_for_news_overload_question():
    high = topic_relevance("How do you keep up with the news without information overload?",
                           "I get news fatigue and doomscroll. Any unbiased news app?")
    low = topic_relevance("My cat did something funny today", "just a photo")
    assert high > 0.4
    assert low < 0.2
    assert high > low


def test_sensitive_topics_are_flagged():
    assert is_sensitive("My father died and I cannot stop reading the news")
    assert is_sensitive("Struggling with depression lately")
    assert not is_sensitive("Best way to follow tech news?")


# ---- engageability gates ----
def test_engageable_accepts_a_good_thread():
    t = _thread(title="How do you keep up with the news these days?",
                selftext="News overload is real, any good news app?", num_comments=20, age_h=6)
    ok, reason = thread_is_engageable(t, NOW)
    assert ok, reason


def test_engageable_rejects_locked_old_thin_or_irrelevant():
    title = "How do you keep up with the news?"
    body = "news overload app"
    # Locked.
    assert not thread_is_engageable(
        _thread(title=title, selftext=body, num_comments=20, age_h=6, locked=True), NOW)[0]
    # Too few comments.
    assert not thread_is_engageable(
        _thread(title=title, selftext=body, num_comments=1, age_h=6), NOW)[0]
    # Too old.
    assert not thread_is_engageable(
        _thread(title=title, selftext=body, num_comments=20, age_h=100), NOW)[0]
    # Topically unrelated thread is rejected on relevance.
    assert not thread_is_engageable(
        _thread(title="Look at my new gaming PC build", selftext="rgb",
                num_comments=20, age_h=6), NOW)[0]


# ---- policy caps ----
def test_caps_are_clamped_and_sane():
    assert effective_cap() <= 25          # hard max holds
    assert promo_daily_cap() >= 1
    assert promo_daily_cap() <= max(1, effective_cap())


def test_dedup_blocks_re_engaging_a_thread():
    state = EngagementState()
    t = _thread(id="dup1")
    state.record_posted(t, promoted=False, now=NOW)
    ok, reason = state.can_post(t, now=NOW)
    assert not ok and "already" in reason


def test_subreddit_cooldown_blocks_flooding():
    state = EngagementState()
    state.record_posted(_thread(id="a", subreddit="technology"), promoted=False, now=NOW)
    # A different thread in the same subreddit, an hour later, is on cooldown.
    later = NOW + timedelta(hours=1)
    ok, reason = state.can_post(_thread(id="b", subreddit="technology"), now=later)
    assert not ok and "cooldown" in reason


def test_daily_cap_blocks_further_posts():
    state = EngagementState()
    for i in range(effective_cap()):
        state.record_posted(_thread(id=f"t{i}", subreddit=f"sub{i}"), promoted=False, now=NOW)
    ok, reason = state.can_post(_thread(id="new", subreddit="brandnew"), now=NOW)
    assert not ok and "cap" in reason


def test_promo_only_in_allowed_subreddits_and_never_when_sensitive():
    state = EngagementState()
    help_only = _thread(id="h", subreddit="technology", allow_promo=False)
    maker = _thread(id="m", subreddit="SideProject", allow_promo=True)
    assert not state.can_promote(help_only, sensitive=False, promo_used=0, now=NOW)[0]
    assert not state.can_promote(maker, sensitive=True, promo_used=0, now=NOW)[0]
    assert state.can_promote(maker, sensitive=False, promo_used=0, now=NOW)[0]


def test_promo_ratio_caps_daily_mentions():
    state = EngagementState()
    maker = _thread(id="m", subreddit="SideProject", allow_promo=True)
    # Once the daily promo cap is used up, further mentions are refused.
    ok, reason = state.can_promote(maker, sensitive=False, promo_used=promo_daily_cap(), now=NOW)
    assert not ok and "promo limit" in reason
