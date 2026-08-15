"""Find the other outlets that covered a story, once that story has been chosen.

Clustering and corroboration look like the same problem and are not. Clustering
decides "are these one post?" and must be conservative: fusing two distinct
stories produces a carousel about nothing. Corroboration decides "how many
outlets reported this event?" and needs recall, because a story covered by six
outlets that we can only prove two of is a story we under-report.

Running both off one similarity score meant one of them was always wrong. On a
297-story day the merge threshold produced 288 events, only 9 of which had a
second source - so Story.verified was false for roughly 97% of the feed, and
the source strip would have been honest but almost always thin.

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
"""

from __future__ import annotations

import math
import re
from collections import Counter

from ..models import Story

# A term must be shared by both headlines and be distinctive in the corpus.
MIN_SHARED_TERMS = 2

# Shared distinctive weight, divided by log(corpus size) so the bar does not
# drift with how many stories a day happens to bring in. Measured on live feeds:
#
#   4.18  Apple proposes to take a 15% cut ...      | same story
#   6.91  Talks to sell PayPal to Stripe ...        | same story   (weakest true)
#   1.51  Samsung headphones vs Fold review         | different    (strongest false)
#
# 2.60 sits well clear of the false pair with margin on both sides. Two earlier
# versions were worse: normalising by the shorter headline's weight let a
# four-word title clear the bar on two shared brand names, and matching on
# headlines alone left only 0.79 between the weakest true pair and the strongest
# false one - too thin to trust on a day this had not been measured against.
MIN_SCORE = 2.60

# A shared entity must also be a *distinctive* one. "African", "Ocean" and "Aug"
# are capitalised and shared by any number of unrelated stories; measured live,
# they let an Ebola outbreak corroborate a whale survey and a Pacific storm
# corroborate a solar eclipse. Requiring the shared entities to carry real
# inverse-document-frequency weight removes those without touching genuine
# matches, where the shared entity is a specific place or organisation.
MIN_ENTITY_WEIGHT = 3.4

# And there must be more than one of them. A single shared entity is a
# coincidence: measured live, a Pacific storm and a solar eclipse photo shared
# exactly "Ocean" and nothing else, while the storm and a genuine second report
# of it shared five - Hawaii, Lala, Pacific, Big, Island. Two accounts of one
# event name several of the same specifics; two unrelated ones rarely name two.
MIN_SHARED_ENTITIES = 2

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
    strikes" - enough to clear an IDF bar and put two outlets on a source strip
    for a story they never covered. They share no entity, so requiring one
    removes them while leaving Israeli/Lebanon/Hezbollah matches untouched.

    Sentence-initial words are skipped: every headline capitalises its first
    word, and that says nothing about what it is about.
    """
    found: set[str] = set()
    for sentence in re.split(r"[.!?]\s+", f"{story.title}. {story.summary}"):
        # Skip the first word of every sentence: it is capitalised by grammar,
        # not because it names anything.
        for word in sentence.split()[1:]:
            match = _CAPITALISED.match(word)
            if match:
                found.add(match.group(1).lower())
    return found - _STOP - _CALENDAR


def _signature(story: Story) -> set[str]:
    """The terms that identify an event: headline plus summary.

    Headlines alone are too short to separate a real match from a coincidental
    one. Measured on live feeds, adding the summary lifted the weakest true pair
    from 2.30 to 6.91 while leaving the strongest false pair unmoved at 1.51 -
    the separation widens from 0.79 to 5.40, because two reports of the same
    event share their specifics while two unrelated ones share only a brand.
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


def agreement(a: Story, b: Story, idf: dict[str, float],
              corpus_size: int = 0) -> float:
    """How strongly two headlines look like the same event.

    The result is shared distinctive weight scaled by corpus size, so it is
    comparable across a quiet day and a busy one. Compare against MIN_SCORE.
    """
    if is_roundup(a.title, a.summary) or is_roundup(b.title, b.summary):
        return 0.0
    # A shared named entity is required, and it must be a distinctive one.
    # Without the entity requirement two unrelated tragedies corroborate on
    # casualty vocabulary; without the weight requirement they corroborate on
    # "African" or "Ocean".
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


def corroborate(story: Story, corpus: list[Story],
                idf: dict[str, float] | None = None,
                *, min_score: float = MIN_SCORE) -> list[Story]:
    """Other outlets' reports of the same event, best match first.

    Only returns stories from a different source than `story`, and never the
    story itself.
    """
    idf = build_idf(corpus) if idf is None else idf
    n = len(corpus)
    hits: list[tuple[float, Story]] = []
    seen_sources: set[str] = {story.source}
    for other in corpus:
        if other is story or other.url == story.url:
            continue
        if other.source in seen_sources:
            continue
        score = agreement(story, other, idf, n)
        if score >= min_score:
            hits.append((score, other))
    hits.sort(key=lambda pair: -pair[0])

    out: list[Story] = []
    for _, other in hits:
        if other.source in seen_sources:
            continue
        seen_sources.add(other.source)
        out.append(other)
    return out


def attach(stories: list[Story], corpus: list[Story]) -> None:
    """Fill in corroborating_sources and verified for each chosen story.

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
        story.verified = story.source_count >= 2
