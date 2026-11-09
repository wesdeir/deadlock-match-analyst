"""Write the two dashboards: docs/index.html (season overview) and docs/matches/<id>.html (one page per match).
Pages are small: the chart code lives in docs/assets/lib.js; each page only embeds its own data."""
import datetime
import json
from pathlib import Path

import insights

DOCS = Path(__file__).parent / "docs"

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="{base}assets/lib.css"></head><body><main>"""
TAIL = """</main><script src="{base}assets/lib.js"></script><script>{script}</script></body></html>"""


def _dump(o):
    return json.dumps(o, separators=(",", ":"))


MATCH_BODY = """
<div id="head"></div>
<h2>Key points</h2><p class="sub">Only the biggest things: up to three to work on, what went well, and what to try next game. "Recurring" means it is also one of your current focus areas on the overview.</p>
<div id="points"></div>
<h2>What happened</h2><p class="sub">Team net-worth gap over time with the fights shaded (green = your team won it, red = lost), your deaths and kills, objectives, mid boss and resist-item purchases. Hover for details.</p>
<div class="card" id="c-timeline"></div>
<h2>Lane</h2><div class="cols"><div class="card" id="c-lane1"></div><div class="card" id="c-lane2"></div></div>
<h2>Deaths</h2><p class="sub">Red = you died alone or outnumbered by 2+ (your teammates die like this about as often, so it is context, not a verdict).</p>
<div class="cols"><div class="card" id="c-map"></div><div class="card"><div id="t-deaths"></div></div></div>
<h2>Fights</h2><p class="sub">Clusters of deaths within 20 seconds (3+ deaths or involving you).</p><div class="card" id="t-fights"></div>
<h2>Damage and defense</h2><p class="sub">What hurt you, and whether the resist items you owned matched it.</p>
<div class="cols"><div class="card" id="c-dmg1"></div><div class="card" id="c-dmg2"></div></div>
<h2>Items</h2><div class="card" id="c-items"></div>
<h2>Economy</h2><div class="cols"><div class="card" id="c-souls"></div><div class="card"><h3>Versus everyone (all-rank averages for your hero)</h3><div id="bench"></div></div></div>
<h2>All the data</h2>
<details><summary>Scoreboard (all 12 players)</summary><div class="card" id="t-board"></div></details>
<details><summary>Your item purchases</summary><div class="card" id="t-items"></div></details>
<details><summary>Objectives</summary><div class="card" id="t-obj"></div></details>
"""

OVERVIEW_BODY = """
<div id="head"></div>
<h2>Your focus right now</h2><p class="sub">The habits flagged most often in your recent games. Pick one or two to concentrate on; the rest can wait. Each shows how it moved game by game (dashed line = the flag threshold, red dots = flagged games).</p>
<div class="cols" id="focus"></div>
<h2>Are you improving?</h2><p class="sub" id="trend-note"></p><div class="card" id="trend"></div>
<h2>Habit pattern by game</h2><p class="sub">Red = flagged that game, green = fine. Click a game for its full breakdown.</p><div class="card" id="matrix"></div>
<h2>Team-level things you can influence</h2><div class="card" id="team"></div>
<h2>Games</h2><div class="card" id="games"></div>
<h2>By hero</h2><div class="card" id="heroes"></div>
"""


def match_page(rec, points, focus):
    script = f"const M={_dump(rec)},P={_dump(points)},F={_dump(focus)};renderMatch(M,P,F);"
    out = DOCS / "matches" / f"{rec['id']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD.format(title=f"Match {rec['id']} - {rec['hero']}", base="../") + MATCH_BODY + TAIL.format(base="../", script=script), encoding="utf-8")
    return out


def overview_page(records, ov):
    games = []
    for m in records:
        ev = {r["id"]: {"value": r["value"], "flag": r["flag"]} for r in insights.evaluate(m)}
        games.append({"id": m["id"], "calib": m["calib"], "win": m["win"], "hero": m["hero"], "lane": m["lane"], "dur": m["dur"], "kda": m["kda"],
                      "kpi": {k: m["kpi"][k] for k in ("deaths", "mate_deaths", "spm", "midboss_mine", "midboss_total")}, "habits": ev})
    data = {"games": games, "ov": ov, "rules": insights.rules(), "built": datetime.date.today().isoformat()}
    out = DOCS / "index.html"
    out.write_text(HEAD.format(title="Deadlock season overview", base="") + OVERVIEW_BODY + TAIL.format(base="", script=f"const O={_dump(data)};renderOverview(O);"), encoding="utf-8")
    return out
