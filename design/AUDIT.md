# Headlinne — pre-redesign audit

**Date:** 17 Aug 2026 · **Scope:** whole repository, before any change is made
**Baseline:** `python -m tests` → **176/176 passing** on the tree as found.

This is the understanding pass the redesign is gated on. It records what the
system is, what the new design system actually specifies, precisely where the
two diverge, and which findings change the order of the work.

---

## Status

Everything below the status block is the audit as written *before* any change.
Only this block moves.

| Phase | State | Evidence |
|---|---|---|
| **A — foundation** | **Shipped** | D1 D2 D4 D12 D14 closed |
| **B — intelligence** | **Shipped** | D5 D13 D15 closed |
| **C — design system, native** | **Shipped** | D3 D6 D7 D8 closed |
| **D — the daily carousel and reel** | **Shipped** | — |
| **E — visual quality control** | **Shipped** | D9 D10 D11 closed |

**All sixteen defects closed. Tests: 211/211** (176/176 as found; the count moved
because the tests describing the replaced architecture were rewritten rather than
added to).

### What the visual gate now enforces

`quality/visual.py` runs on every surface before publication and fails safe — a
non-compliant post is dropped and the rest of the day ships. Nearly **4,000
assertions per reel**: element collision, the y=1450 safe zone, margins, canvas
size, flat-render detection, contrast floors, sprite liveness, receipt
arithmetic, carousel slide order, sober routing for sensitive stories, and both
reading-pace budgets.

It was negative-tested against six deliberate faults — an element pushed below
the safe zone, two overlapping elements, out-of-order slides, a mascot on a
sensitive story, a receipt claiming more agreement than outlets, and a frozen
sprite cycle. All six were caught. A harness that never fails proves nothing.

### The day, as it now runs

One reel (09:30), one carousel (16:00), one story card (21:30), plus X and
LinkedIn. The reel gets first claim on the day's best story; the carousel takes
the next one, so the day never spends two posts on the same event. Three
Instagram posts is what a small account can carry — a fourth divides the reach
rather than adding to it. Both extra slots remain and still publish if something
is written into them.

### Three findings the build surfaced that the read did not

1. **The lexicons matched raw substrings.** `"sun"` matched inside *Sam**sun**g*
   and `"ice"` inside *not**ice*** and *tw**ice***, so a layoff notice scored as
   universal and concrete. In the other direction `"discovered"` never matched
   *"Scientists **discover** why…"*, scoring a real finding at zero novelty. Both
   are fixed by boundary-anchored matching with explicit stems
   (`news/_lexicon.py`), and both are pinned by regression tests.
2. **`first` sat in both the novelty and uplift lexicons**, so one neutral word
   scored twice — which is how *"first close below IPO price"* and *"record
   layoffs"* came to read as good news.
3. **Corrected, the interest ceiling on the real corpus drops from 5.60 to
   3.84.** That is the honest reading and it strengthens §0.2 rather than
   weakening it: nothing published in those eleven days deserved a high score,
   because the feeds could not carry the kind of story that earns one.

### What the agreement engine produces

On the moon story with six raw reports: three are one Reuters wire under three
mastheads and collapse to one voice; Space.com's 8,690 km/h agrees with 8,700
inside tolerance; Phys.org's 5,200 km/h is a genuine conflict. The strip reads
**"3 of 4 outlets agree"** — denominator four, not the six reports fetched and
not the 246 stories in the corpus.

---

## 0. The five findings that change the plan

1. **The redesign already exists, unwired.** `design/ported/` holds six finished
   modules (`interest.py`, `quality.py`, `corroborate.py`, `pip.py`, `plate.py`,
   `receipt.py`), six test files, a 1,971-line branch diff and a wiring patch.
   None of it is in `headlinne/`. This is not a greenfield redesign; it is a
   port, a correction and a completion. Roughly 40% of the work is written.

2. **The ranker change is close to a no-op without the feed change — measured.**
   Run against the 210 headlines Headlinne actually published (`state/history.json`),
   the new interest scorer tops out at **5.60**, and its top ten are *SpaceX stock,
   Chinese IPOs, a 739-person layoff, Chipotle*. The brand book's live run scored
   8.99 / 8.49 / 8.20 on science stories. The difference is not the weights, it is
   the corpus: `_UNIVERSAL` and `_PHYSICAL` are science lexicons (`moon`, `brain`,
   `whale`, `glacier`, `fossil`) and **`config.FEEDS` contains no science feed at
   all**. The brand book's ship order ("ranker first, wonder feeds second") is
   wrong on the evidence. They ship together or the ranker measures nothing but
   "has a digit in the headline".

