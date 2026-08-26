"""The autonomy ladder, and the things no flag can turn on.

The valuable tests here are about refusal, and about one property that is easy
to get backwards: an action nobody has classified must be **refused**, not
permitted. A policy that defaults to yes means every capability added later
arrives with full autonomy by accident, which is the exact opposite of what a
policy module is for.
"""

from __future__ import annotations

import json
from datetime import date

from headlinne.cmo import policy
from headlinne.cmo.policy import Rung


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #
def test_reversible_work_happens_without_asking():
    for action in ("choose_story", "choose_format", "write_copy", "mint_link",
                   "cross_post", "reallocate_effort", "assign_experiment"):
        decision = policy.check(action)
        assert decision.allowed and decision.rung is Rung.GREEN, action
        assert decision.announce is False


def test_consequential_work_happens_and_is_announced():
    decision = policy.check("publish_new_surface")
    assert decision.allowed is True
    assert decision.rung is Rung.AMBER
    assert decision.announce is True


def test_money_is_refused_rather_than_capped_at_zero():
    """A cap of zero invites someone to raise the cap. A refusal invites a
    conversation, which is the correct outcome when the answer is 'no budget'."""
    decision = policy.check("spend")
    assert decision.allowed is False
    assert decision.rung is Rung.RED
    assert "no budget" in decision.why


def test_the_things_that_cannot_be_undone_are_refused():
    for action in ("create_account", "enter_credentials", "speak_as_founder",
                   "direct_message", "change_positioning", "automate_prohibited",
                   "buy_engagement", "incentivise_signup"):
        decision = policy.check(action)
        assert decision.allowed is False, action
        assert decision.rung is Rung.RED, action


def test_gaming_the_metric_is_refused_even_though_it_would_work():
    """Bought engagement and incentivised signups both move the number this is
    judged on. They are refused because moving the number is not the goal."""
    assert policy.check("buy_engagement").allowed is False
    incentive = policy.check("incentivise_signup")
    assert incentive.allowed is False
    assert "may not be counted" in incentive.why


def test_an_unclassified_action_is_refused_not_assumed_harmless():
    decision = policy.check("launch_the_missiles")
    assert decision.allowed is False
    assert decision.rung is Rung.RED
    assert "not in the policy" in decision.why


def test_no_red_action_carries_a_cap_that_could_be_raised():
    """A red action with a cap would be an amber action wearing a warning label,
    and someone would eventually raise the cap."""
    for action in policy.ACTIONS.values():
        if action.rung is Rung.RED:
            assert action.cap == 0, action.name


def test_every_amber_action_has_a_real_cap():
    for action in policy.ACTIONS.values():
        if action.rung is Rung.AMBER:
            assert action.cap >= 1, action.name


# --------------------------------------------------------------------------- #
# Caps
# --------------------------------------------------------------------------- #
def test_an_amber_action_stops_at_its_cap():
    cap = policy.ACTIONS["submit_listing"].cap
    assert policy.check("submit_listing", done_today=cap - 1).allowed is True
    denied = policy.check("submit_listing", done_today=cap)
    assert denied.allowed is False
    assert "capped at" in denied.why


def test_require_raises_where_check_only_reports():
    policy.require("write_copy")            # must not raise
    try:
        policy.require("spend")
    except policy.Denied as exc:
        assert "no budget" in str(exc)
    else:
        raise AssertionError("spend was permitted")


# --------------------------------------------------------------------------- #
# "Acts, then announces" is only true if it is written down
# --------------------------------------------------------------------------- #
def test_an_amber_action_is_recorded_at_the_moment_it_is_taken(tmp_path):
    path = tmp_path / "decisions.jsonl"
    decision = policy.check("publish_new_surface")
    policy.record(decision, "first post to YouTube Shorts", path=path)

    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["action"] == "publish_new_surface"
    assert rows[0]["detail"] == "first post to YouTube Shorts"
    assert rows[0]["at"] and rows[0]["day"]


def test_green_work_is_not_announced_because_nobody_needs_telling(tmp_path):
    path = tmp_path / "decisions.jsonl"
    policy.record(policy.check("write_copy"), "today's captions", path=path)
    assert not path.exists()


def test_the_record_is_append_only(tmp_path):
    path = tmp_path / "decisions.jsonl"
    policy.record(policy.check("change_cadence"), "one", path=path)
    first = path.read_text(encoding="utf-8")
    policy.record(policy.check("retire_channel"), "two", path=path)
    after = path.read_text(encoding="utf-8")
    assert after.startswith(first)
    assert len(after.splitlines()) == 2


def test_decisions_can_be_read_back_for_the_week(tmp_path):
    path = tmp_path / "decisions.jsonl"
    policy.record(policy.check("change_cadence"), "today", path=path)
    assert len(policy.decisions(path=path)) == 1
    assert policy.decisions(date(2099, 1, 1), path=path) == []


def test_a_corrupt_line_does_not_lose_the_log(tmp_path):
    path = tmp_path / "decisions.jsonl"
    policy.record(policy.check("change_cadence"), "good", path=path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"action": "half-writ\n')
    policy.record(policy.check("retire_channel"), "also good", path=path)
    assert len(policy.decisions(path=path)) == 2
