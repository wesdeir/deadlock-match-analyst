"""Deadlock match analyst: writes a compact Markdown report you can paste to Claude.

Usage:
  python analyst.py                    # latest ranked match + trend over last 30 ranked
  python analyst.py --match 133922932  # a specific match
  python analyst.py --last 50          # trend window
  python analyst.py --refresh-assets   # retry the (often down) assets server
"""
import argparse
import collections
import json
import os
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import api

HERE = Path(__file__).parent
ACCOUNT_ID = int(os.environ.get("DEADLOCK_ACCOUNT_ID", 473873958))  # SteamID3; override via env var
MY_HERO = int(os.environ.get("DEADLOCK_MAIN_HERO", 81))  # hero_id of the main hero (81 = Celeste)
RANKED = 4
AGG = {"Bullet", "Ability", "Melee", "UnknownAbility", "Misc"}  # aggregate rows in the damage matrix
OUT_DIR = HERE / "reports"


# ---------------------------------------------------------------- names
class Names:
    """Resolve ids: names.json > cached assets tables > derived from match data > raw id."""

    def __init__(self, refresh_assets=False):
        """Build the id -> name tables: API/assets tables first, then gamedata.json, then names.json overrides."""
        self.heroes, self.items, self.tags = {}, {}, {}
        self.derived_heroes = {}
        self.item_classes = {}
        self.item_meta = {}  # item id -> (tier, slot)
        self.lanes = []
        self.source = []
        for tbl, target, label in ((api.heroes_table(refresh_assets), self.heroes, "heroes"),
                                   (api.items_table(refresh_assets), self.items, "items")):
            if tbl:
                for e in tbl:
                    if "id" in e and e.get("name"):
                        nm = e["name"]
                        if label == "items":
                            tier, slot = e.get("item_tier") or 0, e.get("item_slot_type") or e.get("type", "")
                            self.item_meta[int(e["id"])] = (tier, slot)
                            if e.get("type") == "upgrade":
                                nm = f"{nm} (T{tier} {slot})"
                        target[int(e["id"])] = nm
                self.source.append(f"{label}: api.deadlock-api.com/v1/assets (cached)")
            else:
                self.source.append(f"{label}: assets server unavailable (using names.json / ids)")
        gd = api.generic_data(refresh_assets)
        if gd:
            self.lanes = [l.get("lane_name", "?") for l in gd.get("lane_info", [])]
        self._load_gamedata()
        f = HERE / "names.json"
        if f.exists():
            j = json.loads(f.read_text(encoding="utf-8"))
            for k, v in j.get("heroes", {}).items():
                self.heroes[int(k)] = v
            for k, v in j.get("items", {}).items():
                if isinstance(v, dict):
                    self.items[int(k)] = v.get("name", str(k))
                    if v.get("tags"):
                        self.tags[int(k)] = v["tags"]
                else:
                    self.items[int(k)] = v

    TAGS = {  # item property -> tag (heuristic: property present on the item definition)
        "bullet_resist": ("BulletResist", "BulletResistBelowThreshold", "BulletResistPerStack"),  # NonPlayerBulletResist = vs creeps only, excluded
        "spirit_resist": ("TechResist", "TechArmorDamageReduction", "TechResistBelowThreshold", "SpiritDamageReductionProc"),
        "anti_heal": ("HealAmpReceivePenaltyPercent", "HealAmpRegenPenaltyPercent"),
        "debuff_resist": ("StatusResistancePercent", "DebuffDuration"),
        "barrier": ("CombatBarrier", "TechShieldMaxHealth"),
    }

    def _load_gamedata(self):
        """Merge hero/item names and item property values from gamedata.json (built by gamedata.py); also derives the resist tags."""
        f = HERE / "gamedata.json"
        if not f.exists():
            return
        g = json.loads(f.read_text(encoding="utf-8"))
        for k, v in g["heroes"].items():
            self.heroes.setdefault(int(k), v["name"])
        for k, v in g["items"].items():
            k = int(k)
            self.items.setdefault(k, f"{v['name']} (T{v['tier']} {v['slot']})")  # tags added below
            def num(x):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return 0.0
            # tag only on a non-zero value; show the value so e.g. "spirit_resist=18"
            tags = []
            for t, ps in self.TAGS.items():
                vals = [(p, num(v["props"].get(p))) for p in ps if num(v["props"].get(p))]
                if vals:
                    val = vals[0][1]
                    if val < 0 and t in ("bullet_resist", "spirit_resist"):
                        tags.append(f"{t.split('_')[0]}_resist_SHRED_on_enemy={-val:g}")  # negative = reduces the enemy's resist
                    else:
                        tags.append(f"{t}={val:g}")
            if v.get("disabled"):
                tags.append("DISABLED-in-current-patch")
            if tags:
                self.tags[k] = tags
        self.source.append("names: gamedata.json (GameTracking-Deadlock dump)")

    def hero(self, hid):
        """Display name for a hero id (table name, else internal code derived from the match, else 'hero#id')."""
        if hid in self.heroes:
            return self.heroes[hid]
        if hid in self.derived_heroes:
            return f"{self.derived_heroes[hid]} (#{hid})"
        return f"hero#{hid}"

    def item(self, iid):
        """Display name for an item id, with any resist/anti-heal tags appended in brackets."""
        n = self.items.get(iid) or self.item_classes.get(iid)
        t = self.tags.get(iid)
        base = n if n else f"item#{iid}"
        return f"{base} [{','.join(t)}]" if t else base