3. **The samples and the ported `receipt.py` disagree, and the samples win.**
   Every sample renders a **fraction** — "8 of 8 outlets agree", "4 of 6 outlets
   agree", "3 of 7 outlets agree" with hollow ticks for the remainder.
   `design/ported/headlinne/render/receipt.py:43` returns a **count** —
   `"5 outlets reported this"` — on the explicit argument that a fraction implies
   a dissent we never measured. That argument is correct *given the current
   pipeline*. The fix is not to pick a side: it is to actually measure agreement,
   which makes the denominator honest and the samples reproducible.

4. **The live reel draws into dead pixels.** `render/reel.py:55` sets
   `FOOTER_Y = 1500`. The design system's hard limit is **nothing below y=1450**
   (`design/prototypes/draft.py`, `qa.py` check 2) because Instagram's caption
   block and action rail sit exactly there. The handle and source line on every
   reel shipped so far are underneath Instagram's own UI.

5. **The wiring patch's contrast claim is false.** Its commit message says "All
   four now clear 4.5:1 on paper". Measured: terracotta `#C4562F` = **3.96:1**,
   coral `#CE3E22` = **4.31:1**, `TEXT_MUTED #9A8B7C` = **2.94:1** — which fails
   even the 3.0 large-text floor. Only mint (5.68), marigold (4.65) and violet
   (6.18) clear 4.5. `qa.py` passes because it only asks 3.0 of the accents; it
   never checks `TEXT_MUTED` at all.

---

## 1. Architecture as found

```
cron-job.org ──dispatch──▶ GitHub Actions
                             │
   generate (06:00 IST)      │      publish (per slot)
   ────────────────────      │      ──────────────────
   news/feeds.fetch_all      │      storage.load_*
   news/ranking.rank         │      publish/buffer  → X, LinkedIn, IG
   pipeline._drop_seen       │      publish/meta    → IG (alt path)
   gemini/client (JSON)      │      publish/image_host → raw.githubusercontent
   generate/{twitter,linkedin,instagram,reel,story_card}
   render/{carousel,card,story_card,reel} ── theme ── fonts
   quality/{checks,sanitize,dedup}
   storage.save_* → content/<date>/ ── committed
```

| Layer | Files | State |
|---|---|---|
| Config / tokens | `config.py` (31 KB) | Single source for feeds, schedule, palette, limits. Sound. |
| News | `news/{feeds,images,ranking}.py` | Ranking is the weak point (§5). |
| Copy | `gemini/{client,prompts,tts}.py`, `generate/*` | Model writes words, code owns structure. Sound. |
| Render | `render/{theme,fonts,carousel,card,story_card,reel,graphics,motion,voice}.py` | The whole redesign target (§4). |
| Quality | `quality/{checks,sanitize,dedup}.py` | Text-only. No visual validation at all (§9). |
| Publish | `publish/{buffer,meta,image_host}.py` | Sound; idempotent via `published/<target>.json`. |
| Tests | `tests/` 20 files, 176 tests, zero-network | Good. Nothing tests a rendered pixel. |

**Failure containment is already right.** Every format generates and renders
independently inside a `try` (`pipeline.py:228-291`), and a format that fails is
dropped from the day rather than sinking the run. The new validation work should
extend this pattern, not replace it.

---

## 2. The design system, as the samples specify it

Extracted from `design/brand-book.html`, `design/prototypes/formats.py` and
`design/prototypes/draft.py`. These are exact, not approximate — `formats.py`
is the program that rendered the sample PNGs.

### Palette (paper, not ink)

| Token | Hex | RGB | On paper |
|---|---|---|---|
| `PAPER` (ground) | `#F7F1E6` | 247,241,230 | — |
| `PAPER_DEEP` (rules) | `#E9DFCE` | 233,223,206 | — |
| `CREAM` (bubbles, plates) | `#F5EFE4` | 245,239,228 | — |
| `INK` | `#191310` | 25,19,16 | 16.36:1 |
| `INK_SOFT` | `#6E6156` | 110,97,86 | 5.33:1 |
| `TERRA` | `#C4562F` | 196,86,47 | 3.96:1 ⚠ |
| `MINT` | `#1E6B54` | 30,107,84 | 5.68:1 |
| `MARIGOLD` | `#946217` | 148,98,23 | 4.65:1 |
| `CORAL` | `#CE3E22` | 206,62,34 | 4.31:1 ⚠ |
| `NIGHT` | `#17120E` | 23,18,14 | — |

