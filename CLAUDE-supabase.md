# rbi-percentage — Supabase (Misc project)

Project **Misc** `atqhfbaurrmivjarowco`. It is shared with other apps, so **every object
here is prefixed `rbipct_`** — see the house rule in `supabase_misc_shared_project`.

`supabase db push` does not work on Misc. Apply DDL through the Management API with a
`User-Agent` header (a bare request gets a Cloudflare 403 `error code: 1010`):

```bash
TOKEN=$(security find-generic-password -s "Supabase CLI" -w | sed 's/^go-keyring-base64://' | base64 -d)
curl -s -X POST "https://api.supabase.com/v1/projects/atqhfbaurrmivjarowco/database/query" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "User-Agent: supabase-cli/2.98.2" -d '{"query":"..."}'
```

## The shape that matters: `rbipct_day`
**One row per hitter per day, every season since 2009** (Justin Turner's debut year).
Everything the page shows is derived from it, so a date range is a `WHERE` clause.

Eighteen seasons of raw plate appearances would have been ~3.2M rows and ~550 MB on a
project **five other apps share**. The rollup is ~870k rows and ~70 MB and answers the
same questions, because nobody picks a window finer than a day. `rbipct_pa` keeps the raw
rows for the **current season only**.

AVG, OBP and SLG are not stored — they are rebuilt from `h`, `tb`, `ab`, `bb`, `hbp` and
`sf`, which are themselves counted off the `eventType` of each plate appearance. Checked
against the official season figures: they agree to the third decimal.

## Tables

| Object | What it holds |
|---|---|
| `rbipct_pa` | One row per plate appearance: `game_pk, ab_index, game_date, batter_id, risp, rbi, li`. ~158k rows for 2026. PK `(game_pk, ab_index)`. |
| `rbipct_player` | Season totals per hitter, plus the `qualified` flag. |
| `rbipct_season` | `qual_pa` for the season (3.1 × the leading team's games played). |
| `rbipct_day` | **One row per hitter per day, 2009 onward.** The page reads this, through the functions below. |
| `rbipct_name` | Player id to name and most recent club. Names live once, not once per season. |
| `rbipct_slate` | How many games the majors played each day. Lets "qualifying" scale to any window. |
| `rbipct_leaders` / `rbipct_meta` | Older per-season views. Still correct, no longer read by the page. |

## Functions the page calls
| Function | What it does |
|---|---|
| `rbipct_range(d1, d2)` | The leaderboard over any window. Sub-second across a full season, ~1.2 s across three. |
| `rbipct_range_meta(d1, d2)` | League rates over qualified hitters for the same window, plus `qualPa`. |
| `rbipct_team_games(d1, d2)` | Team games in the window, from `rbipct_slate`: `sum(games) * 2 / 30`. Qualifying is `3.1 x` this. |
| `rbipct_seasons(a, b, min_pa)` | **The fast path.** Whole-season windows off the `rbipct_season_agg` materialized view — ~0.3 s across all eighteen seasons. |
| `rbipct_seasons_meta(a, b)` | League rates for a whole-season window. |
| `rbipct_rollup(d1, d2)` | Rebuilds `rbipct_day` from `rbipct_pa` for a window. The daily job calls it after ingest, so the rollup never drifts. |
| `rbipct_refresh_agg()` | Refreshes `rbipct_season_agg`. **The daily job must call this** or the whole-season view keeps serving yesterday. |

Two limits shaped the design, both worth remembering:
- **The `anon` role gets a 3-second statement timeout.** A raw scan of all 860k daily rows
  lands just over it, which is why whole seasons go through the materialized rollup.
- **PostgREST caps a response at 1000 rows**, and the full span has ~7000 hitters. Both
  functions take `min_pa` and filter in Postgres (`-1` means "whatever qualifies for this
  window"), and the page pages through with `?limit=1000&offset=N` until a short page
  comes back. The `Range` header does **not** work on an RPC POST — it is silently
  ignored and you get page one back every time. Use limit/offset.

`rbipct_seasons` also takes `full_seasons boolean`: when true it keeps only the seasons a
hitter qualified in (`rbipct_season_agg.qualified`) and drops the rest whole, and the
qualifier becomes one season's worth rather than the span's.

Both range functions are `POST /rest/v1/rpc/<name>` with `{"d1": "...", "d2": "..."}`.

## Loading a past season
```bash
SUPABASE_SERVICE_KEY=<service_role> python3 tools/history.py --from 2009 --to 2024
```
About 80 seconds a season. Idempotent — the upsert is keyed on `(game_date, batter_id)`.

RLS is on for all three tables with a read-only policy for `anon`, so the page ships the
anon key in plain sight and nobody can write.

## The daily job

`cron.job` **`rbipct-daily`**, `30 11 * * *` UTC (07:30 ET), calls the edge function
`rbipct-refresh` through `pg_net`.

`supabase/functions/rbipct-refresh/index.ts`:

1. Refreshes `rbipct_player` and `rbipct_season` from one league-wide season call plus
   `/standings`.
2. Finds the last `game_date` in `rbipct_pa` and re-ingests from that day forward, so a
   game that finished after the previous run is not missed.
3. For each hitter, one **date-ranged play log** call — `stats=playLog&startDate=&endDate=`
   returns only that window, a handful of rows each. This is the only exact source of base
   state per plate appearance; see the gotchas in `CLAUDE.md`.
4. One `winProbability` call per game for `leverageIndex` and `rbi`, joined on
   `atBatNumber - 1 == atBatIndex`.
5. Upserts into `rbipct_pa`.

Measured: **41 games and 3,179 plate appearances in 2.3 s.** A normal night is ~15 games.

Manual runs:

```bash
ANON=<anon key>
curl -H "Authorization: Bearer $ANON" \
  "https://atqhfbaurrmivjarowco.supabase.co/functions/v1/rbipct-refresh?days=3"
```

`?days=N` forces the last N days; `?date=YYYY-MM-DD` does one day. Both are idempotent —
the upsert is keyed on `(game_pk, ab_index)`.

## After adding a column
PostgREST caches the schema. A fresh column returns `PGRST204 Could not find the '<name>'
column` on write until you nudge it:

```sql
notify pgrst, 'reload schema';
```

Run that right after the `ALTER TABLE`, then re-run the edge function.

## Backfill

`tools/backfill.py` loads a whole season in one go (~3 minutes). Run it once per season:

```bash
SUPABASE_SERVICE_KEY=<service_role> python3 tools/backfill.py --season 2027
```

## How the page uses it

`index.html` ships a baked-in `window.__RBI__` snapshot so it renders instantly and still
works if Supabase is down. On load it fetches `rbipct_leaders` + `rbipct_meta`, swaps them
in, and the footer stamp flips from `offline copy` to `live`. The weekly GitHub Action
exists only to keep that offline copy from going stale.
