"""Watch for a finished ranked match and rebuild the dashboards automatically.

  python watch.py            # poll every 7 minutes; when a new ranked match shows up, download it and rebuild everything
  python watch.py --open     # ...and open the new match page in your browser
  python watch.py --once     # check one time and exit (handy for a scheduled task)

How it works: the match appears in your API match history shortly after it ends. We poll the history endpoint (the API
allows 10 requests/hour if your account is friends with one of its bots, 100/s otherwise, so the default 7-minute interval
stays under both), then download that match's metadata (limit ~3/hour: we retry gently and respect the server's wait time)
and run `analyze.py all`. State is kept in data/watch_state.json. Stop with Ctrl+C.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import api
import analyst
import kpis

HERE = Path(__file__).parent
STATE = HERE / "data" / "watch_state.json"


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s), encoding="utf-8")


def fetch_metadata(match_id, tries=6, spacing_s=600):
    """Download a match's metadata, waiting politely if it isn't ready yet or we are rate limited. True on success."""
    for attempt in range(1, tries + 1):
        if api.cached_match_metadata(match_id):
            return True
        try:
            if api.match_metadata(match_id):
                return True
            log(f"match {match_id} not available yet (try {attempt}/{tries}); waiting {spacing_s // 60} min")
            wait = spacing_s
        except api.RateLimited as e:
            wait = min(3700, e.wait_s + 30)
            log(f"rate limited; waiting {wait / 60:.0f} min as the server asked")
        time.sleep(wait)
    return False


def rebuild(match_id, open_page):
    log("rebuilding dashboards...")
    subprocess.run([sys.executable, str(HERE / "analyze.py"), "all"], check=False)
    page = HERE / "docs" / "matches" / f"{match_id}.html"
    try:
        import winsound  # Windows only; a short beep so you notice without watching the window
        winsound.MessageBeep()
    except Exception:
        print("\a", end="")
    log(f"done: {page}")
    if open_page and page.exists():
        webbrowser.open(page.as_uri())


def check_once(args, state):
    hist = api.match_history(analyst.ACCOUNT_ID, refresh=True)
    season = kpis.season_matches(hist)
    if not season:
        log("no season matches found")
        return state
    newest = season[-1]["match_id"]
    seen = args.since or state.get("last_seen")
    if seen is None:  # first run: start from now, don't process old games
        state["last_seen"] = newest
        save_state(state)
        log(f"watching from match {newest} (your latest); play a game!")
        return state
    for m in season:
        if m["match_id"] <= seen:
            continue
        log(f"new ranked match {m['match_id']}")
        if fetch_metadata(m["match_id"]):
            rebuild(m["match_id"], args.open)
            state["last_seen"] = m["match_id"]
            save_state(state)
        else:
            log(f"could not download {m['match_id']} yet; will try again next check")
            break
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=7, help="minutes between checks (minimum 6)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--open", action="store_true", help="open the new match page in your browser")
    ap.add_argument("--since", type=int, help="treat matches newer than this id as new (for testing)")
    args = ap.parse_args()
    interval = max(6.0, args.interval) * 60
    state = load_state()
    log(f"watching account {analyst.ACCOUNT_ID} every {interval / 60:.0f} min (Ctrl+C to stop)")
    while True:
        try:
            state = check_once(args, state)
        except api.RateLimited as e:
            log(f"history rate limited: {e}")
        except Exception as e:  # keep watching through network blips
            log(f"check failed: {e}")
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
