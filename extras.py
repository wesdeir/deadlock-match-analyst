"""Extra report sections: economy, fights, enemy items, death HP, objectives, per-game scorecard.

Enum names come from the game's own protobuf definitions (data/gametracking/citadel_gcmessages_common.proto), so
objective ids, gold sources and damage-matrix stat types are authoritative, not guessed.
"""
import collections
import math
import re
from pathlib import Path

from analyst import dead_intervals, interp, mmss, nw_series, pos_at

PROTO = Path(__file__).parent / "data" / "gametracking" / "citadel_gcmessages_common.proto"


def proto_enum(enum_name, prefix):
    """{value: short_name} for an enum in the proto file ({} if the file is missing)."""
    if not PROTO.exists():
        return {}
    txt = PROTO.read_text(encoding="utf-8-sig")
    m = re.search(r"enum\s+" + re.escape(enum_name) + r"\s*\{(.*?)\}", txt, re.S)
    out = {}
    if m:
        for name, val in re.findall(r"(\w+)\s*=\s*(\d+)\s*;", m.group(1)):
            out[int(val)] = name.replace(prefix, "", 1)
    return out


OBJECTIVES = proto_enum("ECitadelTeamObjective", "k_eCitadelTeamObjective_")
GOLD_SOURCES = proto_enum("EGoldSource", "k_e")
STAT_TYPES = proto_enum("EStatType", "k_eType_")


def lane_name(names, lane_id):
    """Name of a lane id (York/Broadway/Greenwich), falling back to 'lane N'."""
    try:
        return names.lanes[lane_id]
    except (AttributeError, IndexError, KeyError):
        return f"lane {lane_id}"


def final_stat(p):
    """A player's last stats snapshot (end-of-game totals)."""
    return p["stats"][-1]


def custom_stat(mi, p, wanted_name, snap=None):
    """Value of a named custom user stat at a snapshot (default: last)."""
    ids = [c["id"] for c in mi.get("custom_user_stats", []) if c["name"] == wanted_name]
    if not ids:
        return None
    s = snap or p["stats"][-1]
    for c in s.get("custom_user_stats", []):
        if c["id"] == ids[0]:
            return c["value"]
    return None


# ---------------------------------------------------------------- economy
def section_economy(mi, me, names, lines):
    """Report section: souls by source versus teammates and lane opponents, plus a few custom stats."""
    team = [p for p in mi["players"] if p["team"] == me["team"]]
    opp = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]]
    lines.append("## 3b. Economy (souls by source, final snapshot)")
    lines.append("Source names are from the game's EGoldSource enum; values are each player's final-snapshot souls per source.")

    def src(p):
        return {g["source"]: g["gold"] for g in final_stat(p)["gold_sources"]}

    ms = src(me)
    tot = sum(ms.values()) or 1
    hdr = ["source", "me", "% of mine", "team avg", "lane opp avg"]
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|---|---|---|---|---|")
    for sid in sorted(ms, key=lambda s: -ms[s]):
        if not ms[sid] and not any(src(p).get(sid) for p in team):
            continue
        tavg = sum(src(p).get(sid, 0) for p in team) / len(team)
        oavg = (sum(src(p).get(sid, 0) for p in opp) / len(opp)) if opp else 0
        lines.append(f"| {GOLD_SOURCES.get(sid, sid)} | {ms[sid]:,} | {ms[sid] / tot:.0%} | {tavg:,.0f} | {oavg:,.0f} |")
    # custom stats worth showing
    rows = []
    for nm, label, fmt in (("Unspent Gold Minutes", "Unspent gold minutes (cumulative; higher = sat on souls longer)", "{:,}"),
                           ("Bullet Stats##HeroHitRate", "Hero hit rate % (final)", "{}"),
                           ("Bullet Stats##HeadshotRate", "Headshot rate % (final)", "{}"),
                           ("Bullet Stats - Incoming##HitRate", "Enemy hit rate on me % (final)", "{}"),
                           ("PowerUp Permanent", "Permanent power-up value gained", "{}")):
        mv = custom_stat(mi, me, nm)
        tv = [custom_stat(mi, p, nm) for p in team if p is not me]
        tv = [v for v in tv if v is not None]
        if mv is not None:
            rows.append(f"- {label}: me {fmt.format(mv)}; teammates avg {sum(tv) / len(tv):,.0f}" if tv else
                        f"- {label}: me {fmt.format(mv)}")
    lines.extend(rows)
    pu = me.get("power_up_buffs") or []
    if pu:
        lines.append("- Power-up pickups (me): " + ", ".join(
            f"{b['type']}@{','.join(mmss(t) for t in b.get('pickup_times_s', []))}" for b in pu if b.get("pickup_times_s")))
        tpu = sum(len(b.get('pickup_times_s', [])) for p in team if p is not me for b in (p.get("power_up_buffs") or [])) / max(1, len(team) - 1)
        mypu = sum(len(b.get('pickup_times_s', [])) for b in pu)
        lines.append(f"  ({mypu} pickups vs {tpu:.1f} avg per teammate)")
    lines.append("")


