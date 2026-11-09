"""Write the two dashboards: docs/index.html (season overview) and docs/matches/<id>.html (one page per match).
Pages are small: the chart code lives in docs/assets/lib.js; each page only embeds its own data."""
import datetime
import json
from pathlib import Path

import insights

DOCS = Path(__file__).parent / "docs"


def _asset_version():
    """Cache-busting token: the newest modification time of the shared css/js (browsers cache them for minutes)."""
    return int(max((DOCS / "assets" / f).stat().st_mtime for f in ("lib.css", "lib.js")))

# Shared page shell. {base} is the relative path back to docs/ ('' for index.html, '../' for match pages).
HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0d0d10">
<title>{title}</title><link rel="stylesheet" href="{base}assets/lib.css?v={v}"></head><body><a class="skip" href="#main">Skip to content</a><header id="nav"></header><main id="main">"""
TAIL = """</main><script src="{base}assets/heroes.js?v={v}"></script><script src="{base}assets/lib.js?v={v}"></script><script>window.ASSET_BASE="{base}";{script}</script></body></html>"""


def _dump(o):
    """JSON for embedding in an inline <script> ('</' is escaped so it can't close the tag)."""
    # '</' must not appear inside an inline <script>
    return json.dumps(o, separators=(",", ":")).replace("</", "<\\/")


MATCH_BODY = """
<div id="head"></div>
<div class="layout">
<aside class="coach" id="s-points"><h2>Key points</h2>
<p class="sub">The biggest things only: what to work on, what went well, what to try next game. "Recurring" = also one of your current focus areas on the overview.</p>
<div id="points"></div></aside>
<div class="stage">
<section id="s-board"><h2>The teams</h2><div class="teams" id="teams"></div></section>
<section id="s-timeline"><h2>What happened</h2><p class="sub">Team net-worth gap over time. Fights are shaded (green = your team won, red = lost); below: your deaths and kills, objectives, mid boss and resist-item buys. Hover for details.</p>
<div class="card" id="c-timeline"></div></section>
<section id="s-lane"><h2>Lane</h2><div class="cols"><div class="card" id="c-lane1"></div><div class="card" id="c-lane2"></div></div></section>
<section id="s-deaths"><h2>Deaths and fights</h2><p class="sub">Where you died, on the real map (white ring = alone or outnumbered by 2+; your teammates die like this about as often, so it is context, not a verdict), and the fights around them.</p>
<div class="deaths-grid"><div class="card"><div class="mapwrap" id="c-map"></div></div>
<div class="stack"><div class="card"><h3>Your deaths</h3><div id="t-deaths"></div></div>
<div class="card" id="s-fights"><h3>Fights (deaths within 20 seconds of each other; 3+ deaths or involving you)</h3><div id="t-fights"></div></div></div></div></section>
<section id="s-damage"><h2>Damage and defense</h2><p class="sub">What hurt you, and whether the resist items you owned matched it.</p>
<div class="cols"><div class="card" id="c-dmg1"></div><div class="card" id="c-dmg2"></div></div></section>
<section id="s-items"><h2>Items</h2><div class="card" id="c-items"></div></section>
<section id="s-economy"><h2>Economy</h2><div class="cols"><div class="card" id="c-souls"></div><div class="card"><h3>Versus everyone (all-rank averages for your hero)</h3><div id="bench"></div></div></div></section>
<section id="s-data"><h2>All the data</h2>
<details><summary>Your item purchases</summary><div class="card" id="t-items"></div></details>
<details><summary>Objectives</summary><div class="card" id="t-obj"></div></details></section>
</div></div>
"""
MATCH_CHIPS = [["s-points", "Key points"], ["s-board", "Teams"], ["s-timeline", "Timeline"], ["s-lane", "Lane"], ["s-deaths", "Deaths"], ["s-fights", "Fights"],
               ["s-damage", "Damage"], ["s-items", "Items"], ["s-economy", "Economy"], ["s-data", "All data"]]

OVERVIEW_BODY = """
<div id="head"></div>
<section id="s-focus"><h2>Your focus right now</h2><p class="sub">The habits flagged most often in your recent games. Pick one or two to concentrate on; the rest can wait. Dashed line = the flag threshold, red dots = flagged games.</p>
<div class="cols" id="focus"></div></section>
<div class="two">
<section id="s-improve"><h2>Are you improving?</h2><p class="sub" id="trend-note"></p><div class="card" id="trend"></div></section>
<section id="s-pattern"><h2>Habit pattern by game</h2><p class="sub">&#10005; red = flagged that game, &#10003; green = fine. Click a game for its full breakdown.</p><div class="card" id="matrix"></div>
<h2>Team-level things you can influence</h2><div class="card" id="team"></div></section>
</div>
<div class="two map-first">
<section id="s-map"><h2>Where you die</h2><p class="sub" id="seasonmap-note"></p><div class="card"><div class="mapwrap" id="c-seasonmap"></div></div></section>
<section id="s-community"><h2>Versus the community (Statlocker)</h2><div id="community"></div></section>
</div>
<div class="two">
<section id="s-games"><h2>Games</h2><div class="card" id="games"></div></section>
<section id="s-heroes"><h2>By hero</h2><div class="card" id="heroes"></div></section>
</div>
"""
OVERVIEW_CHIPS = [["s-focus", "Focus"], ["s-improve", "Improving?"], ["s-pattern", "Habit grid"], ["s-map", "Death map"], ["s-community", "Community"], ["s-games", "Games"], ["s-heroes", "Heroes"]]


def nav_games(records):
    """Short list of the season's games for the navigation bar and game picker."""
    out = []
    for m in records:
        label = f"#{m['calib']}" if m["calib"] else datetime.datetime.fromtimestamp(m["start"], datetime.timezone.utc).strftime("%m-%d")
        out.append({"id": m["id"], "label": label, "win": m["win"], "hero": m["hero"]})
    return out


def match_page(rec, points, focus, records, brief, sl=None):
    """Write docs/matches/<id>.html for one match."""
    rec = dict(rec, sl=sl)  # Statlocker numbers for this game (or None)
    script = (f"const M={_dump(rec)},P={_dump(points)},F={_dump(focus)};"
              f"renderNav({{page:'match',current:{rec['id']},games:{_dump(nav_games(records))},chips:{_dump(MATCH_CHIPS)},brief:{_dump(brief)}}});renderMatch(M,P,F);")
    out = DOCS / "matches" / f"{rec['id']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD.format(title=f"Match {rec['id']} - {rec['hero']}", base="../", v=_asset_version()) + MATCH_BODY + TAIL.format(base="../", script=script, v=_asset_version()), encoding="utf-8")
    return out


def overview_page(records, ov, brief, community=None, sl=None):
    """Write docs/index.html (season overview)."""
    sl = sl or {}
    games = []
    for m in records:
        ev = {r["id"]: {"value": r["value"], "flag": r["flag"]} for r in insights.evaluate(m)}
        games.append({"id": m["id"], "calib": m["calib"], "win": m["win"], "hero": m["hero"], "lane": m["lane"], "dur": m["dur"], "kda": m["kda"],
                      "kpi": {k: m["kpi"][k] for k in ("deaths", "mate_deaths", "spm", "midboss_mine", "midboss_total")}, "habits": ev,
                      "sl": sl.get(m["id"])})
    deaths = [{"x": d["x"], "y": d["y"], "t": d["t"], "side": d["side"], "killer": d["killer"], "game": m["id"]} for m in records for d in m["deaths"]]
    data = {"games": games, "ov": ov, "rules": insights.rules(), "built": datetime.date.today().isoformat(), "deaths": deaths, "community": community}
    script = (f"const O={_dump(data)};renderNav({{page:'overview',current:0,games:{_dump(nav_games(records))},chips:{_dump(OVERVIEW_CHIPS)},brief:{_dump(brief)}}});renderOverview(O);")
    out = DOCS / "index.html"
    out.write_text(HEAD.format(title="Deadlock season overview", base="", v=_asset_version()) + OVERVIEW_BODY + TAIL.format(base="", script=script, v=_asset_version()), encoding="utf-8")
    return out
