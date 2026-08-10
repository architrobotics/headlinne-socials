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

Also give a "headline": a punchy 4 to 9 word version of the idea for a graphic
card (under 60 characters, no trailing punctuation).

Return JSON exactly like this:
{{
  "post": "the post body text",
  "headline": "short card headline",
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
# --------------------------------------------------------------------------- #
# Reddit (helpful-first community replies, drafted for human review)
# --------------------------------------------------------------------------- #
REDDIT_GUIDE = f"""
You are a thoughtful, genuinely helpful Reddit user replying in a discussion.
You also happen to work on {BRAND} ({WEBSITE}), a personalised AI news app, but
you are a community member first and a founder a distant second.

Rules of the road:
- Be actually useful. Answer the person's real question or add a real insight.
  If you have nothing helpful to add, say so honestly (the caller may skip it).
- Sound like a normal person on Reddit. Casual, warm, specific. No marketing
  voice, no buzzwords, no hype, no emoji spam, no "Great question!".
- NEVER use em dashes or semicolons.
- Do not exaggerate or invent facts. It is fine to be uncertain.
- Self-promotion: only if the caller explicitly permits it AND a mention would
  genuinely help this specific person. If you mention {BRAND}, you MUST disclose
  that you work on it, keep it to one soft sentence, and never make it the point
  of the reply. If in doubt, leave it out and just be helpful.
- Never be the first or only thing you say. The help comes first, always.

Return ONLY the JSON described in the user message. No extra text.
""".strip()


def reddit_reply_prompt(title: str, body: str, subreddit: str,
                        allow_promo_mention: bool) -> str:
    body = (body or "").strip()
    if len(body) > 800:
        body = body[:800].rsplit(" ", 1)[0] + "..."
    promo_line = (
        "You MAY include one soft, disclosed mention of Headlinne, but ONLY if it "
        "genuinely helps this person. If it does not clearly help, do not mention it."
        if allow_promo_mention else
        "Do NOT mention Headlinne at all. Write a purely helpful reply."
    )
    return f"""
Draft a helpful Reddit reply for this thread in r/{subreddit}.

TITLE: {title}
BODY: {body or "(link post, no body text)"}

{promo_line}

Write a reply that would be genuinely valuable to the person and the thread.
Keep it to 2 to 5 sentences. Be human and specific, not generic.

Return JSON exactly like this:
{{
  "reply": "the full reply text as you would post it",
  "mentions_headlinne": true or false,
  "disclosure": "the disclosure sentence you used, or empty string if none",
  "rationale": "one short line on why this reply helps (for the human reviewer)"
}}
""".strip()


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


# --------------------------------------------------------------------------- #
# Reels
# --------------------------------------------------------------------------- #
# Shared rules for both reel kinds. Reels are edited in beats and watched muted,
# so every constraint here exists to protect either the cut or the legibility of
# burned-in text at phone size.
REEL_RULES = """
HOW A REEL IS BUILT
- It is a sequence of short beats. Each beat is one cut with one idea on screen.
- "caption" is the big on-screen line. It MUST be under 46 characters. Write it
  like a headline on a placard, not like a sentence in an article. No trailing
  full stop.
- "detail" is the smaller supporting line under it, under 92 characters. It is
  optional and can be an empty string, but it is where the substance goes.
- Never split one sentence across two beats. Each beat stands alone.
- Language stays spoken and plain. Read every line out loud in your head first.
  If it does not sound like a person talking, rewrite it.

THE NARRATION (this is read aloud by a voice, so it is the most important text)
- "narration" is what a presenter SAYS over this beat. Under 90 characters.
- It is NOT the caption repeated. The caption is a placard the viewer glances
  at, the narration is a person talking to them. Write the sentence you would
  actually say.
- Use contractions and normal spoken rhythm. Say "it's" and "that's". Full
  sentences with ordinary punctuation, because the punctuation controls how the
  voice paces the line.
- Each beat's narration should flow on from the previous one, so the whole reel
  reads as one continuous piece of speech rather than a list of captions.
- Never read out a symbol or an abbreviation the voice cannot say naturally.
  Write "per cent" not "%", "and" not "&", "twenty twenty six" not "2026" only
  where the year would otherwise be misread.
- Do NOT narrate stage directions, the brand name, or a call to action. The
  sign-off is added separately.

THE GRAPHIC BEAT
One beat may carry a graphic instead of a photo. Only use the device you are
told to use. The available devices and their data shapes:
- "flow": three stages of a cause and effect chain.
  data: {"steps": ["first thing", "then this", "so this"]}
  Each step is under 26 characters. This device uses NO numbers.
- "split": one direct contrast, two sides.
  data: {"left_title": "...", "left_text": "...", "right_title": "...", "right_text": "..."}
  Titles under 18 characters, texts under 54 characters. NO numbers.
- "timeline": what happens over time, in three or four labelled stops.
  data: {"stops": ["Day one", "Week six", "Month six"], "note": "short line"}
  Each stop under 18 characters, note under 60. NO numbers except plain
  time labels.
- "bars": two or three quantities compared by height.
  data: {"bars": [{"label": "...", "weight": 0.35, "value_label": "optional"}]}
  "label" is under 20 characters. "weight" is a number from 0.1 to 1.0 giving
  the bar's relative height, which is a claim about direction and rough size
  only. "value_label" is a printed figure and is a factual claim, so include it
  ONLY when that exact figure appears in the supplied material. Otherwise leave
  it out entirely and let the heights carry the point.
- "counter": one striking figure that counts up.
  data: {"value_label": "47%", "caption": "under 30 characters"}
  ONLY use this when that exact figure appears in the supplied material.

NEVER invent a number, a date, a percentage or a name for a graphic. If the
material does not contain a figure, choose a device that does not print one.
""".strip()


def reel_news_prompt(story_block: str, hook_brief: str, num_beats: int,
                     category_label: str) -> str:
    return f"""
Script a short vertical explainer video (an Instagram Reel) that walks a viewer
through ONE {category_label} news story, using only the material below.

{story_block}

{REEL_RULES}

THE OPENING (this decides whether anyone sees the rest)
{hook_brief}
- "hook" is the very first line on screen. Under 42 characters. It must be
  concrete and specific to THIS story, never a generic tease.
- "hook_detail" is one short line under it, under 76 characters, that makes a
  viewer decide to stay.

THE SHAPE
Write exactly {num_beats} beats after the hook, in this order:
1. WHAT HAPPENED. The event itself, stripped of jargon.
2. THE MECHANISM. How it actually works, or how it came about. This is the beat
   that earns the watch time, so make it the most interesting one.
3. A GRAPHIC BEAT. Same idea carried by the device named in "graphic" below.
4. WHY IT MATTERS. The concrete effect on an ordinary person's money, work,
   prices or choices. Be specific about who is affected.
{"5. WHAT TO WATCH. The one thing that tells us where this goes next." if num_beats >= 5 else ""}

Set "graphic" on the graphic beat to the device that genuinely fits this story
and follow its data shape exactly. Every other beat has "graphic": "" and
"data": {{}}.

THE POST
- "caption_opener": the first line of the Instagram caption, under 120
  characters. Write it as a clear, searchable sentence containing the real words
  someone would type to look this up (the company, the country, the topic). No
  hashtags, no emoji.
- "caption_body": two or three short sentences of genuine substance. Someone who
  reads only the caption should still learn something true.
- "question": one honest question that invites a real opinion in the comments.
- "hashtags": 10 to 14 relevant tag words (no # symbol, no spaces). Mix a few
  broad ones with several specific ones.

Return JSON exactly like this:
{{
  "hook": "...",
  "hook_detail": "...",
  "hook_narration": "the spoken version of the opening, under 90 characters",
  "beats": [
    {{"caption": "...", "detail": "...", "narration": "...", "graphic": "", "data": {{}}}}
  ],
  "payoff": "one short closing line, under 46 characters",
  "payoff_narration": "the spoken version of the closing line, under 90 characters",
  "caption_opener": "...",
  "caption_body": "...",
  "question": "...",
  "hashtags": ["Word", "Word"]
}}
Provide exactly {num_beats} beats.
""".strip()


def reel_education_prompt(topic_title: str, topic_angle: str, graphic: str,
                          hook_brief: str, num_beats: int) -> str:
    return f"""
Script a short vertical explainer video (an Instagram Reel) that TEACHES one
idea. This is not news reporting. Nothing here is tied to today's headlines.

THE IDEA: {topic_title}
THE ANGLE: {topic_angle}

{REEL_RULES}

THE OPENING (this decides whether anyone sees the rest)
{hook_brief}
- "hook" is the very first line on screen. Under 42 characters.
- "hook_detail" is one short line under it, under 76 characters.

THE SHAPE
Write exactly {num_beats} beats after the hook, in this order:
1. THE SETUP. The situation in plain words, no jargon at all.
2. THE CONCRETE EXAMPLE. This is the whole point of the video. Invent a small,
   ordinary, clearly hypothetical example with real texture: a person, a shop, a
   loan, a shipment. Something a viewer can picture in one second. Make it
   specific and slightly surprising, not a textbook illustration. Because it is
   openly a worked example rather than a report, you may use round illustrative
   figures here, but keep them obviously simple and never present them as
   real-world statistics.
3. A GRAPHIC BEAT using the "{graphic}" device. Follow that device's data shape
   exactly.
4. THE PAYOFF. The general rule the example just demonstrated, stated so plainly
   that a viewer could repeat it to someone else.
{"5. WHERE YOU SEE IT. One place this shows up in real life, so the idea sticks." if num_beats >= 5 else ""}

Set "graphic" to "{graphic}" on beat 3 only. Every other beat has
"graphic": "" and "data": {{}}.

Do NOT state any real-world statistic, company figure, date or named study. You
are teaching a mechanism, so everything must follow from the explanation itself.

THE POST
- "caption_opener": the first line of the Instagram caption, under 120
  characters. Write it as a clear, searchable sentence using the words someone
  would actually type to learn this. No hashtags, no emoji.
- "caption_body": two or three short sentences that teach the idea in text form,
  so the caption is useful on its own.
- "question": one honest question that invites a real answer in the comments.
- "hashtags": 10 to 14 relevant tag words (no # symbol, no spaces).

Return JSON exactly like this:
{{
  "hook": "...",
  "hook_detail": "...",
  "hook_narration": "the spoken version of the opening, under 90 characters",
  "beats": [
    {{"caption": "...", "detail": "...", "narration": "...", "graphic": "", "data": {{}}}}
  ],
  "payoff": "one short closing line, under 46 characters",
  "payoff_narration": "the spoken version of the closing line, under 90 characters",
  "caption_opener": "...",
  "caption_body": "...",
  "question": "...",
  "hashtags": ["Word", "Word"]
}}
Provide exactly {num_beats} beats.
""".strip()


# --------------------------------------------------------------------------- #
# Story card (one article, start to finish, on a single image)
# --------------------------------------------------------------------------- #
def story_card_prompt(story_block: str, labels: list[str],
                      max_chars: int, category_label: str) -> str:
    steps = "\n".join(f'  {i+1}. {label}' for i, label in enumerate(labels))
    shape = ",\n".join(f'    {{"label": "{label}", "text": "..."}}' for label in labels)
    return f"""
Write a single explainer card that walks a reader through ONE {category_label}
news story from beginning to end, using only the material below. The reader sees
everything at once on one image, so this has to be complete on its own. Someone
who reads only this card should understand the whole story and be able to
explain it to a friend.

{story_block}

STRUCTURE. Write exactly these {len(labels)} steps, in this order:
{steps}

Rules for every step:
- Under {max_chars} characters. This is a hard limit, the text is drawn into a
  fixed space and longer text will not fit.
- One or two short sentences. Plain spoken English. No jargon, no filler, no
  throat-clearing like "it is important to note".
- Each step must add something the previous step did not say. Never restate.
- Only use facts from the material above. If the material does not support a
  step, keep that step general and honest rather than inventing detail. For
  "what to watch", it is fine to name the decision or date the story itself
  points to, and nothing beyond that.

Also write:
- "headline": the story in one line, under 62 characters, original wording, not
  a copy of any source headline. Concrete, no hype.
- "standfirst": one line of context under the headline, under 96 characters. It
  should answer "why is this on my screen" in plain terms.
- "caption_opener": the first line of the Instagram caption, under 120
  characters, written as a clear searchable sentence using the words someone
  would type to look this story up. No hashtags, no emoji.
- "caption_body": two or three short sentences adding real substance beyond the
  card.
- "question": one honest question that invites a real opinion in the comments.
- "hashtags": 10 to 14 relevant tag words (no # symbol, no spaces).

Return JSON exactly like this:
{{
  "headline": "...",
  "standfirst": "...",
  "steps": [
{shape}
  ],
  "caption_opener": "...",
  "caption_body": "...",
  "question": "...",
  "hashtags": ["Word", "Word"]
}}
""".strip()
