"""Guards for Pip and the image-plate fallback ladder.

Two of these exist because the equivalent checks failed silently during design.

`test_cycles_actually_move` compares rendered pixels rather than bounding boxes:
the talk cycle animates a beak inside a fixed head outline, so a bbox comparison
passes even when the sprite is frozen.

`test_illustration_is_always_captioned` exists because rung 2 of the fallback
ladder draws a scene that could be mistaken for a photograph. The caption is a
correctness property, not a nicety.
"""

from __future__ import annotations

import inspect

from PIL import Image

from headlinne.render import pip as P
from headlinne.render import plate as PL


def test_every_pose_is_the_declared_width():
    for name, grid in P.SPRITES.items():
        for i, row in enumerate(P._rows(grid)):
            assert len(row) == P.W, f"{name} row {i} is {len(row)}px, expected {P.W}"


def test_every_pose_renders_something():
    for name, grid in P.SPRITES.items():
        assert P.render(grid, 4).getbbox() is not None, f"{name} rendered empty"


def test_pip_survives_avatar_scale():
    """26px is profile-picture size. If he stops reading there he is useless."""
    box = P.render(P.SPRITES["idle"], 1).getbbox()
    assert box is not None
    assert box[2] - box[0] >= 16 and box[3] - box[1] >= 16


def test_cycles_actually_move():
    cycles = {
        "walk": P.walk_cycle(), "jump": P.jump_cycle(), "point": P.point_cycle(),
        "present": P.present_cycle(), "talk": P.talk_cycle(), "idle": P.idle_cycle(),
    }
    for name, frames in cycles.items():
        assert len(frames) >= 2, f"{name} has {len(frames)} frame(s)"
        heights = {len(P._rows(f)) for f in frames}
        assert len(heights) == 1, f"{name} frames differ in height: {heights}"
        rendered = {P.render(f, 4).tobytes() for f in frames}
        assert len(rendered) > 1, f"{name} never changes a pixel"


def test_body_block_is_identical_across_poses():
    """Only heads and props may vary. Drift here is how a mascot stops being one."""
    bodies = set()
    for grid in (P.badged(P.HEAD_OPEN), P.badged(P.HEAD_SHUT),
                 P.badged(P.HEAD_WIDE), P.badged(P.HEAD_GLANCE)):
        bodies.add("\n".join(P._rows(grid)[11:]))
    assert len(bodies) == 1, "the body block drifted between poses"


def test_fallback_ladder_every_rung_produces_an_object():
    rungs = (
        ("photo", PL.tilted(Image.new("RGB", (400, 260), (90, 90, 110)))),
        ("pixel", PL.tilted(PL.moon_scene(w=400, h=260))),
        ("chart", PL.tilted(PL.chart_scene(w=400, h=260))),
        ("pip", P.render(P.SPRITES["carry"], 8)),
    )
    for name, im in rungs:
        assert im.getbbox() is not None, f"rung {name} produced nothing"
        assert im.width > 80 and im.height > 80, f"rung {name} is too small"


def test_generated_scenes_are_deterministic():
    assert PL.moon_scene(seed=5).tobytes() == PL.moon_scene(seed=5).tobytes()
    assert PL.moon_scene(seed=5).tobytes() != PL.moon_scene(seed=11).tobytes()


def test_illustration_is_always_captioned():
    """The caption must be reachable from tilted(), not left to the caller."""
    assert "caption" in inspect.signature(PL.tilted).parameters
    assert "caption" in inspect.getsource(PL.tilted)