Marigold was already corrected once: `#B8791A` → `#946217` after failing at
2.72:1. The brand book's own CSS still carries the *uncorrected* `#B8791A`
(3.23:1) — the HTML was never updated to match the fix its own QA section
describes. **Renderer constants are canonical, not the brand-book CSS.**

### Typography

One family: **Manrope variable**, weight axis 200–800. Anton is retired — it is
single-weight, so nothing can be emphasised inside a headline, and it is the
default face of every automated news account. Inter stays for long body copy.

| Role | Size | Weight |
|---|---|---|
| Wordmark `HEADLINNE` | 34 | 800 |
| Dateline | 26 | 600 |
| Kicker / eyebrow (uppercase) | 30 | 700 |
| Headline (card) | 84, lh 96 | 800 |
| Headline (cover) | 92, lh 104 | 800 |
| Standfirst | 42 | 500 |
| Receipt label | 32–34 | 700 |
| Outlet list | 28 | 500 |
| Footer | 26 | 600 |
| Speech bubble | 34, lh ×1.34 | 650 |

### Grid — 1080 × 1350, margin **84**

```
y=  74   HEADLINNE (34/800 ink)        ·  date right-anchored (26/600 soft)
y= 132   category rule, 4px, full width margin→margin, tone-coloured
y= 196   Pip, scale 15  at x = M − 30       (bleeds 30px past the margin)
y= 236   speech bubble at x = M + 350, max width 560
y= 606   kicker, uppercase, tone
y= 664   headline, 84/800, line height 96
y=H−322  receipt ticks (13 × 46, gap 9)
y=H−248  "N of M outlets agree" 34/700 ink
y=H−200  outlet names 28/500 soft
y=H−132  footer rule 2px PAPER_DEEP
y=H−108  headlinne.com 26/600 soft
```

### Components

- **Receipt strip** — one tick per outlet that reported the event. Filled mint =
  agrees; hollow 3px `INK_SOFT` outline = reported but does not agree. Label
  underneath as a fraction. Named outlets under that, `·`-joined, `+N` overflow.
  Cap at 8 ticks (`receipt.MAX_TICKS`).
- **Speech bubble** — cream fill, chunky ink border drawn twice (offset 0 and 3,
  width 3), stepped pixel tail as a single polygon, tail picks the side with
  room and mirrors itself. 22px horizontal padding, 17px top.
- **Pip** — 26px-wide pixel pigeon, 6 poses + 6 animation cycles. Body block is
  byte-identical across every pose; only heads and props change. Never
  recoloured. Must read at 26px.
- **Plates** — photo in a cream frame, 4px ink border, −3.2° rotation, gaussian
  drop shadow, masking-tape strip at 16% width. Caption in the plate function,
  never at the call site.
- **Masthead** — wordmark + date + tone rule. **No category pill.** The pill was
  the loudest object on the canvas carrying the least useful information.

### Behavioural rules (these are the design system, not decoration)

| Situation | Required behaviour |
|---|---|
| Fewer than 2 independent sources | **Do not publish.** A gate, not a penalty. |
| Story is sensitive (death, disaster) | Sober template: no Pip, no bubble, no kinetic emphasis, no wonder framing. |
| Headline needs > 3 lines | Route to carousel. **Never shrink the type.** |
| No number in the story | Skip the counter beat. Never invent a statistic. |
| Sources disagree | Pip puzzled, both figures shown, resolution in the caption. |
| Requested pose unavailable | Fall back to idle. Never an empty sprite slot. |
| Script exceeds 220 wpm | **Fail the build.** Cut words, don't shorten holds. |
| Generated illustration | Caption `ILLUSTRATION · NOT A PHOTOGRAPH`, always, from inside the plate function. |

### The fallback ladder

| Rung | When | What renders |
|---|---|---|
| 1 | Article has a usable image | Photo, tilted in a paper frame, taped, source caption |
| 2 | No image, category has a scene | Generated pixel scene + mandatory ILLUSTRATION caption |
| 3 | No image, story has figures | Generated chart plate from the article's numbers |
| 4 | Nothing usable | Pip presenting the headline, larger type, more air |

