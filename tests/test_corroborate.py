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


# Summaries are as full as a real feed's, because sparse ones do not exercise
# the entity requirement: two accounts of one event name several of the same
# places, and a two-line fixture never gets the chance to.
AIRSTRIKE = _s("Israeli strikes on southern Lebanon kill 11 in worst toll since June",
               "Strikes across southern Lebanon killed 11 people, officials said. "
               "Hezbollah confirmed several of the dead were its members, and "
               "Israel said it had targeted infrastructure near Nabatieh.",
               "Guardian")
AIRSTRIKE_2 = _s("Eleven killed in Israeli strikes on southern Lebanon, authorities say",
                 "Lebanese authorities said Israeli strikes hit homes near "
                 "Nabatieh in southern Lebanon. Hezbollah said its members were "
                 "among those killed.", "BBC World")
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


# --------------------------------------------------------------------------- #
# Three more false positives, each found by auditing a live run
# --------------------------------------------------------------------------- #
STORM = _s("Hawaii's Big Island lashed by rain and wind as Tropical Storm Lala closes in",
           "This satellite image shows Tropical Storm Lala over the Pacific Ocean.",
           "AP Top News")
STORM_2 = _s("Hurricane poised to hit Hawaii as El Nino stirs the Pacific",
             "Tropical Storm Lala neared Hawaii's Big Island on Saturday.", "Phys.org")
ECLIPSE = _s("Total Solar Eclipse in Sunflower Field",
             "This image shows the eclipse over the Ocean, Aug 2026.", "NASA")
BULLETIN = _s("DR Congo Ebola outbreak spreads to sixth province",
              "In tonight's edition: the Ebola outbreak spreads, and Instagram "
              "accounts fuel the Ceuta border crisis.", "France 24")
CEUTA = _s("Instagram accounts fuelling Ceuta crisis with paid advice",
           "Smugglers advertise routes across the Ceuta border.", "BBC World")


def test_one_shared_entity_is_a_coincidence_not_a_match():
    """A Pacific storm and an eclipse photo shared exactly 'Ocean'."""
    corpus = _corpus(STORM, STORM_2, ECLIPSE)
    idf, n = _idf(corpus), len(corpus)
    assert C.agreement(STORM, STORM_2, idf, n) >= C.MIN_SCORE
    assert C.agreement(STORM, ECLIPSE, idf, n) < C.MIN_SCORE


def test_a_bulletin_cannot_corroborate_its_own_side_stories():
    """'In tonight's edition:' runs six unrelated items under one headline."""
    corpus = _corpus(BULLETIN, CEUTA)
    assert C.is_roundup(BULLETIN.title, BULLETIN.summary)
    assert C.agreement(BULLETIN, CEUTA, _idf(corpus), len(corpus)) == 0.0


def test_month_abbreviations_are_not_entities():
    assert "aug" not in C._entities(ECLIPSE)
