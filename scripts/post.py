#!/usr/bin/env python3
"""Post whatever is due right now from content/schedule.json.

GitHub Actions runs this every hour (8 AM to 9 PM IST). Each run:
  1. works out which posts are due (scheduled time <= now, not posted yet)
  2. posts the OLDEST due one (one per run keeps posts spaced out)
  3. records it in state.json so it never posts twice

If GitHub skips or delays a run, the next run catches up automatically.
Standard library only.

Secrets (env):  IG_USER_ID, IG_ACCESS_TOKEN
Optional env:   IG_API_HOST (default graph.instagram.com), IG_API_VERSION
Flags:          --dry-run   show what would post now
                --list      show the full timetable with dates
                --id ID     post one specific item immediately
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
SCHEDULE = json.loads((ROOT / "content" / "schedule.json").read_text())
CAPTIONS = json.loads((ROOT / "content" / "captions.json").read_text())
STATE_FILE = ROOT / "state.json"

sign = 1 if CFG["timezone_offset"][0] == "+" else -1
hh, mm = map(int, CFG["timezone_offset"][1:].split(":"))
TZ = dt.timezone(sign * dt.timedelta(hours=hh, minutes=mm))


def due_at(item):
    start = dt.date.fromisoformat(CFG["start_date"])
    h, m = map(int, item["time"].split(":"))
    day = start + dt.timedelta(days=item["day_offset"])
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def is_reel(pid):
    return pid.endswith("-reel")


def local_file(pid):
    return ROOT / ("reels" if is_reel(pid) else "posts") / f"{pid}.{'mp4' if is_reel(pid) else 'jpg'}"


def image_url(pid):
    folder, ext = ("reels", "mp4") if is_reel(pid) else ("posts", "jpg")
    return (f"https://raw.githubusercontent.com/{CFG['github_user']}/"
            f"{CFG['github_repo']}/{CFG['branch']}/{folder}/{pid}.{ext}")


def postable(it, now):
    """Reels are optional: only post them if the video exists and isn't >12h late."""
    if not is_reel(it["id"]):
        return True
    return local_file(it["id"]).exists() and now - due_at(it) < dt.timedelta(hours=12)


def api(method, path, params):
    host = os.environ.get("IG_API_HOST") or "graph.instagram.com"
    ver = (os.environ.get("IG_API_VERSION") or "").strip()
    url = f"https://{host}/{ver + '/' if ver else ''}{path}"
    data = urllib.parse.urlencode(params)
    req = (urllib.request.Request(f"{url}?{data}") if method == "GET" else
           urllib.request.Request(url, data=data.encode(), method="POST"))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Instagram API error {e.code} on {path}: "
                 f"{e.read().decode(errors='replace')}")


def check_image(url):
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            print(f"Image reachable ({r.status}): {url}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Image NOT reachable ({e.code}): {url}\n"
                 "Is the repo public, and are config.json github_user/repo right?")


def publish(pid):
    ig_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    url = image_url(pid)
    check_image(url)
    if is_reel(pid):
        params = {"media_type": "REELS", "video_url": url, "share_to_feed": "true",
                  "caption": CAPTIONS[pid], "access_token": token}
        tries, wait = 60, 10            # videos can take a few minutes to process
    else:
        params = {"image_url": url, "caption": CAPTIONS[pid], "access_token": token}
        tries, wait = 12, 5
    container = api("POST", f"{ig_id}/media", params)["id"]
    for _ in range(tries):
        st = api("GET", container, {"fields": "status_code",
                                    "access_token": token}).get("status_code")
        print("Container status:", st)
        if st == "FINISHED":
            break
        if st == "ERROR":
            sys.exit("Instagram could not process the media.")
        time.sleep(wait)
    else:
        sys.exit("Instagram took too long to process the media; will retry next run.")
    return api("POST", f"{ig_id}/media_publish", {
        "creation_id": container, "access_token": token})["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--id")
    a = ap.parse_args()

    state = json.loads(STATE_FILE.read_text())
    posted = {h["id"] for h in state["history"]}
    now = dt.datetime.now(TZ)

    if a.list:
        for it in SCHEDULE:
            mark = "✓" if it["id"] in posted else ("·" if postable(it, now) or due_at(it) > now else "x")
            if is_reel(it["id"]) and not local_file(it["id"]).exists():
                mark += " (no video yet)"
            print(f"{mark} {due_at(it):%a %d %b %H:%M}  {it['id']}")
        return

    if a.id:
        target = a.id
    else:
        due = [it for it in SCHEDULE
               if it["id"] not in posted and due_at(it) <= now and postable(it, now)]
        if not due:
            nxt = next((it for it in SCHEDULE if it["id"] not in posted
                    and (due_at(it) > now or postable(it, now))), None)
            print("Nothing due now." + (f" Next: {nxt['id']} at "
                  f"{due_at(nxt):%a %d %b %H:%M}" if nxt else " Series done!"))
            return
        target = due[0]["id"]
        if len(due) > 1:
            print(f"{len(due)} posts due; posting the oldest, rest catch up "
                  "on the next runs.")

    print(f"=== {target} ===\n{image_url(target)}\n\n{CAPTIONS[target]}\n")
    if a.dry_run:
        print("Dry run: nothing posted.")
        return
    media = publish(target)
    print(f"Published {target}: media id {media}")
    state["history"].append({"id": target, "media_id": media,
                             "posted_at": now.isoformat(timespec="seconds")})
    STATE_FILE.write_text(json.dumps(state, indent=1) + "\n")


if __name__ == "__main__":
    main()
