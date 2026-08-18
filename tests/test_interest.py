"""The interest score: what it rewards, and the matching bugs it must not regress.

Every case in the first two tests is a real headline that scored wrongly before
the lexicons were boundary-anchored. They are here as regressions, not examples.
"""

from headlinne.news import interest as I


def test_a_brand_name_containing_a_lexicon_word_is_not_universal():
    # "Samsung" contains "sun", and a raw substring match scored a layoff notice
    # as though it were about the solar system.
    assert I.breakdown("Samsung Electronics America cuts 739 jobs")["universal"] == 0.0
    # The real word still matches.
    assert I.breakdown("The sun is more active than models predicted")["universal"] > 0


def test_a_word_containing_a_physical_noun_is_not_concrete():
    # "notice" and "twice" both contain "ice".
    assert I.breakdown("WARN notice says the plant will close")["concrete"] == 0.0
    assert I.breakdown("The rate doubled twice over")["concrete"] == 0.0
    # Actual ice still counts.
    assert I.breakdown("Sea ice reached a new low this week")["concrete"] > 0


def test_a_stem_matches_every_ending_of_its_word():
    scores = {form: I.breakdown(f"Scientists {form} why the reaction stalls")["novelty"]
              for form in ("discover", "discovers", "discovered")}
    assert set(scores.values()) == {0.5}, scores


def test_a_stem_does_not_bleed_into_an_unrelated_word():
    # `star` is not a stem, so "start" must not read as a physical noun.
    assert I.breakdown("Talks start in Geneva on Monday")["concrete"] == 0.0
    assert I.breakdown("The star is older than the galaxy")["concrete"] > 0


def test_first_is_counted_as_novelty_but_never_as_uplift():
    # It sat in both lexicons, so one neutral word scored twice and "first close
    # below IPO price" read as good news.
    b = I.breakdown("Chipotle opens its first outlet in Mexico")
    assert b["novelty"] > 0
    assert b["uplift"] == 0.0


def test_a_market_story_is_not_universal_even_under_a_household_brand():
    product = I.interest("Apple says the iPhone will now warn you before an app "
                         "reads your location")
    market = I.interest("Apple stock notches first close below its IPO price")
    assert product > market, (product, market)


def test_usefulness_is_scored():
    plain = I.breakdown("A phone maker changed a setting")["useful"]
    useful = I.breakdown("Your phone will now warn you before an app reads "
                         "your location")["useful"]
    assert useful > plain


def test_a_process_story_loses_to_an_event():
    event = I.interest("A four-tonne rocket stage struck the Moon at 8,700 km/h")
    process = I.interest("Central bank holds rates and meets again to discuss "
                         "whether policy might change")
    assert event > process
    assert process < 0, "a pure process story should score negative"


def test_death_and_disaster_route_sober_without_scoring_lower():
    assert I.is_sensitive("Ferry capsizes, 40 dead and dozens missing")
    assert not I.is_sensitive("Ferry service returns after a decade")
    # Sensitivity is a routing decision, not a penalty: it must not appear as a
    # term in the score.
    assert "sensitive" not in I._terms("40 dead in a ferry capsize", "", False)


def test_universality_is_reported_separately_so_it_can_be_a_tilt():
    assert I.is_universal("What sleep does to the brain")
    assert not I.is_universal("Council approves the borough budget speech")


def test_a_repeated_word_does_not_max_a_term_on_its_own():
    once = I.breakdown("The moon is bright")["universal"]
    thrice = I.breakdown("The moon, the moon, the moon")["universal"]
    assert once == thrice


def test_the_breakdown_explains_the_total():
    b = I.breakdown("Immune cells flood into the aging brain, scientists discover")
    assert b["total"] == round(I.interest(
        "Immune cells flood into the aging brain, scientists discover"), 2)
    for term in ("concrete", "novelty", "surprise", "universal", "useful",
                 "uplift", "standalone", "procedural"):
        assert term in b, term