def derive_hero_codes(mi, names):
    """Internal hero codes (e.g. 'unicorn') come from each player's own weapon names in the damage matrix."""
    dm = mi["damage_matrix"]
    sd = dm["source_details"]
    slot_hero = {p["player_slot"]: p["hero_id"] for p in mi["players"]}
    for d in dm["damage_dealers"]:
        sl = d["dealer_player_slot"]
        if sl not in slot_hero:
            continue
        best, bv = None, -1
        for s in d["damage_sources"]:
            i = s["source_details_index"]
            if sd["stat_type"][i] != 0:
                continue
            m = re.match(r"citadel_weapon_(.+?)_set\d*(?:_crit)?$", sd["source_name"][i])
            if not m:
                continue
            v = sum(tp["damage"][-1] for tp in s["damage_to_players"] if tp["damage"])
            if v > bv:
                best, bv = m.group(1), v
        if best:
            names.derived_heroes[slot_hero[sl]] = best


def murmur2(data: bytes, seed=0x31415926):
    """Deadlock item/ability ids are MurmurHash2(class_name, seed 0x31415926) - verified: 92 of 105 candidate
    class names in match 133922932 hit real item ids."""
    m = 0x5bd1e995
    n = len(data)
    h = (seed ^ n) & 0xffffffff
    i = 0
    while n >= 4:
        k = int.from_bytes(data[i:i + 4], "little")
        k = (k * m) & 0xffffffff
        k ^= k >> 24
        k = (k * m) & 0xffffffff
        h = ((h * m) & 0xffffffff) ^ k
        i += 4
        n -= 4
    if n == 3:
        h ^= data[i + 2] << 16
    if n >= 2:
        h ^= data[i + 1] << 8
    if n >= 1:
        h ^= data[i]
        h = (h * m) & 0xffffffff
    h ^= h >> 13
    h = (h * m) & 0xffffffff
    h ^= h >> 15
    return h


def derive_item_classes(mi, names):
    """Reverse item ids to class names using every source name seen in the damage matrix."""
    for n in set(mi["damage_matrix"]["source_details"]["source_name"]):
        if n.startswith(("upgrade_", "ability_")):
            names.item_classes.setdefault(murmur2(n.encode()), n)


# ---------------------------------------------------------------- helpers
def mmss(t):
    """Format seconds as m:ss (e.g. 1234 -> '20:34')."""
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"


def interp(points, t):
    """points: sorted [(time, value)] starting anywhere; linear interpolation, flat after the end."""
    if not points:
        return 0
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1
    return points[-1][1]


def nw_series(p):
    """A player's net-worth snapshots as sorted (time_s, net_worth) points, starting from (0, 0)."""
    # Snapshots only start at 3:00, so prepend (0, 0) to let curves be interpolated from the start of the game.
    return [(0, 0)] + sorted((s["time_stamp_s"], s["net_worth"]) for s in p["stats"])


def nearest_snapshot(p, t):
    """The stats snapshot closest in time to t (snapshots are every 3-5 minutes)."""
    return min(p["stats"], key=lambda s: abs(s["time_stamp_s"] - t))


