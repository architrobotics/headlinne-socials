"""Legibility: no beat may outrun the text it is carrying.

The frame carries two kinds of text and they are consumed at different speeds.
The primary line is read word by word; the detail line under it is scanned. An
earlier cut measured both against one rate, came out at 308 wpm, and read fine
on the page while being unwatchable in motion. So there are two budgets, and a
beat has to satisfy both.

The stillness rule is expressed the same way. "Flag any beat over 2.5 seconds"
would fire on every beat of a reel where Pip's cycle and the progress bar move
every frame - nothing is ever actually static. What matters is whether a beat is
held longer than its own text justifies.
"""

from __future__ import annotations

from headlinne.render.motion import (READING_WPM, SCANNING_WPM, minimum_hold,
                                     wpm)


def test_a_line_gets_at_least_its_reading_time():
    # Twelve words at 230 wpm is a little over three seconds.
    line = "On Tuesday a four tonne rocket stage struck the far side today"
    assert minimum_hold(line) >= len(line.split()) / READING_WPM * 60 - 0.01


def test_the_detail_line_is_scanned_rather_than_read():
    # Adding a detail lengthens the beat, but by far less than reading it would,
    # because nobody reads it - they take its shape.
    caption = "Two orbiters turned to photograph the site"
    detail = "NASA's Lunar Reconnaissance Orbiter and South Korea's Danuri"
    read_both = len((caption + " " + detail).split()) / READING_WPM * 60
    assert minimum_hold(caption, detail) < read_both


def test_both_budgets_are_honoured_not_just_the_first():
    # A short headline with a long support line is held by the scanning budget.
    caption = "It missed"
    detail = " ".join(["word"] * 40)
    assert minimum_hold(caption, detail) >= 40 / SCANNING_WPM * 60 - 0.01


def test_a_beat_held_to_its_floor_never_exceeds_the_ceilings():
    caption = "A four tonne rocket stage struck the Moon on Tuesday"
    detail = "A Falcon 9 second stage, adrift since 2015"
    hold = minimum_hold(caption, detail)
    primary_words = len(caption.split())
    total_words = primary_words + len(detail.split())
    assert wpm(primary_words, hold) <= READING_WPM + 0.5
    assert wpm(total_words, hold) <= SCANNING_WPM + 0.5


def test_an_empty_line_still_gets_a_moment():
    assert minimum_hold("") > 0
