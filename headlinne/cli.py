"""Command-line entry point.

Usage:
  python -m headlinne generate                 # gather, write and render today
  python -m headlinne generate --no-render      # skip image and video rendering
  python -m headlinne generate --no-schedule    # do not schedule into Buffer
  python -m headlinne publish --target reel-1    # publish one slot
  python -m headlinne preview                    # render every format offline
  python -m headlinne preview --no-video         # ... but skip the reels
  python -m headlinne status                     # did it post, and did it reach?
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .logging_setup import get_logger

log = get_logger("cli")


def _cmd_generate(args: argparse.Namespace) -> int:
    from .pipeline import generate

    schedule = None
    if args.no_schedule:
        schedule = False
    generate(render=not args.no_render, schedule_buffer=schedule)
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    from .pipeline import publish

    publish(args.target)
    return 0


def _cmd_reddit(args: argparse.Namespace) -> int:
    """Reddit opportunity finder (read-only) and guarded single post."""
    from .reddit import find_opportunities, post_one

    if args.reddit_command == "find":
        opps = find_opportunities(limit=args.limit)
        print(f"Surfaced {len(opps)} opportunities. "
              f"Full review queue (JSON + Markdown) is in state/reddit_queue/.")
        for o in opps:
            tag = "PROMO" if o.mentions_headlinne else "help"
            print(f"  [{tag:5}] r/{o.thread.subreddit:16} id={o.thread.id}  "
                  f"{o.thread.title[:56]}")
        if opps:
            print("\nReview them, then post the good ones yourself, or with:\n"
                  "  python -m headlinne reddit post --id <ID> --confirm")
        return 0

    if args.reddit_command == "post":
        print(post_one(args.id, confirm=args.confirm))
        return 0

    return 1


def _cmd_status(args: argparse.Namespace) -> int:
    """Report whether the account is still generating, and still reaching.

    Exits non-zero when something is wrong, so this can be a CI step rather
    than something a person has to remember to look at. Nothing else in the
    system notices silence: contained failures are the right call for one bad
    format on one day, and the wrong call as a way of finding out that a
    fortnight went by without a reel.
    """
    from . import health

    report = health.scan(days=args.days)
    print(health.as_json(report) if args.json else health.format_report(report))
    return 1 if report.problems() else 0


def _cmd_preview(args: argparse.Namespace) -> int:
    """Render a sample carousel with mock content so you can check the design.

    Works fully offline: no Gemini calls and no network image fetches. Every
    plate therefore takes the fallback ladder down to a generated scene, which
    is the rung most worth checking by eye.
    """
    from .models import (Agreement, Conflict, InstagramCarousel, Slide,
                         Story, TwitterPost)
    from .render import render_carousel, render_twitter_card

    out_root = Path(args.out or "preview")

    # One story, argued across five slides. The mock carries a full agreement
    # record because half the furniture on a slide is derived from it: the
    # kicker, the masthead tone, Pip's pose and the whole source strip.
    story = Story(
        title="A SpaceX rocket just hit the Moon",
        summary="A four-tonne Falcon 9 upper stage struck the far side of the "
                "Moon at 8700 km/h. Two orbiters photographed the crater.",
        url="https://example.com/moon", category="Science", source="Reuters",
        tier=1.4, published_iso="2026-08-18T06:00:00+00:00",
        corroborating_sources=["AP", "Al Jazeera", "Space.com", "New Scientist"],
        verified=True,
        agreement=Agreement(
            reported=8, agree=8,
            outlets=["Reuters", "AP", "Al Jazeera", "Space.com",
                     "New Scientist", "Sky", "BBC", "Guardian"]),
    )
    slides = [
        Slide(role="cover", headline="A SpaceX rocket just hit the Moon",
              subtitle="8,700 km/h. Nobody meant to do it.", kicker="SCIENCE",
              pose="alert", say="Something hit the Moon.", index=1),
        Slide(role="scale", headline="", kicker="HOW BIG", figure="4",
              unit="tonnes", index=2,
              explanation="About the size of a school bus, travelling at "
                          "roughly six times the speed of a rifle bullet."),
        Slide(role="twist", kicker="THIS HAPPENED ONCE BEFORE", index=3,
              headline="In 2022 everyone blamed SpaceX. It was a Chinese rocket.",
              pose="puzzled", say="Here's the bit I love.",
              explanation="The correction took months. The original headline is "
                          "still the one most people remember."),
        Slide(role="sources", headline="", kicker="SOURCES", index=4,
              pose="verified", say="I read all eight. They agree.",
              explanation="Headlinne reads every outlet covering a story and "
                          "shows you where they agree, and where they do not."),
        Slide(role="cta", headline="", kicker="READ THE FULL STORY", index=5,
              pose="carry", say="Come and read it.",
              subtitle="Every source on this story, side by side."),
    ]
    carousel = InstagramCarousel(
        slot="instagram_1", category=story.category, num_slides=len(slides),
        title=slides[0].headline, slides=slides,
        caption="One story, explained. What did you make of it?",
        hashtags=["Science", "Space", "Headlinne"],
        scheduled_time="2026-08-18T16:00:00+05:30",
        story=story, story_url=story.url,
    )
    # No network: the loader returns None so every plate takes the fallback
    # ladder down to a generated scene, which is the rung most worth checking.
    produced = list(render_carousel(carousel, out_root / "carousel",
                                    image_loader=lambda _src: None))

    # The X cards. Four layouts, and which one a post earns is decided by the
    # sourcing rather than chosen by hand.
    disputed = Story(
        title="Same memo, two numbers", summary="", url="https://example.com/memo",
        category="Finance", source="Reuters", tier=1.4,
        published_iso="2026-08-18T06:00:00+00:00",
        corroborating_sources=["Financial Times"], verified=True,
        agreement=Agreement(reported=7, agree=3, conflict=4,
                            claim="12,000 jobs", claim_unit="jobs",
                            outlets=["Reuters", "Financial Times", "WSJ", "Sky"],
                            conflicts=[Conflict("Financial Times", "4,000 jobs")]),
    )
    x_news = TwitterPost(category="Science", post="", hashtags=[],
                         scheduled_time="", kind="news", lead=story.title)
    x_promo = TwitterPost(category="Promo", post="", hashtags=[],
                          scheduled_time="", kind="promo",
                          lead="Every source, side by side")
    produced.append(render_twitter_card(x_news, out_root / "x" / "receipt.png",
                                        story=story))
    produced.append(render_twitter_card(x_news, out_root / "x" / "compare.png",
                                        story=disputed))
    produced.append(render_twitter_card(x_promo, out_root / "x" / "promo.png"))

    produced.append(_preview_story_card(out_root))
    if not args.no_video:
        produced.extend(_preview_reels(out_root, args))

    print("Rendered preview slides and cards:")
    for p in produced:
        print("  ", p)
    return 0


def _preview_story_card(out_root: Path) -> Path:
    """Render a sample story card so the daily format can be checked offline."""
    from .models import Agreement, StoryCard, StoryStep, Story
    from .render import render_story_card

    # The card carries its story so the source strip, the masthead tone and
    # Pip's pose all render. Without one it draws a headline and a rail and
    # none of the furniture that makes it a Headlinne card.
    story = Story(
        title="The rate decision that changes your loan", summary="",
        url="https://example.com/rates", category="Finance", source="Reuters",
        tier=1.4, published_iso="2026-08-18T06:00:00+00:00",
        corroborating_sources=["BBC Business", "CNBC", "Sky Business"],
        verified=True,
        agreement=Agreement(reported=6, agree=4,
                            outlets=["Reuters", "BBC Business", "CNBC",
                                     "Sky Business", "MarketWatch", "Guardian"]),
    )

    card = StoryCard(
        slot="story_card", category="Finance",
        headline="The rate decision that changes your loan",
        standfirst="A single vote this week reaches your monthly payment by autumn.",
        steps=[
            StoryStep("What happened",
                      "The central bank held rates steady for a fourth meeting, "
                      "against expectations of a cut."),
            StoryStep("How we got here",
                      "Inflation fell fast last year, then stalled just above "
                      "target, which split the committee."),
            StoryStep("Why it matters",
                      "Tracker mortgages and business loans stay where they are, "
                      "so household budgets get no relief this quarter."),
            StoryStep("What to watch",
                      "The next inflation print. Two soft readings in a row would "
                      "put a cut back on the table."),
        ],
        caption="A sample caption.", hashtags=["Finance"],
        sources="Reuters, BBC +2",
        scheduled_time="2026-08-10T21:30:00+05:30",
    )
    return render_story_card(card, out_root / "story_card" / "story_card.png",
                             story=story)


def _preview_reels(out_root: Path, args: argparse.Namespace | None = None) -> list[Path]:
    """Render the daily reel, if ffmpeg is available.

    The real layout, the real plate ladder and the real pacing, so this is the
    honest way to check the design without spending a Gemini call or waiting for
    a scheduled run. It goes through the visual gate first, exactly as the
    pipeline does, so a preview that would not have published says so.
    """
    from .models import Agreement, Reel, ReelBeat, Story
    from .quality import visual
    from .render import render_reel
    from .render.motion import ffmpeg_available
    from .render.reel import ReelFrames, plan_durations

    if not ffmpeg_available():
        print("Skipping the reel preview: ffmpeg not found. Install it, "
              "or run `pip install imageio-ffmpeg`, then try again.")
        return []

    story = Story(
        title="A SpaceX rocket just hit the Moon",
        summary="A four-tonne Falcon 9 upper stage struck the far side of the "
                "Moon at 8700 km/h. Two orbiters photographed the crater.",
        url="https://example.com/moon", category="Science", source="Reuters",
        tier=1.4, published_iso="2026-08-18T06:00:00+00:00",
        corroborating_sources=["AP", "Al Jazeera", "Space.com", "New Scientist"],
        verified=True,
        agreement=Agreement(
            reported=8, agree=8,
            outlets=["Reuters", "AP", "Al Jazeera", "Space.com",
                     "New Scientist", "Sky", "BBC", "Guardian"]),
    )
    reel = Reel(
        slot="reel_1", kind="news", category="Science", title="Moon impact",
        hook="A four-tonne rocket stage just hit the Moon",
        beats=[
            ReelBeat(role="hook", chapter="What happened", pose="walk",
                     caption="On Tuesday a *four-tonne* rocket stage struck the Moon.",
                     detail="A Falcon 9 second stage.",
                     narration="On Tuesday a four-tonne rocket stage struck the Moon."),
            ReelBeat(role="point", chapter="Why", pose="point",
                     say="Not deliberate.",
                     caption="It was up there because solar activity pulled it *off course*.",
                     detail="Nobody planned this.",
                     narration="It was up there because solar activity had pulled it off course."),
            ReelBeat(role="graphic", chapter="Where", pose="present",
                     plates=["story"],
                     caption="It came down near *Einstein Crater*, on the far side.",
                     detail="Out of view from Earth.",
                     narration="It came down near Einstein Crater, on the far side."),
            ReelBeat(role="graphic", chapter="How fast", pose="jump",
                     graphic="counter", data={"value": "8700"},
                     caption="kilometres per hour.",
                     detail="About six times a rifle bullet.",
                     narration="Eight thousand seven hundred kilometres per hour."),
            ReelBeat(role="point", chapter="The correction", pose="talk",
                     caption="That one was reported as *SpaceX* too.",
                     detail="Every major outlet ran it.",
                     narration="The last one was reported as SpaceX too."),
            ReelBeat(role="outro", chapter="Read it", pose="cta",
                     say="Come and read it.",
                     caption="The full story is on *headlinne.com*.",
                     detail="Every source, side by side.",
                     narration="The full story is on headlinne dot com."),
        ],
        caption="A sample caption.", hashtags=["Science"],
        sources="Reuters · AP · Al Jazeera · Space.com +4",
        dateline="TUE 18 AUG", story=story,
        scheduled_time="2026-08-18T09:30:00+05:30",
    )

    plan_durations(reel)
    pace = visual.check_pace(reel)
    frames = ReelFrames(reel, story, loader=lambda _src: None)
    geometry = visual.check_reel_frames(frames, sample_every=12, story=story)
    for message in pace.errors + geometry.errors:
        print(f"  visual gate: {message}")
    if not (pace.ok and geometry.ok):
        print("  the preview reel would not have published; not encoding it.")
        return []

    # voiceover=False on purpose. A preview is for checking the layout and the
    # cut points, both of which are honest at reading speed, and it should never
    # spend a speech request just because a key happens to be in the environment.
    video = render_reel(reel, out_root / "reels", story=story,
                        image_loader=lambda _src: None, voiceover=False)
    cover = Path(reel.cover_file) if reel.cover_file else None
    print(f"  reel {reel.slot}: {reel.duration_seconds:.1f}s, "
          f"{geometry.checks} geometry checks passed")
    return [p for p in (video, cover) if p]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="headlinne", description="Headlinne social automation")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="gather, generate, render and save today's content")
    g.add_argument("--no-render", action="store_true", help="skip carousel image rendering")
    g.add_argument("--no-schedule", action="store_true", help="do not schedule X/LinkedIn into Buffer")
    g.set_defaults(func=_cmd_generate)

    p = sub.add_parser("publish", help="publish one slot for today")
    p.add_argument("--target", required=True,
                   choices=["x-1", "x-2", "linkedin", "instagram-1", "instagram-2",
                            "reel-1", "reel-2", "story-card"],
                   help="which slot to publish")
    p.set_defaults(func=_cmd_publish)

    pv = sub.add_parser("preview",
                        help="render sample carousels, cards, the story card "
                             "and both reels offline")
    pv.add_argument("--out", help="output folder (default: preview)")
    pv.add_argument("--no-video", action="store_true",
                    help="skip the reel previews (they need ffmpeg and take "
                         "about two minutes each)")
    pv.set_defaults(func=_cmd_preview)

    st = sub.add_parser("status",
                        help="is the account still generating, and still reaching?")
    st.add_argument("--days", type=int, default=30,
                    help="how many days back to look (default 30)")
    st.add_argument("--json", action="store_true", help="machine-readable output")
    st.set_defaults(func=_cmd_status)

    r = sub.add_parser("reddit",
                       help="find relevant Reddit threads and draft helpful replies for review")
    rsub = r.add_subparsers(dest="reddit_command", required=True)
    rf = rsub.add_parser("find", help="build today's review queue (read-only, never posts)")
    rf.add_argument("--limit", type=int, default=None,
                    help="max opportunities to surface (clamped to the safe cap)")
    rf.set_defaults(func=_cmd_reddit)
    rp = rsub.add_parser("post", help="post ONE reviewed draft from today's queue")
    rp.add_argument("--id", required=True, help="thread id shown in the review queue")
    rp.add_argument("--confirm", action="store_true",
                    help="required: confirms you have reviewed this specific draft")
    rp.set_defaults(func=_cmd_reddit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    except Exception as exc:  # noqa: BLE001
        log.error("command failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
