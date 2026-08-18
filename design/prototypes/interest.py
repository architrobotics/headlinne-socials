"""Verification harness: does the proposed interest score actually beat the
consensus score at picking a story worth posting?

Runs both rankers over live RSS. The old scorer is a faithful reimplementation
of headlinne/news/ranking.py::_score. The new one splits verification (a gate)
from interest (the ranking).
"""
from __future__ import annotations
import math, re, sys, collections

try:
    import feedparser
except ImportError:
    sys.exit("pip install feedparser")

# --------------------------------------------------------------------------- #
# Feeds: the current config, plus the wonder tier it is missing
# --------------------------------------------------------------------------- #
CURRENT = [
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", 1.4),
    ("BBC Business",   "https://feeds.bbci.co.uk/news/business/rss.xml", 1.4),
    ("BBC World",      "https://feeds.bbci.co.uk/news/world/rss.xml", 1.4),
    ("Ars Technica",   "https://feeds.arstechnica.com/arstechnica/index", 1.1),
    ("Guardian World", "https://www.theguardian.com/world/rss", 1.1),
    ("The Verge",      "https://www.theverge.com/rss/index.xml", 1.1),
]
WONDER = [
    ("Phys.org",       "https://phys.org/rss-feed/", 1.0),
    ("Space.com",      "https://www.space.com/feeds/all", 1.0),
    ("New Scientist",  "https://www.newscientist.com/subject/space/feed/", 1.0),
    ("Sci Daily",      "https://www.sciencedaily.com/rss/top/science.xml", 1.0),
]

# --------------------------------------------------------------------------- #
# OLD: headlinne/news/ranking.py weights, reproduced
# --------------------------------------------------------------------------- #
_SOURCE_W, _TIER_W, _KEYWORD_W, _RECENCY_W = 3.2, 1.6, 0.9, 1.0
_LOW_VALUE_PENALTY = 1.15
_LOW_VALUE = ("opinion", "editorial", "live:", "watch:", "video:", "in pictures",
              "recap", "best deals", "how to", "review:", "sponsored",
              "explainer", "podcast", "listen:", "quiz", "horoscope")
HIGH_INTEREST = ("election", "inflation", "rates", "sanctions", "tariff", "war",
                 "court", "ruling", "summit", "treaty", "gdp", "recession",
                 "central bank", "regulator", "parliament", "senate", "vote")


def old_score(title: str, tier: float, sources: int, hours: float) -> float:
    t = title.lower()
    s = _SOURCE_W * math.log2(sources + 1)
    s += _TIER_W * tier
    s += _KEYWORD_W * min(sum(1 for k in HIGH_INTEREST if k in t), 4)
    s += _RECENCY_W * math.exp(-hours / 18.0)
    s -= _LOW_VALUE_PENALTY * min(sum(1 for m in _LOW_VALUE if m in t), 2)
    return s


# --------------------------------------------------------------------------- #
# NEW: interest score. Verification is a gate, not a term.
# --------------------------------------------------------------------------- #
UNITS = r"(km/h|mph|kg|tonne|tonnes|metres|meters|miles|light-years|degrees|" \
        r"years|billion|million|trillion|percent|%|km|ft|mm)"
NOVELTY = ("first", "first-ever", "never before", "unprecedented", "discovered",
           "confirmed", "found", "detected", "spotted", "new species",
           "breakthrough", "record", "oldest", "largest", "smallest")
SURPRISE = ("turned out", "actually", "instead", "contrary", "unexpected",
            "surprised", "mystery", "puzzle", "baffl", "not what", "wrong",
            "reversal", "but it")
PHYSICAL = ("rocket", "crater", "moon", "asteroid", "comet", "volcano", "whale",
            "fossil", "glacier", "telescope", "satellite", "reactor", "bridge",
            "tunnel", "ship", "aircraft", "brain", "cell", "virus", "star",
            "planet", "ice", "ocean", "forest", "storm", "quake", "dinosaur")
