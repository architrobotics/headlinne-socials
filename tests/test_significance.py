"""news.significance: does this matter in the world today?

Every case below is a real headline from the saved digests in content/, from
the month when the ranker led with interest and the account published a
neutron star, a PS5 controller and a BMW trim level while elections, wars and
price shocks sat underneath.
"""

from __future__ import annotations

from headlinne.news import significance as sig
from tests.helpers import make_story


def _score(title, *, outlets=1, tier=1.2, category="Geopolitics", summary=""):
    return sig.significance(title, summary, outlets=outlets, tier=tier,
                            category=category)


def test_coverage_counts_publishers_not_feeds():
    assert sig.publisher("BBC World") == sig.publisher("BBC Business") == "bbc"
    assert sig.publisher("Guardian World") == "guardian"
    assert sig.publisher("AP Top News") == "ap"
    a = make_story("G7 to release 100 million barrels of oil after Trump threat",
                   source="BBC Business")
    b = make_story("G7 to release 100 million barrels of oil and diesel after "
                   "Trump export threat", source="BBC World")
    c = make_story("G7 to release 100 million barrels of emergency oil after "
                   "Trump threat", source="Guardian Business")
    # Two BBC feeds and one Guardian feed are two publishers, not three.
    assert sig.coverage([a, b, c]) == [2, 2, 2]


def test_real_news_beats_a_vivid_paper():
    brazil = _score("Brazil election goes to run-off as right-wing Flávio "
                    "Bolsonaro wins first round", outlets=6)
    neutron = _score("Hidden X-ray phase revealed in likely neutron star merger",
                     category="Science", tier=1.0)
    plankton = _score("Marine biologists discover new plankton off Oregon coast",
                      category="Science", tier=1.0)
    assert brazil > neutron + 8
    assert brazil > plankton + 8


def test_stakes_beat_a_spec_sheet_even_from_one_outlet():
    ruling = _score("Judge dismisses antitrust lawsuits over Google's AI Overviews",
                    category="Technology", tier=1.1)
    for gadget in ("Nacon launches a PS5 controller with a built-in screen",
                   "Motorola debuts its new Signature 27 smartphone",
                   "The MacBook Air M5 is $200 off for the first time in months",
                   "How to improve your iPhone's call quality",
                   "Meta VR Glasses, Ray-Ban Meta Audio: Specs, Features, Prices"):
        assert ruling > _score(gadget, category="Technology", tier=1.1), gadget


def test_a_question_headline_ranks_below_the_report_of_the_event():
    report = _score("Trump rejects Iran's seven-day peace deal to reopen strait "
                    "of Hormuz", outlets=4)
    debate = _score("Why has Trump rejected Iran's peace proposal?", outlets=4)
    assert report > debate


def test_first_person_features_are_not_the_days_news():
    feature = _score("My wife never went back to work after raising our kids. "
                     "Do I have to share my retirement savings?", category="Finance")
    news = _score("UK diesel price hits all-time high, the RAC says",
                  category="Finance")
    assert news > feature


def test_country_acronyms_are_case_sensitive():
    """"with us" is not the United States and "who" is not the WHO."""
    plain = sig.terms("Tell us who you think won")["actors"]
    named = sig.terms("US and WHO clash over pandemic treaty")["actors"]
    assert plain == 0
    assert named == 2


def test_stakes_match_on_word_boundaries():
    """The lesson news._lexicon was written for: "ai" is not in "said"."""
    for innocent in ("said", "again", "warning", "software", "boiling", "award"):
        assert sig.terms(innocent)["stakes"] == 0, innocent
    for genuine in ("an AI model", "the war in Ukraine", "oil prices", "the election"):
        assert sig.terms(genuine)["stakes"] > 0, genuine


def test_paraphrases_of_one_event_are_one_event():
    """Three wordings of one hack took the reel, the carousel and the story card
    on a replayed day before the day's formats used the loose match."""
    from headlinne.news.ranking import same_event

    a = make_story("OpenAI agent hacked Australia government portal: PM Albanese")
    b = make_story("Rogue OpenAI agent 'infiltrated' Australian government "
                   "website in world first")
    c = make_story("Australia to investigate if OpenAI hack of government health "
                   "website broke the law")
    assert same_event(a, b) and same_event(a, c)
    unrelated = make_story("Trump orders US government to call AI 'Super "
                           "Intelligence'")
    other = make_story("Trump rejects Iran's seven-day peace deal to reopen "
                       "strait of Hormuz")
    assert not same_event(unrelated, other)
