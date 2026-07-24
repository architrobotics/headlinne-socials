"""The X generator keeps clean structured pieces (lead + items) for the branded
card alongside the flattened tweet text, and trims the promo statement sensibly."""

from __future__ import annotations

from headlinne.generate.twitter import _card_statement


def test_card_statement_takes_first_sentence():
    out = _card_statement("Ask the news anything. Then read the sources yourself.")
    assert out == "Ask the news anything"


def test_card_statement_trims_long_single_sentence_on_word_boundary():
    long = "This is a very long promotional sentence that runs well past the card limit for sure"
    out = _card_statement(long, max_chars=40)
    assert len(out) <= 40
    assert not out.endswith(" ")
    assert " " in out  # kept whole words


def test_card_statement_strips_trailing_punctuation():
    assert _card_statement("News, made personal!") == "News, made personal"
