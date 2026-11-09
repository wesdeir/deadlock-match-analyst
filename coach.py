"""Plain-text (Markdown) briefs meant to be pasted to Claude - or read by Claude straight from this repo - so it can
act as a coach: teaching points, what to practise next, and what to measure.

The pages embed the same text behind their "Copy for Claude" button, and `python analyze.py coach` writes it to
docs/coach/season.md and docs/coach/match_<id>.md.
"""
from analyst import mmss
import insights

ASK_SEASON = """You are my Deadlock coach. Use ONLY the data below (be honest about small sample sizes).
1. Pick the 2-3 most valuable things for me to practise, ordered by impact.
2. For each, give one concrete in-game adjustment I can apply next game, and how I'll measure it from this data.
3. Point out any pattern across games that the tool did not flag.
4. Tell me what to ignore for now. Keep it short and practical."""

ASK_MATCH = """You are my Deadlock coach. Use ONLY the data below.
1. Tell me what actually decided this game, in order of importance.
2. Give me 2-3 specific teaching points (what to do differently, in which situation), tied to moments in the data.
3. Say which of my recurring focus areas showed up, and what to try next game.
Skip tiny mistakes. Be concrete, not generic."""


def _f(v, d=1):
    return "n/a" if v is None else f"{v:.{d}f}"


def season_brief(records, ov):
    n = len(records)
    wins = sum(1 for m in records if m["win"])
    L = [f"# Deadlock coaching request: season overview", "", ASK_SEASON, "",
         f"## Me", f"Ranked season so far: {n} games, {wins} win(s), {n - wins} loss(es). Heroes: "
         + ", ".join(f"{h} x{sum(1 for m in records if m['hero'] == h)}" for h in sorted({m['hero'] for m in records})) + ". Low rank; main is Celeste.", ""]
    L.append("## Focus areas (flagged most often in recent games)")
    for f in ov["focus"][:3]:
        L.append(f"- **{f['title']}**: flagged in {f['flagged']} of the last {f['of']} games. Measure: {f['unit']} (target {f['target']}).")
        for e in f["examples"]:
            L.append(f"  - game {e['id']}: {e['evidence']}")
    L += ["", "## Are the habits improving? (baseline = first games, recent = latest games)",
          "| habit | baseline | recent | verdict |", "|---|---|---|---|"]
    for t in ov["trends"]:
        L.append(f"| {t['title']} ({t['unit']}) | {_f(t['baseline'])} | {_f(t['recent'])} | {t['verdict']}{' (tentative)' if t.get('tentative') else ''} |")
    L += ["", "## Game by game",
          "| game | hero | result | KDA | deaths vs teammate avg | souls/min | mid boss | flagged habits |", "|---|---|---|---|---|---|---|---|"]
    for m in records:
        flags = [r["title"] for r in insights.evaluate(m) if r["flag"]]
        k = m["kpi"]
        L.append(f"| {m['id']} | {m['hero']} | {'W' if m['win'] else 'L'} {mmss(m['dur'])} | {'/'.join(map(str, m['kda']))} | {k['deaths']} vs {k['mate_deaths']:.1f} | {k['spm']:,.0f} | "
                 f"{k['midboss_mine']}/{k['midboss_total']} | {'; '.join(flags) or '-'} |")
    mb = [m for m in records if m["kpi"]["midboss_total"]]
    L += ["", "## Team-level",
          f"- My team claimed every mid boss in {sum(1 for m in mb if m['kpi']['midboss_mine'] == m['kpi']['midboss_total'])} of {len(mb)} games; the enemy claimed every one in {sum(1 for m in mb if m['kpi']['midboss_mine'] == 0)}.",
          f"- Deaths in enemy territory: {sum(1 for m in records for d in m['deaths'] if d['side'] == 'enemy')} of {sum(len(m['deaths']) for m in records)}.", ""]
    return "\n".join(L)


def match_brief(m, points, focus):
    k = m["kpi"]
    L = [f"# Deadlock coaching request: match {m['id']}", "", ASK_MATCH, "",
         f"## Result", f"{m['hero']} - {'WIN' if m['win'] else 'LOSS'} - {mmss(m['dur'])} - {m['lane']} lane with {', '.join(m['lane_mate']) or 'nobody'} vs {' + '.join(m['lane_opp'])}. "
         f"KDA {'/'.join(map(str, m['kda']))}, net worth {m['nw']:,}, {k['spm']:,.0f} souls/min.", "",
         "My current recurring focus areas: " + (", ".join(f["title"] for f in focus) or "none yet"), "",
         "## Key points the tool found"]
    for p in points["problems"]:
        L.append(f"- PROBLEM{' (recurring)' if p['recurring'] else ''}: {p['title']} - {p['evidence']}")
    for p in points["positives"]:
        L.append(f"- GOOD: {p['title']} - {p['evidence']}")
    L += ["", "## Deaths", "| time | killed by | allies/enemies near | HP% 20/10/5/2s before | map half | respawn |", "|---|---|---|---|---|---|"]
    for d in m["deaths"]:
        L.append(f"| {mmss(d['t'])} | {d['killer']}{' (lane opp)' if d['killer_lane'] else ''} | {d['allies']}/{d['enemies']} | {'/'.join(map(str, d['hp']))} | {d['side']} | {d['respawn']}s |")
    L += ["", f"## Fights ({len(m['fights'])}; deaths cluster within 20s)"]
    for f in m["fights"]:
        L.append(f"- {mmss(f['t0'])}: {f['res'].upper()} ({f['theirs']} enemy/{f['ours']} ally deaths), first death {f['first']} ({'ally' if f['first_us'] else 'enemy'}), me: {f['pres']}{' + kill' if f['kill'] else ''}")
    L += ["", "## Lane vs a typical duo (all ranks)"]
    for c in m["lane_curve"]:
        L.append(f"- {mmss(c['t'])}: {c['mine'] - c['mean']:+,.0f} souls vs typical ({c['z']:+.1f} sd)")
    L += ["", "## Damage I took",
          f"{k['bullet_share']:.0%} bullet, {k['ability_share']:.0%} ability/other. Top dealer {k['top_dealer']} ({k['top_dealer_bullet']:.0%} bullet). "
          f"Resist I owned at 20:00: {k['res_s_20']:g}% spirit, {k['res_b_20']:g}% bullet."]
    for d in m["dmg"][:4]:
        t = d["bullet"] + d["ability"] + d["melee"]
        L.append(f"- {d['hero']}: {t:,} ({d['bullet'] / max(1, t):.0%} bullet)")
    L += ["", "## Items (tier 3+ I kept, with resist items marked)"]
    L.append("- " + "; ".join(f"{mmss(i['t'])} {i['name']}{' [resist]' if any(t.startswith(('spirit_resist', 'bullet_resist')) for t in i['tags']) else ''}"
                              for i in m["items"] if i["tier"] >= 3 and i["slot"] != "ability" and not i["sold"]))
    L.append("- Enemy first tier-3 items: " + "; ".join(f"{h} {mmss(v[0]['t'])}" for h, v in m["enemy_t3"].items() if v))
    L += ["", "## Economy", "- Souls by source (me vs teammate avg): " + ", ".join(
        f"{s} {m['souls'].get(s, 0):,} vs {m['souls_team_avg'].get(s, 0):,.0f}" for s in ("Neutrals", "LaneCreeps", "Players", "Assists", "Bosses"))]
    mb = m["midboss"]
    L.append(f"- Mid boss: " + (", ".join(f"{mmss(b['t'])} claimed by {'my team' if b['mine'] else 'the enemy'}" for b in mb) or "none"))
    L.append("")
    return "\n".join(L)
