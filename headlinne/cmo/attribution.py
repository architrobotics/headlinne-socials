"""Tagged links, and an honest account of which surfaces cannot carry one.

Every post today ends with the bare string `HEADLINNE.com`. A reel, a LinkedIn
essay and a Reddit reply are therefore indistinguishable at the destination, so
no channel can ever be shown to work or shown to fail. This module fixes that
where it is fixable, and - the more useful half - says plainly where it is not.

**Where a link is clickable, it gets tagged.** X, LinkedIn, Reddit and a
directory listing all take a real URL, so they get UTM parameters derived from
the day and the slot. Deterministic: the same day and slot always produce the
same URL, so regenerating a day cannot fork the attribution.

**Instagram cannot carry a clickable link at all.** Not in a caption, not in a
reel, not on a story card. The only clickable link on the account is the one in
the bio, it is the same link for every post, and the Graph API cannot change it.
So Instagram output is marked `UNATTRIBUTABLE` rather than given a tag that
would look measured and never resolve.

That is not a limitation to be worked around, it is the finding. Three of the
four things this pipeline makes every day go to a surface where their
contribution cannot be observed, and `coverage()` puts a number on it. An
allocator that did not know this would keep spending on the channel it cannot
see and call the silence a result.

Two ways out exist and both need the product, not this repository: serve a short
typeable path per day (`headlinne.com/d/0914`), or rotate the bio link daily by
hand. Until one exists, the honest report is a share below one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from urllib.parse import urlencode, urlsplit, urlunsplit

from ..config import PRODUCT_URL, WEBSITE


class Link(str, Enum):
    CLICKABLE = "clickable"          # a real URL the reader can tap
    UNATTRIBUTABLE = "unattributable"  # no link surface at all


@dataclass(frozen=True)
class Surface:
    slot: str
    source: str          # utm_source: the platform
    medium: str          # utm_medium: the format
    link: Link
    code: str = ""       # short slot code, for the compact form
    # True where characters are the binding constraint. A full UTM string is
    # about 98 characters; on a 280 character post that is a third of the space,
    # spent on something the reader never sees. The compact form carries the
    # same three facts - which surface, which slot, which day - in 32.
    compact: bool = False


# Every slot the pipeline can publish, and what it can carry.
SURFACES: dict[str, Surface] = {s.slot: s for s in (
    Surface("x_1", "x", "post", Link.CLICKABLE, "x1", compact=True),
    Surface("x_2", "x", "post", Link.CLICKABLE, "x2", compact=True),
    Surface("linkedin", "linkedin", "post", Link.CLICKABLE, "li"),
    # Instagram. No clickable link exists on any of these surfaces.
    Surface("instagram_1", "instagram", "carousel", Link.UNATTRIBUTABLE, "ig1"),
    Surface("instagram_2", "instagram", "carousel", Link.UNATTRIBUTABLE, "ig2"),
    Surface("reel_1", "instagram", "reel", Link.UNATTRIBUTABLE, "rl1"),
    Surface("reel_2", "instagram", "reel", Link.UNATTRIBUTABLE, "rl2"),
    Surface("story_card", "instagram", "story_card", Link.UNATTRIBUTABLE, "sc"),
    # Off-pipeline surfaces the CMO also drives.
    Surface("reddit", "reddit", "comment", Link.CLICKABLE, "rd", compact=True),
    Surface("listing", "directory", "listing", Link.CLICKABLE, "ls"),
    Surface("devto", "devto", "article", Link.CLICKABLE, "dv"),
    Surface("hashnode", "hashnode", "article", Link.CLICKABLE, "hn"),
)}


def campaign_for(day: date) -> str:
    """The campaign a day belongs to. Monthly, so a month is comparable to a
    month without anyone having to name a campaign by hand."""
    return f"{day:%Y-%m}"


def content_for(day: date, slot: str) -> str:
    """The one post. This is what makes attribution per-post rather than
    per-channel, and it is what lets a good day be told from a good channel."""
    return f"{day.isoformat()}-{slot}"


def tag(url: str, *, source: str, medium: str, campaign: str,
        content: str, term: str = "") -> str:
    """Append UTM parameters, preserving anything already on the URL.

    Sorted, so the same inputs always produce a byte-identical URL. An
    attribution scheme whose output depends on dictionary ordering produces two
    links for one post the first time the interpreter changes its mind.
    """
    parts = urlsplit(url)
    existing = parts.query
    params = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
        "utm_content": content,
    }
    if term:
        params["utm_term"] = term
    query = urlencode(sorted(params.items()))
    if existing:
        query = f"{existing}&{query}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query,
                       parts.fragment))


def ref_for(day: date, slot: str, *, arm: str = "") -> str:
    """The compact code: which slot, which day, and the arm if there is one.

    `x1-0914` rather than five UTM parameters. It carries the same facts, it
    survives being read aloud, and it costs 19 characters over the bare domain
    instead of 85.
    """
    surface = SURFACES.get(slot)
    code = (surface.code if surface and surface.code else slot)
    ref = f"{code}-{day:%m%d}"
    return f"{ref}.{arm}" if arm else ref


def for_slot(day: date, slot: str, *, arm: str = "",
             url: str | None = None) -> str | None:
    """The tagged URL for one post, or None when the surface cannot carry one.

    None is the important return value. A caller that gets None must print the
    plain domain, because a URL with tracking parameters typed out in an
    Instagram caption is worse than the bare one: it is longer, it is uglier, it
    is not clickable, and nobody types it.
    """
    surface = SURFACES.get(slot)
    if surface is None or surface.link is Link.UNATTRIBUTABLE:
        return None
    base = url or PRODUCT_URL
    if surface.compact:
        parts = urlsplit(base)
        query = urlencode([("r", ref_for(day, slot, arm=arm))])
        if parts.query:
            query = f"{parts.query}&{query}"
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/",
                           query, parts.fragment))
    return tag(base,
               source=surface.source, medium=surface.medium,
               campaign=campaign_for(day), content=content_for(day, slot),
               term=arm)


def display_for(day: date, slot: str, *, arm: str = "") -> str:
    """What actually goes in the copy: a tagged URL, or the plain wordmark.

    The pipeline calls this instead of interpolating WEBSITE, and the fallback
    is the exact string it used before, so a slot with no attribution reads
    today exactly as it read yesterday.
    """
    return for_slot(day, slot, arm=arm) or WEBSITE


# --------------------------------------------------------------------------- #
# How much of the day can be measured at all
# --------------------------------------------------------------------------- #
@dataclass
class Coverage:
    slots: list[str]
    attributable: list[str]
    blind: list[str]

    @property
    def share(self) -> float:
        return len(self.attributable) / len(self.slots) if self.slots else 0.0

    def summary(self) -> str:
        if not self.blind:
            return f"every one of the {len(self.slots)} posts carries a tagged link."
        return (f"{len(self.attributable)} of {len(self.slots)} posts carry a "
                f"tagged link ({self.share:.0%}). The other "
                f"{len(self.blind)} ({', '.join(self.blind)}) go to surfaces "
                f"with no clickable link, so their contribution cannot be "
                f"observed at all.")


def coverage(slots) -> Coverage:
    """What share of a day's output can be measured. Below 1.0 is the finding."""
    slots = list(slots)
    attributable, blind = [], []
    for slot in slots:
        surface = SURFACES.get(slot)
        if surface and surface.link is Link.CLICKABLE:
            attributable.append(slot)
        else:
            blind.append(slot)
    return Coverage(slots=slots, attributable=attributable, blind=blind)


