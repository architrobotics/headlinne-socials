"""Does this matter in the world today?

The question the ranker should have been asking from the start, and the one
the founder asked for directly on 2026-10-05 ("real world news... I hate the
news I've been seeing, it's completely irrelevant").

What went wrong. news.interest answers "would a curious person enjoy this?",
and it was made the primary ranking term on the argument that coverage is
"attendance, not interest". Its vocabulary is the vocabulary of wonder -
discover, planet, fossil, cell - so for a month the reel went to single-outlet
science papers while the day's actual news sat underneath. Measured on the
saved digests: on 2026-10-05 the reel was "Hidden X-ray phase revealed in
likely neutron star merger" (one outlet) while Brazil's presidential election
went to a run-off (five outlets); on 2026-10-04 it was lunar soil magnetism
while tens of thousands marched on housing in Spain (four outlets) and
OpenAI's safety lead quit warning the culture was broken (three). The story
card went to a Motorola phone, a PS5 controller and a BMW trim level.

So significance leads now, and interest is a tiebreaker for vividness. Six
terms, all from text already fetched:

  coverage   how many separate PUBLISHERS ran the event today - BBC World and
             BBC Business are one publisher. This is the editors of every
             outlet in the feed set voting with their front pages, which is
             the best single measure of "the news" there is. It is counted
             with a looser event match than corroboration uses, and it is
             never printed: the source strip still shows only outlets that
             took a position on the claim (see news.corroborate).
  stakes     the vocabulary of consequence - elections, courts, war, prices,
             jobs, rates, bans, arrests, strikes.
  actors     people and institutions whose decisions reach millions -
             heads of government, central banks, the largest companies.
  scale      a number of people, or a country-wide reach.
  decision   a verb of something actually happening: rules, bans, quits,
             approves, arrests, withdraws.
  reputable  the best outlet carrying it.

And four things that are not news to this account, however vivid:

  consumer   deals, how-tos, buying advice, product explainers
  launch     a product's spec sheet (shared with news.interest)
  feature    first-person and human-interest feature shapes
  niche      a single-outlet research paper with no stakes in it

Pure functions over (title, summary, outlets, tier). No I/O.
"""

from __future__ import annotations

import math
import re

from ._lexicon import compile_terms, distinct_hits
from . import interest as interest_mod

# --------------------------------------------------------------------------- #
# Lexicons
# --------------------------------------------------------------------------- #
_STAKES = (
    # politics and power
    "election*", "vote", "votes", "voters", "voting", "ballot*", "run-off",
    "runoff", "referendum", "parliament*", "congress", "senate", "government*",
    "president*", "prime minister", "minister*", "chancellor", "cabinet",
    "coalition", "opposition", "impeach*", "coup", "regime", "law", "laws",
    "bill", "legislation", "policy", "regulat*", "executive order", "veto",
    # courts and enforcement
    "court", "supreme court", "judge", "ruling", "lawsuit", "trial", "verdict",
    "convicted", "sentenced", "charged", "indicted", "arrest*", "investigation",
    "probe", "fine", "fined", "antitrust", "deport*", "extradit*",
    # conflict and security
    "war", "invasion", "troops", "military", "missile*", "drone strike*",
    "airstrike*", "bomber*", "ceasefire", "truce", "peace deal", "hostage*",
    "sanction*", "nuclear", "terror*", "attack", "border", "refugee*",
    "migrant*", "asylum",
    # economy reaching households
    "inflation", "interest rate*", "rate cut", "rate rise", "recession",
    "economy", "gdp", "unemployment", "jobs", "wages", "layoff*", "job cuts",
    "prices", "cost of living", "tariff*", "trade war", "trade deal", "oil",
    "energy", "fuel", "petrol", "gas prices", "housing", "rent", "rents",
    "mortgage*", "pension*", "tax", "taxes", "budget", "debt", "default",
    "bank", "banks", "stock market", "markets", "shortage*", "supply",
    # technology as power
    "ai", "artificial intelligence", "openai", "safety", "data breach",
    "breach", "hack*", "cyberattack*", "outage", "ban", "bans", "banned",
    "privacy", "surveillance", "misinformation", "disinformation",
    # people in numbers and public life
    "protest*", "strike", "strikes", "walkout", "riot*", "unrest", "crisis",
    "emergency", "evacuat*", "outbreak", "pandemic", "epidemic", "vaccine*",
    "schools", "hospital*", "nhs", "climate", "wildfire*", "flood*",
    "hurricane", "typhoon", "earthquake", "heatwave", "drought",
)

