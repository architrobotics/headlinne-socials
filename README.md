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
days there are two news posts covering two different categories. Posts stay
within 280 characters with room reserved for the website and hashtags. Each post
also gets a **branded card** attached automatically.

**LinkedIn: 1 post a day.** These build credibility: how the recommendation
engine works, what AI Search changes, the product philosophy, the founder
journey, engineering decisions, the roadmap. Every Friday it posts a "This Week
in Finance and Tech" roundup instead.

**Instagram: 1 reel, 1 carousel and 1 story card a day.** All three are drawn
from the same design system (`headlinne/render/theme.py`), so a reel, a carousel
and a card read as one brand.

### The design system

Everything sits on **paper** (`#F7F1E6`), not on near-black. Feed presence comes
from contrast at the edge of a post, and warm paper against Instagram's white
chrome separates cleanly while looking like something printed rather than
something generated.

- **One face.** Manrope, on its variable weight axis. That axis is what lets a
  single word inside a headline carry emphasis without changing size, which is
  what the reel's kinetic type is built on.
- **A masthead, not a pill.** The wordmark sits top-left, the date top-right, and
  a coloured rule runs beneath. The rule's colour is semantic: coral for the live
  story, marigold when the sources disagree, mint for agreement.
- **Pip.** A 26-pixel pigeon, named for the BBC pips and for the carrier pigeons
  Paul Reuter flew across the Aachen telegraph gap in 1850. He exists because an
  automated account cannot have a presenter, and a character is the only way a
  faceless brand gets a personality that scales to every post at no cost per
  post. His pose is metadata: a regular reader learns the kind of story from the
  character before reading a word. **Sensitive stories carry no mascot at all.**
- **Plates.** Photographs appear tilted in a paper frame with a strip of tape. A
  straight rectangle reads as a screenshot; a tilted one reads as an object
  someone put there.
- **The source strip.** A tick per outlet and a line stating the agreement.

### The fallback ladder

A slide is never empty and never a bare gradient:

| Rung | When | What renders |
| --- | --- | --- |
| 1 | The article has a usable photo | The photo, tilted in a paper frame with a source caption |
| 2 | No photo, the category has a scene | A generated pixel scene, captioned `ILLUSTRATION - NOT A PHOTOGRAPH`, always |
| 3 | No photo, but the story has figures | A chart plate built from the article's own numbers |
| 4 | Nothing usable | Pip presents the headline. Larger type, more air. |

That caption on rung 2 is not optional and lives inside the plate function rather
than at the call site, so it cannot be forgotten. Shipping a drawn crater a
reader could mistake for a NASA photograph would undo more trust in one post than
the source strip builds in a month.

### The source strip

The component that makes the product's argument. One number decides whether it
builds trust or destroys it, and it is the denominator.

"4 of 32" would be a lie by framing: thirty-two is how many feeds we read, not
how many covered the story. The other twenty-eight never wrote about it, so
counting them as absent agreement invents a disagreement that never happened.

So three counts are tracked, and they are not interchangeable:

- **reported** - outlets that covered the event, *after syndication collapse*. Six
  outlets running one agency wire are one voice wearing six mastheads.
- **agree** - outlets whose account of the central claim matches.
- **conflict** - outlets that reported a materially different figure for it.

An outlet that covered the story but never mentioned the figure is **silent, not
dissenting**. It counts toward `reported` and toward neither of the others, and
it draws no tick, because a hollow tick reads as "this outlet disagrees" and that
would be false.

That distinction is what lets the label be honest in all three shapes:

| Renders | When |
| --- | --- |
| `8 of 8 outlets agree` | every outlet that reported it took a position, and they matched |
| `4 sources agree` | four agreed and the rest were silent, so a count rather than a fraction |
| `3 of 7 outlets agree` | seven took a position and four of them differ |

A story with one source is **not published**. That is a gate, not a penalty.

### The reel (1 a day, 9:30 AM IST)

Reels are the only Instagram surface that reliably reaches people who do not
already follow the account, so the day's single reel gets first claim on the
day's best story. 1080x1920, around 28 seconds, seven beats.

Three things carry the motion, and none of them is a transition effect:

- **Pip walks.** His position is a function of elapsed time across the whole
  reel, so the character crosses the frame once. The pose cycles underneath at
  its own rate, so he is animated whether or not he is moving.
- **The line reveals word by word.** The layout is computed for the finished line
  and only the drawing is withheld, so nothing re-wraps mid-beat, which is the
  difference between a reveal and a jitter.
- **Plates slide in and settle.** A plate that animates on every frame competes
  with the text.

The masthead rule doubles as the completion bar, so a viewer can see how much is
left without a second piece of furniture. **Nothing renders below y=1450** -
Instagram's caption block, handle, audio strip and action rail sit exactly there.

**It is narrated, and the narration drives the edit.** Each cut lasts as long as
the voice needs rather than as long as the code guesses the text takes to read.
The whole script goes to Gemini TTS as **one request per reel** - it used to be
one per beat plus the sign-off, which on the free tier's three-per-minute limit
meant eight calls spaced 21 seconds apart and several minutes of waiting per run.
The trade is that sync comes from word-count proportions rather than measured
clips, which is imperceptible for kinetic text and nothing is lip-synced. If
speech fails for any reason the reel still ships: it falls back to reading-speed
pacing and a silent track, and the burned-in captions carry it.

On a thin news day, when the top story scores below the bar, the reel teaches an
evergreen idea from `config.EDUCATION_TOPICS` instead. A news explainer is worth
a day; an explainer of why a rate rise reaches your loan is worth as long as
loans exist.

### The carousel (1 a day, 4 PM IST)

One carousel, **one story**, five slides doing five different jobs:

| Slide | Job | Tone |
| --- | --- | --- |
| `cover` | what happened | coral |
| `scale` | how big, one number set enormous and what it compares to | terracotta |
| `twist` | the thing you did not already know | marigold |
| `sources` | the receipt, in full, with every outlet named | mint |
| `cta` | the domain, as the loudest object on the slide | terracotta |

That shape is the whole change. The old carousel was a listicle, a cover then
three or five unrelated stories under identical layouts, and a list has no reason
to be swiped past its second entry. An argument does: each slide answers the
question the previous one raised, which is what carries a reader to the last
slide where the call to action lives.

The order is enforced. `quality/visual.py` rejects a carousel whose roles are out
of sequence, because the order *is* the argument.

### The story card (1 a day, 9:30 PM IST)

One article, walked through from start to finish, on a single image. A carousel
asks for a swipe, and every swipe is another chance to leave. This asks for a
save instead, which is worth far more to a post's reach.

The rail is always the same four stops, fixed in code and not up to the model:
**what happened**, **how we got here**, **why it matters**, **what to watch**. A
reader who has seen one knows where the "does this affect me" line will be before
they have finished the headline.

The layout measures the steps first and hands the headline whatever is left, and
it **shrinks the type rather than cutting a line**. The step most likely to run
long is "why it matters", which is the one a reader came for.

### The X cards (1200 x 675)

On X the post text is the hook, so the image has to add something rather than
repeat it. The card carries the proof:

| Layout | Shows |
| --- | --- |
| `receipt` | who reported it, every outlet named, a tick each |
| `compare` | two outlets, one document, two different numbers |
| `correct` | the original claim struck through, and what was established later |
| `plate` | one figure beside one image |

The correction card is the one to lead with. It is a format no single-outlet
account can run, and it makes the argument for the product without a word of
marketing.
## Why the format mix looks like this

Worth reading before changing it, because the reasoning is the useful part.

**Reels exist to be found. Everything else exists to convert.** Instagram serves
the Reels tab to people who do not follow you, and shows feed posts almost
entirely to people who already do. An account with no video is therefore close to
invisible to anyone new, however good the carousels are. That is why the reel
leads the day and gets first claim on the day's best story, where the search
interest already exists. The carousel takes the second-best one, so the day never
spends two of its three posts on the same event.

**Carousels and cards earn more per person reached, so they follow the reels.**
Once someone has arrived, a format that is dense and saveable is worth more than
another one asking to be discovered. The story card is the strongest version of
that, because it is complete on one frame and the natural response is to keep it.

