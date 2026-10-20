# Fantasy Football ROS Rankings Site

Static HTML site (no build step) with three features: rest-of-season rankings, a trade calculator, and a start/sit comparison. Open `index.html` directly in a browser.

## League rules
- 0.5 PPR, plus 0.5 per rushing first down and 0.5 per receiving first down.
- Everything else is assumed standard (4-pt pass TD, 0.04/pass yd, 0.1/rush and rec yd, 6-pt TD, -2 INT, -2 fumble lost). Not confirmed by the user.
- 10 teams, superflex (confirmed by the user). Lineup assumed: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 SUPERFLEX. Not confirmed.
- Replacement ranks are derived in `update_data.py` from TEAMS, LINEUP and FLEX_SPLIT (currently QB 20, RB 26, WR 26, TE 12). Superflex slots are assumed ~85% filled by QBs.
- `QB_TRADE_PREMIUM` (1.3) boosts QB `tradeValue` for the trade calculator only; rankings use pure points-based `value`.
- Only QB/RB/WR/TE are covered (no K or DEF).

## Files
- `index.html`: the whole site (HTML, CSS and JS inline). Reads `window.FF_DATA` from `data/data.js`.
- `update_data.py`: fetches sources, re-scores with league rules, blends, writes `data/data.js`. Python stdlib only. Config (SCORING, TEAMS, LINEUP, FLEX_SPLIT) is at the top.
- `update.bat`: double-click wrapper for the updater.
- `data/data.js`: generated. Do not hand-edit; re-run the updater.
- `assets/logo.svg`: the Pup Fantasy logo (animated SVG: the user's black-and-tan dog leaps and catches a football; also the favicon and the header image in `index.html`). Pure CSS animation, so it runs inside an `<img>`; `prefers-reduced-motion` users see the still catch pose. The lettering is Arial Black converted to outlines, on its own cream banner so it reads on light and dark pages.
- `assets/make_logo.py`: generator for the logo (`python assets/make_logo.py assets/logo.svg`). Needs `pip install fonttools` and Arial Black at `C:/Windows/Fonts/ariblk.ttf`. Edit the dog/animation there, not in the SVG, then regenerate. Optional args: ball end x y, sparkle x y (defaults match the catch point).
- `LOG.md`: running log of the conversation and decisions.

## Data sources
- Rotowire projections via `api.sleeper.com/projections` (the only provider there with real stat lines; others return empty data).
- ESPN projections via `lm-api-reads.fantasy.espn.com` (kona_player_info, `scoringPeriodId` = current week, source 1 / split 1 weekly lines). Stat lines include first downs (ids 212 rush, 213 rec), so they are re-scored with league rules like Rotowire. Stat-id map is `ESPN_STATS` in the script. Capped at 600 players.
- Flock Fantasy via its public JSON API `api.flockfantasy.com/rankings?format=redraft_sf|weekly&pickType=general&year=` (no login; the site is a SPA, endpoint found in its JS bundle). Positional ranks are averaged from the per-expert `positionalRanks`, then mapped to points like FantasyPros. Flock does not state a PPR setting for its redraft board. This API is unofficial and could change.
- FantasyCalc via `api.fantasycalc.com/values/current?isDynasty=false&numQbs=2&numTeams=10&ppr=0.5` (public, no login; params follow `LINEUP`/`TEAMS`/`SCORING`). Trade-market values for ~200 players; its `positionRank` is used as another ROS ranking (mapped to points like FantasyPros). No weekly numbers, so it does not affect start/sit. Its `espnId` also backfills headshots. Because it reflects trade demand (age and upside count), it can differ from pure rest-of-season projections.
- Draft Sharks via the HTMX endpoints behind its ranking pages: `draftsharks.com/ros-rankings/load-table` and `/weekly-rankings/load-table?week=N` (params `pprSuperflexSlug=half-ppr`, `fantasyPosition=<pos>`, `researchDepth=rankings`, `playerGroup=all`; no login). They return HTML; each player is a `<tbody data-player-row>` with `data-player-name`, `data-fantasy-position` and a `<pos-roster-spot>` positional rank, parsed with regex in `draftsharks_pos()`. One call per position (the overall board stops at 250 players). Positional rank is mapped to points like FantasyPros. Scraped HTML, so it can break if their markup changes.
- Yahoo was investigated and NOT used: its ADP/player pages are consent-gated and client-rendered (no player data in the HTML), and its API needs a user OAuth login.
- FantasyPros consensus rankings (per-position ROS half-PPR, plus weekly), scraped from the `ecrData` JSON embedded in the page. Ranks are converted to points via the per-position points curve of the stat-line sources (Rotowire + ESPN averaged), then all available sources are averaged equally per player. Per-position pages are used so points stay format-independent; superflex scarcity is applied afterward through replacement levels.
- The browser can't fetch these directly (CORS), so data refreshes only when the updater runs. `data.js` is a script file, not JSON, so the site works from `file://`.

## Suggested trades tab
- User enters their roster (saved in localStorage under `ff-roster-v1`; "Keep" marks untouchable players). `bestLineup()` fills QB/RB/WR/TE slots, then SUPERFLEX, then FLEX by `ros` points, using `D.league.lineup`.
- `findTrades()` tries 1-for-1, 2-for-1 and 1-for-2 swaps against the top 120 players not on the roster. A trade must be roughly fair in `tradeValue^1.35` terms (get/give between 0.85 and 1.05) and raise the lineup total by at least 5 ROS pts. Top 6 are shown, each target at most once and each given player at most twice. `explain()` writes the reasoning from the lineup diff, value ratio, injuries, byes and source agreement.
- Other teams' rosters are unknown, so this is market-based, not partner-specific.
- "Players you want" (`wants`, persisted with the roster): `findWantTrades()` tries every 1, 2 and 3-player package from the movable roster (zero-trade-value players excluded) against each wanted player and keeps those with get/give in 0.85 to 1.05; picks up to 3 non-overlapping offers ranked by lineup effect (a small penalty per extra player). The lineup effect may be negative and is reported honestly. If nothing is fair, the closest package (ratio 0.6 to 1.4) is shown as "Closest match".
- `bestLineup()` fills an empty slot with replacement-level points (`REPL`, from `D.replacementRank`) instead of 0, so consolidating trades aren't penalized for slots a waiver player could fill.

## Waiver wire tab
- Waiver player = `own` < 50 for RB/WR/TE and `own` < 25 for QB (stricter, because QBs are more valuable in superflex; `WAIVER_MAX_OWNED` in `index.html`). `own` is ESPN `percentOwned`, saved per player by the updater along with `ownChange`), excluding season-ending injury statuses. Players with no ESPN ownership figure are never suggested. ESPN fetch limit is 1000 (covers all QB/RB/WR/TE, ~960 rows).
- Uses the same roster, Keep list and `bestLineup()` as Suggested trades (the roster card renders on both tabs via `drawRosterInto`). `bestLineup(players, key)` can score by `ros` or this week's `wk`.
- `findPickups()`: for each available player, finds the best player to drop. "Lineup upgrade" = lineup total rises by at least 3 ROS pts and the pickup starts; "Bench upgrade" = no lineup change, but the pickup projects 10+ ROS pts more than a bench player at the same position. Top 6, each drop used once. A "Best available" list (top 15 by value over replacement, `vor`, filter by position) is always shown.

