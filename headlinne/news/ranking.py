"""Rank the day's news.

Two jobs:

1. Cross-source verification. Stories about the same event appear in several
   feeds. We cluster near-duplicate headlines together. A cluster backed by more
   independent, reputable sources is both better verified and (as a proxy)
   higher discussion volume. This is how we avoid posting an unverified scoop.

2. Scoring and category weighting. Each cluster gets a composite score from
   source count, source reputability, importance keywords and a gentle recency
   term. We deliberately keep recency a minor factor so significance beats
   "just published". From the scores we derive how much attention each category
   earned today and which category dominates.

No paid APIs or embeddings: similarity is computed from token overlap plus a
sequence ratio, which is robust enough for headline matching.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from ..config import CATEGORIES, HIGH_INTEREST_KEYWORDS
from ._lexicon import compile_terms, distinct_hits
from ..logging_setup import get_logger
from ..models import NewsDigest, Story
from . import interest as interest_mod
from . import quality as quality_mod

log = get_logger("news.ranking")

# Tuning knobs.
_SIM_THRESHOLD = 0.52          # how alike two headlines must be to merge
# Cross-source coverage used to be the heaviest term at 3.2, which meant the top
# story was always the one the most outlets ran: a central bank, a summit, an
# earnings print. That is a measure of attendance, not of interest. It is now a
# small tiebreaker between stories the interest score rates equally, and the real
# verification signal moved to Story.verified, where it gates rather than ranks.
_SOURCE_WEIGHT = 0.6           # tiebreaker only; see news/interest.py
_INTEREST_WEIGHT = 1.0         # the primary ranking signal
_TIER_WEIGHT = 1.6             # weight on best source reputability
# Topical fit, not interest - see config.HIGH_INTEREST_KEYWORDS. Weighted and
# capped so it can rank two comparably interesting stories against each other
# and never overturn the interest score itself. At 0.9 x 4 it contributed 29% of
# the ranking's variance while the interest score contributed 68%, which made a
# vocabulary match worth more than half of what the whole editorial model was
# worth. It is a tiebreaker now, and sized like one.
_TOPIC_WEIGHT = 0.35           # per distinct on-beat term
_TOPIC_CAP = 3                 # distinct terms that count
_RECENCY_WEIGHT = 1.0          # small recency nudge
_BREADTH_BONUS = 0.7           # bonus for a big story verified by trusted outlets
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


_TOPIC_RX = compile_terms(HIGH_INTEREST_KEYWORDS)

def _score(story: Story) -> float:
    sources = story.source_count
    verification = _SOURCE_WEIGHT * math.log2(sources + 1)
    reputability = _TIER_WEIGHT * story.tier

    text = story.title + " " + story.summary
    # Distinct on-beat terms, matched on word boundaries. `k in text` counted
    # "said" as an AI story - see config.HIGH_INTEREST_KEYWORDS.
    topic = _TOPIC_WEIGHT * min(distinct_hits(text, _TOPIC_RX), _TOPIC_CAP)

    age = _hours_old(story)
    recency = _RECENCY_WEIGHT * math.exp(-age / 18.0)  # gentle decay

    # Reward the sweet spot: a story that is both widely covered and carried by
    # a reputable outlet is the kind of significant, verified news we want to
    # lead with (this is a proxy for genuine importance, not just volume).
    breadth = _BREADTH_BONUS if (sources >= 3 and story.tier >= 1.2) else 0.0

    penalty = _low_value_penalty(text.lower())

    # The primary signal: would a person who is not obliged to read this want to?
    appeal = _INTEREST_WEIGHT * interest_mod.interest(
        story.title, story.summary, has_image=bool(story.image_url))

    return (appeal + verification + reputability + topic + recency
            + breadth - penalty)


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
    for s in merged:
        s.verified = s.source_count >= 2
        s.sensitive = interest_mod.is_sensitive(s.title, s.summary)
        s.score = round(_score(s), 3)
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
            b = interest_mod.breakdown(s.title, s.summary, bool(s.image_url))
            log.info(
                "rank %s#%d score=%.2f interest=%.2f sources=%d verified=%s "
                "sensitive=%s | conc=%.2f univ=%.2f use=%.2f nov=%.2f surp=%.2f "
                "upl=%.2f proc=%.2f | %s",
                category, rank_i, s.score, b["total"], s.source_count,
                s.verified, s.sensitive, b["concrete"], b["universal"],
                b["useful"], b["novelty"], b["surprise"], b["uplift"],
                b["procedural"], s.title[:70])


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
    return len(ta & tb) / len(ta | tb) >= SAME_EVENT_SIM


def strongest_categories(digest: NewsDigest, n: int = 2) -> list[str]:
    """The n categories with the most attention today (non-empty only)."""
    ranked = sorted(
        (c for c in CATEGORIES if digest.by_category.get(c)),
        key=lambda c: digest.category_weights.get(c, 0.0),
        reverse=True,
    )
    return ranked[:n] if ranked else list(CATEGORIES[:n])
