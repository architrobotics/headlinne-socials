"""The brief, and the guarantee that the layer can fail without taking the day.

The seam between the growth layer and the content factory is one optional file.
That is only safe if a missing, malformed or refused brief produces exactly the
day the pipeline would have had anyway, so most of this file tests absence
rather than presence.

The other property worth pinning: a brief may only ask for what policy already
permits. An instruction that the pipeline is not allowed to carry out should
never reach the file - it should be dropped at assembly with its reason kept.
"""

from __future__ import annotations

import json
from datetime import date

from headlinne.cmo import brief as brief_mod
from headlinne.cmo import ledger, review
from headlinne.cmo.metrics import Snapshot

DAY = date(2026, 9, 14)


def _ledger(tmp_path, rows):
    path = tmp_path / "ledger.jsonl"
    for day, users, mau in rows:
        ledger.append(Snapshot(day=date.fromisoformat(day), users=users,
                               dau=0, mau=mau), path=path)
    return path


# --------------------------------------------------------------------------- #
# A missing brief changes nothing
# --------------------------------------------------------------------------- #
def test_no_brief_reads_as_none_rather_than_an_empty_instruction(tmp_path):
    """None means 'run the standing mix'. An empty Brief would mean 'make
    nothing today', which is the same value with the opposite meaning."""
    assert brief_mod.read(DAY, root=tmp_path) is None


def test_a_malformed_brief_is_ignored_rather_than_raised(tmp_path):
    path = brief_mod.path_for(DAY, root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json at all", encoding="utf-8")
    assert brief_mod.read(DAY, root=tmp_path) is None


def test_a_brief_from_a_future_schema_is_ignored_rather_than_raised(tmp_path):
    """A field this version does not know about must not take the daily run
    down. The worst outcome of a broken brief is a normal day."""
    path = brief_mod.path_for(DAY, root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"day": DAY.isoformat(), "invented": True}),
                    encoding="utf-8")
    assert brief_mod.read(DAY, root=tmp_path) is None


def test_the_pipeline_helper_swallows_everything(tmp_path):
    """`pipeline._todays_brief` is the actual seam, and it must never raise."""
    from headlinne import pipeline

    assert pipeline._todays_brief(date(1999, 1, 1)) is None


# --------------------------------------------------------------------------- #
# What the brief decides
# --------------------------------------------------------------------------- #
def test_a_brief_with_no_reading_says_so_instead_of_inventing_a_pace(tmp_path):
    built = brief_mod.build(DAY, ledger_path=tmp_path / "empty.jsonl",
                            experiments_path=tmp_path / "e.json")
    assert built.verdict == "unreadable"
    assert built.required_per_day is None
    assert "never been read" in built.reason
    assert "nothing here is evidence-based" in built.reason.lower()


def test_falling_behind_changes_which_story_leads(tmp_path):
    """The bias change is earned by the pace verdict, not by a feeling."""
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-11-01", 1000, 500)])
    built = brief_mod.build(date(2026, 11, 1), ledger_path=path,
                            experiments_path=tmp_path / "e.json")
    assert built.verdict in ("behind", "off_track")
    assert built.story_bias == brief_mod.BEHIND_BIAS
    assert built.story_bias in built.reason


def test_a_healthy_pace_leaves_the_day_leading_on_interest(tmp_path):
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-09-14", 1400, 800)])
    built = brief_mod.build(DAY, ledger_path=path,
                            experiments_path=tmp_path / "e.json")
    assert built.verdict == "ahead"
    assert built.story_bias == "interest"


def test_the_brief_only_tags_the_slots_that_can_carry_a_link(tmp_path):
    built = brief_mod.build(DAY, ledger_path=tmp_path / "l.jsonl",
                            experiments_path=tmp_path / "e.json")
    assert set(built.links) == {"x_1", "x_2", "linkedin"}
    assert set(built.blind_slots) == {"reel_1", "instagram_1", "story_card"}
    assert built.attribution_share == 0.5


def test_every_instruction_carries_its_evidence(tmp_path):
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-09-14", 300, 150)])
    built = brief_mod.build(DAY, ledger_path=path,
                            experiments_path=tmp_path / "e.json")
    assert built.reason
    assert built.evidence.startswith("ledger://")
    assert "2026-09-01" in built.evidence


