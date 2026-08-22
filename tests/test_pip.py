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
    """Only heads and props may vary. Drift here is how a mascot stops being one.

    This walks P.HEADS rather than a list written out here, so a head added
    later is covered without anyone having to remember to add it.
    """
    bodies = {"\n".join(P._rows(P.badged(h))[11:]) for h in P.HEADS.values()}
    assert len(bodies) == 1, "the body block drifted between heads"


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


def test_every_head_is_eleven_rows_of_full_width():
    """The head is a fixed block.

    squash(), stretch() and head_shift() all read the first eleven rows as the
    head, so a twelve-row head would silently take a slice of the body with it.
    """
    for name, head in P.HEADS.items():
        rows = P._rows(head)
        assert len(rows) == 11, f"head {name} is {len(rows)} rows"
        for i, row in enumerate(rows):
            assert len(row) == P.W, f"head {name} row {i} is {len(row)}px"


def test_every_pose_is_legible_at_avatar_size():
    """26px is profile-picture size, and every pose has to survive it - not just
    idle. A prop that only reads at 8x is decoration, not metadata."""
    for name, grid in P.SPRITES.items():
        box = P.render(grid, 1).getbbox()
        assert box is not None, f"{name} rendered empty"
        assert box[2] - box[0] >= 16 and box[3] - box[1] >= 16, (
            f"{name} collapses at 1x: {box}")


def test_every_cycle_builder_is_registered_for_checking():
    """quality.visual only guards the cycles listed in theme.CYCLES.

    A builder missing from that map is checked by nothing, which is exactly how
    a frozen animation ships unnoticed.
    """
    from headlinne.render import theme

    builders = {n for n in dir(P)
                if n.endswith("_cycle") and not n.startswith("_")}
    registered = {b.__name__ for b in theme.CYCLES.values()}
    assert builders == registered, (
        f"unguarded: {sorted(builders - registered)}; "
        f"stale: {sorted(registered - builders)}")


def test_every_registered_cycle_actually_moves():
    """The same check quality.visual runs, kept here so a broken cycle fails the
    test suite and not only a render."""
    from headlinne.render import theme

    for name, builder in theme.CYCLES.items():
        frames = builder()
        assert len(frames) >= 2, f"{name}: {len(frames)} frame(s)"
        heights = {len(P._rows(f)) for f in frames}
        assert len(heights) == 1, f"{name}: frames differ in height {heights}"
        for f in frames:
            for i, row in enumerate(P._rows(f)):
                assert len(row) == P.W, f"{name} row {i} is {len(row)}px"
        assert len({P.render(f, 4).tobytes() for f in frames}) > 1, (
            f"{name} never changes a pixel")


def test_squash_and_stretch_keep_the_canvas_height():
    """Both change the body and neither changes the frame. A cycle whose frames
    differ in height cannot be played at all."""
    base = P.badged(P.HEAD_OPEN)
    height = len(P._rows(base))
    for frame in (P.squash(base, 1), P.stretch(base, 1), P.squash(base, 2)):
        assert len(P._rows(frame)) == height
        assert all(len(r) == P.W for r in P._rows(frame))
    assert P.squash(base, 1) != base
    assert P.stretch(base, 1) != base


def test_squash_leaves_the_head_alone():
    """Only the body compresses. A head that deforms reads as the character
    being damaged rather than as weight arriving."""
    base = P.badged(P.HEAD_OPEN)
    squashed = P._rows(P.squash(base, 1))
    # A blank row is added on top, so the head starts one row lower, unchanged.
    assert squashed[1:12] == P._rows(base)[:11]


def test_head_shift_never_moves_the_body():
    """The body is a fixed mark in this design. A nod moves the head into the
    shoulders; it does not move the bird."""
    base = P.badged(P.HEAD_OPEN)
    body = P._rows(base)[11:]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        moved = P.head_shift(base, dx=dx, dy=dy)
        assert P._rows(moved)[11:] == body, f"body moved on ({dx},{dy})"
        assert moved != base, f"({dx},{dy}) changed nothing"
        assert all(len(r) == P.W for r in P._rows(moved))


def test_hold_is_what_gives_a_cycle_uneven_timing():
    """The player steps frames at a fixed rate, so repetition is the only timing
    control available. bounce_cycle has to actually use it, or the apex passes
    in a single tick and the jump carries no weight."""
    assert P.hold("x", 3) == ["x", "x", "x"]
    assert P.hold("x", 0) == ["x"]           # never produces an empty cycle
    frames = P.bounce_cycle()
    assert len(frames) > len(set(frames)), "bounce_cycle holds nothing"


def test_easing_keeps_its_endpoints_and_only_moves_forward():
    """Pip's travel across a reel is eased, so the overlap and safe-zone harness
    has to see the same start and end bounds it saw when travel was linear."""
    for ease in (P.ease_in_out_sine, P.ease_out_cubic):
        assert ease(0.0) == 0.0
        assert abs(ease(1.0) - 1.0) < 1e-9
        assert ease(-5.0) == 0.0 and abs(ease(5.0) - 1.0) < 1e-9
        seen = [ease(i / 40) for i in range(41)]
        assert all(b >= a for a, b in zip(seen, seen[1:])), "travel reversed"
    # and it is genuinely not linear, or there was no point easing it
    assert abs(P.ease_in_out_sine(0.25) - 0.25) > 0.05


def test_a_single_source_story_does_not_look_like_a_disputed_one():
    """Two different statements about the reporting. Disputed is a shrug: the
    outlets took positions and they differ. Single is a note that the checking
    is still going on."""
    from headlinne.render import receipt

    assert receipt.POSE["single"] != receipt.POSE["disputed"]
    for state, pose in receipt.POSE.items():
        assert pose in P.SPRITES, f"{state} maps to missing pose {pose!r}"
