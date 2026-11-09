# deadlock-match-analyst

Personal Deadlock match analyst. Pulls my ranked matches from the Deadlock API, caches everything on disk, and writes a
compact Markdown report to paste into Claude ("what did I do badly in the loss / well in the win?").

Python 3 standard library only - nothing to install.

## Quick start
```bash
python analyst.py                       # latest ranked match -> reports/report_<id>.md
python analyst.py --match 133922932     # a specific match
python analyst.py --calibration         # this season's calibration run, one combined report (+ scorecard)
python analyst.py --calibration --brief # shorter version
python viz.py                           # rebuild docs/dashboard.html (also done by --calibration)
python refresh.py                       # refresh history, fetch missing matches (rate-limit safe), rebuild reports
python refresh.py --gamedata            # also re-download the game-file dumps (hash-verified) -> gamedata.json
python refresh.py --benchmarks          # also re-download global benchmark tables
```
## Using it for your own account
Set your SteamID3 (the number in your Steam friend code / the part of your profile id, e.g. from the `account_id` in
match history) and main hero id (see `gamedata.json` or `/v1/assets/heroes`):
```bash
# PowerShell
$env:DEADLOCK_ACCOUNT_ID = "123456789"; $env:DEADLOCK_MAIN_HERO = "81"; python analyst.py
```
The defaults are the author's own account.


## Files
| file | purpose |
|---|---|
| `api.py` | cached, rate-limited client (descriptive User-Agent, 6s between live requests, stops on long 429s) |
| `analyst.py` | report sections: lane/net-worth curve, deaths, damage types vs items, what went well, trends; CLI |
| `extras.py` | economy, fights, enemy items, HP before death, named objectives, per-game scorecard |
| `benchmarks.py` | compares a game with all ranked games of that hero (hero stats, performance curve, lane curve) |
| `gamedata.py` | builds `gamedata.json` (hero/item names, tiers, item property values) from GameTracking-Deadlock text dumps |
| `viz.py` | builds `docs/dashboard.html`, a self-contained offline dashboard (scorecard, team gap, lane vs typical, fights, damage mix, souls, death map) |
| `refresh.py` | one-command update |
| `names.json` | manual name overrides / item tags |
| `NOTES.md` | decoded data formats, findings, open questions, next steps - **read this to pick up** |

`cache/` (API responses, so you can run offline and skip the strict rate limit) is committed. `data/gametracking/` and `reports/` are git-ignored and recreated by the scripts.

## Credits, data sources, and disclaimer
- Match data: the community [Deadlock API](https://deadlock-api.com). Please respect its rate limits (see `NOTES.md`);
  the client here is deliberately slow and caches everything.
- Game data (hero/item names, item values, enum names): text dumps from
  [SteamTracking/GameTracking-Deadlock](https://github.com/SteamTracking/GameTracking-Deadlock), downloaded on demand with
  hash verification and never executed. `gamedata.json` is a small derived table of names and numbers.
- This is an unofficial fan project, not affiliated with or endorsed by Valve. Deadlock and related names are Valve's.
- Licensed under the [MIT License](LICENSE).
