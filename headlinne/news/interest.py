"""Is this story worth anyone's attention?

The old scoring answered a different question. Its heaviest term by far was
cross-source count, with outlet tier and importance keywords behind it - three
proxies for institutional consensus. The story that maximises that function is,
by definition, the one the most outlets ran: a central bank, a summit, an
earnings print. Nobody chose those stories. The arithmetic did.

Run live on 208 stories, the old weights put an X-Files director's cut in the
top eight twice and never surfaced a rocket hitting the Moon at all - partly
because it scored badly, mostly because no configured feed carried it.

So verification and interest are separated here. Cross-source count answers
"is this true?" and is a property of the story (see Story.verified); it is not
a ranking term, because being well attended is not the same as being worth
reading. This module answers "should anyone care?"

Eight terms, all computable from the headline, summary and metadata already
fetched. No extra API call.

  concrete     physical nouns and measured quantities beat abstractions
  novelty      first, never before, confirmed, discovered
  surprise     turned out, actually, instead, contrary
  universal    things every human has a stake in; penalises the parochial
  uplift       recovery, progress, awe - positive emotion transmits better
  imageable    a real photograph exists
  standalone   understandable without yesterday's episode
  procedural   penalty: a process, not an event

The ordering that falls out of it: "X happened" beats "X may happen" beats
"X met to discuss whether X might happen." Almost everything the old ranker
surfaced sat in the third bucket.

SENSITIVE is a separate axis and deliberately not a score. Deaths and disasters
come with concrete nouns and hard numerals, which is exactly what `concrete`
rewards - the first live run put a ferry disaster fourth on a list of things it
considered interesting. Those stories still publish; they route to a plain
treatment with no mascot, no bubble and no wonder framing. See is_sensitive().
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Lexicons. Deliberately small and readable: this is editorial judgement written
# down, and it should be arguable over by a person rather than tuned blindly.
# --------------------------------------------------------------------------- #
_UNITS = re.compile(
    r"\b(km/h|mph|kg|tonnes?|met(?:res|ers)|miles|light[- ]years|degrees|"
    r"billion|million|trillion|percent|%|km|ft|mm|hours|minutes)\b")

_NOVELTY = ("first", "first-ever", "never before", "unprecedented", "discovered",
            "confirmed", "detected", "spotted", "new species", "breakthrough",
            "record", "oldest", "largest", "smallest", "revealed")

_SURPRISE = ("turned out", "actually", "instead", "contrary", "unexpected",
             "surprised", "mystery", "puzzle", "baffl", "not what", "wrong",
             "reversal", "far more", "far fewer")

_PHYSICAL = ("rocket", "crater", "moon", "asteroid", "comet", "volcano", "whale",
             "fossil", "glacier", "telescope", "satellite", "reactor", "bridge",
             "tunnel", "ship", "aircraft", "brain", "cell", "virus", "star",
             "planet", "ice", "ocean", "forest", "storm", "dinosaur", "engine")

# Applies to a reader anywhere, with no prior expertise.
_UNIVERSAL = ("moon", "space", "earth", "ocean", "brain", "sleep", "body",
              "human", "cancer", "memory", "ageing", "aging", "heart", "climate",
              "whale", "bird", "forest", "water", "food", "light", "sun", "star",
              "planet", "universe", "cell", "dna", "gravity", "phone", "internet",
              "battery", "energy", "everyone", "people", "children")

# Local, expert-only or in-group. The opposite of universal.
_PAROCHIAL = ("council", "borough", "constituency", "senator", "shares",
              "shareholder", "earnings", "quarterly", "ftse", "nasdaq",
              "premier league", "transfer window", "midfielder", "by-election",
              "reshuffle", "select committee", "budget speech", "primary race")

_UPLIFT = ("discovered", "breakthrough", "recovering", "reclaiming", "restored",
           "revived", "saved", "thriving", "rebound", "cure", "solved", "first",
           "record", "milestone", "repair", "better than", "returns")

_PROCEDURAL = ("holds", "held", "meets", "meeting", "discuss", "considers",
               "is set to", "could", "may ", "might", "expected to", "plans to",
               "unchanged", "consecutive", "talks", "urges", "calls for",
               "seeks", "weighs", "mulls", "to decide", "ahead of", "amid")

_CONTEXT_DEPENDENT = ("continues", "latest", "amid ongoing", "another round",
                      "as it happened", "update:", "day two", "day three")

# Death and disaster. Not a disqualification - a routing decision.
_SENSITIVE = ("dead", "death", "killed", "kills", "killing", "casualt",
              "massacre", "shooting", "stabbed", "murder", "victims", "bodies",
              "capsiz", "earthquake", "famine", "genocide", "atrocit", "suicide",
              "abuse", "missing after", "death toll", "wounded", "injured",
              "hostage", "airstrike", "bombing", "war crime")

# Weights. Concrete leads because it is the strongest single predictor of a
# story a person will actually look at; procedural is the only negative and is
# weighted to fully cancel a strong positive, because a process story dressed in
# concrete nouns is still a process story.
_W_CONCRETE, _W_NOVELTY, _W_SURPRISE = 3.0, 2.4, 2.2
_W_UNIVERSAL, _W_UPLIFT = 2.6, 1.8
_W_IMAGE, _W_STANDALONE, _W_PROCEDURAL = 1.4, 1.2, 3.0


def _hits(text: str, bag: tuple[str, ...]) -> int:
    return sum(1 for k in bag if k in text)


def is_sensitive(title: str, summary: str = "") -> bool:
    """True if the story is about death or disaster.

    Callers must not render these with the mascot, a speech bubble or any
    wonder framing. They are reported plainly.
    """
    return _hits((title + " " + summary).lower(), _SENSITIVE) > 0


def interest(title: str, summary: str = "", has_image: bool = False) -> float:
    """Score how much a person who is not obliged to read this would want to."""
    text = (title + " " + summary).lower()

    concrete = min(1.0, _hits(text, _PHYSICAL) * 0.45
                   + len(_UNITS.findall(text)) * 0.3
                   + (0.25 if re.search(r"\d", title) else 0.0))
    novelty = min(1.0, _hits(text, _NOVELTY) * 0.5)
    surprise = min(1.0, _hits(text, _SURPRISE) * 0.55)
    universal = max(0.0, min(1.0, _hits(text, _UNIVERSAL) * 0.4
                             - _hits(text, _PAROCHIAL) * 0.5))
    uplift = min(1.0, _hits(text, _UPLIFT) * 0.45)
    standalone = max(0.0, 1.0 - _hits(text, _CONTEXT_DEPENDENT) * 0.5)
    procedural = min(1.0, _hits(text, _PROCEDURAL) * 0.34)

    return (_W_CONCRETE * concrete
            + _W_NOVELTY * novelty
            + _W_SURPRISE * surprise
            + _W_UNIVERSAL * universal
            + _W_UPLIFT * uplift
            + _W_IMAGE * (1.0 if has_image else 0.0)
            + _W_STANDALONE * standalone
            - _W_PROCEDURAL * procedural)


def breakdown(title: str, summary: str = "", has_image: bool = False) -> dict:
    """Per-term detail, for tuning and for explaining a ranking in the logs."""
    text = (title + " " + summary).lower()
    return {
        "concrete": round(min(1.0, _hits(text, _PHYSICAL) * 0.45
                              + len(_UNITS.findall(text)) * 0.3
                              + (0.25 if re.search(r"\d", title) else 0.0)), 2),
        "novelty": round(min(1.0, _hits(text, _NOVELTY) * 0.5), 2),
        "surprise": round(min(1.0, _hits(text, _SURPRISE) * 0.55), 2),
        "universal": round(max(0.0, min(1.0, _hits(text, _UNIVERSAL) * 0.4
                                        - _hits(text, _PAROCHIAL) * 0.5)), 2),
        "uplift": round(min(1.0, _hits(text, _UPLIFT) * 0.45), 2),
        "image": 1.0 if has_image else 0.0,
        "standalone": round(max(0.0, 1.0 - _hits(text, _CONTEXT_DEPENDENT) * 0.5), 2),
        "procedural": round(min(1.0, _hits(text, _PROCEDURAL) * 0.34), 2),
        "sensitive": is_sensitive(title, summary),
        "total": round(interest(title, summary, has_image), 2),
    }