## League settings tab (top right of the tab bar)
- The updater ships raw inputs and the page does the scoring: each player has stat-line totals `sr` (Rotowire ROS), `se` (ESPN ROS), `sw`/`ew` (this week's lines) plus the sources' positional ranks (`fpRosRank`, `flockRosRank`, `calcRosRank`, `dsRosRank`, and weekly `fpWkRank`, `flockWkRank`, `dsWkRank`). `D.scoring` (all `STAT_KEYS` + `te_rec_bonus`), `D.league`, `D.flexSplit`, `D.benchBuffer` are the defaults.
- `recompute()` in `index.html` re-scores stat lines, rebuilds the per-position rank-to-points curves, blends all sources, sets replacement levels from teams/lineup/flex shares, and sets `ros`, `rosRoto`..., `wk`, `posRank`, `vor`, `value`, `tradeValue`, `rank`, `deep` in place on the `P` objects. It mirrors the Python build exactly (so Python's own output equals the page's result under the default settings). `applySettings()` then redraws every tab. If you change blending logic, change BOTH `update_data.py` and `recompute()`.
- `deep` = rank-only player (no stat line) far below replacement level; hidden from rankings and waivers, kept in the data so a settings change can bring them back.
- The form edits a `draft`; nothing recalculates until the user clicks **Save settings** (`saveDraft()`: copies the draft into `S`, `saveSettings()`, `applySettings()`). The sticky save bar also has Discard changes and Reset to my league defaults (which only loads defaults into the draft; Save applies them). The tab label shows a dot while there are unsaved changes.
- Settings persist in localStorage `ff-settings-v1` (`{v, settings:{teams, lineup, scoring, qbPremium}}`); untouched defaults are not stored (the key is removed) so new defaults apply. Reset button restores the defaults from `data.js`.
- Rank-only sources (FantasyPros, Flock, FantasyCalc, Draft Sharks) are fixed-format rankings; they follow the settings only through the points curve of the stat-line sources.

## Daily refresh
- A Windows scheduled task `FantasyRankingsDailyUpdate` runs `update_scheduled.bat` (which runs `update_data.py` and saves the last run's output to `data/update.log`) every day at 9:00 AM by the PC clock, which is set to Pacific time (DST handled by Windows). `StartWhenAvailable` runs it when the PC is next on if 9 AM was missed; it needs the network and an interactive logon.
- Created by `schedule_update.ps1` (re-run it to recreate). Remove: `Unregister-ScheduledTask -TaskName FantasyRankingsDailyUpdate -Confirm:$false`. Check: `Get-ScheduledTaskInfo -TaskName FantasyRankingsDailyUpdate`.
- The page reads `data.js` when it loads, so an open tab needs a reload to show new data. It shows a notice if the data is more than 30 hours old.
- Python path is hard-coded in `update_scheduled.bat` (`C:\Python314\python.exe`, falls back to `python`).

## Source safety net (update_data.py)
- Every source goes through `load_source()`: the result is validated (minimum player counts per source/position), saved as a last-good copy in `data/cache/*.pkl`, and if the live fetch fails or fails validation the saved copy is used (max `MAX_CACHE_DAYS` = 10 days old; saved weekly ranks are dropped if from a different week). With no usable copy the source is left out. Saved stat-line copies are filtered to weeks >= the current week.
- Outcomes are written to `data.js` as `sourceStatus` (ok / cached / missing) and the page shows a banner for anything not ok.
- The build aborts without touching `data.js` if fewer than `MIN_SOURCES` (3) work or neither Rotowire nor ESPN is available. `data.js` is written via a temp file + atomic replace.
- The scrapers raise specific errors (e.g. Draft Sharks "markup probably changed") so the failure message says what broke. When adding a source, wrap it with `src(...)` in `build()` and give it a validator.

## Hosting (GitHub Pages) and the daily GitHub job
- Live at https://nferencko.github.io/Pup_Fantasy/ (repo `nferencko/Pup_Fantasy`, Pages source: branch `main`, root). `data/data.js` is committed so the site works; `data/cache/` is not.
- `.github/workflows/update-data.yml` runs `update_data.py` daily starting 9 AM Pacific (two UTC crons, 16:00 and 17:00, both always run; no hour gate because GitHub starts scheduled jobs 1-2 hours late and a gate skipped every update) and commits `data/data.js` when it changes; it can also be run by hand from the Actions tab. If the data sources block GitHub's servers the job fails and the last snapshot stays up (the page shows a stale-data notice after 30 hours).
- The local Windows scheduled task (`FantasyRankingsDailyUpdate`) still updates the local copy only; pull before pushing local data to avoid conflicts, or just let GitHub own `data/data.js`.

## Look and feel
- Palette comes from the logo (all CSS variables in `:root`, with a matching dark set under `prefers-color-scheme: dark`): cream page (`--bg`) and cards, navy ink/hero band (`--hero`), burnt-orange accent (`--accent`, buttons/pressed chips) and a brighter orange stripe (`--stripe`: top bar, active tab underline), tan, and collar-blue for WR/meter. Position tag colours: QB brick red, RB green, WR blue, TE brown, all with white text.
- The header is a full-width navy band (`box-shadow` + `clip-path` trick) so the cream logo badge stands out. If you change the palette, keep the logo's cream (`#f6e6c8`), orange (`#e08a2c`) and navy (`#1d2433`) in mind (they are fixed inside `assets/logo.svg`).

## Conventions
- Scraped names are inserted with `textContent` (the `h()` helper), never `innerHTML`.
- Match existing style: compact vanilla JS, CSS variables with dark-mode support.

## Log
Keep `LOG.md` up to date. At the end of each exchange, append a dated entry: what the user asked, what was done, and any decisions or open questions. Summarize; don't paste full transcripts.