# ---------------------------------------------------------------- objectives
def objective_line(mi, me):
    """Two report lines: objectives my team destroyed and objectives we lost, with their names."""
    objs = sorted((o for o in mi["objectives"] if o["destroyed_time_s"]), key=lambda o: o["destroyed_time_s"])

    def nm(o):
        return OBJECTIVES.get(o["team_objective_id"], f"obj{o['team_objective_id']}")

    # 'team' on an objective is its owner: the loser's Core/Titan falls last (checked in verify below)
    mine = [o for o in objs if o["team"] != me["team"]]
    lost = [o for o in objs if o["team"] == me["team"]]
    return (f"- Objectives my team destroyed ({len(mine)}): " + ", ".join(f"{mmss(o['destroyed_time_s'])} {nm(o)}" for o in mine)
            + f"\n- Objectives we lost ({len(lost)}): " + ", ".join(f"{mmss(o['destroyed_time_s'])} {nm(o)}" for o in lost))


def check_objective_owner(mi):
    """Sanity check for the 'team = owner' assumption: the losing team's Core/Titan is destroyed, the winner's isn't."""
    loser = 1 - mi["winning_team"]
    ends = [o for o in mi["objectives"] if o["team_objective_id"] in (0, 9) and o["destroyed_time_s"]]
    return bool(ends) and all(o["team"] == loser for o in ends)


# ---------------------------------------------------------------- fights
def find_fights(mi, gap=20):
    """Group all deaths in the match into fights: a new fight starts when the gap between deaths exceeds `gap` seconds."""
    deaths = []
    players = {p["player_slot"]: p for p in mi["players"]}
    for p in mi["players"]:
        for dd in p["death_details"]:
            deaths.append((dd["game_time_s"], p["player_slot"], p["team"], dd["killer_player_slot"], dd["death_pos"]))
    deaths.sort()
    fights, cur = [], []
    for d in deaths:
        # A new fight starts when the gap since the previous death is longer than `gap` seconds.
        if cur and d[0] - cur[-1][0] > gap:
            fights.append(cur)
            cur = []
        cur.append(d)
    if cur:
        fights.append(cur)
    return fights, players


