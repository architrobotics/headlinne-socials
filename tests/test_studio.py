"""The studio reel (render/studio): sets, papercraft Pip and the paper overlays.

The style copies the @nocodealex reels the founder sent on 2026-10-05. These
tests hold the parts of it that must not drift: it passes the same geometry
gate as every reel, it never dresses a sensitive story, it never prints a
figure the source does not contain, and the words on screen follow the voice.
"""

from __future__ import annotations

from headlinne.models import Reel, ReelBeat
from tests.helpers import make_story


def _story(sensitive=False, title="Brazil election goes to run-off as "
           "Flávio Bolsonaro wins first round"):
    s = make_story(title, category="Geopolitics", source="BBC World",
                   summary="Bolsonaro took 43% of the vote against Lula's 41%, "
                           "forcing a second round on 25 October.",
                   corroborating=["Guardian World", "Al Jazeera"])
    s.sensitive = sensitive
    return s


def _reel(story, **overrides):
    beats = [
        ReelBeat(role="hook", chapter="Brazil goes to a run-off", seconds=3.2,
                 narration="Brazil voted on Sunday, and nobody won outright.",
                 caption="Nobody won outright", pose="present",
                 stat={"value": "43%", "label": "first-round vote"}),
        ReelBeat(role="point", chapter="Who came first", seconds=3.6,
                 narration="Flávio Bolsonaro finished first, short of a majority.",
                 caption="Bolsonaro first", pose="talk",
                 fact="Run-off set for 25 October", scene={"set": "parliament"}),
        ReelBeat(role="point", chapter="Who came first", seconds=3.0,
                 narration="So the top two go head to head again.",
                 caption="Top two again", pose="point", stamp="RUN-OFF",
                 stamp_tone="bad"),
        ReelBeat(role="graphic", chapter="How a run-off works", seconds=3.4,
                 narration="Round one narrows the field. Round two picks the winner.",
                 caption="Two rounds", graphic="flow",
                 data={"steps": ["Round one", "Top two remain", "Run-off decides"]}),
        ReelBeat(role="outro", chapter="Follow the run-off", seconds=3.0,
                 narration="Follow it with us at headlinne dot com.",
                 caption="headlinne.com", pose="cta"),
    ]
    reel = Reel(slot="reel_1", kind="news", category="Geopolitics",
                title=story.title, hook="Brazil goes to a run-off", beats=beats,
                caption="Brazil heads to a second round.\nWho wins?\n",
                hashtags=[], scheduled_time="",
                sources="BBC · Guardian · Al Jazeera", story=story)
    for k, v in overrides.items():
        setattr(reel, k, v)
    return reel


def test_the_studio_reel_passes_the_geometry_gate():
    from headlinne.quality import visual
    from headlinne.render.studio.frames import StudioFrames

    story = _story()
    frames = StudioFrames(_reel(story), story)
    report = visual.check_reel_frames(frames, sample_every=20, story=story)
    assert report.ok, report.errors[:5]
    assert report.checks > 100


def test_every_furniture_piece_appears_and_is_traced():
    from headlinne.render.studio.frames import StudioFrames

    story = _story()
    frames = StudioFrames(_reel(story), story)
    seen = set()
    for i in range(0, int(frames.duration * 30), 6):
        frames.render(i / 30)
        seen |= {name for name, *_ in frames.trace}
    for piece in ("title", "stat", "source", "bleed-lowerthird", "stamp",
                  "chips", "graphic-flow", "comment"):
        assert piece in seen, piece


def test_a_sensitive_story_gets_no_pip_no_stamp_and_a_sober_set():
    from headlinne.render.studio import direction, sets
    from headlinne.render.studio.frames import StudioFrames

    story = _story(sensitive=True, title="Earthquake kills dozens as rescuers "
                   "search collapsed buildings")
    reel = _reel(story)
    reel.beats[1].scene = {"set": "street"}       # asked for; must be refused
    looks = direction.plan(reel, story)
    assert all(look.pose == "" for look in looks)
    assert all(look.spec.name in sets.SOBER_SETS for look in looks)
    frames = StudioFrames(reel, story)
    for i in range(0, int(frames.duration * 30), 10):
        frames.render(i / 30)
        assert not any(name == "stamp" for name, *_ in frames.trace)


def test_the_set_follows_the_story():
    from headlinne.render.studio.direction import classify

    assert classify("Brazil election goes to run-off") == "parliament"
    assert classify("Supreme court allows Trump to resume deportations") == "courtroom"
    assert classify("G7 to release 100 million barrels of oil") == "harbour"
    assert classify("Tens of thousands protest in Spain over housing") == "street"
    assert classify("OpenAI safety leader quits") == "server"
    assert classify("Something with no vocabulary", "Finance") == "trading"


