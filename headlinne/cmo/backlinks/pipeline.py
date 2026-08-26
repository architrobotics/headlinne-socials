"""Build the submission queue, submit what may be submitted, verify what landed.

Three commands, and the split between them is the whole design.

`plan()` is autonomous and read-only. It does the part that is actually work:
tailoring one product into thirty listings, each cut to that platform's own
limits, ordered by what a link there is worth. It writes a queue as JSON and as
a Markdown checklist, and it never touches a network.

`submit()` acts only on platforms whose own interface is the intended path -
today that is IndexNow, DEV and Hashnode. For everything else it refuses and
prints the copy and the URL instead, which is not a smaller version of the same
thing: it is the difference between a campaign and a domain ban.

`verify()` is autonomous again. It fetches the page a listing should be on and
looks for the link. This is the only honest way to know a submission worked,
because "submitted" and "listed" are different events separated by a human
reviewer, and only one of them is a backlink.

**Truncation is done by the code, never by the model.** The model writes copy;
the code cuts it to the limit on a word boundary and appends nothing. That is
the same rule the rest of this repository runs on, and here it means a form that
silently truncates at 60 characters cannot turn a sentence into a fragment that
ends mid-word in a listing nobody will edit again.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from ...config import (PRODUCT_CATEGORIES, PRODUCT_NAME, PRODUCT_PITCH,
                       PRODUCT_PITCH_SHORT, PRODUCT_TAGLINE,
                       PRODUCT_TAGLINE_SHORT, PRODUCT_URL, STATE_DIR)
from ...logging_setup import get_logger
from .registry import BY_ID, Automation, Cadence, Platform, ranked

log = get_logger("cmo.backlinks")

QUEUE_DIR = STATE_DIR / "cmo"
QUEUE_JSON = QUEUE_DIR / "backlinks.json"
QUEUE_MD = QUEUE_DIR / "backlinks.md"
STATE_PATH = QUEUE_DIR / "backlinks_state.json"


# --------------------------------------------------------------------------- #
# Copy
# --------------------------------------------------------------------------- #
def fit(text: str, limit: int) -> str:
    """Cut to `limit` characters on a word boundary. Never mid-word.

    A form that truncates server-side produces a listing ending in "and where
    they disag", and nobody goes back to edit a directory entry. Cutting here,
    on a boundary, means the worst case is a shorter true sentence.
    """
    text = " ".join(text.split())
    if not limit or len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,.;:-")


def copy_for(platform: Platform) -> dict[str, str | list[str]]:
    """The product, in the shapes this platform's form asks for."""
    out: dict[str, str | list[str]] = {}
    for name, limit in platform.fields.items():
        key = name.lower()
        if key in ("name", "title"):
            # A title field on a link aggregator is a headline, not a brand.
            value = (PRODUCT_NAME if limit and limit <= 40
                     else f"{PRODUCT_NAME} - {PRODUCT_TAGLINE_SHORT}")
        elif "tagline" in key or key == "short_description":
            value = (PRODUCT_TAGLINE_SHORT if limit and limit < 80
                     else PRODUCT_TAGLINE)
        elif "description" in key or key in ("text", "body_markdown",
                                             "contentmarkdown"):
            # A tight field gets the pitch that was written to be that length,
            # not the long one with its last sentence sawn off.
            value = (PRODUCT_PITCH_SHORT if limit and limit < 400
                     else PRODUCT_PITCH)
        elif key in ("topics", "tags"):
            out[name] = list(PRODUCT_CATEGORIES[:limit or 3])
            continue
        else:
            value = PRODUCT_TAGLINE
        out[name] = fit(value, limit)
    return out


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
@dataclass
class Record:
    """What happened with one platform. Append-minded: `verified` only ever
    becomes True on evidence, never on the assumption that submitting worked."""

    platform: str
    submitted_iso: str = ""
    live_url: str = ""
    verified: bool = False
    checked_iso: str = ""
    note: str = ""


def load_state(*, path: Path | None = None) -> dict[str, Record]:
    path = path or STATE_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("backlink state unreadable, starting fresh: %s", exc)
        return {}
    return {k: Record(**v) for k, v in raw.items() if isinstance(v, dict)}


def save_state(state: dict[str, Record], *, path: Path | None = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({k: asdict(v) for k, v in sorted(state.items())}, indent=2),
        encoding="utf-8")