**None of them is a bare gradient.** The old carousel fell back to one on roughly
half its slides.

### Reel — 1080 × 1920, margin 84, paper ground

```
   0– 140  masthead + progress bar
 150– 200  chapter marker
 210– 830  plate zone (1–3 tilted photos)
 830–1010  Pip on the ground line, bubble above
1020–1210  the kinetic line (Manrope weight axis for *emphasis*)
1215–1300  secondary detail
1310–1400  persistent source strip
1400–1450  safe-zone rule
1450+      dead — Instagram's UI owns it
```

Two pace budgets, not one: **176 wpm on the primary line** (ceiling 230) and
**288 wpm total on-screen load** (ceiling 380). Measuring them as one block gives
308 wpm and forces a rewrite that isn't needed.

### X cards — 1200 × 675, four types

`receipt` (who reported it) · `compare` (two outlets, one document, two numbers) ·
`correct` (struck-through original, corrected fact) · `plate` (one number, one
image). The card carries the **proof**, never the headline — on X the post text
is the hook, so a card repeating it wastes the strongest position on the platform.

---

## 3. The design system, as the code actually implements it

`headlinne/render/theme.py` + `config.py` lines 98–131.

| | Live | Sample |
|---|---|---|
| Ground | `#141210` near-black + radial gradient + ghost logo + diagonal sheen | Flat `#F7F1E6` paper |
| Display face | Anton (single weight) | Manrope 800 |
| Category | Solid coloured pill, top-right, dark text | 4px rule under the wordmark |
| Index | Ghosted `01` at alpha 46, 300px | Removed |
| Swipe | Outlined `SWIPE →` pill | Removed |
| Photo | Full-bleed under a 5-stop cinematic scrim | Tilted taped plate on paper |
| No photo | `brand_fallback()` — tinted radial wash | 4-rung ladder |
| Sources | `◆ SOURCES Reuters, BBC +2` | Tick strip + fraction + names |
| Mascot | none | Pip, pose = story kind |
| Type over photo | Gaussian drop shadows everywhere | No shadows (paper needs none) |
| Progress | Pips bottom-left | Removed (Instagram draws its own) |
| CTA slide | Dark panel + terracotta glow + FOLLOW/SAVE pills | Paper, Pip, domain as the loudest object |
| X card | 1080 × 1080 square, one layout | 1200 × 675, four layouts |

**Every visual token, every furniture primitive and every layout differs.** This
is not a re-skin. `theme.py` is 421 lines of a *different* design system that
happens to occupy the right filenames.

Verified live output: `preview/technology/slide_1.png` and `slide_2.png` show the
dark ground, Anton headline, coral pill, ghost `01`, SWIPE pill and `◆ SOURCES`
line — and the photo-less fallback rendering as a near-flat dark smudge.

---

## 4. Gap register, surface by surface

| Surface | File | Gap |
|---|---|---|
| Carousel cover | `render/carousel.py:166` | Whole layout. Photo+scrim → paper+Pip+bubble. Swipe hint, progress pips out. |
| Carousel story | `:257` | Ghost index out, Pip in, source line → receipt strip, plate treatment for the photo. |
| Carousel CTA | `:330` | Only slide not on paper. Glow, logo mark, FOLLOW/SAVE pills all out. |
| Story card | `render/story_card.py` | Background, masthead, Pip band, receipt footer. Rail (4 stops) is **correct and stays**. |
| X card | `render/card.py` | Wrong canvas (1080² vs 1200×675), wrong count (1 vs 4 layouts), wrong content model (repeats the headline). |
| Reel | `render/reel.py` | Ground, face, safe zone (`FOOTER_Y=1500`), no Pip, no plates, no kinetic weight-axis type, no two-budget pacing. |
| Theme | `render/theme.py` | Needs `paper`, `draw_masthead`, `draw_pip`, `draw_bubble`, `draw_receipt`, `draw_plate`, `pose_for`. Has none. |
| Fonts | `render/fonts.py` | `title_font` is Anton and takes no weight argument. |
| Graphics | `render/graphics.py` | 5 devices built for the dark palette; need paper equivalents. |
| Models | `models.py:17` | `Story` has no `verified`, no `sensitive`, no agreement data. |
| Config | `config.py:104` | Dark tokens; no Science category; no science feeds; no `FEED_TIMEOUT_SECONDS`. |

