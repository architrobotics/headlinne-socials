"""Command-line entry point.

Usage:
  python -m headlinne generate                 # gather, write and render today
  python -m headlinne generate --no-render      # skip image rendering
  python -m headlinne generate --no-schedule    # do not schedule into Buffer
  python -m headlinne publish --target x-1       # publish one slot
  python -m headlinne preview                    # render a sample carousel offline
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

    print("Rendered preview slides and cards:")
    for p in produced:
        print("  ", p)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="headlinne", description="Headlinne social automation")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="gather, generate, render and save today's content")
    g.add_argument("--no-render", action="store_true", help="skip carousel image rendering")
    g.add_argument("--no-schedule", action="store_true", help="do not schedule X/LinkedIn into Buffer")
    g.set_defaults(func=_cmd_generate)

    p = sub.add_parser("publish", help="publish one slot for today")
    p.add_argument("--target", required=True,
                   choices=["x-1", "x-2", "linkedin", "instagram-1", "instagram-2"],
                   help="which slot to publish")
    p.set_defaults(func=_cmd_publish)

    pv = sub.add_parser("preview", help="render a sample carousel offline")
    pv.add_argument("--out", help="output folder (default: preview)")
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
