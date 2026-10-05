"""Art direction: which set, costume, pose and camera each beat gets.

The reference reels are dressed per story - a game-show stage for a pitching
tool, a courtroom for a judging one - and that is what makes each one feel
made rather than templated. Here the script writer proposes a set and a
costume for every beat from a closed vocabulary (see gemini/prompts.py), and
this module decides what is actually shot:

  * an unknown or missing choice is replaced from the story itself, by its
    vocabulary and then by its category, so a beat is never undressed;
  * a chapter keeps its set across its beats and the set changes when the
    chapter does, which is the rhythm of the reference edits;
  * a reel never spends every chapter in one place - consecutive chapters
    rotate through the primary set's neighbours;
  * a sensitive story is shot plainly: a sober set, no Pip, no stamp.

Everything is deterministic in the reel's content and the day, so a re-render
of the same reel is the same film.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import theme
from . import sets, voxel
from .paper import Rng

# A story's vocabulary, matched on word boundaries, to the set that shows it.
# Order matters: the first set with a hit wins, so the specific sits above the
# general ("supreme court" above "election" above "government").
_SET_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("space", ("nasa", "rocket", "spacecraft", "astronaut*", "moon", "mars",
               "satellite*", "orbit*", "iss", "spacex", "telescope", "asteroid",
               "galaxy", "planet*")),
    ("courtroom", ("court", "courts", "judge*", "ruling", "ruled", "lawsuit*",
                   "trial", "verdict", "jury", "sued", "sues", "prosecut*",
                   "supreme court", "appeal*", "convicted", "sentenced")),
    ("street", ("protest*", "strike", "strikes", "march*", "rally", "rallies",
                "riot*", "unrest", "demonstrat*", "arrests", "arrested",
                "walkout", "schools", "crowd*", "police")),
    ("parliament", ("election*", "vote", "votes", "voters", "ballot*", "poll",
                    "polls", "run-off", "runoff", "parliament", "congress",
                    "senate", "president", "prime minister", "minister*",
                    "government", "bill", "law", "legislat*", "campaign",
                    "party", "white house", "chancellor", "cabinet", "czar")),
    ("harbour", ("oil", "barrels", "shipping", "ship", "ships", "port", "ports",
                 "tariff*", "export*", "import*", "trade", "cargo", "diesel",
                 "fuel", "opec", "strait", "supply chain")),
    ("server", ("ai", "openai", "anthropic", "chatgpt", "chatbot*", "model",
                "algorithm*", "data", "cyber*", "hack*", "breach*", "software",
                "nvidia", "chip", "chips", "semiconductor*", "google", "meta",
                "microsoft", "apple", "app", "apps", "scam*", "online")),
    ("trading", ("market*", "stock*", "shares", "inflation", "interest rate*",
                 "rates", "economy", "economic", "recession", "wages", "prices",
                 "bank", "banks", "fed", "central bank", "bond*", "gdp",
                 "jobs", "unemployment", "crypto*", "bitcoin")),
    ("maproom", ("war", "military", "troops", "missile*", "bomber*", "nato",
                 "border", "ceasefire", "sanction*", "invasion", "diplomat*",
                 "summit", "treaty", "allies", "defence", "defense", "base",
                 "nuclear", "un", "united nations")),
    ("home", ("housing", "rent", "rents", "mortgage*", "household*", "bills",
              "energy bills", "cost of living", "families", "family", "home",
              "homes", "food prices", "childcare")),
    ("lab", ("scientist*", "study", "research*", "cells", "dna", "virus*",
             "vaccine*", "disease*", "health", "cancer", "brain", "climate",
             "species", "fossil*", "experiment*", "medicine", "drug")),
    ("skyline", ("ceo", "company", "companies", "startup*", "firm", "deal",
                 "acquisition", "acquire*", "merger", "layoff*", "resign*",
                 "quits", "steps down", "boss", "executive*", "billion")),
)

_RX = {name: re.compile(r"\b(?:" + "|".join(
    re.escape(t[:-1]) + r"\w*" if t.endswith("*") else re.escape(t)
    for t in terms) + r")\b", re.I) for name, terms in _SET_TERMS}

_CATEGORY_SET = {"Technology": "server", "Finance": "trading",
                 "Geopolitics": "maproom", "Science": "lab"}

# Where a chapter goes next, so a reel moves through related places.
_NEIGHBOURS = {
    "parliament": ("street", "maproom", "newsroom"),
    "courtroom": ("parliament", "newsroom", "street"),
    "street": ("parliament", "home", "newsroom"),
    "harbour": ("trading", "maproom", "skyline"),
    "server": ("skyline", "lab", "newsroom"),
    "trading": ("skyline", "home", "harbour"),
    "maproom": ("newsroom", "parliament", "harbour"),
    "home": ("trading", "street", "newsroom"),
    "lab": ("space", "newsroom", "home"),
    "space": ("lab", "newsroom", "maproom"),
    "skyline": ("server", "trading", "newsroom"),
    "newsroom": ("maproom", "skyline", "street"),
    "board": ("newsroom", "skyline", "lab"),
}

# The costume a set suggests. A hat is a prop, never a recolour of Pip.
_SET_HAT = {
    "newsroom": "press", "parliament": "press", "courtroom": "press",
    "street": "beanie", "harbour": "hardhat", "server": "cap",
    "trading": "tophat", "maproom": "press", "home": "", "lab": "grad",
    "space": "", "skyline": "tophat", "board": "grad",
}

_EXTERIOR = ("street", "harbour", "space")

# Poses the old generator assigns, translated for a figure standing in a set.
# "walk" walks in place on a set and reads as a malfunction, so it becomes
# talking; the sign-off waves.
_POSE_MAP = {"walk": "talk", "cta": "cheer", "": "talk"}

# Pip's block size by beat kind. A graphic beat shares the frame with a board,
# so he steps back and down.
PIP_CELL = 22
PIP_CELL_BOARD = 12


@dataclass(frozen=True)
class Look:
    spec: sets.SetSpec
    hat: str
    pose: str            # an entry in theme.CYCLES, or "" for no Pip
    cell: int
    zoom: tuple[float, float]
    pan: tuple[float, float]
    chapter_start: bool  # the first beat of its chapter: titles and cuts animate


def chapters(reel) -> list[str]:
    """The title strip each beat shows.

    A beat with no chapter of its own keeps the one before it, so the strip is
    never blank mid-reel; the first beat falls back to the reel's hook. The
    set changes exactly where this text changes.
    """
    out: list[str] = []
    current = ""
    for i, beat in enumerate(reel.beats):
        text = (beat.chapter or "").strip()
        if not text and i == 0:
            text = (reel.hook or reel.title or "").strip()
        current = text or current
        out.append(current)
    return out


def classify(text: str, category: str = "") -> str:
    """The set a piece of text belongs in."""
    for name, _terms in _SET_TERMS:
        if _RX[name].search(text or ""):
            return name
    return _CATEGORY_SET.get(category, "newsroom")


def _valid_set(name) -> str:
    name = str(name or "").strip().lower()
    return name if name in sets.SETS else ""


def _valid_hat(name) -> str | None:
    name = str(name or "").strip().lower()
    if name in ("none", "no", "bare"):
        return ""
    return name if name in voxel.HAT_NAMES else None


def _valid_pose(name: str) -> str:
    name = _POSE_MAP.get(str(name or "").strip().lower(), str(name or "").strip().lower())
    return name if name in theme.CYCLES else "talk"


def plan(reel, story=None, day_ordinal: int = 0) -> list[Look]:
    """One Look per beat."""
    beats = list(reel.beats)
    sensitive = bool(getattr(story, "sensitive", False))
    text = " ".join(filter(None, [getattr(story, "title", ""),
                                  getattr(story, "summary", ""), reel.title]))
    primary = classify(text, reel.category)
    if sensitive and primary not in sets.SOBER_SETS:
        primary = "maproom" if primary in ("street", "parliament", "harbour") else "newsroom"
    accent = theme.tone_for(story, category=reel.category, role="")
    variant = (day_ordinal + len(reel.title)) % 97
    rng = Rng("direction", reel.title, day_ordinal)

    looks: list[Look] = []
    chapter_index = -1
    current_set = primary
    last_chapter = None
    titles = chapters(reel)
    for i, beat in enumerate(beats):
        scene = getattr(beat, "scene", None) or {}
        chapter = titles[i].lower() or f"beat-{i}"
        starts = chapter != last_chapter
        if starts:
            chapter_index += 1
            asked = _valid_set(scene.get("set"))
            if sensitive:
                asked = asked if asked in sets.SOBER_SETS else ""
            if asked:
                current_set = asked
            elif chapter_index == 0:
                current_set = primary
            else:
                # Primary, then its neighbours in turn, then back home.
                ring = (primary, *_NEIGHBOURS.get(primary, ("newsroom",)))
                current_set = ring[chapter_index % len(ring)]
                if sensitive and current_set not in sets.SOBER_SETS:
                    current_set = primary
        last_chapter = chapter

        is_last = i == len(beats) - 1
        board = bool(beat.graphic and beat.graphic != "counter")
        time = str(scene.get("time") or "").lower()
        if time not in ("day", "dusk", "night"):
            time = "dusk" if current_set in _EXTERIOR else "night"
        trend = str(scene.get("trend") or "").lower()
        if trend not in ("up", "down"):
            trend = _trend(text)
        spec = sets.SetSpec(name=current_set, time=time, accent=tuple(accent),
                            trend=trend, board=board, variant=variant,
                            sober=sensitive)

        hat = _valid_hat(scene.get("hat"))
        if hat is None:
            hat = _SET_HAT.get(current_set, "")
        pose = "" if sensitive else _valid_pose(
            scene.get("pose") or ("cheer" if is_last else
                                  "point" if board else beat.pose))

        # The camera: a slow push in every beat, drifting a different way each
        # chapter. The cut itself is the whip; nothing else moves fast.
        z0 = 1.02 + rng.uniform(0.0, 0.02)
        z1 = z0 + rng.uniform(0.04, 0.07)
        pan = (rng.uniform(-30, 30), rng.uniform(-20, 10))
        looks.append(Look(spec=spec, hat=hat, pose=pose,
                          cell=PIP_CELL_BOARD if board else PIP_CELL,
                          zoom=(z0, z1), pan=pan, chapter_start=starts))
    return looks


_UP = re.compile(r"\b(rise|rises|rising|rose|soar\w*|jump\w*|surge\w*|record high|"
                 r"gain\w*|climb\w*|up)\b", re.I)
_DOWN = re.compile(r"\b(fall|falls|falling|fell|drop\w*|plunge\w*|slump\w*|"
                   r"crash\w*|tumble\w*|lose|loses|loss\w*|down|cut|cuts)\b", re.I)


def _trend(text: str) -> str:
    up, down = len(_UP.findall(text or "")), len(_DOWN.findall(text or ""))
    return "down" if down > up else "up"