# --------------------------------------------------------------------------- #
# The queue
# --------------------------------------------------------------------------- #
@dataclass
class Item:
    platform: Platform
    copy: dict = field(default_factory=dict)
    record: Record | None = None

    @property
    def done(self) -> bool:
        return bool(self.record and self.record.submitted_iso)

    @property
    def live(self) -> bool:
        return bool(self.record and self.record.verified)


def plan(*, state_path: Path | None = None) -> list[Item]:
    """Everything outstanding, most valuable first. No network, no key."""
    state = load_state(path=state_path)
    items = []
    for platform in ranked():
        items.append(Item(platform=platform,
                          copy=copy_for(platform),
                          record=state.get(platform.id)))
    return items


def write_queue(items: list[Item], *, json_path: Path | None = None,
                md_path: Path | None = None) -> tuple[Path, Path]:
    """Write the queue as data and as something a person can work through."""
    json_path = json_path or QUEUE_JSON
    md_path = md_path or QUEUE_MD
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps({
        "built": datetime.now(timezone.utc).isoformat(),
        "product": {"name": PRODUCT_NAME, "url": PRODUCT_URL},
        "items": [{
            "id": i.platform.id,
            "name": i.platform.name,
            "url": i.platform.submit_url,
            "automation": i.platform.automation.value,
            "cadence": i.platform.cadence.value,
            "value": i.platform.value,
            "copy": i.copy,
            "submitted": bool(i.done),
            "verified": bool(i.live),
        } for i in items],
    }, indent=2), encoding="utf-8")

    md_path.write_text(_markdown(items), encoding="utf-8")
    return json_path, md_path


