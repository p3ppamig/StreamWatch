#!/usr/bin/env python3
"""
Turn collected polls into a 7 x 24 grid of competition and demand.

The metric that matters is NOT how many streams exist - it is how many sit
ABOVE you in the directory, because Twitch orders by viewer count. So a
"competitor" is a stream in your language with at least THRESHOLD viewers,
where THRESHOLD is the concurrent count you realistically expect.

Reported as MEDIAN across weeks, never mean: a single large channel dipping
into the category for two hours would otherwise swamp a whole bucket.

  TZ_NAME    local timezone for the grid   (default America/New_York)
  LANG_FILTER  language to count           (default en)
  THRESHOLD  viewers a stream needs to count as competition (default 3)
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

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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

    return stamps, by_stamp


def main():
    stamps, by_stamp = load()
    if not stamps:
        print("no polls collected yet")
        return

    buckets = defaultdict(list)
    for stamp in stamps:
        local = datetime.fromisoformat(stamp).astimezone(TZ)
        rows = [r for r in by_stamp.get(stamp, []) if r["language"] == LANG]
        competitors = sum(1 for r in rows if int(r["viewer_count"]) >= THRESHOLD)
        viewers = sum(int(r["viewer_count"]) for r in rows)
        buckets[(local.weekday(), local.hour)].append((competitors, viewers))

    weeks = len(stamps) / (7 * 24 * 4.0)
    print("polls: %d   approx weeks of coverage: %.1f" % (len(stamps), weeks))
    print("language=%s  competitor threshold=>=%d viewers  tz=%s"
          % (LANG, THRESHOLD, TZ))
    if weeks < 3:
        print("\n*** UNDER THREE WEEKS OF DATA - THIS IS STILL NOISE ***")
    print()

    for label, idx in (("COMPETING STREAMS (median)", 0),
                       ("CATEGORY VIEWERS (median)", 1)):
        print(label)
        print("      " + "".join("%5d" % h for h in range(24)))
        for d in range(7):
            cells = []
            for h in range(24):
                vals = [v[idx] for v in buckets.get((d, h), [])]
                cells.append("%5s" % (int(statistics.median(vals)) if vals else "-"))
            print("  %-4s%s" % (DAYS[d], "".join(cells)))
        print()

    scored = []
    for (d, h), vals in buckets.items():
        if len(vals) < 2:
            continue
        comp = statistics.median(v[0] for v in vals)
        view = statistics.median(v[1] for v in vals)
        scored.append((view / (1.0 + comp), d, h, comp, view, len(vals)))

    print("BEST SLOTS  (viewers per competitor, needs >=2 samples)")
    for score, d, h, comp, view, n in sorted(scored, reverse=True)[:12]:
        print("  %-4s %02d:00   score %6.1f   competitors %3d   viewers %5d   n=%d"
              % (DAYS[d], h, score, comp, view, n))


if __name__ == "__main__":
    main()
