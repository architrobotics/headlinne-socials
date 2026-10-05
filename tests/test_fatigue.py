"""Topic fatigue: the account should not tell the same kind of story all week.

Of the 25 reels from 2026-09-09 to 2026-10-05, fourteen were space and three
in a row named James Webb. These tests pin the behaviour that fixes that, and
the ways it must not overreach.
"""

import json
from datetime import date

from headlinne import pipeline, storage
from headlinne.models import NewsDigest, Story
from headlinne.news import fatigue as F

WEBB = ("Webb reveals dynamic panorama of star formation",
        "The James Webb Space Telescope captured a stellar nursery.")


def test_a_fresh_subject_pays_nothing():
    recent = [(1, *WEBB), (2, "Webb detects ammonia on a giant planet", "")]
    assert F.penalty("Scientists discover a major brain shift between ages 50 and 75",
                     "", recent) == 0.0


def test_a_repeat_subject_is_docked_and_more_repeats_cost_more():
    one = F.penalty("Astronomers discover a backward planet", "", [(1, *WEBB)])
    three = F.penalty("Astronomers discover a backward planet", "",
                      [(1, *WEBB), (2, *WEBB), (3, *WEBB)])
    assert 0 < one < three <= F.PENALTY_CAP


def test_the_penalty_fades_and_then_stops():
    yesterday = F.penalty("Hubble finds a new moon", "", [(1, *WEBB)])
    last_week = F.penalty("Hubble finds a new moon", "", [(F.WINDOW_DAYS, *WEBB)])
    gone = F.penalty("Hubble finds a new moon", "", [(F.WINDOW_DAYS + 1, *WEBB)])
    assert yesterday > last_week > gone == 0.0


def test_a_rocket_launch_is_not_tired_by_yesterday_s_telescope():
    # Split families: on 2026-09-07 one "space" family docked a European
    # rocket launch for a radio-telescope result and cost the day its reel.
    assert F.penalty("German startup sends first commercial rocket into space",
                     "", [(1, "FAST finds two mysterious hydrogen clouds with no "
                              "visible star", "")]) == 0.0


def test_a_passing_word_in_a_summary_does_not_set_the_subject():
    # A plankton story mentions "the planet" once; that is not astronomy.
    assert "astronomy" not in F.families(
        "Marine biologists discover new plankton off Oregon coast",
        "Nearly every breath you take was made by plankton somewhere on the planet.")
    # Two distinct terms in the opening does set it.
    assert "astronomy" in F.families(
        "A strange new object", "Astronomers using a telescope found it.")


def test_a_name_repeat_is_caught_without_a_family():
    recent = [(1, "Pope Leo celebrates mass in Paris", "")]
    assert F.penalty("Huge crowds cheer Pope Leo along the Champs-Elysees", "", recent) > 0


def _story(title, category="Science", score=10.0, url=None):
    return Story(title=title, summary="", url=url or f"https://x.test/{abs(hash(title))}",
                 category=category, source="Test", tier=1.0,
                 published_iso="2026-10-05T00:00:00+00:00", score=score)


def test_recent_picks_resolves_urls_through_that_day_s_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CONTENT_DIR", tmp_path, raising=False)
    monkeypatch.setattr(storage, "content_dir_for",
                        lambda d: tmp_path / d.isoformat())
    yesterday = date(2026, 10, 4)
    picked = _story("Webb detects ammonia", url="https://x.test/webb")
    digest = NewsDigest(day=yesterday.isoformat(),
                        by_category={"Science": [picked]},
                        category_weights={"Science": 1.0},
                        dominant_category="Science")
    folder = tmp_path / yesterday.isoformat()
    folder.mkdir(parents=True)
    (folder / "news_digest.json").write_text(json.dumps(digest.to_dict()),
                                             encoding="utf-8")
    (folder / "reels.json").write_text(json.dumps(
        [{"title": "a rewritten reel title", "story_url": "https://x.test/webb",
          "story": None}]), encoding="utf-8")
    (folder / "story_card.json").write_text("{not json", encoding="utf-8")

    picks = storage.recent_picks(date(2026, 10, 5))
    assert picks == [(1, "Webb detects ammonia", "")]


def test_the_pipeline_hook_reorders_and_never_raises(monkeypatch):
    webb = _story("Webb spots a far galaxy", score=12.0)
    brain = _story("Scientists find a brain shift at 50", score=11.5)
    digest = NewsDigest(day="2026-10-05", by_category={"Science": [webb, brain]},
                        category_weights={"Science": 1.0}, dominant_category="Science")
    monkeypatch.setattr(storage, "recent_picks",
                        lambda day, n: [(1, *WEBB), (2, *WEBB)])
    pipeline._apply_fatigue(digest, date(2026, 10, 5))
    assert digest.by_category["Science"][0] is brain

    def boom(day, n):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(storage, "recent_picks", boom)
    before = [s.score for s in digest.by_category["Science"]]
    pipeline._apply_fatigue(digest, date(2026, 10, 5))
    assert [s.score for s in digest.by_category["Science"]] == before
