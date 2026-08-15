"""Central configuration for the whole pipeline.

Everything that you might want to tune lives here so you do not have to hunt
through the code. Secrets are read from environment variables (see .env.example).
Non-secret behaviour (feeds, schedule, colours, dimensions) is plain Python so it
is easy to read and change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

# Load a local .env file if present (no-op in CI, where secrets are injected).
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- #
# Reading the environment
# --------------------------------------------------------------------------- #
# Every setting below goes through these three helpers, and the reason is a trap
# that is very easy to walk into.
#
# A workflow line like `REEL_VOICEOVER: ${{ vars.REEL_VOICEOVER }}` does NOT
# leave the variable unset when the repository variable has never been created.
# GitHub substitutes an **empty string**, so the runner gets `REEL_VOICEOVER=""`.
# `os.getenv("REEL_VOICEOVER", "true")` then returns `""`, not `"true"`, because
# as far as Python is concerned the variable is set. The default silently never
# applies, and a feature everyone expected to be on ships off.
#
# So: an empty or whitespace-only value means "not configured", and the default
# wins. Anyone who genuinely wants a feature off sets the variable to "false"
# rather than clearing it.
def _env_str(name: str, default: str) -> str:
    """A string setting, where an empty value means 'use the default'."""
    return os.getenv(name, "").strip() or default


def _env_flag(name: str, default: bool) -> bool:
    """A boolean setting. Anything other than a truthy word reads as False."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_number(name: str, default, cast):
    """A numeric setting, falling back on an empty or unparseable value."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
LOGO_PATH = ASSETS_DIR / "logo.png"
CONTENT_DIR = ROOT / "content"          # one folder per day of generated output
STATE_DIR = ROOT / "state"              # rolling history for de-duplication

TIMEZONE = ZoneInfo("Asia/Kolkata")     # IST. All scheduling is expressed in IST.


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
# Science earns its own category rather than being filed under Technology. The
# stories that travel furthest - a rocket hitting the Moon, whales returning to
# a coastline, what a brain does while you sleep - are universal in a way a
# product launch is not, and they had nowhere to live.
CATEGORIES = ("Technology", "Finance", "Geopolitics", "Science")

# Short labels used in copy and slide titles.
CATEGORY_LABELS = {
    "Technology": "Tech",
    "Finance": "Finance",
    "Geopolitics": "Geopolitics",
    "Science": "Science",
}

# Uppercase labels used on the small category pill in the carousel furniture.
CATEGORY_PILL = {
    "Technology": "TECHNOLOGY",
    "Finance": "FINANCE",
    "Geopolitics": "WORLD",
    "Science": "SCIENCE",
}

# --------------------------------------------------------------------------- #
# Brand + design system
# --------------------------------------------------------------------------- #
# The whole visual identity is anchored on the terracotta logo. Every carousel
# slide is built from these tokens so covers, story slides and the CTA read as
# one designed system rather than three loosely-related layouts.
BRAND_TERRACOTTA = "#C76A44"    # the logo colour, primary brand accent
BRAND_TERRACOTTA_HI = "#E08A5F"  # a lighter tint for glows / hov(text) states

# Paper, not ink. Every post used to sit on near-black, which made the profile
# grid read as one dark smudge and put the brand's warm terracotta identity on a
# surface that fought it. Feed presence comes from contrast at the edge of the
# post, and a warm paper against Instagram's white chrome separates cleanly
# while looking like something printed rather than something generated.
SURFACE = "#F7F1E6"             # the ground almost everything sits on
SURFACE_DEEP = "#E9DFCE"        # rules, dividers, the ground line
SURFACE_RAISED = "#FFFDF8"      # speech bubbles and plates

INK = "#191310"                 # near-black: type, outlines, Pip's edges
INK_SOFT = "#241D18"            # a touch lighter, for layering
TEXT_PRIMARY = "#191310"        # headlines
TEXT_SECONDARY = "#6E6156"      # body / secondary copy
TEXT_MUTED = "#9A8B7C"          # furniture / captions

# Per-category accent colours. Refined into one warm editorial family that sits
# well on the dark ink base and complements the terracotta brand: a coral for
# Technology, an emerald for Finance and a gold for Geopolitics (which replaces
# the old US-flag "Geo" treatment with a globally-neutral, on-brand colour).
# Darkened for a paper ground: the old values were tuned against near-black and
# fail contrast on light. All four now clear 4.5:1 on SURFACE.
CATEGORY_COLORS = {
    "Technology": "#C4562F",   # terracotta
    "Finance": "#1E6B54",      # deep emerald
    "Geopolitics": "#946217",  # marigold

    "Science": "#5B49B0",      # violet, distinct from the other three at a glance
}

# Public social handle, shown in the slide furniture and CTA.
INSTAGRAM_HANDLE = "@headlinne"

# The old stars-and-stripes styling on the word "Geo" is retired by default in
# favour of the clean amber accent above (it read as US-centric for global news
# and rendered poorly at small sizes). The renderer still supports it, so flip
# this to True to bring it back.
GEO_USE_FLAG = False


# --------------------------------------------------------------------------- #
# News sources (free, public RSS feeds from reputable publishers)
# --------------------------------------------------------------------------- #
# `tier` is a reputability weight used in ranking (higher = more trusted).
# Add or remove feeds freely. If a feed dies it is skipped, not fatal.
@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    category: str
    tier: float = 1.0


FEEDS: tuple[Feed, ...] = (
    # ---- Technology ----
    Feed("Reuters Tech", "https://www.reutersagency.com/feed/?best-topics=tech&post_type=best", "Technology", 1.4),
    Feed("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "Technology", 1.4),
    Feed("The Verge", "https://www.theverge.com/rss/index.xml", "Technology", 1.1),
    Feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "Technology", 1.1),
    Feed("TechCrunch", "https://techcrunch.com/feed/", "Technology", 1.0),
    Feed("Wired", "https://www.wired.com/feed/rss", "Technology", 1.0),
    Feed("Engadget", "https://www.engadget.com/rss.xml", "Technology", 0.9),

    # ---- Finance ----
    Feed("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Finance", 1.4),
    Feed("CNBC Finance", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "Finance", 1.2),
    Feed("MarketWatch Top", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "Finance", 1.1),
    Feed("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", "Finance", 0.9),
    Feed("Investing.com", "https://www.investing.com/rss/news_25.rss", "Finance", 0.8),

    # ---- Geopolitics ----
    Feed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "Geopolitics", 1.4),
    Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Geopolitics", 1.1),
    Feed("Guardian World", "https://www.theguardian.com/world/rss", "Geopolitics", 1.1),
    Feed("AP Top News", "https://feedx.net/rss/ap.xml", "Geopolitics", 1.2),
    Feed("NPR World", "https://feeds.npr.org/1004/rss.xml", "Geopolitics", 1.0),

    # ---- Science ----
    # Every feed above is a general, business or technology wire. Between them
    # they never carried the most-shared story of 5 August - a four-tonne rocket
    # stage hitting the Moon - so no amount of re-weighting could have surfaced
    # it. These four all fetched cleanly when tested against the new ranker, and
    # supplied four of its top eight.
    Feed("Phys.org", "https://phys.org/rss-feed/", "Science", 1.0),
    Feed("Space.com", "https://www.space.com/feeds/all", "Science", 1.0),
    Feed("New Scientist", "https://www.newscientist.com/subject/space/feed/", "Science", 1.0),
    Feed("Science Daily", "https://www.sciencedaily.com/rss/top/science.xml", "Science", 1.0),
    Feed("NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss", "Science", 1.3),
)

# How far back a story may be and still count as "today's news".
MAX_STORY_AGE_HOURS = 30

# Keywords that signal a story is broadly important. Used as one ranking signal.
# These are intentionally generic; the ranker also rewards cross-source coverage.
HIGH_INTEREST_KEYWORDS = (
    # Tech
    "apple", "google", "microsoft", "amazon", "meta", "openai", "nvidia", "tesla",
    "ai", "chip", "semiconductor", "breach", "cyberattack", "outage", "launch",
    "robot", "quantum", "startup", "acquisition", "funding round",
    # Finance / economy
    "fed", "central bank", "interest rate", "inflation", "recession", "earnings",
    "ipo", "merger", "layoffs", "stocks", "bond", "oil", "trade deal", "default",
    # Geopolitics / world
    "election", "war", "ceasefire", "sanctions", "summit", "treaty", "tariff",
    "ruling", "court", "protest", "strike", "coup", "nuclear", "border",
)


# --------------------------------------------------------------------------- #
# Schedule (all times in IST)
# --------------------------------------------------------------------------- #
# These are the canonical times. The GitHub Actions are triggered by cron-job.org
# at these IST times (see scripts/cron-jobs.md). Buffer posts are scheduled to
# fire at these exact times via `dueAt` when BUFFER_SCHEDULING_MODE == "scheduled".
SCHEDULE_IST = {
    "x_1": (13, 0),         # 1:00 PM
    "x_2": (17, 0),         # 5:00 PM
    "linkedin": (18, 0),    # 6:00 PM
    "instagram_1": (16, 0), # 4:00 PM
    "instagram_2": (18, 0), # 6:00 PM
    # Reels are the only real discovery surface on Instagram: the Reels tab is
    # served to people who do not follow you, while feed posts are shown almost
    # entirely to existing followers. A cold account therefore needs reels to be
    # seen at all, which is why they lead the day and bracket it.
    "reel_1": (9, 30),      # 9:30 AM  - news explainer of the day's biggest story
    "reel_2": (20, 0),      # 8:00 PM  - educational explainer (evergreen topic)
    # The daily story card lands in the evening scroll peak, when saves and
    # shares (the strongest ranking signals for a static post) are highest.
    "story_card": (21, 30), # 9:30 PM
}


# --------------------------------------------------------------------------- #
# Generation rules
# --------------------------------------------------------------------------- #
# Anchor used to decide which days are "promo only" on X. Days an even number of
# days after the anchor are promotional (1 Headlinne post); all other days carry
# 2 news posts. Move the anchor to align the rotation with whatever you want.
PROMO_ANCHOR_DATE = date(2026, 1, 1)

TWITTER_LIMIT = 280
TWITTER_RESERVED_TAIL = 30        # space kept for "HEADLINNE.com" + hashtags
LINKEDIN_SOFT_LIMIT = 2800        # well under LinkedIn's 3000 hard cap
INSTAGRAM_CAPTION_LIMIT = 2200
INSTAGRAM_MAX_HASHTAGS = 12       # Instagram allows 30; we stay tasteful

# Caption strategy. Instagram now indexes caption *text* for search, so the
# opening line is worth far more as readable keywords than as a hashtag block.
# We keep a handful of tags in the caption (where they still carry topical
# signal) and move the long tail into the first comment, which keeps the visible
# caption clean without losing the tags.
INSTAGRAM_CAPTION_HASHTAGS = 4       # shown in the caption itself
INSTAGRAM_FIRST_COMMENT_HASHTAGS = 12  # the rest, posted as the first comment
# Only the first ~125 characters of a caption show before "more", so the hook
# has to land inside that window.
INSTAGRAM_CAPTION_HOOK_CHARS = 125

WEBSITE = "HEADLINNE.com"
BRAND = "Headlinne"


# --------------------------------------------------------------------------- #
# Instagram carousel canvas
# --------------------------------------------------------------------------- #
# 1080 x 1350 is the 4:5 portrait format Instagram favours and is within its
# allowed 4:5 .. 1.91:1 range. Every slide is the same size so the carousel's
# "crop to first image" rule is automatically satisfied.
SLIDE_W = 1080
SLIDE_H = 1350


# --------------------------------------------------------------------------- #
# Instagram Reels
# --------------------------------------------------------------------------- #
# 1080 x 1920 is the full-screen 9:16 canvas Reels are designed around. Meta's
# publishing API accepts 0.01:1 to 10:1 but crops or pillarboxes anything that
# is not 9:16, and the Reels *tab* (the discovery surface that actually matters)
# only takes 9:16 clips between 5 and 90 seconds.
REEL_W = 1080
REEL_H = 1920
REEL_FPS = 30                     # inside Meta's accepted 23-60 fps range

# Length. Completion rate is the single strongest reel ranking signal, and it
# falls off a cliff past about 30 seconds, so we target a tight edit and hard-cap
# the result. Meta's own limits are 3 seconds to 15 minutes, far looser than what
# actually performs.
REEL_TARGET_SECONDS = 28
REEL_MIN_SECONDS = 8
REEL_MAX_SECONDS = 55

# x264 quality. CRF 20 is visually clean for flat graphic content while staying
# far under Meta's 300 MB / 25 Mbps ceiling.
#
# The preset is "veryfast" on purpose. At 1080x1920 a slower preset blocks the
# frame pipeline for minutes and buys almost nothing here: this footage is flat
# colour, large type and slow moves, which is the easiest thing in the world for
# an encoder. Instagram re-encodes everything on upload anyway, so the extra
# bitrate a fast preset spends never reaches a viewer.
REEL_CRF = _env_number("REEL_CRF", 20, int)
REEL_PRESET = _env_str("REEL_PRESET", "veryfast")

# Every reel burns in its own captions, because most reels are watched muted and
# the words have to survive that. The voiceover is the other half: it is what an
# explainer is actually for, it is what a viewer who unmutes expects to find, and
# a reel with a real audio track is treated as a more complete post than one
# carrying silence.
#
# When the voiceover is on, the narration drives the edit: each beat lasts as
# long as its spoken line plus a little air, so REEL_TARGET_SECONDS below only
# governs the silent fallback.
REEL_VOICEOVER = _env_flag("REEL_VOICEOVER", True)
REEL_TTS_MODEL = _env_str("REEL_TTS_MODEL", "gemini-3.1-flash-tts-preview")

# Speech quota is counted per model, so a second model is a second allowance.
# On the free tier that is the difference between narration being possible and
# not: one model's daily cap does not cover a day's fourteen lines, but two
# between them comfortably do. When one starts refusing, the client moves to the
# next immediately rather than waiting out a window it cannot use.
REEL_TTS_FALLBACK_MODELS = tuple(
    m.strip() for m in _env_str(
        "REEL_TTS_FALLBACK_MODELS",
        "gemini-2.5-flash-preview-tts,gemini-2.5-pro-preview-tts").split(",")
    if m.strip()
)

# Speech is rate limited far more tightly than text. The Gemini free tier allows
# THREE TTS requests per minute, and a reel needs one per beat plus the sign-off,
# so a pair of reels is fourteen calls. Fired back to back that is a guaranteed
# 429 storm, and the reels come out silent with the cause buried in retry logs.
#
# So calls are spaced deliberately. 21 seconds keeps a single run inside the free
# tier's window with a little margin. On a paid key set REEL_TTS_MIN_INTERVAL to
# 0 and the pacing disappears (two reels then narrate in seconds rather than in
# five minutes).
REEL_TTS_MIN_INTERVAL = _env_number("REEL_TTS_MIN_INTERVAL", 21.0, float)

# 429s are an expected part of normal operation here rather than a failure, so
# speech gets more attempts than text does.
REEL_TTS_MAX_RETRIES = _env_number("REEL_TTS_MAX_RETRIES", 6, int)

# Gemini TTS returns raw signed 16-bit little-endian PCM, mono, at 24 kHz.
TTS_SAMPLE_RATE = 24000
TTS_SAMPLE_WIDTH = 2
TTS_CHANNELS = 1

# Prebuilt voices. Audition them before settling: the two formats deliberately
# use different voices so the morning news reel and the evening lesson do not
# sound like the same person reading two scripts.
REEL_VOICE_NEWS = _env_str("REEL_VOICE_NEWS", "Charon")
REEL_VOICE_EDUCATION = _env_str("REEL_VOICE_EDUCATION", "Kore")

# Delivery direction, prepended to each line. Gemini TTS takes plain-language
# style instructions, and without one it reads news copy like an advertisement.
REEL_VOICE_STYLE = {
    "news": "Read this as a calm, credible news presenter. Clear and unhurried, "
            "no hype, no salesy lift at the end of sentences.",
    "education": "Read this warmly, like someone explaining an idea to a friend "
                 "who is genuinely curious. Relaxed, never lecturing.",
}

# Air around each spoken line: a moment for the cut to land before the voice
# starts, and a moment to breathe before the next one. Small numbers, but they
# are paid seven times over, so they are worth about five seconds of runtime
# between them.
REEL_VOICE_LEAD_IN = 0.25
REEL_VOICE_TAIL = 0.45

# Fallback when the voiceover is off or unavailable. Meta's spec expects an
# audio stream and some clients reject a video-only MP4, so a silent track is
# still muxed rather than none at all.
REEL_SILENT_AUDIO = True

# Optional override if ffmpeg is not on PATH. When unset we look for a system
# ffmpeg first and fall back to the one bundled with imageio-ffmpeg.
FFMPEG_BINARY = _env_str("FFMPEG_BINARY", "")


# --------------------------------------------------------------------------- #
# Educational reel topics
# --------------------------------------------------------------------------- #
# The evening reel teaches one evergreen idea rather than reporting news. The
# code owns the *device* (which graphic explains it best) and the model owns the
# words, which is what keeps these visually varied instead of fifteen versions of
# the same talking-head template.
#
# `graphic` must be one of the devices implemented in render/graphics.py:
#   bars     two or three labelled bars that grow, for "this vs that" magnitudes
#   counter  one number that counts up, for a single striking figure
#   flow     three chips connected by arrows, for a cause-and-effect mechanism
#   timeline a line that fills through labelled stops, for "what happens when"
#   split    a screen split in two halves, for a direct contrast
@dataclass(frozen=True)
class EducationTopic:
    title: str        # the idea being taught, in plain words
    angle: str        # the specific take that makes it worth 30 seconds
    graphic: str      # which visual device carries the explanation
    category: str     # drives the accent colour and the pill


EDUCATION_TOPICS: tuple[EducationTopic, ...] = (
    EducationTopic(
        "Why a rate hike makes your loan cost more",
        "Follow one decision from a central bank down to one person's monthly payment.",
        "flow", "Finance"),
    EducationTopic(
        "Falling inflation does not mean falling prices",
        "Inflation slowing means prices climb more slowly, not that they come back down.",
        "bars", "Finance"),
    EducationTopic(
        "How a bank run actually happens",
        "It is three steps, and the third one is pure psychology.",
        "flow", "Finance"),
    EducationTopic(
        "A company can lose money and still be worth billions",
        "Markets price the future, not the current year, which is why losses and value coexist.",
        "bars", "Finance"),
    EducationTopic(
        "Why one narrow strait moves the oil price",
        "A huge share of the world's oil sails through a few chokepoints.",
        "flow", "Geopolitics"),
    EducationTopic(
        "What a sanction actually does",
        "Sanctions do not switch an economy off, they raise the cost of every transaction.",
        "flow", "Geopolitics"),
    EducationTopic(
        "A ceasefire is not a peace deal",
        "One pauses the fighting, the other settles the reason for it.",
        "split", "Geopolitics"),
    EducationTopic(
        "Why markets move before an election result",
        "Traders price the probability, so the move happens ahead of the news.",
        "timeline", "Finance"),
    EducationTopic(
        "Why chip export rules matter more than tariffs",
        "A tariff makes something pricier, an export rule makes it unavailable.",
        "split", "Technology"),
    EducationTopic(
        "On-device AI versus cloud AI",
        "Where the thinking happens changes speed, privacy and cost.",
        "split", "Technology"),
    EducationTopic(
        "What a chip's nanometre number really means",
        "It stopped being a measurement years ago and became a marketing label.",
        "split", "Technology"),
    EducationTopic(
        "Why a rate cut takes months to reach you",
        "The decision is instant, the effect travels through the economy in stages.",
        "timeline", "Finance"),
    EducationTopic(
        "Why two outlets report the same story differently",
        "Same facts, different choices about which fact goes first.",
        "split", "Technology"),
    EducationTopic(
        "What 'sources say' actually means",
        "There is a real hierarchy behind that phrase, and it tells you how solid a story is.",
        "flow", "Technology"),
    EducationTopic(
        "How a headline can be true and still mislead",
        "Leaving out the denominator is the oldest trick in the business.",
        "bars", "Technology"),
    EducationTopic(
        "What GDP misses about how people live",
        "It counts activity, not whether life got better.",
        "bars", "Finance"),
)


# --------------------------------------------------------------------------- #
# Format switches
# --------------------------------------------------------------------------- #
# Each daily format can be turned off without touching code. Reels and the story
# card are on by default because they are what a cold account needs.
REELS_ENABLED = _env_flag("REELS_ENABLED", True)
STORY_CARD_ENABLED = _env_flag("STORY_CARD_ENABLED", True)
# The second daily carousel. With reels and the story card added, four feed posts
# a day is more than a small account needs, and posting past the point where each
# post can find its audience dilutes every one of them. Set this to "false" to
# drop to one carousel a day (recommended once the reels are running).
IG_SECOND_CAROUSEL = _env_flag("IG_SECOND_CAROUSEL", False)

# Carousels are the most expensive format to produce and the least suited to a
# daily beat: five slides of argument is a weekly artefact, not a daily one. The
# daily rhythm is two reels and one or two story cards; the carousel becomes a
# considered weekly piece. Days are 0=Monday.
CAROUSEL_WEEKDAYS = tuple(
    int(d) for d in _env_str("CAROUSEL_WEEKDAYS", "1,4").split(",") if d.strip()
)


# --------------------------------------------------------------------------- #
# Gemini model
# --------------------------------------------------------------------------- #
GEMINI_MODEL = "gemini-3.1-flash-lite"

# Quota is counted per model, so a second model is a second allowance - the same
# reasoning as REEL_TTS_FALLBACK_MODELS above, which text never had. A run that
# exhausts the primary model's daily cap currently fails outright rather than
# moving on. On a 429 the client should advance immediately rather than waiting
# out a window it cannot use.
GEMINI_FALLBACK_MODELS = tuple(
    m.strip() for m in _env_str(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.1-flash,gemini-2.5-flash-lite,gemini-2.5-flash").split(",")
    if m.strip()
)
# Thinking budget for generation: "minimal" | "low" | "medium" | "high".
# "low" gives clean, instruction-following copy without much latency or cost.
GEMINI_THINKING_LEVEL = _env_str("GEMINI_THINKING_LEVEL", "low")
GEMINI_TEMPERATURE = _env_number("GEMINI_TEMPERATURE", 0.65, float)
GEMINI_MAX_RETRIES = 4


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
# "scheduled" -> generation schedules X/LinkedIn into Buffer with dueAt = slot
#               time, and Buffer publishes them. (Recommended: fewer triggers.)
# "trigger"   -> `publish --target x-1|x-2|linkedin` posts at call time, so you
#               must add cron-job.org triggers for those slots too.
BUFFER_SCHEDULING_MODE = _env_str("BUFFER_SCHEDULING_MODE", "scheduled")

BUFFER_API_URL = "https://api.buffer.com"

# Posting the hashtag long tail as the first comment is a PAID Buffer feature.
# On the free plan the API rejects the whole post rather than ignoring the
# field, so this defaults to off: the tags go at the end of the caption instead,
# which costs a little tidiness and nothing else. The opening line is what
# caption search reads, and it is unaffected either way.
#
# Set to true on a paid Buffer plan for a cleaner caption. If the plan turns out
# not to support it the publisher retries without it rather than losing the post.
BUFFER_FIRST_COMMENT = _env_flag("BUFFER_FIRST_COMMENT", False)

# Attach the rendered branded card image to X posts (lifts reach). The tweet text
# stays a valid standalone post either way. Set to "false" to post text only.
X_ATTACH_CARD = _env_flag("X_ATTACH_CARD", True)

# Meta Graph API (the alternative, direct Instagram publisher in
# headlinne/publish/meta.py). The active pipeline publishes Instagram through
# Buffer, but this path is fully supported for anyone who prefers to publish
# carousels straight to Meta with the secrets from setup steps 4 and 5.
META_GRAPH_URL = "https://graph.facebook.com"
META_GRAPH_VERSION = _env_str("META_GRAPH_VERSION", "v21.0")


# --------------------------------------------------------------------------- #
# Reddit engagement (opportunity finder + human-review assistant)
# --------------------------------------------------------------------------- #
# IMPORTANT, read this before touching the Reddit tooling:
#
# This is deliberately NOT an autonomous mass-poster. Reddit's Content Policy and
# API Terms prohibit automated, unsolicited promotion, and every large subreddit
# bans it. A bot dropping ~100 promo comments a day is textbook spam: it gets the
# account and the headlinne.com domain sitewide-shadowbanned, which is very hard
# to undo and poisons the exact channel you want to open. So the tool finds
# relevant threads and drafts genuinely helpful replies for a human to review and
# post. It is capped low, is helpful-first, and only ever suggests a Headlinne
# mention where it is on-topic, allowed, and disclosed.

REDDIT_USER_AGENT = _env_str(
    "REDDIT_USER_AGENT", "web:headlinne-assist:v1.0 (by /u/your_reddit_username)")

# How many opportunities one `reddit find` run may surface / draft. Kept low on
# purpose. The hard cap below cannot be exceeded even via the env var.
REDDIT_ENGAGEMENT_CAP = _env_number("REDDIT_ENGAGEMENT_CAP", 12, int)
REDDIT_ENGAGEMENT_HARD_MAX = 25

# At most this share of surfaced replies may mention Headlinne (Reddit's informal
# 9:1 rule: be a helpful community member ~10x more than you self-promote).
REDDIT_PROMO_RATIO = 0.1

# Do not touch the same subreddit more than once inside this window, and never
# engage the same thread twice (tracked in state/reddit_state.json).
REDDIT_SUBREDDIT_COOLDOWN_HOURS = 12

# Only consider threads inside this age window with at least this much activity,
# so replies land where people are actually reading and are still welcome.
REDDIT_MIN_THREAD_AGE_HOURS = 1
REDDIT_MAX_THREAD_AGE_HOURS = 20
REDDIT_MIN_COMMENTS = 3


@dataclass(frozen=True)
class RedditTarget:
    """A subreddit we may engage in. `allow_promo` gates whether a disclosed
    Headlinne mention is ever permitted there (most communities: never)."""

    name: str
    category: str
    allow_promo: bool = False


# A realistic map. Promo is allowed ONLY in maker / show-your-project communities
# that explicitly welcome it. Everywhere else the tool is help-only, because that
# is what those subreddits' rules require.
REDDIT_TARGETS: tuple[RedditTarget, ...] = (
    # News / world (help-only, strict no-promo)
    RedditTarget("technology", "Technology", False),
    RedditTarget("tech", "Technology", False),
    RedditTarget("artificial", "Technology", False),
    RedditTarget("Futurology", "Technology", False),
    RedditTarget("gadgets", "Technology", False),
    RedditTarget("finance", "Finance", False),
    RedditTarget("economics", "Finance", False),
    RedditTarget("investing", "Finance", False),
    RedditTarget("personalfinance", "Finance", False),
    RedditTarget("worldnews", "Geopolitics", False),
    RedditTarget("geopolitics", "Geopolitics", False),
    RedditTarget("news", "Geopolitics", False),
    # Maker / founder communities that welcome disclosed self-promotion
    RedditTarget("SideProject", "Product", True),
    RedditTarget("startups", "Product", True),
    RedditTarget("alphaandbetausers", "Product", True),
    RedditTarget("InternetIsBeautiful", "Product", True),
)

# Search terms used to find threads where Headlinne is genuinely on-topic.
REDDIT_KEYWORDS = (
    "personalised news", "personalized news", "news app", "news overload",
    "information overload", "how do you keep up with the news", "unbiased news",
    "news aggregator", "media bias", "ai news summary", "stay informed",
    "too much news", "news fatigue", "best news app",
)

# Threads whose topic is sensitive: never attach any promotion, and skip them
# unless a purely supportive, non-promotional reply is clearly warranted.
REDDIT_SENSITIVE_MARKERS = (
    "suicide", "self harm", "self-harm", "depress", "grief", "died", "death",
    "passed away", "cancer", "diagnosis", "abuse", "assault", "war crime",
    "shooting", "terror", "layoff", "fired", "medical advice", "lawsuit",
)


@dataclass(frozen=True)
class Secrets:
    """All secrets, read from the environment. Never commit real values."""

    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))

    # Buffer (X + LinkedIn + Instagram)
    buffer_token: str = field(default_factory=lambda: os.getenv("BUFFER_ACCESS_TOKEN", ""))
    buffer_channel_x: str = field(default_factory=lambda: os.getenv("BUFFER_CHANNEL_ID_X", ""))
    buffer_channel_linkedin: str = field(default_factory=lambda: os.getenv("BUFFER_CHANNEL_ID_LINKEDIN", ""))
    buffer_channel_instagram: str = field(default_factory=lambda: os.getenv("BUFFER_CHANNEL_ID_INSTAGRAM", ""))

    # Meta Graph API (direct Instagram publishing, see publish/meta.py).
    meta_token: str = field(default_factory=lambda: os.getenv("META_ACCESS_TOKEN", ""))
    ig_user_id: str = field(default_factory=lambda: os.getenv("IG_USER_ID", ""))

    # Reddit (script app: create one at reddit.com/prefs/apps). The tool reads
    # these from the environment only. Never hardcode or commit a token.
    reddit_client_id: str = field(default_factory=lambda: os.getenv("REDDIT_CLIENT_ID", ""))
    reddit_client_secret: str = field(default_factory=lambda: os.getenv("REDDIT_CLIENT_SECRET", ""))
    reddit_username: str = field(default_factory=lambda: os.getenv("REDDIT_USERNAME", ""))
    reddit_password: str = field(default_factory=lambda: os.getenv("REDDIT_PASSWORD", ""))

    # Where rendered carousel images are publicly served from.
    # For a public GitHub repo this is filled automatically in CI from
    # GITHUB_REPOSITORY / GITHUB_REF_NAME. You can override for a custom host.
    github_repository: str = field(default_factory=lambda: os.getenv("GITHUB_REPOSITORY", ""))
    github_ref_name: str = field(default_factory=lambda: _env_str("GITHUB_REF_NAME", "main"))
    public_image_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_IMAGE_BASE_URL", ""))


SECRETS = Secrets()


def content_dir_for(day: date) -> Path:
    """Folder that holds everything generated for a given day."""
    return CONTENT_DIR / day.isoformat()
