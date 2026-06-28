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


def _cmd_preview(args: argparse.Namespace) -> int:
    """Render a sample carousel with mock content so you can check the design.

    Works fully offline: no Gemini calls and no network image fetches (the
    renderer falls back to clean branded gradients when an image is missing).
    """
    from .models import InstagramCarousel, Slide
    from .render import render_carousel

    out_root = Path(args.out or "preview")
    samples = {
        "Technology": "Top 3 Things In Tech Today",
        "Geopolitics": "Top 3 Geopolitics Headlines",
    }
    mock_stories = [
        ("A major phone maker shows a new AI chip",
         "It promises faster on-device features while using less battery. More AI could now run without the cloud."),
        ("A big cloud outage briefly hit popular apps",
         "Several services went dark for a few hours. It is a reminder of how much the internet leans on a few providers."),
        ("Fresh rules are proposed for AI labelling",
         "Regulators want clearer tags on AI made content. Platforms will need to adjust how features ship."),
    ]

    produced = []
    for cat, title in samples.items():
        slides = [Slide(role="cover", headline=title, image_url=None)]
        for h, e in mock_stories:
            slides.append(Slide(role="story", headline=h, explanation=e, image_url=None))
        slides.append(Slide(role="cta", headline="Stay ahead with HEADLINNE.com"))
        carousel = InstagramCarousel(
            slot="instagram_1", category=cat, num_slides=len(slides),
            title=title, slides=slides,
            caption="A quick look at today's biggest stories. Read more on HEADLINNE.com.",
            hashtags=["News", "Headlinne"], scheduled_time="",
        )
        out_dir = out_root / cat.lower()
        paths = render_carousel(carousel, out_dir)
        produced.extend(paths)

    print("Rendered preview slides:")
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
