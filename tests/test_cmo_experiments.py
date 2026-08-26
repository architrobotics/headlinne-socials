"""Stop rules fixed in advance, and the refusal to call a test early.

Every test here defends one property: the terms of an experiment are decided
before the numbers arrive and cannot be revised after. An experiment whose
stopping point moves is a search for a flattering week wearing the vocabulary of
science, and it is exactly what an agent under a deadline would produce if the
register let it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from headlinne.cmo import experiments
from headlinne.cmo.experiments import ExperimentError

START = date(2026, 9, 1)


def _register(tmp_path, **kwargs):
    kwargs.setdefault("hypothesis", "a question-form CTA converts better")
    kwargs.setdefault("slot", "linkedin")
    kwargs.setdefault("arms", ["control", "question"])
    kwargs.setdefault("today", START)
    kwargs.setdefault("runs_for_days", 21)
    return experiments.register(path=tmp_path / "e.json", **kwargs)


# --------------------------------------------------------------------------- #
# Registration fixes the terms
# --------------------------------------------------------------------------- #
def test_registering_seals_the_terms(tmp_path):
    exp = _register(tmp_path)
    assert exp.seal and exp.sealed
    assert exp.control == "control"
    assert exp.ends_on() == START + timedelta(days=21)


def test_editing_the_record_afterwards_breaks_the_seal(tmp_path):
    """The whole point. A stop rule that can be shortened once the numbers look
    good is not a stop rule."""
    path = tmp_path / "e.json"
    _register(tmp_path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["experiments"][0]["minimum"] = 1          # "it is obviously winning"
    path.write_text(json.dumps(raw), encoding="utf-8")

    register = experiments.load(path=path)
    tampered = register.tampered()
    assert len(tampered) == 1
    assert tampered[0].sealed is False
    # A broken seal takes the experiment out of the live set entirely.
    assert register.live() == []


def test_a_tampered_experiment_will_not_be_called(tmp_path):
    path = tmp_path / "e.json"
    exp = _register(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["experiments"][0]["runs_for_days"] = 1
    path.write_text(json.dumps(raw), encoding="utf-8")

    try:
        experiments.decide(exp.id, {"control": 1, "question": 99},
                           today=START + timedelta(days=40), path=path)
    except ExperimentError as exc:
        assert "edited since it was registered" in str(exc)
    else:
        raise AssertionError("a tampered experiment was called")


def test_two_experiments_cannot_run_on_one_surface(tmp_path):
    """Every post would carry both changes, so neither result could be read."""
    _register(tmp_path)
    try:
        _register(tmp_path, hypothesis="shorter posts do better")
    except ExperimentError as exc:
        assert "already running" in str(exc)
    else:
        raise AssertionError("a second experiment started on a busy slot")


def test_an_experiment_needs_at_least_two_arms(tmp_path):
    try:
        _register(tmp_path, arms=["control"])
    except ExperimentError as exc:
        assert "at least two arms" in str(exc)
    else:
        raise AssertionError("a one-armed experiment was registered")


def test_duplicate_arm_names_are_refused(tmp_path):
    try:
        _register(tmp_path, arms=["a", "a"])
    except ExperimentError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate arms were registered")


# --------------------------------------------------------------------------- #
# Assignment is deterministic, never random
# --------------------------------------------------------------------------- #
def test_the_same_day_always_gets_the_same_arm(tmp_path):
    """A regenerated day must not switch arms mid-flight, and the whole history
    has to be recomputable from the committed record."""
    exp = _register(tmp_path)
    day = START + timedelta(days=5)
    assert exp.arm_for(day) == exp.arm_for(day)

    reloaded = experiments.load(path=tmp_path / "e.json").get(exp.id)
    assert reloaded.arm_for(day) == exp.arm_for(day)


def test_arms_are_actually_split_rather_than_all_going_one_way(tmp_path):
    exp = _register(tmp_path)
    counts = exp.assignments(START + timedelta(days=21))
    assert all(n > 0 for n in counts.values())
    assert sum(counts.values()) == 22          # inclusive of both ends


def test_assign_returns_nothing_when_no_experiment_is_running(tmp_path):
    assert experiments.assign(START, "x_1", path=tmp_path / "e.json") == ("", "")


def test_assign_returns_nothing_once_the_window_has_passed(tmp_path):
    _register(tmp_path)
    after = START + timedelta(days=99)
    assert experiments.assign(after, "linkedin", path=tmp_path / "e.json") == ("", "")


def test_assign_gives_the_experiment_and_the_arm_while_it_runs(tmp_path):
    exp = _register(tmp_path)
    exp_id, arm = experiments.assign(START + timedelta(days=3), "linkedin",
                                     path=tmp_path / "e.json")
    assert exp_id == exp.id
    assert arm in exp.arms


# --------------------------------------------------------------------------- #
# Calling it early is refused
# --------------------------------------------------------------------------- #
def test_a_winner_cannot_be_named_before_the_clock_runs_out(tmp_path):
    exp = _register(tmp_path)
    try:
        experiments.decide(exp.id, {"control": 2, "question": 40},
                           today=START + timedelta(days=4),
                           path=tmp_path / "e.json")
    except ExperimentError as exc:
        assert "cannot be called yet" in str(exc)
        assert "noise" in str(exc)
    else:
        raise AssertionError("an experiment was called on day four")


def test_a_winner_cannot_be_named_before_every_arm_has_enough(tmp_path):
    """The clock alone is not the stop rule. Both conditions have to hold."""
    exp = _register(tmp_path, runs_for_days=6)   # 7 days, so ~3-4 per arm
    assert exp.ready(START + timedelta(days=6)) is False
    try:
        experiments.decide(exp.id, {"control": 1, "question": 9},
                           today=START + timedelta(days=6),
                           path=tmp_path / "e.json")
    except ExperimentError as exc:
        assert "per arm" in str(exc)
    else:
        raise AssertionError("an under-powered experiment was called")


def test_a_finished_experiment_is_called_and_records_its_reasoning(tmp_path):
    exp = _register(tmp_path, runs_for_days=40)
    today = START + timedelta(days=40)
    assert exp.ready(today) is True

    note = experiments.decide(exp.id, {"control": 10, "question": 30},
                              today=today, path=tmp_path / "e.json")
    assert "question won" in note
    called = experiments.load(path=tmp_path / "e.json").get(exp.id)
    assert called.winner == "question"
    assert called.live is False


def test_a_narrow_lead_keeps_the_control(tmp_path):
    """At these volumes a 5% difference is not a result, and the threshold was
    written down before the numbers arrived."""
    exp = _register(tmp_path, runs_for_days=40)
    today = START + timedelta(days=40)
    experiments.decide(exp.id, {"control": 100, "question": 104},
                       today=today, path=tmp_path / "e.json")
    called = experiments.load(path=tmp_path / "e.json").get(exp.id)
    assert called.winner == "control"
    assert "less than 10%" in called.note


def test_calling_a_called_experiment_reports_rather_than_recalls(tmp_path):
    exp = _register(tmp_path, runs_for_days=40)
    today = START + timedelta(days=40)
    experiments.decide(exp.id, {"control": 10, "question": 30},
                       today=today, path=tmp_path / "e.json")
    again = experiments.decide(exp.id, {"control": 99, "question": 1},
                               today=today, path=tmp_path / "e.json")
    assert "already called" in again
    assert experiments.load(path=tmp_path / "e.json").get(exp.id).winner == "question"


def test_due_lists_only_the_ones_whose_stop_rule_is_satisfied(tmp_path):
    _register(tmp_path, runs_for_days=40)
    assert experiments.due(START + timedelta(days=5), path=tmp_path / "e.json") == []
    ready = experiments.due(START + timedelta(days=40), path=tmp_path / "e.json")
    assert len(ready) == 1


def test_an_unknown_experiment_is_refused(tmp_path):
    try:
        experiments.decide("nope-01", {"a": 1}, path=tmp_path / "e.json")
    except ExperimentError as exc:
        assert "no experiment" in str(exc)
    else:
        raise AssertionError("an unknown experiment was called")


def test_an_unreadable_register_is_empty_rather_than_fatal(tmp_path):
    path = tmp_path / "e.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert experiments.load(path=path).experiments == []
