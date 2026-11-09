"""Compare a game against everyone: all ranked games in the last ~30 days (as of when the data was first fetched).

Data comes from api.deadlock-api.com/v1/analytics (hero-stats, player-performance-curve, lane-soul-curve), cached on
disk like everything else. These are ALL ranks combined (your lobby badge is unknown), so treat them as a rough
yardstick, not a same-rank comparison.
"""
import api
from analyst import interp, mmss, nw_series

A = api.API


def hero_stats(hero_id, refresh=False):
    """All-rank ranked averages for one hero (win rate, K/D/A, accuracy...), cached."""
    rows = api.get_json(f"{A}/v1/analytics/hero-stats?match_mode=ranked", refresh) or []
    return next((r for r in rows if r["hero_id"] == hero_id), None)


def perf_curve(hero_id, refresh=False):
    """Average net worth etc. over the course of a game for one hero, in 10% steps, cached."""
    return api.get_json(f"{A}/v1/analytics/player-performance-curve?match_mode=ranked&hero_ids={hero_id}&resolution=10", refresh)


def lane_curve(hero_id, lane, refresh=False):
    """Typical lead of a duo containing this hero in this lane over time (mean and sd), cached."""
    rows = api.get_json(f"{A}/v1/analytics/lane-soul-curve?match_mode=ranked&hero_ids={hero_id}"
                        f"&group_by=assigned_lane&min_matches=30", refresh) or []
    return next((r for r in rows if r["assigned_lane"] == lane), None)


def section_benchmarks(mi, me, names, lines):
    """Report section: compare this game with the all-rank averages for the hero."""
    hid = me["hero_id"]
    lines.append(f"## 3e. Benchmarks vs all ranked {names.hero(hid)} games (all ranks, ~30 days; rough yardstick)")
    try:
        hs, pc, lc = hero_stats(hid), perf_curve(hid), lane_curve(hid, me["assigned_lane"])
    except api.RateLimited as e:
        lines.append(f"(benchmarks unavailable: {e})")
        lines.append("")
        return
    fin = me["stats"][-1]
    if hs:
        n = hs["matches"]
        shots = hs["total_shots_hit"] + hs["total_shots_missed"]
        mine_shots = fin["shots_hit"] + fin["shots_missed"]
        lines.append(f"- {n:,} games: win rate {hs['wins'] / n:.1%}; per game avg K/D/A "
                     f"{hs['total_kills'] / n:.1f}/{hs['total_deaths'] / n:.1f}/{hs['total_assists'] / n:.1f}, net worth "
                     f"{hs['total_net_worth'] / n:,.0f}, last hits {hs['total_last_hits'] / n:.0f}, denies {hs['total_denies'] / n:.1f}, "
                     f"shot accuracy {hs['total_shots_hit'] / shots:.0%}")
        lines.append(f"- This game: K/D/A {me['kills']}/{me['deaths']}/{me['assists']}, net worth {me['net_worth']:,}, "
                     f"last hits {me['last_hits']}, denies {me['denies']}, shot accuracy {fin['shots_hit'] / mine_shots:.0%} "
                     f"(note: game length differs, so totals are only roughly comparable)")
    if pc:
        # Performance-curve rows are keyed by the percentage of the game elapsed (0, 10, ... 100).
        pts = {r["game_time"]: r for r in pc}
        mys = nw_series(me)
        out = []
        for pct in (30, 50, 70, 100):
            r = pts.get(pct)
            if not r:
                continue
            mine = interp(mys, mi["duration_s"] * pct / 100)
            z = (mine - r["net_worth_avg"]) / r["net_worth_std"] if r["net_worth_std"] else 0
            out.append(f"{pct}% of game: me {mine:,.0f} vs avg {r['net_worth_avg']:,.0f} ({z:+.1f} sd)")
        lines.append("- Net worth at same share of game length: " + "; ".join(out))
    if lc:
        opp = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]]
        mate = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] == me["team"]]
        if opp and mate:
            ms = [nw_series(p) for p in mate]
            os_ = [nw_series(p) for p in opp]
            out = []
            # Lane samples exist every 180s up to 15:00, then every 300s; stop at the end of this match.
            for t, mean, sd in zip(lc["sample_times_s"], lc["net_worth_diff"], lc["net_worth_diff_std"]):
                if t not in (360, 540, 900) or t > mi["duration_s"]:
                    continue
                mine = sum(interp(s, t) for s in ms) - sum(interp(s, t) for s in os_)
                out.append(f"{mmss(t)}: duo diff {mine:+,.0f} vs typical {mean:+,.0f} ({(mine - mean) / sd:+.1f} sd)")
            lines.append(f"- Lane duo lead vs enemy duo (lane {lc['assigned_lane']}, {lc['matches_played']:,} lane samples for "
                         f"{names.hero(hid)} duos; assumes the API's diff is the duo's combined souls): " + "; ".join(out))
    lines.append("")
