# deadlock-match-analyst

Personal Deadlock match analyst. Pulls my ranked matches from the Deadlock API, caches everything on disk, and builds
two dashboards so I can improve a few things at a time:

- **Overview** (`docs/index.html`): this season's ranked games, the 1-3 habits to focus on right now, and an
  "are you improving?" tracker (baseline vs recent) for each habit.
- **Per match** (`docs/matches/<id>.html`): key points (what to work on, what went well, what to try next game), then
  every chart and table: timeline, lane, deaths, fights, damage and defense, items, economy, all the raw data.

Python 3 standard library only - nothing to install. The pages are plain HTML and work offline.

## The workflow
```bash
python refresh.py          # after playing: update history, download the newest missing match(es), rebuild everything
# open docs/matches/<newest id>.html   -> read "Work on / Try next game", pick one thing for the next game
# every so often:
# open docs/index.html                 -> focus areas + are-you-improving tracker
```
Or step by step:
```bash
python analyze.py match [ID]     # one match page (default: latest ranked match this season)
python analyze.py overview       # the overview page
python analyze.py all            # every page
python analyze.py all --refresh  # fetch new matches first
```
The per-match endpoint allows only ~3 requests per hour, so `refresh.py` downloads at most 2 matches per run and stops
politely if rate limited (see `NOTES.md`). Already-downloaded matches are cached and committed.

## Automatic mode: run it when a game ends
```bash
python watch.py --open      # leave it running while you play
```
It checks your match history every 7 minutes (gentle on the API's limits). When a new ranked match appears it downloads
it (respecting the 3-per-hour limit), rebuilds every page and opens the new match page. To start it at login on Windows,
add a Task Scheduler task (run `taskschd.msc`, trigger "At log on", action `pythonw` with arguments
`C:\path\to\watch.py --open`, start in the repo folder). `python watch.py --once` does a single check, handy for a
scheduled task that runs every few minutes instead.

## Using it with Claude
- **Pages -> Claude:** every page has a **Copy for Claude** button (top right) that copies a compact summary of that page
  plus a coaching prompt; paste it into any Claude chat and ask for teaching points. The same text is saved as
  `docs/coach/season.md` and `docs/coach/match_<id>.md` (`python analyze.py coach`).
- **In Claude Code:** open this repo and say e.g. "refresh and analyze my latest game" - it can run `refresh.py`, read the
  briefs / `data/matches/*.json`, and coach from the real data.

## Publish as a website (GitHub Pages, free)
The site is just the `docs/` folder. In the GitHub repo: **Settings -> Pages -> Build and deployment -> Source: Deploy
from a branch -> Branch `main`, folder `/docs` -> Save**. It appears at
`https://<your-username>.github.io/deadlock-match-analyst/` after a minute. (Free Pages needs a public repo.) The
published pages contain your match data, so only publish if you are happy with that. The map image is Valve's art, so it
is not stored in the repo: the pages load it from the Deadlock API's asset server (and use a local copy if you have run
`analyze.py`).

## How "improving" is measured
Seven habits are measured the same way in every game (`insights.py`): deaths vs your teammates, lane-phase deaths,
being first to die in fights, defensive items by 20:00, time to your first tier-3 item, lane performance vs a typical
duo, and total souls vs the average for your hero. Each is flagged only when clearly off; small stuff is ignored.
The overview compares your first games of the season (baseline) with your latest games and says "need more games"
until there are enough. Win rate is shown for context but is mostly noise over a few games.

## Markdown reports (to paste into Claude)
```bash
python analyst.py                       # latest ranked match -> reports/report_<id>.md
python analyst.py --match 133922932     # a specific match
python analyst.py --calibration         # calibration run, one combined report (+ scorecard)
python analyst.py --calibration --brief # shorter version
python refresh.py --gamedata            # re-download game-file dumps (hash-verified) -> gamedata.json
python refresh.py --benchmarks          # re-download global benchmark tables
```

## Using it for your own account
Set your SteamID3 (the `account_id` in match history) and main hero id (see `gamedata.json` or `/v1/assets/heroes`):
```bash
# PowerShell
$env:DEADLOCK_ACCOUNT_ID = "123456789"; $env:DEADLOCK_MAIN_HERO = "81"; python refresh.py
```
The defaults are the author's own account.

## Files
| file | purpose |
|---|---|
| `analyze.py` | CLI for the dashboards (`match`, `overview`, `all`, `coach`) |
| `watch.py` | polls for a finished match and rebuilds everything automatically |
| `coach.py` | the Markdown briefs for Claude (also behind the "Copy for Claude" buttons) |
| `kpis.py` | turns one match into a compact record + the habit measurements; saved to `data/matches/<id>.json` |
| `insights.py` | the habits (thresholds, advice), per-match key points, focus areas, baseline-vs-recent trends |
| `pages.py` | writes the HTML pages; chart code is in `docs/assets/lib.js` / `lib.css` |
| `api.py` | cached, rate-limited client (descriptive User-Agent, 6s between live requests, stops on long 429s) |
| `analyst.py` | the Markdown report builder (lane curve, deaths, damage types vs items, trends) |
| `extras.py` | economy, fights, enemy items, HP before death, named objectives, scorecard (used by the reports) |
| `benchmarks.py` | compares a game with all ranked games of that hero (hero stats, performance curve, lane curve) |
| `gamedata.py` | builds `gamedata.json` (hero/item names, tiers, item property values) from GameTracking-Deadlock text dumps |
| `refresh.py` | one-command update |
| `names.json` | manual name overrides / item tags |
| `NOTES.md` | decoded data formats, findings, open questions, next steps - **read this to pick up** |

`cache/` (API responses, so you can run offline and skip the strict rate limit), `data/matches/` and `docs/` are
committed. `data/gametracking/` and `reports/` are git-ignored and recreated by the scripts.

## Credits, data sources, and disclaimer
- Match data: the community [Deadlock API](https://deadlock-api.com). Please respect its rate limits (see `NOTES.md`);
  the client here is deliberately slow and caches everything.
- Game data (hero/item names, item values, enum names): text dumps from
  [SteamTracking/GameTracking-Deadlock](https://github.com/SteamTracking/GameTracking-Deadlock), downloaded on demand with
  hash verification and never executed. `gamedata.json` is a small derived table of names and numbers.
- This is an unofficial fan project, not affiliated with or endorsed by Valve. Deadlock and related names are Valve's.
- Licensed under the [MIT License](LICENSE).
