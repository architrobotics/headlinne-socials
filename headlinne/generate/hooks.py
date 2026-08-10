"""Hook archetypes and caption construction.

Two things decide whether a news post is seen at all: the first two seconds of a
reel and the first line of a caption. Left to itself a model writes the same
shape of opener every single day ("X just announced Y, and here is why it
matters"), and an account that opens the same way daily trains the algorithm and
the audience to skip it.

So the *structure* of the hook is owned here, in code, and rotated
deterministically. The model still writes the words, but it is handed a specific
rhetorical shape to write into, which is what keeps a month of posts from
collapsing into one voice.

The archetypes are the ones that actually earn watch time in news, finance and
technology explainers. Each pairs a reel opener (spoken/on-screen, must land in
under two seconds) with a caption opener (must land inside the ~125 characters
Instagram shows before "more").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..config import (INSTAGRAM_CAPTION_HASHTAGS, INSTAGRAM_CAPTION_HOOK_CHARS,
                      INSTAGRAM_FIRST_COMMENT_HASHTAGS, INSTAGRAM_HANDLE,
                      WEBSITE)
from ..quality.sanitize import sanitize


# --------------------------------------------------------------------------- #
# Archetypes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Hook:
    """One rhetorical shape for an opener.

    `brief` is written straight into the prompt, so it is phrased as an
    instruction to a writer rather than as documentation.
    """

    name: str
    brief: str
    example: str


HOOKS: tuple[Hook, ...] = (
    Hook(
        "contradiction",
        "Open by naming the assumption most people hold, then puncture it with "
        "what the reporting actually shows. Two short sentences, no more.",
        "Everyone assumed this would raise prices. It did the opposite.",
    ),
    Hook(
        "stakes",
        "Open with the concrete thing this costs or changes for an ordinary "
        "person. Money, time, or a decision they are about to make.",
        "This quietly changes what your bank can charge you.",
    ),
    Hook(
        "scale",
        "Open by making a number feel real through a comparison an ordinary "
        "person can picture. Never just state the figure.",
        "That is not a company. That is the entire economy of a mid-sized country.",
    ),
    Hook(
        "mechanism",
        "Open by promising the machinery, not the event. Tell the viewer they "
        "are about to see how the thing actually works.",
        "Here is what physically happens when a country freezes another's money.",
    ),
    Hook(
        "consequence",
        "Open from the future. Name the specific thing that changes next if "
        "this holds, then go back and explain why.",
        "If this holds, your next phone gets cheaper. Here is the chain.",
    ),
    Hook(
        "question_gap",
        "Open with a genuine question the reporting answers and the viewer "
        "cannot. It must be a real puzzle, never a rhetorical one.",
        "Why would a company sell this at a loss on purpose?",
    ),
    Hook(
        "analogy",
        "Open by transplanting the situation into something domestic and "
        "familiar, so the shape of it lands before any jargon does.",
        "Imagine your landlord could rewrite your lease after you signed it.",
    ),
    Hook(
        "count",
        "Open by promising a specific small number of things and flagging that "
        "one of them matters more than the rest.",
        "Three things happened this week. The third one is the expensive one.",
    ),
)

HOOK_NAMES = tuple(h.name for h in HOOKS)


def pick_hook(day: date, slot: str) -> Hook:
    """Deterministically choose an archetype for a day and slot.

    Deterministic (rather than random) so a re-run of the same day produces the
    same content, and offset by slot so the morning and evening reels never open
    the same way on the same day.
    """
    offset = sum(ord(c) for c in slot)
    return HOOKS[(day.toordinal() + offset) % len(HOOKS)]


def hook_brief(day: date, slot: str) -> str:
    """The archetype rendered as prompt text."""
    hook = pick_hook(day, slot)
    return (f"Use the \"{hook.name}\" opening. {hook.brief}\n"
            f"Shape (do not copy the words, only the shape): \"{hook.example}\"")


# --------------------------------------------------------------------------- #
# Hashtags
# --------------------------------------------------------------------------- #
def clean_tag(tag: str) -> str:
    return "#" + str(tag).lstrip("#").replace(" ", "")


def split_hashtags(hashtags: list[str]) -> tuple[str, str]:
    """Split tags into a short caption block and a first-comment block.

    Instagram reads caption text for search now, so a wall of tags at the top of
    a caption costs readability without buying reach. A few topical tags stay
    where they carry signal, and the long tail moves to the first comment.
    """
    clean = []
    seen: set[str] = set()
    for tag in hashtags:
        t = clean_tag(tag)
        if len(t) <= 1 or t.lower() in seen:
            continue
        seen.add(t.lower())
        clean.append(t)

    in_caption = clean[:INSTAGRAM_CAPTION_HASHTAGS]
    remainder = clean[INSTAGRAM_CAPTION_HASHTAGS:
                      INSTAGRAM_CAPTION_HASHTAGS + INSTAGRAM_FIRST_COMMENT_HASHTAGS]
    return " ".join(in_caption), " ".join(remainder)


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def _first_line(text: str, limit: int = INSTAGRAM_CAPTION_HOOK_CHARS) -> str:
    """Trim the opener to what Instagram shows before the 'more' fold.

    Cuts at a sentence end when one is available inside the window, so the
    visible caption never ends mid-thought.
    """
    text = sanitize(text).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    for stop in (". ", "? ", "! "):
        idx = window.rfind(stop)
        if idx > limit * 0.5:
            return window[: idx + 1].strip()
    return window.rsplit(" ", 1)[0].rstrip(",.:;- ").strip()


def build_caption(
    *,
    opener: str,
    body: str = "",
    question: str = "",
    hashtags: list[str] | None = None,
    cta: str = "",
    include_website: bool = True,
) -> tuple[str, str]:
    """Assemble an Instagram caption and its first comment.

    Layout, in the order the reader meets it:
      1. the opener, kept inside the visible-before-"more" window and written as
         readable keywords because that line is what caption search indexes,
      2. the substance, in short paragraphs,
      3. one genuine question, because comments are the heaviest ranking signal
         a post can earn,
      4. the follow / site line,
      5. a few topical hashtags.

    Returns ``(caption, first_comment)``.
    """
    body = sanitize(body)
    full_opener = sanitize(opener).replace("\n", " ").strip()
    opener = _first_line(full_opener)
    if len(opener) < len(full_opener):
        # Whatever did not fit in the visible window moves into the body. The
        # fold decides where the caption *breaks*, not how much of it survives.
        overflow = full_opener[len(opener):].strip()
        body = f"{overflow}\n\n{body}".strip() if body else overflow
    question = sanitize(question).strip()
    if question and not question.endswith("?"):
        question = question.rstrip(".") + "?"

    cta = cta or f"Follow {INSTAGRAM_HANDLE} for a daily brief."
    if include_website and WEBSITE.lower() not in cta.lower():
        cta = f"{cta} Full story on {WEBSITE}."

    caption_tags, comment_tags = split_hashtags(hashtags or [])

    parts = [p for p in (opener, body, question, cta, caption_tags) if p]
    return "\n\n".join(parts), comment_tags