def _markdown(items: list[Item]) -> str:
    lines = [f"# Backlinks for {PRODUCT_NAME}", "",
             f"Built {date.today().isoformat()}. Highest value first.", ""]

    auto = [i for i in items if i.platform.automatable]
    manual = [i for i in items if i.platform.automation is Automation.MANUAL]
    blocked = [i for i in items if i.platform.automation is Automation.PROHIBITED]

    lines += ["## Runs on its own", "",
              "No account and no person. `python -m headlinne cmo backlinks "
              "submit --target <id>`.", ""]
    for item in auto:
        lines.append(f"- [{'x' if item.done else ' '}] **{item.platform.name}** "
                     f"(`{item.platform.id}`)"
                     + (f" - {item.platform.notes}" if item.platform.notes else ""))
    lines.append("")

    lines += ["## Needs you, and only for the last click", "",
              "The copy below is cut to each form's own limit. Open the link, "
              "paste, submit.", ""]
    for item in manual:
        p = item.platform
        mark = "x" if item.done else " "
        once = " **one-shot**" if p.cadence is Cadence.ONCE else ""
        lines.append(f"### [{mark}] {p.name}{once}  ({'*' * p.value})")
        lines.append("")
        lines.append(f"<{p.submit_url}>")
        lines.append("")
        if p.notes:
            lines.append(f"> {p.notes}")
            lines.append("")
        for key, value in item.copy.items():
            is_list = isinstance(value, list)
            shown = ", ".join(value) if is_list else value
            limit = p.fields.get(key) or 0
            # A list field's limit counts entries, not characters. Printing
            # "36/3" beside three topics reads as a violated limit and sends
            # somebody off to shorten copy that was never too long.
            used = len(value) if is_list else len(shown)
            unit = " topics" if is_list else ""
            size = f" ({used}/{limit}{unit})" if limit else ""
            lines.append(f"**{key}**{size}")
            lines.append("")
            lines.append(f"```\n{shown}\n```")
            lines.append("")
        lines.append("")

    lines += ["## Not to be automated", "",
              "In the registry on purpose. A target that is worth having and "
              "must not be scripted is more useful written down than left for "
              "someone to rediscover.", ""]
    for item in blocked:
        lines.append(f"- **{item.platform.name}** - {item.platform.notes}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #
class RefusedError(RuntimeError):
    """Raised when a target may not be submitted to programmatically."""


def submit(target: str, *, state_path: Path | None = None, session=None,
           dry_run: bool = False) -> str:
    """Submit to one platform. Refuses anything that is not API-automatable.

    The refusal carries the reason and the copy, because the useful response to
    "this one needs a person" is the paste-ready text and the URL, not an error.
    """
    platform = BY_ID.get(target)
    if platform is None:
        raise RefusedError(
            f"unknown target {target!r}. "
            f"Known: {', '.join(sorted(BY_ID))}.")

    if not platform.automatable:
        why = ("its own rules forbid automated submission"
               if platform.automation is Automation.PROHIBITED
               else "submission is a form behind a login, and this system does "
                    "not enter credentials on your behalf")
        raise RefusedError(
            f"{platform.name} will not be submitted to automatically: {why}.\n"
            f"{platform.notes}\n\n"
            f"Open {platform.submit_url} and paste from "
            f"state/cmo/backlinks.md, then record it with:\n"
            f"  python -m headlinne cmo backlinks done --target {platform.id} "
            f"--url <the live listing>")

    if platform.id == "indexnow":
        return _submit_indexnow(session=session, dry_run=dry_run,
                                state_path=state_path)

    raise RefusedError(
        f"{platform.name} is API-automatable but its adapter is not built yet. "
        f"It needs a credential of its own (a DEV API key or a Hashnode token) "
        f"and an article to post, which the story archive does not produce yet.")


def _submit_indexnow(*, session=None, dry_run: bool = False,
                     state_path: Path | None = None) -> str:
    """Ask Bing, Yandex and Seznam to crawl the story archive.

    Not a backlink, and it is here anyway: the archive is the only asset in the
    plan that is still earning in February, and an uncrawled page earns nothing
    at all. One request, no account, no rate limit worth worrying about.
    """
    urls = [PRODUCT_URL]
    if dry_run:
        return f"would ask IndexNow to crawl {len(urls)} URL(s): {urls[0]}"

    # Deliberately not implemented as a live call yet: IndexNow requires a key
    # file served from the site's own root to prove ownership, and the story
    # archive it would point at does not exist. Submitting the homepage alone
    # would spend the integration on the one page search engines already have.
    raise RefusedError(
        "IndexNow needs two things that do not exist yet: a key file served "
        "from headlinne.com/<key>.txt, and pages worth crawling. Build the "
        "story archive first - until then this would ask Bing to re-crawl a "
        "homepage it already has.")


def mark_done(target: str, live_url: str = "", *,
              state_path: Path | None = None) -> str:
    """Record that a human submitted this one. Does not claim it went live."""
    if target not in BY_ID:
        raise RefusedError(f"unknown target {target!r}.")
    state = load_state(path=state_path)
    record = state.get(target) or Record(platform=target)
    record.submitted_iso = datetime.now(timezone.utc).isoformat()
    record.live_url = live_url or record.live_url
    # Submitting is not being listed. Most of these go through a human reviewer,
    # and only `verify` may set this.
    record.verified = False
    state[target] = record
    save_state(state, path=state_path)
    return (f"recorded {BY_ID[target].name} as submitted"
            + (f" ({live_url})" if live_url else "")
            + ". Run `backlinks verify` once it has been reviewed.")


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def verify(*, state_path: Path | None = None, session=None) -> list[Record]:
    """Fetch each recorded listing and check the link is actually on it.

    "Submitted" and "listed" are different events with a human reviewer in
    between, and only one of them is a backlink. A campaign that counts the
    first as the second reports a link profile it does not have.
    """
    state = load_state(path=state_path)
    checked = []
    for target, record in sorted(state.items()):
        if not record.live_url:
            continue
        record.verified = _link_is_on(record.live_url, session=session)
        record.checked_iso = datetime.now(timezone.utc).isoformat()
        if not record.verified:
            record.note = "the listing page does not mention headlinne.com"
        checked.append(record)
    if checked:
        save_state(state, path=state_path)
    return checked


def _link_is_on(url: str, *, session=None) -> bool:
    try:
        if session is None:
            import requests

            session = requests
        resp = session.get(url, timeout=15, headers={
            "User-Agent": "HeadlinneBot/1.0 (+https://headlinne.com; "
                          "link verification)"})
        resp.raise_for_status()
        return "headlinne.com" in resp.text.lower()
    except Exception as exc:  # noqa: BLE001 - unreachable is unverified
        log.warning("could not verify %s: %s", url, exc)
        return False
