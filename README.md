# Headlinne Social Automation

Autonomous daily social media for [HEADLINNE.com](https://HEADLINNE.com). Every
day this system gathers the most significant news in Technology, Finance and
Geopolitics, writes human-sounding posts, renders Instagram carousels from a
design template, and publishes to X, LinkedIn and Instagram on a fixed schedule.
It runs entirely on free infrastructure: GitHub Actions for compute, a daily
trigger from cron-job.org, Buffer for X and LinkedIn, and the Meta Graph API for
Instagram. Content is written by Google's `gemini-3.1-flash-lite` model.

There is no server to maintain. You set it up once, add your keys, and it posts
on its own.

---

## Table of contents

1. [How it works](#how-it-works)
2. [What it posts](#what-it-posts)
3. [The writing style](#the-writing-style)
4. [Reddit engagement](#reddit-engagement-opportunity-finder-not-a-spam-bot)
5. [Prerequisites](#prerequisites)
5. [Setup](#setup)
   - [1. Create the repository](#1-create-the-repository)
   - [2. Get a Gemini API key](#2-get-a-gemini-api-key)
   - [3. Connect Buffer (X and LinkedIn)](#3-connect-buffer-x-and-linkedin)
   - [4. Connect the Meta Graph API (Instagram)](#4-connect-the-meta-graph-api-instagram)
   - [5. Add GitHub secrets and variables](#5-add-github-secrets-and-variables)
   - [6. Schedule the daily trigger with cron-job.org](#6-schedule-the-daily-trigger-with-cron-joborg)
6. [Scheduled mode vs trigger mode](#scheduled-mode-vs-trigger-mode)
7. [The daily schedule](#the-daily-schedule)
8. [Running and testing locally](#running-and-testing-locally)
9. [Project structure](#project-structure)
10. [Customising](#customising)
11. [Troubleshooting](#troubleshooting)

---

## How it works

The day splits into two stages.

**Generate (morning).** Once a day GitHub Actions runs the generate job. It pulls
RSS feeds from a list of reputable publishers, clusters stories that appear in
several outlets so it can verify them across sources, and ranks them by
significance rather than by how recently they were published. A story backed by
more independent, trusted sources scores higher. From the ranking it picks the
two strongest categories of the day, asks Gemini to write the copy, renders the
Instagram carousel images with Pillow, and commits everything to the `content/`
folder. It also records a small rolling history in `state/` so it does not repeat
stories or phrasing over the following days.

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

**Instagram: 2 carousels a day.** One for each of the two strongest categories,
at 4 PM and 6 PM IST. Each carousel covers the top 3 or top 5 stories (the system
decides based on how strong the deeper stories are). Every slide is built from a
shared design system (`headlinne/render/theme.py`) so the whole set reads as one
polished, editorial template:

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
| `REDDIT_ENGAGEMENT_CAP` | `12` | Max Reddit drafts per run (hard-capped at 25) |

For local runs, copy `.env.example` to `.env` and fill in the same values. The
`.env` file is git-ignored. Never commit real keys.

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
| x-1 | 13:00 | 07:30 | X | First post (news or promo) |
| instagram-1 | 16:00 | 10:30 | Instagram | First carousel |
| x-2 | 17:00 | 11:30 | X | Second post (only on non-promo days) |
| linkedin | 18:00 | 12:30 | LinkedIn | Daily post or Friday roundup |
| instagram-2 | 18:00 | 12:30 | Instagram | Second carousel |

In scheduled mode you do not need cron jobs for x-1, x-2 or linkedin. Buffer
handles those.

The generate workflow also has a built-in backup schedule at 00:30 UTC in case
the external trigger ever misses a day. You can remove it if you prefer to rely
only on cron-job.org.

---

## Running and testing locally

You do not need any API keys to preview the design or run the tests.

**Preview the Instagram carousel design.** This renders sample carousels with
mock content, fully offline, so you can check how the slides look:

```bash
pip install -r requirements.txt
python -m headlinne preview --out preview
```

Open the PNGs it writes under `preview/`.

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
python -m headlinne generate --no-render     # skip image rendering
python -m headlinne generate --no-schedule   # do not touch Buffer
python -m headlinne publish --target x-1      # publish one slot
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
│   ├── gemini/              Gemini client and the prompts
│   ├── generate/            Builds X, LinkedIn and Instagram content
│   ├── render/              Draws the carousel slides with Pillow
│   │   ├── theme.py         The design system: palette, furniture, fallbacks
│   │   ├── fonts.py         Display / body / label font loading and fitting
│   │   ├── carousel.py      Cover, story and CTA slide layouts
│   │   └── card.py          Branded square image card for X posts
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
- **Model.** `GEMINI_MODEL`, `GEMINI_THINKING_LEVEL` and `GEMINI_TEMPERATURE`.

The feature list used in X promo posts and the topic list used for LinkedIn live
in `headlinne/generate/common.py`. The prompts themselves are in
`headlinne/gemini/prompts.py`.

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

---

Built as a foundation to grow with Headlinne. The code favours clear, readable
structure over cleverness, so it is easy to extend as the product evolves.
#   h e a d l i n n e - s o c i a l s  
 