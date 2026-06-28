"""Pre-publish quality gate.

Validates the generated content against the brief's hard rules (character limits,
no forbidden punctuation) and a few soft heuristics (clickbait phrasing, ALL-CAPS
shouting). Soft issues are warnings; hard issues fail the item so it is not
published with a broken constraint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import (INSTAGRAM_CAPTION_LIMIT, LINKEDIN_SOFT_LIMIT, TWITTER_LIMIT)
from ..models import InstagramCarousel, LinkedInPost, TwitterPost
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
