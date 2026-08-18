# Scheduling with cron-job.org

cron-job.org fires the GitHub Actions in this repo at the right times. Each job
sends exactly one HTTP request that starts a workflow and returns immediately, so
it always finishes well inside cron-job.org's 30 second limit. All the real work
(fetching, ranking, writing, rendering, encoding, publishing) runs on GitHub's
runners.

**The short version.** In the default setup you need **four** cron jobs, and you
must remove one line from `generate.yml` first. Read [Before you start](#before-you-start).

---

## Before you start

### Remove the built-in generate schedule, or skip the generate cron job

`.github/workflows/generate.yml` currently contains its own schedule:

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "30 0 * * *"   # 06:00 IST backup run
```

That means **GitHub already runs the generate job every day at 00:30 UTC**. If
you also create a cron-job.org job at the same time, the whole day generates
twice: two sets of Gemini text calls, two speech requests, two full renders, and
two commits racing each other. `concurrency: cancel-in-progress: false` means the
second one queues and then runs rather than being dropped, so nothing protects
you from the double spend.

Pick one:

- **Option A (recommended).** Delete the two `schedule:` lines from
  `generate.yml` and create the cron-job.org generate job below. cron-job.org
  becomes the single trigger, it fires on time, and it tells you when it fails.
- **Option B.** Keep the workflow's own schedule and **do not** create the
  generate cron job. You then only need three cron jobs. The trade is that
  GitHub's scheduler runs on a best-effort queue and can be delayed by 5–30
  minutes under load, and it gives you no failure notification.

Either is fine. What is not fine is doing both.

### A GitHub token that can start workflows

GitHub → **Settings** → **Developer settings** → **Personal access tokens** →
**Fine-grained tokens** → **Generate new token**.

| Field | Value |
| --- | --- |
| Token name | `headlinne-cron` |
| Expiration | 1 year (set a calendar reminder — an expired token fails **silently** from GitHub's side) |
| Repository access | Only select repositories → `architrobotics/headlinne-socials` |
| Permissions → **Actions** | **Read and write** |

Actions write is the only permission the dispatch needs. The workflows commit
their own output using the built-in `GITHUB_TOKEN`, not this one, so you do not
need to grant Contents.

Copy the token now. GitHub shows it once.

### A cron-job.org account

Free, at https://console.cron-job.org. The free plan covers this comfortably.

---

## The request every job sends

All jobs call the GitHub workflow-dispatch API. Same method, same headers, only
the URL and body differ.

**Method:** `POST`

**Headers** (all four):

```
Authorization: Bearer ghp_YOUR_TOKEN_HERE
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

**Generate — URL:**

```
https://api.github.com/repos/architrobotics/headlinne-socials/actions/workflows/generate.yml/dispatches
```

**Generate — body:**

```json
{"ref": "main"}
```

**Publish — URL:**

```
https://api.github.com/repos/architrobotics/headlinne-socials/actions/workflows/publish.yml/dispatches
```

**Publish — body** (change `target` per job):

```json
{"ref": "main", "inputs": {"target": "reel-1"}}
```

Valid targets, exactly as spelled: `reel-1`, `x-1`, `instagram-1`, `x-2`,
`linkedin`, `instagram-2`, `reel-2`, `story-card`. Note the **hyphens** — the CLI
uses underscores internally but the workflow input takes hyphens.

A successful dispatch returns **HTTP 204 No Content** with an empty body. That is
success, not a failure. cron-job.org treats any 2xx as success by default.

---

## The four jobs

Times are IST (the schedule this product is built around) and UTC. In
cron-job.org you set a time zone per job — pick **Asia/Kolkata** and use the IST
column, or leave it on UTC and use the UTC column. Do not mix.

This assumes `BUFFER_SCHEDULING_MODE` is `scheduled`, which is the default. In
that mode the morning generate run schedules your X and LinkedIn posts straight
into Buffer with their exact slot times, so those need no cron job at all.

| # | Job title | Workflow | `target` | IST | UTC | Cron (UTC) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Headlinne — generate | `generate.yml` | — | 06:00 | 00:30 | `30 0 * * *` |
| 2 | Headlinne — reel | `publish.yml` | `reel-1` | 09:30 | 04:00 | `0 4 * * *` |
| 3 | Headlinne — carousel | `publish.yml` | `instagram-1` | 16:00 | 10:30 | `30 10 * * *` |
| 4 | Headlinne — story card | `publish.yml` | `story-card` | 21:30 | 16:00 | `0 16 * * *` |

Buffer then publishes on its own, with no trigger from you:

- X post 1 at **13:00 IST**
- X post 2 at **17:00 IST** (non-promo days only)
- LinkedIn at **18:00 IST**

### Why the gaps are what they are

The generate run at 06:00 IST does everything for the day: fetches 32 feeds,
ranks, corroborates, writes the copy, renders the carousel and the story card,
encodes the reel, runs the visual gate and commits. Expect **8–20 minutes**,
most of it video encoding. The first publish slot is 3.5 hours later, so there is
a very large margin. Do not move reel-1 earlier than about 07:00 IST.

---

## Setting one up, click by click

1. Log in at https://console.cron-job.org and press **CREATE CRONJOB**.
2. **Title** — `Headlinne — reel` (or whichever job).
3. **URL** — paste the publish URL above.
4. **Execution schedule** — choose **Every day**, then set the time. Set the
   **time zone** selector to `Asia/Kolkata` if you are using IST times.
5. Expand **ADVANCED**.
6. **Request method** — change from `GET` to **`POST`**.
7. **Headers** — add all four rows from above. The Authorization value is the
   word `Bearer`, one space, then your token.
8. **Request body** — paste the JSON. Make sure the body field is enabled.
9. **Save**.

Repeat for each job. The only things that change between jobs are the title, the
schedule, and the `target` in the body (and the URL for the generate job).

### Two settings worth turning on

- **Notify on failure.** In the job's settings, enable email notification when
  execution fails. This is what tells you an expired PAT has silently broken the
  whole schedule — the most common way this system dies quietly.
- **Treat redirects as success: off**, and leave the expected status at any 2xx.
  GitHub returns 204.

---

## Optional extra slots

Both are **off by default** in `config.py`. The slots exist and will publish if
something is written into them, so turning one on is a repository variable plus a
cron job — no code change.

| Job | Workflow | `target` | IST | UTC | Cron (UTC) | Enable with |
| --- | --- | --- | --- | --- | --- | --- |
| Second carousel | `publish.yml` | `instagram-2` | 18:00 | 12:30 | `30 12 * * *` | `IG_SECOND_CAROUSEL=true` |
| Evening reel | `publish.yml` | `reel-2` | 20:00 | 14:30 | `30 14 * * *` | `SECOND_REEL=true` |

Before you add either, read "Why the format mix looks like this" in the README.
Three Instagram posts a day is what a small account can carry: each post competes
with the others for the same initial test audience, so a fourth tends to divide
the reach rather than add to it.

---

## Alternative: Buffer in "trigger" mode

Set the repository variable `BUFFER_SCHEDULING_MODE` to `trigger` if you would
rather fire every slot yourself and keep Buffer's queue empty between runs. Then
add these three as well:

| Job | Workflow | `target` | IST | UTC | Cron (UTC) |
| --- | --- | --- | --- | --- | --- |
| X post 1 | `publish.yml` | `x-1` | 13:00 | 07:30 | `30 7 * * *` |
| X post 2 | `publish.yml` | `x-2` | 17:00 | 11:30 | `30 11 * * *` |
| LinkedIn | `publish.yml` | `linkedin` | 18:00 | 12:30 | `30 12 * * *` |

Instagram is always published at trigger time in both modes, because the Meta
Graph API has no native scheduling.

---

## Checking it works

**Before wiring anything up.** Go to the repo's **Actions** tab, pick a workflow,
and use **Run workflow**. That runs the exact same path a cron job triggers, and
it is the fastest way to confirm your secrets are right.

**After the first real day.** Three places tell you the truth:

1. **cron-job.org → the job → execution history.** Shows the HTTP status it got
   back. A 204 means GitHub accepted the dispatch. A 401 means the token is wrong
   or expired; a 404 usually means the token lacks Actions write, or the repo
   path or workflow filename is wrong.
2. **GitHub → Actions.** Shows whether the run itself succeeded.
3. **The repo itself.** `content/<today>/` holds the day's JSON and rendered
   media, and `content/<today>/published/<slot>.json` is written only after a
   slot actually goes out.

Publishing is idempotent: each slot writes a marker file, and re-triggering a
slot that already published logs "already published today, skipping" and does
nothing. Re-firing a job by hand is safe.

## When nothing posts

Check in this order, because the cheap causes are also the common ones:

1. **Is the machine running at all?** If the newest folder in `content/` is not
   today, this is a plumbing problem and no amount of content tuning will fix it.
2. **Expired GitHub PAT.** Fails silently from GitHub's side — cron-job.org's own
   execution history is the only place it shows. This is the single most common
   cause after a few months.
3. **Expired Meta token.** Long-lived tokens last about 60 days.
4. **A disconnected Buffer channel.**
5. **Missing or wrong `GEMINI_API_KEY`.** The generate run fails early and the
   day has nothing to publish.

A format that fails its quality gate is dropped and logged rather than published
broken, and the rest of the day still goes out. If one slot is missing but the
others posted, look for `dropping <format>` in that day's generate log.
