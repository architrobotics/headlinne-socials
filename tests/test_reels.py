"""The daily reel: pacing, geometry, and the guarantees that must never break.

The reel is one continuous scene rather than one scene per beat. Pip walks
across the whole runtime and the progress bar fills across it, so both are
functions of absolute time; cutting the render at beat boundaries would make
every segment need to know where the previous one left him.
"""

from headlinne.config import (REEL_FPS, REEL_H, REEL_MAX_SECONDS,
                              REEL_MIN_SECONDS, REEL_W)
from headlinne.models import Agreement, Reel, ReelBeat, Story
from headlinne.quality import visual
from headlinne.render import reel as reel_render
from headlinne.render.reel import ReelFrames, cta_pose, plan_durations


def _story(sensitive=False):
    story = Story(title="A rocket stage struck the Moon at 8,700 km/h",
                  summary="Four tonnes, at 8,700 km/h.", url="http://x/moon",
                  category="Science", source="Reuters", tier=1.4,
                  published_iso="2026-08-17T06:00:00+00:00",
                  sensitive=sensitive, verified=True)
    story.agreement = Agreement(reported=4, agree=4,
                                outlets=["Reuters", "AP", "Space.com", "Sky"])
    return story


def _reel(sensitive=False):
    pose = "" if sensitive else "walk"
    return Reel(
        slot="reel_1", kind="news", category="Science",
        title="Moon impact", hook="A rocket hit the Moon",
        beats=[
            ReelBeat(role="hook", chapter="What happened", pose=pose, seconds=3.0,
                     caption="On Tuesday a *four-tonne* stage struck the Moon.",
                     detail="A Falcon 9 second stage.",
                     narration="On Tuesday a four-tonne rocket stage struck the Moon."),
            ReelBeat(role="point", chapter="Why", pose=pose, seconds=3.0,
                     caption="Solar activity pulled it *off course*.",
                     detail="Nobody planned this.",
                     narration="Solar activity had pulled it off course."),
            ReelBeat(role="graphic", chapter="Where", pose=pose, seconds=3.0,
                     plates=["story"],
                     caption="It came down near *Einstein Crater*.",
                     detail="Out of view from Earth.",
                     narration="It came down near Einstein Crater."),
            ReelBeat(role="graphic", chapter="How fast", pose=pose, seconds=3.0,
                     graphic="counter", data={"value": "8700"},
                     caption="kilometres per hour.",
                     detail="Six times a rifle bullet.",
                     narration="Eight thousand seven hundred kilometres per hour."),
            ReelBeat(role="outro", chapter="Read it", pose="" if sensitive else "cta",
                     seconds=3.0,
                     caption="The full story is on *headlinne.com*.",
                     detail="Every source, side by side.",
                     narration="The full story is on headlinne dot com."),
        ],
        caption="A sample caption.", hashtags=["Science"],
        scheduled_time="2026-08-17T09:30:00+05:30",
        sources="Reuters · AP · Space.com +1", dateline="MON 17 AUG")


class _Track:
    def __init__(self, beat_seconds, outro_seconds=None):
        self.beat_seconds = beat_seconds
        self.outro_seconds = outro_seconds


def _frames(sensitive=False):
    return ReelFrames(_reel(sensitive), _story(sensitive), loader=lambda _s: None)


# --------------------------------------------------------------------------- #
# Pacing
# --------------------------------------------------------------------------- #
def test_the_narration_drives_the_edit():
    reel = _reel()
    plan_durations(reel, _Track([5.0, 4.0, 6.0, 3.0, 2.5]))
    assert [b.seconds for b in reel.beats] == [5.0, 4.0, 6.0, 3.0, 2.5]


def test_an_outro_measured_separately_is_appended():
    reel = _reel()
    plan_durations(reel, _Track([5.0, 4.0, 6.0, 3.0], outro_seconds=2.5))
    assert [b.seconds for b in reel.beats] == [5.0, 4.0, 6.0, 3.0, 2.5]


def test_a_mismatched_track_is_ignored_rather_than_trusted():
    # A stale track would silently desync every cut after it diverges.
    reel = _reel()
    plan_durations(reel, _Track([5.0, 4.0]))
    assert [b.seconds for b in reel.beats][:2] != [5.0, 4.0]


def test_reading_speed_lands_inside_the_target_window():
    reel = _reel()
    total = sum(plan_durations(reel))
    assert REEL_MIN_SECONDS <= total <= REEL_MAX_SECONDS


def test_no_beat_is_ever_shorter_than_a_glance():
    reel = _reel()
    plan_durations(reel)
    assert all(b.seconds >= 1.0 for b in reel.beats)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_every_frame_is_the_reel_canvas():
    frames = _frames()
    for t in (0.0, frames.duration / 2, frames.duration - 0.01):
        assert frames.render(t).size == (REEL_W, REEL_H)


def test_nothing_is_drawn_into_instagrams_ui():
    frames = _frames()
    report = visual.check_reel_frames(frames, sample_every=10, story=_story())
    assert report.ok, report.errors[:3]
    assert report.checks > 200, "the harness stopped checking anything"


def test_no_two_elements_overlap_on_any_sampled_frame():
    frames = _frames()
    report = visual.check_reel_frames(frames, sample_every=4, story=_story())
    overlaps = [e for e in report.errors if "overlaps" in e]
    assert not overlaps, overlaps[:3]