def pos_at(path, t):
    """A player's map position (x, y) at second t, converted from the packed path data to game coordinates."""
    t = max(0, min(int(t), len(path["x_pos"]) - 1))
    # Paths store each coordinate as a 0..16383 fraction of that player's own bounding box (x_min..x_max).
    x = path["x_min"] + path["x_pos"][t] / 16383 * (path["x_max"] - path["x_min"])
    y = path["y_min"] + path["y_pos"][t] / 16383 * (path["y_max"] - path["y_min"])
    return x, y


def matrix_cells(mi):
    """Yield (dealer_slot, target_slot, stat_type, source_name, cumulative_series_aligned_to_samples)."""
    dm = mi["damage_matrix"]
    sd = dm["source_details"]
    n = len(dm["sample_time_s"])
    for d in dm["damage_dealers"]:
        for s in d["damage_sources"]:
            i = s["source_details_index"]
            for tp in s["damage_to_players"]:
                a = tp["damage"]
                if not a:
                    continue
                # VERIFIED: shorter arrays are end-aligned (leading zeros trimmed).
                a = [0] * (n - len(a)) + a
                yield d["dealer_player_slot"], tp["target_player_slot"], sd["stat_type"][i], sd["source_name"][i], a


def damage_profile(mi, dealer, target):
    """Damage dealer->target split by aggregate source (stat_type 0, aggregate rows). VERIFIED: sums to player_damage."""
    out = collections.Counter()
    # Walk the damage matrix: dealer d, target t, stat type st (0 = damage), source name, cumulative series a.
    for d, t, st, name, a in matrix_cells(mi):
        if d == dealer and t == target and st == 0 and name in AGG:
            out[name] += a[-1]
    return out


BRIEF = False


def resist_owned(p, t, names):
    """Sum of base bullet/spirit resist % from items owned at time t (bought <= t, not sold before t)."""
    br = sr = 0.0
    for i in p["items"]:
        if i["game_time_s"] > t or (i["sold_time_s"] and i["sold_time_s"] <= t):
            continue
        for tag in names.tags.get(i["item_id"], []):
            if tag.startswith("DISABLED"):
                continue
            k, _, v = tag.partition("=")
            if k == "bullet_resist":
                br += float(v)
            elif k == "spirit_resist":
                sr += float(v)
    return br, sr


def dead_intervals(mi):
    """Per player slot: list of (death_time, respawn_time) intervals - used to know who is alive at a given second."""
    iv = collections.defaultdict(list)
    for p in mi["players"]:
        for dd in p["death_details"]:
            iv[p["player_slot"]].append((dd["game_time_s"], dd["game_time_s"] + dd.get("death_duration_s", 0)))
    return iv


# ---------------------------------------------------------------- report sections
def section_overview(mi, me, names, lines):
    """Report section 1: result, lane matchup and the net-worth curve against the lane opponents."""
    players = {p["player_slot"]: p for p in mi["players"]}
    won = me["team"] == mi["winning_team"]
    start = datetime.fromtimestamp(mi["start_time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"## 1. Result and lane")
    lines.append(f"- **{'WIN' if won else 'LOSS'}** | {names.hero(me['hero_id'])} | {mmss(mi['duration_s'])} | "
                 f"match {mi['match_id']} | {start} | mode {mi['match_mode']} (4=ranked)")
    lines.append(f"- KDA {me['kills']}/{me['deaths']}/{me['assists']} | net worth {me['net_worth']:,} | "
                 f"last hits {me['last_hits']} | denies {me['denies']} | level {me['level']}")
    opp = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]]
    mate = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] == me["team"]
            and p["player_slot"] != me["player_slot"]]
    lines.append(f"- Lane {me['assigned_lane']}: with " + (", ".join(names.hero(p['hero_id']) for p in mate) or "nobody")
                 + " vs " + ", ".join(f"{names.hero(p['hero_id'])} (slot {p['player_slot']}, final NW {p['net_worth']:,}, "
                                       f"KDA {p['kills']}/{p['deaths']}/{p['assists']})" for p in opp))
    lines.append("- Note: lanes are 2v2 here; 'lane opponent' = both enemies sharing my assigned_lane.")
    lines.append("")
    # NW curve on a 3-minute grid (interpolated: players' snapshots are not aligned)
    grid = list(range(360 if BRIEF else 180, mi["duration_s"], 360 if BRIEF else 180)) + [mi["duration_s"]]
    lines.append("Net worth curve (interpolated between each player's stat snapshots, so +/-small error):")
    hdr = ["time", "me"] + [f"opp {names.hero(p['hero_id'])}" for p in opp] + ["lane diff (me - avg opp)", "team diff"]
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|" + "---|" * len(hdr))
    my_s = nw_series(me)
    opp_s = [nw_series(p) for p in opp]
    team = {tm: [nw_series(p) for p in mi["players"] if p["team"] == tm] for tm in (0, 1)}
    for t in grid:
        mv = interp(my_s, t)
        ov = [interp(s, t) for s in opp_s]
        avg = sum(ov) / len(ov) if ov else 0
        td = sum(interp(s, t) for s in team[me["team"]]) - sum(interp(s, t) for s in team[1 - me["team"]])
        lines.append(f"| {mmss(t)} | {mv:,.0f} | " + " | ".join(f"{v:,.0f}" for v in ov)
                     + f" | {mv - avg:+,.0f} | {td:+,.0f} |")
    lines.append("")


