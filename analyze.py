#!/usr/bin/env python3
"""
Turn collected polls into a read on when to stream.

Two passes, because they answer at different speeds.

RAW GRID     median competitors and viewers for each of the 168 day x hour
             cells. Truthful, but each cell only refills once a week, so it
             needs a month before it says anything.

ADDITIVE     hour-of-day and day-of-week effects are largely separable: Sunday
MODEL        is quieter than Tuesday at more or less any hour, 4am is dead on
             more or less any day. Modelling it that way estimates 24 + 7 = 31
             parameters instead of 168, which is answerable in days rather
             than weeks. Fitted by Tukey's median polish, so one large channel
             dipping into the category cannot drag an effect the way it would
             drag a mean.

The metric that matters is not how many streams exist - it is how many sit
ABOVE you in the directory, since Twitch orders by viewer count and everything
below you is not competition. So a "competitor" is a stream in your language
with at least THRESHOLD viewers: the concurrent count you realistically expect.

  TZ_NAME      timezone for the grid    (default America/New_York)
  LANG_FILTER  language to count        (default en)  -- not LANG, which the
                                        runner already uses for its locale
  THRESHOLD    viewers a stream needs to count as competition (default 3)
"""

import csv
import glob
import os
import statistics
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("TZ_NAME", "America/New_York"))
LANG = os.environ.get("LANG_FILTER", "en")
THRESHOLD = int(os.environ.get("THRESHOLD", "3"))
# Empty means both games pooled - the right default while the run spans TTW.
GAME = os.environ.get("GAME_FILTER", "")

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
POLLS_PER_HOUR = 4.0


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load():
    """Poll timestamps come from the polls file, which is written even when the
    category is empty. Stream rows are joined onto them; a missing join means
    genuinely zero live streams, not a gap in collection."""
    stamps = set()
    for path in sorted(glob.glob("data/polls-*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stamps.add(r["collected_at"])

    by_stamp = defaultdict(list)
    for path in sorted(glob.glob("data/2*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                by_stamp[r["collected_at"]].append(r)

    buckets = defaultdict(list)
    for stamp in stamps:
        local = datetime.fromisoformat(stamp).astimezone(TZ)
        # Rows collected before the game column existed were New Vegas only,
        # so that is the fallback rather than dropping them.
        rows = [r for r in by_stamp.get(stamp, [])
                if r["language"] == LANG
                and (not GAME or r.get("game", "Fallout: New Vegas") == GAME)]
        competitors = sum(1 for r in rows if int(r["viewer_count"]) >= THRESHOLD)
        viewers = sum(int(r["viewer_count"]) for r in rows)
        buckets[(local.weekday(), local.hour)].append((competitors, viewers))

    return stamps, buckets


# ---------------------------------------------------------------------------
# median polish
# ---------------------------------------------------------------------------

def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def median_polish(grid, rounds=10):
    """Decompose grid[7][24] (None allowed) into overall + day + hour + residual."""
    res = [[grid[d][h] for h in range(24)] for d in range(7)]
    day = [0.0] * 7
    hour = [0.0] * 24
    overall = 0.0

    for _ in range(rounds):
        moved = 0.0

        for d in range(7):
            m = med(res[d])
            if m:
                day[d] += m
                moved += abs(m)
                for h in range(24):
                    if res[d][h] is not None:
                        res[d][h] -= m
        m = med(day)
        if m:
            overall += m
            day = [v - m for v in day]

        for h in range(24):
            m = med([res[d][h] for d in range(7)])
            if m:
                hour[h] += m
                moved += abs(m)
                for d in range(7):
                    if res[d][h] is not None:
                        res[d][h] -= m
        m = med(hour)
        if m:
            overall += m
            hour = [v - m for v in hour]

        if moved < 1e-6:
            break

    return overall, day, hour, res


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def cell_grid(buckets, idx):
    grid = [[None] * 24 for _ in range(7)]
    for d in range(7):
        for h in range(24):
            vals = [v[idx] for v in buckets.get((d, h), [])]
            if vals:
                grid[d][h] = float(statistics.median(vals))
    return grid


def report_raw(buckets):
    for label, idx in (("COMPETING STREAMS (median)", 0),
                       ("CATEGORY VIEWERS (median)", 1)):
        grid = cell_grid(buckets, idx)
        print(label)
        print("      " + "".join("%5d" % h for h in range(24)))
        for d in range(7):
            cells = "".join(
                "%5s" % ("-" if grid[d][h] is None else int(grid[d][h]))
                for h in range(24))
            print("  %-4s%s" % (DAYS[d], cells))
        print()


def report_model(buckets, idx, label):
    grid = cell_grid(buckets, idx)
    filled = sum(1 for d in range(7) for h in range(24) if grid[d][h] is not None)
    if filled < 24:
        print("%s: only %d/168 cells observed - too early to model\n"
              % (label, filled))
        return

    overall, day, hour, res = median_polish(grid)

    print("%s  (%d/168 cells observed)" % (label, filled))
    print("  typical level  %.1f" % overall)
    print("  by day   " + "  ".join("%s %+.1f" % (DAYS[d], day[d]) for d in range(7)))
    print("  by hour")
    for block in range(0, 24, 8):
        print("    " + "  ".join("%02d %+5.1f" % (h, hour[h])
                                 for h in range(block, block + 8)))

    worst = sorted(
        ((abs(res[d][h]), d, h, res[d][h])
         for d in range(7) for h in range(24) if res[d][h] is not None),
        reverse=True)[:5]
    print("  where the additive story breaks down")
    for _, d, h, r in worst:
        print("    %-4s %02d:00  %+.1f" % (DAYS[d], h, r))
    print()


def report_slots(buckets):
    scored = []
    for (d, h), vals in buckets.items():
        if len(vals) < 2:
            continue
        comp = statistics.median(v[0] for v in vals)
        view = statistics.median(v[1] for v in vals)
        scored.append((view / (1.0 + comp), d, h, comp, view, len(vals)))

    if not scored:
        return
    print("BEST SLOTS OBSERVED  (viewers per competitor, >=2 samples)")
    for score, d, h, comp, view, n in sorted(scored, reverse=True)[:12]:
        print("  %-4s %02d:00   score %6.1f   competitors %3d   viewers %5d   n=%d"
              % (DAYS[d], h, score, comp, view, n))
    print()


# ---------------------------------------------------------------------------

def main():
    stamps, buckets = load()
    if not stamps:
        print("no polls collected yet")
        return

    weeks = len(stamps) / (7 * 24 * POLLS_PER_HOUR)
    print("polls %d   approx weeks of coverage %.1f" % (len(stamps), weeks))
    print("language=%s   competitor threshold >=%d viewers   tz=%s"
          % (LANG, THRESHOLD, TZ))
    print()

    print("=" * 66)
    print("ADDITIVE MODEL - fewer parameters, stabilises in days")
    print("=" * 66)
    print()
    report_model(buckets, 0, "COMPETING STREAMS")
    report_model(buckets, 1, "CATEGORY VIEWERS")

    print("=" * 66)
    print("RAW GRID - truthful but needs a month to settle")
    if weeks < 3:
        print("*** under three weeks of data: read the model above, not this ***")
    print("=" * 66)
    print()
    report_raw(buckets)
    report_slots(buckets)


if __name__ == "__main__":
    main()