def test_the_progress_bar_runs_from_zero_to_one():
    frames = _frames()
    first = frames.render(0.0)
    last = frames.render(frames.duration - 0.01)
    # The bar is the masthead rule, so the two frames differ along that row.
    row = 128
    start = [first.getpixel((x, row)) for x in range(90, 1000, 40)]
    end = [last.getpixel((x, row)) for x in range(90, 1000, 40)]
    assert start != end, "the progress bar never moved"


def test_the_beat_showing_at_a_time_is_the_one_that_started_before_it():
    frames = _frames()
    index, beat, local = frames.beat_at(0.0)
    assert index == 0 and 0.0 <= local <= 1.0
    late_index, _beat, _local = frames.beat_at(frames.duration - 0.01)
    assert late_index == len(frames.reel.beats) - 1


# --------------------------------------------------------------------------- #
# Content guarantees
# --------------------------------------------------------------------------- #
def test_a_counter_only_prints_a_figure_the_story_contains():
    from headlinne.generate.reel import _daily_beats

    story = _story()
    data = {"beats": [
        {"chapter": "How fast", "caption": "kilometres per hour.",
         "detail": "d", "narration": "n", "counter": "8700"},
        {"chapter": "How big", "caption": "tonnes.", "detail": "d",
         "narration": "n", "counter": "999999"},
    ]}
    beats = _daily_beats(data, story)
    assert beats[0].graphic == "counter"
    assert beats[1].graphic == "", "an invented figure must lose its counter"


def test_a_sensitive_story_carries_no_mascot_and_no_plate():
    from headlinne.generate.reel import _place_plates

    reel = _reel(sensitive=True)
    _place_plates(reel.beats, _story(sensitive=True))
    assert all(not b.pose for b in reel.beats)
    assert all(not b.plates for b in reel.beats)
    # And the renderer draws neither, even if a pose slipped through.
    frames = _frames(sensitive=True)
    frames.render(1.0)
    assert not any(e[0] == "pip" for e in frames.trace)


def test_the_sign_off_pose_varies_across_a_month():
    assert len({cta_pose(d) for d in range(10)}) >= 4


def test_the_reel_still_renders_when_no_photograph_resolves():
    # The fallback ladder means a bad image day produces a designed plate, not
    # an empty frame.
    frames = _frames()
    img = frames.render(frames.duration * 0.55)
    assert img.getbbox() is not None
    colours = img.convert("RGB").resize((60, 60)).getcolors(3600) or []
    assert max(c for c, _ in colours) / 3600 < 0.985


# --------------------------------------------------------------------------- #
# The cover frame
# --------------------------------------------------------------------------- #
def _reel_with_first_beat(seconds: float):
    """The sample reel, with its opening beat stretched or squeezed.

    Only the opening beat's length matters to the cover frame, and reusing
    _reel() keeps this honest about the shape the renderer actually walks.
    """
    reel = _reel()
    reel.beats[0].seconds = seconds
    return reel


def test_the_cover_frame_lands_after_the_hook_has_finished_revealing():
    """The thumbnail is permanent, so a part-drawn hook is permanent too.

    The check is the renderer's own reveal arithmetic: the line is complete at
    LINE_REVEAL_FRACTION through the opening beat, so the cover has to be taken
    later than that for every beat length the generator can produce.
    """
    from headlinne.render import reel as R

    for seconds in (0.5, 1.0, 2.0, 3.0, 4.5, 6.0, 9.0, 12.0):
        offset = R.cover_offset_ms(_reel_with_first_beat(seconds)) / 1000
        first = max(0.4, seconds)
        local = offset / first
        reveal = min(1.0, local / R.LINE_REVEAL_FRACTION)
        assert reveal >= 1.0, (
            f"a {seconds}s opening beat covers at {offset:.2f}s, "
            f"when the line is only {reveal:.0%} drawn")


def test_the_cover_frame_stays_inside_the_opening_beat():
    """Past the first cut the frame shows the second beat, which is not the
    hook and is not what the grid should advertise."""
    from headlinne.render import reel as R

    for seconds in (0.5, 1.0, 3.0, 6.0, 12.0):
        offset = R.cover_offset_ms(_reel_with_first_beat(seconds)) / 1000
        assert 0 <= offset < max(0.4, seconds), (
            f"a {seconds}s beat covers at {offset:.2f}s, outside the beat")


def test_a_long_narrated_beat_is_the_case_the_fixed_offset_got_wrong():
    """The regression this replaced. With voiceover on, beats stretch to fit the
    spoken line, and the old fixed 1200ms froze a half-written hook onto the
    profile grid."""
    from headlinne.render import reel as R

    long_beat = _reel_with_first_beat(6.0)
    assert 1.2 / 6.0 / R.LINE_REVEAL_FRACTION < 1.0      # the old value failed
    assert R.cover_offset_ms(long_beat) > 1200            # the derived one does not


def test_a_reel_with_no_beats_falls_back_rather_than_raising():
    """Losing a thumbnail choice is a cosmetic problem. Losing the post is not."""
    from headlinne.render import reel as R

    class Bare:
        beats = []

    assert R.cover_offset_ms(Bare()) == 1200
    assert R.cover_offset_ms(object()) == 1200
