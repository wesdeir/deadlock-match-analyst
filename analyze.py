"""Focus on one match at a time, and check progress now and then.

  python analyze.py match [ID]    # per-match page for ID (default: your latest ranked match this season)
  python analyze.py overview      # season overview: focus areas + are-you-improving tracker
  python analyze.py all           # rebuild every page
  add --refresh to fetch new matches first (rate-limit safe: stops politely on a 429)

Output goes to docs/ (open docs/index.html). Pages are plain HTML and work offline.
"""
import argparse
import sys

import api
import analyst
import insights
import kpis
import pages


def load_records(history, names, refresh=False, max_fetch=2):
    season = kpis.season_matches(history)
    fetched = 0
    if refresh:
        for m in reversed(season):  # newest first
            if api.cached_match_metadata(m["match_id"]) is None and fetched < max_fetch:
                try:
                    api.match_metadata(m["match_id"])
                    fetched += 1
                except api.RateLimited as e:
                    print("Stopping fetch:", e)
                    break
    records = []
    for m in season:
        rec = kpis.build(m["match_id"], m, names)
        if rec:
            records.append(rec)
        else:
            print(f"(skipping {m['match_id']}: metadata not downloaded yet)")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["match", "overview", "all"])
    ap.add_argument("match_id", nargs="?", type=int)
    ap.add_argument("--refresh", action="store_true", help="refresh match history and download missing season matches first")
    args = ap.parse_args()
    history = api.match_history(analyst.ACCOUNT_ID, refresh=args.refresh)
    names = analyst.Names()
    records = load_records(history, names, args.refresh)
    if not records:
        sys.exit("No season matches with metadata yet.")
    ov = insights.overview(records)
    recurring = {f["id"] for f in ov["focus"][:3]}
    focus3 = [{"id": f["id"], "title": f["title"]} for f in ov["focus"][:3]]
    out = []
    if args.what in ("overview", "all"):
        out.append(pages.overview_page(records, ov))
    if args.what in ("match", "all"):
        if args.what == "all":
            targets = records
        else:
            targets = [r for r in records if r["id"] == args.match_id] if args.match_id else [records[-1]]
            if not targets:
                sys.exit(f"Match {args.match_id} is not a cached ranked match of this season.")
        for r in targets:
            out.append(pages.match_page(r, insights.match_points(r, recurring), focus3))
    for o in out:
        print("wrote", o)


if __name__ == "__main__":
    main()