_ACTORS = (
    # heads of government and the people their decisions are reported through
    "trump", "biden", "vance", "harris", "xi", "xi jinping", "putin",
    "zelensky", "zelenskyy", "netanyahu", "modi", "starmer", "macron", "merz",
    "lula", "bolsonaro", "milei", "erdogan", "kim jong un", "khamenei",
    "sheinbaum", "carney", "albanese", "ishiba", "takaichi", "meloni",
    "sanchez", "sánchez", "von der leyen", "guterres", "pope",
    # institutions
    "white house", "pentagon", "kremlin", "downing street",
    "united nations", "nato", "european union", "g7", "g20", "opec",
    "imf", "world bank", "fed", "federal reserve", "ecb",
    "bank of england", "supreme court", "congress", "parliament",
    # companies whose moves reach billions
    "openai", "anthropic", "google", "alphabet", "apple", "microsoft", "meta",
    "amazon", "nvidia", "tesla", "spacex", "tiktok", "bytedance", "samsung",
    "tsmc", "intel", "musk", "altman", "zuckerberg", "bezos",
    # places that are the news (US, UK, EU, UN and WHO are matched
    # case-sensitively below: "us" and "who" are also ordinary words)
    "america", "american", "china", "chinese", "russia", "ukraine", "israel", "gaza",
    "iran", "india", "uk", "britain", "france", "germany", "japan", "brazil",
    "mexico", "canada", "taiwan", "north korea", "south korea", "saudi",
    "pakistan", "syria", "lebanon", "yemen", "venezuela", "turkey", "europe",
)

_DECISION = (
    "bans", "banned", "approves", "approved", "passes", "passed", "rules",
    "ruled", "orders", "ordered", "fires", "fired", "sacks", "sacked",
    "resigns", "resigned", "quits", "steps down", "cuts", "raises", "hikes",
    "halts", "suspends", "suspended", "withdraws", "withdrew", "pulls out",
    "blocks", "blocked", "scraps", "scrapped", "recalls", "shuts",
    "closes", "closed", "wins", "won", "loses", "lost", "defeats", "signs",
    "signed", "launches strike*", "invades", "seizes", "seized", "arrests",
    "arrested", "charges", "sues", "fines", "fined", "names", "appoints",
    "announces", "confirms", "agrees", "rejects", "rejected", "overturns",
    "collapses", "collapsed", "goes to", "heads to", "declares", "declared",
    "warns", "threatens", "release", "releases", "to release",
)

_SCALE = re.compile(
    r"\b(?:\d[\d,.]*\s*(?:million|billion|thousand|m|bn|k)?\s*"
    r"(?:people|workers|jobs|homes|households|students|pupils|schools|"
    r"passengers|patients|users|customers|residents|voters|families|"
    r"barrels|troops|refugees|migrants|children)\b|"
    r"tens of thousands|hundreds of thousands|millions of|thousands of|"
    r"nationwide|across the country|countrywide|worldwide|global|"
    r"across europe|across the us)", re.I)

# Consumer content: useful to someone, but not news, and not this account.
_CONSUMER = (
    "how to", "here's how", "here’s how", "you should", "should you",
    "here's why", "here’s why", "your iphone", "your phone", "your mac",
    "your macbook", "your android", "your pc", "your tv", "your laptop",
    "explained:", "model numbers", "which is right for you", "may be right for you",
    "every starlink", "setup", "settings", "tips", "best way to", "worth it",
    "leaks", "leak", "rumor", "rumour", "first look", "first impressions",
    "for the first time in months", "off for the first time",
    "specs", "spec sheet", "features, prices", "price and availability",
    "release date", "preorder", "pre-order",
)

