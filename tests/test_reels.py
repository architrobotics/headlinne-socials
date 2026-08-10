"""Reel generation and layout.

The important guarantees here are the accuracy ones. A graphic that prints a
number is a factual claim in a form people screenshot and reshare, so a figure
the source material does not contain must never reach a frame. The rest covers
pacing (the graphic beat has to be the longest cut, not the shortest) and that
every scene actually renders at the canvas size.

Everything runs offline: frames are rendered directly rather than encoded, so
these tests need no ffmpeg and no network.
"""

from __future__ import annotations

from datetime import date, timedelta

from headlinne.config import (EDUCATION_TOPICS, REEL_H, REEL_MAX_SECONDS,
                              REEL_MIN_SECONDS, REEL_W)
from headlinne.generate.reel import (CAPTION_CHARS, DETAIL_CHARS, HOOK_CHARS,
                                     _beats_from, _digits, topic_for,
                                     verify_graphic)
from headlinne.models import Reel, ReelBeat
from headlinne.render import graphics, motion, reel as reel_render


# --------------------------------------------------------------------------- #
# Figure verification
# --------------------------------------------------------------------------- #
def test_digits_ignores_separators_inside_a_number():
    assert _digits("$2,400 by 2026") == ["2400", "2026"]
    assert _digits("no numbers here") == []


def test_counter_survives_when_the_figure_is_in_the_source():
    device, data = verify_graphic("counter", {"value_label": "47%", "caption": "of trips"},
                                  "Some 47% of journeys are now electric.",
                                  allow_figures=True)
    assert device == "counter"
    assert data["value_label"] == "47%"


def test_counter_is_dropped_when_the_figure_is_invented():
    device, data = verify_graphic("counter", {"value_label": "63%"},
                                  "The report gave no percentage at all.",
                                  allow_figures=True)
    # A counter with no number is not a weaker graphic, it is nothing, so the
    # whole device goes rather than rendering an empty disc.
    assert device == ""
    assert data == {}


def test_bars_keep_their_shape_but_lose_an_unsupported_figure():
    device, data = verify_graphic(
        "bars",
        {"bars": [{"label": "Before", "weight": 0.4, "value_label": "12"},
                  {"label": "After", "weight": 1.0, "value_label": "999"}]},
        "Twelve firms were affected.".replace("Twelve", "12"),
        allow_figures=True)
    assert device == "bars"
    # The supported figure stays, the invented one is stripped, and both bars
    # survive so the comparison still reads.
    assert data["bars"][0]["value_label"] == "12"
    assert "value_label" not in data["bars"][1]
    assert len(data["bars"]) == 2


def test_education_reels_never_print_a_figure():
    # Educational examples are openly hypothetical. A hypothetical number drawn
    # as a chart stops looking hypothetical, so figures are stripped outright.
    device, data = verify_graphic(
        "bars", {"bars": [{"label": "Rent", "weight": 0.5, "value_label": "500"}]},
        "", allow_figures=False)
    assert device == "bars"
    assert "value_label" not in data["bars"][0]

    device, _ = verify_graphic("counter", {"value_label": "100"}, "",
                               allow_figures=False)
    assert device == ""


def test_label_only_devices_pass_through_untouched():
    payload = {"steps": ["Rates rise", "Banks charge more", "You pay more"]}
    for name in graphics.LABEL_ONLY_DEVICES:
        device, data = verify_graphic(name, dict(payload), "", allow_figures=False)
        assert device == name


def test_unknown_device_is_rejected():
    assert verify_graphic("piechart", {"x": 1}, "", allow_figures=True) == ("", {})


# --------------------------------------------------------------------------- #
# Beat assembly
# --------------------------------------------------------------------------- #
def test_beats_are_clamped_to_what_the_frame_can_carry():
    data = {"beats": [{"caption": "word " * 40, "detail": "detail " * 60}]}
    beats = _beats_from(data, source_text="", allow_figures=False)
    assert len(beats) == 1
    assert len(beats[0].caption) <= CAPTION_CHARS
    assert len(beats[0].detail) <= DETAIL_CHARS


