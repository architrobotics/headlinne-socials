"""The quality gate: what is not news, however well it scores.

Every rejection below was ranked into one day's top twenty-five by the interest
model before this gate existed. A promo-code page placed thirteenth.
"""

from __future__ import annotations

from headlinne.news import quality as Q

REJECTED = [
    "Google Workspace Promo Codes: 14% Off for August 2026",
    "Our expert thinks this portable Celestron telescope will delight stargazers",
    "5 Weird Tricks for Having a Brain",
    "On this day in space! Aug. 15, 1977: Mysterious 'Wow!' Signal",
    "Samsung Galaxy Z Fold 8 Ultra review: The ultra fold",
    "Dell XPS 13 Review: Move Over, Neo",
    "iPhone 18 vs Pixel 11: which is better?",
    "The best robot vacuums for 2026",
    "Engadget review recap: everything we tested this week",
    "'My heart breaks into a million pieces': emotional tributes pour in",
    "10 things you should know before buying an EV",
    "Live updates: markets react",
]

KEPT = [
    "A SpaceX rocket crashed into the Moon at 8,700 kilometres per hour",
    "Israeli strikes on southern Lebanon kill 11 in worst toll since June",
    "Immune cells flood into the aging brain, Stanford scientists discover",
    "DR Congo Ebola outbreak spreads to sixth province",
    "Bank of England holds interest rates for a fourth consecutive meeting",
    "After commercial whaling nearly erased them, blue whales are returning",
    "2026 budget raises the threshold for the top rate of income tax",
    "First test flight of largest all-electric aircraft used just $5 of electricity",
]


def test_commerce_and_product_copy_is_rejected():
    for title in REJECTED:
        assert not Q.is_publishable(title), f"should have been dropped: {title}"


def test_real_reporting_survives():
    for title in KEPT:
        reason = Q.reject_reason(title)
        assert reason is None, f"dropped real news {title!r} for {reason}"


def test_a_year_at_the_start_is_not_a_listicle():
    """'2026 budget raises...' must not read as a numbered list."""
    assert Q.is_publishable("2026 budget raises the threshold for income tax")
    assert not Q.is_publishable("7 budget changes you should know about")


def test_the_reason_names_the_rule_that_fired():
    reason = Q.reject_reason("Google Workspace Promo Codes: 14% Off")
    assert reason and reason.startswith("commerce:")


def test_summaries_do_not_trigger_rejection():
    """A story that mentions a price is not an advert."""
    assert Q.is_publishable(
        "Regulator fines the airline over cancelled flights",
        "The best outcome for passengers is a refund, the review said.")
