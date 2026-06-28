# Scheduling with cron-job.org

cron-job.org triggers the GitHub Actions in this repo at the right times. Each job
just sends one HTTP request that starts a workflow and returns immediately, so it
always finishes well within cron-job.org's 30 second limit. The actual work runs
on GitHub's servers.

## What you need

1. A GitHub Personal Access Token (PAT) that can start workflows.
   - GitHub -> Settings -> Developer settings -> Personal access tokens.
   - A fine-grained token scoped to this repository with **Actions: Read and write**
     and **Contents: Read and write** is enough.
2. A free account at https://cron-job.org/en.

## The request each job sends

All jobs call the GitHub "workflow dispatch" API.

- Method: `POST`
- Headers:
  - `Authorization: Bearer YOUR_GITHUB_PAT`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Content-Type: application/json`

### Generate job (runs once in the morning)

- URL:
  `https://api.github.com/repos/OWNER/REPO/actions/workflows/generate.yml/dispatches`
- Body:
  ```json
  { "ref": "main" }
  ```

### Publish jobs (one per slot)

- URL:
  `https://api.github.com/repos/OWNER/REPO/actions/workflows/publish.yml/dispatches`
- Body (change the target for each job):
  ```json
  { "ref": "main", "inputs": { "target": "instagram-1" } }
  ```
  Valid targets: `x-1`, `x-2`, `linkedin`, `instagram-1`, `instagram-2`.

Replace `OWNER/REPO` with your repository, and `main` with your branch if different.

## The schedule

Times below are shown in IST and UTC. In cron-job.org you can set each job's
time zone. If you set it to **Asia/Kolkata**, just use the IST times. If you leave
it on UTC, use the UTC times.

### Default setup (recommended): Buffer in "scheduled" mode

In scheduled mode the generate run schedules your X and LinkedIn posts straight
into Buffer at their slot times, so you only need three cron jobs:

| Job             | Workflow      | Target        | IST    | UTC    |
| --------------- | ------------- | ------------- | ------ | ------ |
| Generate        | generate.yml  | (none)        | 06:00  | 00:30  |
| Instagram 1     | publish.yml   | instagram-1   | 16:00  | 10:30  |
| Instagram 2     | publish.yml   | instagram-2   | 18:00  | 12:30  |

Buffer then publishes:
- X post 1 at 13:00 IST, X post 2 at 17:00 IST
- LinkedIn at 18:00 IST

### Alternative: Buffer in "trigger" mode

Set the repository variable `BUFFER_SCHEDULING_MODE` to `trigger` if you would
rather fire every slot yourself. Then add these jobs as well:

| Job             | Workflow      | Target     | IST    | UTC    |
| --------------- | ------------- | ---------- | ------ | ------ |
| X post 1        | publish.yml   | x-1        | 13:00  | 07:30  |
| X post 2        | publish.yml   | x-2        | 17:00  | 11:30  |
| LinkedIn        | publish.yml   | linkedin   | 18:00  | 12:30  |

## Cron expressions (UTC)

If your cron-job.org jobs use UTC and you prefer cron syntax:

```
Generate      30 0 * * *
Instagram 1   30 10 * * *
Instagram 2   30 12 * * *
X post 1      30 7 * * *     (trigger mode only)
X post 2      30 11 * * *    (trigger mode only)
LinkedIn      30 12 * * *    (trigger mode only)
```

## Checking it works

After a job fires, open the repo's **Actions** tab on GitHub to watch the run.
You can also trigger any workflow manually from that tab using the "Run workflow"
button, which is the easiest way to test before wiring up cron-job.org.