def section_deaths(mi, me, names, lines):
    """Report section 2: every death with killer, net worth, who was nearby, HP beforehand and a snapshot."""
    players = {p["player_slot"]: p for p in mi["players"]}
    paths = {p["player_slot"]: p for p in mi["match_paths"]["paths"]}
    dead = dead_intervals(mi)
    opp_slots = {p["player_slot"] for p in mi["players"]
                 if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]}
    lines.append(f"## 2. Deaths ({len(me['death_details'])})")
    lines.append("NW values are interpolated at the death time. 'Near' counts living players within 2500 map units "
                 "(position scale checked against death_pos). 'TTK' = seconds from first damage to death.")
    lines.append("")
    for n, dd in enumerate(me["death_details"], 1):
        t = dd["game_time_s"]
        k = players.get(dd["killer_player_slot"])
        lines.append(f"**Death {n} at {mmss(t)}** (respawn {dd.get('death_duration_s', '?')}s, TTK {dd['time_to_kill_s']:.1f}s)")
        if k:
            knw = interp(nw_series(k), t)
            mnw = interp(nw_series(me), t)
            tag = " (lane opponent)" if k["player_slot"] in opp_slots else ""
            prof = damage_profile(mi, k["player_slot"], me["player_slot"])
            tot = sum(prof.values()) or 1
            split = ", ".join(f"{n_}:{v / tot:.0%}" for n_, v in prof.most_common())
            lines.append(f"- Killer: {names.hero(k['hero_id'])} slot {k['player_slot']}{tag}; "
                         f"NW me {mnw:,.0f} vs killer {knw:,.0f} ({mnw - knw:+,.0f}); "
                         f"killer's whole-game damage on me: {split}")
        else:
            lines.append(f"- Killer slot {dd['killer_player_slot']} (not a player: creep/objective/world)")
        # proximity
        if me["player_slot"] in paths:
            mx, my = pos_at(paths[me["player_slot"]], t - 1)
            al, en = [], []
            for sl, pp in paths.items():
                if sl == me["player_slot"] or sl not in players:
                    continue
                if any(a <= t - 1 < b for a, b in dead[sl]):
                    continue
                x, y = pos_at(pp, t - 1)
                # 'Near' = within 2500 map units, measured 1s before the death so we see who was close as it happened.
                if math.hypot(x - mx, y - my) <= 2500:
                    (al if players[sl]["team"] == me["team"] else en).append(names.hero(players[sl]["hero_id"]))
            lines.append(f"- Near at t-1s: allies {len(al)} {al or ''}; enemies {len(en)} {en or ''}")
        # Imported here (not at the top): extras imports helpers from this module, so a top-level import would be circular.
        import extras
        hp = extras.death_hp_line(mi, me, dd)
        if hp:
            lines.append(hp)
        s = nearest_snapshot(me, t)
        if not BRIEF:
            lines.append(f"- Nearest own snapshot t={mmss(s['time_stamp_s'])}: NW {s['net_worth']:,}, lvl {s['level']}, "
                         f"K/D/A {s['kills']}/{s['deaths']}/{s['assists']}, max HP {s['max_health']}, "
                         f"weapon/tech power {s['weapon_power']}/{s['tech_power']}, dmg taken so far {s['player_damage_taken']:,}")
        lines.append("")


