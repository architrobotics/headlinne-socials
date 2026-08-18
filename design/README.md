# Design work — August 2026

Everything produced during the redesign session. Nothing here is wired into the
running pipeline; `headlinne/` in this folder is untouched. The equivalent code
lives on the `redesign/pip` branch on GitHub, at `ee1931e`.

---

## brand-book.html

The design document. Open it in a browser. Covers the character, the voice, the
formats, the fallback ladder, the reel spec, the X cards, the rate-limit
arithmetic and the QA harness. Self-contained — fonts and images are embedded,
so it works offline.

`earlier-drafts/` holds the two versions it replaced, kept only because they
show how the direction changed: `01-audit-report.html` was the first audit of
the old design, `02-playbook.html` the version before Pip existed.

---

## prototypes/

Standalone modules. Each runs on its own with `python <file>.py` from inside
this folder and writes its output beside itself. They need Pillow, and
`interest.py` needs feedparser.

| File | What it does |
|---|---|
| `pip.py` | The mascot. Six poses, five animation cycles, the chest emblem, GIF export. Run it to regenerate every sprite. |
| `plate.py` | Tilted paper photo frames and the generated fallback scenes behind them. |
| `interest.py` | The ranking harness. Fetches live feeds and prints the old scorer against the new one side by side. This is the one to run if you want to re-check the story selection on a given day. |
| `qa.py` | The runthrough. Renders all 720 reel frames and checks them for collisions, safe-zone breaches, contrast and pacing. ~19,800 assertions. |
| `draft.py` | The reel renderer that produced `reel_draft.mp4`. Word-by-word reveal, walking Pip, plates, progress bar. |
| `reel.py`, `reel2.py` | Earlier reel passes. `reel2.py` is the informational-voice rewrite; `draft.py` supersedes both. |
| `formats.py` | Carousel slides and the first reel frames. |
| `xpost.py` | The four X card types at 1200×675. |
| `cards.py` | The first story-card mockups. |

---

## samples/

Rendered output, by format.

- `reels/` — `reel_draft.mp4` is the 30-second draft. `draft_loop.gif` is the
  same thing as a loop. Stills are individual beats.
- `sprites/` — Pip in every pose and cycle. `pip_walk.gif`, `pip_jump.gif` etc.
  are the animations; `pip_small.png` is the 26px legibility check.
- `cards/`, `carousels/`, `x/`, `plates/` — the static formats.

Anything named `sheet_*` is a contact sheet of several renders side by side.

---

## ported/

The same work as it exists in the package on the branch, so you can read it
without checking the branch out.

- `headlinne/render/` — `pip.py`, `plate.py`, `receipt.py`
- `headlinne/news/` — `interest.py`, `quality.py`, `corroborate.py`
- `tests/` — the six new test files
- `branch-vs-live.diff` — everything on `redesign/pip` that is not on `main`
- `design-wiring.patch` — the commit that flipped the renderers to the paper
  palette, dropped Anton for Manrope, removed the category pill and the ghost
  numerals, and put Pip on the cards. This was pushed and then pulled back off
  the remote at your request, so it exists only here and as a local branch in
  the working clone. Apply it with `git am design-wiring.patch`.

---

## What is not here

The reel renderer was never ported into `headlinne/render/reel.py` — `draft.py`
is a standalone prototype, not an integration. The X cards were never ported
either. The TTS batching change (one speech call per reel instead of one per
beat) was never written. `theme.draw_receipt` exists on the branch but nothing
calls it, so the source strip in these samples is the old footer line rather
than the designed component.