PROCEDURAL = ("holds", "held", "meets", "meeting", "discuss", "considers",
              "is set to", "could", "may ", "might", "expected to", "plans to",
              "unchanged", "consecutive", "talks", "urges", "calls for",
              "warns", "seeks", "weighs", "mulls", "eyes ", "to decide",
              "ahead of", "amid", "continues", "latest")
# Applies to everyone, regardless of where they live or what they already know.
UNIVERSAL = ("moon", "space", "earth", "ocean", "brain", "sleep", "body",
             "human", "humans", "cancer", "memory", "ageing", "aging", "heart",
             "climate", "whale", "bird", "forest", "water", "food", "light",
             "sun", "star", "planet", "universe", "cell", "dna", "gravity",
             "phone", "internet", "battery", "energy", "everyone", "people")
# Local, expert-only or in-group stories. The opposite of universal.
PAROCHIAL = ("council", "borough", "constituency", "senator", "mp ", "mps ",
             "shares", "shareholder", "earnings", "quarterly", "ftse",
             "nasdaq", "premier league", "transfer", "midfielder", "by-election",
             "reshuffle", "committee", "select committee", "budget speech")
# Awe, recovery, progress. Positive emotion transmits better than negative.
UPLIFT = ("discovered", "breakthrough", "recovering", "reclaiming", "restored",
          "revived", "saved", "thriving", "rebound", "success", "cure",
          "solved", "first", "record", "milestone", "returns", "revealed",
          "brighter", "hope", "repair", "better than")

CONTEXT_DEP = ("continues", "latest", "amid ongoing", "again", "further",
               "another round", "as it happened", "update")


def _hits(text: str, bag) -> int:
    return sum(1 for k in bag if k in text)


def interest(title: str, summary: str = "", has_image: bool = False) -> dict:
    t = (title + " " + summary).lower()
    numerals = len(re.findall(r"\d", title))
    units = len(re.findall(UNITS, t))

    concrete = min(1.0, (_hits(t, PHYSICAL) * 0.45) + (units * 0.3)
                   + (0.25 if numerals else 0))
    novelty = min(1.0, _hits(t, NOVELTY) * 0.5)
    surprise = min(1.0, _hits(t, SURPRISE) * 0.55)
    image = 1.0 if has_image else 0.0
    selfcontained = max(0.0, 1.0 - _hits(t, CONTEXT_DEP) * 0.5)
    procedural = min(1.0, _hits(t, PROCEDURAL) * 0.34)
    universal = max(0.0, min(1.0, _hits(t, UNIVERSAL) * 0.4
                             - _hits(t, PAROCHIAL) * 0.5))
    uplift = min(1.0, _hits(t, UPLIFT) * 0.45)

    score = (3.0 * concrete + 2.4 * novelty + 2.2 * surprise
             + 2.6 * universal + 1.8 * uplift
             + 1.4 * image + 1.2 * selfcontained - 3.0 * procedural)
    return dict(score=round(score, 2), concrete=round(concrete, 2),
                novelty=round(novelty, 2), surprise=round(surprise, 2),
                universal=round(universal, 2), uplift=round(uplift, 2),
                image=image, selfcont=round(selfcontained, 2),
                procedural=round(procedural, 2))


# Stories about death and disaster score high on "concrete + numerals" and must
# never be ranked as though they were delightful. They are not disqualified -
# they are routed to a plain, sober treatment with no Pip bubble and no wonder
# framing. This guard exists because the first live run put a ferry disaster
# fourth on an interestingness list.
SENSITIVE = ("dead", "death", "deaths", "killed", "kills", "killing", "casualt",
             "massacre", "shooting", "stabbed", "murder", "victims", "bodies",
             "capsiz", "crash kills", "quake", "earthquake", "famine",
             "genocide", "atrocit", "suicide", "abuse", "missing after",
             "toll", "wounded", "injured", "hostage", "airstrike", "bombing")


def is_sensitive(title: str, summary: str = "") -> bool:
    return _hits((title + " " + summary).lower(), SENSITIVE) > 0


