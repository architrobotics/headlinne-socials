"""Has the account just told this story's kind of story?

The interest score is a property of one headline on one day, and it has no idea
what the account published yesterday. Its lexicon also leans one way on
purpose - discover, star, planet, cell, fossil are the vocabulary of wonder -
so the same kind of story wins day after day. Of the 25 reels from 2026-09-09
to 2026-10-05, fourteen were space, and four named James Webb - three of those
on consecutive days. Each was the best story of its own day. Together they made
a space account.

So a candidate is docked for every recent pick it shares a subject with,
weighted by how recent that pick was. A fresh subject pays nothing, and the
penalty fades over WINDOW_DAYS, so a beat comes back once it has rested. It
never removes a story: an extraordinary space result still beats an ordinary
anything else. It only stops an ordinary space result from beating a good
story about something the account has not covered all week.

Subject is decided two ways:

  family   a small hand-written lexicon per beat (space, deep time, cell
           biology, gadgets, AI...). Readable and arguable, like the rest of
           news/interest.py.
  name     a capitalised word from the headline that also appears in a recent
           pick: "Webb", "Hubble", "Pope", "Motorola". This catches the repeat
           the families were never written for.

Read-only and pure: callers pass in the recent texts. This module never reads
the disk, so a missing or unreadable history is just an empty list, which is
no penalty, which is what the ranker did before it existed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ._lexicon import compile_terms

# How far back a pick still counts, and what each one costs at full strength
# (yesterday). Two picks a day, so a five-day run on one beat can cost at most
# PENALTY_CAP. Measured on the replay of 38 saved days: at 0.9 per pick a sixth
# telescope story in five days needs roughly 2.5 points of extra interest over
# the best fresh subject to lead, which is the size of gap between "a planet
# orbiting backwards" and "Webb detects ammonia".
WINDOW_DAYS = 5
PER_PICK = 0.9
PENALTY_CAP = 3.6

_FAMILIES: dict[str, tuple[str, ...]] = {
    # Two families, not one "space": a European rocket launch is an industry
    # story, and docking it for yesterday's radio-telescope result cost
    # 2026-09-07 its best reel. NASA is in neither; as a name in a headline it
    # is matched by name anyway.
    "astronomy": ("webb", "hubble", "telescope", "telescopes", "galaxy",
                  "galaxies", "planet", "planets", "exoplanet*", "star",
                  "stars", "stellar", "asteroid*", "comet*", "moon", "lunar",
                  "mars", "martian", "jupiter", "saturn", "astronom*",
                  "black hole*", "nebula*", "cosmic", "universe",
                  "solar system", "neutron star*", "supernova*", "pulsar*",
                  "light-years", "light years", "chang'e", "chang’e"),
    "spaceflight": ("rocket*", "spacecraft", "astronaut*", "iss",
                    "space station", "spacex", "starship", "launch pad",
                    "satellite*", "orbit*", "rover"),
    "deep_time": ("fossil*", "dinosaur*", "t. rex", "million-year-old",
                  "billion-year-old", "million years", "billion years",
                  "prehistoric", "ancient", "evolution", "evolved"),
    "cell_biology": ("cell", "cells", "cellular", "protein*", "dna", "gene",
                     "genes", "genetic", "enzyme*", "molecul*", "mitochondri*",
                     "bacteria", "bacterial", "microb*", "immune", "tissue"),
    "brain": ("brain", "brains", "neuron*", "dementia", "alzheimer*", "sleep",
              "memory", "dreaming"),
    "gadgets": ("iphone", "smartphone*", "phone", "phones", "android",
                "controller", "headphones", "earbuds", "laptop*", "tablet",
                "smartwatch*", "console", "glasses", "pixel", "galaxy s*",
                "ipad", "macbook"),
    "ai": ("ai", "artificial intelligence", "chatbot*", "openai", "chatgpt",
           "gemini", "anthropic", "llm", "machine learning"),
    "climate": ("climate", "heatwave*", "flood*", "drought*", "wildfire*",
                "emissions", "carbon", "warming", "glacier*", "ice sheet*"),
    "ev_energy": ("ev", "evs", "electric vehicle*", "battery", "batteries",
                  "grid", "solar power", "nuclear", "power plant*"),
    "markets": ("stocks", "shares", "markets", "inflation", "interest rate*",
                "central bank", "fed", "tariff*", "recession"),
    "religion": ("pope", "papal", "pontiff", "vatican", "church"),
}

_FAMILY_RX = {name: compile_terms(terms) for name, terms in _FAMILIES.items()}

# Capitalised words that say nothing about subject.
_NAME_STOP = {
    "the", "a", "an", "new", "how", "why", "what", "this", "these", "its",
    "scientists", "researchers", "study", "report", "exclusive", "here",
    "first", "after", "with", "from", "says", "say", "us", "uk", "eu",
    "world", "today", "week", "year", "years", "could", "may", "can", "will",
    "is", "are", "was", "in", "on", "of", "and", "for", "to", "at", "by",
    # People and offices in the news every day. Since significance leads the
    # ranking (news/significance.py), "Trump" is in most days' best stories
    # whatever they are about, and matching on it docked a G7 oil release for
    # yesterday's Iran talks. The families still catch a genuine repeat.
    "trump", "president", "prime", "minister", "government", "police",
    "white", "house", "court", "supreme", "state", "states", "united",
}
_NAME = re.compile(r"\b[A-Z][\w’'.-]{2,}")


# How much of a summary is read for subject. The opening sentence says what a
# story is about; by the third, a plankton story has mentioned "the planet" and
# a climate report has mentioned the moon.
_SUMMARY_CHARS = 220


@lru_cache(maxsize=8192)
def families(title: str, summary: str = "") -> frozenset[str]:
    """Which beats a story belongs to. Usually one, sometimes none.

    The headline decides on a single term. The summary only adds a beat when
    it names two distinct terms from it, so a passing "our planet" in the
    second sentence of a plankton story does not make it astronomy.
    """
    head = summary[:_SUMMARY_CHARS]
    out = set()
    for name, rx in _FAMILY_RX.items():
        if rx.search(title):
            out.add(name)
        elif len({m.group(0).lower() for m in rx.finditer(head)}) >= 2:
            out.add(name)
    return frozenset(out)


def _names(title: str) -> set[str]:
    """Capitalised words worth matching on, from a headline.

    The headline's own first word is skipped: it is capitalised because it is
    first, not because it is a name.
    """
    words = _NAME.findall(title)
    first = re.match(r"\W*(\w+)", title)
    out = set()
    for w in words:
        key = w.strip(".’'-").lower()
        if first and w == first.group(1):
            continue
        if key and key not in _NAME_STOP:
            out.add(key)
    return out


def _mentions(text: str, names: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names)


def penalty(title: str, summary: str,
            recent: list[tuple[int, str, str]]) -> float:
    """Points to dock from a candidate, given what the account just published.

    `recent` is (days_ago, title, summary) for each story the account
    published lately. Days outside the window cost nothing. Names are matched
    from the candidate's headline against the past headline only.
    """
    cand_fam = families(title, summary)
    names = _names(title)
    total = 0.0
    for days_ago, past_title, past_summary in recent:
        if not 0 < days_ago <= WINDOW_DAYS:
            continue
        if (cand_fam & families(past_title, past_summary)
                or _mentions(past_title, names)):
            # Linear fade: yesterday costs the full amount, the edge of the
            # window costs a fifth of it.
            total += PER_PICK * (WINDOW_DAYS + 1 - days_ago) / WINDOW_DAYS
    return min(PENALTY_CAP, round(total, 3))
