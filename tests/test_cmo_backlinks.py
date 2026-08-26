"""What the backlink campaign may do on its own, and what it must not.

The valuable tests here are the refusals. Copy that is one character too long
gets rejected by a form and someone fixes it in a minute; a submission bot
pointed at Hacker News gets headlinne.com banned at the domain level, which
takes out the story archive - the only asset in the plan still earning after
January. So the properties worth pinning are that `submit` cannot be talked into
acting on a platform that forbids it, and that submitting is never recorded as
being listed.
"""

from __future__ import annotations

import json

from headlinne.cmo import backlinks
from headlinne.cmo.backlinks import pipeline, registry
from headlinne.cmo.backlinks.registry import Automation, Cadence


# --------------------------------------------------------------------------- #
# The registry is honest about itself
# --------------------------------------------------------------------------- #
def test_every_platform_declares_how_it_may_be_reached():
    for p in registry.PLATFORMS:
        assert isinstance(p.automation, Automation)
        assert isinstance(p.cadence, Cadence)
        assert p.submit_url.startswith("https://")
        assert 1 <= p.value <= 5


def test_platform_ids_are_unique():
    ids = [p.id for p in registry.PLATFORMS]
    assert len(ids) == len(set(ids))


def test_the_queue_is_ordered_by_what_a_link_is_worth():
    """Not by how easy it is to get. A queue sorted by convenience finishes
    with eleven directory listings nobody visits and the two that mattered
    still undone."""
    values = [p.value for p in registry.ranked()]
    assert values == sorted(values, reverse=True)


def test_the_platforms_that_ban_by_domain_are_marked_prohibited():
    """Hacker News, Reddit and Lobsters all ban the domain rather than the
    account, and all three treat automated submission as the thing they ban
    for. Marking one of these automatable would be the expensive mistake."""
    for target in ("showhn", "reddit", "lobsters", "wikipedia"):
        assert registry.BY_ID[target].automation is Automation.PROHIBITED


def test_reddit_points_at_the_reviewed_tool_that_already_exists():
    assert "reddit find" in registry.BY_ID["reddit"].notes
    assert "--confirm" in registry.BY_ID["reddit"].notes


def test_the_one_shot_launches_are_marked_as_spendable_once():
    for target in ("showhn", "producthunt", "betalist"):
        assert registry.BY_ID[target].cadence is Cadence.ONCE


# --------------------------------------------------------------------------- #
# Submission refuses everything it has not been permitted
# --------------------------------------------------------------------------- #
def test_submitting_to_a_prohibited_platform_is_refused_with_the_reason():
    try:
        backlinks.submit("showhn")
    except backlinks.RefusedError as exc:
        message = str(exc)
        assert "forbid automated submission" in message
        assert "news.ycombinator.com/submit" in message   # the manual path
        assert "backlinks done --target showhn" in message
    else:
        raise AssertionError("Show HN was submitted to automatically")


def test_submitting_to_a_login_only_platform_is_refused_without_credentials():
    try:
        backlinks.submit("crunchbase")
    except backlinks.RefusedError as exc:
        assert "does not enter credentials" in str(exc)
    else:
        raise AssertionError("a credentialed form was submitted")


def test_every_non_api_platform_is_refused():
    """The guarantee is the whole set, not the two examples above."""
    for p in registry.PLATFORMS:
        if p.automatable:
            continue
        try:
            backlinks.submit(p.id)
        except backlinks.RefusedError:
            continue
        raise AssertionError(f"{p.id} was submitted to automatically")


def test_an_unknown_target_is_refused_rather_than_guessed_at():
    try:
        backlinks.submit("producthunnt")          # a typo
    except backlinks.RefusedError as exc:
        assert "unknown target" in str(exc)
    else:
        raise AssertionError("a typo was treated as a platform")


def test_indexnow_refuses_until_there_are_pages_worth_crawling(tmp_path):
    """It is API-automatable and still declines, because asking Bing to
    re-crawl a homepage it already has spends the integration on nothing."""
    try:
        backlinks.submit("indexnow", state_path=tmp_path / "s.json")
    except backlinks.RefusedError as exc:
        assert "key file" in str(exc) and "story archive" in str(exc)
    else:
        raise AssertionError("IndexNow submitted with nothing to submit")


def test_a_dry_run_sends_nothing_and_says_so(tmp_path):
    out = backlinks.submit("indexnow", dry_run=True,
                           state_path=tmp_path / "s.json")
    assert out.startswith("would ask")


