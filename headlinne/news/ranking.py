"""Rank the day's news.

Two jobs:

1. Cross-source verification. Stories about the same event appear in several
   feeds. We cluster near-duplicate headlines together. A cluster backed by more
   independent, reputable sources is both better verified and (as a proxy)
   higher discussion volume. This is how we avoid posting an unverified scoop.

2. Scoring and category weighting. Each cluster is scored by
   news.significance - how many publishers ran the event, what is at stake,
   who is involved - plus a gentle recency term. Recency stays minor so
   significance beats "just published". From the scores we derive how much
   attention each category earned today and which category dominates.

No paid APIs or embeddings: similarity is computed from token overlap plus a
sequence ratio, which is robust enough for headline matching.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from ..config import CATEGORIES
from ..logging_setup import get_logger
from ..models import NewsDigest, Story
from . import categorise as categorise_mod
from . import interest as interest_mod
from . import quality as quality_mod
from . import significance as significance_mod

log = get_logger("news.ranking")

# Tuning knobs.
_SIM_THRESHOLD = 0.52          # how alike two headlines must be to merge
# The weights that used to sit here - source count as a tiebreaker, interest
# as the primary signal, a topical-fit bonus and a breadth bonus - are gone.
# Ranking is news.significance now: coverage, stakes, actors, scale and
# reputability in one place, with interest as a small term inside it.
_RECENCY_WEIGHT = 1.0          # small recency nudge
_LOW_VALUE_PENALTY = 1.15      # docked per soft/low-value marker (capped)
_BREAKING_MIN_SOURCES = 3
_BREAKING_AGE_HOURS = 8
_CATEGORY_TOPK = 5             # clusters per category that count toward weight

# Markers of low-signal content we would rather not lead a carousel with:
# opinion, live blogs, video/photo galleries, deals, sponsored posts. A soft,
# capped penalty nudges genuine news above these; the hard cases are dropped
# outright by news.quality before scoring ever happens.
#
# "explainer" and "how to" used to sit in this list. They are the exact genre of
# the evening educational reel, and the genre the best explainer channels are
# built on - penalising them was penalising our own second daily format.
_LOW_VALUE_MARKERS = (
    "opinion", "comment is free", "editorial", "live:", "live updates",
    "as it happened", "watch:", "video:", "in pictures", "in photos",
    "recap", "best deals", "deal of the day", "discount",
    "review:", "sponsored", "advertisement", "paid post", "horoscope",
    "quiz", "podcast", "listen:",
)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "these", "those", "after", "over", "amid", "into", "new",
    "say", "says", "said", "will", "has", "have", "had", "but", "not", "you",
    "report", "reports", "update", "live", "watch", "video", "us", "uk",
}


def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _similarity(a: Story, b: Story, ta: set[str], tb: set[str]) -> float:
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    jaccard = inter / union if union else 0.0
    seq = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
    # Weighted blend: token overlap matters most, sequence ratio breaks ties.
    return 0.7 * jaccard + 0.3 * seq


def _hours_old(story: Story) -> float:
    try:
        dt = datetime.fromisoformat(story.published_iso)
    except ValueError:
        return 99.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


def _cluster(stories: list[Story]) -> list[list[Story]]:
    """Greedy single-pass clustering of near-duplicate stories."""
    toks = [_tokens(s.title) for s in stories]
    clusters: list[list[int]] = []
    cluster_tokens: list[set[str]] = []

    for i, story in enumerate(stories):
        best_j, best_sim = -1, 0.0
        for ci, members in enumerate(clusters):
            # Compare against the cluster's seed story for stability.
            seed = members[0]
            sim = _similarity(story, stories[seed], toks[i], toks[seed])
            if sim > best_sim:
                best_sim, best_j = sim, ci
        if best_sim >= _SIM_THRESHOLD:
            clusters[best_j].append(i)
            cluster_tokens[best_j] |= toks[i]
        else:
            clusters.append([i])
            cluster_tokens.append(set(toks[i]))

    return [[stories[i] for i in members] for members in clusters]


def _merge(members: list[Story]) -> Story:
    """Collapse a cluster into one representative Story."""
    # Representative = highest tier, then longest summary.
    rep = sorted(members, key=lambda s: (s.tier, len(s.summary)), reverse=True)[0]
    others = [m for m in members if m is not rep]

    image = rep.image_url or next((m.image_url for m in others if m.image_url), None)
    # Distinct corroborating source names (excludes the representative's source).
    corroborating = sorted({m.source for m in others if m.source != rep.source})

    merged = Story(
        title=rep.title,
        summary=rep.summary or next((m.summary for m in members if m.summary), ""),
        url=rep.url,
        category=_majority_category(members),
        source=rep.source,
        tier=max(m.tier for m in members),
        published_iso=min(m.published_iso for m in members),  # earliest sighting
        image_url=image,
        corroborating_sources=corroborating,
    )
    return merged


def _majority_category(members: list[Story]) -> str:
    counts: dict[str, float] = {}
    for m in members:
        counts[m.category] = counts.get(m.category, 0.0) + m.tier
    return max(counts, key=counts.get)


def _low_value_penalty(text: str) -> float:
    """Soft, capped penalty for opinion / live / gallery / deal / listicle copy."""
    hits = sum(1 for m in _LOW_VALUE_MARKERS if m in text)
    return _LOW_VALUE_PENALTY * min(hits, 2)


def _score(story: Story, outlets: int = 1) -> float:
    """Significance first, then a small nudge for freshness.

    Until 2026-10 the primary term was news.interest - "would a curious person
    enjoy this?" - and the reel spent a month on single-outlet science papers
    while elections, wars and price shocks ranked underneath. The primary term
    is now news.significance - "does this matter in the world today?" - which
    leads with how many publishers ran the event. Interest survives inside it
    as a small vividness tiebreaker. See news/significance.py for the replay.
    """
    text = story.title + " " + story.summary
    age = _hours_old(story)
    recency = _RECENCY_WEIGHT * math.exp(-age / 18.0)  # gentle decay
    penalty = _low_value_penalty(text.lower())
    weight = significance_mod.significance(
        story.title, story.summary, outlets=outlets, tier=story.tier,
        has_image=bool(story.image_url), category=story.category)
    return weight + recency - penalty


def rank(stories: list[Story]) -> NewsDigest:
    """Cluster, score and organise the day's stories into a NewsDigest."""
    day = datetime.now(timezone.utc).date().isoformat()
    if not stories:
        log.warning("No stories to rank.")
        return NewsDigest(
            day=day,
            by_category={c: [] for c in CATEGORIES},
            category_weights={c: 0.0 for c in CATEGORIES},
            dominant_category=CATEGORIES[0],
        )

    # Drop what is not news before anything else looks at it. This is a gate
    # rather than a penalty: a soft, capped score cannot hold back a promo code
    # that the interest model finds genuinely interesting.
    publishable, dropped = [], {}
    for story in stories:
        reason = quality_mod.reject_reason(story.title, story.summary)
        if reason is None:
            publishable.append(story)
        else:
            kind = reason.split(":")[0]
            dropped[kind] = dropped.get(kind, 0) + 1
    if dropped:
        log.info("Quality gate dropped %d/%d: %s", len(stories) - len(publishable),
                 len(stories), dict(sorted(dropped.items())))
    # If the gate somehow rejects everything, publish from the raw set rather
    # than producing an empty day: a bad filter must not be able to silence the
    # whole pipeline.
    stories = publishable or stories

    clusters = _cluster(stories)
    merged = [_merge(c) for c in clusters]
    # Publishers carrying each event, counted generously across clusters. A
    # ranking input only - never printed, never a claim of agreement.
    coverage = significance_mod.coverage(merged)
    for s, outlets in zip(merged, coverage):
        s.verified = s.source_count >= 2
        s.sensitive = interest_mod.is_sensitive(s.title, s.summary)
        # The feed decides the category, and general feeds carry everything, so
        # a bone-marrow discovery filed on a world-news feed goes out labelled
        # Geopolitics with Geopolitics hashtags over it. Correct the clear cases
        # before the label reaches the weights, since the weights are what the
        # next format is allowed to cover. See news/categorise.py.
        corrected = categorise_mod.recategorise(s.title, s.summary, s.category)
        if corrected != s.category:
            log.info("Recategorised %r: %s -> %s", s.title[:56], s.category,
                     corrected)
            s.category = corrected
        s.score = round(_score(s, outlets), 3)
    merged.sort(key=lambda s: s.score, reverse=True)

    log.info("Clustered %d stories into %d events", len(stories), len(merged))
    log.info("%d/%d events reached two independent sources; %d route sober",
             sum(1 for s in merged if s.verified), len(merged),
             sum(1 for s in merged if s.sensitive))

    by_category: dict[str, list[Story]] = {c: [] for c in CATEGORIES}
    for s in merged:
        if s.category in by_category:
            by_category[s.category].append(s)

    reserve_non_universal(by_category, merged)
    _log_decisions(by_category)

    # Category weight = sum of top-K cluster scores in that category.
    weights = {
        c: round(sum(s.score for s in by_category[c][:_CATEGORY_TOPK]), 3)
        for c in CATEGORIES
    }
    total = sum(weights.values()) or 1.0
    norm_weights = {c: round(weights[c] / total, 3) for c in CATEGORIES}
    dominant = max(norm_weights, key=norm_weights.get)

    # Breaking: most-corroborated very recent story across all categories.
    breaking = None
    for s in merged:
        if s.source_count >= _BREAKING_MIN_SOURCES and _hours_old(s) <= _BREAKING_AGE_HOURS:
            breaking = s
            break

    log.info("Category weights: %s | dominant=%s", norm_weights, dominant)
    if breaking:
        log.info("Breaking flagged: %s (%d sources)", breaking.title[:70], breaking.source_count)

    return NewsDigest(
        day=day,
        by_category=by_category,
        category_weights=norm_weights,
        dominant_category=dominant,
        breaking=breaking,
    )


