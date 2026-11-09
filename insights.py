"""Habits: the few recurring things worth working on, how each is measured per game, and how to tell if you're improving.

Design rules
- Only habits that stand out against *your own teammates in the same game* or against all-rank averages for your hero.
  (Checked: dying alone/outnumbered and kill participation were about the same for you and your teammates, so they are
  context on the match page, not habits.)
- Few habits (7), clear thresholds, concrete advice. Thresholds are judgment calls - tune them in HABITS.
- Trends compare your baseline (first games of the season) with your most recent games and say "need more games" until
  the sample is big enough. Win rate is shown but not used to judge a habit: over a handful of games it is mostly noise.
"""
from analyst import mmss

# ---------------------------------------------------------------- metric extraction


def eff_resist_20(k):
    """Damage-weighted resist at 20:00: bullet resist x bullet share + spirit resist x ability/other share (percent points)."""
    return k["res_b_20"] * k["bullet_share"] + k["res_s_20"] * k["ability_share"]


def value(habit_id, m):
    """The tracked number for one habit in one match (None if it can't be measured)."""
    k = m["kpi"]
    if habit_id == "deaths":
        return k["deaths_rel"]
    if habit_id == "early":
        return k["early_deaths"]
    if habit_id == "first":
        return k["first_die"] - k["mate_first_die"]
    if habit_id == "resist":
        return eff_resist_20(k)
    if habit_id == "t3":
        return k["first_t3_delta"]
    if habit_id == "lane":
        z = [v for v in (k["lane_z9"], k["lane_z15"]) if v is not None]
        return min(z) if z else None
    if habit_id == "souls":
        return k["nw_z_end"]
    return None


def _late_cost(m):
    """Seconds of respawn time lost to deaths after 25:00."""
    return sum(d["respawn"] for d in m["deaths"] if d["t"] >= 1500)


def _ev_deaths(m):
    """Evidence text for the 'dying more than teammates' habit."""
    k = m["kpi"]
    late = _late_cost(m)
    return (f"{k['deaths']} deaths vs {k['mate_deaths']:.1f} teammate average; {k['dead_pct']:.0%} of the game spent dead "
            f"(teammates {k['mate_dead_pct']:.0%})" + (f"; deaths after 25:00 alone cost {late}s of respawn" if late >= 120 else ""))


def _ev_early(m):
    """Evidence text for the lane-phase deaths habit."""
    ds = [d for d in m["deaths"] if d["early"]]
    killers = {}
    for d in ds:
        killers[d["killer"]] = killers.get(d["killer"], 0) + 1
    top = max(killers.items(), key=lambda x: x[1]) if killers else None
    return (f"{len(ds)} deaths before 10:00 (" + ", ".join(mmss(d["t"]) for d in ds) + ")"
            + (f"; {top[0]} killed you {top[1]}x" if top and top[1] > 1 else ""))


def _ev_first(m):
    """Evidence text for the first-to-die habit."""
    k = m["kpi"]
    ts = [mmss(f["t0"]) for f in m["fights"] if f["first_me"] and f["ours"] + f["theirs"] >= 2]
    return f"first to die in {k['first_die']} fights (teammates average {k['mate_first_die']:.1f}): " + ", ".join(ts)


def _ev_resist(m):
    """Evidence text for the late-resist-items habit."""
    k = m["kpi"]
    firsts = [i for i in m["items"] if any(t.startswith(("spirit_resist=", "bullet_resist=")) for t in i["tags"])]
    first = f"; first resist item {firsts[0]['name']} at {mmss(firsts[0]['t'])}" if firsts else "; no resist item bought"
    gun = (f"; top damage dealer {k['top_dealer']} was {k['top_dealer_bullet']:.0%} bullet and you owned {k['res_b_20']:g}% bullet resist"
           if k["top_dealer_bullet"] >= .55 and k["res_b_20"] < 10 else "")
    return (f"{k['ability_share']:.0%} of damage taken was ability/other, {k['bullet_share']:.0%} bullet; at 20:00 you owned "
            f"{k['res_s_20']:g}% spirit and {k['res_b_20']:g}% bullet resist (damage-weighted {eff_resist_20(k):.1f}%)" + first + gun)


def _ev_t3(m):
    """Evidence text for the slow first tier-3 item habit."""
    k = m["kpi"]
    t3 = [i for i in m["items"] if i["tier"] >= 3 and i["slot"] != "ability"]
    nm = f" ({t3[0]['name']})" if t3 else ""
    return f"first tier-3 item at {mmss(k['first_t3'])}{nm}, {k['first_t3_delta'] / 60:+.1f} min vs the enemy team's average"


def _ev_lane(m):
    """Evidence text for the lane habit."""
    k = m["kpi"]
    bits = []
    for t, z in ((540, k["lane_z9"]), (900, k["lane_z15"])):
        c = next((c for c in m["lane_curve"] if c["t"] == t), None)
        if c:
            bits.append(f"{mmss(t)}: {c['mine'] - c['mean']:+,.0f} souls vs a typical {m['hero']} duo ({z:+.1f} sd)")
    return "; ".join(bits)


