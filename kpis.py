"""Turn one match's raw metadata into a compact, JSON-friendly record: everything the per-match page shows plus a small set
of habit KPIs that are measured the same way in every game (so they can be tracked over time).

Saved to data/matches/<match_id>.json (committed; small), so the overview works without re-reading the big cache files.
"""
import collections
import json
import math
from pathlib import Path

import api
import analyst
import benchmarks
import extras

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "matches"
SCHEMA = 5  # bump when the record layout/KPI definitions change (forces a rebuild)

NEAR = 2500  # map units: "near" means within this distance
EARLY_S = 600  # lane-phase cutoff for "early deaths"


def _first_t3(p, meta):
    ts = [i["game_time_s"] for i in p["items"]
          if meta.get(i["item_id"], (0, ""))[0] >= 3 and meta.get(i["item_id"], (0, ""))[1] != "ability"]
    return min(ts) if ts else None


def _safe(fn, *a):
    try:
        return fn(*a)
    except (api.RateLimited, Exception):  # benchmarks are a bonus; never fail a match build because of them
        return None


def compute(match_id, hist_row, names, hero_cache=None):
    raw = api.cached_match_metadata(match_id) or api.match_metadata(match_id)
    mi = raw["match_info"]
    analyst.derive_hero_codes(mi, names)
    analyst.derive_item_classes(mi, names)
    me = next(p for p in mi["players"] if p["account_id"] == analyst.ACCOUNT_ID)
    meta = names.item_meta
    dur = mi["duration_s"]
    slot = me["player_slot"]
    players = {p["player_slot"]: p for p in mi["players"]}
    paths = {p["player_slot"]: p for p in mi["match_paths"]["paths"]}
    dead = analyst.dead_intervals(mi)
    mates = [p for p in mi["players"] if p["team"] == me["team"] and p is not me]
    team = mates + [me]
    foes = [p for p in mi["players"] if p["team"] != me["team"]]
    lane_opp = [p for p in foes if p["assigned_lane"] == me["assigned_lane"]]
    lane_mate = [p for p in mates if p["assigned_lane"] == me["assigned_lane"]]
    series = {p["player_slot"]: analyst.nw_series(p) for p in mi["players"]}
    win = me["team"] == mi["winning_team"]
    grid = list(range(0, dur, 60)) + [dur]

    def gap(t):
        return (sum(analyst.interp(series[p["player_slot"]], t) for p in team)
                - sum(analyst.interp(series[p["player_slot"]], t) for p in foes))

    # ---- scoreboard (all 12 players)
    board = []
    for p in sorted(mi["players"], key=lambda p: (p["team"] != me["team"], -p["net_worth"])):
        f = p["stats"][-1]
        board.append({"slot": p["player_slot"], "me": p is me, "ally": p["team"] == me["team"],
                      "hero": names.hero(p["hero_id"]), "lane": extras.lane_name(names, p["assigned_lane"]),
                      "k": p["kills"], "d": p["deaths"], "a": p["assists"], "nw": p["net_worth"], "lh": p["last_hits"],
                      "dmg": f["player_damage"], "taken": f["player_damage_taken"], "heal": f["player_healing"], "lvl": p["level"]})

    def near_counts(p, t):
        """(allies, enemies) of player p within NEAR map units at time t (alive players only)."""
        al = en = 0
        sl_ = p["player_slot"]
        if sl_ not in paths:
            return 0, 0
        mx, my = analyst.pos_at(paths[sl_], t)
        for sl, pp in paths.items():
            if sl == sl_ or sl not in players or any(a <= t < b for a, b in dead[sl]):
                continue
            x, y = analyst.pos_at(pp, t)
            if math.hypot(x - mx, y - my) <= NEAR:
                if players[sl]["team"] == p["team"]:
                    al += 1
                else:
                    en += 1
        return al, en

    # peers (the other 11 players) give a same-game baseline for "caught" deaths
    peer_caught = peer_deaths = 0
    mate_first_die = []
    for p in mi["players"]:
        if p is me:
            continue
        for dd in p["death_details"]:
            a_, e_ = near_counts(p, dd["game_time_s"] - 1)
            peer_deaths += 1
            peer_caught += (a_ == 0 or e_ >= a_ + 2)

    # ---- deaths with context
    deaths = []
    fights, _ = extras.find_fights(mi)
    fight_of = {}
    for fi, f in enumerate(fights):
        for d in f:
            fight_of[(d[1], d[0])] = fi
    for dd in me["death_details"]:
        t = dd["game_time_s"]
        k = players.get(dd["killer_player_slot"])
        al = en = 0
        if slot in paths:
            mx, my = analyst.pos_at(paths[slot], t - 1)
            for sl, pp in paths.items():
                if sl == slot or sl not in players or any(a <= t - 1 < b for a, b in dead[sl]):
                    continue
                x, y = analyst.pos_at(pp, t - 1)
                if math.hypot(x - mx, y - my) <= NEAR:
                    if players[sl]["team"] == me["team"]:
                        al += 1
                    else:
                        en += 1
        hp = paths[slot]["health"] if slot in paths else []
        deaths.append({
            "t": t, "respawn": dd.get("death_duration_s", 0), "ttk": round(dd["time_to_kill_s"], 1),
            "killer": names.hero(k["hero_id"]) if k else "creep/world", "killer_lane": bool(k and k in lane_opp),
            "nw_me": round(analyst.interp(series[slot], t)), "nw_killer": round(analyst.interp(series[k["player_slot"]], t)) if k else None,
            "allies": al, "enemies": en, "early": t < EARLY_S,
            "caught": al == 0 or en >= al + 2,  # alone, or outnumbered by 2+
            "hp": [hp[max(0, min(len(hp) - 1, t - o))] for o in (20, 10, 5, 2)] if hp else [],
            "x": round(dd["death_pos"]["x"]), "y": round(dd["death_pos"]["y"]),
            # which half of the map: team 0's base is at negative y, team 1's at positive y
            "side": "own" if (dd["death_pos"]["y"] < 0) == (me["team"] == 0) else "enemy",
        })

    # ---- fights
    frows = []
    for f in fights:
        died = any(d[1] == slot for d in f)
        kill = any(d[3] == slot for d in f)
        if len(f) < 3 and not died and not kill:
            continue
        ours = sum(1 for d in f if d[2] == me["team"])
        theirs = len(f) - ours
        t0 = f[0][0]
        if died:
            pres = "died"
        elif any(a <= t0 - 10 < b for a, b in dead[slot]):
            pres = "dead"
        else:
            x, y = analyst.pos_at(paths[slot], t0 - 10)
            pres = "there" if math.hypot(x - f[0][4]["x"], y - f[0][4]["y"]) <= 3000 else "away"
        frows.append({"t0": t0, "t1": f[-1][0], "res": "won" if theirs > ours else ("lost" if ours > theirs else "even"),
                      "theirs": theirs, "ours": ours, "pres": pres, "kill": kill,
                      "first": names.hero(players[f[0][1]]["hero_id"]), "first_me": f[0][1] == slot, "first_us": players[f[0][1]]["team"] == me["team"]})
    for p in mates:
        mate_first_die.append(sum(1 for f in fights if len(f) >= 2 and f[0][1] == p["player_slot"]))
    mate_kp = [(p["kills"] + p["assists"]) / max(1, sum(q["kills"] for q in team)) for p in mates]
    kills = sorted(dd["game_time_s"] for p in mi["players"] for dd in p["death_details"] if dd["killer_player_slot"] == slot)

    # ---- damage taken (by enemy, and over time with resist owned)
    dmg = []
    for e in foes:
        pr = analyst.damage_profile(mi, e["player_slot"], slot)
        dmg.append({"hero": names.hero(e["hero_id"]), "bullet": pr["Bullet"],
                    "ability": pr["Ability"] + pr["UnknownAbility"] + pr["Misc"], "melee": pr["Melee"]})
    dmg.sort(key=lambda d: -(d["bullet"] + d["ability"] + d["melee"]))
    tot_b = sum(d["bullet"] for d in dmg)
    tot_a = sum(d["ability"] for d in dmg)
    tot_m = sum(d["melee"] for d in dmg)
    tot = (tot_b + tot_a + tot_m) or 1
    per = collections.defaultdict(collections.Counter)
    ens = {e["player_slot"] for e in foes}
    ts = mi["damage_matrix"]["sample_time_s"]
    for d, t, st, name, a in analyst.matrix_cells(mi):
        if d in ens and t == slot and st == 0 and name in analyst.AGG:
            prev = 0
            for kx, v in enumerate(a):
                per[kx][name] += v - prev
                prev = v
    intervals = []
    for kx, t in enumerate(ts):
        c = per[kx]
        tt = sum(c.values())
        if tt:
            rb, rs = analyst.resist_owned(me, t, names)
            intervals.append({"t": t, "total": tt, "bullet": c["Bullet"], "other": tt - c["Bullet"], "res_b": rb, "res_s": rs})

    # ---- items
    def item_row(i):
        tier, sl = meta.get(i["item_id"], (0, ""))
        return {"t": i["game_time_s"], "name": names.item(i["item_id"]).split(" [")[0].split(" (")[0], "tier": tier, "slot": sl,
                "sold": i["sold_time_s"] or None, "tags": names.tags.get(i["item_id"], [])}

    my_items = [item_row(i) for i in sorted(me["items"], key=lambda i: i["game_time_s"])]
    enemy_t3 = {}
    for e in foes:
        enemy_t3[names.hero(e["hero_id"])] = [{"t": r["t"], "name": r["name"]} for r in
                                              (item_row(i) for i in sorted(e["items"], key=lambda i: i["game_time_s"]))
                                              if r["tier"] >= 3 and r["slot"] != "ability" and not r["sold"]]

    # ---- economy
    def src(p):
        return {extras.GOLD_SOURCES.get(g["source"], str(g["source"])): g["gold"] for g in p["stats"][-1]["gold_sources"]}

    souls_me = src(me)
    souls_team = collections.Counter()
    for p in mates:
        souls_team.update(src(p))
    souls_opp = collections.Counter()
    for p in lane_opp:
        souls_opp.update(src(p))

    # ---- objectives / mid boss
    objs = [{"t": o["destroyed_time_s"], "name": extras.OBJECTIVES.get(o["team_objective_id"], str(o["team_objective_id"])),
             "mine": o["team"] != me["team"]} for o in sorted(mi["objectives"], key=lambda o: o["destroyed_time_s"]) if o["destroyed_time_s"]]
    mb = [{"t": b["destroyed_time_s"], "mine": b["team_claimed"] == me["team"]} for b in (mi.get("mid_boss") or [])]

    # ---- benchmarks (all-rank averages for this hero)
    hs = _safe(benchmarks.hero_stats, me["hero_id"])
    pc = _safe(benchmarks.perf_curve, me["hero_id"])
    lc = _safe(benchmarks.lane_curve, me["hero_id"], me["assigned_lane"])
    fin = me["stats"][-1]
    acc = fin["shots_hit"] / max(1, fin["shots_hit"] + fin["shots_missed"])
    bench = {"hero_games": hs["matches"] if hs else None, "hero_winrate": hs["wins"] / hs["matches"] if hs else None,
             "hero_acc": hs["total_shots_hit"] / (hs["total_shots_hit"] + hs["total_shots_missed"]) if hs else None,
             "hero_deaths": hs["total_deaths"] / hs["matches"] if hs else None, "hero_nw": hs["total_net_worth"] / hs["matches"] if hs else None}
    nw_z = {}
    if pc:
        pts = {r["game_time"]: r for r in pc}
        for pct in (30, 50, 70, 100):
            r = pts.get(pct)
            if r and r["net_worth_std"]:
                nw_z[pct] = {"me": analyst.interp(series[slot], dur * pct / 100), "avg": r["net_worth_avg"],
                             "z": (analyst.interp(series[slot], dur * pct / 100) - r["net_worth_avg"]) / r["net_worth_std"]}
    lane_curve = []
    if lc and lane_opp and lane_mate:
        for t, mean, sd in zip(lc["sample_times_s"], lc["net_worth_diff"], lc["net_worth_diff_std"]):
            if t > dur:
                break
            mine = (sum(analyst.interp(series[p["player_slot"]], t) for p in lane_mate + [me])
                    - sum(analyst.interp(series[p["player_slot"]], t) for p in lane_opp))
            lane_curve.append({"t": t, "mine": mine, "mean": mean, "sd": sd, "z": (mine - mean) / sd if sd else 0})
    lz = {c["t"]: c["z"] for c in lane_curve}

    # ---- KPIs (the habits we track)
    n_d = me["deaths"]
    mate_d = sum(p["deaths"] for p in mates) / max(1, len(mates))
    my_dead = sum(d["respawn"] for d in deaths)
    mate_dead = sum(sum(x["death_duration_s"] for x in p["death_details"]) for p in mates) / max(1, len(mates))
    first_die = sum(1 for f in frows if f["first_me"] and f["ours"] + f["theirs"] >= 2)
    fights_in = sum(1 for f in frows if f["pres"] in ("died", "there") or f["kill"])
    team_kills = sum(p["kills"] for p in team)
    f3, ef = _first_t3(me, meta), [x for x in (_first_t3(p, meta) for p in foes) if x]
    res20 = analyst.resist_owned(me, 1200, names)
    top = dmg[0] if dmg else None
    top_total = (top["bullet"] + top["ability"] + top["melee"]) if top else 0
    kpi = {
        "deaths": n_d, "deaths_rel": n_d - mate_d, "mate_deaths": mate_d,
        "dead_pct": my_dead / dur, "mate_dead_pct": mate_dead / dur,
        "early_deaths": sum(1 for d in deaths if d["early"]),
        "caught": sum(1 for d in deaths if d["caught"]), "caught_pct": (sum(1 for d in deaths if d["caught"]) / n_d) if n_d else 0,
        "peer_caught_pct": peer_caught / max(1, peer_deaths),
        "first_die": first_die, "mate_first_die": sum(mate_first_die) / max(1, len(mate_first_die)), "fights": len(frows), "fights_in": fights_in,
        "ability_share": (tot_a + 0) / tot, "bullet_share": tot_b / tot,
        "res_b_20": res20[0], "res_s_20": res20[1],
        "top_dealer": top["hero"] if top else None, "top_dealer_share": top_total / tot if top else 0,
        "top_dealer_bullet": (top["bullet"] / top_total) if top_total else 0,
        "first_t3": f3, "first_t3_delta": (f3 - sum(ef) / len(ef)) if f3 and ef else None,
        "kp": (me["kills"] + me["assists"]) / max(1, team_kills), "mate_kp": sum(mate_kp) / max(1, len(mate_kp)),
        "nw_z_end": nw_z.get(100, {}).get("z"), "nw_z_50": nw_z.get(50, {}).get("z"),
        "lane_z9": lz.get(540), "lane_z15": lz.get(900),
        "acc": acc, "acc_delta": (acc - bench["hero_acc"]) if bench["hero_acc"] else None,
        "midboss_mine": sum(1 for b in mb if b["mine"]), "midboss_total": len(mb),
        "spm": me["net_worth"] / (dur / 60), "win": win,
        "fights_lost_away": sum(1 for f in frows if f["res"] == "lost" and f["pres"] in ("away", "dead")),
    }

    return {
        "schema": SCHEMA, "id": match_id, "calib": hist_row.get("ranked_calibration_match") or 0, "start": mi["start_time"],
        "hero": names.hero(me["hero_id"]), "hero_id": me["hero_id"], "team": me["team"], "win": win, "dur": dur, "lane": extras.lane_name(names, me["assigned_lane"]),
        "kda": [me["kills"], me["deaths"], me["assists"]], "nw": me["net_worth"], "lh": me["last_hits"], "denies": me["denies"], "level": me["level"],
        "lane_opp": [names.hero(p["hero_id"]) for p in lane_opp], "lane_mate": [names.hero(p["hero_id"]) for p in lane_mate],
        "board": board,
        "nw_curve": [{"t": t, "me": analyst.interp(series[slot], t), "opp": [analyst.interp(series[p["player_slot"]], t) for p in lane_opp],
                      "mate": [analyst.interp(series[p["player_slot"]], t) for p in lane_mate], "gap": gap(t)} for t in grid],
        "deaths": deaths, "fights": frows, "kills": kills, "midboss": mb, "objectives": objs,
        "dmg": dmg, "dmg_intervals": intervals, "items": my_items, "enemy_t3": enemy_t3,
        "souls": souls_me, "souls_team_avg": {k: v / max(1, len(mates)) for k, v in souls_team.items()},
        "souls_lane_opp_avg": {k: v / max(1, len(lane_opp)) for k, v in souls_opp.items()},
        "bench": bench, "nw_z": nw_z, "lane_curve": lane_curve, "kpi": kpi,
    }


def season_matches(history):
    """Ranked matches of the current season, oldest first: everything from the first game of the latest calibration run on."""
    cal = analyst.calibration_matches(history)
    if not cal:
        return []
    start = min(m["match_id"] for m in cal)
    return sorted((m for m in history if m["match_mode"] == analyst.RANKED and m["match_id"] >= start), key=lambda m: m["match_id"])


def load(match_id):
    f = OUT_DIR / f"{match_id}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("schema") == SCHEMA:
            return d
    return None


def build(match_id, hist_row, names, force=False):
    """Return the record for a match (from disk if fresh, else computed and saved). None if the match isn't cached."""
    if not force:
        d = load(match_id)
        if d:
            return d
    if not api.cached_match_metadata(match_id):
        return None
    d = compute(match_id, hist_row, names)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{match_id}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    return d
