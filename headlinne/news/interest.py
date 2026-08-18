"""Is this story worth anyone's attention?

The old scoring answered a different question. Its heaviest term by far was
cross-source count, with outlet tier and importance keywords behind it - three
proxies for institutional consensus. The story that maximises that function is,
by definition, the one the most outlets ran: a central bank, a summit, an
earnings print. Nobody chose those stories. The arithmetic did.

So verification and interest are separated here. Cross-source count answers
"is this true?" and is a property of the story (see Story.verified); it is not
a ranking term, because being well attended is not the same as being worth
reading. This module answers "should anyone care?"

Nine terms, all computable from the headline, summary and metadata already
fetched. No extra API call.

  concrete     physical nouns and measured quantities beat abstractions
  novelty      first, never before, confirmed, discovered
  surprise     turned out, actually, instead, contrary
  universal    things every human has a stake in; penalises the parochial
  useful       knowing this changes what a reader does or checks
  uplift       recovery, progress, awe - positive emotion transmits better
  imageable    a real photograph exists
  standalone   understandable without yesterday's episode
  procedural   penalty: a process, not an event

The ordering that falls out of it: "X happened" beats "X may happen" beats
"X met to discuss whether X might happen." Almost everything the old ranker
surfaced sat in the third bucket.

SENSITIVE is a separate axis and deliberately not a score. Deaths and disasters
come with concrete nouns and hard numerals, which is exactly what `concrete`
rewards - the first live run put a ferry disaster fourth on a list of things it
considered interesting. Those stories still publish; they route to a plain
treatment with no mascot, no bubble and no wonder framing. See is_sensitive().


Matching
--------
Terms match on word boundaries, and a trailing `*` marks a stem. This is not
fussiness. The previous version tested `term in text` against raw substrings,
and measured against real published headlines that produced:

    "Samsung Electronics ... 739 in New Jersey"   universal 0.4  <- "sun" in "Samsung"
    "Researchers ... last twice as long"          concrete  0.45 <- "ice" in "twice"
    "... WARN notice says"                        concrete  0.70 <- "ice" in "notice"

while `discovered` failed to match "Scientists **discover** why some people
never get sick", scoring a genuine finding at zero novelty. The scorer was
rewarding a phone manufacturer for containing the sun and penalising a
discovery for using the present tense.

Stems are marked one at a time rather than applied to everything, because a
blanket prefix match reintroduces the same class of error from the other end:
`star` would match "start", `ship` would match "shipping".
"""

from __future__ import annotations

import re

from ._lexicon import compile_terms, distinct_hits

# --------------------------------------------------------------------------- #
# Lexicons. Deliberately small and readable: this is editorial judgement written
# down, and it should be arguable over by a person rather than tuned blindly.
#
# A trailing `*` means "this stem plus any ending". Everything else must match
# as a whole word (or, for multi-word entries, as a whole phrase).
# --------------------------------------------------------------------------- #
_UNITS = re.compile(
    r"\b(km/h|mph|kg|tonnes?|kilomet(?:res|ers)|met(?:res|ers)|miles|"
    r"light[- ]years|degrees|billion|million|trillion|percent|%|km|ft|mm|"
    r"hours|minutes)\b")

_NOVELTY = ("first", "first-ever", "never before", "unprecedented", "discover*",
            "confirm*", "detect*", "spotted", "new species", "breakthrough",
            "record", "oldest", "largest", "smallest", "reveal*")

_SURPRISE = ("turned out", "actually", "instead", "contrary", "unexpected*",
             "surprised", "surprising", "mystery", "puzzle", "baffl*",
             "not what", "wrong", "reversal", "far more", "far fewer")

_PHYSICAL = ("rocket", "crater", "moon", "asteroid", "comet", "volcano", "whale",
             "fossil", "glacier", "telescope", "satellite", "reactor", "bridge",
             "tunnel", "ship", "aircraft", "brain", "cell", "cells", "virus",
             "star", "stars", "planet", "ice", "ocean", "forest", "storm",
             "dinosaur", "engine", "battery", "batteries", "chip", "chips")

