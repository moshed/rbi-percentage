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

## Tables

| Object | What it holds |
|---|---|
| `rbipct_pa` | One row per plate appearance: `game_pk, ab_index, game_date, batter_id, risp, rbi, li`. ~158k rows for 2026. PK `(game_pk, ab_index)`. |
| `rbipct_player` | Season totals per hitter, plus the `qualified` flag. |
| `rbipct_season` | `qual_pa` for the season (3.1 × the leading team's games played). |
| `rbipct_leaders` | View. One row per hitter with `risp`, `pct` (RBI%) and `pct2` (CL%) already computed. **This is what the page reads.** |
| `rbipct_meta` | View. Pooled league rates over qualified hitters, plus `qualPa` and the last update time. |

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
