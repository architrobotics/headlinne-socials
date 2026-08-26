"""The experiment register: hypotheses with their stop rules fixed in advance.

An experiment whose stopping point is decided after the numbers arrive is not an
experiment, it is a search for a flattering week. That failure mode is the whole
reason this module exists, and it is designed around one rule:

**The stop rule is written at creation and cannot be edited afterwards.**
`minimum` and `runs_for_days` are set when the experiment is registered, they
are hashed into the record, and `decide()` refuses to name a winner before both
are satisfied. An experiment file that has been edited fails its own integrity
check and is reported as tampered rather than quietly used.

**Assignment is deterministic.** Which arm a given day and slot gets is a hash
of the experiment id, the day and the slot - not a random draw. Three things
follow, and all three matter more than the elegance of a coin flip: a
regenerated day gets the same arm rather than silently switching mid-flight, the
whole assignment history can be recomputed from the committed record, and there
is no seed to lose.

**One live experiment per surface.** Two experiments running on the same slot
means neither can be read, because every post carries both changes. The register
refuses the second one rather than producing two results that each explain the
other's noise.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import STATE_DIR
from ..logging_setup import get_logger

log = get_logger("cmo.experiments")

REGISTER_PATH = STATE_DIR / "cmo" / "experiments.json"

# Below this many posts per arm, a difference is noise. Deliberately blunt: the
# volumes here are small enough that anything subtler than "did it obviously
# move" is not detectable, and pretending otherwise produces confident wrong
# calls. An experiment that cannot clear this is not worth running.
MIN_PER_ARM = 12


class ExperimentError(RuntimeError):
    pass


@dataclass
class Experiment:
    id: str
    hypothesis: str
    slot: str                       # the surface it runs on
    arms: list[str]                 # arm names, first is the control
    started: str                    # ISO day
    runs_for_days: int
    minimum: int                    # posts per arm before a call may be made
    stopped: str = ""               # ISO day, once called
    winner: str = ""
    note: str = ""
    seal: str = ""                  # hash of the terms fixed at creation

    # -- the terms that may never change --------------------------------- #
    def terms(self) -> str:
        return json.dumps({
            "id": self.id, "hypothesis": self.hypothesis, "slot": self.slot,
            "arms": self.arms, "started": self.started,
            "runs_for_days": self.runs_for_days, "minimum": self.minimum,
        }, sort_keys=True)

    def compute_seal(self) -> str:
        return hashlib.sha256(self.terms().encode()).hexdigest()[:16]

    @property
    def sealed(self) -> bool:
        """False when the record has been edited since it was registered."""
        return bool(self.seal) and self.seal == self.compute_seal()

    @property
    def control(self) -> str:
        return self.arms[0]

    @property
    def live(self) -> bool:
        return not self.stopped

    def ends_on(self) -> date:
        return date.fromisoformat(self.started) + timedelta(days=self.runs_for_days)

    def arm_for(self, day: date, slot: str = "") -> str:
        """Which arm this day's post takes. Deterministic, never random."""
        key = f"{self.id}|{day.isoformat()}|{slot or self.slot}".encode()
        digest = hashlib.sha256(key).digest()
        return self.arms[digest[0] % len(self.arms)]

    def assignments(self, upto: date) -> dict[str, int]:
        """How many days each arm has had, from the start to `upto`."""
        counts = {arm: 0 for arm in self.arms}
        start = date.fromisoformat(self.started)
        last = min(upto, self.ends_on())
        day = start
        while day <= last:
            counts[self.arm_for(day)] += 1
            day += timedelta(days=1)
        return counts

    def ready(self, today: date) -> bool:
        """Both stop conditions met: the clock ran out AND every arm has enough."""
        if today < self.ends_on():
            return False
        return all(n >= self.minimum for n in self.assignments(today).values())


# --------------------------------------------------------------------------- #
# The register
# --------------------------------------------------------------------------- #
@dataclass
class Register:
    experiments: list[Experiment] = field(default_factory=list)

    def live(self) -> list[Experiment]:
        return [e for e in self.experiments if e.live and e.sealed]

    def on(self, slot: str) -> Experiment | None:
        return next((e for e in self.live() if e.slot == slot), None)

    def get(self, experiment_id: str) -> Experiment | None:
        return next((e for e in self.experiments if e.id == experiment_id), None)

    def tampered(self) -> list[Experiment]:
        """Records whose terms were edited after registration."""
        return [e for e in self.experiments if e.seal and not e.sealed]


