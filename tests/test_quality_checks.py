"""The quality gate blocks anything that breaks a hard rule from being
published. These tests check it fails over-limit posts and forbidden
punctuation, and passes clean content."""

from __future__ import annotations

from headlinne.config import TWITTER_LIMIT
from headlinne.models import InstagramCarousel, LinkedInPost, Slide, TwitterPost
from headlinne.quality.checks import check_instagram, check_linkedin, check_twitter


def _good_tweet(text="Markets had a calm day. Read more on HEADLINNE.com"):
    return TwitterPost(category="Finance", post=text, hashtags=["Finance"],
                       scheduled_time="2026-06-28T13:00:00+05:30")


def test_clean_tweet_passes():
    assert check_twitter(_good_tweet()).ok


def test_overlong_tweet_fails():
    post = _good_tweet(text="x" * (TWITTER_LIMIT + 5))
    report = check_twitter(post)
    assert not report.ok
    assert any("exceeds" in e for e in report.errors)


def test_tweet_with_semicolon_fails():
    report = check_twitter(_good_tweet("Stocks rose; bonds fell. HEADLINNE.com"))
    assert not report.ok


def test_empty_tweet_fails():
    assert not check_twitter(_good_tweet("   ")).ok


def test_clean_linkedin_passes():
    post = LinkedInPost(
        title="Why personalised news matters",
        body="A short, clear, professional thought about building a calmer news app.",
        cta="Curious to hear how you stay informed. More at HEADLINNE.com",
        scheduled_time="2026-06-28T18:00:00+05:30",
    )
    assert check_linkedin(post).ok


def test_linkedin_with_em_dash_fails():
    post = LinkedInPost(
        title="A thought",
        body="Personalised news is the future \u2014 and we are building it.",
        cta="More at HEADLINNE.com",
        scheduled_time="2026-06-28T18:00:00+05:30",
    )
    assert not check_linkedin(post).ok


def _carousel(slides, caption="Today's biggest stories. Read more on HEADLINNE.com"):
    return InstagramCarousel(
        slot="instagram_1", category="Technology", num_slides=len(slides),
        title="Top 3 Things In Tech Today", slides=slides, caption=caption,
        hashtags=["Tech"], scheduled_time="2026-06-28T16:00:00+05:30",
    )


def test_clean_carousel_passes():
    slides = [
        Slide(role="cover", headline="Top 3 Things In Tech Today"),
        Slide(role="story", headline="A new chip", explanation="It is faster and cheaper."),
        Slide(role="story", headline="A new app", explanation="It helps people read news."),
        Slide(role="cta", headline="Stay ahead with HEADLINNE.com"),
    ]
    assert check_instagram(_carousel(slides)).ok


def test_carousel_with_no_story_slides_fails():
    slides = [
        Slide(role="cover", headline="Cover only"),
        Slide(role="cta", headline="Stay ahead with HEADLINNE.com"),
    ]
    report = check_instagram(_carousel(slides))
    assert not report.ok
    assert any("no story slides" in e for e in report.errors)


def test_carousel_caption_over_limit_fails():
    slides = [
        Slide(role="cover", headline="Cover"),
        Slide(role="story", headline="Story", explanation="Body."),
        Slide(role="cta", headline="CTA"),
    ]
    report = check_instagram(_carousel(slides, caption="x" * 2300))
    assert not report.ok