def section_counter(mi, me, names, lines):
    """Report section 3: damage taken by enemy and type, per-interval mix with resist owned, and item timing."""
    slot = me["player_slot"]
    enemies = [p for p in mi["players"] if p["team"] != me["team"]]
    lines.append("## 3. Enemy damage types vs my item timing")
    lines.append("Damage matrix (stat types are the game's own enum: 0 Damage, 1 Healing, 2 HealPrevented, 3 Mitigated, "
                 "4 LethalDamage, 5 Regen, 6 CrowdControl, 7 MitigatedBySource). Used here: type 0, dealer->target; the aggregate "
                 "rows Bullet/Ability/Melee/UnknownAbility each sum to exactly player_damage, and enemy->me sums to exactly my "
                 "player_damage_taken (checked). Shorter arrays are end-aligned. 'Ability'+'UnknownAbility' = non-gun damage "
                 "(abilities, spirit, item procs); the matrix cannot split spirit from gun-abilities.")
    lines.append("")
    lines.append("Damage dealt to me, by enemy:")
    lines.append("| enemy | total | Bullet | Ability | Melee | Unknown | bullet % |")
    lines.append("|---|---|---|---|---|---|---|")
    grand = collections.Counter()
    for e in sorted(enemies, key=lambda p: -sum(damage_profile(mi, p["player_slot"], slot).values())):
        pr = damage_profile(mi, e["player_slot"], slot)
        tot = sum(pr.values())
        grand.update(pr)
        lines.append(f"| {names.hero(e['hero_id'])} | {tot:,} | {pr['Bullet']:,} | {pr['Ability']:,} | {pr['Melee']:,} | "
                     f"{pr['UnknownAbility']:,} | {pr['Bullet'] / tot:.0%} |" if tot else
                     f"| {names.hero(e['hero_id'])} | 0 | | | | | |")
    gt = sum(grand.values()) or 1
    lines.append(f"\nTotal taken from enemy heroes: {gt:,} -> bullet {grand['Bullet'] / gt:.0%}, "
                 f"ability/other {(grand['Ability'] + grand['UnknownAbility']) / gt:.0%}, melee {grand['Melee'] / gt:.0%}")
    # per-interval
    dm = mi["damage_matrix"]
    ts = dm["sample_time_s"]
    per = collections.defaultdict(lambda: collections.Counter())
    ens = {e["player_slot"] for e in enemies}
    for d, t, st, name, a in matrix_cells(mi):
        if d in ens and t == slot and st == 0 and name in AGG:
            # The matrix is cumulative, so each interval's damage is this sample minus the previous one.
            prev = 0
            for k, v in enumerate(a):
                per[k][name] += v - prev
                prev = v
    if not BRIEF:
        lines.append(chr(10) + "Damage taken per interval (ending at sample time), with the resist items I owned then "
                     "(sum of base values from the game files; 'owned' = bought and not yet sold):")
        lines.append("| until | total | bullet % | non-bullet % | my bullet-resist owned | my spirit-resist owned |")
        lines.append("|---|---|---|---|---|---|")
        for k, t in enumerate(ts):
            c = per[k]
            tt = sum(c.values())
            if tt:
                br, sr = resist_owned(me, t, names)
                lines.append(f"| {mmss(t)} | {tt:,} | {c['Bullet'] / tt:.0%} | "
                             f"{(c['Ability'] + c['UnknownAbility'] + c['Melee']) / tt:.0%} | {br:g}% | {sr:g}% |")
    # items
    items = sorted(me["items"], key=lambda i: i["game_time_s"])
    if not BRIEF:
        lines.append(chr(10) + "Items bought (time, sold time):")
    row = []
    for i in items:
        s = f"{mmss(i['game_time_s'])} {names.item(i['item_id'])}"
        if i["sold_time_s"]:
            s += f" (sold {mmss(i['sold_time_s'])})"
        if i["upgrade_id"] and i["upgrade_id"] != 1:
            s += f" +upg#{i['upgrade_id']}"
        row.append(s)
    if not BRIEF:
        lines.append("; ".join(row))
    tagged = [i for i in items if names.tags.get(i["item_id"])]
    if tagged:
        lines.append("\nTagged counter items: " + "; ".join(f"{mmss(i['game_time_s'])} {names.item(i['item_id'])}" for i in tagged))
    else:
        lines.append(chr(10) + "No defensive/counter items identified in my build.")
    lines.append("")


