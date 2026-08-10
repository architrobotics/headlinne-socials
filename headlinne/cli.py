"""Command-line entry point.

Usage:
  python -m headlinne generate                 # gather, write and render today
  python -m headlinne generate --no-render      # skip image and video rendering
  python -m headlinne generate --no-schedule    # do not schedule into Buffer
  python -m headlinne publish --target reel-1    # publish one slot
  python -m headlinne preview                    # render every format offline
  python -m headlinne preview --no-video         # ... but skip the reels
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


def _cmd_preview(args: argparse.Namespace) -> int:
    """Render a sample carousel with mock content so you can check the design.

    Works fully offline: no Gemini calls and no network image fetches (the
    renderer falls back to clean branded gradients when an image is missing).
    """
    from .models import InstagramCarousel, Slide, TwitterPost
    from .render import render_carousel, render_twitter_card

    out_root = Path(args.out or "preview")
    samples = {
        "Technology": ("The AI chip race just moved on-device",
                       "Three shifts that change what your phone can do without the cloud."),
        "Geopolitics": ("A tense week reshapes three borders",
                        "What actually happened, and why it matters beyond the headlines."),
    }
    mock_stories = [
        ("A major phone maker shows a new AI chip",
         "It promises faster on-device features while using less battery. More AI could now run without the cloud.",
         "Reuters, BBC +2"),
        ("A big cloud outage briefly hit popular apps",
         "Several services went dark for a few hours. It is a reminder of how much the internet leans on a few providers.",
         "The Verge, AP"),
        ("Fresh rules are proposed for AI labelling",
         "Regulators want clearer tags on AI made content. Platforms will need to adjust how features ship.",
         "Guardian +3"),
    ]

    produced = []
    for cat, (title, hook) in samples.items():
        slides = [Slide(role="cover", headline=title, subtitle=hook, image_url=None)]
        for i, (h, e, src) in enumerate(mock_stories, 1):
            slides.append(Slide(role="story", headline=h, explanation=e,
                                sources=src, index=i, image_url=None))
        slides.append(Slide(role="cta", headline="That's your brief for today.",
                            subtitle="Personalised news, minus the noise."))
        carousel = InstagramCarousel(
            slot="instagram_1", category=cat, num_slides=len(slides),
            title=title, slides=slides,
            caption="A quick look at today's biggest stories. Read more on HEADLINNE.com.",
            hashtags=["News", "Headlinne"], scheduled_time="2026-07-21T16:00:00+05:30",
        )
        out_dir = out_root / cat.lower()
        paths = render_carousel(carousel, out_dir)
        produced.extend(paths)

    # Sample X (Twitter) cards: one news roundup, one feature/promo.
    x_news = TwitterPost(
        category="Tech", post="", hashtags=[], scheduled_time="", kind="news",
        lead="AI just moved onto your phone",
        items=["A major maker unveiled an on-device AI chip",
               "A big cloud outage briefly hit popular apps",
               "New rules proposed for labelling AI content"],
    )
    x_promo = TwitterPost(
        category="Promo", post="", hashtags=[], scheduled_time="", kind="promo",
        lead="Ask the news a question, get answers with sources",
    )
    produced.append(render_twitter_card(x_news, out_root / "x" / "news_card.png"))
    produced.append(render_twitter_card(x_promo, out_root / "x" / "promo_card.png"))

    produced.append(_preview_story_card(out_root))
    if not args.no_video:
        produced.extend(_preview_reels(out_root, args))

    print("Rendered preview slides and cards:")
    for p in produced:
        print("  ", p)
    return 0


def _preview_story_card(out_root: Path) -> Path:
    """Render a sample story card so the daily format can be checked offline."""
    from .models import StoryCard, StoryStep
    from .render import render_story_card

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
    return render_story_card(card, out_root / "story_card" / "story_card.png")


def _preview_reels(out_root: Path, args: argparse.Namespace | None = None) -> list[Path]:
    """Render one sample reel of each kind, if ffmpeg is available.

    Uses the real layouts and a real graphic device, so this is the honest way
    to check the pacing and the type sizes without spending a Gemini call or
    waiting for a scheduled run.
    """
    from .models import Reel, ReelBeat
    from .render import render_reel
    from .render.motion import ffmpeg_available

    args = args or argparse.Namespace(voice=False)
    if not ffmpeg_available():
        print("\nSkipping reel previews: ffmpeg not found. Install it, or run "
              "`pip install imageio-ffmpeg`, then try again.\n")
        return []

    news = Reel(
        slot="reel_1", kind="news", category="Technology",
        title="On-device AI chip",
        hook="Your phone just stopped needing the cloud",
        beats=[
            ReelBeat(role="hook", caption="Your phone just stopped needing the cloud",
                     detail="A new chip runs the AI work on the handset itself.",
                     narration="Your phone just stopped needing the cloud. Here's why that matters."),
            ReelBeat(role="point", caption="What happened",
                     detail="A major maker put a dedicated AI chip in a "
                            "mainstream phone, not a flagship.",
                     narration="A big maker put a dedicated AI chip in an ordinary phone, not a flagship."),
            ReelBeat(role="point", caption="Why that is hard",
                     detail="Running a model locally means fitting it into a "
                            "battery budget, not a data centre.",
                     narration="Running a model locally means fitting it in a battery, not a data centre."),
            ReelBeat(role="graphic", caption="Where the thinking happens",
                     narration="So where does the thinking happen? That's the whole difference.",
                     graphic="split",
                     data={"left_title": "Cloud", "left_text": "Sent away, "
                           "answered in a second, needs signal.",
                           "right_title": "On device", "right_text": "Answered "
                           "instantly, works on a plane, stays private."}),
            ReelBeat(role="point", caption="What it means for you",
                     detail="Faster replies, and the things you type never leave "
                            "the phone.",
                     narration="You get faster replies, and what you type never leaves the phone."),
            ReelBeat(role="payoff", caption="The cloud just got optional",
                     narration="For a lot of everyday AI, the cloud just became optional."),
        ],
        caption="A sample caption.", hashtags=["Tech"], sources="Reuters, BBC +2",
        scheduled_time="2026-08-10T09:30:00+05:30",
    )

    education = Reel(
        slot="reel_2", kind="education", category="Finance",
        title="Why a rate hike makes your loan cost more",
        hook="One vote. Your mortgage. Six months.",
        beats=[
            ReelBeat(role="hook", caption="One vote. Your mortgage. Six months.",
                     detail="Here is the chain nobody explains.",
                     narration="One vote, your mortgage, six months. Here's the chain nobody explains."),
            ReelBeat(role="point", caption="It starts with one rate",
                     detail="The central bank sets what banks pay to borrow "
                            "from each other overnight.",
                     narration="It starts with one rate: what banks pay to borrow overnight."),
            ReelBeat(role="point", caption="Meet Priya's bakery",
                     detail="Her loan is priced off that rate. It moves, her "
                            "repayment moves, her bread gets more expensive.",
                     narration="Priya's bakery loan is priced off it. It moves, so does her bread."),
            ReelBeat(role="graphic", caption="The chain",
                     narration="The whole chain runs in three steps, and you're the last one.",
                     graphic="flow",
                     data={"steps": ["Central bank raises",
                                     "Banks charge more",
                                     "You pay more"]}),
            ReelBeat(role="point", caption="The rule",
                     detail="Rates are the price of money, and everything "
                            "bought with borrowed money reprices.",
                     narration="Rates are the price of money, so borrowed money reprices everything."),
            ReelBeat(role="payoff", caption="That is the whole mechanism",
                     narration="And that's the whole mechanism, start to finish."),
        ],
        caption="A sample caption.", hashtags=["Finance"],
        scheduled_time="2026-08-10T20:00:00+05:30",
    )

    produced: list[Path] = []
    for reel in (news, education):
        # No network in preview: a loader that always returns None makes every
        # beat use the designed brand panel instead of an article photo, and the
        # stub voice below stands in for Gemini TTS so a preview never spends a
        # request. Pass --voice to hear the real thing.
        video, cover = render_reel(
            reel, out_root / "reels", image_loader=lambda _src: None,
            voiceover=True,
            tts_client=None if args.voice else _StubVoice())
        produced.extend([video, cover])
        print(f"  reel {reel.slot}: {reel.duration_seconds:.1f}s "
              f"({'narrated' if reel.has_voiceover else 'silent'})")
    return produced


class _StubVoice:
    """Stands in for Gemini TTS in previews.

    Returns silence of the length the real voice would take, so the preview has
    the same pacing and the same cut points as a narrated reel without making a
    single API call. It is the timing that needs checking offline, not the timbre.
    """

    CHARS_PER_SECOND = 13.0

    def synthesize(self, text: str, *, voice: str, style: str = "") -> bytes:
        from .gemini.tts import silence

        return silence(max(1.2, len(text or "") / self.CHARS_PER_SECOND))


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
    pv.add_argument("--voice", action="store_true",
                    help="narrate the preview reels with the real Gemini TTS "
                         "voice (needs GEMINI_API_KEY). Without this the "
                         "preview uses correctly-timed silence.")
    pv.set_defaults(func=_cmd_preview)

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
