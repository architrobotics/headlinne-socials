"""The hook rotation and caption builder.

These guard the two things that decide whether a post is seen at all: that
openers vary in *shape* rather than only in wording, and that a caption puts its
keywords where Instagram actually reads them.
"""

from __future__ import annotations

from datetime import date

from headlinne.config import (INSTAGRAM_CAPTION_HASHTAGS,
                              INSTAGRAM_CAPTION_HOOK_CHARS, WEBSITE)
from headlinne.generate.hooks import (HOOKS, build_caption, hook_brief,
                                      pick_hook, split_hashtags)


def test_hook_choice_is_deterministic_for_a_day_and_slot():
    day = date(2026, 8, 10)
    assert pick_hook(day, "reel_1").name == pick_hook(day, "reel_1").name


def test_morning_and_evening_reels_never_open_the_same_way():
    # Both reels go out on the same day, so an identical opening shape would be
    # visible to anyone who saw both.
    for offset in range(21):
        day = date(2026, 8, 10).replace(day=1 + offset % 28)
        assert pick_hook(day, "reel_1").name != pick_hook(day, "reel_2").name


def test_hook_rotation_covers_every_archetype_within_a_cycle():
    day = date(2026, 8, 10)
    seen = {pick_hook(date.fromordinal(day.toordinal() + i), "reel_1").name
            for i in range(len(HOOKS))}
    assert seen == {h.name for h in HOOKS}


def test_hook_brief_names_the_archetype_and_gives_a_shape():
    brief = hook_brief(date(2026, 8, 10), "reel_1")
    assert pick_hook(date(2026, 8, 10), "reel_1").name in brief
    assert "Shape" in brief


def test_split_hashtags_keeps_a_few_and_moves_the_rest():
    tags = [f"Tag{i}" for i in range(20)]
    caption_tags, comment_tags = split_hashtags(tags)
    assert len(caption_tags.split()) == INSTAGRAM_CAPTION_HASHTAGS
    assert comment_tags.split()
    # Nothing appears in both places.
    assert not set(caption_tags.split()) & set(comment_tags.split())
    assert all(t.startswith("#") for t in caption_tags.split())


def test_split_hashtags_dedupes_case_insensitively():
    caption_tags, comment_tags = split_hashtags(["AI", "ai", "#AI", "Tech"])
    all_tags = caption_tags.split() + comment_tags.split()
    assert len(all_tags) == len({t.lower() for t in all_tags})


def test_caption_opener_fits_the_visible_window():
    long_opener = ("Regulators opened a formal case against three cloud "
                   "providers this week. That is the first step toward forcing "
                   "them to separate their businesses, which would reshape the "
                   "market.")
    caption, _ = build_caption(opener=long_opener, body="Body.", question="What next",
                               hashtags=["Tech"])
    first_line = caption.split("\n")[0]
    # Instagram truncates around 125 characters, so the whole hook must land
    # inside that window or nobody reads it without tapping "more".
    assert len(first_line) <= INSTAGRAM_CAPTION_HOOK_CHARS


def test_an_opener_that_already_fits_is_left_whole():
    opener = "Rates held steady again today, against every forecast."
    caption, _ = build_caption(opener=opener, hashtags=[])
    assert caption.split("\n")[0] == opener


def test_an_over_long_opener_cuts_at_a_sentence_end():
    opener = ("The central bank held rates steady for a fourth straight "
              "meeting today. The committee split three ways and the minutes "
              "will show exactly how close this one was to a cut.")
    assert len(opener) > INSTAGRAM_CAPTION_HOOK_CHARS
    first_line = build_caption(opener=opener, hashtags=[])[0].split("\n")[0]
    # Cut at a sentence boundary inside the window, never mid-thought.
    assert first_line.endswith(".")
    assert first_line == ("The central bank held rates steady for a fourth "
                          "straight meeting today.")


def test_an_over_long_opener_keeps_its_tail_in_the_body():
    tail = "That is the first step toward forcing them to separate."
    opener = ("The central bank held rates steady for a fourth straight "
              f"meeting today. {tail}")
    caption, _ = build_caption(opener=opener, body="Existing body.", hashtags=[])
    # The fold decides where the caption breaks, not how much of it survives.
    assert tail in caption
    assert "Existing body." in caption


def test_caption_has_a_question_and_the_website():
    caption, _ = build_caption(opener="A thing happened.", body="Some detail.",
                               question="Which part surprised you",
                               hashtags=["News"])
    assert "Which part surprised you?" in caption      # normalised to a question
    assert WEBSITE.lower() in caption.lower()


def test_caption_ends_with_its_hashtags_and_the_rest_go_to_the_comment():
    tags = [f"Tag{i}" for i in range(12)]
    caption, first_comment = build_caption(opener="Opener.", hashtags=tags)
    assert caption.strip().split("\n")[-1].startswith("#")
    assert first_comment.startswith("#")
    # The visible caption is not a wall of tags.
    assert caption.count("#") == INSTAGRAM_CAPTION_HASHTAGS