# First-person and feature shapes. Journalism, but a magazine's, not the day's.
_FEATURE = re.compile(
    r"^\s*(?:i|my|we|our)\b|\b(?:my wife|my husband|my son|my daughter|"
    r"my partner|dear \w+|meet the|the man who|the woman who|the people who|"
    r"inside the|a day in|the secret life|what it's like|what it’s like|"
    r"the story of|why i|how i)\b", re.I)

# A research result with nothing at stake for anyone today. Not a filter -
# one with real coverage or real stakes still ranks - but a single outlet's
# paper about a neutron star is not the news.
_RESEARCH = (
    "study", "studies", "researchers", "scientists", "astronomers",
    "physicists", "biologists", "paper", "journal", "findings", "fossil*",
    "species", "galaxy", "galaxies", "star", "stars", "planet*", "neutron*",
    "quantum", "particle*", "cells", "molecul*", "protein*", "ancient",
    "million years", "billion years", "million-year-old", "billion-year-old",
)

_ACRONYMS = re.compile(r"\b(?:US|U\.S\.|UK|EU|UN|WHO|IMF|NHS)\b")

_RX = {name: compile_terms(bag) for name, bag in (
    ("stakes", _STAKES), ("actors", _ACTORS), ("decision", _DECISION),
    ("consumer", _CONSUMER), ("research", _RESEARCH),
)}

# --------------------------------------------------------------------------- #
# Weights
# --------------------------------------------------------------------------- #
# Coverage leads: three publishers is worth a strong stakes vocabulary, and a
# story most of the feed set ran beats anything one outlet ran alone.
W_COVERAGE = 3.2          # per doubling of publishers
W_TIER = 2.0              # per point of best-outlet tier above 1.0
W_STAKES = 1.25           # per distinct stakes term, capped
STAKES_CAP = 3
W_ACTORS = 0.9            # per distinct actor, capped
ACTORS_CAP = 2
W_SCALE = 1.0
W_DECISION = 0.9
W_INTEREST = 0.22         # news.interest, clamped, as a vividness tiebreaker
INTEREST_RANGE = (-4.0, 10.0)
W_RECENCY = 1.0

P_CONSUMER = 3.5
P_LAUNCH = 2.0
P_FEATURE = 1.8
P_NICHE = 2.2
P_OFF_BEAT = 2.5
# A headline that is a question is an explainer or a debate about an event,
# not the event: "Should cockpits stay locked from the inside?", "Why has Trump
# rejected Iran's peace proposal?". The report of the event itself ranks.
P_QUESTION = 1.4


# --------------------------------------------------------------------------- #
# Publishers and event coverage
# --------------------------------------------------------------------------- #
_FEED_SUFFIX = re.compile(
    r"\s+(?:tech|technology|business|world|finance|top news|top|news|"
    r"science|politics|uk|us)$", re.I)


def publisher(feed_name: str) -> str:
    """The publisher behind a feed: "BBC Business" and "BBC World" are one."""
    name = (feed_name or "").strip()
    while True:
        shorter = _FEED_SUFFIX.sub("", name)
        if shorter == name or not shorter:
            return name.lower()
        name = shorter


def publishers_of(story) -> set[str]:
    names = [getattr(story, "source", "")] + list(
        getattr(story, "corroborating_sources", []) or [])
    return {publisher(n) for n in names if n}


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "after", "over", "amid", "into", "new", "says", "said",
    "will", "has", "have", "had", "but", "not", "you", "your", "how", "why",
    "what", "who", "when", "live", "news", "update", "could", "may", "more",
    "than", "just", "now", "first", "after", "his", "her", "their", "they",
}
_COMMON_CAPS = {"how", "why", "what", "the", "this", "new", "scientists",
                "researchers", "study", "watch", "live", "breaking", "exclusive"}