def test_the_reason_quotes_only_numbers_that_came_from_the_ledger(tmp_path):
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-09-14", 300, 150)])
    built = brief_mod.build(DAY, ledger_path=path,
                            experiments_path=tmp_path / "e.json")
    assert "300 users" in built.reason


# --------------------------------------------------------------------------- #
# Policy is applied while the brief is assembled, not after
# --------------------------------------------------------------------------- #
def test_a_refused_instruction_never_reaches_the_file(tmp_path, monkeypatch=None):
    from headlinne.cmo import policy

    real = policy.check

    def deny_links(action, **kwargs):
        if action == "mint_link":
            return policy.Decision(action, policy.Rung.RED, False,
                                   "minting is switched off for this test")
        return real(action, **kwargs)

    policy.check = deny_links
    try:
        built = brief_mod.build(DAY, ledger_path=tmp_path / "l.jsonl",
                                experiments_path=tmp_path / "e.json")
    finally:
        policy.check = real

    assert built.links == {}
    assert any("mint_link" in r for r in built.refused)


# --------------------------------------------------------------------------- #
# Round trip
# --------------------------------------------------------------------------- #
def test_a_written_brief_reads_back_identically(tmp_path):
    built = brief_mod.build(DAY, ledger_path=tmp_path / "l.jsonl",
                            experiments_path=tmp_path / "e.json")
    brief_mod.write(built, root=tmp_path)
    back = brief_mod.read(DAY, root=tmp_path)
    assert back is not None
    assert back.links == built.links
    assert back.story_bias == built.story_bias
    assert back.link_for("x_1") == built.link_for("x_1")
    assert back.link_for("reel_1") is None


def test_the_printed_brief_names_what_cannot_be_tagged(tmp_path):
    built = brief_mod.build(DAY, ledger_path=tmp_path / "l.jsonl",
                            experiments_path=tmp_path / "e.json")
    text = brief_mod.format_brief(built)
    assert "Cannot be tagged" in text
    assert "reel_1" in text


# --------------------------------------------------------------------------- #
# The review, and the escalation that has to arrive early
# --------------------------------------------------------------------------- #
def test_a_review_with_no_readings_escalates_immediately(tmp_path):
    current = review.build(DAY, ledger_path=tmp_path / "l.jsonl",
                           experiments_path=tmp_path / "e.json",
                           decisions_path=tmp_path / "d.jsonl")
    problems = review.escalation(current)
    assert problems
    assert "guess wearing a number" in problems[0]


def test_a_long_blind_campaign_escalates_even_when_nothing_looks_wrong(tmp_path):
    """The failure that never announces itself. A channel with no link surface
    produces no bad numbers because it produces none at all."""
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-10-15", 3000, 1800)])
    current = review.build(date(2026, 10, 15), ledger_path=path,
                           experiments_path=tmp_path / "e.json",
                           decisions_path=tmp_path / "d.jsonl")
    assert current.pace.verdict in ("ahead", "slipping")   # nothing looks wrong
    problems = review.escalation(current)
    assert any("cannot be observed" in p for p in problems)
    assert any("allocation cannot improve" in p for p in problems)


def test_a_young_campaign_is_not_nagged_about_attribution_yet(tmp_path):
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-09-05", 200, 120)])
    current = review.build(date(2026, 9, 5), ledger_path=path,
                           experiments_path=tmp_path / "e.json",
                           decisions_path=tmp_path / "d.jsonl")
    assert not any("cannot be observed" in p for p in review.escalation(current))


def test_the_review_reports_the_amber_actions_it_took(tmp_path):
    from headlinne.cmo import policy

    decisions = tmp_path / "d.jsonl"
    policy.record(policy.check("publish_new_surface"), "first YouTube Short",
                  day=DAY, path=decisions)
    path = _ledger(tmp_path, [("2026-09-01", 100, 60), ("2026-09-14", 300, 150)])
    current = review.build(DAY, ledger_path=path,
                           experiments_path=tmp_path / "e.json",
                           decisions_path=decisions)
    text = review.format_review(current)
    assert "Acted, and telling you now" in text
    assert "first YouTube Short" in text