def test_beats_without_a_caption_are_dropped():
    data = {"beats": [{"caption": "", "detail": "orphaned detail"},
                      {"caption": "A real beat"}]}
    beats = _beats_from(data, source_text="", allow_figures=False)
    assert [b.caption for b in beats] == ["A real beat"]


def test_forced_device_falls_back_to_the_models_own_payload():
    # The topic declares "bars" but the model wrote a flow payload. Rather than
    # ship a beat with no picture, the flow is used.
    data = {"beats": [{"caption": "The chain", "graphic": "flow",
                       "data": {"steps": ["one", "two", "three"]}}]}
    beats = _beats_from(data, source_text="", allow_figures=False,
                        forced_device="bars")
    assert beats[0].graphic == "flow"
    assert beats[0].role == "graphic"


# --------------------------------------------------------------------------- #
# Topic rotation
# --------------------------------------------------------------------------- #
def test_education_topics_cycle_without_repeating_inside_a_cycle():
    start = date(2026, 8, 10)
    seen = [topic_for(start + timedelta(days=i)).title
            for i in range(len(EDUCATION_TOPICS))]
    assert len(set(seen)) == len(EDUCATION_TOPICS)


def test_every_education_topic_names_a_real_device():
    for topic in EDUCATION_TOPICS:
        assert topic.graphic in graphics.DEVICES
        # Educational topics may never use the one device that exists purely to
        # print a figure.
        assert topic.graphic != "counter"


# --------------------------------------------------------------------------- #
# Pacing
# --------------------------------------------------------------------------- #
def _sample_reel(category: str = "Technology") -> Reel:
    return Reel(
        slot="reel_1", kind="news", category=category, title="A title",
        hook="A hook that fits",
        beats=[
            ReelBeat(role="hook", caption="A hook that fits",
                     detail="One line under it that adds the reason to stay."),
            ReelBeat(role="point", caption="What happened",
                     detail="A short sentence that says what actually took place."),
            ReelBeat(role="graphic", caption="The chain", graphic="flow",
                     data={"steps": ["First", "Then this", "So this"]}),
            ReelBeat(role="point", caption="Why it matters",
                     detail="The concrete effect on somebody's money or choices."),
            ReelBeat(role="payoff", caption="That is the mechanism"),
        ],
        caption="Caption.", hashtags=["Tech"], sources="Reuters, BBC +2",
        scheduled_time="2026-08-10T09:30:00+05:30")


def test_total_runtime_lands_inside_the_target_window():
    durations = reel_render.plan_durations(_sample_reel())
    total = sum(durations) + 2.6  # the outro
    assert REEL_MIN_SECONDS <= total <= REEL_MAX_SECONDS


def test_the_graphic_beat_gets_the_longest_cut():
    reel = _sample_reel()
    durations = reel_render.plan_durations(reel)
    graphic_index = next(i for i, b in enumerate(reel.beats) if b.graphic)
    # Measured by text alone a graphic beat wins the shortest slot in the reel,
    # which is backwards: half of it is spent animating the device in.
    assert durations[graphic_index] == max(durations)


def test_normalise_durations_respects_the_hard_ceiling():
    scaled = motion.normalise_durations([20.0] * 6, target=25.0, minimum=8.0,
                                        maximum=30.0)
    assert sum(scaled) <= 30.0 + 0.1


def test_beats_never_shrink_below_a_readable_cut():
    scaled = motion.normalise_durations([2.0] * 12, target=10.0, minimum=8.0,
                                        maximum=12.0)
    assert min(scaled) >= 1.2


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def _no_photos(_src):
    """Image loader used in tests: forces the designed brand panels, no network."""
    return None


