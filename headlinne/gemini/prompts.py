"""All prompts in one place.

Design choice: the model owns the *prose*, the code owns the *structure and
length*. So prompts ask for small, well-described JSON (headlines, reasons,
captions) and the generators assemble the final posts and enforce limits. This
keeps copy natural and varied while guaranteeing character limits and format.

The STYLE_GUIDE is shared as the system instruction everywhere so the human,
trustworthy voice is consistent across platforms.
"""

from __future__ import annotations

import json

from ..config import BRAND, WEBSITE
from ..models import Story

# --------------------------------------------------------------------------- #
# Shared voice
# --------------------------------------------------------------------------- #
STYLE_GUIDE = f"""
You write social media copy for {BRAND}, an AI-powered personalised news app
({WEBSITE}). You are an experienced human news editor with a sharp eye for what
makes people stop scrolling. Your writing must:

VOICE
- Sound like a real, smart person wrote it. Never robotic, never obviously AI.
- Use simple, conversational English. Short, punchy, readable sentences.
- Avoid jargon and fancy vocabulary. Write for a broad, curious audience.
- NEVER use em dashes. NEVER use semicolons.
- Be friendly, modern, informative and trustworthy.

HOOKS AND ENGAGEMENT (this is how we earn attention honestly)
- Lead with the single most interesting, concrete fact. Specifics beat vague
  teasers. "A phone that runs AI without the internet" beats "You won't believe
  this phone."
- Create curiosity through real substance, never through withholding or hype.
- Always answer "why should someone care?" in plain terms.
- No clickbait, no exaggeration, no fake urgency, no invented drama, no
  exclamation spam.

ACCURACY (non-negotiable, it is the whole brand)
- Never invent facts, numbers, names, quotes, dates or statistics. Use ONLY what
  is in the supplied story material. If a detail is not given, stay general
  rather than guessing.
- Do not overstate certainty. If sources say something "may" happen, do not say
  it "will".
- Rewrite everything in your own original words. Do not copy headlines verbatim.
- When in doubt, be precise and modest. Accuracy matters more than flair.

Return ONLY the JSON described in the user message. No extra text, no markdown.
""".strip()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def stories_block(stories: list[Story]) -> str:
    """Compact, model-friendly rendering of the source material."""
    lines = []
    for i, s in enumerate(stories, 1):
        srcs = s.source
        if s.corroborating_sources:
            srcs += " + " + ", ".join(s.corroborating_sources[:4])
        verified = (f"  Verified across {s.source_count} independent sources"
                    if s.source_count >= 2 else "")
        summary = (s.summary or "").strip()
        if len(summary) > 320:
            summary = summary[:320].rsplit(" ", 1)[0] + "..."
        lines.append(
            f"STORY {i}\n"
            f"  Headline: {s.title}\n"
            f"  Detail: {summary or '(no extra detail provided)'}\n"
            f"  Reported by: {srcs}" + (f"\n{verified}" if verified else "")
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# X / Twitter
# --------------------------------------------------------------------------- #
def twitter_news_prompt(category_label: str, stories: list[Story]) -> str:
    return f"""
Write a short X (Twitter) post rounding up today's biggest {category_label}
news, using the stories below.

{stories_block(stories)}

Rules:
- One short lead line, then one line per story.
- Each story line packs the "what" and a hint of "why it matters" into a single
  natural sentence. Keep each line tight (aim for under 70 characters).
- Keep it human and a little bit lively, but never hyped or clickbaity.
- Suggest 1 to 3 short, relevant hashtag words (no # symbol, no spaces).

Return JSON exactly like this:
{{
  "lead": "short lead line, vary the wording day to day, under 42 characters",
  "items": [
    {{"text": "story one in one tight sentence"}},
    {{"text": "story two in one tight sentence"}},
    {{"text": "story three in one tight sentence"}}
  ],
  "hashtags": ["Word", "Word"]
}}
Use up to 3 items. Do not include the website or hashtags inside lead or items.
""".strip()


def twitter_promo_prompt(feature_focus: str) -> str:
    return f"""
Write one short, friendly X (Twitter) post for {BRAND} ({WEBSITE}) that gently
showcases this feature: "{feature_focus}".

Make it educational and curiosity-driven, like a helpful tip from a real editor.
It must NOT read like an advertisement. No hype, no clickbait, no exclamation
spam. Help the reader understand why the feature is genuinely useful for keeping
up with the news.

Keep the post body under 220 characters. Do not put the website or hashtags in
the body. Suggest 1 to 3 short relevant hashtag words (no # symbol).

Return JSON exactly like this:
{{
  "post": "the post body text",
  "hashtags": ["Word", "Word"]
}}
""".strip()


# --------------------------------------------------------------------------- #
# LinkedIn
# --------------------------------------------------------------------------- #
def linkedin_product_prompt(topic: str) -> str:
    return f"""
Write a LinkedIn post for {BRAND} ({WEBSITE}) on this theme: "{topic}".

Goal: build credibility around {BRAND}, AI and personalised news. Sound
professional but approachable, like a thoughtful founder sharing a real idea.
Avoid buzzwords. Avoid hype. Encourage discussion naturally. Keep paragraphs
short and easy to read. Do not use hashtags.

The post should:
- Open with a strong but honest first line (no clickbait).
- Develop the idea in a few short paragraphs with a concrete point of view.
- End with a subtle line that invites the reader to explore {WEBSITE}.

Keep the whole thing comfortably under 2500 characters.

Return JSON exactly like this:
{{
  "title": "the opening line",
  "body": "the main body, a few short paragraphs separated by blank lines",
  "cta": "one subtle closing line inviting readers to explore {WEBSITE}"
}}
""".strip()


def linkedin_roundup_prompt(stories: list[Story]) -> str:
    return f"""
Write a LinkedIn post titled "This Week in Finance & Tech" for {BRAND}
({WEBSITE}). Professionally summarise the week's biggest developments using the
stories below. Group related items, keep it skimmable with short paragraphs, and
stay factual. Avoid buzzwords and hype. Do not use hashtags.

{stories_block(stories)}

End with a subtle line inviting readers to keep up with the full picture on
{WEBSITE}. Keep the whole thing comfortably under 2500 characters.

Return JSON exactly like this:
{{
  "title": "This Week in Finance & Tech",
  "body": "the main body, short paragraphs separated by blank lines",
  "cta": "one subtle closing line inviting readers to explore {WEBSITE}"
}}
""".strip()


# --------------------------------------------------------------------------- #
# Instagram
# --------------------------------------------------------------------------- #
def instagram_prompt(category_label: str, stories: list[Story], num_stories: int) -> str:
    return f"""
Create the text for an Instagram carousel covering today's top {num_stories}
{category_label} stories, using the material below. There is one slide per story,
plus a cover.

{stories_block(stories[:num_stories])}

COVER (the first thing people see, it decides whether they swipe):
- "cover_title": a short, magnetic title for the whole set (aim for 4 to 7 words,
  under 46 characters). Spark genuine curiosity with a concrete angle drawn from
  the stories. No clickbait, no hype, no "you won't believe". Original wording,
  not a copy of any source headline.
- "cover_hook": one short sentence (under 90 characters) teasing the value of
  swiping through, in plain language.

For EACH story slide:
- "headline": a short, punchy, human headline (under 58 characters). Original
  wording, not a copy of the source headline.
- "explanation": 2 short sentences. The first says what happened, the second says
  why it matters to an ordinary reader. Conversational and clear. No jargon, no
  hype, no invented facts, no numbers that are not in the material.

FOR THE POST:
- "caption": 2 to 4 engaging sentences that summarise the set and make people
  want to read. End with ONE natural question that invites a comment (for
  example, which story surprised them). Do not stuff hashtags into the caption.
- "hashtags": 8 to 12 relevant hashtag words (no # symbol, no spaces). Mix a few
  broad-reach tags with a few specific, niche ones for the topic.

Return JSON exactly like this:
{{
  "cover_title": "...",
  "cover_hook": "...",
  "slides": [
    {{"headline": "...", "explanation": "..."}}
  ],
  "caption": "...",
  "hashtags": ["Word", "Word"]
}}
Provide exactly {num_stories} slides, in the same order as the stories.
""".strip()