def section_good(mi, me, names, lines):
    """Report section 4: what went well - farm, kills, accuracy, objectives, mid boss and team swings."""
    players = {p["player_slot"]: p for p in mi["players"]}
    slot = me["player_slot"]
    lines.append("## 4. What went well")
    dur_min = mi["duration_s"] / 60
    opp = [p for p in mi["players"] if p["assigned_lane"] == me["assigned_lane"] and p["team"] != me["team"]]
    team = [p for p in mi["players"] if p["team"] == me["team"]]
    fin = me["stats"][-1]
    lines.append(f"- Souls/min {me['net_worth'] / dur_min:,.0f}; last hits {me['last_hits']} "
                 f"(team avg {sum(p['last_hits'] for p in team) / len(team):.0f}, lane opponents "
                 f"{', '.join(str(p['last_hits']) for p in opp)}); denies {me['denies']}")
    lines.append(f"- Net worth rank on my team: {sorted((p['net_worth'] for p in team), reverse=True).index(me['net_worth']) + 1}/{len(team)}"
                 f"; hero damage {fin['player_damage']:,} (team share "
                 f"{fin['player_damage'] / sum(p['stats'][-1]['player_damage'] for p in team):.0%}), healing {fin['player_healing']:,}")
    shots = fin["shots_hit"] + fin["shots_missed"]
    lines.append(f"- Accuracy {fin['shots_hit'] / shots:.0%} overall; hero bullet hits {fin['hero_bullets_hit']} "
                 f"({fin['hero_bullets_hit_crit']} crit/headshot); headshot kills {fin['headshot_kills']}")
    # kills
    kills = []
    for p in mi["players"]:
        for dd in p["death_details"]:
            if dd["killer_player_slot"] == slot:
                kills.append((dd["game_time_s"], p))
    kills.sort(key=lambda x: x[0])
    lines.append(f"- Kills ({len(kills)}): " + ", ".join(f"{mmss(t)} {names.hero(p['hero_id'])}" for t, p in kills))
    # kill clusters (<=20s apart)
    clusters, cur = [], []
    for t, p in kills:
        if cur and t - cur[-1][0] > 20:
            clusters.append(cur)
            cur = []
        cur.append((t, p))
    if cur:
        clusters.append(cur)
    multi = [c for c in clusters if len(c) >= 2]
    if multi:
        lines.append("- Multi-kills: " + "; ".join(f"{len(c)} kills at {mmss(c[0][0])}" for c in multi))
    # objectives
    objs = sorted((o for o in mi["objectives"] if o["destroyed_time_s"]), key=lambda o: o["destroyed_time_s"])
    # Imported here (not at the top): extras imports helpers from this module, so a top-level import would be circular.
    import extras
    if not BRIEF:
        lines.append(extras.objective_line(mi, me) + ("" if extras.check_objective_owner(mi) else
                     "  (WARNING: objective-owner check failed for this match)"))
    mb = mi.get("mid_boss") or []
    if mb:
        lines.append("- Mid boss: " + ", ".join(f"killed by {'my team' if m_['team_killed'] == me['team'] else 'enemy'}, "
                                                 f"claimed by {'my team' if m_['team_claimed'] == me['team'] else 'enemy'} at {mmss(m_['destroyed_time_s'])}"
                                                 for m_ in mb))
    # comeback: team NW diff over time
    my_t = [nw_series(p) for p in mi["players"] if p["team"] == me["team"]]
    en_t = [nw_series(p) for p in mi["players"] if p["team"] != me["team"]]
    diffs = [(t, sum(interp(s, t) for s in my_t) - sum(interp(s, t) for s in en_t)) for t in range(180, mi["duration_s"], 60)]
    worst = min(diffs, key=lambda x: x[1])
    best = max(diffs, key=lambda x: x[1])
    lines.append(f"- Team NW swing: worst {worst[1]:+,.0f} at {mmss(worst[0])}, best {best[1]:+,.0f} at {mmss(best[0])}, "
                 f"final {diffs[-1][1]:+,.0f}")
    if worst[1] < -3000 and diffs[-1][1] > worst[1] + 4000:
        lines.append(f"  - Comeback pattern: recovered from {worst[1]:+,.0f} at {mmss(worst[0])}")
    # deaths vs team
    lines.append(f"- Deaths {me['deaths']} vs team avg {sum(p['deaths'] for p in team) / len(team):.1f} "
                 f"(KDA ratio {(me['kills'] + me['assists']) / max(1, me['deaths']):.1f})")
    lines.append("")