# --------------------------------------------------------------------------- #
# The reserved slot
# --------------------------------------------------------------------------- #
# How far up its category a reserved story is promoted. Third, not first: the
# point is to guarantee the story a place where it will actually be seen, not to
# lead the day with it over something that scored better.
RESERVED_RANK = 2


def reserve_non_universal(by_category: dict[str, list[Story]],
                          merged: list[Story]) -> Story | None:
    """Guarantee one slot to a story that is important without being universal.

    Universality has to be a tilt, not a filter, and the difference is not
    academic. Weighting it pushed "Afghan women tell the BBC their lives are
    unrecognisable" out of the top eight entirely - a story that matters, from a
    place a news product cannot simply stop covering because its readers have no
    personal stake in it. A feed optimised purely for universality becomes all
    wonder and no world.

    So the best story in the non-universal pool is promoted into the visible part
    of its category, chosen by score within that pool rather than handed a bonus
    that would distort every other ranking.

    Returns the promoted story, or None if the day's top stories were already
    a mix.
    """
    pool = [s for s in merged
            if not interest_mod.is_universal(s.title, s.summary)
            and not s.sensitive]
    if not pool:
        return None

    # Already represented near the top of its own category? Then nothing to do.
    best = pool[0]                       # merged is score-sorted, so is the pool
    siblings = by_category.get(best.category, [])
    if best in siblings[:RESERVED_RANK + 1]:
        return None

    if best in siblings:
        siblings.remove(best)
    siblings.insert(min(RESERVED_RANK, len(siblings)), best)
    log.info("Reserved slot: promoted %r (%s, score %.2f) into %s at position %d",
             best.title[:60], best.source, best.score, best.category,
             min(RESERVED_RANK, len(siblings) - 1) + 1)
    return best