# Applies to a reader anywhere, with no prior expertise.
_UNIVERSAL = ("moon", "space", "earth", "ocean", "brain", "sleep", "body",
              "human", "humans", "cancer", "memory", "ageing", "aging", "heart",
              "climate", "whale", "whales", "bird", "birds", "forest", "water",
              "food", "light", "sun", "star", "planet", "universe", "cell",
              "dna", "gravity", "phone", "iphone", "android", "internet",
              "battery", "batteries", "energy", "everyone", "people",
              "children",
              # Technology that reaches everyone, rather than technology as an
              # industry. Without these the score is a science detector, and a
              # genuinely useful phone or privacy story ranks below a listicle.
              "privacy", "password", "passwords", "wi-fi", "wifi", "browser",
              "email", "messaging", "camera", "screen", "charging", "chatbot",
              "your data", "smartphone", "electricity", "vaccine", "antibiotic*",
              "sleep", "medicine", "language")

# Local, expert-only or in-group. The opposite of universal.
#
# The market vocabulary is here because it is what separates "Apple changed what
# the iPhone does" from "Apple's stock moved". The first is universal, the second
# is a trading update wearing the same brand name, and only one of them is worth
# stopping for.
_PAROCHIAL = ("council", "borough", "constituency", "senator", "shares",
              "shareholder*", "earnings", "quarterly", "ftse", "nasdaq",
              "premier league", "transfer window", "midfielder", "by-election",
              "reshuffle", "select committee", "budget speech", "primary race",
              "ipo", "stock", "stocks", "valuation", "revenue", "profit",
              "guidance", "short seller*", "market cap", "warn notice",
              "workforce", "headcount", "funding round", "series a", "series b")

# Genuinely positive movement. `first` and `record` used to sit here as well as
# in _NOVELTY, so a single word scored twice - and both are neutral in valence,
# which is how "first close below IPO price" and "record layoffs" came to read
# as uplifting. `breakthrough` and `discovered` keep the overlap on purpose: a
# discovery really is both new and good.
_UPLIFT = ("discover*", "breakthrough", "recovering", "recovered", "reclaim*",
           "restored", "revived", "saved", "thriving", "rebound", "cure",
           "cured", "solved", "milestone", "repair*", "better than", "returns")

# Knowing this changes what a reader does, checks or expects. Deliberately
# factual and actionable rather than curiosity-gap: "you won't believe" is
# clickbait and is caught by news.quality, not rewarded here.
_USEFUL = ("will now", "you can", "your", "warns", "warning", "affects",
           "what it means", "means for", "you need", "for users", "rolling out",
           "available", "free to", "deadline", "eligible", "refund", "recall*",
           "security update", "vulnerabilit*", "patch", "scam", "how it works",
           "explains", "explained", "why it", "protect*")

# Both the base and the third-person form of every verb. Listing only "urges"
# meant "Musicians urge government to ..." scored a full point higher than
# "Musicians urges ...", which is a ranking decision made on grammar. Explicit
# forms rather than stems: `urge*` would also catch "urgent" and `weigh*` would
# catch "weight".
_PROCEDURAL = ("hold", "holds", "held", "meet", "meets", "meeting", "discuss*",
               "consider", "considers", "is set to", "could", "may", "might",
               "expected to", "plan to", "plans to", "unchanged", "consecutive",
               "talks", "urge", "urges", "urged", "call for", "calls for",
               "seek", "seeks", "weigh", "weighs", "mull", "mulls",
               "to decide", "ahead of", "amid", "vow", "vows", "pledge",
               "pledges", "demand", "demands")

_CONTEXT_DEPENDENT = ("continues", "latest", "amid ongoing", "another round",
                      "as it happened", "update:", "day two", "day three")

# Death and disaster. Not a disqualification - a routing decision.
_SENSITIVE = ("dead", "death", "deaths", "killed", "kills", "killing",
              "casualt*", "massacre", "shooting", "stabbed", "murder",
              "victims", "bodies", "capsiz*", "earthquake", "famine",
              "genocide", "atrociti*", "atrocity", "suicide", "abuse",
              "missing after", "death toll", "wounded", "injured", "hostage",
              "airstrike", "bombing", "war crime")