def test_scenes_are_built_in_the_right_order():
    scenes = reel_render.build_scenes(_sample_reel(), _no_photos)
    kinds = [type(s).__name__ for s in scenes]
    assert kinds[0] == "HookScene"
    assert "GraphicScene" in kinds
    assert kinds[-1] == "OutroScene"
    # One scene per beat, plus the sign-off.
    assert len(scenes) == len(_sample_reel().beats) + 1


def test_every_scene_renders_at_the_reel_canvas_size():
    for category in ("Technology", "Finance", "Geopolitics"):
        scenes = reel_render.build_scenes(_sample_reel(category), _no_photos)
        for scene in scenes:
            scene.prepare()
            for t in (0.0, 0.5, 0.99):
                frame = scene.frame(t)
                assert frame.size == (REEL_W, REEL_H)
                assert frame.mode == "RGBA"


def test_progress_bar_runs_from_zero_to_one_across_the_reel():
    scenes = reel_render.build_scenes(_sample_reel(), _no_photos)
    assert scenes[0].progress_from == 0.0
    assert scenes[-1].progress_to == 1.0
    # Each scene picks up exactly where the previous one left off.
    for earlier, later in zip(scenes, scenes[1:]):
        assert abs(earlier.progress_to - later.progress_from) < 1e-9


def test_a_malformed_graphic_payload_does_not_kill_the_frame():
    reel = _sample_reel()
    reel.beats[2].data = {"steps": None}
    scenes = reel_render.build_scenes(reel, _no_photos)
    graphic_scene = next(s for s in scenes if type(s).__name__ == "GraphicScene")
    graphic_scene.prepare()
    # The caption still renders, the device just produces nothing.
    assert graphic_scene.frame(0.5).size == (REEL_W, REEL_H)


def test_every_device_renders_without_error():
    payloads = {
        "flow": {"steps": ["One", "Two", "Three"]},
        "split": {"left_title": "Before", "left_text": "How it used to work.",
                  "right_title": "After", "right_text": "How it works now."},
        "timeline": {"stops": ["Day one", "Week six", "Month six"],
                     "note": "The effect arrives in stages."},
        "bars": {"bars": [{"label": "Before", "weight": 0.4},
                          {"label": "After", "weight": 1.0, "value_label": "12"}]},
        "counter": {"value_label": "47%", "caption": "of all journeys"},
    }
    assert set(payloads) == set(graphics.DEVICES)
    for device, data in payloads.items():
        reel = _sample_reel()
        reel.beats[2].graphic = device
        reel.beats[2].data = data
        scene = next(s for s in reel_render.build_scenes(reel, _no_photos)
                     if type(s).__name__ == "GraphicScene")
        scene.prepare()
        for t in (0.2, 0.7, 0.99):
            assert scene.frame(t).size == (REEL_W, REEL_H)


def test_a_reel_without_video_is_only_rejected_when_rendering_was_asked_for():
    from headlinne.quality import check_reel

    reel = _sample_reel()
    reel.duration_seconds = 28.0
    assert not check_reel(reel).ok                       # no video file
    # `generate --no-render` produces scripts without video on purpose.
    assert check_reel(reel, require_media=False).ok


def test_a_reel_shorter_than_the_reels_tab_minimum_is_rejected():
    from headlinne.quality import check_reel

    reel = _sample_reel()
    reel.video_file = "reel_1.mp4"
    reel.duration_seconds = 4.0
    assert not check_reel(reel).ok


def test_counting_a_number_preserves_its_formatting():
    assert graphics.animate_number("$2,400", 0.0) == "$0"
    assert graphics.animate_number("$2,400", 1.0) == "$2,400"
    assert graphics.animate_number("47%", 1.0) == "47%"
    assert graphics.animate_number("2.4bn", 1.0) == "2.4bn"
    # A label with no number in it is left exactly as written.
    assert graphics.animate_number("no digits", 0.5) == "no digits"
