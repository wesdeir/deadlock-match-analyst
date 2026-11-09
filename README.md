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
python refresh.py                       # refresh history, fetch missing matches (rate-limit safe), rebuild reports
python refresh.py --gamedata            # also re-download the game-file dumps (hash-verified) -> gamedata.json
python refresh.py --benchmarks          # also re-download global benchmark tables
```
Account id and main hero are constants at the top of `analyst.py` (`ACCOUNT_ID`, `MY_HERO`).

## Files
| file | purpose |
|---|---|
| `api.py` | cached, rate-limited client (descriptive User-Agent, 6s between live requests, stops on long 429s) |
| `analyst.py` | report sections: lane/net-worth curve, deaths, damage types vs items, what went well, trends; CLI |
| `extras.py` | economy, fights, enemy items, HP before death, named objectives, per-game scorecard |
| `benchmarks.py` | compares a game with all ranked games of that hero (hero stats, performance curve, lane curve) |
| `gamedata.py` | builds `gamedata.json` (hero/item names, tiers, item property values) from GameTracking-Deadlock text dumps |
| `refresh.py` | one-command update |
| `names.json` | manual name overrides / item tags |
| `NOTES.md` | decoded data formats, findings, open questions, next steps - **read this to pick up** |

`cache/`, `data/gametracking/` and `reports/` are git-ignored; they are recreated by the scripts.