# --------------------------------------------------------------------------- #
# Reading a ref back
# --------------------------------------------------------------------------- #
# Slot codes, inverted. Built once from SURFACES so the two can never drift:
# a code added on one side and forgotten on the other would decode as unknown
# and quietly land in "direct", which is where attribution goes to die.
_BY_CODE: dict[str, str] = {s.code: s.slot for s in SURFACES.values() if s.code}


@dataclass(frozen=True)
class Ref:
    """A decoded ref. `slot` and `day` are None when the ref did not carry them."""

    raw: str
    slot: str | None = None
    channel: str | None = None
    day: date | None = None
    arm: str = ""

    @property
    def known(self) -> bool:
        return self.channel is not None


def parse_ref(raw: str, *, today: date | None = None) -> Ref:
    """Decode whatever the signup flow captured, in any of the forms we mint.

    Three shapes reach the product, because three surfaces have different room:

        x1-0914       the compact form, from a character-constrained post
        2026-09-14-linkedin   utm_content, from a surface with room
        linkedin      a bare utm_source, when only that was kept

    Anything else - `direct`, a referrer we never minted, a truncated string -
    decodes to a Ref with `known` False. That is reported as unattributed rather
    than guessed into the nearest channel: a wrong attribution is worse than an
    absent one, because the wrong one gets acted on.

    **The compact form carries no year.** `0914` is September 14th of whichever
    year is most recently past, resolved against `today`. That is unambiguous
    inside any twelve month window and this campaign is four months long, so it
    holds - but a ref read more than a year after it was minted will be misdated,
    and that limit is the price of the 19 characters it saves on a 280 character
    post.
    """
    today = today or date.today()
    raw = (raw or "").strip()
    if not raw:
        return Ref(raw=raw)

    body, _, arm = raw.partition(".")

    # utm_content: 2026-09-14-linkedin
    parts = body.split("-")
    if len(parts) >= 4 and len(parts[0]) == 4 and parts[0].isdigit():
        slot = "-".join(parts[3:])
        try:
            day = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            day = None
        surface = SURFACES.get(slot)
        return Ref(raw=raw, slot=slot if surface else None,
                   channel=surface.source if surface else None,
                   day=day, arm=arm)

    # compact: x1-0914
    if len(parts) == 2 and len(parts[1]) == 4 and parts[1].isdigit():
        slot = _BY_CODE.get(parts[0])
        surface = SURFACES.get(slot) if slot else None
        return Ref(raw=raw, slot=slot,
                   channel=surface.source if surface else None,
                   day=_resolve_mmdd(parts[1], today), arm=arm)

    # a bare source, e.g. linkedin
    sources = {s.source for s in SURFACES.values()}
    if body in sources:
        return Ref(raw=raw, channel=body, arm=arm)

    return Ref(raw=raw, arm=arm)


def _resolve_mmdd(mmdd: str, today: date) -> date | None:
    """The most recent past date matching MMDD, relative to `today`."""
    month, dayno = int(mmdd[:2]), int(mmdd[2:])
    for year in (today.year, today.year - 1):
        try:
            candidate = date(year, month, dayno)
        except ValueError:
            continue                      # 29 February in a non-leap year
        if candidate <= today:
            return candidate
    return None