def load(*, path: Path | None = None) -> Register:
    path = path or REGISTER_PATH
    if not path.exists():
        return Register()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("experiment register unreadable: %s", exc)
        return Register()
    out = []
    for row in raw.get("experiments", []):
        try:
            out.append(Experiment(**row))
        except TypeError:
            log.warning("skipping an unusable experiment record: %r", row)
    return Register(experiments=out)


def save(register: Register, *, path: Path | None = None) -> Path:
    path = path or REGISTER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"experiments": [asdict(e) for e in register.experiments]}, indent=2),
        encoding="utf-8")
    return path


def register(hypothesis: str, slot: str, arms: list[str], *,
             today: date | None = None, runs_for_days: int = 21,
             minimum: int = MIN_PER_ARM, experiment_id: str = "",
             path: Path | None = None) -> Experiment:
    """Register one experiment, with its stop rule fixed now rather than later."""
    today = today or date.today()
    if len(arms) < 2:
        raise ExperimentError("an experiment needs at least two arms.")
    if len(set(arms)) != len(arms):
        raise ExperimentError(f"duplicate arm names: {arms}")

    reg = load(path=path)
    running = reg.on(slot)
    if running is not None:
        raise ExperimentError(
            f"{running.id!r} is already running on {slot}. Two experiments on "
            f"one surface means every post carries both changes and neither "
            f"result can be read. Stop that one first.")

    experiment_id = experiment_id or _next_id(reg, slot)
    if reg.get(experiment_id) is not None:
        raise ExperimentError(f"{experiment_id!r} already exists.")

    exp = Experiment(
        id=experiment_id, hypothesis=hypothesis, slot=slot, arms=list(arms),
        started=today.isoformat(), runs_for_days=runs_for_days,
        minimum=minimum)
    exp.seal = exp.compute_seal()
    reg.experiments.append(exp)
    save(reg, path=path)
    log.info("registered %s on %s: %s", exp.id, slot, hypothesis)
    return exp


def _next_id(reg: Register, slot: str) -> str:
    n = sum(1 for e in reg.experiments if e.slot == slot) + 1
    return f"{slot}-{n:02d}"


def assign(day: date, slot: str, *, path: Path | None = None) -> tuple[str, str]:
    """The (experiment id, arm) for this post, or ("", "") when none is running."""
    exp = load(path=path).on(slot)
    if exp is None or day > exp.ends_on() or day < date.fromisoformat(exp.started):
        return "", ""
    return exp.id, exp.arm_for(day, slot)


def decide(experiment_id: str, results: dict[str, float], *,
           today: date | None = None, path: Path | None = None) -> str:
    """Call an experiment, if and only if its own stop rule permits it.

    `results` is signups per arm, and it has to come from the ledger like every
    other number here. The refusal below is the point of the module: a winner
    named on day four of a twenty-one day test is a coin flip with a rationale.
    """
    today = today or date.today()
    reg = load(path=path)
    exp = reg.get(experiment_id)
    if exp is None:
        raise ExperimentError(f"no experiment {experiment_id!r}.")
    if not exp.sealed:
        raise ExperimentError(
            f"{experiment_id!r} has been edited since it was registered, so its "
            f"stop rule is no longer the one it started with. Its result cannot "
            f"be trusted and will not be called.")
    if not exp.live:
        return f"{experiment_id} was already called: {exp.winner or 'no winner'}."

    if not exp.ready(today):
        counts = exp.assignments(today)
        short = {a: n for a, n in counts.items() if n < exp.minimum}
        raise ExperimentError(
            f"{experiment_id} cannot be called yet. It runs until "
            f"{exp.ends_on()} and needs {exp.minimum} days per arm; "
            f"{short or 'the clock'} is short. Stopping now would name a winner "
            f"from noise.")

    ranked = sorted(results.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    control_score = results.get(exp.control, 0.0)
    # A challenger has to beat the control by enough to be worth the change.
    # Ten percent is arbitrary and it is written down, which is the part that
    # matters: it was chosen before the numbers arrived.
    if best != exp.control and best_score < control_score * 1.10:
        best, note = exp.control, (
            f"{ranked[0][0]} led but by less than 10%, which at these volumes "
            f"is not a result. Keeping the control.")
    else:
        note = f"{best} won on {best_score:g} against {control_score:g}."

    exp.stopped = today.isoformat()
    exp.winner = best
    exp.note = note
    save(reg, path=path)
    log.info("%s called: %s", experiment_id, note)
    return note


def due(today: date | None = None, *, path: Path | None = None) -> list[Experiment]:
    """Experiments whose stop rule is now satisfied and which need a call."""
    today = today or date.today()
    return [e for e in load(path=path).live() if e.ready(today)]