def calibration_matches(history):
    """The latest calibration run: ranked matches that carry a calibration counter, returned newest first.

    Ordering is by match_id (start_time is unreliable for some very old entries). Ranked games played AFTER calibration
    have no counter, so they are skipped first; then we collect games while the counter keeps falling as we go back in
    time (a rise means we have reached an older season's calibration run, so we stop).
    """
    ranked = sorted((m for m in history if m["match_mode"] == RANKED), key=lambda m: -m["match_id"])
    out = []
    prev = 10**9
    for m in ranked:
        c = m.get("ranked_calibration_match") or 0
        if c <= 0:
            if out:
                break  # the counter ended: older, pre-calibration games
            continue  # newer ranked games played after calibration: skip them
        if c >= prev:  # counter went up going back in time = an older calibration run
            break
        out.append(m)
        prev = c
    return out


def section_trends(history, names, last_n, lines, matches=None):
    """Report section 5: results by hero over a set of ranked matches."""
    ranked = sorted((m for m in history if m["match_mode"] == RANKED), key=lambda m: -m["match_id"])
    rec = matches if matches is not None else ranked[:last_n]
    label = "calibration run" if matches is not None else f"last {len(rec)} ranked"
    lines.append(f"## 5. Trends: {label}, {len(rec)} matches (ordered by match_id)")

    def agg(ms):
        if not ms:
            return None
        w = sum(1 for m in ms if m["match_result"] == m["player_team"])
        mins = sum(m["match_duration_s"] for m in ms) / 60
        return dict(n=len(ms), w=w, k=sum(m["player_kills"] for m in ms) / len(ms),
                    d=sum(m["player_deaths"] for m in ms) / len(ms), a=sum(m["player_assists"] for m in ms) / len(ms),
                    spm=sum(m["net_worth"] for m in ms) / mins, dpm=sum(m["player_deaths"] for m in ms) / mins * 10,
                    lh=sum(m["last_hits"] for m in ms) / len(ms), dur=mins / len(ms))

    def row(label, a):
        if not a:
            return f"| {label} | 0 | | | | | | |"
        return (f"| {label} | {a['n']} | {a['w']}-{a['n'] - a['w']} ({a['w'] / a['n']:.0%}) | "
                f"{a['k']:.1f}/{a['d']:.1f}/{a['a']:.1f} | {(a['k'] + a['a']) / max(a['d'], .1):.1f} | "
                f"{a['spm']:,.0f} | {a['dpm']:.1f} | {a['lh']:.0f} |")

    hdr = "| group | games | W-L | avg K/D/A | KDA ratio | souls/min | deaths/10min | last hits |\n|---|---|---|---|---|---|---|---|"
    lines.append(hdr)
    cel = [m for m in rec if m["hero_id"] == MY_HERO]
    oth = [m for m in rec if m["hero_id"] != MY_HERO]
    lines.append(row(f"{names.hero(MY_HERO)}", agg(cel)))
    lines.append(row("other heroes", agg(oth)))
    lines.append(row("all", agg(rec)))
    by = collections.defaultdict(list)
    for m in oth:
        by[m["hero_id"]].append(m)
    lines.append("\nOther heroes (most played first):")
    lines.append(hdr)
    for hid, ms in sorted(by.items(), key=lambda kv: -len(kv[1])):
        lines.append(row(names.hero(hid), agg(ms)))
    # form
    form = "".join("W" if m["match_result"] == m["player_team"] else "L" for m in rec)
    lines.append(f"\nForm, newest first: {form}")
    half = len(rec) // 2
    if half >= 5:
        a1, a2 = agg(rec[:half]), agg(rec[half:])
        lines.append(f"Recent {half}: {a1['w']}/{a1['n']} wins, {a1['dpm']:.1f} deaths/10min, {a1['spm']:,.0f} souls/min; "
                     f"previous {len(rec) - half}: {a2['w']}/{a2['n']} wins, {a2['dpm']:.1f} deaths/10min, {a2['spm']:,.0f} souls/min")
    lines.append("")


