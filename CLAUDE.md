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
`tools/build.py` is the only moving part. Two MLB Stats API calls per player:

1. `people/{id}/stats?stats=playLog&group=hitting&season=YYYY&gameType=R`
   Returns **one split per plate appearance** (the deciding pitch) with
   `stat.play.count.{outs,runnerOn1b,runnerOn2b,runnerOn3b}`. This is what makes the
   exact ROB and 2-out ROB possible — the situational splits API cannot do it.
2. `people/{id}/stats?stats=statSplits&sitCodes=o2,ron&...` for official 2-out RBI/HR.

Gotchas learned building it:
- `sitCode` **`ron2`** ("Runners On - 2 Outs") is listed by `/api/v1/situationCodes`
  but returns an **empty splits array** for hitting. Do not rely on it; that is why the
  2-out denominator comes from the play log instead.
- Base-state splits (`r1,r2,r3,r12,r13,r23,r123`) do sum to the `ron` split, so they are
  a valid cross-check on ROB — but they cannot be crossed with outs.
- The play-log split count equals the official `plateAppearances`; `build.py` asserts it.

## Design
Greenbar-ledger look: paper ground, banded rows, IBM Plex Mono for every figure,
Barlow Condensed for display, Source Serif 4 for prose. Full light and dark palettes are
defined as CSS custom properties on `:root`, then redone for
`@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`. Accent green
`#16674A`/`#2E8B67`, red-pencil `#A33520` for below-average and for reference lines.

Data is inlined as `window.__RBI__` near the bottom of `index.html`, so the page has no
network dependency at runtime except Google Fonts.