# Weights. Concrete leads because it is the strongest single predictor of a
# story a person will actually look at; procedural is the only negative and is
# weighted to fully cancel a strong positive, because a process story dressed in
# concrete nouns is still a process story.
_W_CONCRETE, _W_NOVELTY, _W_SURPRISE = 3.0, 2.4, 2.2
_W_UNIVERSAL, _W_USEFUL, _W_UPLIFT = 2.6, 2.0, 1.8
_W_IMAGE, _W_STANDALONE, _W_PROCEDURAL = 1.4, 1.2, 3.0


_RX = {name: compile_terms(bag) for name, bag in (
    ("novelty", _NOVELTY), ("surprise", _SURPRISE), ("physical", _PHYSICAL),
    ("universal", _UNIVERSAL), ("parochial", _PAROCHIAL), ("uplift", _UPLIFT),
    ("useful", _USEFUL), ("procedural", _PROCEDURAL),
    ("context", _CONTEXT_DEPENDENT), ("sensitive", _SENSITIVE),
)}


def _hits(text: str, name: str) -> int:
    return distinct_hits(text, _RX[name])


def is_sensitive(title: str, summary: str = "") -> bool:
    """True if the story is about death or disaster.

    Callers must not render these with the mascot, a speech bubble or any
    wonder framing. They are reported plainly.
    """
    return _hits(f"{title} {summary}", "sensitive") > 0


def _terms(title: str, summary: str, has_image: bool) -> dict[str, float]:
    """Every term, normalised to 0..1 (procedural is a penalty, same scale)."""
    text = f"{title} {summary}"
    return {
        "concrete": min(1.0, _hits(text, "physical") * 0.45
                        + len(_UNITS.findall(text.lower())) * 0.3
                        + (0.25 if re.search(r"\d", title) else 0.0)),
        "novelty": min(1.0, _hits(text, "novelty") * 0.5),
        "surprise": min(1.0, _hits(text, "surprise") * 0.55),
        "universal": max(0.0, min(1.0, _hits(text, "universal") * 0.4
                                  - _hits(text, "parochial") * 0.5)),
        "useful": min(1.0, _hits(text, "useful") * 0.4),
        "uplift": min(1.0, _hits(text, "uplift") * 0.45),
        "image": 1.0 if has_image else 0.0,
        "standalone": max(0.0, 1.0 - _hits(text, "context") * 0.5),
        "procedural": min(1.0, _hits(text, "procedural") * 0.34),
    }


def interest(title: str, summary: str = "", has_image: bool = False) -> float:
    """Score how much a person who is not obliged to read this would want to."""
    t = _terms(title, summary, has_image)
    return (_W_CONCRETE * t["concrete"]
            + _W_NOVELTY * t["novelty"]
            + _W_SURPRISE * t["surprise"]
            + _W_UNIVERSAL * t["universal"]
            + _W_USEFUL * t["useful"]
            + _W_UPLIFT * t["uplift"]
            + _W_IMAGE * t["image"]
            + _W_STANDALONE * t["standalone"]
            - _W_PROCEDURAL * t["procedural"])


def is_universal(title: str, summary: str = "") -> bool:
    """Whether the story clears the universality bar.

    Used for the reserved slot: universality is a tilt, not a filter. Weighting
    it pushed "Afghan women tell the BBC their lives are unrecognisable" out of
    the top eight, and a news product that never covers Afghanistan because it
    is not universal has a real problem. One slot a day goes to the best story
    in the non-universal pool. See news.ranking.reserve_non_universal().
    """
    text = f"{title} {summary}"
    return _hits(text, "universal") * 0.4 - _hits(text, "parochial") * 0.5 > 0


def breakdown(title: str, summary: str = "", has_image: bool = False) -> dict:
    """Per-term detail, for tuning and for explaining a ranking in the logs.

    Every published story's breakdown is logged, so a decision the ranker made
    six weeks ago can still be accounted for.
    """
    t = {k: round(v, 2) for k, v in _terms(title, summary, has_image).items()}
    t["sensitive"] = is_sensitive(title, summary)
    t["universal_pool"] = is_universal(title, summary)
    t["total"] = round(interest(title, summary, has_image), 2)
    return t
