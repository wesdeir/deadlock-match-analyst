# Notes (state as of 2026-11-08)

## Rate limits - important
- `/v1/matches/{id}/metadata` (per match): about **3 requests per hour per IP**; the 429 body gives `next_request_in`.
  `api.py` raises `RateLimited` when told to wait >90s. Never loop on it.
- Bulk `/v1/matches/metadata` (30 req/min) only knows matches the API has ingested (the 12 old 2024 matches: "No matches
  found") and has no damage matrix / paths, so it can't replace the per-match endpoint for reports.
- Analytics endpoints: 200 req/min per IP (shared). `/v1/players/hero-stats`: 100 req/s.
- assets.deadlock-api.com is often down; the same data is on `api.deadlock-api.com/v1/assets/*` (used first).

## Account
Steam account id 473873958 (SteamID64 76561198434139686). Main hero Celeste (81); recently also Wraith (7).
Calibration run this season: ranked matches with `ranked_calibration_match` 1,2,3,4,6,7 (game 5 missing from the API
history; game 8 not played yet). The calibration run is 8 games (ranked-seasons asset).

## Decoded / verified (checked on all 5-6 calibration games unless noted)
- Item and ability ids = MurmurHash2(class_name, seed 0x31415926).
- Damage matrix: slot 0 is not a player; players are slots 1-12. Shorter `damage` arrays are END-aligned (leading zeros trimmed).
  `stat_type` enum (from the game's protobuf): 0 Damage, 1 Healing, 2 HealPrevented, 3 Mitigated, 4 LethalDamage,
  5 Regen, 6 CrowdControl, 7 MitigatedBySource. Type 0 aggregate rows (Bullet/Ability/Melee/UnknownAbility) sum exactly to
  `player_damage`; enemy->me sums exactly to my `player_damage_taken`. Spirit vs gun-ability damage cannot be split.
- `match_paths`: position = x_min + x_pos[t]/16383*(x_max-x_min); `health` is percent 0-100; one sample per second.
- Objective ids = `ECitadelTeamObjective` (names via the protobuf); the objective's `team` is its OWNER (losing team's
  Core/Titan falls). Lane ids: `generic-data.lane_info` (1 York, 4 Broadway, 6 Greenwich).
- Stat snapshots are not time-aligned across players; curves are linearly interpolated.
- Item tags (bullet/spirit resist, anti-heal) come from non-zero property values in `abilities.vdata` (base values only; conditional bonuses not modelled). 37 of 148 items are flagged disabled in the current patch.
- Lanes are 2v2 (two players share an `assigned_lane` per team).

## Findings so far (see reports for detail)
- Calibration record 1-5 (W-L) over games 1,2,3,4,6,7. Being behind in lane at 9:00 is typical for Celeste duos (about -350 mean).
  Game 3 was the real outlier lane (about -1.6 sd). Game 7 was even in lane and +2.5k at 15:00 yet lost: late-game problem.
- Several fights where I was the first to die (game 1: 5, game 4: 4).

## Known gaps / ideas
- Game 5 not in history; check `refresh.py` later.
- Benchmarks are all-rank (lobby badge unknown in calibration).
- Not pulled yet: item win rates (`/v1/analytics/item-stats`), counter-pick rates (`hero-counter-stats`), builds,
  patch notes (`/v1/patches`), death heatmaps (`kill-death-stats`), SQL endpoint (`/v1/sql`).
- Fight detection is a simple death-cluster heuristic (deaths <=20s apart); "unspent gold minutes" meaning is inferred.
- `ACCOUNT_ID` is hard-coded in `analyst.py`.

## Repo contents
`cache/` is committed on purpose (public API data incl. other players' account ids, same visibility as their public profiles) so reports can be rebuilt without re-fetching, which matters because of the 3/hour per-match limit.
