# rbi-percentage

Static one-page site at **rbipercentage.dancykier.com**. Repo `moshed/rbi-percentage`.

## Hosting: Cloudflare Pages, project `rbi-percentage`
Moved off GitHub Pages 2026-09-02. GitHub pinned `Cache-Control: max-age=600` with no
purge, so an edit could take ten minutes to appear. Cloudflare serves
`max-age=0, must-revalidate` (set in `dist/_headers`) and deploys in seconds.

**To publish an edit, run `./deploy.sh` — about 7 seconds, no GitHub in the path.**
Push to git separately, for history. The push-triggered workflow is a backstop for
commits that land from somewhere else (the weekly snapshot job runs on GitHub's
machines, so it needs one).

It is **direct upload, not the Git integration** — connecting Pages to GitHub is a
browser OAuth flow only Moshe can click. `.github/workflows/deploy.yml` runs
`wrangler pages deploy dist` on every push instead, which keeps it in step without the
click. Secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are set on the repo.

DNS still lives at Namecheap: `rbipercentage` is a CNAME to `rbi-percentage.pages.dev.`
Repoint it with `python3 /Users/moshe/Apps/spin360/tools/nc_dns.py set-cname <host> <target>`
— a single write, so the host never stops resolving mid-change. The GitHub Pages site and
the repo's `CNAME` file are gone.

## What it is
Moshe's own answer to the "RBI is just opportunity" complaint: divide the RBI by the
chances. Two rates, both from real per-plate-appearance data:

- **RBI%** = `RBI / RISP`
- **CL%** = `sum(RBI x LI) / sum(RISP x LI)`

**Two readings, and the page toggles between them.** `risp` counts every runner in
scoring position. `rispx` keeps only the trips where he got a pitch to swing at: every
`FREE_PASS` event (walk, intentional walk, hit-by-pitch) leaves **both** halves of the
fraction — the forced-in run goes with the runners it was forced from.

It got there in two steps on 2026-09-02, both Moshe's calls. First: drop all walks and a
bases-loaded walk puts an RBI on top with no chance underneath, so the rule keyed on RBI.
Then: a bases-loaded walk caps you at one run out of two chances when you never got to
swing, so the forced run should leave too. The second version is the consistent one —
the plate appearance is either a chance or it isn't. Worth 340 RBI out of 17,850 league
-wide, so nobody moves more than about a point.

**Walks count by default.** The `Walks aren't a chance` checkbox switches to `rispx`.
He set that default deliberately after seeing what excluding walks does: Alvarez leads MLB
with 29 intentional walks, 25 of them with a runner in scoring position, and dropping them
takes him from 62.3% to 93.1% against a 45.6% league. Both views ship; the toggle is the
answer, not a new default.

`RISP` counts runners in scoring position one at a time — second and third is two, a man
on first is none. Every RBI stays in the numerator, home runs included: **do not subtract
home runs.** An earlier version used `(RBI - HR) / all runners on base` and Moshe
rejected it on 2026-09-02 — an RBI that scores a man from first is still an RBI, and a
solo homer is still a run he drove in.

`LI` is the MLB leverage index of that plate appearance — **applied per plate
appearance, never as a season average.** Weighting by it is Moshe's replacement for the
earlier two-out clutch definition. An average-LI column was shown briefly and removed on
2026-09-02: it read as though CL% multiplied by a single average. Do not add it back.

Column headings are centered over their column. The sort arrow and the `?` are both
absolutely positioned inside the heading cell so neither shifts the label. The `?` is
touch-only (`@media (pointer:coarse)`) — on a pointer the hover tooltip covers it. The
tooltip opens **above** the heading so it never sits on top of the numbers.

## Shape of the page
**One sortable table, nothing else.** Moshe asked for exactly this on 2026-09-02 after a
first version that had a hero, a scatter plot and prose sections — do not add charts,
tiles or essays back unless he asks. Controls are a search box and a Min PA selector
(defaults to 100; the rate column is meaningless on a 12-PA sample).