def emit_match(mi, me, names, lines):
    """Write every report section for one match, in order."""
    # Imported here (not at the top): extras imports helpers from this module, so a top-level import would be circular.
    import extras
    section_overview(mi, me, names, lines)
    section_deaths(mi, me, names, lines)
    section_counter(mi, me, names, lines)
    extras.section_enemy_items(mi, me, names, lines)
    if not BRIEF:
        extras.section_economy(mi, me, names, lines)
    extras.section_fights(mi, me, names, lines)
    import benchmarks
    benchmarks.section_benchmarks(mi, me, names, lines)
    section_good(mi, me, names, lines)


def calibration_report(history, args):
    """Build reports/calibration_report.md: trends, scorecard and a full per-match report for each calibration game."""
    cal = calibration_matches(history)
    names = Names(args.refresh_assets)
    lines = [f"# Deadlock calibration run - account {ACCOUNT_ID}",
             f"_{len(cal)} ranked matches with a calibration counter; counters seen: "
             f"{sorted(m['ranked_calibration_match'] for m in cal)} (a gap means that game is missing from the API history). "
             f"Names: {'; '.join(names.source)}._", ""]
    section_trends(history, names, 0, lines, matches=cal)
    # Imported here (not at the top): extras imports helpers from this module, so a top-level import would be circular.
    import extras
    summaries, body_start = [], len(lines)
    lines.append("## Per-match reports (oldest first)")
    lines.append("")
    missing = []
    for m in sorted(cal, key=lambda m: m["match_id"]):
        meta = api.match_metadata(m["match_id"])
        if not meta:
            missing.append(m["match_id"])
            continue
        mi = meta["match_info"]
        derive_hero_codes(mi, names)
        derive_item_classes(mi, names)
        me = next(p for p in mi["players"] if p["account_id"] == ACCOUNT_ID)
        lines.append(f"# Calibration game {m['ranked_calibration_match']} (match {m['match_id']})")
        emit_match(mi, me, names, lines)
        summaries.append(extras.game_summary(mi, me, names, m))
    if missing:
        lines.append(f"_No metadata cached for: {missing}_")
    card = extras.scorecard_lines(summaries) + extras.pattern_lines(summaries) + [""]
    lines[body_start:body_start] = card
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / ("calibration_report_brief.md" if BRIEF else "calibration_report.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes); matches {len(cal)}, missing metadata {missing}")


# ---------------------------------------------------------------- main
def main():
    """Command-line entry point: one match report (default) or the calibration report."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", type=int)
    ap.add_argument("--last", type=int, default=30)
    ap.add_argument("--calibration", action="store_true", help="one combined report for this season's calibration run")
    ap.add_argument("--brief", action="store_true", help="shorter report (about half the size)")
    ap.add_argument("--refresh-assets", action="store_true")
    ap.add_argument("--refresh-history", action="store_true")
    args = ap.parse_args()
    global BRIEF
    BRIEF = args.brief

    history = api.match_history(ACCOUNT_ID, refresh=args.refresh_history)
    if not history:
        sys.exit("Could not load match history.")
    if args.calibration:
        return calibration_report(history, args)
    mid = args.match
    if not mid:
        ranked = sorted((m for m in history if m["match_mode"] == RANKED), key=lambda m: -m["match_id"])
        mid = ranked[0]["match_id"]
    meta = api.match_metadata(mid)
    if not meta:
        sys.exit(f"Could not load metadata for {mid}.")
    mi = meta["match_info"]
    names = Names(args.refresh_assets)
    derive_hero_codes(mi, names)
    derive_item_classes(mi, names)
    me = next((p for p in mi["players"] if p["account_id"] == ACCOUNT_ID), None)
    if not me:
        sys.exit("I am not in that match.")

    lines = [f"# Deadlock match report - account {ACCOUNT_ID}",
             f"_Names: {'; '.join(names.source)}. Hero names in the form 'code (#id)' are internal codes read from the "
             f"match's weapon names; add real names to names.json._", ""]
    emit_match(mi, me, names, lines)
    section_trends(history, names, args.last, lines)

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / (f"report_{mid}_brief.md" if BRIEF else f"report_{mid}.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
