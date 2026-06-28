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
({WEBSITE}). You are an experienced human news editor. Your writing must:

- Sound like a real person wrote it. Never robotic, never obviously AI.
- Use simple, conversational English. Short, readable sentences.
- Avoid technical jargon and fancy vocabulary. Write for a broad audience.
- NEVER use em dashes. NEVER use semicolons.
- Be friendly, modern, informative and trustworthy.
- Never use clickbait. Never exaggerate. Never overhype.
- Never invent facts, numbers, names, quotes or statistics. Use ONLY what is in
  the supplied story material. If a detail is not given, stay general rather
  than guessing.
- Rewrite everything in your own original words. Do not copy headlines verbatim.
- Stay factual and accurate. Accuracy matters more than flair.

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
        summary = (s.summary or "").strip()
        if len(summary) > 320:
            summary = summary[:320].rsplit(" ", 1)[0] + "..."
        lines.append(
            f"STORY {i}\n"
            f"  Headline: {s.title}\n"
            f"  Detail: {summary or '(no extra detail provided)'}\n"
            f"  Reported by: {srcs}"
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
Create the text for an Instagram carousel summarising today's top
{num_stories} {category_label} stories, using the material below. There is one
slide per story.

{stories_block(stories[:num_stories])}

For each story slide write:
- "headline": a short, punchy, human headline (under 60 characters). Original
  wording, not a copy of the source headline.
- "explanation": 1 to 2 short sentences covering what happened and why it
  matters. Conversational and clear. No jargon, no hype, no invented facts.

Also write:
- "caption": a brief, engaging overall summary for the post (2 to 4 sentences).
- "hashtags": 6 to 10 short relevant hashtag words (no # symbol, no spaces).

Return JSON exactly like this:
{{
  "slides": [
    {{"headline": "...", "explanation": "..."}}
  ],
  "caption": "...",
  "hashtags": ["Word", "Word"]
}}
Provide exactly {num_stories} slides, in the same order as the stories.
""".strip()
