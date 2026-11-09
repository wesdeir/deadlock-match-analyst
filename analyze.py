"""Focus on one match at a time, and check progress now and then.

  python analyze.py match [ID]    # per-match page for ID (default: your latest ranked match this season)
  python analyze.py overview      # season overview: focus areas + are-you-improving tracker
  python analyze.py all           # rebuild every page (+ the coach briefs)
  python analyze.py coach [ID]    # only write the Markdown briefs to paste into Claude (docs/coach/)
  add --refresh to fetch new matches first (rate-limit safe: stops politely on a 429)

Output goes to docs/ (open docs/index.html). Pages are plain HTML and work offline.
"""
import argparse
import sys
from pathlib import Path

import api
import analyst
import coach
import insights
import kpis
import pages
import statlocker

DOCS = Path(__file__).parent / "docs"


def load_records(history, names, refresh=False, max_fetch=2):
    """Return per-match records for the season, optionally downloading missing matches first (newest first, rate-limit safe)."""
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
    """Parse the command, build records and insights, then write the requested pages and coach briefs."""
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["match", "overview", "all", "coach"])
    ap.add_argument("match_id", nargs="?", type=int)
    ap.add_argument("--refresh", action="store_true", help="refresh match history and download missing season matches first")
    args = ap.parse_args()
    history = api.match_history(analyst.ACCOUNT_ID, refresh=args.refresh)
    names = analyst.Names()
    records = load_records(history, names, args.refresh)
    if not records:
        sys.exit("No season matches with metadata yet.")
    api.ensure_map_image(DOCS / "assets" / "map.png")  # cosmetic; pages fall back to the remote image
    ov = insights.overview(records)
    # The top-3 focus habits get a 'recurring' tag on each match page.
    recurring = {f["id"] for f in ov["focus"][:3]}
    focus3 = [{"id": f["id"], "title": f["title"]} for f in ov["focus"][:3]]
    snap = statlocker.load()  # optional: community percentiles + per-game grade/MMR from Statlocker
    sl = statlocker.match_games(records, snap) if snap else {}
    community = statlocker.community(snap) if snap else None
    season_text = coach.season_brief(records, ov, community, sl)
    out = []
    if args.what in ("overview", "all", "coach"):
        if args.what != "coach":
            out.append(pages.overview_page(records, ov, season_text, community, sl))
        (DOCS / "coach").mkdir(parents=True, exist_ok=True)
        (DOCS / "coach" / "season.md").write_text(season_text, encoding="utf-8")
        out.append(DOCS / "coach" / "season.md")
    if args.what in ("match", "all", "coach"):
        if args.what == "all":
            targets = records
        else:
            targets = [r for r in records if r["id"] == args.match_id] if args.match_id else [records[-1]]
            if not targets:
                sys.exit(f"Match {args.match_id} is not a cached ranked match of this season.")
        for r in targets:
            pts = insights.match_points(r, recurring)
            text = coach.match_brief(r, pts, focus3, sl.get(r['id']))
            (DOCS / "coach").mkdir(parents=True, exist_ok=True)
            (DOCS / "coach" / f"match_{r['id']}.md").write_text(text, encoding="utf-8")
            if args.what != "coach":
                out.append(pages.match_page(r, pts, focus3, records, text, sl.get(r['id'])))
            out.append(DOCS / "coach" / f"match_{r['id']}.md")
    for o in out:
        print("wrote", o)


if __name__ == "__main__":
    main()
