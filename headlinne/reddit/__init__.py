"""Reddit opportunity finder and human-review assistant.

Deliberately not an autonomous poster: it surfaces relevant threads and drafts
helpful replies for a person to approve, with hard guardrails (low caps,
per-subreddit cooldowns, de-duplication, the 9:1 promo ratio, sensitive-topic
filtering). See headlinne/config.py for the policy knobs.
"""

from .pipeline import find_opportunities, post_one  # noqa: F401