def gate(sources: int) -> bool:
    """Verification is pass/fail, not a ranking term. No exceptions."""
    return sources >= 2


# --------------------------------------------------------------------------- #
def harvest(feeds, limit=25):
    out = []
    for name, url, tier in feeds:
        try:
            d = feedparser.parse(url)
        except Exception as e:                       # noqa: BLE001
            print(f"  ! {name}: {e}"); continue
        if not d.entries:
            print(f"  ! {name}: no entries"); continue
        for e in d.entries[:limit]:
            title = re.sub(r"\s+", " ", e.get("title", "")).strip()
            if not title:
                continue
            summ = re.sub("<[^>]+>", " ", e.get("summary", ""))[:300]
            img = bool(e.get("media_content") or e.get("media_thumbnail")
                       or "img" in e.get("summary", ""))
            out.append(dict(title=title, summary=summ, src=name,
                            tier=tier, image=img))
        print(f"  · {name}: {len(d.entries)} entries")
    return out


def cluster_counts(items):
    """Crude cross-source count: shared significant words in the headline."""
    STOP = set("the a an and or of to in on for with at by from as is are was "
               "were be been it its this that new says said will has have had "
               "but not you how why what when who".split())
    keyed = []
    for it in items:
        toks = {w for w in re.findall(r"[a-z]{4,}", it["title"].lower())
                if w not in STOP}
        keyed.append((it, toks))
    for it, toks in keyed:
        n = sum(1 for other, otoks in keyed
                if other is not it and len(toks & otoks) >= 3)
        it["sources"] = 1 + n
    return items


def show(title, rows, key):
    print(f"\n{'='*76}\n{title}\n{'='*76}")
    for i, it in enumerate(rows[:8], 1):
        print(f"{i}. [{it[key]:>6.2f}] ({it['src']}, {it['sources']}src) "
              f"{it['title'][:88]}")


if __name__ == "__main__":
    print("Fetching current feed set...")
    cur = harvest(CURRENT)
    print("Fetching wonder tier...")
    won = harvest(WONDER)
    allitems = cluster_counts(cur + won)
    print(f"\n{len(cur)} current-config items, {len(won)} wonder items, "
          f"{len(allitems)} total")

    for it in allitems:
        it["old"] = old_score(it["title"], it["tier"], it["sources"], 6.0)
        it["new"] = interest(it["title"], it["summary"], it["image"])["score"]

    # OLD ranker only ever sees the current feed set
    old_pool = sorted([i for i in cur], key=lambda x: x["old"], reverse=True)
    show("OLD RANKER — current weights, current feeds", old_pool, "old")

    for it in allitems:
        it["sensitive"] = is_sensitive(it["title"], it["summary"])

    ungated = sorted(allitems, key=lambda x: x["new"], reverse=True)
    show("NEW RANKER — no gate, no sensitivity guard (what I proposed)",
         ungated, "new")

    passed = [i for i in allitems if gate(i["sources"])]
    new_pool = sorted([i for i in passed if not i["sensitive"]],
                      key=lambda x: x["new"], reverse=True)
    show("NEW RANKER — 2-source gate + sensitivity routing", new_pool, "new")

    sens = sorted([i for i in passed if i["sensitive"]],
                  key=lambda x: x["new"], reverse=True)
    show("ROUTED TO SOBER TREATMENT (still published, no wonder framing)",
         sens, "new")
    print(f"\ngate: {len(passed)}/{len(allitems)} stories reached 2+ sources")
    print(f"of those, {len(sens)} routed sober, {len(new_pool)} eligible for Pip")

    print(f"\n{'='*76}\nWHERE THE WONDER FEEDS LAND IN EACH\n{'='*76}")
    src_old = collections.Counter(i["src"] for i in old_pool[:8])
    src_new = collections.Counter(i["src"] for i in new_pool[:8])
    print("old top-8 sources:", dict(src_old))
    print("new top-8 sources:", dict(src_new))
