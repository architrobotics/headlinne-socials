"""Corroboration must never claim an outlet reported something it did not.

Every case here is taken from a live run. The airstrike/earthquake pair is the
important one: an earlier version of this module put NPR and Phys.org on the
source strip of an Israeli airstrike story because both had covered an
Indonesian earthquake, and the two shared "early, homes, people, saturday,
strikes". It cleared the weight bar comfortably. Requiring a shared named
entity is what removes it.
"""

from __future__ import annotations

from headlinne.models import Story
from headlinne.news import corroborate as C


def _s(title, summary="", source="Example"):
    return Story(title=title, summary=summary, url="https://x/" + title[:9],
                 category="Geopolitics", source=source, tier=1.2,
                 published_iso="2026-08-15T09:00:00+00:00")


AIRSTRIKE = _s("Israeli strikes on southern Lebanon kill 11 in worst toll since June",
               "Hezbollah said the attacks hit homes early on Saturday.", "Guardian")
AIRSTRIKE_2 = _s("Eleven killed in Israeli strikes on southern Lebanon, authorities say",
                 "Lebanon said homes were hit and people fled.", "BBC World")
QUAKE = _s("Magnitude 7.7 earthquake strikes off the coast of Indonesia",
           "People fled homes in Indonesia early on Saturday.", "Phys.org")


# Inverse document frequency needs a corpus to be a frequency *of* something.
# Three stories cannot tell you which words are rare, so every test runs against
# a realistic day's worth of unrelated filler - the same conditions the pipeline
# sees, where the corpus is a few hundred headlines.
_FILLER = [
    _s(f"Company {i} announces a quarterly update for investors",
       f"Analysts covering sector {i} said the outlook was unchanged.",
       f"Outlet{i}")
    for i in range(60)
]


def _corpus(*stories):
    return [*stories, *_FILLER]


def _idf(corpus):
    return C.build_idf(corpus)


def test_two_reports_of_one_event_corroborate():
    corpus = _corpus(AIRSTRIKE, AIRSTRIKE_2, QUAKE)
    score = C.agreement(AIRSTRIKE, AIRSTRIKE_2, _idf(corpus), len(corpus))
    assert score >= C.MIN_SCORE, score


def test_two_unrelated_disasters_do_not():
    """The regression. Casualty vocabulary is not agreement."""
    corpus = _corpus(AIRSTRIKE, AIRSTRIKE_2, QUAKE)
    score = C.agreement(AIRSTRIKE, QUAKE, _idf(corpus), len(corpus))
    assert score < C.MIN_SCORE, f"airstrike corroborated by an earthquake ({score})"


def test_a_shared_entity_is_required():
    assert C._entities(AIRSTRIKE) & C._entities(AIRSTRIKE_2)
    assert not (C._entities(AIRSTRIKE) & C._entities(QUAKE))


def test_calendar_words_are_not_entities():
    """Two stories filed on one Saturday are not one story."""
    assert "saturday" not in C._entities(QUAKE)
    assert "june" not in C._entities(AIRSTRIKE)


def test_sentence_initial_capitals_are_not_entities():
    assert "eleven" not in C._entities(AIRSTRIKE_2)


def test_roundups_never_corroborate():
    recap = _s("Engadget review recap: everything we tested this week",
               "Including the new foldable.", "Engadget")
    single = _s("Samsung Galaxy Z Fold 8 Ultra review", "The Ultra fold.", "Ars")
    corpus = _corpus(recap, single)
    assert C.is_roundup(recap.title)
    assert C.agreement(single, recap, _idf(corpus), len(corpus)) == 0.0


def test_an_outlet_never_corroborates_itself():
    same = _s("Israeli strikes on southern Lebanon kill 11", "Again.", "Guardian")
    out = C.corroborate(AIRSTRIKE, _corpus(AIRSTRIKE, same))
    assert all(o.source != AIRSTRIKE.source for o in out)


def test_attach_sets_verified_only_with_a_second_outlet():
    corpus = _corpus(AIRSTRIKE, AIRSTRIKE_2, QUAKE)
    C.attach([AIRSTRIKE, QUAKE], corpus)
    assert AIRSTRIKE.verified is True
    assert "BBC World" in AIRSTRIKE.corroborating_sources
    assert QUAKE.verified is False, "a lone report is not verified"