def _ev_souls(m):
    """Evidence text for the low-souls habit."""
    k = m["kpi"]
    return (f"net worth {m['nw']:,} at the end = {k['nw_z_end']:+.1f} sd vs the average {m['hero']} game; {k['spm']:,.0f} souls/min")


# Each habit: how it is measured (value), when it is flagged (flag/thresh), how bad (sev), what counts as a meaningful change (change), and advice.
HABITS = [
    dict(id="deaths", title="Dying more than your teammates", unit="deaths vs team avg", better="lower", target="at or below 0",
         thresh=2.0, flag=lambda m, v: v is not None and v >= 2.0, sev=lambda v: v / 2.0, change=1.0, ev=_ev_deaths,
         advice=["Before every fight, find your nearest ally: if nobody is within reach, don't take the fight.",
                 "When your team is behind, switch to safe farming and holding space; each late death costs 60-90 seconds of respawn.",
                 "After the game, look at which deaths came at full HP with no ally near - those are the avoidable ones."]),
    dict(id="early", title="Dying in the lane phase", unit="deaths before 10:00", better="lower", target="0-1",
         thresh=3, flag=lambda m, v: v is not None and v >= 3, sev=lambda v: v / 3.0, change=0.8, ev=_ev_early,
         advice=["Before 10:00 only trade when your lane partner is near; back off at about 50% HP instead of chasing a kill.",
                 "Note which enemy kills you early and play around their burst (stay out of their range when their abilities are ready)."]),
    dict(id="first", title="Being first to die in fights", unit="first deaths vs teammates", better="lower", target="at or below 0",
         thresh=1.5, flag=lambda m, v: v is not None and m["kpi"]["first_die"] >= 3 and v >= 1.5, sev=lambda v: v / 1.5, change=0.8, ev=_ev_first,
         advice=["Let an ally or the enemy commit first; stay a screen behind your team and join once their first abilities are used.",
                 "If you're being targeted early in a fight, fall back toward allies rather than forward."]),
    dict(id="resist", title="Defensive items arrive late", unit="% damage-weighted resist at 20:00", better="higher", target="15%+ by 20:00 (experiment)",
         thresh=10, flag=lambda m, v: v is not None and v < 10, sev=lambda v: (10 - v) / 10.0 + .3, change=2.0, ev=_ev_resist,
         advice=["Experiment: buy one resist item that matches the damage you are actually taking by about 15:00 (spirit resist vs ability-heavy teams, bullet resist vs gun heroes like Haze).",
                 "After the game, check the damage-mix chart: if one damage type dominates, that is the resist to buy first next time.",
                 "Measure it: this habit's number is the damage-weighted resist you own at 20:00 - it should climb if the experiment works."]),
    dict(id="t3", title="Slow to your first tier-3 item", unit="seconds later than enemies", better="lower", target="no later than the enemy average",
         thresh=150, flag=lambda m, v: v is not None and v >= 150, sev=lambda v: v / 150.0, change=60, ev=_ev_t3,
         advice=["Aim for your first tier-3 item by about 12-14 minutes; don't float souls - spend them when you reach a shop or respawn.",
                 "Compare your first tier-3 time with the enemy list on the match page after every game."]),
    dict(id="lane", title="Losing the lane", unit="sd vs a typical duo (worst of 9:00/15:00)", better="higher", target="above -0.5",
         thresh=-1.0, flag=lambda m, v: v is not None and v <= -1.0, sev=lambda v: -v / 1.0, change=0.4, ev=_ev_lane,
         advice=["In lane, prioritise last hits and denies over trading; avoid taking damage you can't convert into a kill.",
                 "If you're down at 6:00, ask your partner to play safe and rotate rather than force fights."]),
    dict(id="souls", title="Low souls overall", unit="sd vs average hero game (final net worth)", better="higher", target="above -0.5",
         thresh=-0.8, flag=lambda m, v: v is not None and v <= -0.8, sev=lambda v: -v / 0.8, change=0.3, ev=_ev_souls,
         advice=["Fill dead time between fights with creeps or neutral camps; compare your 'souls by source' with your team on the match page.",
                 "Spend or bank souls deliberately - unspent souls don't help in fights."]),
]
HABIT = {h["id"]: h for h in HABITS}


def rules():
    """Flag rule per habit for the dashboards' threshold lines: {id: {op, v}} (op '>=' when lower is better, else '<=')."""
    return {h["id"]: {"op": ">=" if h["better"] == "lower" else "<=", "v": h["thresh"]} for h in HABITS}


