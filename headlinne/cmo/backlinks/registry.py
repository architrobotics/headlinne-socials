"""Where Headlinne can be listed, and what each place actually permits.

A backlink campaign is mostly clerical: the same product described thirty times
in thirty different shapes, each with its own length limit, its own category
vocabulary and its own rule about what counts as spam. The writing and the
tailoring are the work, and they are entirely automatable. The submitting mostly
is not, and this file is where that distinction is recorded honestly, per
platform, rather than discovered one ban at a time.

`Automation` is the field that matters, and it has three values:

  API        the platform publishes an interface for creating a post or entry,
             and using it is the intended path. These are submitted by
             `backlinks submit` with no human in the loop.
  MANUAL     submission is a web form behind a login. Not forbidden, just not
             reachable without credentials, and entering credentials on
             somebody's behalf is not something this system does. The queue
             produces paste-ready copy and the exact URL to paste it into.
  PROHIBITED the platform's own rules forbid automated or bulk submission.
             These are in the registry deliberately rather than omitted,
             because a target that is worth having and must not be automated is
             more useful written down than left for someone to rediscover.

**Why the manual ones are not worth forcing.** Hacker News and Reddit both ban
at the *domain* level, not the account level, and both treat automated
submission as the thing they ban for. A domain ban would take headlinne.com out
of the one channel that compounds - the story archive, which is the only asset
in the plan still earning in February. Trading that for a few hours of clerical
work is a bad trade at any deadline, and it is not reversible by apologising.

**One-shot targets are spent, not earned.** Show HN and a Product Hunt launch
work once. Firing them on a Tuesday because a queue said so wastes the single
best distribution moment the product gets. `cadence == ONCE` marks these, and
the queue puts them behind an explicit readiness question rather than a date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Automation(str, Enum):
    API = "api"
    MANUAL = "manual"
    PROHIBITED = "prohibited"


class Cadence(str, Enum):
    ONCE = "once"              # a launch. Spent, not earned.
    RECURRING = "recurring"    # can carry a new item repeatedly


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    submit_url: str
    automation: Automation
    cadence: Cadence
    # Roughly how much a live link there is worth, 1 (a directory nobody reads)
    # to 5 (a front page that sends real traffic). Judgement, not a measurement,
    # and it is only ever used to order the queue - never to claim a result.
    value: int
    # The copy fields this platform asks for, and their limits. This is what
    # lets one product description become thirty tailored ones.
    fields: dict[str, int] = field(default_factory=dict)
    account: bool = True
    notes: str = ""

    @property
    def automatable(self) -> bool:
        return self.automation is Automation.API


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
PLATFORMS: tuple[Platform, ...] = (
    # ---- Fully automatable. No account, no human, official interface. ----
    Platform(
        "indexnow", "IndexNow (Bing, Yandex, Seznam)",
        "https://api.indexnow.org/indexnow",
        Automation.API, Cadence.RECURRING, value=4,
        account=False,
        notes="Not a backlink - a crawl request. It is in this registry because "
              "the story archive is the campaign's only compounding asset and "
              "an unindexed page earns nothing. Costs one request per URL and "
              "is the single most automatable thing in the plan."),
    Platform(
        "devto", "DEV Community",
        "https://dev.to/api/articles",
        Automation.API, Cadence.RECURRING, value=3,
        fields={"title": 128, "body_markdown": 0, "tags": 4},
        notes="An API key creates articles directly, which is the intended use. "
              "Always set canonical_url back to headlinne.com: that is what "
              "makes a cross-post a citation rather than a duplicate competing "
              "with the original in search."),
    Platform(
        "hashnode", "Hashnode",
        "https://gql.hashnode.com/",
        Automation.API, Cadence.RECURRING, value=3,
        fields={"title": 250, "contentMarkdown": 0, "tags": 5},
        notes="GraphQL publish mutation with a personal access token. Same "
              "canonical rule as DEV."),

    # ---- One-shot launches. Worth a great deal, and spendable exactly once. --
    Platform(
        "producthunt", "Product Hunt",
        "https://www.producthunt.com/posts/new",
        Automation.MANUAL, Cadence.ONCE, value=5,
        fields={"name": 40, "tagline": 60, "description": 260, "topics": 3},
        notes="A launch, not a listing. Needs a maker account, a launch day, "
              "and someone awake to answer comments for twelve hours. The API "
              "can read posts but a launch is not something to fire from cron."),
    Platform(
        "showhn", "Hacker News (Show HN)",
        "https://news.ycombinator.com/submit",
        Automation.PROHIBITED, Cadence.ONCE, value=5,
        fields={"title": 80, "text": 2000},
        notes="Guidelines: one Show HN per project, it must be something people "
              "can try, and the title takes no marketing language. Automated "
              "submission is against the rules and HN bans by domain. This is "
              "the highest-value single link available and the one most worth "
              "not rushing."),
    Platform(
        "betalist", "BetaList",
        "https://betalist.com/submit",
        Automation.MANUAL, Cadence.ONCE, value=3,
        fields={"name": 40, "tagline": 90, "description": 600},
        notes="For products still early. Reviewed by a human before listing."),

    # ---- Company and product profiles. Created once, updated after. ----
    Platform(
        "crunchbase", "Crunchbase",
        "https://www.crunchbase.com/register",
        Automation.MANUAL, Cadence.ONCE, value=4,
        fields={"name": 80, "short_description": 220, "description": 2000},
        notes="Creating or claiming the profile needs an account and identity "
              "verification, which is a founder action. Once it exists the "
              "profile is worth revisiting when anything real changes."),
    Platform(
        "alternativeto", "AlternativeTo",
        "https://alternativeto.net/manage/add-app/",
        Automation.MANUAL, Cadence.ONCE, value=4,
        fields={"name": 60, "tagline": 120, "description": 1000},
        notes="High intent: people arrive already looking for a replacement for "
              "something. Listing against Google News, Artifact and Feedly is "
              "worth more than the raw authority number suggests."),
    Platform(
        "saashub", "SaaSHub",
        "https://www.saashub.com/submit",
        Automation.MANUAL, Cadence.ONCE, value=2,
        fields={"name": 60, "tagline": 120, "description": 800}),
    Platform(
        "indiehackers", "Indie Hackers",
        "https://www.indiehackers.com/products/new",
        Automation.MANUAL, Cadence.ONCE, value=3,
        fields={"name": 60, "tagline": 120, "description": 1000},
        notes="The product page is the link. The forum is a separate thing and "
              "is governed by the same rule as Reddit: contribute first."),
    Platform(
        "startupstash", "Startup Stash",
        "https://startupstash.com/add-listing/",
        Automation.MANUAL, Cadence.ONCE, value=2,
        fields={"name": 60, "tagline": 120, "description": 600}),
    Platform(
        "sideprojectors", "SideProjectors",
        "https://www.sideprojectors.com/project/submit",
        Automation.MANUAL, Cadence.ONCE, value=1,
        fields={"name": 60, "tagline": 120, "description": 600}),
    Platform(
        "f6s", "F6S",
        "https://www.f6s.com/company/signup",
        Automation.MANUAL, Cadence.ONCE, value=2,
        fields={"name": 80, "tagline": 140, "description": 1500}),
    Platform(
        "producthuntship", "Product Hunt Ship / upcoming pages",
        "https://www.producthunt.com/ship",
        Automation.MANUAL, Cadence.ONCE, value=2,
        fields={"name": 40, "tagline": 60, "description": 260},
        notes="Collects an email list before the launch, which is the asset the "
              "launch itself mostly fails to keep."),

    # ---- Communities. Recurring, and the ones where restraint is the tactic. -
    Platform(
        "reddit", "Reddit",
        "https://www.reddit.com/",
        Automation.PROHIBITED, Cadence.RECURRING, value=4,
        notes="Already built, deliberately, as a human-reviewed opportunity "
              "finder rather than a poster: `headlinne reddit find`, then "
              "`headlinne reddit post --id <id> --confirm`. Unattended "
              "promotional posting gets the account and the domain "
              "sitewide-banned, and the domain is the part that matters."),
    Platform(
        "lobsters", "Lobsters",
        "https://lobste.rs/stories/new",
        Automation.PROHIBITED, Cadence.RECURRING, value=3,
        notes="Invite-only, and self-promotion is capped by its own rules. A "
              "link here is earned by being a member, not by submitting."),
    Platform(
        "quora", "Quora",
        "https://www.quora.com/",
        Automation.MANUAL, Cadence.RECURRING, value=2,
        notes="Answers to 'best news app' style questions rank in search for "
              "years. Slow, and the same 9:1 rule as Reddit applies."),

    # ---- Editorial. Listed so nobody proposes them again. ----
    Platform(
        "wikipedia", "Wikipedia / Wikidata",
        "https://en.wikipedia.org/",
        Automation.PROHIBITED, Cadence.ONCE, value=5,
        account=False,
        notes="Here to be refused, not attempted. Adding your own product is "
              "against the conflict-of-interest policy, the links are nofollow "
              "anyway, and being caught doing it is a lasting reputational "
              "problem that no amount of traffic pays for."),
)

BY_ID = {p.id: p for p in PLATFORMS}


def automatable() -> list[Platform]:
    """Targets `backlinks submit` may act on without a human."""
    return [p for p in PLATFORMS if p.automatable]


def needs_a_person() -> list[Platform]:
    """Targets that produce paste-ready copy and a link, and nothing more."""
    return [p for p in PLATFORMS if p.automation is Automation.MANUAL]


def ranked() -> list[Platform]:
    """Highest value first, and within a value, the automatable ones first.

    Ordering by what a link is worth rather than by how easy it is to get is
    deliberate. A queue sorted by convenience finishes with eleven directory
    listings nobody visits and the two links that mattered still undone.
    """
    return sorted(PLATFORMS,
                  key=lambda p: (-p.value, not p.automatable, p.name.lower()))
