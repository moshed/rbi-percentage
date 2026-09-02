# rbipercentage.dancykier.com

**RBI Percentage** — every MLB hitter, sortable, with the RBI divided by the opportunity.

| Stat | Formula |
|---|---|
| **RBI%** | `(RBI − HR) ÷ ROB` |
| **CL%** | `(2-out RBI − 2-out HR) ÷ 2-out ROB` |

`ROB` is every runner standing on base during his plate appearances, counted one at a
time: a man on first is one, bases loaded is three. Home runs come off the top because
that run is the hitter driving himself in — so the numerator is *other people* he sent
home.

## Refresh the numbers

```bash
python3 tools/build.py            # ~20 seconds
git commit -am "refresh data" && git push
```

`build.py` rewrites the `window.__RBI__` blob inside `index.html`. Nothing else changes.
The site is a single static file with no build step and no dependencies.