def positives(m):
    """Things clearly done well this game (compared with teammates / all-rank averages)."""
    k = m["kpi"]
    out = []
    if k["deaths_rel"] <= -1.5:
        out.append(("Fewer deaths than your team", f"{k['deaths']} deaths vs {k['mate_deaths']:.1f} teammate average"))
    if k["lane_z15"] is not None and k["lane_z15"] >= 0.8:
        out.append(("Strong lane", f"{k['lane_z15']:+.1f} sd above a typical {m['hero']} duo at 15:00"))
    if k["nw_z_end"] is not None and k["nw_z_end"] >= 0.8:
        out.append(("Big souls game", f"net worth {k['nw_z_end']:+.1f} sd above the average {m['hero']} game ({k['spm']:,.0f}/min)"))
    if k["first_t3_delta"] is not None and k["first_t3_delta"] <= -60:
        out.append(("Early tier-3 item", f"{-k['first_t3_delta'] / 60:.1f} min earlier than the enemy average"))
    if k["acc_delta"] is not None and k["acc_delta"] >= 0.04:
        out.append(("Accurate shooting", f"{k['acc']:.0%} shot accuracy vs {m['bench']['hero_acc']:.0%} average for {m['hero']}"))
    if k["midboss_total"] and k["midboss_mine"] == k["midboss_total"]:
        out.append(("Won the mid boss", f"your team claimed all {k['midboss_total']}"))
    if k["kp"] - k["mate_kp"] >= 0.1:
        out.append(("High kill participation", f"{k['kp']:.0%} vs {k['mate_kp']:.0%} teammate average"))
    fights = [f for f in m["fights"]]
    if len(fights) >= 6 and sum(f["res"] == "won" for f in fights) / len(fights) >= 0.6:
        out.append(("Won most fights", f"{sum(f['res'] == 'won' for f in fights)} of {len(fights)} fights won"))
    return out


def evaluate(m):
    """Evaluate every habit for one match: value, flagged or not, severity and evidence."""
    rows = []
    for h in HABITS:
        v = value(h["id"], m)
        fl = bool(h["flag"](m, v))
        rows.append({"id": h["id"], "title": h["title"], "value": v, "flag": fl, "sev": h["sev"](v) if fl else 0.0,
                     "evidence": h["ev"](m) if (fl and v is not None) else None})
    return rows


def match_points(m, recurring_ids=()):
    """The few things to say about one match: up to 3 problems, up to 3 positives, and up to 3 concrete things to try next."""
    ev = evaluate(m)
    flagged = sorted((r for r in ev if r["flag"]), key=lambda r: -(r["sev"] + (0.5 if r["id"] in recurring_ids else 0)))
    problems = [{"id": r["id"], "title": r["title"], "evidence": r["evidence"], "recurring": r["id"] in recurring_ids,
                 "advice": HABIT[r["id"]]["advice"]} for r in flagged[:3]]
    nxt = []
    for p in problems:
        nxt.append({"habit": p["id"], "text": p["advice"][0], "recurring": p["recurring"]})
    return {"problems": problems, "positives": [{"title": t, "evidence": e} for t, e in positives(m)[:3]],
            "next": nxt, "all": ev}


# ---------------------------------------------------------------- overview: focus + progress
def overview(matches, window=10):
    """matches: season matches oldest->newest. Returns focus areas, per-habit series and baseline-vs-recent trends."""
    n = len(matches)
    recent = matches[-window:]
    focus = []
    for h in HABITS:
        flags = [evaluate(m) for m in recent]
        hits = [(m, next(r for r in ev if r["id"] == h["id"])) for m, ev in zip(recent, flags)]
        flagged = [(m, r) for m, r in hits if r["flag"]]
        if not flagged:
            continue
        focus.append({"id": h["id"], "title": h["title"], "flagged": len(flagged), "of": len(recent),
                      "mean_sev": sum(r["sev"] for _, r in flagged) / len(flagged),
                      "values": [r["value"] for _, r in hits], "advice": h["advice"], "target": h["target"], "unit": h["unit"],
                      "examples": [{"id": m["id"], "evidence": r["evidence"]} for m, r in flagged[-3:]]})
    focus.sort(key=lambda f: (-(f["flagged"] / f["of"]), -f["mean_sev"]))

    # trends: first B vs last B games
    # Baseline vs recent window: 5 games each from 10 games on, half the games from 6-9, otherwise not enough data.
    if n >= 10:
        b = 5
    elif n >= 6:
        b = n // 2
    else:
        b = 0
    trends = []
    for h in HABITS:
        series = [value(h["id"], m) for m in matches]
        row = {"id": h["id"], "title": h["title"], "unit": h["unit"], "better": h["better"], "target": h["target"], "series": series,
               "baseline": None, "recent": None, "delta": None, "verdict": "need more games"}
        if b:
            base = [v for v in series[:b] if v is not None]
            rec = [v for v in series[-b:] if v is not None]
            if len(base) >= 3 and len(rec) >= 3:
                bm, rm = sum(base) / len(base), sum(rec) / len(rec)
                d = rm - bm
                good = d < 0 if h["better"] == "lower" else d > 0
                row.update(baseline=bm, recent=rm, delta=d)
                if abs(d) < h["change"]:
                    row["verdict"] = "no clear change"
                else:
                    row["verdict"] = "improving" if good else "getting worse"
                row["tentative"] = n < 10
        trends.append(row)
    wins = [1 if m["win"] else 0 for m in matches]
    outcome = {"wins": sum(wins), "n": n, "baseline_wr": (sum(wins[:b]) / b) if b else None, "recent_wr": (sum(wins[-b:]) / b) if b else None, "b": b}
    return {"focus": focus, "trends": trends, "outcome": outcome, "need": max(0, 10 - n)}