---

## 5. Ranking — why it produces what it produces

`news/ranking.py:152`

```
score = 3.2·log₂(sources+1) + 1.6·tier + 0.9·min(keywords,4)
      + 1.0·e^(−age/18) + 0.7·breadth − 1.15·min(lowvalue,2)
```

The heaviest term by a wide margin is **cross-source count**. The story that
maximises that function is, by construction, the one the most outlets ran: a
central bank decision, a summit, an earnings print. *Nobody chose those stories.
The arithmetic did.* The second term, `HIGH_INTEREST_KEYWORDS` (`config.py:176`),
is 46 words of which ~40 are corporate and institutional — `apple`, `google`,
`fed`, `earnings`, `ipo`, `merger`, `election`, `summit`. It reinforces the same
bias rather than correcting it.

Three further defects:

- **`explainer` and `how to` are in `_LOW_VALUE_MARKERS`** (`ranking.py:52`).
  That is the exact genre of the evening educational reel — the ranker penalises
  the product's own second daily format.
- **The low-value list is a soft capped penalty (max 2.3)** against scores above
  11. It cannot hold back a promo code the model finds interesting.
- **Verification and interest are the same number.** "Is this true?" and "should
  anyone care?" are different questions and must be different terms.

### The replacement, and what it actually does — measured

`design/ported/headlinne/news/interest.py` scores eight terms:
`concrete` (3.0), `universal` (2.6), `novelty` (2.4), `surprise` (2.2),
`uplift` (1.8), `imageable` (1.4), `standalone` (1.2), minus `procedural` (3.0).
Cross-source drops from 3.2 to 0.6 — a tiebreaker, not a driver.

Run over the 210 headlines Headlinne has actually published:

| | Result |
|---|---|
| Quality gate rejects | 5 / 210 (2 listicles, 3 housekeeping) |
| Sensitive routing fires | 16 / 210 (8%) |
| Top score achieved | **5.60** |
| Top ten composition | SpaceX stock, Chinese humanoid IPOs, OpenAI speaker, Samsung 739 layoffs, Kimi K3, Chipotle Mexico, AI drug startup, AliExpress fine, AT&T ruling, SpaceX short sellers |

Compare the brand book's live run: 8.99, 8.49, 8.20, 7.90 — immune cells in the
aging brain, a rocket hitting the Moon, lunar debris.

**The conclusion is unambiguous.** The new ranker is a science-and-wonder
detector pointed at a corpus containing no science. Of its top ten on real
Headlinne data, nine are corporate/financial and score highly on `concrete`
purely because they contain digits — "reduce workforce by 739" reads as concrete
to a lexicon looking for measured quantities. Without the Science feeds the
change is not an improvement; on this evidence it is a lateral move with a
different bias.

**The two must ship as one change**, and the interest lexicons need widening
beyond the science vocabulary they were tuned on, so a genuinely useful Apple or
SpaceX story ranks for being useful rather than for containing a number.

Also missing, and named in the brand book itself: **the reserved non-universal
slot.** Weighting universality pushed "Afghan women tell the BBC their lives are
unrecognisable" out of the top eight. One slot a day must be reserved for a story
that is important without being universal, or the feed becomes all wonder and no
world.

---

## 6. Source retrieval and corroboration

### Retrieval

17 feeds across 3 categories (`config.py:146`). Technology 7, Finance 5,
Geopolitics 5. Two structural problems:

- **No timeout.** `feeds.py:63` calls `feedparser.parse()` with no timeout;
  feedparser inherits the global socket default, which is *wait forever*. One
  publisher that accepts the connection and stalls burns the workflow's entire
  45-minute ceiling. The branch fixes this (`FEED_TIMEOUT_SECONDS`, default 12s).
- **Depth per beat is too thin to corroborate.** Corroboration can only find a
  second outlet if a second outlet is in the room. The branch adds 15 feeds
  (2 tech, 2 finance, 4 geo, 7 science) taking the pool to 32.

### Corroboration — the core arithmetic error

Today, clustering and corroboration are **the same operation**
(`ranking.py:91`, `_SIM_THRESHOLD = 0.52`). They are different problems with
opposite error costs:

