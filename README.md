# rbipercentage.dancykier.com

**Who Drives Them In** — the RBI leaderboard, divided by opportunity.

Two stats the page publishes:

| Stat | Formula |
|---|---|
| **DI%** (drive-in rate) | `(RBI − HR) ÷ runners on base when he batted` |
| **CL%** (two-out clutch) | `(2-out RBI − 2-out HR) ÷ runners on base with two outs` |

Subtracting home runs removes the run a hitter drove in with his own legs, so the
numerator counts *other people* he sent home.

## Refresh the numbers

```bash
python3 tools/build.py
git commit -am "refresh data" && git push
```

`build.py` reads every plate appearance of the top-40 RBI men from the MLB Stats API
play log (`stats=playLog`), records the exact base state and out count at the deciding
pitch, and rewrites the `window.__RBI__` blob inside `index.html`. It asserts the play
log count matches the official plate-appearance total before it writes.

The site is a single static `index.html` — no build step, no dependencies.
