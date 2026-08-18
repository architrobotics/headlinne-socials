"""Find the other outlets that covered a story, and work out whether they agree.

Clustering and corroboration look like the same problem and are not. Clustering
decides "are these one post?" and must be conservative: fusing two distinct
stories produces a carousel about nothing. Corroboration decides "how many
outlets reported this event?" and needs recall, because a story covered by six
outlets that we can only prove two of is a story we under-report.

Running both off one similarity score meant one of them was always wrong. On a
297-story day the merge threshold produced 288 events, only 9 of which had a
second source - so Story.verified was false for roughly 97% of the feed, and the
source strip would have been honest but almost always thin.

Lowering the merge threshold does not fix it. Measured on live feeds:

    0.45  Samsung Galaxy Z Fold 8 Ultra review        | same story
    0.44  Apple proposes to take a 15% cut ...        | same story
    0.36  Talks to sell PayPal to Stripe ...          | same story
    0.27  Samsung has new Galaxy headphones ...       | DIFFERENT story
    0.26  Dell XPS 13 Review ...                      | DIFFERENT story

The false pairs outscore the true one. Plain token overlap weights "review" and
"samsung" exactly like "PayPal", so no single threshold separates them.

So this module scores shared *distinctive* terms instead, weighting each by how
rare it is across the day's own corpus. "PayPal" appears in two headlines and
carries weight; "review" appears in thirty and carries almost none. Two outlets
must share at least MIN_SHARED_TERMS distinctive terms before they corroborate
at all, which is what stops a single shared brand name counting as agreement.

Precision matters more than recall here in one direction only: claiming two
outlets agree when they covered different events is a trust failure, and this
brand is built on the source strip being true. When in doubt, do not corroborate.

This runs on the day's already-fetched corpus. It costs no extra API call and no
network - the coverage was always there, it was the matching that missed it.

Two things happen after the matching, and both exist because the source strip
makes a claim the matching alone cannot support:

  syndication  Six outlets running one agency's copy are one source wearing six
               mastheads. Counting them as six independent confirmations is the
               single easiest way to turn the trust signal into a lie.
  agreement    "8 of 8 outlets agree" claims the outlets were compared on
               something. So they are: the story's central figure is extracted
               from each report and matched, and an outlet that never mentions
               it is recorded as silent rather than as dissenting.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

from ..models import Agreement, Conflict, Story

# A term must be shared by both headlines and be distinctive in the corpus.
MIN_SHARED_TERMS = 2

# Shared distinctive weight, divided by log(corpus size) so the bar does not
# drift with how many stories a day happens to bring in. Measured on live feeds:
#
#   4.18  Apple proposes to take a 15% cut ...      | same story
#   6.91  Talks to sell PayPal to Stripe ...        | same story   (weakest true)
#   1.51  Samsung headphones vs Fold review         | different    (strongest false)
#
# 2.60 sits well clear of the false pair with margin on both sides.
MIN_SCORE = 2.60

# A shared entity must also be a *distinctive* one. "African", "Ocean" and "Aug"
# are capitalised and shared by any number of unrelated stories; measured live,
# they let an Ebola outbreak corroborate a whale survey and a Pacific storm
# corroborate a solar eclipse.
MIN_ENTITY_WEIGHT = 3.4

# And there must be more than one of them. A single shared entity is a
# coincidence: measured live, a Pacific storm and a solar eclipse photo shared
# exactly "Ocean" and nothing else, while the storm and a genuine second report
# of it shared five - Hawaii, Lala, Pacific, Big, Island.
MIN_SHARED_ENTITIES = 2

# Above this, two reports are the same copy rather than two accounts of one
# event. Deliberately high: independent reporters covering one press release do
# converge on its phrasing, and calling that syndication would under-count real
# corroboration. Measured against hand-checked pairs, genuine independent
# coverage of one event sat below 0.80 and verbatim republication above 0.90.
SYNDICATION_RATIO = 0.86

# Roundups name a dozen unrelated subjects and would corroborate all of them.
# They are excluded as *sources* of corroboration; they can still be published.
_ROUNDUP_MARKERS = ("recap", "roundup", "round-up", "week in", "best of",
                    "everything we", "what we know", "live updates",
                    "as it happened", "deals of the", "top stories",
                    "your guide to", "explained:",
                    "in tonight's edition", "in this edition", "also in the",
                    "here are the stories", "the headlines:", "briefing:")

_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{2,}")

_STOP = frozenset("""
the a an and or of to in on for with at by from as is are was were be been it
its this that these those after over amid into new say says said will has have
had but not you how why what when who which their there here more most than
then now just also can could would should may might about against between
first last next year years day days week month report reports according
""".split())


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


_CAPITALISED = re.compile(r"([A-Z][A-Za-z'-]{2,})")

# Capitalised by convention, but they name no one. Two unrelated stories filed
# on the same Saturday are not the same story.
_CALENDAR = frozenset("""
monday tuesday wednesday thursday friday saturday sunday january february march
april may june july august september october november december
mon tue tues wed thu thur thurs fri sat sun
jan feb mar apr jun jul aug sept sep oct nov dec
""".split())


def _entities(story: Story) -> set[str]:
    """Proper nouns: the places, people and organisations a report names.

    This is the discriminator that generic vocabulary cannot fake. Two accounts
    of one event name the same places; two unrelated disasters share only the
    language of disaster. Measured live, an Israeli airstrike in Lebanon and an
    Indonesian earthquake matched at 2.85 on "early, homes, people, saturday,
    strikes" - enough to put two outlets on a source strip for a story they
    never covered. They share no entity, so requiring one removes them while
    leaving Israeli/Lebanon/Hezbollah matches untouched.

    Sentence-initial words are skipped: every headline capitalises its first
    word, and that says nothing about what it is about.
    """
    found: set[str] = set()
    for sentence in re.split(r"[.!?]\s+", f"{story.title}. {story.summary}"):
        for word in sentence.split()[1:]:
            match = _CAPITALISED.match(word)
            if match:
                found.add(match.group(1).lower())
    return found - _STOP - _CALENDAR


def _signature(story: Story) -> set[str]:
    """The terms that identify an event: headline plus summary.

    Headlines alone are too short to separate a real match from a coincidental
    one. Measured on live feeds, adding the summary lifted the weakest true pair
    from 2.30 to 6.91 while leaving the strongest false pair unmoved at 1.51.
    """
    return _terms(f"{story.title} {story.summary}")


def build_idf(corpus: list[Story]) -> dict[str, float]:
    """Inverse document frequency over the day's own headlines.

    Computed per run rather than from a fixed list because what counts as a
    distinctive word changes daily: on a launch day "rocket" is common and
    carries little; most days it is rare and carries a lot.
    """
    n = max(1, len(corpus))
    df: Counter[str] = Counter()
    for story in corpus:
        df.update(_signature(story))
    # Floored at zero: a term carried by most of the corpus tells us nothing,
    # and on a small corpus the unclamped form goes negative, which would let
    # common words subtract from a genuine match.
    return {term: max(0.0, math.log(n / (1 + count)))
            for term, count in df.items()}


def _weight(terms: set[str], idf: dict[str, float]) -> float:
    return sum(idf.get(t, 0.0) for t in terms)


def is_roundup(title: str, summary: str = "") -> bool:
    """A post that lists many subjects cannot vouch for any one of them.

    The summary is checked as well as the headline. Broadcast bulletins open
    "In tonight's edition:" and then run through six unrelated stories under a
    headline naming only the first, which is how a Congo Ebola report came to
    corroborate a piece about Instagram accounts in Ceuta.
    """
    low = f"{title} {summary[:160]}".lower()
    return any(m in low for m in _ROUNDUP_MARKERS)


def agreement_score(a: Story, b: Story, idf: dict[str, float],
                    corpus_size: int = 0) -> float:
    """How strongly two headlines look like the same event.

    The result is shared distinctive weight scaled by corpus size, so it is
    comparable across a quiet day and a busy one. Compare against MIN_SCORE.
    """
    if is_roundup(a.title, a.summary) or is_roundup(b.title, b.summary):
        return 0.0
    shared_entities = _entities(a) & _entities(b)
    if len(shared_entities) < MIN_SHARED_ENTITIES:
        return 0.0
    if _weight(shared_entities, idf) < MIN_ENTITY_WEIGHT:
        return 0.0
    shared = _signature(a) & _signature(b)
    if len(shared) < MIN_SHARED_TERMS:
        return 0.0
    scale = math.log(max(corpus_size, math.e))
    return _weight(shared, idf) / scale


# --------------------------------------------------------------------------- #
# Syndication
# --------------------------------------------------------------------------- #
# An agency credit inside the copy. A story that says "(Reuters)" is not an
# independent confirmation of a Reuters story, it *is* the Reuters story.
_WIRE_CREDIT = re.compile(
    r"\(\s*(reuters|ap|afp|pa media|dpa|ani|pti)\s*\)"
    r"|\b(?:reuters|associated press|agence france-presse|press association)\b"
    r"\s*(?:/|-|–|—|contributed|reported)",
    re.I)


def wire_credit(story: Story) -> str | None:
    """The agency this report is credited to, if it says so in the copy."""
    match = _WIRE_CREDIT.search(f"{story.title} {story.summary}")
    if not match:
        return None
    return (match.group(1) or match.group(0)).strip("()/-–— ").lower()


def _same_copy(a: Story, b: Story) -> bool:
    """Two reports that are one piece of copy rather than two accounts of it.

    Verbatim republication is the common shape - an agency story carried whole -
    so a high text ratio is the primary test. A shared explicit agency credit
    lowers the bar, because at that point both reports have told us themselves
    where the words came from.
    """
    text_a = f"{a.title} {a.summary}".strip().lower()
    text_b = f"{b.title} {b.summary}".strip().lower()
    if not text_a or not text_b:
        return False
    ratio = SequenceMatcher(None, text_a, text_b).ratio()
    credit_a, credit_b = wire_credit(a), wire_credit(b)
    if credit_a and credit_a == credit_b:
        return ratio >= SYNDICATION_RATIO - 0.16
    return ratio >= SYNDICATION_RATIO


def collapse_syndication(reports: list[Story]) -> list[list[Story]]:
    """Group reports that are the same copy. Each group is one independent voice.

    Six outlets carrying one agency story are six mastheads on one report. A
    receipt strip that counts them as six independent confirmations is not a
    thin claim, it is a false one - and it fails in the worst possible
    direction, because the stories most likely to be syndicated are the big ones
    the strip is most likely to be shown beside.

    The report kept as each group's representative is the highest-tier one, so
    the named outlet on the strip is the most authoritative carrier.
    """
    groups: list[list[Story]] = []
    for report in reports:
        for group in groups:
            if _same_copy(group[0], report):
                group.append(report)
                break
        else:
            groups.append([report])
    for group in groups:
        group.sort(key=lambda s: (-s.tier, s.source))
    return groups


# --------------------------------------------------------------------------- #
# Claim-level agreement
# --------------------------------------------------------------------------- #
# A figure with its unit and the words around it, which is what makes two
# figures comparable: "12,000 jobs" and "4,000 jobs" are the same claim with
# different answers; "12,000 jobs" and "4,000 miles" are two different facts.
_FIGURE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(%|percent|million|billion|trillion|km/h|kmh|mph|km|kg|tonnes?|tons?|"
    r"met(?:res|ers)|miles|years?|months?|days?|hours?|people|jobs?)?",
    re.I)

_SCALE = {"million": 1e6, "billion": 1e9, "trillion": 1e12}

# How far two figures may differ and still count as the same claim. Outlets
# round: 8,700 km/h and 8,690 km/h are one fact reported twice, while 12,000
# jobs and 4,000 jobs are a genuine dispute worth a card of its own.
AGREEMENT_TOLERANCE = 0.05


def _figures(text: str) -> list[tuple[float, str, str]]:
    """(value, unit, context) for every figure in a piece of text."""
    out: list[tuple[float, str, str]] = []
    for m in _FIGURE.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit in _SCALE:
            value *= _SCALE[unit]
            unit = ""
        # A four-digit bare number is almost always a year, not a quantity.
        if not unit and 1800 <= value <= 2100 and "." not in raw:
            continue
        start = max(0, m.start() - 42)
        context = text[start:m.start()].lower()
        out.append((value, _canonical_unit(unit), context))
    return out


_UNIT_ALIASES = {"kmh": "km/h", "percent": "%", "tons": "tonnes", "ton": "tonnes",
                 "meters": "metres", "meter": "metres", "metre": "metres",
                 "job": "jobs", "year": "years", "month": "months", "day": "days",
                 "hour": "hours"}


def _canonical_unit(unit: str) -> str:
    return _UNIT_ALIASES.get(unit, unit)


def _comparable(a: tuple[float, str, str], b: tuple[float, str, str]) -> bool:
    """Whether two figures are answers to the same question."""
    if a[1] != b[1]:
        return False
    if a[1]:
        return True
    # No unit on either: fall back to shared context words, so "12,000 jobs
    # affected" and "4,000 staff affected" still line up while two unrelated
    # bare numbers do not.
    ca, cb = _terms(a[2]), _terms(b[2])
    return len(ca & cb) >= 1


def central_claim(story: Story) -> tuple[float, str, str] | None:
    """The figure a story is about, if it is about one.

    The headline figure wins: a number the outlet put in the headline is the
    one it is asserting, and it is the one a reader would check.
    """
    in_title = _figures(story.title)
    if in_title:
        return in_title[0]
    body = _figures(story.summary)
    return body[0] if body else None


def _describe(figure: tuple[float, str, str]) -> str:
    value, unit, _ = figure
    text = f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}"
    return f"{text} {unit}".strip()


def assess(story: Story, others: list[Story]) -> Agreement:
    """Build the agreement record for a story and the outlets that corroborate it.

    `others` must already be syndication-collapsed: one entry per independent
    voice. Every one of them counts toward `reported`, because they all covered
    the event. Only the ones that state a comparable figure count toward
    `agree` or `conflict` - an outlet that covered the story without repeating
    the number is silent, and silence is not dissent.
    """
    outlets = [story.source] + [o.source for o in others if o.source != story.source]
    seen, unique = set(), []
    for name in outlets:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)

    record = Agreement(reported=len(unique), outlets=unique)

    claim = central_claim(story)
    if claim is None:
        # Nothing quantified to compare. Every outlet that reported it is
        # counted as agreeing that the event happened, which is the only claim
        # actually on the table.
        record.agree = record.reported
        return record

    record.claim = _describe(claim)
    record.claim_unit = claim[1] or "reported"
    record.agree = 1                       # the originating outlet states it
    for other in others:
        if other.source == story.source:
            continue
        match = next((f for f in _figures(f"{other.title} {other.summary}")
                      if _comparable(claim, f)), None)
        if match is None:
            continue                       # silent on the figure, not dissenting
        spread = abs(match[0] - claim[0]) / max(abs(claim[0]), 1e-9)
        if spread <= AGREEMENT_TOLERANCE:
            record.agree += 1
        else:
            record.conflict += 1
            record.conflicts.append(
                Conflict(outlet=other.source, value=_describe(match)))
    return record


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def corroborate(story: Story, corpus: list[Story],
                idf: dict[str, float] | None = None,
                *, min_score: float = MIN_SCORE) -> list[Story]:
    """Other outlets' independent reports of the same event, best match first.

    Only returns stories from a different source than `story`, never the story
    itself, and never two members of one syndication group.
    """
    idf = build_idf(corpus) if idf is None else idf
    n = len(corpus)
    hits: list[tuple[float, Story]] = []
    for other in corpus:
        if other is story or other.url == story.url or other.source == story.source:
            continue
        score = agreement_score(story, other, idf, n)
        if score >= min_score:
            hits.append((score, other))
    hits.sort(key=lambda pair: -pair[0])

    # One report per outlet first, then one voice per syndication group.
    seen_sources = {story.source}
    per_outlet: list[Story] = []
    for _, other in hits:
        if other.source in seen_sources:
            continue
        seen_sources.add(other.source)
        per_outlet.append(other)

    independent: list[Story] = []
    for group in collapse_syndication([story] + per_outlet):
        representative = group[0]
        if representative.source != story.source:
            independent.append(representative)
    return independent


def attach(stories: list[Story], corpus: list[Story]) -> None:
    """Fill in corroborating sources, verification and agreement for each story.

    Runs after ranking, on the handful of stories actually being published,
    rather than across the whole corpus - the expensive matching is only worth
    doing for what will be posted.
    """
    idf = build_idf(corpus)
    for story in stories:
        others = corroborate(story, corpus, idf)
        known = set(story.corroborating_sources)
        for other in others:
            if other.source != story.source and other.source not in known:
                known.add(other.source)
                story.corroborating_sources.append(other.source)
        story.corroborating_sources.sort()
        story.agreement = assess(story, others)
        story.verified = story.agreement.publishable
