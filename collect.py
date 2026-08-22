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

GAME_NAME = "Fallout: New Vegas"
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

    games = api_get("/games?name=" + urllib.parse.quote(GAME_NAME), tok, cid)
    if not games.get("data"):
        sys.exit("game not found on Twitch: " + GAME_NAME)
    game_id = games["data"][0]["id"]

    # One timestamp for the whole poll so every row of a poll groups cleanly.
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    rows = []
    cursor = None
    while True:
        path = "/streams?game_id=%s&first=100" % game_id
        if cursor:
            path += "&after=" + urllib.parse.quote(cursor)
        page = api_get(path, tok, cid)
        for s in page.get("data", []):
            rows.append({
                "collected_at": stamp,
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
               ["collected_at", "user_login", "viewer_count",
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
