"""Pre-publish quality gate.

Validates the generated content against the brief's hard rules (character limits,
no forbidden punctuation) and a few soft heuristics (clickbait phrasing, ALL-CAPS
shouting). Soft issues are warnings; hard issues fail the item so it is not
published with a broken constraint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import (INSTAGRAM_CAPTION_LIMIT, LINKEDIN_SOFT_LIMIT,
                      REEL_MAX_SECONDS, TWITTER_LIMIT)
from ..models import InstagramCarousel, LinkedInPost, Reel, StoryCard, TwitterPost
from .sanitize import contains_forbidden

_CLICKBAIT = (
    "you won't believe", "you wont believe", "shocking", "mind-blowing",
    "this one trick", "what happens next", "will blow your mind", "jaw-dropping",
    "doctors hate", "number will shock", "gone wrong", "must see", "insane",
)


@dataclass
class QualityReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)      # block publishing
    warnings: list[str] = field(default_factory=list)    # logged only

    def error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _common_text_checks(text: str, label: str, report: QualityReport) -> None:
    for issue in contains_forbidden(text):
        report.error(f"{label}: {issue}")
    low = text.lower()
    for phrase in _CLICKBAIT:
        if phrase in low:
            report.warn(f"{label}: possible clickbait phrasing '{phrase}'")
    # Shouty all-caps words (allow short acronyms and the brand/website).
    for word in re.findall(r"\b[A-Z]{4,}\b", text):
        if word.upper() in {"HEADLINNE", "HEADLINNE.COM"}:
            continue
        report.warn(f"{label}: all-caps word '{word}'")


def check_twitter(post: TwitterPost) -> QualityReport:
    r = QualityReport()
    if len(post.post) > TWITTER_LIMIT:
        r.error(f"twitter: {len(post.post)} chars exceeds {TWITTER_LIMIT}")
    if not post.post.strip():
        r.error("twitter: empty post")
    _common_text_checks(post.post, "twitter", r)
    return r


def check_linkedin(post: LinkedInPost) -> QualityReport:
    r = QualityReport()
    full = f"{post.title}\n{post.body}\n{post.cta}"
    if len(full) > LINKEDIN_SOFT_LIMIT:
        r.error(f"linkedin: {len(full)} chars exceeds soft limit {LINKEDIN_SOFT_LIMIT}")
    if not post.body.strip():
        r.error("linkedin: empty body")
    _common_text_checks(full, "linkedin", r)
    return r


def check_instagram(carousel: InstagramCarousel) -> QualityReport:
    r = QualityReport()
    if len(carousel.caption) > INSTAGRAM_CAPTION_LIMIT:
        r.error(f"instagram: caption {len(carousel.caption)} exceeds {INSTAGRAM_CAPTION_LIMIT}")
    if not (2 <= len(carousel.slides) <= 11):  # cover + up to 5 stories + cta
        r.error(f"instagram: unexpected slide count {len(carousel.slides)}")
    story_slides = [s for s in carousel.slides if s.role == "story"]
    if not story_slides:
        r.error("instagram: no story slides")
    _common_text_checks(carousel.caption, "instagram caption", r)
    for i, s in enumerate(carousel.slides):
        _common_text_checks(f"{s.headline} {s.explanation}", f"instagram slide {i+1}", r)
    return r


def check_reel(reel: Reel, *, require_media: bool = True) -> QualityReport:
    """Validate a reel before it is scheduled.

    The errors here are the conditions that would publish something broken: no
    video file, no hook, or a runtime outside what Instagram will accept. The
    warnings are the craft problems that are worth seeing in the logs but are
    not worth withholding a post over.

    `require_media` is off for a `--no-render` run, where the absence of a video
    is the point rather than a fault.
    """
    r = QualityReport()
    if require_media and not reel.video_file:
        r.error(f"reel {reel.slot}: no rendered video")
    if not reel.hook.strip():
        r.error(f"reel {reel.slot}: empty hook")
    if len(reel.beats) < 3:
        r.error(f"reel {reel.slot}: only {len(reel.beats)} beats, too thin to publish")
    if len(reel.caption) > INSTAGRAM_CAPTION_LIMIT:
        r.error(f"reel {reel.slot}: caption {len(reel.caption)} exceeds "
                f"{INSTAGRAM_CAPTION_LIMIT}")

    # Meta's floor is 3 seconds, but the Reels tab (the surface that matters)
    # only takes clips of 5 seconds or more.
    if reel.duration_seconds and reel.duration_seconds < 5:
        r.error(f"reel {reel.slot}: {reel.duration_seconds:.1f}s is under the "
                f"5 second minimum for the Reels tab")
    if reel.duration_seconds > REEL_MAX_SECONDS + 1:
        r.warn(f"reel {reel.slot}: {reel.duration_seconds:.1f}s is longer than "
               f"the {REEL_MAX_SECONDS}s target, completion rate will suffer")

    # A hook that runs long gets shrunk by the renderer until it stops being a
    # hook, which is a quiet way for a reel to fail.
    if len(reel.hook) > 52:
        r.warn(f"reel {reel.slot}: hook is {len(reel.hook)} chars, it will render small")

    # Silence is a supported fallback, not a target: the reel still works muted,
    # but it loses the audio-page discovery a narrated one gets, so it is worth
    # seeing in the logs when it happens.
    if require_media and not reel.has_voiceover:
        r.warn(f"reel {reel.slot}: no voiceover, the track is silent")

    _common_text_checks(reel.caption, f"reel {reel.slot} caption", r)
    for i, beat in enumerate(reel.beats):
        _common_text_checks(f"{beat.caption} {beat.detail}",
                            f"reel {reel.slot} beat {i+1}", r)
    return r


def check_story_card(card: StoryCard, *, require_media: bool = True) -> QualityReport:
    """Validate the daily story card.

    The card is one claim and the evidence for it, so an empty headline or a
    receipt with nothing behind it is not a weaker card - it is a post that
    argues nothing. Both are errors rather than warnings.
    """
    r = QualityReport()
    if not card.headline.strip():
        r.error("story card: empty headline")
    if not card.outlets:
        r.error("story card: no outlets behind the receipt")
    elif card.agree > len(card.outlets):
        r.error(f"story card: {card.agree} agreeing outlets of only "
                f"{len(card.outlets)} reported")
    if require_media and not card.image_file:
        r.error("story card: no rendered image")
    if len(card.caption) > INSTAGRAM_CAPTION_LIMIT:
        r.error(f"story card: caption {len(card.caption)} exceeds {INSTAGRAM_CAPTION_LIMIT}")

    _common_text_checks(f"{card.headline} {card.standfirst}", "story card", r)
    _common_text_checks(card.caption, "story card caption", r)
    return r
