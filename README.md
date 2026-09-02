# rbipercentage.dancykier.com

**RBI Percentage** — every MLB hitter, sortable, with the RBI divided by the opportunity.

| Stat | Formula |
|---|---|
| **RBI%** | `RBI ÷ RISP` |
| **CL%** | `Σ(RBI × LI) ÷ Σ(RISP × LI)` |

`RISP` is every runner in scoring position while he batted, counted one at a time:
second and third on the bases is two, a man on first is none. Every RBI counts in the
numerator, home runs included.

`LI` is the MLB leverage index of that plate appearance — how much that moment swings
the game. A bases-loaded ninth counts several times a blowout.

## Refresh the numbers

```bash
python3 tools/build.py            # ~50 seconds
git commit -am "refresh data" && git push
```

`build.py` takes about 50 seconds: seven league-wide split calls for the season RISP
totals, one play log per hitter for the base state of every plate appearance, and one
`winProbability` call per game for the leverage index. It rewrites the `window.__RBI__` blob inside `index.html`. Nothing else changes.
The site is a single static file with no build step and no dependencies.