def _log_decisions(by_category: dict[str, list[Story]], top: int = 3) -> None:
    """Write out the per-term reasoning for the stories most likely to publish.

    Ranking has to be auditable: a decision made six weeks ago should still be
    accountable from the run log alone, without re-fetching a feed that has long
    since rotated the story out.
    """
    for category, stories in by_category.items():
        for rank_i, s in enumerate(stories[:top], 1):
            b = significance_mod.breakdown(
                s.title, s.summary, outlets=s.source_count, tier=s.tier,
                has_image=bool(s.image_url), category=s.category)
            log.info(
                "rank %s#%d score=%.2f sources=%d verified=%s sensitive=%s | "
                "stakes=%.0f actors=%.0f scale=%.0f decision=%.0f interest=%.1f "
                "consumer=%.0f niche=%.0f feature=%.0f | %s",
                category, rank_i, s.score, s.source_count, s.verified,
                s.sensitive, b["stakes"], b["actors"], b["scale"], b["decision"],
                b["interest"], b["consumer"], b["niche"], b["feature"],
                s.title[:70])


# How alike two headlines must be for the day to treat them as one event when
# choosing what each format covers.
#
# Deliberately looser than _SIM_THRESHOLD, and the asymmetry is the reason it is
# a separate number rather than a reuse of that one. Clustering merges the
# sources behind a published claim: a false merge there puts "4 outlets agree"
# under a story four outlets did not agree on, which is the one thing this
# system must never print. Here a false positive costs the day its second-best
# story and nothing else. The two decisions do not deserve the same caution.
#
# 0.52 let Wired's "Astronomers Discover the Existence of a Black Hole Star" and
# Phys.org's "Black hole star: Astronomers discover a brand-new type of
# astrophysical object" through as separate events, and the day put the same
# discovery on the carousel and the story card.
SAME_EVENT_SIM = 0.30


def same_event(a: Story, b: Story) -> bool:
    """Whether two stories are two outlets covering one thing.

    Used to stop a day spending two of its three formats on one event. Compares
    headline tokens rather than URLs, because two outlets on one story share
    neither a URL nor, necessarily, a category - the black hole star above was
    filed under Technology by one and Science by the other.
    """
    ta, tb = _tokens(a.title), _tokens(b.title)
    if not ta or not tb:
        return False
    if len(ta & tb) / len(ta | tb) >= SAME_EVENT_SIM:
        return True
    # Paraphrases share names, not wording: "OpenAI agent hacked Australia
    # government portal" and "Australia to investigate if OpenAI hack of
    # government health website broke the law" took the reel, the carousel and
    # the story card on one replayed day once significance began ranking the
    # day's real news, which is exactly the kind of story every outlet words
    # differently. The same generous match coverage uses applies here.
    return significance_mod.same_event_loose(significance_mod._keys(a.title),
                                             significance_mod._keys(b.title))


def strongest_categories(digest: NewsDigest, n: int = 2) -> list[str]:
    """The n categories with the most attention today (non-empty only)."""
    ranked = sorted(
        (c for c in CATEGORIES if digest.by_category.get(c)),
        key=lambda c: digest.category_weights.get(c, 0.0),
        reverse=True,
    )
    return ranked[:n] if ranked else list(CATEGORIES[:n])