- *Clustering* asks "are these one post?" Fusing two distinct stories produces a
  carousel about nothing. It must be **conservative**.
- *Corroboration* asks "how many outlets reported this event?" It needs **recall**.

Running both off one threshold means one is always wrong. Measured on a 297-story
day: 288 events, only **9** with a second source — `verified` false for ~97% of
the feed. Lowering the threshold does not help; the false pairs outscore the true
ones because plain token overlap weights "review" exactly like "PayPal":

```
0.45  Samsung Galaxy Z Fold 8 Ultra review   | same story
0.36  Talks to sell PayPal to Stripe         | same story
0.27  Samsung has new Galaxy headphones      | DIFFERENT
```

`corroborate.py` is the correct answer: a second pass over the same already-fetched
corpus, scoring shared **distinctive** terms weighted by per-run IDF, gated on
≥2 shared named entities carrying ≥3.4 IDF weight, with roundups excluded as
sources. Separation between the weakest true pair and the strongest false pair
widens from 0.79 to 5.40. It costs no extra API call and no network.

**It is not wired in.** And the branch's `pipeline._corroborate_selected()` calls
`corroborate.attach()` without importing `corroborate` — the wiring would raise
`NameError` on the first run.

### Syndication is not handled at all

`corroborate.py` de-duplicates by `story.source`, so two feeds from the same
publisher can't double-count. But **an AP wire story republished verbatim by six
outlets counts as six independent sources.** The samples' whole claim —
"Headlinne reads every outlet covering a story and shows you where they agree" —
collapses if six copies of one AP report render as six agreeing outlets. This is
the single largest correctness gap in the trust story, and nothing in the branch,
the brand book or the live code addresses it.

---

## 7. "X of Y sources agree" — stated precisely

Three incompatible positions exist in the repository:

| Source | Renders | Rationale |
|---|---|---|
| Samples (`card_sheet.png`, `sheet_x.png`) | `9 of 9` · `4 of 6` · `3 of 7` · `8 of 8` | Filled ticks agree, hollow ticks don't |
| `receipt.py:43` (ported) | `5 outlets reported this` | A fraction implies a dissent we never measured |
| Live `generate/instagram.py:43` | `Reuters, BBC +2` | No quantity at all |

`receipt.py` is right about the *current* pipeline and wrong as a destination.
The brief and the samples agree, so the resolution is to build what makes the
fraction true:

```
denominator  = outlets that reported this event, after syndication collapse
               (never the number of feeds read, never the retrieval count)
numerator    = outlets whose account of the central claim agrees
remainder    = reported but conflicting → hollow ticks
```

That requires a claim-level comparison the pipeline does not have today: extract
the story's headline figure or central assertion, compare each corroborating
outlet's account of it, and classify agree / conflict / silent. **Silent is not
disagreement** — an outlet that never mentioned the number must not become a
hollow tick, or the denominator inflates again by a different route.

State machine, driving the eyebrow, the rule colour and Pip's pose:

| State | Condition | Eyebrow | Tone | Pose |
|---|---|---|---|---|
| Unanimous | agree == total, total ≥ 2 | `YOUR BRIEF` | terra | carry/alert |
| Developing | agree < total, no hard conflict | `DEVELOPING` | terra | read |
| Disputed | ≥1 outlet conflicts on the claim | `SOURCES DISAGREE` | marigold | puzzled |
| Single | total == 1 | — | — | **do not publish** |

All four states are already drawn in `design/samples/cards/card_sheet.png`.

---

## 8. Carousel — current state vs the daily target

**Current:** 1–2 per day, each a *listicle* — cover + 3 or 5 unrelated stories +
CTA (`generate/instagram.py:103`). Every story slide is the same layout with a
different headline.

