"""Correct a story's category when the headline plainly contradicts its feed.

A story's category comes from the feed it arrived on - `Feed(..., "Geopolitics",
1.4)` in config - and nothing downstream ever looks at what the story is
actually about. That is right most of the time and badly wrong at the edges,
because general feeds carry everything: `phys.org` files a bone-marrow discovery
under a world-news feed, a space feed carries an executive order about a space
academy. Measured over the reels published in August and September, "Scientists
discover new 'immune hubs' in skull bone marrow" went out labelled Geopolitics
and "President Trump Signs Executive Order to Create US Space Academy" went out
labelled Science.

The label is not cosmetic. It picks the hashtags, it sets the eyebrow above the
headline, and it is what the day's category weights are computed from - so one
mislabelled story tilts what the *next* format is allowed to cover.

This is deliberately a correction and not a classifier. The feed's label is the
default and keeps every ambiguous case; the override fires only when the
headline shows clear evidence of one category and none at all of the one it was
given. On the 9,562 headlines in content/ that is a few per cent, which is the
intended shape: a wrong label is worth fixing, a coin-flip is not.
"""

from __future__ import annotations

from ._lexicon import compile_terms, distinct_hits

# Vocabulary that only really appears in one beat. Words that straddle two
# categories are left out on purpose - "startup" is finance and technology,
# "tariff" is finance and geopolitics, "president" is in every category's
# stories - because a term that could go either way cannot be evidence.
_TERMS: dict[str, tuple[str, ...]] = {
    "Science": (
        "astronomer*", "telescope", "galaxy", "galaxies", "exoplanet",
        "asteroid", "comet", "nebula", "black hole", "supernova",
        "researcher*", "scientist*", "study finds", "new study", "peer-review*",
        "fossil", "dinosaur*", "species", "genome", "gene", "protein",
        "neuron*", "molecule", "enzyme", "bacteri*", "microb*",
        "physicist*", "biologist*", "geologist*", "paleontolog*", "archaeolog*",
        "quantum", "particle", "isotope", "photosynthesis", "ecosystem",
        "clinical trial", "antibod*", "immune", "bone marrow", "stem cell*",
    ),
    "Technology": (
        "smartphone", "app store", "operating system", "browser", "chipset",
        "semiconductor", "gpu", "processor", "algorithm", "software",
        "open source", "data breach", "cybersecurity", "malware", "encryption",
        "large language model", "chatbot", "machine learning",
        "android", "ios ", "iphone", "laptop", "cloud computing", "data centre",
        "data center", "social media platform", "user data",
    ),
    "Finance": (
        "shares", "share price", "stock market", "earnings", "quarterly results",
        "revenue", "profits", "ipo", "listing", "valuation", "market cap",
        "interest rate*", "inflation", "central bank", "bond*", "yield*",
        "hedge fund", "private equity", "venture capital", "funding round",
        "merger", "acquisition", "takeover bid", "dividend", "bankrupt*",
    ),
    "Geopolitics": (
        "election*", "parliament", "referendum", "coalition government",
        "sanction*", "treaty", "ceasefire", "armistice", "troops", "airstrike*",
        "border", "embassy", "diplomat*", "summit", "coup", "junta",
        "prime minister", "foreign minister", "united nations", "nato",
        "asylum", "refugee*", "deport*", "extradit*", "war crimes",
        "executive order", "signs order", "justice department",
        "state department", "supreme court", "attorney general",
    ),
}

_RX = {name: compile_terms(terms) for name, terms in _TERMS.items()}

# How much better the winning category has to be than the label the feed gave.
# Two distinct terms rather than one, because a single word is as likely to be a
# passing mention as a subject - "a study of election turnout" is Geopolitics.
MIN_EVIDENCE = 2


def evidence(title: str, summary: str = "") -> dict[str, int]:
    """Distinct on-category terms found, per category."""
    text = f"{title} {summary}"
    return {name: distinct_hits(text, rx) for name, rx in _RX.items()}


def recategorise(title: str, summary: str = "", current: str = "") -> str:
    """The category this story is actually about, or `current` if unclear.

    The feed's label wins every tie and every ambiguous case. It only loses when
    the headline shows at least MIN_EVIDENCE terms from one other category and
    none whatsoever from the one it was filed under - a story that is visibly
    about something else, rather than one that merely could be.
    """
    if not title:
        return current
    hits = evidence(title, summary)
    if hits.get(current, 0) > 0:
        return current                       # it shows its own colours: keep it

    best = max(hits, key=lambda name: hits[name])
    if hits[best] < MIN_EVIDENCE or best == current:
        return current

    # A second category with equal evidence means the headline is genuinely
    # mixed, and a coin flip is worse than the label we already have.
    runners = [n for n, c in hits.items() if c == hits[best]]
    if len(runners) > 1:
        return current
    return best
