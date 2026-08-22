"""The source strip's arithmetic, and the four shapes it is allowed to take.

One number decides whether this component builds trust or destroys it, and it is
the denominator. Each state below is drawn in design/samples/cards/card_sheet.png.
"""

from headlinne.models import Agreement, Conflict, Story


def test_every_outlet_took_a_position_and_they_matched():
    a = Agreement(reported=8, agree=8)
    assert a.state == "unanimous"
    assert a.label() == "8 of 8 outlets agree"
    assert a.ticks() == (8, 0)


def test_silence_is_reported_as_a_count_not_as_a_fraction():
    # Four agreed and two covered the story without mentioning the figure.
    # "4 of 6" would claim two outlets dissented. They did not.
    a = Agreement(reported=6, agree=4)
    assert a.silent == 2
    assert a.state == "developing"
    assert a.label() == "4 sources agree"


def test_silence_never_draws_a_hollow_tick():
    a = Agreement(reported=6, agree=4)
    filled, hollow = a.ticks()
    assert (filled, hollow) == (4, 0), "a hollow tick reads as disagreement"


def test_a_real_dispute_uses_the_eligible_set_as_the_denominator():
    a = Agreement(reported=9, agree=3, conflict=4,
                  conflicts=[Conflict("Reuters", "12,000 jobs"),
                             Conflict("Financial Times", "4,000 jobs")])
    assert a.eligible == 7
    assert a.silent == 2
    assert a.state == "disputed"
    assert a.label() == "3 of 7 outlets agree"
    assert a.ticks() == (3, 4)


def test_a_single_source_says_so_and_is_not_publishable():
    a = Agreement(reported=1, agree=1)
    assert a.state == "single"
    assert not a.publishable
    assert a.ticks() == (0, 1), "one outlined tick: visibly thin, which is the point"
    assert "Single source" in a.label()


def test_two_independent_outlets_is_the_publishing_bar():
    assert not Agreement(reported=1, agree=1).publishable
    assert Agreement(reported=2, agree=2).publishable


def test_the_numerator_never_exceeds_the_denominator():
    for a in (Agreement(reported=8, agree=8),
              Agreement(reported=6, agree=4),
              Agreement(reported=9, agree=3, conflict=4)):
        assert a.agree <= a.reported
        assert a.eligible <= a.reported
        assert a.silent >= 0


def test_the_record_survives_the_trip_through_disk():
    # It is written to content/<date>/news_digest.json by the generate run and
    # read back by the publish run hours later. A flag that does not round-trip
    # silently loses sensitive routing between the two.
    story = Story(title="t", summary="s", url="u", category="Science",
                  source="Reuters", tier=1.4,
                  published_iso="2026-08-17T00:00:00+00:00",
                  verified=True, sensitive=True,
                  agreement=Agreement(reported=9, agree=3, conflict=4,
                                      claim="12,000 jobs",
                                      conflicts=[Conflict("FT", "4,000 jobs")]))
    back = Story.from_dict(story.to_dict())
    assert back.verified is True
    assert back.sensitive is True
    assert back.agreement.label() == "3 of 7 outlets agree"
    assert back.agreement.conflicts[0].outlet == "FT"


def test_a_record_written_before_agreement_existed_still_loads():
    data = Story(title="t", summary="s", url="u", category="Science",
                 source="Reuters", tier=1.4,
                 published_iso="2026-08-17T00:00:00+00:00").to_dict()
    del data["agreement"]
    assert Story.from_dict(data).agreement.state == "single"


def test_one_outlet_cannot_agree_with_itself():
    # The first live run printed "1 sources agree" - wrong on the grammar and
    # wrong on the claim. Three outlets covered it, one stated the figure, two
    # were silent on it. The coverage is what is true, so that is what is said.
    a = Agreement(reported=3, agree=1,
                  outlets=["Guardian Business", "Sky Business", "Guardian World"])
    assert a.state == "developing"
    assert a.label() == "3 outlets reported this"


def test_two_agreeing_outlets_are_still_reported_as_agreement():
    assert Agreement(reported=6, agree=2).label() == "2 sources agree"


def test_no_label_is_ever_grammatically_wrong():
    # Every reachable shape, not a sampled few. Word-boundary matching, because
    # "11 outlets reported this" contains the substring "1 outlets".
    import re

    singular_plural = re.compile(r"1 (?:sources|outlets)")
    for reported in range(2, 13):
        for agree in range(0, reported + 1):
            for conflict in range(0, reported - agree + 1):
                label = Agreement(reported=reported, agree=agree,
                                  conflict=conflict).label()
                assert not singular_plural.search(label), label
                assert not label.startswith("0 "), label