def section_fights(mi, me, names, lines, brief=False):
    """Report section: each fight (3+ deaths or involving me), who won it, who died first and where I was."""
    fights, players = find_fights(mi)
    paths = {p["player_slot"]: p for p in mi["match_paths"]["paths"]}
    dead = dead_intervals(mi)
    lines.append("## 3c. Fights (death clusters: deaths <=20s apart, 3+ deaths or any involving me)")
    lines.append("Presence = my distance (map units) to the cluster's first death at 10s before it; <=3000 counts as 'there'.")
    my_team = me["team"]
    rows, absent_loss, first_me = [], 0, 0
    for f in fights:
        mine_died = any(d[1] == me["player_slot"] for d in f)
        my_kill = any(d[3] == me["player_slot"] for d in f)
        if len(f) < 3 and not mine_died and not my_kill:
            continue
        t0 = f[0][0]
        ours = sum(1 for d in f if d[2] == my_team)
        theirs = len(f) - ours
        first = players[f[0][1]]
        fx, fy = f[0][4]["x"], f[0][4]["y"]
        mypath = paths.get(me["player_slot"])
        alive = not any(a <= t0 - 10 < b for a, b in dead[me["player_slot"]])
        if mine_died:
            pres = "DIED"
        elif not alive:
            pres = "dead (respawning)"
        elif mypath:
            x, y = pos_at(mypath, t0 - 10)
            dist = math.hypot(x - fx, y - fy)
            pres = f"there ({dist:,.0f})" if dist <= 3000 else f"away ({dist:,.0f})"
            if dist > 3000 and ours > theirs:
                absent_loss += 1
        else:
            pres = "?"
        outcome = "WON" if theirs > ours else ("LOST" if ours > theirs else "even")
        first_me += f[0][1] == me["player_slot"] and len(f) >= 2
        rows.append((t0, f"{mmss(t0)}-{mmss(f[-1][0])}", f"{theirs}-{ours} enemy-vs-us deaths", outcome,
                     f"first death: {names.hero(first['hero_id'])} ({'us' if first['team'] == my_team else 'them'})",
                     f"me: {pres}" + (", got a kill" if my_kill else "")))
    for r in rows:
        lines.append(f"- {r[1]}: {r[2]} -> **{r[3]}**; {r[4]}; {r[5]}")
    lost = [r for r in rows if r[3] == "LOST"]
    away_lost = [r for r in lost if "away" in r[5] or "dead" in r[5]]
    lines.append(f"- Summary: {sum(r[3] == 'WON' for r in rows)} fights won, {len(lost)} lost, "
                 f"{sum(r[3] == 'even' for r in rows)} even; lost fights where I was away/dead: {len(away_lost)}; "
                 f"multi-death fights where I was the FIRST to die: {first_me}")
    lines.append("")


# ---------------------------------------------------------------- enemy items
def section_enemy_items(mi, me, names, lines):
    """Report section: each enemy's tier-3+ item purchases with times."""
    enemies = [p for p in mi["players"] if p["team"] != me["team"]]
    lines.append("## 3d. Enemy tier-3+ item timeline (for judging when counters were needed)")
    meta = getattr(names, "item_meta", {})
    for e in sorted(enemies, key=lambda p: p["player_slot"]):
        its = []
        for i in sorted(e["items"], key=lambda i: i["game_time_s"]):
            tier, slot = meta.get(i["item_id"], (0, ""))
            if tier >= 3 and slot != "ability" and not i["sold_time_s"]:
                its.append(f"{mmss(i['game_time_s'])} {names.item(i['item_id']).split(' (')[0]}")
        lines.append(f"- {names.hero(e['hero_id'])}: " + ("; ".join(its) if its else "(no tier-3+ items identified)"))
    lines.append("")


# ---------------------------------------------------------------- death HP
def death_hp_line(mi, me, dd):
    """One report line: my HP% just before a death and how far the killer was."""
    paths = {p["player_slot"]: p for p in mi["match_paths"]["paths"]}
    pa = paths.get(me["player_slot"])
    if not pa or "health" not in pa:
        return None
    t = dd["game_time_s"]
    hp = pa["health"]
    pts = [(o, hp[max(0, min(len(hp) - 1, t - o))]) for o in (20, 10, 5, 2)]
    d = math.hypot(dd["death_pos"]["x"] - dd["killer_pos"]["x"], dd["death_pos"]["y"] - dd["killer_pos"]["y"])
    return (f"- HP% before death: " + ", ".join(f"t-{o}s {v}%" for o, v in pts)
            + f"; killer {d:,.0f} units away at the kill")


