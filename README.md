# Headlinne Social Automation

Autonomous daily social media for [HEADLINNE.com](https://HEADLINNE.com). Every
day this system gathers the most significant news in Technology, Finance and
Geopolitics, writes human-sounding posts, renders Instagram reels, carousels and
explainer cards from a shared design system, and publishes to X, LinkedIn and
Instagram on a fixed schedule. It runs entirely on free infrastructure: GitHub
Actions for compute, a daily trigger from cron-job.org, Buffer for publishing,
and the Meta Graph API as an alternative Instagram path. Content is written by
Google's `gemini-3.1-flash-lite` model.

There is no server to maintain. You set it up once, add your keys, and it posts
on its own.

---

## Table of contents

1. [How it works](#how-it-works)
2. [What it posts](#what-it-posts)
3. [Why the format mix looks like this](#why-the-format-mix-looks-like-this)
4. [The writing style](#the-writing-style)
5. [Hooks and captions](#hooks-and-captions)
6. [Reddit engagement](#reddit-engagement-opportunity-finder-not-a-spam-bot)
7. [Prerequisites](#prerequisites)
8. [Setup](#setup)
   - [1. Create the repository](#1-create-the-repository)
   - [2. Get a Gemini API key](#2-get-a-gemini-api-key)
   - [3. Connect Buffer (X and LinkedIn)](#3-connect-buffer-x-and-linkedin)
   - [4. Connect the Meta Graph API (Instagram)](#4-connect-the-meta-graph-api-instagram)
   - [5. Add GitHub secrets and variables](#5-add-github-secrets-and-variables)
   - [6. Schedule the daily trigger with cron-job.org](#6-schedule-the-daily-trigger-with-cron-joborg)
9. [Scheduled mode vs trigger mode](#scheduled-mode-vs-trigger-mode)
10. [The daily schedule](#the-daily-schedule)
11. [Running and testing locally](#running-and-testing-locally)
12. [Project structure](#project-structure)
13. [Customising](#customising)
14. [Troubleshooting](#troubleshooting)

---

## How it works

The day splits into two stages.

**Generate (morning).** Once a day GitHub Actions runs the generate job. It pulls
RSS feeds from a list of reputable publishers, clusters stories that appear in
several outlets so it can verify them across sources, and ranks them by
significance rather than by how recently they were published. A story backed by
more independent, trusted sources scores higher. From the ranking it picks the
strongest categories of the day, asks Gemini to write the copy, renders the
Instagram carousels and the story card with Pillow and the two reels with Pillow
plus ffmpeg, and commits everything to the `content/` folder. It also records a
small rolling history in `state/` so it does not repeat stories or phrasing over
the following days, and prunes rendered media older than six days so a daily pair
of videos does not grow the repository without bound.

Each Instagram format is generated independently and failures are contained. If
a reel cannot be encoded, or the model returns a story card with half its steps
empty, that one format is dropped from the day and everything else still goes
out.

**Publish (through the day).** At each scheduled time a lightweight trigger fires
and the matching post goes out. X and LinkedIn go through Buffer. Instagram
carousels are published directly through the Meta Graph API, which has no native
scheduling, so they always post at trigger time.

A key design choice: the model writes the words, the code owns the structure and
the limits. Gemini returns small pieces of JSON. The code assembles them, strips
anything the brief forbids, and enforces character limits deterministically. That
is why the rules hold every single time, not just most of the time.

cron-job.org has a 30 second request limit, so it never does any real work. It
only calls the GitHub `workflow_dispatch` API, which returns instantly. All the
gathering, generating, rendering and publishing happens on GitHub's runners.

---

## What it posts

**X (Twitter): 2 posts a day.** Every second day is a single Headlinne promo post
that highlights a product feature in an educational, non-salesy way. On the other
days there are two news posts covering two different categories. Each news post
leads with a short line and lists the top stories with brief explanations. Posts
stay within 280 characters with room reserved for the website and hashtags. Each
post also gets a **branded image card** (rendered from the same design system as
the carousels) attached automatically, which lifts reach in the timeline. The
tweet text stays a valid standalone post, so the card is a bonus, not a
dependency. Turn it off with the `X_ATTACH_CARD` variable.

**LinkedIn: 1 post a day.** These build credibility: how the recommendation
engine works, what AI Search changes, the product philosophy, the founder
journey, engineering decisions, the roadmap. Every Friday it posts a "This Week
in Finance and Tech" roundup instead. Professional but approachable, no
buzzwords, no hashtags, with a light invitation to visit the site.

**Instagram: 2 reels, 1 story card and 1 or 2 carousels a day.** All four formats
are drawn from the same design system (`headlinne/render/theme.py`), so a reel, a
carousel and a card read as one brand.

### Reels (2 a day)

Reels are the only Instagram surface that reliably reaches people who do not
already follow the account, so they lead the day and close it.

- **Morning (9:30 AM IST): a news explainer.** Walks through the single biggest
  story of the day. Hook, what happened, the mechanism, a graphic, why it matters
  to you.
- **Evening (8 PM IST): an educational explainer.** Teaches one evergreen idea
  with a small worked example: why a rate hike reaches your loan, what a sanction
  actually does, why two outlets report the same story differently. These are
  what get saved and sent on, and they keep earning reach weeks later. The topic
  rotates deterministically through the list in `config.EDUCATION_TOPICS`, so a
  full cycle takes about a fortnight.

Both are 1080x1920, cut into six beats plus a sign-off. Narrated they run around
35 to 40 seconds; silent, about 28. Every word is also burned into the frame
because most reels are watched muted, a progress bar across the top tells the
viewer how much is left, and nothing important sits where Instagram draws its own
caption and action rail.

**They are narrated.** Gemini TTS speaks a line per beat, and *the narration
drives the edit*: each cut lasts exactly as long as its spoken line plus a little
air, rather than as long as the code guesses the text takes to read. The spoken
line is written separately from the on-screen line, because a sentence written to
be glanced at and a sentence written to be said are rarely the same one, and the
prompt asks for both. The morning and evening reels use different voices so the
news brief and the lesson do not sound like one person reading two scripts.

That matters beyond sounding better: a reel with a real audio track is a more
complete post than one carrying silence, and anyone who unmutes gets something
rather than nothing. The two voices, the delivery direction and the pacing are
all in `config.py` under "Instagram Reels", and are worth auditioning before you
settle on them.

If speech cannot be produced (no key, a quota, an outage) the reel still ships:
it falls back to reading-speed pacing and a silent track, logs a warning through
the quality gate, and the burned-in captions carry the content. Set
`REEL_VOICEOVER=false` to choose silence deliberately.

Worth knowing about cost: narration is **one API call per beat**, so two reels
add about fourteen speech requests a day on top of the text generation, and a
couple of minutes to the generate run. Speech quotas are counted separately from
text quotas on a Gemini key, so if reels start coming out silent while the
written copy is fine, that is the first place to look.

**One beat carries a graphic instead of a photo.** This is what makes an
explainer feel authored rather than templated, and there are five devices to
choose from, in `headlinne/render/graphics.py`:

| Device | What it shows | Prints figures? |
| --- | --- | --- |
| `flow` | a cause-and-effect chain, three chips joined by arrows | no |
| `split` | one direct contrast, two stacked panels with a VS pivot | no |
| `timeline` | what happens over time, a rail filling through labelled stops | no |
| `bars` | two or three quantities compared by height | optionally |
| `counter` | one striking figure, counted up | yes |

The split matters. `bars` and `counter` print numbers, which is a factual claim
in a form people screenshot, so **every figure they print is checked character by
character against the source article** and anything that does not appear there is
removed (`generate/reel.py`). Bar *heights* are a separate, softer claim about
relative size, so a bar can still show direction without printing a statistic.
Educational reels lose printed figures entirely, since their examples are openly
hypothetical and a hypothetical number drawn as a chart stops looking
hypothetical.

### The story card (1 a day, 9:30 PM IST)

One article, walked through from start to finish, on a single image. A carousel
asks for a swipe, and every swipe is another chance to leave. This asks for a
save instead, which is worth far more to a post's reach.

The rail is always the same four stops, fixed in code and not up to the model:
**what happened**, **how we got here**, **why it matters**, **what to watch**. A
reader who has seen one of these knows where the "does this affect me" line will
be before they have finished the headline. The layout measures the steps first
and hands the headline whatever is left over, so a long story shrinks its type
rather than silently truncating the line that carries the point.

### Carousels (1 or 2 a day)

One for each of the strongest categories, at 4 PM and 6 PM IST. Each covers the
top 3 or top 5 stories (the system decides based on how strong the deeper stories
are). Every slide is built from the shared design system so the whole set reads
as one polished, editorial template:

- **Brand furniture on every slide.** The `h` logo mark and the `HEADLINNE`
  wordmark sit top-left, a category pill (colour-coded) sits top-right, and a row
  of page-progress pips shows how far through the set you are. Because carousels
  get screenshotted and reshared, the brand travels with every slide.
- **Cover slide:** a full-bleed photo under a cinematic scrim, a dateline eyebrow
  ("Your daily brief · Tue, 21 Jul"), a large curiosity-driven title written by
  the model, a one-line hook, and a "Swipe" affordance to pull people in.
- **Story slides:** the article photo with the same furniture, a large ghosted
  index number ("01"), an accent rule, the headline, a short "what happened and
  why it matters", and a **Sources** line naming the outlets that corroborated
  the story. That trust line is the audience-facing side of the cross-source
  verification the ranker already does.
- **Final slide:** a warm branded sign-off with the logo, a "Follow" and a "Save"
  call to action (the two actions Instagram rewards most), and the website.

Colours are one warm family anchored on the terracotta logo: a coral accent for
Technology, emerald for Finance and amber for Geopolitics. When a story has no
usable photo, the renderer draws a designed, category-tinted brand background
instead of a flat block, so a slide is never empty. The model never generates
images. It only produces the text that fills the template. The renderer draws
everything.

The second carousel is optional. Set the `IG_SECOND_CAROUSEL` variable to
`false` to drop to one a day, which is the recommendation once the reels are
running (see the next section).

---

## Why the format mix looks like this

Worth reading before changing it, because the reasoning is the useful part.

**Reels exist to be found. Everything else exists to convert.** Instagram serves
the Reels tab to people who do not follow you, and shows feed posts almost
entirely to people who already do. An account with no video is therefore close to
invisible to anyone new, however good the carousels are. That is why the two
reels bracket the day, and why the morning one covers the day's biggest story,
where the search interest already exists.

**Carousels and cards earn more per person reached, so they follow the reels.**
Once someone has arrived, a format that is dense and saveable is worth more than
another one asking to be discovered. The story card is the strongest version of
that, because it is complete on one frame and the natural response is to keep it.

**The educational reel is the part that compounds.** A news explainer is worth a
day. An explainer of why a rate rise reaches your loan is worth as long as loans
exist, and it keeps being served long after it was posted. An account that only
posts news has nothing that accumulates.

**More posting is not more reach.** Four Instagram posts a day is at the top of
what a small account can carry: each post competes with the others for the same
initial test audience, and going past that point makes every one of them land
softer. If you want to add a format, take one away. `IG_SECOND_CAROUSEL=false`
is the intended lever, leaving one reel, one carousel, one reel and the story
card.

---

## The writing style

Every post follows the same voice, enforced in code:

- Simple, clear, conversational English. Short sentences.
- **No em dashes and no semicolons, ever.** The sanitiser strips them out
  deterministically, so even if the model slips, the published text is clean.
- Friendly, modern and trustworthy. No clickbait, no hype, no invented numbers.
- Original wording, never copied from the source articles.

The shared style guide also pushes for **honest hooks** (lead with the most
interesting concrete fact, create curiosity through substance rather than
withholding), **engagement** (captions end with a genuine question, carousels
invite a follow and a save) and **accuracy** (only claim what the sources
support, never overstate certainty). Impressions are earned by being genuinely
interesting and correct, not by hyping.

These guarantees are covered by the test suite (see
[Running and testing locally](#running-and-testing-locally)).

---

## Hooks and captions

Two things decide whether a post is seen at all: the first two seconds of a reel
and the first line of a caption. Both are owned by `headlinne/generate/hooks.py`
rather than left to the model.

**The hook's shape is rotated in code.** Left to itself a model writes the same
opener every day ("X just announced Y, and here is why it matters"), and an
account that opens the same way daily teaches both the algorithm and the audience
to scroll past. So the model is handed a specific rhetorical shape to write into,
picked deterministically from the day and the slot. There are eight, and they are
the ones that actually earn watch time in news and finance explainers:

`contradiction` (name the assumption, then puncture it) · `stakes` (what this
costs you) · `scale` (make the number picturable) · `mechanism` (promise the
machinery, not the event) · `consequence` (open from the future) ·
`question_gap` (a real puzzle the reporting answers) · `analogy` (transplant it
into something domestic) · `count` (three things, one of them expensive).

The rotation is offset by slot, so the morning and evening reels never open the
same way on the same day.

**Captions lead with keywords, not hashtags.** Instagram indexes caption text for
search now, so the opening line is worth far more as a readable, searchable
sentence than as a block of tags. Every caption is built the same way: an opener
that fits inside the ~125 characters shown before "more", the substance in short
paragraphs, one genuine question (comments are the heaviest ranking signal a post
can earn), the follow and site line, then a handful of topical hashtags. The long
tail of tags goes to the **first comment**, where Instagram treats them the same
but they do not clutter what a reader sees.

---

## Reddit engagement (opportunity finder, not a spam bot)

Reddit can be a great channel for a news app, but only if you engage like a real
person. This tool is built for that, and it is deliberately **not** an autonomous
mass-poster.

**Why not a 100-comments-a-day bot?** Automated, unsolicited promotion violates
Reddit's Content Policy and API Terms, and essentially every large subreddit bans
it. A bot spraying promotional comments gets the account and the `headlinne.com`
domain sitewide-shadowbanned, which is very hard to undo and kills the exact
channel you are trying to open. It does not grow a product, it burns it.

**What it does instead.** `python -m headlinne reddit find`:

1. searches your target subreddits for threads where Headlinne is genuinely
   on-topic (news overload, staying informed, media bias, personalised feeds),
2. filters out threads that are locked, too old, too thin, or sensitive
   (grief, medical, tragedy - those never get a promo angle),
3. drafts a genuinely **helpful** reply with Gemini, in a normal-person Reddit
   voice,
4. honestly decides whether a *disclosed* Headlinne mention is even appropriate
   (usually not, and never more than the 9:1 rule allows, only in communities
   that welcome it),
5. writes a **review queue** to `state/reddit_queue/<date>.json` and a readable
   `.md` file.

You read the queue and post the good ones yourself, or approve one at a time:

```bash
python -m headlinne reddit find                 # build today's review queue (never posts)
python -m headlinne reddit post --id <THREAD_ID> --confirm   # post ONE reviewed draft
```

**Guardrails (in `headlinne/config.py`, enforced in code and tested):** a low
daily cap with a hard maximum, a per-subreddit cooldown, de-duplication so no
thread is engaged twice, the 9:1 helpful-to-promo ratio, and a sensitive-topic
filter. There is no bulk or unattended posting path on purpose.

**Credentials.** Reddit needs a *script app* (create one at
`reddit.com/prefs/apps`), not a single token. Set `REDDIT_CLIENT_ID`,
`REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` and
`REDDIT_USER_AGENT`. If someone hands you one long bearer string as a "Reddit
key", it is almost certainly for another service (for example a Gemini token) and
will not work here.

---

## Prerequisites

- A GitHub account (the repository should be public, see below).
- A Google AI Studio account for a Gemini API key.
- A Buffer account with your X and LinkedIn channels connected.
- A Meta Business account with an Instagram Business or Creator account and a
  Facebook Page linked to it.
- A free cron-job.org account.

No paid news APIs are needed. The system reads public RSS feeds.

---

## Setup

### 1. Create the repository

Create a new GitHub repository and push this project to it.

**Make the repository public.** Instagram fetches carousel images over the
internet, and the simplest free way to host them is to serve the committed
`content/` folder through `raw.githubusercontent.com`, which only works for
public repos. When the repo is public, image hosting needs zero configuration.

If you must keep the repo private, you can instead serve the `content/` folder
from any public host (a CDN, an S3 bucket, GitHub Pages on a separate public
repo, and so on) and set the `PUBLIC_IMAGE_BASE_URL` variable to its base URL.
Everything else works the same.

### 2. Get a Gemini API key

Sign in to Google AI Studio, create an API key, and keep it handy. You will add
it as the `GEMINI_API_KEY` secret in step 5. The model used is
`gemini-3.1-flash-lite`, which is fast and inexpensive. You can change the model
or the thinking level in `headlinne/config.py`.

### 3. Connect Buffer (X and LinkedIn)

Buffer publishes both X and LinkedIn.

1. In Buffer, connect your X account and your LinkedIn account as channels.
2. Get a personal access token: Buffer **Settings → API**. You need to be the
   organisation owner to create one. This becomes `BUFFER_ACCESS_TOKEN`.
3. Find the channel IDs for your X and LinkedIn channels. These become
   `BUFFER_CHANNEL_ID_X` and `BUFFER_CHANNEL_ID_LINKEDIN`.

The system talks to Buffer's GraphQL API and schedules each post for its exact
slot time (in scheduled mode), or posts immediately (in trigger mode). Buffer's
free plan is enough for this volume.

### 4. Connect the Meta Graph API (Instagram)

Instagram carousels publish directly through the Meta Graph API.

1. Make sure your Instagram account is a **Business or Creator** account and is
   linked to a **Facebook Page**.
2. Create an app in the Meta for Developers dashboard and add the Instagram
   Graph API product.
3. Generate a **long-lived access token** with the permissions needed to publish
   content (`instagram_basic`, `instagram_content_publish`,
   `pages_read_engagement`, and the related Page permissions). A long-lived token
   lasts about 60 days, so plan to refresh it. This becomes `META_ACCESS_TOKEN`.
4. Get your **Instagram Business user ID**. This becomes `IG_USER_ID`.

The publish flow uploads each slide as a carousel item, waits for Meta to process
it, creates the carousel container, waits again, and then publishes. This is all
handled for you in `headlinne/publish/meta.py`.

### 5. Add GitHub secrets and variables

In your repository, go to **Settings → Secrets and variables → Actions**.

Add these as **secrets** (encrypted, never shown again):

| Secret | What it is |
| --- | --- |
| `GEMINI_API_KEY` | Your Google AI Studio key |
| `BUFFER_ACCESS_TOKEN` | Buffer personal access token |
| `BUFFER_CHANNEL_ID_X` | Buffer channel ID for X |
| `BUFFER_CHANNEL_ID_LINKEDIN` | Buffer channel ID for LinkedIn |
| `META_ACCESS_TOKEN` | Long-lived Meta Graph API token (only if publishing IG directly via Meta) |
| `IG_USER_ID` | Instagram Business user ID (only if publishing IG directly via Meta) |
| `REDDIT_CLIENT_ID` | Reddit script-app client id (only for the Reddit tool) |
| `REDDIT_CLIENT_SECRET` | Reddit script-app secret (only for the Reddit tool) |
| `REDDIT_USERNAME` | Reddit account the tool acts as (only for the Reddit tool) |
| `REDDIT_PASSWORD` | That account's password (only for the Reddit tool) |

Add these as **variables** (plain, non-secret):

| Variable | Default | What it does |
| --- | --- | --- |
| `BUFFER_SCHEDULING_MODE` | `scheduled` | `scheduled` or `trigger`, see below |
| `PUBLIC_IMAGE_BASE_URL` | empty | Only needed for a private repo (step 1) |
| `X_ATTACH_CARD` | `true` | Attach the branded image card to X posts |
| `REELS_ENABLED` | `true` | Render and publish the two daily reels |
| `STORY_CARD_ENABLED` | `true` | Render and publish the daily story card |
| `IG_SECOND_CAROUSEL` | `true` | Set `false` to drop to one carousel a day |
| `REEL_CRF` | `20` | x264 quality for reels (lower is better and bigger) |
| `REEL_PRESET` | `veryfast` | x264 speed preset |
| `REEL_VOICEOVER` | `true` | Narrate reels with Gemini TTS |
| `REEL_TTS_MODEL` | `gemini-3.1-flash-tts-preview` | Speech model |
| `REEL_VOICE_NEWS` | `Charon` | Voice for the morning news reel |
| `REEL_VOICE_EDUCATION` | `Kore` | Voice for the evening lesson |
| `FFMPEG_BINARY` | empty | Path to ffmpeg, if it is not on `PATH` |
| `REDDIT_ENGAGEMENT_CAP` | `12` | Max Reddit drafts per run (hard-capped at 25) |

For local runs, copy `.env.example` to `.env` and fill in the same values. The
`.env` file is git-ignored. Never commit real keys.

**You do not need to create any of the variables above.** Every one has a working
default, and the workflows pass them through as `${{ vars.NAME }}`, which hands
the runner an empty string when the variable does not exist. `config.py` treats
an empty value as "not configured" and uses the default, so a variable is only
worth creating when you want to *change* something. To turn a feature off, set
it to `false` rather than clearing it, since clearing it just restores the
default.

### 6. Schedule the daily trigger with cron-job.org

cron-job.org calls the GitHub `workflow_dispatch` API on a schedule. The full
walkthrough, including the exact request bodies, the IST to UTC conversion table,
and how to create a GitHub personal access token for the calls, is in
[`scripts/cron-jobs.md`](scripts/cron-jobs.md).

In short: you create a GitHub token with `actions: write` permission, then add
cron jobs that POST to the workflow dispatch endpoint for the generate workflow
(once in the morning) and the publish workflow (once per Instagram slot, plus the
X and LinkedIn slots if you use trigger mode).

In **scheduled mode** you only need three cron jobs: generate in the morning, and
the two Instagram slots. X and LinkedIn are already scheduled inside Buffer during
generation. This is the recommended setup.

---

## Scheduled mode vs trigger mode

This controls how X and LinkedIn get published. Set it with the
`BUFFER_SCHEDULING_MODE` variable.

**`scheduled` (default, recommended).** During the morning generate run, the
system schedules the X and LinkedIn posts directly into Buffer with each post's
exact slot time. Buffer publishes them for you. The publish triggers for X and
LinkedIn become no-ops. You only need three cron jobs total.

**`trigger`.** Nothing is pre-scheduled. Instead cron-job.org fires a trigger at
each slot and the post publishes immediately at that moment. This gives you a
trigger for every slot but keeps Buffer's queue empty between runs. You need a
cron job for all six slots.

Instagram is always published at its slot time in both modes, because the Meta
Graph API does not support scheduling.

---

## The daily schedule

All times are IST. The generate run happens once in the morning. Each post then
fires at its slot.

| Slot | IST | UTC | Platform | What |
| --- | --- | --- | --- | --- |
| generate | 06:00 | 00:30 | (none) | Gather, write, render, commit |
| reel-1 | 09:30 | 04:00 | Instagram | News explainer reel |
| x-1 | 13:00 | 07:30 | X | First post (news or promo) |
| instagram-1 | 16:00 | 10:30 | Instagram | First carousel |
| x-2 | 17:00 | 11:30 | X | Second post (only on non-promo days) |
| linkedin | 18:00 | 12:30 | LinkedIn | Daily post or Friday roundup |
| instagram-2 | 18:00 | 12:30 | Instagram | Second carousel (optional) |
| reel-2 | 20:00 | 14:30 | Instagram | Educational explainer reel |
| story-card | 21:30 | 16:00 | Instagram | The daily story card |

In scheduled mode you do not need cron jobs for x-1, x-2 or linkedin. Buffer
handles those. The Instagram slots always need a trigger, because Meta has no
native scheduling and Buffer publishes these at call time.

The generate workflow also has a built-in backup schedule at 00:30 UTC in case
the external trigger ever misses a day. You can remove it if you prefer to rely
only on cron-job.org.

---

## Running and testing locally

You do not need any API keys to preview the design or run the tests.

**Preview every format.** This renders sample carousels, X cards, the story card
and both reels with mock content, fully offline, so you can check how everything
looks without spending a Gemini call or waiting for a scheduled run:

```bash
pip install -r requirements.txt
python -m headlinne preview --out preview
```

Open the PNGs and MP4s it writes under `preview/`.

The reels take a couple of minutes each to render, so while you are iterating on
the still formats you can skip them:

```bash
python -m headlinne preview --out preview --no-video
```

Previews use a **stub voice** by default: silence of exactly the length the real
narration would take, so the pacing and the cut points are honest without
spending an API request. To hear the actual voices (needs `GEMINI_API_KEY`):

```bash
python -m headlinne preview --out preview --voice
```

**About ffmpeg.** Reels are encoded with ffmpeg. GitHub's Ubuntu runners already
ship it, so CI needs nothing extra. Locally, `imageio-ffmpeg` in
`requirements.txt` carries a static build, so `pip install -r requirements.txt`
is enough on Windows and macOS too. If you have your own build somewhere unusual,
point `FFMPEG_BINARY` at it. When no encoder can be found the reels are skipped
with a clear error and the rest of the day still generates.

**Run the test suite.** The tests cover the parts that must never break: the
forbidden-punctuation guarantees, the 280 character limit, the schedule maths,
the ranking and clustering, and the de-duplication. They never touch the network:

```bash
python -m tests          # zero-dependency runner, no pytest needed
# or, if you have pytest:
pytest tests
```

**Run the real pipeline locally.** With a filled-in `.env`, you can run the full
generate step on your own machine:

```bash
python -m headlinne generate                # gather, write, render, schedule
python -m headlinne generate --no-render     # skip image and video rendering
python -m headlinne generate --no-schedule   # do not touch Buffer
python -m headlinne publish --target reel-1   # publish one slot
```

**Trigger a run manually on GitHub.** In the Actions tab you can run either
workflow by hand with "Run workflow", which is the easiest way to confirm your
keys are set up correctly before relying on the schedule.

---

## Project structure

```
headlinne-social/
├── headlinne/
│   ├── config.py            All tuning: feeds, schedule, colours, limits, model
│   ├── models.py            Typed data passed between stages
│   ├── scheduling.py        IST slot maths, promo and Friday rules
│   ├── pipeline.py          Orchestrates generate and publish
│   ├── storage.py           Reads and writes the content/ folder
│   ├── cli.py               Command-line entry point
│   ├── news/                Fetch feeds, extract images, rank and verify
│   ├── gemini/              Gemini clients and the prompts
│   │   ├── client.py        JSON generation for all the copy
│   │   └── tts.py           Speech generation for reel narration
│   ├── generate/            Builds X, LinkedIn and Instagram content
│   │   ├── hooks.py         Hook archetype rotation and caption assembly
│   │   ├── reel.py          Both reel scripts, plus figure verification
│   │   └── story_card.py    The daily walk-through card
│   ├── render/              Draws every visual with Pillow (video via ffmpeg)
│   │   ├── theme.py         The design system: palette, furniture, fallbacks
│   │   ├── fonts.py         Display / body / label font loading and fitting
│   │   ├── carousel.py      Cover, story and CTA slide layouts
│   │   ├── card.py          Branded square image card for X posts
│   │   ├── story_card.py    The single-image walk-through layout
│   │   ├── motion.py        Animation engine, frames piped into ffmpeg
│   │   ├── graphics.py      The five explanatory devices for reel graphics
│   │   ├── voice.py         Narration track, and the pacing it dictates
│   │   └── reel.py          Hook, beat, graphic, payoff and outro layouts
│   ├── reddit/              Reddit opportunity finder + human-review assistant
│   │   ├── client.py        Reddit API (read + guarded single-comment submit)
│   │   ├── relevance.py     Topic fit and sensitive-topic filtering
│   │   ├── policy.py        Caps, cooldowns, de-dup, the 9:1 promo ratio
│   │   ├── drafts.py        Gemini-drafted helpful replies
│   │   └── pipeline.py      Build the review queue, guarded manual post
│   ├── publish/             Buffer, Meta Graph API, image hosting
│   └── quality/             Sanitiser, quality gate, de-duplication
├── tests/                   Offline test suite (python -m tests)
├── assets/
│   ├── fonts/               Display and body fonts
│   └── logo.png             The Headlinne logo used on the CTA slide
├── scripts/
│   └── cron-jobs.md         cron-job.org setup walkthrough
├── .github/workflows/
│   ├── generate.yml         Daily generate job
│   ├── publish.yml          Per-slot publish job
│   └── tests.yml            Runs the test suite on every push
├── content/                 Generated output, one folder per day (auto-created)
├── state/                   Rolling history for de-duplication (auto-created)
├── requirements.txt
└── .env.example
```

---

## Customising

Almost everything you might want to change lives in `headlinne/config.py`:

- **News sources.** Add or remove feeds in the `FEEDS` list. Each has a `tier`
  weight for how much to trust it. A dead feed is skipped, not fatal.
- **Schedule.** Change the slot times in `SCHEDULE_IST`.
- **Promo rotation.** Move `PROMO_ANCHOR_DATE` to shift which days are promo days
  on X.
- **Categories and colours.** `CATEGORIES`, `CATEGORY_LABELS`, `CATEGORY_PILL`
  and `CATEGORY_COLORS`.
- **Design tokens.** The whole carousel identity lives in the "Brand + design
  system" block: `BRAND_TERRACOTTA`, `INK`, the text colours, the per-category
  accents and `INSTAGRAM_HANDLE`. Set `GEO_USE_FLAG = True` to bring back the old
  stars-and-stripes "Geo" cover treatment. The drawing primitives that use these
  tokens (top bar, pills, progress pips, scrims, fallback backgrounds) live in
  `headlinne/render/theme.py`.
- **Limits.** Character limits, hashtag counts and the carousel canvas size.
- **Reels.** `REEL_TARGET_SECONDS` and the min/max window, `REEL_FPS`, the canvas
  size and the encoder settings.
- **Educational reel topics.** `EDUCATION_TOPICS` is the rotation for the evening
  reel. Each entry is a title, the angle that makes it worth 30 seconds, and the
  graphic device that explains it best. Adding one is the cheapest way to extend
  the evergreen library.
- **Model.** `GEMINI_MODEL`, `GEMINI_THINKING_LEVEL` and `GEMINI_TEMPERATURE`.

The feature list used in X promo posts and the topic list used for LinkedIn live
in `headlinne/generate/common.py`. The hook archetypes are in
`headlinne/generate/hooks.py`, and the prompts themselves are in
`headlinne/gemini/prompts.py`.

**If you change a text length limit, check the layout it feeds.** The character
limits in `generate/reel.py` and `generate/story_card.py` are worked back from
what the frames can carry at a readable size (and, for reels, from reading speed
at four seconds a cut). Raising them does not overflow anything, the renderers
shrink to fit, but the text arrives smaller than it should be.

---

## Troubleshooting

**Instagram publish fails to fetch the image.** The image URL must be publicly
reachable. Confirm the repo is public, or that `PUBLIC_IMAGE_BASE_URL` points to a
host that serves the committed `content/` folder. You can open the image URL in a
private browser window to check.

**Meta token stopped working.** Long-lived Meta tokens expire after about 60
days. Generate a fresh one and update the `META_ACCESS_TOKEN` secret.

**Buffer returns an error.** Buffer's API always responds with HTTP 200 and puts
errors in the response body, which the client surfaces in the logs. Check that
the channel IDs are correct and that the token belongs to the organisation owner.

**A post seems to repeat a recent story.** The de-duplication window is ten days
and is stored in `state/history.json`. If you reset that file, the system loses
its memory of what it has already posted.

**Nothing posted today.** Check the Actions tab for the generate run and the
publish runs. Each commits its output back to the repo, so an empty `content/`
folder for today usually means the generate run did not complete. The most common
cause is a missing or incorrect `GEMINI_API_KEY`.

**Nothing posted for days, and the numbers are flat.** Before changing any
content, confirm the machine is running at all. `state/history.json` records
every day the generate job completed, and `content/<date>/published/` holds a
marker file per slot that actually went out. If the newest day in either is not
today, this is a plumbing problem, not a content problem, and no amount of new
formats will fix it. The usual causes are an expired GitHub PAT on the
cron-job.org jobs (they fail silently from GitHub's side, so check cron-job.org's
own execution history), an expired Meta token, or a Buffer channel that got
disconnected.

**Reels do not publish but carousels do.** Almost always the video URL. Reels are
megabytes rather than kilobytes and `raw.githubusercontent.com` serves them with
a generic content type that some fetchers dislike, so this is the first thing to
move to a real host: point `PUBLIC_IMAGE_BASE_URL` at an object store that serves
the committed `content/` folder. Open the MP4 URL from the run log in a private
browser window to check it plays.

**Reels are skipped entirely.** The log line to look for is "ffmpeg is not
available". On a runner this should never happen, since `imageio-ffmpeg` is in
`requirements.txt`. Locally, install ffmpeg or set `FFMPEG_BINARY`.

**Reels publish but are silent.** Look for "falling back to silence" in the
generate log, which names the beat that failed. The usual causes are a speech
quota, or `REEL_TTS_MODEL` pointing at a model your key cannot reach (the TTS
models are separate from the text model, so a working `GEMINI_API_KEY` does not
by itself guarantee access). The reel is still correct and still publishes, it
just loses the narration.

**The repository is getting large.** Each day commits two MP4s of a megabyte or
two. The generate run prunes rendered PNGs and MP4s older than six days
(`storage.MEDIA_KEEP_DAYS`), which keeps the working tree small, but git history
still holds every version. If that becomes a problem, serve media from an object
store via `PUBLIC_IMAGE_BASE_URL` instead of committing it.

---

Built as a foundation to grow with Headlinne. The code favours clear, readable
structure over cleverness, so it is easy to extend as the product evolves.
#   h e a d l i n n e - s o c i a l s  
 