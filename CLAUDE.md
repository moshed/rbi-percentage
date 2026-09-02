# rbi-percentage

Static one-page site at **rbipercentage.dancykier.com**. GitHub Pages, repo `moshed/rbi-percentage`.

## What it is
Moshe's proposed answer to the "RBI is just opportunity" complaint: divide the RBI by
the opportunity. Two rates, both computed from real per-plate-appearance base states:

- **DI%** = `(RBI − HR) ÷ ROB`, where ROB is every runner on base during his plate appearances.
- **CL%** = `(2-out RBI − 2-out HR) ÷ 2-out ROB`.

`RBI − HR` is exact, not an approximation: every home run contains exactly one
self-driven run, so subtracting HR leaves the runners he drove in.

## Data
`tools/build.py` is the only moving part. It runs in about 20 seconds.

**Overall ROB — league-wide, 7 calls total, not one per player.** The `/api/v1/stats`
endpoint accepts `stats=statSplits&sitCodes=<code>&sportId=1&playerPool=All`, which
returns that split for *every* hitter in one paged response. Call it once per base state
and weight the plate appearances by the runners on:

    r1 r2 r3 = 1 runner    r12 r13 r23 = 2    r123 = 3

Those PAs sum exactly to the official `ron` split, so this is not an estimate.

**2-out ROB — one play log per hitter (~650 calls, 8 threads).** There is no way around
it: the splits API will not cross base state with out count, and the sitCode **`ron2`**
("Runners On - 2 Outs") is listed by `/api/v1/situationCodes` but returns an **empty
array** for hitting. So read
`people/{id}/stats?stats=playLog&group=hitting&season=YYYY&gameType=R`, which gives one
row per plate appearance with `stat.play.count.{outs,runnerOn1b,runnerOn2b,runnerOn3b}`.
Filter rows on `details.isPlateAppearance` — an inning-ending caught stealing logs a row
that is not a completed PA. Expect the filtered count to differ from the official PA
total by one or two a season either way; do not assert equality.

2-out RBI and HR come from one league-wide `sitCodes=o2` call.

Gotchas learned building it:
- `sitCode` **`ron2`** ("Runners On - 2 Outs") is listed by `/api/v1/situationCodes`
  but returns an **empty splits array** for hitting. Do not rely on it; that is why the
  2-out denominator comes from the play log instead.
- Base-state splits (`r1,r2,r3,r12,r13,r23,r123`) do sum to the `ron` split, so they are
  a valid cross-check on ROB — but they cannot be crossed with outs.
- The play-log split count equals the official `plateAppearances`; `build.py` asserts it.

## Shape of the page
**One sortable table, nothing else.** Moshe asked for exactly this on 2026-09-02 after a
first version that had a hero, a scatter plot and prose sections — do not add charts,
tiles or essays back unless he asks. Controls are a search box and a Min PA selector
(defaults to 100; the rate column is meaningless on a 12-PA sample).

Every hitter with a plate appearance is included — about 650, all rendered at once.

## Design
Greenbar-ledger look: paper ground, banded rows, IBM Plex Mono throughout,
Barlow Condensed for the heading and player names. Light and dark palettes are both
defined as CSS custom properties on `:root`, then redone for
`@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`. Accent green
`#16674A`, red-pencil `#A33520` marks a rate below the 300+ PA league average.

Data is inlined as `window.__RBI__` near the bottom of `index.html`, so the page has no
network dependency at runtime except Google Fonts.
