"""The daily reel: pacing, geometry, and the guarantees that must never break.

The reel is one continuous scene rather than one scene per beat. Pip walks
across the whole runtime and the progress bar fills across it, so both are
functions of absolute time; cutting the render at beat boundaries would make
every segment need to know where the previous one left him.
"""

from datetime import date

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


# --------------------------------------------------------------------------- #
# Graphic devices
# --------------------------------------------------------------------------- #
# render/graphics.py has had bars, counter, flow, timeline and split since the
# format was designed. Nothing ever called draw_device: the generator validated
# a device, wrote it into reels.json, and the renderer drew nothing where it
# should have been. Across the 23 reels in content/, 163 of 170 beats carried
# no graphic and the seven that did rendered as blank paper anyway. Both halves
# of that are pinned here - the generator must be able to produce a device, and
# the renderer must actually put it on the frame.
def _flow_reel():
    reel = _reel()
    beat = reel.beats[1]
    beat.graphic = "flow"
    beat.data = {"steps": ["Launched in 2015", "Solar activity drags it",
                           "Orbit decays into the Moon"]}
    beat.plates = []
    return reel


def test_a_graphic_beat_puts_something_on_the_stage():
    from headlinne.render.reel import GRAPHIC_BOTTOM, GRAPHIC_TOP

    frames = ReelFrames(_flow_reel(), _story(), loader=lambda _s: None)
    bare = frames.render(1.5).crop((0, GRAPHIC_TOP, REEL_W, GRAPHIC_BOTTOM))
    drawn = frames.render(4.9).crop((0, GRAPHIC_TOP, REEL_W, GRAPHIC_BOTTOM))

    changed = sum(1 for a, b in zip(bare.getdata(), drawn.getdata()) if a != b)
    assert changed > 20000, (
        f"the flow device changed only {changed} pixels on the stage - "
        f"draw_device is not being reached")


def test_the_daily_reel_can_produce_every_device_and_not_just_a_counter():
    """The daily prompt offered a bare "counter" field, so five of the six
    devices were unreachable from the only reel that publishes."""
    from headlinne.generate.reel import _daily_beats

    data = {"beats": [
        {"chapter": "Why", "caption": "c", "detail": "d", "narration": "n",
         "graphic": "flow", "data": {"steps": ["one", "two", "three"]}},
        {"chapter": "Versus", "caption": "c", "detail": "d", "narration": "n",
         "graphic": "split", "data": {"left_title": "Was", "left_text": "a",
                                      "right_title": "Is", "right_text": "b"}},
        {"chapter": "Read it", "caption": "c", "detail": "d", "narration": "n"},
    ]}
    beats = _daily_beats(data, _story())

    assert [b.graphic for b in beats] == ["flow", "split", ""]
    assert beats[0].data["steps"][0] == "one"


def test_the_number_of_graphic_beats_is_capped():
    """Density is a design decision. The prompt asks for two or three; the cap
    is what makes that true when the model returns seven."""
    from headlinne.generate.reel import MAX_GRAPHIC_BEATS, _daily_beats

    data = {"beats": [
        {"chapter": f"B{i}", "caption": "c", "detail": "d", "narration": "n",
         "graphic": "flow", "data": {"steps": ["one", "two", "three"]}}
        for i in range(7)
    ]}
    beats = _daily_beats(data, _story())

    assert sum(1 for b in beats if b.graphic) == MAX_GRAPHIC_BEATS
    assert all(b.caption for b in beats), "a capped beat keeps its words"


def test_a_device_panel_is_legible_on_the_ground_it_is_drawn_on():
    """The chips were filled INK_SOFT and lettered TEXT_PRIMARY: 1.11:1. Each
    colour is perfectly legal against paper, which is why every contrast check
    in the suite passed while the text was invisible."""
    from headlinne.render import theme
    from headlinne.render.graphics import panel_colours

    for dark in (False, True):
        panel = panel_colours(theme.hex_to_rgb(theme.BRAND_TERRACOTTA), dark)
        ratio = theme.contrast_ratio(panel["body"], panel["fill"])
        assert ratio >= 4.5, f"panel body is {ratio:.2f}:1 on its own fill"


def test_a_graphic_beat_drops_pip_rather_than_sharing_the_stage():
    frames = ReelFrames(_flow_reel(), _story(), loader=lambda _s: None)
    frames.render(4.9)
    names = {entry[0] for entry in frames.trace}
    assert any(n.startswith("graphic-") for n in names)
    assert "pip" not in names, "Pip and the diagram both shrink if they share"


# --------------------------------------------------------------------------- #
# Which story the reel leads with
# --------------------------------------------------------------------------- #
# "Breaking" here means three or more outlets inside eight hours, which measures
# wire syndication rather than importance. It fired on 16 of the 38 days in
# content/ and was less interesting than the day's best story on 13 of them.
def _digest_with(breaking, others):
    from headlinne.models import NewsDigest

    by_category: dict[str, list] = {}
    for s in [*others, breaking]:
        if s is not None:
            by_category.setdefault(s.category, []).append(s)
    return NewsDigest(day="2026-09-06", by_category=by_category,
                      category_weights={}, dominant_category="Science",
                      breaking=breaking)