# --------------------------------------------------------------------------- #
# Submitted is not listed
# --------------------------------------------------------------------------- #
def test_marking_one_done_does_not_mark_it_verified(tmp_path):
    """A human reviewer sits between submitting and being listed, and only one
    of those two events is a backlink."""
    path = tmp_path / "state.json"
    backlinks.mark_done("betalist", "https://betalist.com/startups/headlinne",
                        state_path=path)
    state = pipeline.load_state(path=path)
    assert state["betalist"].submitted_iso
    assert state["betalist"].verified is False


def test_verification_needs_the_link_to_actually_be_on_the_page(tmp_path):
    class _Page:
        def __init__(self, body):
            self.body, self.status_code = body, 200

        def raise_for_status(self):
            pass

        @property
        def text(self):
            return self.body

    class _Session:
        def __init__(self, body):
            self.body = body

        def get(self, url, **kwargs):
            return _Page(self.body)

    path = tmp_path / "state.json"
    backlinks.mark_done("betalist", "https://betalist.com/x", state_path=path)

    missing = backlinks.verify(state_path=path,
                               session=_Session("<html>some other startup</html>"))
    assert missing[0].verified is False
    assert "does not mention" in missing[0].note

    found = backlinks.verify(
        state_path=path,
        session=_Session('<a href="https://headlinne.com">Headlinne</a>'))
    assert found[0].verified is True


def test_an_unreachable_listing_is_unverified_rather_than_an_error(tmp_path):
    class _Down:
        def get(self, *a, **k):
            raise ConnectionError("timed out")

    path = tmp_path / "state.json"
    backlinks.mark_done("saashub", "https://www.saashub.com/headlinne",
                        state_path=path)
    checked = backlinks.verify(state_path=path, session=_Down())
    assert checked[0].verified is False


def test_nothing_is_verified_before_a_live_url_is_recorded(tmp_path):
    path = tmp_path / "state.json"
    backlinks.mark_done("saashub", state_path=path)      # submitted, no URL yet
    assert backlinks.verify(state_path=path) == []


# --------------------------------------------------------------------------- #
# The copy fits the form
# --------------------------------------------------------------------------- #
def test_every_field_is_within_the_limit_the_form_actually_enforces():
    for p in registry.PLATFORMS:
        copy = pipeline.copy_for(p)
        for name, limit in p.fields.items():
            if not limit:
                continue
            value = copy[name]
            used = len(value) if isinstance(value, list) else len(value)
            assert used <= limit, f"{p.id}.{name} is {used} of {limit}"


def test_copy_is_cut_on_a_word_boundary_and_never_mid_word():
    out = pipeline.fit("where the outlets disagree about it", 20)
    assert out == "where the outlets"
    assert not out.endswith(" ")


def test_a_tight_description_field_gets_a_pitch_written_to_be_that_short():
    """Truncating the long pitch to 260 characters ends it mid-argument, and a
    directory listing is not something anyone goes back to edit."""
    tight = pipeline.copy_for(registry.BY_ID["producthunt"])["description"]
    roomy = pipeline.copy_for(registry.BY_ID["crunchbase"])["description"]
    assert tight != roomy
    assert tight.endswith(".")            # a complete thought, not a fragment
    assert len(tight) <= 260


def test_the_pitch_leads_with_the_mechanism_not_the_category():
    """"A personalised AI news app" describes forty products and is worth
    nothing in a directory that already lists all forty."""
    pitch = pipeline.copy_for(registry.BY_ID["crunchbase"])["description"].lower()
    assert "agree" in pitch or "outlet" in pitch


# --------------------------------------------------------------------------- #
# The queue a person actually works through
# --------------------------------------------------------------------------- #
def test_the_queue_writes_both_a_checklist_and_machine_readable_data(tmp_path):
    items = backlinks.plan(state_path=tmp_path / "state.json")
    json_path, md_path = backlinks.write_queue(
        items, json_path=tmp_path / "q.json", md_path=tmp_path / "q.md")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["items"]) == len(registry.PLATFORMS)
    assert data["product"]["url"] == "https://headlinne.com"

    md = md_path.read_text(encoding="utf-8")
    assert "Runs on its own" in md
    assert "Not to be automated" in md
    # The prohibited ones appear with their reason rather than being hidden.
    assert "Hacker News" in md and "bans by domain" in md
    # Every manual target carries the URL to paste into.
    assert "https://www.producthunt.com/posts/new" in md


def test_a_submitted_target_shows_as_done_in_the_next_plan(tmp_path):
    path = tmp_path / "state.json"
    backlinks.mark_done("saashub", state_path=path)
    items = {i.platform.id: i for i in backlinks.plan(state_path=path)}
    assert items["saashub"].done is True
    assert items["saashub"].live is False
    assert items["betalist"].done is False