**The evergreen explainer is the part that compounds.** A news explainer is
worth a day. An explainer of why a rate rise reaches your loan is worth as long
as loans exist, and it keeps being served long after it was posted. An account
that only posts news has nothing that accumulates, which is why the reel falls
back to a topic from `EDUCATION_TOPICS` when the day's best story is not worth
thirty seconds.

**More posting is not more reach.** Three Instagram posts a day is what a small
account can carry. Each post competes with the others for the same initial test
audience, so a fourth does not add reach, it divides it, and the reel is the one
that has to win that competition because it is the only surface reaching people
who do not already follow.

This used to be four - two reels plus one or two carousels plus the card. The
second reel and the second carousel are now opt-in (`SECOND_REEL=true`,
`IG_SECOND_CAROUSEL=true`). Both slots still exist and still publish if something
is written into them, so a manual extra post needs no code change.

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
can earn), the follow and site line, then a handful of topical hashtags.

The long tail of tags goes at the **end of the caption**. Posting it as a first
comment would be tidier, but that is a paid Buffer feature and the free plan
rejects the whole post rather than ignoring the field, which is a bad trade for a
cosmetic gain. The tags work identically from the end of a caption, and the
opening line, the part that actually drives search, is unaffected either way. On
a paid Buffer plan set `BUFFER_FIRST_COMMENT=true` for the cleaner version; if
the plan turns out not to support it, the publisher retries once without the
field and folds the tags back into the caption rather than losing the post.

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
| `BUFFER_FIRST_COMMENT` | `false` | Post the hashtag tail as a first comment. Needs a **paid** Buffer plan |
| `PUBLIC_IMAGE_BASE_URL` | empty | Only needed for a private repo (step 1) |
| `X_ATTACH_CARD` | `true` | Attach the branded image card to X posts |
| `REELS_ENABLED` | `true` | Render and publish the daily reel |
| `STORY_CARD_ENABLED` | `true` | Render and publish the daily story card |
| `CAROUSEL_ENABLED` | `true` | Render and publish the daily carousel |
| `IG_SECOND_CAROUSEL` | `false` | Set `true` to add a second carousel |
| `SECOND_REEL` | `false` | Set `true` to add an evening educational reel |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.1-flash,...` | Models to fall through to when the primary hits its daily cap |
| `FEED_TIMEOUT_SECONDS` | `12` | Per-feed socket timeout, so one stalled publisher cannot hang the run |
| `REEL_CRF` | `20` | x264 quality for reels (lower is better and bigger) |
| `REEL_PRESET` | `veryfast` | x264 speed preset |
| `REEL_VOICEOVER` | `true` | Narrate reels with Gemini TTS |
| `REEL_TTS_MODEL` | `gemini-3.1-flash-tts-preview` | Speech model |
| `REEL_VOICE_NEWS` | `Charon` | Voice for the morning news reel |
| `REEL_VOICE_EDUCATION` | `Kore` | Voice for the evening lesson |
| `REEL_TTS_MIN_INTERVAL` | `21` | Seconds between speech calls. Rarely applies now that a reel costs one call |
| `REEL_TTS_FALLBACK_MODELS` | `gemini-2.5-flash-preview-tts,gemini-2.5-pro-preview-tts` | Comma-separated models to fall through to when the primary hits its quota |
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
| generate | 06:00 | 00:30 | (none) | Gather, write, render, validate, commit |
| reel-1 | 09:30 | 04:00 | Instagram | The daily reel |
| x-1 | 13:00 | 07:30 | X | First post (news or promo) |
| instagram-1 | 16:00 | 10:30 | Instagram | The daily carousel |
| x-2 | 17:00 | 11:30 | X | Second post (only on non-promo days) |
| linkedin | 18:00 | 12:30 | LinkedIn | Daily post or Friday roundup |
| instagram-2 | 18:00 | 12:30 | Instagram | Second carousel (off by default) |
| reel-2 | 20:00 | 14:30 | Instagram | Second reel (off by default) |
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

Previews are **silent**: the reel is paced at reading speed and spends no API
request. Cut points and layout are what a preview is for, and both are honest
without the voice. A real generate run narrates it.

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
│   ├── news/                Fetch feeds, rank, and corroborate
│   │   ├── interest.py      Nine-term interest score: is this worth reading?
│   │   ├── quality.py       The news-worthiness gate: what is not news at all
│   │   ├── corroborate.py   Independent outlets, syndication, claim agreement
│   │   ├── _lexicon.py      Boundary-anchored term matching, shared by both
│   │   └── ranking.py       Clustering, scoring, the reserved slot, audit log
│   ├── gemini/              Gemini clients and the prompts
│   │   ├── client.py        JSON generation for all the copy
│   │   └── tts.py           Speech generation for reel narration
│   ├── generate/            Builds X, LinkedIn and Instagram content
│   │   ├── hooks.py         Hook archetype rotation and caption assembly
│   │   ├── instagram.py     The daily carousel: one story, five slides
│   │   ├── reel.py          The daily reel script, plus figure verification
│   │   └── story_card.py    The daily walk-through card
│   ├── render/              Draws every visual with Pillow (video via ffmpeg)
│   │   ├── theme.py         The design system: paper, masthead, Pip, receipt
│   │   ├── pip.py           The mascot: 6 poses, 6 animation cycles, 26px wide
│   │   ├── plate.py         Tilted taped frames and the 4-rung fallback ladder
│   │   ├── receipt.py       The source strip: ticks, label, state, pose
│   │   ├── fonts.py         Manrope on its weight axis, plus fitting helpers
│   │   ├── carousel.py      The five slide layouts
│   │   ├── card.py          The four X card layouts, 1200x675
│   │   ├── story_card.py    The single-image walk-through layout
│   │   ├── motion.py        Encoder, easing, frames piped into ffmpeg
│   │   ├── graphics.py      Explanatory devices for educational reels
│   │   ├── voice.py         Narration track, and the pacing it dictates
│   │   └── reel.py          Frame rendering, the element trace, the encode
│   ├── reddit/              Reddit opportunity finder + human-review assistant
│   │   ├── client.py        Reddit API (read + guarded single-comment submit)
│   │   ├── relevance.py     Topic fit and sensitive-topic filtering
│   │   ├── policy.py        Caps, cooldowns, de-dup, the 9:1 promo ratio
│   │   ├── drafts.py        Gemini-drafted helpful replies
│   │   └── pipeline.py      Build the review queue, guarded manual post
│   ├── publish/             Buffer, Meta Graph API, image hosting
│   └── quality/             Sanitiser, text gate, visual gate, de-duplication
│       ├── checks.py        Character limits, punctuation, clickbait
│       └── visual.py        Collision, safe zone, contrast, receipt arithmetic
├── tests/                   Offline test suite (python -m tests)
├── assets/
│   ├── fonts/               Manrope (display + body), Inter, Anton (legacy)
│   └── logo.png             The app tile, for store surfaces
├── design/
│   ├── AUDIT.md             The pre-redesign audit and its defect register
│   ├── brand-book.html      The design system, as presented
│   ├── samples/             The approved renders. These are the source of truth
│   └── prototypes/          The programs the samples were rendered from
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
generate log, which names the beat that failed. In order of likelihood:

1. **Speech quota.** The free tier is three TTS requests a minute and a daily
   cap on top of that. A reel costs **one** request, so hitting this now means
   either the daily cap or a key without speech access - check the next item
   before touching `REEL_TTS_MIN_INTERVAL`.
2. **Model access.** `REEL_TTS_MODEL` must be a model your key can reach. The
   speech models are separate from the text model, so a `GEMINI_API_KEY` that
   generates copy fine does not by itself guarantee TTS access.
3. **An empty repository variable.** Only if you have created `REEL_VOICEOVER`
   and left it blank, which now reads as "not configured" rather than "off".

The reel is still correct and still publishes either way, it just loses the
narration and falls back to reading-speed pacing.

**The repository is getting large.** Each day commits two MP4s of a megabyte or
two. The generate run prunes rendered PNGs and MP4s older than six days
(`storage.MEDIA_KEEP_DAYS`), which keeps the working tree small, but git history
still holds every version. If that becomes a problem, serve media from an object
store via `PUBLIC_IMAGE_BASE_URL` instead of committing it.

---

Built as a foundation to grow with Headlinne. The code favours clear, readable
structure over cleverness, so it is easy to extend as the product evolves.
