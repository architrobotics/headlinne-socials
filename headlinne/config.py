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
CATEGORIES = ("Technology", "Finance", "Geopolitics")

# Short labels used in copy and slide titles.
CATEGORY_LABELS = {
    "Technology": "Tech",
    "Finance": "Finance",
    "Geopolitics": "Geopolitics",
}

# Uppercase labels used on the small category pill in the carousel furniture.
CATEGORY_PILL = {
    "Technology": "TECHNOLOGY",
    "Finance": "FINANCE",
    "Geopolitics": "WORLD",
}

# --------------------------------------------------------------------------- #
# Brand + design system
# --------------------------------------------------------------------------- #
# The whole visual identity is anchored on the terracotta logo. Every carousel
# slide is built from these tokens so covers, story slides and the CTA read as
# one designed system rather than three loosely-related layouts.
BRAND_TERRACOTTA = "#C76A44"    # the logo colour, primary brand accent
BRAND_TERRACOTTA_HI = "#E08A5F"  # a lighter tint for glows / hov(text) states

INK = "#141210"                 # warm near-black, base for panels and the CTA
INK_SOFT = "#1F1A16"            # a touch lighter, for layering
TEXT_PRIMARY = "#F6F1EA"        # warm off-white for headlines
TEXT_SECONDARY = "#C7BCB0"      # warm grey for body / secondary copy
TEXT_MUTED = "#8B8177"          # dim warm grey for furniture / captions

# Per-category accent colours. Refined into one warm editorial family that sits
# well on the dark ink base and complements the terracotta brand: a coral for
# Technology, an emerald for Finance and a gold for Geopolitics (which replaces
# the old US-flag "Geo" treatment with a globally-neutral, on-brand colour).
CATEGORY_COLORS = {
    "Technology": "#F0553A",   # coral / vermilion
    "Finance": "#22B07D",      # emerald
    "Geopolitics": "#E3A63A",  # amber / gold
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
# Gemini model
# --------------------------------------------------------------------------- #
GEMINI_MODEL = "gemini-3.1-flash-lite"
# Thinking budget for generation: "minimal" | "low" | "medium" | "high".
# "low" gives clean, instruction-following copy without much latency or cost.
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.65"))
GEMINI_MAX_RETRIES = 4


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
# "scheduled" -> generation schedules X/LinkedIn into Buffer with dueAt = slot
#               time, and Buffer publishes them. (Recommended: fewer triggers.)
# "trigger"   -> `publish --target x-1|x-2|linkedin` posts at call time, so you
#               must add cron-job.org triggers for those slots too.
BUFFER_SCHEDULING_MODE = os.getenv("BUFFER_SCHEDULING_MODE", "scheduled")

BUFFER_API_URL = "https://api.buffer.com"

# Meta Graph API (the alternative, direct Instagram publisher in
# headlinne/publish/meta.py). The active pipeline publishes Instagram through
# Buffer, but this path is fully supported for anyone who prefers to publish
# carousels straight to Meta with the secrets from setup steps 4 and 5.
META_GRAPH_URL = "https://graph.facebook.com"
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")


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

    # Where rendered carousel images are publicly served from.
    # For a public GitHub repo this is filled automatically in CI from
    # GITHUB_REPOSITORY / GITHUB_REF_NAME. You can override for a custom host.
    github_repository: str = field(default_factory=lambda: os.getenv("GITHUB_REPOSITORY", ""))
    github_ref_name: str = field(default_factory=lambda: os.getenv("GITHUB_REF_NAME", "main"))
    public_image_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_IMAGE_BASE_URL", ""))


SECRETS = Secrets()


def content_dir_for(day: date) -> Path:
    """Folder that holds everything generated for a given day."""
    return CONTENT_DIR / day.isoformat()
