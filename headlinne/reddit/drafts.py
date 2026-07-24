"""Draft a genuinely helpful reply for a thread, with an honest promo call.

The model writes the reply (and, only when permitted, a soft disclosed mention).
The code decides whether a mention is even allowed (see policy) and sanitises the
result. The human makes the final call before anything is posted.
"""

from __future__ import annotations

from ..gemini.client import GeminiClient
from ..gemini.prompts import REDDIT_GUIDE, reddit_reply_prompt
from ..logging_setup import get_logger
from ..quality.sanitize import sanitize
from .models import RedditThread

log = get_logger("reddit.drafts")


def draft_reply(gemini: GeminiClient, thread: RedditThread,
                allow_promo_mention: bool) -> dict:
    """Return {reply, mentions_headlinne, disclosure, rationale}.

    The reply is sanitised (brand punctuation rules) and, if a mention was not
    permitted, any accidental brand reference is treated as non-promotional by
    the caller. Failures degrade to an empty reply rather than raising.
    """
    try:
        data = gemini.generate_json(
            system=REDDIT_GUIDE,
            prompt=reddit_reply_prompt(thread.title, thread.selftext,
                                       thread.subreddit, allow_promo_mention),
        )
    except Exception as exc:  # pragma: no cover - network/model best-effort
        log.warning("draft failed for %s: %s", thread.id, exc)
        return {"reply": "", "mentions_headlinne": False, "disclosure": "", "rationale": ""}

    reply = sanitize(data.get("reply", ""))
    mentions = bool(data.get("mentions_headlinne")) and "headlinne" in reply.lower()
    # If a mention was not permitted, never report it as a promo.
    if not allow_promo_mention:
        mentions = False
    return {
        "reply": reply,
        "mentions_headlinne": mentions,
        "disclosure": sanitize(data.get("disclosure", "")),
        "rationale": sanitize(data.get("rationale", "")),
    }
