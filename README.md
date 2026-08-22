# StreamWatch

Polls the Twitch API every 15 minutes for live **Fallout: New Vegas** streams
and accumulates the results, so the best time to go live can be measured rather
than guessed.

## The question this answers

Not "when are the most viewers watching" — that slot is also the most crowded.
The useful question is **when is demand highest relative to the streams already
above me in the directory**, because Twitch orders the category by viewer count
and everything below you is not competition.

So a *competitor* is a stream in your language with at least N viewers, where N
is the concurrent count you realistically expect. Change `THRESHOLD` as you grow.

## Repository visibility: public

Make it **public** when you create it on GitHub.

Actions minutes are unlimited on public repositories and capped at 2,000/month
on private ones. At 15-minute polling this job burns roughly 1,440 of those —
72% of the cap, with no headroom for a re-run or a backfill. Public removes the
constraint entirely.

Nothing here is sensitive. The credentials live in GitHub's secret store, never
in the code, and the collected data is public Twitch information: channel names
and viewer counts that anyone can read off the directory.

## Setup

**1. Create a Twitch application** at <https://dev.twitch.tv/console/apps>

- Name: anything
- OAuth Redirect URL: `http://localhost`
- Category: Application Integration

Copy the **Client ID**, then **New Secret** and copy that too.

**2. Add them as repository secrets** — Settings → Secrets and variables →
Actions → New repository secret:

| Name | Value |
|---|---|
| `TWITCH_CLIENT_ID` | your client ID |
| `TWITCH_CLIENT_SECRET` | your client secret |

**3. Enable Actions** if prompted, then run **collect** once manually from the
Actions tab to confirm it works before leaving it to the schedule.

## Reading the data

Run the **report** workflow from the Actions tab. Output appears in the run
summary — a 7×24 grid of median competitors and median viewers, plus a ranked
list of the best slots.

Inputs let you re-run against a different threshold, language, or timezone
without recollecting anything.

## What gets stored

    data/YYYY-MM.csv        one row per live stream per poll
    data/polls-YYYY-MM.csv  one row per poll, written even when nobody is live

The polls file is the important one. If the category is empty at 4am the
per-stream file gets nothing, and without a poll record the analysis cannot
distinguish "nobody was streaming" from "we never looked" — and an empty
category is precisely the signal being hunted.

## Things that will bite you

**Three weeks minimum before the numbers mean anything.** There are 168 hourly
buckets and the variance is severe — one large channel dipping into the category
distorts a bucket badly. The report prints a warning until coverage is adequate.

**Medians, not means.** Already handled in `analyze.py`, but worth knowing why:
the category's watch time is dominated by a handful of very large channels, so
averages describe an experience nobody actually has.

**GitHub disables scheduled workflows after 60 days of repository inactivity.**
Commits made by Actions do not always reset that timer. You will get an email;
re-enable from the Actions tab.

**Fifteen minutes is deliberate, not a budget limit.** Going faster buys very
little: the thing being measured is how many streams are live, and streams last
hours, so four samples an hour already oversamples the signal. The variance that
actually hurts is between weeks, not within an hour, and no amount of extra
polling touches that.

**Cron drift is normal.** GitHub's scheduler is best-effort and `*/15` often runs
further apart under load. Rows are stamped at collection time, so this shows up
as uneven sampling rather than incorrect data.