def test_a_chapter_change_changes_the_set_and_an_unknown_set_is_replaced():
    from headlinne.render.studio import direction

    story = _story()
    reel = _reel(story)
    reel.beats[0].scene = {"set": "volcano-lair"}         # not in the vocabulary
    looks = direction.plan(reel, story)
    names = [look.spec.name for look in looks]
    assert names[0] == "parliament"                      # replaced from the story
    assert names[1] == names[2]                          # same chapter, same set
    assert looks[2].chapter_start is False
    assert len(set(names)) >= 2                          # never one room all reel
    assert looks[3].spec.board                           # the graphic beat


def test_the_hat_sits_on_his_head_in_every_frame_of_every_pose():
    """A squash frame drops the crown's outline row; the hat used to land on
    his chest in the cheer cycle because it was anchored to that row."""
    from headlinne.render import theme
    from headlinne.render.studio import voxel

    for pose in ("cheer", "talk", "point", "present", "bounce", "jump", "nod"):
        for grid in theme.CYCLES[pose]():
            rows = voxel._rows(voxel.with_hat(grid, "press"))
            hat = [i for i, r in enumerate(rows) if "D" in r]
            cream = next(i for i, r in enumerate(rows) if "C" in r)
            assert hat and max(hat) < cream, (pose, max(hat), cream)


def test_the_outline_is_gone_from_the_papercraft_figure():
    from headlinne.render import pip
    from headlinne.render.studio import voxel

    cells = voxel._strip_outline(voxel._rows(pip.SPRITES["idle"]))
    h, w = len(cells), pip.W
    for y in range(h):
        for x in range(w):
            if cells[y][x] != "K":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                assert 0 <= nx < w and 0 <= ny < h and cells[ny][nx] != ".", (x, y)


def test_chips_page_the_spoken_line_in_order_inside_the_beat():
    from headlinne.render.studio.frames import StudioFrames, group_words

    groups = group_words("Brazil voted on Sunday, and nobody won outright.")
    assert groups[0] == ["Brazil", "voted", "on"]
    assert ["Sunday"] in groups                          # breaks at the comma
    assert all(len(g) <= 3 for g in groups)
    assert all("," not in w and "." not in w for g in groups for w in g)

    story = _story()
    frames = StudioFrames(_reel(story, has_voiceover=True), story)
    assert frames._groups[0][0][1] == ["Brazil", "voted", "on"]   # the narration
    for index in range(len(frames.reel.beats)):
        start, end = frames._beat_span(index)
        times = [t for t, _ in frames._groups[index]]
        assert times == sorted(times)
        assert all(start <= t < end for t in times)


def test_a_stat_or_fact_the_source_does_not_contain_is_dropped():
    from headlinne.generate.reel import _digits, verified_fact, verified_stat

    digits = set(_digits("Bolsonaro took 43% of the vote against Lula's 41%"))
    assert verified_stat({"value": "43%", "label": "vote"}, digits,
                         allow_figures=True)["value"] == "43%"
    assert verified_stat({"value": "52%", "label": "vote"}, digits,
                         allow_figures=True) == {}
    assert verified_stat({"value": "43%"}, digits, allow_figures=False) == {}
    assert verified_stat({"value": "a lot"}, digits, allow_figures=True) == {}
    assert verified_fact("Lula took 41%", digits, allow_figures=True)
    assert verified_fact("Turnout hit 79%", digits, allow_figures=True) == ""
    assert verified_fact("Run-off is next", digits, allow_figures=True)


def test_the_daily_beats_cap_stamps_and_keep_them_off_sensitive_stories():
    from headlinne.generate.reel import _daily_beats

    raw = {"beats": [
        {"chapter": "One", "caption": "a", "narration": "a", "stamp": "BANNED",
         "stamp_tone": "bad", "scene": {"set": "Parliament", "hat": "press"}},
        {"chapter": "Two", "caption": "b", "narration": "b", "stamp": "AGAIN"},
        {"chapter": "Three", "caption": "c", "narration": "c",
         "stamp": "TWO WORDS"},
    ]}
    beats = _daily_beats(raw, _story())
    assert [b.stamp for b in beats] == ["BANNED", "", ""]
    assert beats[0].scene == {"set": "parliament", "hat": "press"}
    sober = _daily_beats(raw, _story(sensitive=True))
    assert all(not b.stamp for b in sober)


def test_the_studio_style_is_the_default_and_paper_is_still_there():
    from headlinne.render.reel import ReelFrames, reel_frames
    from headlinne.render.studio.frames import StudioFrames

    story = _story()
    assert isinstance(reel_frames(_reel(story), story), StudioFrames)
    assert isinstance(reel_frames(_reel(story), story, style="paper"), ReelFrames)


