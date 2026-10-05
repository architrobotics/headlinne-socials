"""The news-worthiness gate: what it drops, and what it must never drop.

A gate rather than a weight, because a soft capped penalty cannot hold back a
promo code that the interest model finds genuinely interesting.
"""

from headlinne.news import quality as Q


def test_commerce_copy_is_not_news():
    assert Q.reject_reason("Google Workspace Promo Codes: 14% Off for August 2026")
    assert Q.reject_reason("Our expert thinks this telescope will delight stargazers")
    assert Q.reject_reason("Where to buy the new console before it sells out")


def test_a_product_verdict_is_not_an_event():
    assert Q.reject_reason("Dell XPS 13 Review: still the one to beat")
    assert Q.reject_reason("iPhone 18 vs Galaxy S27: which is better?")
    assert Q.reject_reason("The best noise-cancelling headphones in 2026")


def test_listicles_and_filler_are_dropped():
    assert Q.reject_reason("5 Weird Tricks for Having a Brain")
    assert Q.reject_reason("On this day in space! Aug. 15, 1977")
    assert Q.reject_reason("12 states sue to block the merger")


def test_a_term_ending_in_punctuation_still_matches():
    # "watch:" cannot take a trailing word boundary - a colon followed by a
    # space has none - so anchoring it naively let broadcast furniture through.
    assert Q.reject_reason("Watch: Fed Chairman testifies to the House committee")
    assert Q.reject_reason("Quiz: how well do you know the solar system?")
    assert Q.reject_reason("Correction: an earlier version misstated the figure")


def test_a_word_containing_a_marker_is_not_a_listicle():
    # "always to" contains "ways to". Dropping a real story is a silent loss, so
    # the matcher is boundary-anchored in both directions.
    assert Q.reject_reason("Researchers always to blame? Study questions science") is None


def test_a_leading_year_is_not_a_list_count():
    assert Q.reject_reason("2026 was the hottest year on record, scientists confirm") is None
    assert Q.reject_reason("10 years of Pokemon Go and the millions still playing")


def test_real_reporting_passes_untouched():
    for title in (
        "SpaceX rocket crashes into the Moon at 8,700 kilometres per hour",
        "Apple says the iPhone will now warn you before an app reads your location",
        "Immune cells flood into the aging brain, Stanford scientists discover",
        "Fed holds rates steady for a fourth consecutive meeting",
    ):
        assert Q.is_publishable(title), title


def test_the_reason_names_the_rule_and_the_marker():
    reason = Q.reject_reason("Google Workspace Promo Codes: 14% Off")
    assert reason.startswith("commerce:")
    assert ":" in reason


# --------------------------------------------------------------------------- #
# Opinion and diary
# --------------------------------------------------------------------------- #
# Both shapes led reels. An opinion column under a source strip claims eight
# outlets agree with a position only its author holds, and a diary entry has
# nothing to explain - "Prince William to attend King Harald's funeral in
# Norway" took the reel off two unexplained hydrogen clouds.
def test_a_signed_comment_piece_is_not_news():
    assert Q.reject_reason(
        "Reform says we need to choose between climate and economy. "
        "It's wrong | Larry Elliott") == "opinion:byline"
    assert Q.reject_reason(
        "We are finally witnessing the decline of corporate Democrats "
        "| Robert Reich") == "opinion:byline"


def test_a_pipe_that_is_not_a_byline_is_left_alone():
    """Outlets also use the pipe for sections and straplines, and a rule that
    cannot tell the difference would drop real reporting."""
    for title in ("Nvidia | Q3 earnings beat expectations",
                  "Apple unveils M5 | the fastest chip it has shipped",
                  "Storm Bella makes landfall | live coverage from the coast"):
        assert Q.reject_reason(title) != "opinion:byline", title


def test_a_scheduled_non_event_is_not_a_story():
    assert Q.reject_reason(
        "Prince William to attend King Harald's funeral in Norway"
    ) == "diary:to attend"
    assert Q.reject_reason(
        "A guide to this week's election in Zambia") == "diary:a guide to"
    assert Q.reject_reason("Solar eclipse to occur next week. Here is what to know")


def test_the_new_rules_do_not_touch_ordinary_reporting():
    for title in ("FAST finds two mysterious hydrogen clouds with no visible stars",
                  "James Webb Space Telescope observes 72 stars and finds planets",
                  "Germany says Russia behind Leipzig airport drone attack",
                  "Scientists find a human-only gene that may explain our brainpower"):
        assert Q.reject_reason(title) is None, title


def test_event_marketing_is_not_news():
    assert Q.reject_reason(
        "Discover how to take your startup from prototype to production at "
        "TechCrunch Disrupt 2026").startswith("event_promo")
    # A finding phrased with the same verb is untouched.
    assert Q.reject_reason("Scientists discover how the brain stores fear") is None


def test_a_price_cut_as_an_amount_is_commerce():
    assert Q.reject_reason("The MacBook Air M5 is $200 off for the first time in months")
    assert Q.reject_reason("Amazon’s Fire TV Stick 4K is over half off")
    # A fare policy and a government contract are reported the same way, and
    # are news.
    assert Q.reject_reason("Half price rail travel extended to 18-year-olds") is None
    assert Q.reject_reason("Anthropic and Gov. Newsom forge deal allowing California "
                           "government to use Claude at half price") is None


def test_a_live_blog_names_itself_at_the_end():
    assert Q.reject_reason("French education minister says up to 500 schools will "
                           "remain closed – Europe live") == "housekeeping:live"
    assert Q.reject_reason("Bats live far longer than their size predicts") is None


def test_editorials_and_reaction_panels_are_opinion():
    assert Q.reject_reason("The Guardian view on global inequality: extreme wealth "
                           "threatens democracy").startswith("opinion")
    assert Q.reject_reason("Bernie Sanders is right about the four-day workweek – "
                           "but wrong about how").startswith("opinion")
    # "join US" is a country, not an event invitation.
    assert Q.reject_reason("Iran threatens countries that join US ‘economic D-Day’") is None
