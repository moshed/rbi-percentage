# rbi-percentage

Static one-page site at **rbipercentage.dancykier.com**. GitHub Pages, repo `moshed/rbi-percentage`.

## What it is
Moshe's own answer to the "RBI is just opportunity" complaint: divide the RBI by the
chances. Two rates, both from real per-plate-appearance data:

- **RBI%** = `RBI / RISP`
- **CL%** = `sum(RBI x LI) / sum(RISP x LI)`

`RISP` counts runners in scoring position one at a time — second and third is two, a man
on first is none. Every RBI stays in the numerator, home runs included: **do not subtract
home runs.** An earlier version used `(RBI - HR) / all runners on base` and Moshe
rejected it on 2026-09-02 — an RBI that scores a man from first is still an RBI, and a
solo homer is still a run he drove in.

`LI` is the MLB leverage index of that plate appearance. Weighting by it is Moshe's
replacement for the earlier two-out clutch definition.

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