def _keys(title: str) -> tuple[set[str], set[str]]:
    """(all salient tokens, proper-noun tokens) of a headline."""
    words = re.findall(r"[A-Za-zÀ-ÿ0-9][\w'’-]*", title or "")
    tokens, proper = set(), set()
    for i, w in enumerate(words):
        low = w.lower().strip("'’")
        # Two characters only when one is a digit: "G7", "F1", "5G".
        short_ok = len(low) == 2 and any(ch.isdigit() for ch in low)
        if (len(low) < 3 and not short_ok) or low in _STOP:
            continue
        tokens.add(low)
        if w[0].isupper() and low not in _COMMON_CAPS and (i > 0 or len(low) >= 4):
            proper.add(low)
    return tokens, proper


def same_event_loose(a_keys, b_keys) -> bool:
    """Two headlines about one event, judged generously.

    Looser than ranking._SIM_THRESHOLD on purpose, and safe to be: this only
    counts publishers for ranking. A false match makes a story rank a little
    higher; it never puts a word on screen.
    """
    (ta, pa), (tb, pb) = a_keys, b_keys
    if not ta or not tb:
        return False
    shared = ta & tb
    if len(shared) / len(ta | tb) >= 0.3:
        return True
    return len(pa & pb) >= 1 and len(shared) >= 2


def coverage(stories: list) -> list[int]:
    """Distinct publishers carrying each story's event, aligned with `stories`."""
    keys = [_keys(s.title) for s in stories]
    pubs = [publishers_of(s) for s in stories]
    out = []
    for i in range(len(stories)):
        seen = set(pubs[i])
        for j in range(len(stories)):
            if i != j and same_event_loose(keys[i], keys[j]):
                seen |= pubs[j]
        out.append(max(1, len(seen)))
    return out


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #
def terms(title: str, summary: str = "", *, outlets: int = 1, tier: float = 1.0,
          has_image: bool = False, category: str = "") -> dict[str, float]:
    text = f"{title} {summary}"
    stakes = min(distinct_hits(text, _RX["stakes"]), STAKES_CAP)
    actors = min(distinct_hits(title, _RX["actors"])
                 + len(set(_ACRONYMS.findall(title))), ACTORS_CAP)
    research = distinct_hits(text, _RX["research"])
    interest = interest_mod.interest(title, summary, has_image=has_image)
    itr = interest_mod._terms(title, summary, has_image)
    niche = (outlets <= 1 and stakes == 0 and actors == 0
             and (research >= 1 or category == "Science"))
    return {
        "coverage": math.log2(max(1, outlets)),
        "tier": max(0.0, tier - 1.0),
        "stakes": float(stakes),
        "actors": float(actors),
        "scale": 1.0 if _SCALE.search(text) else 0.0,
        "decision": 1.0 if distinct_hits(title, _RX["decision"]) else 0.0,
        "interest": max(INTEREST_RANGE[0], min(INTEREST_RANGE[1], interest)),
        "consumer": 1.0 if distinct_hits(title, _RX["consumer"]) else 0.0,
        "launch": itr["launch"],
        "feature": 1.0 if _FEATURE.search(title) else 0.0,
        "niche": 1.0 if niche else 0.0,
        "off_beat": itr["off_beat"],
        "question": 1.0 if (title or "").strip().endswith("?") else 0.0,
    }


def significance(title: str, summary: str = "", *, outlets: int = 1,
                 tier: float = 1.0, has_image: bool = False,
                 category: str = "") -> float:
    """How much this matters in the world today. Higher is more."""
    t = terms(title, summary, outlets=outlets, tier=tier, has_image=has_image,
              category=category)
    return (W_COVERAGE * t["coverage"]
            + W_TIER * t["tier"]
            + W_STAKES * t["stakes"]
            + W_ACTORS * t["actors"]
            + W_SCALE * t["scale"]
            + W_DECISION * t["decision"]
            + W_INTEREST * t["interest"]
            - P_CONSUMER * t["consumer"]
            - P_LAUNCH * t["launch"]
            - P_FEATURE * t["feature"]
            - P_NICHE * t["niche"]
            - P_OFF_BEAT * t["off_beat"]
            - P_QUESTION * t["question"])


def breakdown(title: str, summary: str = "", **kw) -> dict:
    t = {k: round(v, 2) for k, v in terms(title, summary, **kw).items()}
    t["total"] = round(significance(title, summary, **kw), 2)
    return t
