#!/usr/bin/env python3
"""
Poll the Twitch Helix API for live Fallout: New Vegas streams.

Writes two files per month:

  data/YYYY-MM.csv        one row per live stream per poll
  data/polls-YYYY-MM.csv  one row per poll, always written

The polls file matters: if the category is empty at 4am, the per-stream file
gets nothing, and without a poll record the analysis cannot tell "nobody was
streaming" apart from "we never looked". A zero-competition hour is exactly
the signal we are hunting, so it has to be recorded explicitly.

Every language is collected. Filtering happens at analysis time so one dataset
can answer more than one question.

Stdlib only - no pip install step, so the Action stays fast.
"""

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Tale of Two Wastelands streams tag under EITHER game depending on the
# streamer, so both are collected and the game is recorded per row. Filtering
# happens at analysis time - collecting one and wishing for the other later is
# not recoverable, collecting both costs one extra API call per poll.
GAME_NAMES = ["Fallout 3", "Fallout: New Vegas"]
API = "https://api.twitch.tv/helix"
TIMEOUT = 30


def _json(req):
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def token(client_id, client_secret):
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(
        "https://id.twitch.tv/oauth2/token", data=body, method="POST")
    return _json(req)["access_token"]


def api_get(path, tok, client_id):
    req = urllib.request.Request(API + path, headers={
        "Client-ID": client_id,
        "Authorization": "Bearer " + tok,
    })
    return _json(req)


def main():
    try:
        cid = os.environ["TWITCH_CLIENT_ID"]
        secret = os.environ["TWITCH_CLIENT_SECRET"]
    except KeyError as e:
        sys.exit("missing secret: %s" % e)

    tok = token(cid, secret)

    game_ids = {}
    for name in GAME_NAMES:
        g = api_get("/games?name=" + urllib.parse.quote(name), tok, cid)
        if not g.get("data"):
            sys.exit("game not found on Twitch: " + name)
        game_ids[name] = g["data"][0]["id"]

    # One timestamp for the whole poll so every row of a poll groups cleanly,
    # across both games.
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    rows = []
    for name, game_id in game_ids.items():
        cursor = None
        while True:
            path = "/streams?game_id=%s&first=100" % game_id
            if cursor:
                path += "&after=" + urllib.parse.quote(cursor)
            page = api_get(path, tok, cid)
            for s in page.get("data", []):
                rows.append({
                    "collected_at": stamp,
                    "game": name,
                    "user_login": s["user_login"],
                    "viewer_count": s["viewer_count"],
                    "language": s["language"],
                    "started_at": s["started_at"],
                    "title": (s.get("title") or "").replace("\n", " ")[:180],
                })
            cursor = (page.get("pagination") or {}).get("cursor")
            if not cursor or not page.get("data"):
                break

    month = stamp[:7]
    os.makedirs("data", exist_ok=True)

    if rows:
        append("data/%s.csv" % month,
               ["collected_at", "game", "user_login", "viewer_count",
                "language", "started_at", "title"],
               rows)

    en = [r for r in rows if r["language"] == "en"]
    append("data/polls-%s.csv" % month,
           ["collected_at", "streams", "streams_en", "viewers", "viewers_en"],
           [{
               "collected_at": stamp,
               "streams": len(rows),
               "streams_en": len(en),
               "viewers": sum(r["viewer_count"] for r in rows),
               "viewers_en": sum(r["viewer_count"] for r in en),
           }])

    print("%s  streams=%d (en %d)  viewers=%d (en %d)" % (
        stamp, len(rows), len(en),
        sum(r["viewer_count"] for r in rows),
        sum(r["viewer_count"] for r in en)))


def append(path, fields, rows):
    fresh = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        # csv writes \r\n by default (RFC 4180). .gitattributes normalises to
        # LF on commit, so leaving it would log a line-ending warning on every
        # one of the ~96 runs a day and drift the working copy from the commit.
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        if fresh:
            w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
