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


def test_a_verb_is_penalised_in_both_its_forms():
    # The lexicon listed only third-person forms, so "Musicians urge government
    # to ..." scored a full point above "Musicians urges ...". A ranking
    # decision made on grammar is a ranking decision made on nothing.
    for base, third in (("urge", "urges"), ("consider", "considers"),
                        ("seek", "seeks"), ("plan to", "plans to")):
        a = I.breakdown(f"Ministers {base} a ban on drilling")["procedural"]
        b = I.breakdown(f"Ministers {third} a ban on drilling")["procedural"]
        assert a == b > 0, (base, third, a, b)


def test_the_procedural_verbs_do_not_catch_unrelated_words():
    # `urge*` would match "urgent" and `weigh*` would match "weight", which is
    # why these are listed as explicit forms rather than stems.
    assert I.breakdown("An urgent recall of 40,000 batteries")["procedural"] == 0.0
    assert I.breakdown("The weight of the stage was four tonnes")["procedural"] == 0.0


# --------------------------------------------------------------------------- #
# What the scorer must not mistake for interest
# --------------------------------------------------------------------------- #
def test_returns_is_not_uplift():
    """`returns` is a noun as often as a verb and both senses are neutral. It
    scored a celebrity house listing as uplifting and put it second in a pool of
    380, above every discovery in the day."""
    assert "returns" not in I._UPLIFT
    listing = "Chris Pratt's Pacific Palisades home returns to the market for just under $25 million"
    assert I.breakdown(listing, "", True)["uplift"] == 0


def test_a_celebrity_house_listing_does_not_outrank_a_discovery():
    listing = ("Chris Pratt's Pacific Palisades home returns to the market "
               "for just under $25 million")
    finding = "Immune cells have a 'sense of touch,' scientists discover"
    assert I.interest(finding, "", True) > I.interest(listing, "", True)


def test_entertainment_and_sport_are_off_the_beat():
    """The account covers technology, finance and world news. It has already
    published a story card about Travis Kelce confirming his marriage."""
    for headline in (
        "Travis Kelce confirms marriage to Taylor Swift",
        "Premier League club agrees transfer fee for midfielder",
        "Oscars 2027: every nomination, ranked",
    ):
        assert I.breakdown(headline, "", True)["off_beat"] > 0, headline


def test_the_off_beat_penalty_does_not_catch_a_real_business_story():
    """The boundary is soft on purpose. A studio's results, a housing market
    story and an athlete's contract can all be genuinely on the beat."""
    for headline in (
        "House prices fall for a fourth month as mortgage rates bite",
        "Warner Bros results fall as streaming losses widen",
        "Sony raises PlayStation prices after tariff ruling",
    ):
        assert I.breakdown(headline, "", True)["off_beat"] == 0, headline


# --------------------------------------------------------------------------- #
# Sensitivity: broad on purpose, but not blind
# --------------------------------------------------------------------------- #
def test_a_dying_star_is_not_a_casualty():
    """The single best story in a real 380-story day was a nebula showing how
    our own sun ends. "dead star" routed it to plain treatment: no mascot, no
    wonder framing - on the one story most in need of both."""
    for headline in (
        "Scientists find dead star that predicts our sun's future",
        "Astronomers watch a dying star shed its outer layers",
        "The ocean's dead zones are spreading faster than models predicted",
        "How the heat death of the universe actually works",
    ):
        assert not I.is_sensitive(headline), headline


def test_a_real_disaster_is_still_sensitive():
    for headline in (
        "Ferry capsizes off Bali, 40 dead",
        "At least 6 dead after aerial attack",
        "Powerful 7.7 earthquake hits eastern Indonesia",
        "Death toll rises after building collapse",
    ):
        assert I.is_sensitive(headline), headline


def test_a_figurative_phrase_does_not_launder_a_real_death_toll():
    """The guard subtracts figurative uses; it must never clear a text that has
    a genuine casualty term in it as well."""
    assert I.is_sensitive(
        "Earthquake kills 40 near the observatory studying a dead star")
    assert I.is_sensitive("Dead star research halted after lab fire kills two")


# --------------------------------------------------------------------------- #
# The October 2026 pass. Every headline here was a story card or a reel, or
# would have been one on replay, and should not have been.
# --------------------------------------------------------------------------- #
def test_a_return_is_not_a_first():
    comeback = I.breakdown("Celine Dion plays her first concert since 2020")
    visit = I.breakdown("The first papal visit to France in 18 years")
    assert comeback["novelty"] == 0.0
    assert visit["novelty"] == 0.0
    # A real first is untouched.
    assert I.breakdown("The first-ever image of a black hole's shadow")["novelty"] > 0


def test_a_routine_product_launch_is_docked():
    for title in ("Motorola’s wild-looking Signature 27 runs Qualcomm’s new Extreme chipset",
                  "Nacon’s new PS5 controller can mix audio from your phone and console",
                  "Firefox 156 arrives with a forest of forks in its wake",
                  "BMW’s revamped i3 boasts up to 468 miles of range"):
        assert I.breakdown(title)["launch"] == 1.0, title


def test_a_launch_verb_or_a_number_alone_is_not_a_product_launch():
    for title in ("Germany launches first commercial rocket into space",
                  "NASA launches 30 satellites",
                  "Ukraine launches over 600 drones at Moscow region",
                  "UN adds 61 firms to settlements blacklist",
                  "What to know about Trump’s new tariffs on more than 80 countries",
                  "Artemis 2 launches crew around the Moon"):
        assert I.breakdown(title)["launch"] == 0.0, title


def test_off_beat_spectacle_is_docked():
    assert I.breakdown("Celine Dion fever hits Paris as comeback tour opens")["off_beat"] > 0
    assert I.breakdown("Pope Leo celebrates open-air mass before 700,000 people")["off_beat"] > 0


def test_a_headline_of_jargon_scores_below_the_same_finding_in_plain_words():
    jargon = I.interest("Hidden X-ray phase revealed in likely neutron star merger")
    plain = I.interest("Hidden flash revealed in likely collision of two dead stars")
    assert plain > jargon


def test_a_how_to_is_service_not_news():
    assert I.breakdown("How to know it's time to replace your EV battery")["service"] == 1.0
    assert I.breakdown("Think you maxed out your 401(k)? The real limit is higher")["service"] == 1.0
    # "Here's how you can see it" is a finding with a viewing tip, not a how-to.
    assert I.breakdown("A star is exploding - here's how you can see it")["service"] == 0.0