Every hitter with a plate appearance is included — about 650, all rendered at once, each
with an MLB headshot beside the name
(`img.mlbstatic.com/.../w_64,q_auto:best/v1/people/{id}/headshot/67/current`, lazy-loaded,
hidden on error).

The Min PA control defaults to **Qualifying**: MLB's own rule, 3.1 plate appearances per
team game. `build.py` reads each team's `gamesPlayed` from `/api/v1/standings` and stamps
a `q` flag on every player, so the cutoff moves with the season instead of being a guess.

The rank, headshot and name are frozen (`position: sticky; left`) so they survive a
sideways scroll. Their `left` offsets come from `--wrank` / `--wname` on `:root` — change
a column width there, not on the cells, or the two get out of step. Frozen cells must
carry their own background (plain, banded and hover), otherwise scrolled content shows
through them. The name sits in a `.pn` box clamped to two lines inside a fixed 32px
flex row, so it never changes the row height.

`fitName()` measures the widest name currently on screen with a canvas and writes
`--wname` on the container, so the frozen block reserves no space nothing uses. It has to
be measured rather than read off the cell: the cell's width is fixed, so it can never
report its natural one. It re-runs on every draw, on the scroll-state flip, and once
`document.fonts.ready` resolves.

A `scroll` handler puts `.narrow` on the container as soon as `scrollLeft > 4`. That one
class drops the name to 11.5px, breaks it first-name-over-last (`.pn em{display:block}`)
and shrinks `--wname` to 140px, so more of the table fits while you are reading across.
At rest the name is back to one full-size line.

Desktop layout is pinned: `body` does not scroll, the table does, so the column headings
stay visible. Under 820px it falls back to normal page flow with a static heading row.

## Bot links in the footer
The five X handles carry their profile photos, **inlined as base64 JPEG data URIs**, not
hotlinked — unavatar.io rate-limits and would leave holes in the footer. To refresh one:

    curl -sL -o a.img https://unavatar.io/twitter/<handle>   # /x/<handle> if that 403s
    sips -s format jpeg -s formatOptions 72 -Z 44 a.img --out a.jpg
    base64 -i a.jpg          # paste into the <img src="data:image/jpeg;base64,...">

`build.py` only rewrites the `window.__RBI__` blob, so the images survive every refresh.

## Remembered settings
Min PA and the `Walks aren't a chance` checkbox persist in `localStorage` under
`rbipct.controls`. Every read and write is wrapped in try/catch — the accessor itself
throws in a private window or a thumbnail preview, not just returns null. Sort order is
deliberately not stored.

## Design
Greenbar-ledger look: paper ground, banded rows, IBM Plex Mono throughout,
Barlow Condensed for the heading and player names. Light and dark palettes are both
defined as CSS custom properties on `:root`, then redone for
`@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`. Accent green
`#16674A`, red-pencil `#A33520` marks a rate below the 300+ PA league average.

Data is inlined as `window.__RBI__` near the bottom of `index.html`, so the page has no
network dependency at runtime except Google Fonts.

## Qualifying across a multi-season window
**"Qualifying" means he qualified in at least ONE season** — not 3.1 PA per team game
across the whole span. That span rule is ~9,000 plate appearances over eighteen years and
leaves six hitters on the list; Moshe caught it. The Min PA figure shown is one season's
worth (~502) and the other options are fractions of that, so the choice stays meaningful
whatever window is on screen. Over a **single** season the options are fractions of the
qualifier (half, quarter, a tenth) for looking further down the board; over **several**
they are multiples (2x, 4x, 8x), because there a season's worth is the floor rather than
the ceiling — a quarter of one season across eighteen years is noise.

Rates print to **two decimals**. In the band around the league average a tenth of a point
is worth roughly forty places, so one decimal hid real separation.

Two controls, deliberately separate:

| Control | What it decides |
|---|---|
| Min PA / Qualifying | **who appears** on the list |
| `Qualified seasons only` | **which of his seasons count** toward the totals |

With `Qualified seasons only` on, a hitter's part-time years are dropped whole, so a
rookie half-season cannot drag his rate. The `Sn` column shows how many seasons went in,
and appears only when the window spans more than one.
