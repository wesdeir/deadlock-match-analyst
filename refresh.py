"""One command to bring everything up to date and rebuild the reports.

  python refresh.py             # history + any missing calibration metadata (stops politely if rate limited) + reports
  python refresh.py --gamedata  # also re-download the GameTracking text dumps (hash-verified) and rebuild gamedata.json

Rate limits: the per-match endpoint allows only a few requests per hour per IP, so this fetches at most
--max-fetch missing matches (default 2) per run and stops on the first 429. Re-run later for the rest.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import api
import analyst

HERE = Path(__file__).parent
REPO = "SteamTracking/GameTracking-Deadlock"
FILES = [
    "game/citadel/pak01_dir/scripts/heroes.vdata", "game/citadel/pak01_dir/scripts/abilities.vdata",
    "game/citadel/resource/localization/citadel_gc_hero_names/citadel_gc_hero_names_english.txt",
    "game/citadel/resource/localization/citadel_gc_mod_names/citadel_gc_mod_names_english.txt",
    "Protobufs/citadel_gcmessages_common.proto",
]


def refresh_gamedata():
    H = {"User-Agent": "deadlock-match-analyst/0.1 (personal; data files only)"}
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60).read()
    tree = json.loads(get(f"https://api.github.com/repos/{REPO}/git/trees/master?recursive=1"))["tree"]
    sha = {e["path"]: e["sha"] for e in tree if e["type"] == "blob"}
    out = HERE / "data" / "gametracking"
    out.mkdir(parents=True, exist_ok=True)
    for p in FILES:
        b = get(f"https://raw.githubusercontent.com/{REPO}/master/{p}")
        ok = hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest() == sha.get(p)
        b.decode("utf-8-sig")
        if not ok or b"\0" in b:
            print("SKIPPED (hash mismatch or binary):", p)
            continue
        (out / p.split("/")[-1]).write_bytes(b)
        print("ok", p.split("/")[-1])
    subprocess.run([sys.executable, str(HERE / "gamedata.py")], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gamedata", action="store_true")
    ap.add_argument("--max-fetch", type=int, default=2)
    ap.add_argument("--benchmarks", action="store_true", help="re-download the global benchmark tables")
    args = ap.parse_args()
    if args.gamedata:
        refresh_gamedata()
    try:
        hist = api.match_history(analyst.ACCOUNT_ID, refresh=True)
    except api.RateLimited as e:
        print("History rate limited:", e)
        hist = api.match_history(analyst.ACCOUNT_ID)
    if args.benchmarks:
        import benchmarks
        for hid in sorted({m["hero_id"] for m in analyst.calibration_matches(hist)}):
            benchmarks.hero_stats(hid, refresh=True)
            benchmarks.perf_curve(hid, refresh=True)
    cal = analyst.calibration_matches(hist)
    print("calibration counters:", sorted(m["ranked_calibration_match"] for m in cal))
    fetched = 0
    for m in cal:
        path = api._cache_path(f"{api.API}/v1/matches/{m['match_id']}/metadata")
        if path.exists() or fetched >= args.max_fetch:
            continue
        try:
            api.match_metadata(m["match_id"])
            fetched += 1
        except api.RateLimited as e:
            print("Stopping:", e)
            break
    for flags in ([], ["--brief"]):
        subprocess.run([sys.executable, str(HERE / "analyst.py"), "--calibration", *flags], check=False)


if __name__ == "__main__":
    main()