def _wire(title, score, summary=""):
    s = _story()
    s.title, s.summary, s.url, s.score = title, summary, f"http://w/{score}", score
    s.category = "Geopolitics"
    return s


def _find(title, score, summary=""):
    s = _story()
    s.title, s.summary, s.url, s.score = title, summary, f"http://f/{score}", score
    s.category = "Science"
    return s


def test_a_dull_wire_story_does_not_take_the_reel_off_a_real_one():
    from headlinne.generate.reel import lead_story

    diary = _wire("Prince William to attend King Harald's funeral in Norway", 9.0)
    find = _find("FAST finds two mysterious hydrogen clouds with no visible stars",
                 12.77)
    assert lead_story(_digest_with(diary, [find])) is find


def test_breaking_still_wins_when_it_is_the_best_thing_available():
    """The original reasoning holds when the breaking story is worth watching:
    it starts with an audience already searching for it."""
    from headlinne.generate.reel import lead_story

    big = _wire("Meta fined $567m in largest child safety ruling against social "
                "media", 11.0)
    quiet = _find("Researchers tune a mineral surface to trigger ice formation", 9.0)
    assert lead_story(_digest_with(big, [quiet])) is big


def test_the_reel_never_repeats_a_story_it_was_told_to_skip():
    from headlinne.generate.reel import lead_story

    diary = _wire("Prince William to attend King Harald's funeral", 9.0)
    find = _find("Seven new frog species were found beneath the forest floor", 12.0)
    other = _find("A human-only gene may explain our brainpower", 11.0,
                  "The first gene found only in humans appears to drive the "
                  "brain growth that separates us from other primates.")
    picked = lead_story(_digest_with(diary, [find, other]),
                        exclude_urls={find.url})
    assert picked is other


# --------------------------------------------------------------------------- #
# A day never loses its only discovery surface
# --------------------------------------------------------------------------- #
def test_a_failed_news_reel_falls_back_to_the_evergreen_one():
    """Reels are the only surface that reaches people who do not follow, and
    seven of thirty days published none because this one call raised."""
    from headlinne.generate import reel as gen

    story = _find("FAST finds two mysterious hydrogen clouds", 12.0)

    class _Client:
        def __init__(self):
            self.calls = 0

        def generate_json(self, *, system, prompt, **kw):
            self.calls += 1
            if "THE STORY" in prompt:          # the daily news prompt
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return {"beats": [{"chapter": f"B{i}", "caption": f"line {i}",
                               "detail": "d", "narration": "n"}
                              for i in range(5)],
                    "caption": "c", "hashtags": ["Science"]}

    client = _Client()
    out = gen.generate_daily(client, _digest_with(None, [story]), date(2026, 9, 6))

    assert out is not None, "the day published no reel at all"
    assert out.slot == "reel_1"
    assert client.calls == 2, "it should have tried the news reel first"


def test_a_comparison_uses_two_hues_and_not_one_dimmed_one():
    """A two-bar chart drawn in a single hue says "this, and this dead thing".
    Both sides of a comparison are real, so the far side gets its own colour -
    and it has to be legible in its own right, which the old accent-mixed-with-
    ink never was."""
    from headlinne.render import theme
    from headlinne.render.graphics import counterpart

    accent = theme.hex_to_rgb(theme.BRAND_TERRACOTTA)
    other = counterpart(accent)

    assert other != accent
    assert theme.contrast_ratio(other, theme.SURFACE) >= 4.5, \
        "the counterpart carries labels, so it clears the body floor"
    # And it never collides with itself when the accent already is violet.
    assert counterpart(other) != other


def test_the_line_reveals_across_the_cut_rather_than_the_first_third():
    """With a narration track the beat lasts exactly as long as the spoken line,
    so a reveal that finished at 34% left the frame motionless for most of every
    beat."""
    assert reel_render.LINE_REVEAL_FRACTION >= 0.6


def test_the_cover_frame_still_lands_after_the_line_has_settled():
    """The cover is the reel's permanent thumbnail, and it is derived from the
    reveal fraction - so lengthening the reveal must not freeze a half-written
    sentence onto the profile grid."""
    for seconds in (1.6, 3.0, 6.0, 9.0):
        reel = _reel()
        reel.beats[0].seconds = seconds
        offset = reel_render.cover_offset_ms(reel) / 1000.0
        assert offset < seconds, f"cover at {offset:.2f}s is outside a {seconds}s beat"
        assert offset >= min(seconds * 0.5, seconds - 0.2), \
            f"cover at {offset:.2f}s lands before the line finishes"