def test_every_set_builds_with_and_without_a_board():
    from headlinne.render.studio import sets

    for name in sets.SETS:
        for board in (False, True):
            built = sets.build(sets.SetSpec(name=name, board=board))
            assert built.back.size == (sets.SET_W, sets.SET_H)
            if board:
                assert built.board is not None, name


def test_a_silent_reel_pages_the_caption_not_the_narration():
    """Without a voice the beat is paced for reading, and twenty spoken words
    paged in silence run at nearly 300 wpm."""
    from headlinne.render.studio.frames import StudioFrames

    story = _story()
    frames = StudioFrames(_reel(story, has_voiceover=False), story)
    assert frames._groups[0][0][1] == ["Nobody", "won", "outright"]


# --------------------------------------------------------------------------- #
# The carousel in the studio style
# --------------------------------------------------------------------------- #
def _carousel(story):
    from headlinne.models import InstagramCarousel, Slide

    slides = [
        Slide(role="cover", headline="Brazil heads to a run-off",
              subtitle="Nobody won outright.", kicker="WORLD", pose="alert",
              say="Round two."),
        Slide(role="scale", headline="", kicker="HOW BIG", figure="43%",
              unit="of the vote", explanation="Bolsonaro's first-round share."),
        Slide(role="twist", headline="The run-off is on 25 October",
              explanation="Three weeks of campaigning left.", pose="puzzled",
              say="Close one."),
        Slide(role="sources", headline="", kicker="SOURCES", pose="verified"),
        Slide(role="cta", headline="", kicker="READ THE FULL STORY", pose="carry"),
    ]
    return InstagramCarousel(slot="instagram_1", category="Geopolitics",
                             num_slides=5, title=slides[0].headline, slides=slides,
                             caption="x", hashtags=[], scheduled_time="",
                             story=story, story_url=story.url)


def test_the_studio_carousel_renders_five_slides_that_pass_the_gate(tmp_path):
    from PIL import Image

    from headlinne.config import SLIDE_H, SLIDE_W
    from headlinne.quality import visual
    from headlinne.render.carousel import render_carousel

    story = _story()
    car = _carousel(story)
    paths = render_carousel(car, tmp_path, image_loader=lambda _s: None,
                            style="studio")
    images = [Image.open(p) for p in paths]
    assert len(images) == 5
    assert all(im.size == (SLIDE_W, SLIDE_H) for im in images)
    assert visual.check_carousel(car, images).ok


def test_a_sensitive_carousel_carries_no_pip(tmp_path):
    from headlinne.render.carousel import render_carousel

    story = _story(sensitive=True, title="Earthquake kills dozens")
    car = _carousel(story)
    render_carousel(car, tmp_path, image_loader=lambda _s: None, style="studio")
    assert all(not s.pose and not s.say for s in car.slides)


def test_a_studio_carousel_failure_falls_back_to_paper(tmp_path, monkeypatch):
    from headlinne.render import carousel as carousel_mod
    from headlinne.render.studio import carousel as studio_carousel

    def boom(*_a, **_k):
        raise RuntimeError("set builder fell over")

    monkeypatch.setattr(studio_carousel, "render_carousel", boom)
    paths = carousel_mod.render_carousel(_carousel(_story()), tmp_path,
                                         image_loader=lambda _s: None,
                                         style="studio")
    assert len(paths) == 5


def test_a_prepared_reel_is_rendered_from_the_days_file_and_saved_back(monkeypatch):
    """render-reel: the hand-written reel goes through the same render path
    as a generated one, and the result lands back in the day's reels.json."""
    from datetime import date

    from headlinne import pipeline

    story = _story()
    first, second = _reel(story), _reel(story)
    second.slot = "reel_2"
    saved = {}
    monkeypatch.setattr(pipeline.storage, "load_reels", lambda day: [first, second])
    monkeypatch.setattr(pipeline.storage, "save_reels",
                        lambda day, reels: saved.setdefault("reels", reels))

    def fake_render(day, reels):
        for r in reels:
            r.video_file, r.duration_seconds = "reel_2.mp4", 31.0
        return reels

    monkeypatch.setattr(pipeline, "_render_reels", fake_render)
    assert pipeline.render_prepared_reel("reel-2", date(2026, 10, 5))
    assert [r.slot for r in saved["reels"]] == ["reel_1", "reel_2"]
    assert saved["reels"][1].video_file == "reel_2.mp4"
    assert saved["reels"][0].video_file is None          # the other slot untouched