**Sample:** one carousel, **one story**, five slides doing five different jobs —
`cover` (what happened) → `scale` (how big, one number set huge) → `twist` (the
thing you didn't know) → `sources` (the receipt, in full) → `cta`. That is an
argument, not a list, and it is exactly what "each carousel centred on a distinct
story" describes.

**Conflict to resolve:** the branch sets `IG_SECOND_CAROUSEL=False` and gates
carousels to `CAROUSEL_WEEKDAYS="1,4"` — Tuesday and Friday only. The brief asks
for one high-quality carousel **every day**. The brief wins; it is the later and
explicit instruction. The reasoning behind the gate still needs honouring though:
the README's own argument is that four Instagram posts a day is the ceiling for a
small account. Daily carousel + 2 reels + story card = exactly four, provided the
second carousel stays off. Quota is not a constraint — a carousel is one text call
against a budget the brand book puts at 5–6 a day.

---

## 9. Validation and quality control

**What exists:** `quality/checks.py` — 162 lines, entirely textual. Character
limits, forbidden punctuation, clickbait phrases, all-caps, slide counts, reel
duration, empty story-card steps. Good, and it correctly distinguishes errors
(block) from warnings (log).

**What does not exist:** *any* check on a rendered pixel. Nothing verifies that a
slide matches the design system, that elements don't overlap, that the reel stays
inside the safe zone, that contrast holds, that a sprite rendered non-empty, that
a plate carries its mandatory caption, or that a receipt's arithmetic is sound.

**What the prototype proves is achievable:** `design/prototypes/qa.py` renders all
720 reel frames and runs **19,806 assertions** across seven families — collision,
safe zone, margins, contrast, legibility, assets, fallbacks. It has caught six
real bugs, two of them only after its coverage widened. Its own best lesson is
recorded in the brand book: *a test that cannot see the thing it is testing passes
while the product is broken* — the pose check compared bounding boxes, so a beak
opening changed nothing and a frozen sprite passed. It compares pixels now.

Gaps to close, in the pipeline rather than in a prototype:

| Check | Blocks publish? |
|---|---|
| Canvas size exact per format | yes |
| Not >98.5% one colour (failed draw) | yes |
| No two traced elements overlap | yes |
| Nothing below y=1450 on a reel | yes |
| Every accent clears its contrast floor | yes (at build time) |
| Every sprite pose renders non-empty | yes |
| Generated plate carries the ILLUSTRATION caption | yes |
| Receipt: numerator ≤ denominator, denominator = corroborated set | yes |
| Carousel: exactly one story, 5 slides, roles in order | yes |
| Sensitive story carries no Pip and no bubble | yes |
| Ranking decision is logged with its per-term breakdown | audit trail |
| Two pace budgets hold (176/288 wpm) | yes |

---

## 10. Defect and debt register — verified, not inferred

| # | Where | Finding |
|---|---|---|
| D1 | `headlinne/__init__ (1).py` | Package has **no `__init__.py`**. The file was saved with a browser-duplicate suffix. `import headlinne` succeeds only as a PEP 420 namespace package; `__version__` is unreachable. |
| D2 | `workflows/` | Workflows are not in `.github/workflows/`. As checked out, **nothing runs on GitHub at all.** README documents the correct path. |
| D3 | `render/reel.py:55` | `FOOTER_Y = 1500` — below the 1450 safe-zone floor. Handle and sources are drawn under Instagram's UI on every reel. |
| D4 | `models.py:17` | `Story` lacks `verified` / `sensitive`. Setting them dynamically works but `asdict()` drops them, so the flags **do not survive** `content/<date>/news_digest.json` — the publish stage loses sensitive routing entirely. |
| D5 | branch `pipeline.py` | `_corroborate_selected()` uses `corroborate` with no import. `NameError` on first run. |
| D6 | wiring patch, `theme.py` | `_legacy_cinematic_scrim`, `_legacy_panel_gradient`, `_legacy_brand_fallback`, `story_card._unused_background` — four dead functions retained as commented-out history. |
| D7 | wiring patch, `carousel.py:230` | `_draw_footer_rule(canvas, draw) if "_draw_footer_rule" in globals() else None` — a runtime `globals()` probe for a function that does not exist. |
| D8 | wiring patch, `carousel.py:131` | `pose_for("cover" if slide.role == "cover" else "explainer")` inside `_render_story`, where `role` is never `"cover"`. Dead branch. |
| D9 | wiring patch commit message | "All four now clear 4.5:1 on paper" is false — terra 3.96, coral 4.31 (§0.5). |
| D10 | `design/prototypes/qa.py:100` | Contrast floors are 3.0 for terra/marigold/coral and `TEXT_MUTED` is never checked (2.94:1, fails even large-text). |
| D11 | `brand-book.html:8` | Carries the *uncorrected* marigold `#B8791A` (3.23:1) that its own §04 says was replaced. |
| D12 | `render/card.py:36` | `_LABEL_TO_CATEGORY` has no `"Science"` entry; a Science X post would silently render as Technology. |
| D13 | `ranking.py:52` | `explainer` and `how to` penalised — the genre of the product's own evening reel. |
| D14 | `news/feeds.py:63` | No socket timeout on `feedparser.parse()`. |
| D15 | `corroborate.py:242` | No syndication collapse. Six outlets carrying one AP wire read as six independent sources (§6). |
| D16 | `content/` | Empty. No generated day exists in this checkout, so no published artefact could be inspected directly — the audit of live output rests on `preview/` and `state/history.json`. |

---

## 11. Conflicts between the brand book, the branch and the brief

| # | Conflict | Resolution |
|---|---|---|
| C1 | Brand book: carousel → 1–2/**week**. Branch: Tue+Fri gate. Brief: **daily**. | Brief wins. Keep `IG_SECOND_CAROUSEL=False` so the daily total stays at four IG posts. |
| C2 | `receipt.py`: count. Samples + brief: fraction. | Samples win, and the fraction is *earned* by measuring agreement (§7). |
| C3 | Brand book ship order: ranker first, feeds second. Measurement: ranker alone is a lateral move. | Ship as one change (§5). |
| C4 | Brand book: batch TTS to one call per reel. Never written. | Keep — it is a 12× quota reduction and the enabling change for a reliable daily cadence. |
| C5 | Brand book CSS marigold vs corrected renderer marigold. | Renderer constant `#946217` is canonical; correct the brand book. |
| C6 | Brief: reproduce samples exactly. Reality: terra and coral fail 4.5:1 as text. | Reproduce the samples; use terra/coral **only at ≥24px display sizes** (both clear the 3.0 large-text floor), never for body copy. Encode this as a lint, not a colour change — changing the hex would break sample fidelity. |

---

## 12. Execution plan

Ordered so each layer is stable before the one above it lands, and so nothing
publishes non-compliant output at any point in between.

**Phase A — foundation (no visual change ships)**
1. Fix D1 (`__init__.py`), D2 (`.github/workflows/`).
2. `models.py`: `verified`, `sensitive`, and an `Agreement` record on `Story`.
3. `config.py`: paper tokens, Science category, +15 feeds, `FEED_TIMEOUT_SECONDS`,
   `GEMINI_FALLBACK_MODELS`. Keep the dark tokens under `_legacy_` only if a
   caller still needs them; otherwise delete.
4. `fonts.py`: `title_font(size, weight)` → Manrope; retire Anton.

**Phase B — intelligence**
5. Port `interest.py`, `quality.py` and widen the lexicons past the science
   vocabulary (§5). Add the reserved non-universal slot.
6. Port `corroborate.py`, wire it into `pipeline.generate` (fixing D5), add
   **syndication collapse** (D15) and the claim-level agreement classifier (§7).
7. Auditable ranking: log the per-term `breakdown()` for every published story.

**Phase C — design system, native**
8. Rewrite `theme.py` as the paper system: `paper`, `draw_masthead`, `draw_pip`,
   `draw_bubble`, `draw_receipt`, `draw_plate`, `pose_for`, `tone_for`. Delete the
   dark primitives rather than shadowing them (D6, D7, D8).
9. Port `pip.py`, `plate.py`; rewrite `receipt.py` to the fraction model.
10. Rebuild `carousel.py`, `story_card.py`, `card.py` (→ 1200×675, four types),
    `reel.py` (fixing D3, adding plates, Pip, kinetic weight-axis type).

**Phase D — the daily carousel**
11. Story selection → supporting-fact gathering → 5-slide argument generation →
    render → validate → publish, on the existing slot machinery.

**Phase E — quality control**
12. `quality/visual.py`: the `qa.py` assertion families, running against real
    output inside the pipeline, failing safe — a non-compliant post is dropped,
    never published broken.
13. `quality/receipt.py`: agreement arithmetic validation.
14. Extend `tests/` with the six ported test files plus new visual tests.

---

### What this audit did not cover

- No generated day exists in `content/`, so no *published* artefact was inspected;
  live-output findings rest on `preview/` and `state/history.json` (D16).
- The `redesign/pip` branch at `ee1931e` was not checked out — this working copy
  is not a git repository. Everything about the branch is read from
  `design/ported/branch-vs-live.diff` and `design-wiring.patch`.
- Reddit tooling was reviewed for architecture only. It is out of scope and
  deliberately unchanged.