# ---------------------------------------------------------------- scorecard
def game_summary(mi, me, names, hist):
    """One row of per-game numbers (lane diffs, early deaths, souls/min...) for the calibration scorecard."""
    opp = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]]
    team = [p for p in mi["players"] if p["team"] == me["team"]]
    mys = nw_series(me)
    oppser = [nw_series(p) for p in opp]

    def lane_diff(t):
        if t > mi["duration_s"]:
            return None
        return interp(mys, t) - sum(interp(s, t) for s in oppser) / max(1, len(oppser))

    def team_diff(t):
        my = sum(interp(nw_series(p), t) for p in team)
        en = sum(interp(nw_series(p), t) for p in mi["players"] if p["team"] != me["team"])
        return my - en

    deaths = [d["game_time_s"] for d in me["death_details"]]
    fights, _ = find_fights(mi)
    first_die = sum(1 for f in fights if len(f) >= 2 and f[0][1] == me["player_slot"])
    from analyst import damage_profile
    prof = collections.Counter()
    for e in mi["players"]:
        if e["team"] != me["team"]:
            prof.update(damage_profile(mi, e["player_slot"], me["player_slot"]))
    tot = sum(prof.values()) or 1
    return {
        "n": hist.get("ranked_calibration_match"), "match": mi["match_id"], "hero": names.hero(me["hero_id"]),
        "win": me["team"] == mi["winning_team"], "dur": mi["duration_s"], "lane": lane_name(names, me["assigned_lane"]),
        "kda": f"{me['kills']}/{me['deaths']}/{me['assists']}",
        "ld6": lane_diff(360), "ld9": lane_diff(540), "ld15": lane_diff(900), "ldend": lane_diff(mi["duration_s"]),
        "td15": team_diff(900), "d_early": sum(1 for t in deaths if t < 600), "first_death": min(deaths) if deaths else None,
        "first_die": first_die, "deaths": me["deaths"], "team_deaths": sum(p["deaths"] for p in team) / len(team),
        "spm": me["net_worth"] / (mi["duration_s"] / 60), "bullet_pct": prof["Bullet"] / tot,
        "unspent": custom_stat(mi, me, "Unspent Gold Minutes"),
    }


def scorecard_lines(rows):
    """Markdown table of the per-game summaries."""
    f = lambda v: "-" if v is None else f"{v:+,.0f}"
    out = ["## Scorecard", "| game | match | hero | lane | result | KDA | lane diff @6/@9/@15/end | team diff @15 | deaths <10m | first death | first to die in fights | deaths (team avg) | souls/min | bullet % taken |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['n']} | {r['match']} | {r['hero']} | {r['lane']} | {'W' if r['win'] else 'L'} {mmss(r['dur'])} | {r['kda']} | "
                   f"{f(r['ld6'])}/{f(r['ld9'])}/{f(r['ld15'])}/{f(r['ldend'])} | {f(r['td15'])} | {r['d_early']} | "
                   f"{mmss(r['first_death']) if r['first_death'] is not None else '-'} | {r['first_die']} | {r['deaths']} ({r['team_deaths']:.1f}) | "
                   f"{r['spm']:,.0f} | {r['bullet_pct']:.0%} |")
    return out


def pattern_lines(rows):
    """Short wins-versus-losses comparison across the summarised games."""
    out = ["", "Patterns across these games:"]
    losses = [r for r in rows if not r["win"]]
    wins = [r for r in rows if r["win"]]

    def avg(rs, k):
        v = [r[k] for r in rs if r[k] is not None]
        return sum(v) / len(v) if v else None

    for k, label in (("ld9", "lane diff @9:00"), ("ld15", "lane diff @15:00"), ("d_early", "deaths before 10:00"),
                     ("deaths", "total deaths"), ("spm", "souls/min"), ("td15", "team NW diff @15:00")):
        a, b = avg(losses, k), avg(wins, k)
        out.append(f"- {label}: losses avg {a:+,.1f}" + (f", wins avg {b:+,.1f}" if b is not None else ", (no wins to compare)")
                   if a is not None else f"- {label}: n/a")
    lowdeath = [r for r in rows if r["deaths"] > r["team_deaths"]]
    out.append(f"- Games where I died more than my team's average: {len(lowdeath)}/{len(rows)}")
    out.append(f"- Games behind in lane at 9:00: {sum(1 for r in rows if r['ld9'] is not None and r['ld9'] < 0)}/{len(rows)}; "
               f"at 15:00: {sum(1 for r in rows if r['ld15'] is not None and r['ld15'] < 0)}/{len(rows)}")
    return out
