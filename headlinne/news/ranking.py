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
from ..logging_setup import get_logger
from ..models import NewsDigest, Story

log = get_logger("news.ranking")

# Tuning knobs.
_SIM_THRESHOLD = 0.52          # how alike two headlines must be to merge
_SOURCE_WEIGHT = 3.2           # weight on (verified) cross-source coverage
_TIER_WEIGHT = 1.6             # weight on best source reputability
_KEYWORD_WEIGHT = 0.9          # weight per importance keyword (capped)
_RECENCY_WEIGHT = 1.0          # small recency nudge
_BREAKING_MIN_SOURCES = 3
_BREAKING_AGE_HOURS = 8
_CATEGORY_TOPK = 5             # clusters per category that count toward weight

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


def _score(story: Story) -> float:
    sources = story.source_count
    verification = _SOURCE_WEIGHT * math.log2(sources + 1)
    reputability = _TIER_WEIGHT * story.tier

    text = (story.title + " " + story.summary).lower()
    kw = sum(1 for k in HIGH_INTEREST_KEYWORDS if k in text)
    keywords = _KEYWORD_WEIGHT * min(kw, 4)

    age = _hours_old(story)
    recency = _RECENCY_WEIGHT * math.exp(-age / 18.0)  # gentle decay

    return verification + reputability + keywords + recency


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

    clusters = _cluster(stories)
    merged = [_merge(c) for c in clusters]
    for s in merged:
        s.score = round(_score(s), 3)
    merged.sort(key=lambda s: s.score, reverse=True)

    log.info("Clustered %d stories into %d events", len(stories), len(merged))

    by_category: dict[str, list[Story]] = {c: [] for c in CATEGORIES}
    for s in merged:
        if s.category in by_category:
            by_category[s.category].append(s)

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


def strongest_categories(digest: NewsDigest, n: int = 2) -> list[str]:
    """The n categories with the most attention today (non-empty only)."""
    ranked = sorted(
        (c for c in CATEGORIES if digest.by_category.get(c)),
        key=lambda c: digest.category_weights.get(c, 0.0),
        reverse=True,
    )
    return ranked[:n] if ranked else list(CATEGORIES[:n])
