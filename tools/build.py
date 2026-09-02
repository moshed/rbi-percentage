#!/usr/bin/env python3
"""Rebuild rbipercentage.dancykier.com from live MLB Stats API data.

Every hitter in the majors, one row each.

    RBI%  =  RBI / RISP
    CL%   =  sum(RBI x LI) / sum(RISP x LI)

RISP is every runner in scoring position during his plate appearances, counted one
at a time: second and third on the bases is two, a man on first is none. Every RBI
counts in the numerator, home runs included.

LI is the MLB leverage index of that plate appearance, so a bases-loaded ninth
counts for several times a blowout.

    python3 tools/build.py
    python3 tools/build.py --season 2027
"""
import argparse, collections, concurrent.futures, datetime, json, os, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://statsapi.mlb.com/api/v1"

WP_FIELDS = "fields=atBatIndex,leverageIndex,result,rbi,eventType,matchup,batter,id"

# A walk or a hit-by-pitch is not a chance he wasted — he was never given a pitch to
# drive. It only counts when it forced a run in, and then it counts on both sides.
FREE_PASS = {'walk', 'intent_walk', 'hit_by_pitch'}

TEAM_ABBR = {'Arizona Diamondbacks':'ARI','Atlanta Braves':'ATL','Baltimore Orioles':'BAL',
 'Boston Red Sox':'BOS','Chicago Cubs':'CHC','Chicago White Sox':'CWS','Cincinnati Reds':'CIN',
 'Cleveland Guardians':'CLE','Colorado Rockies':'COL','Detroit Tigers':'DET','Houston Astros':'HOU',
 'Kansas City Royals':'KC','Los Angeles Angels':'LAA','Los Angeles Dodgers':'LAD','Miami Marlins':'MIA',
 'Milwaukee Brewers':'MIL','Minnesota Twins':'MIN','New York Mets':'NYM','New York Yankees':'NYY',
 'Athletics':'ATH','Oakland Athletics':'ATH','Philadelphia Phillies':'PHI','Pittsburgh Pirates':'PIT',
 'San Diego Padres':'SD','San Francisco Giants':'SF','Seattle Mariners':'SEA','St. Louis Cardinals':'STL',
 'Tampa Bay Rays':'TB','Texas Rangers':'TEX','Toronto Blue Jays':'TOR','Washington Nationals':'WSH'}


def get(url):
    err = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            err = e
    raise err


def paged(params):
    """Every split of a league-wide query, following the offset pages."""
    out, offset = [], 0
    while True:
        d = get(f"{API}/stats?{params}&limit=1000&offset={offset}")
        splits = d['stats'][0]['splits']
        out += splits
        total = d['stats'][0].get('totalSplits', len(out))
        offset += len(splits)
        if not splits or offset >= total:
            return out


def team_games(s):
    """Games played per team, for the 3.1-PA-per-team-game qualifier."""
    d = get(f"{API}/standings?leagueId=103,104&season={s}&standingsTypes=regularSeason")
    return {t['team']['id']: t.get('gamesPlayed') or 0
            for rec in d['records'] for t in rec['teamRecords']}


def season_rows(s, tg):
    players = {}
    for sp in paged(f"stats=season&group=hitting&season={s}&sportId=1&gameType=R&playerPool=All"):
        st, p = sp['stat'], sp['player']
        if not st.get('plateAppearances'):
            continue
        # MLB's batting qualifier: 3.1 plate appearances per team game.
        games = tg.get(sp.get('team', {}).get('id'), max(tg.values()) if tg else 0)
        players[p['id']] = dict(
            id=p['id'], n=p['fullName'],
            t=TEAM_ABBR.get(sp.get('team', {}).get('name', ''), '---'),
            tn=sp.get('team', {}).get('name', ''),      # searchable full club name
            g=st.get('gamesPlayed', 0), pa=st['plateAppearances'],
            rbi=st.get('rbi', 0), hr=st.get('homeRuns', 0),
            ab=st.get('atBats', 0), bb=st.get('baseOnBalls', 0),
            ibb=st.get('intentionalWalks', 0), hbp=st.get('hitByPitch', 0),
            avg=st.get('avg', '.000'), ops=st.get('ops', '.000'),
            q=1 if st['plateAppearances'] >= 3.1 * games else 0,
            risp=0, rispx=0, wRbi=0.0, wRisp=0.0, wRispx=0.0, liSum=0.0, liPa=0)
    return players


def risp_per_pa(players, s):
    """(gamePk, atBatIndex) -> runners in scoring position, from each hitter's play log.

    The play log is the only place base state and plate appearance meet, and its
    atBatNumber is the winProbability atBatIndex plus one.
    """
    def one(p):
        log = get(f"{API}/people/{p['id']}/stats?stats=playLog&group=hitting"
                  f"&season={s}&gameType=R")
        rows = log['stats'][0]['splits'] if log['stats'] else []
        out = []
        for row in rows:
            play = row['stat']['play']
            # An inning-ending caught stealing logs a row that is not a completed PA.
            if not play['details'].get('isPlateAppearance'):
                continue
            c = play['count']
            out.append((row['game']['gamePk'], play['atBatNumber'] - 1,
                        (1 if c['runnerOn2b'] else 0) + (1 if c['runnerOn3b'] else 0)))
        return out

    risp, games, done = {}, set(), 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for rows in ex.map(one, list(players.values())):
            for pk, idx, n in rows:
                risp[(pk, idx)] = n
                games.add(pk)
            done += 1
            if done % 100 == 0:
                print(f"  play logs {done}/{len(players)}")
    return risp, sorted(games)


def add_leverage(players, risp, games):
    """Weight every plate appearance by the leverage index of that moment."""
    def one(pk):
        return pk, get(f"{API}/game/{pk}/winProbability?{WP_FIELDS}")

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for pk, plays in ex.map(one, games):
            for play in plays:
                idx = play.get('atBatIndex')
                n = risp.get((pk, idx))
                if n is None:                       # not a completed plate appearance
                    continue
                p = players.get(play.get('matchup', {}).get('batter', {}).get('id'))
                if not p:
                    continue
                res = play.get('result', {})
                rbi = res.get('rbi') or 0
                # A walk or hit-by-pitch that drove nobody in is only dropped from the
                # second denominator; the page toggles between the two.
                free = res.get('eventType') in FREE_PASS and rbi == 0
                li = play.get('leverageIndex')
                li = 1.0 if li is None else float(li)
                p['risp'] += n
                p['wRbi'] += rbi * li
                p['wRisp'] += n * li
                if not free:
                    p['rispx'] += n
                    p['wRispx'] += n * li
                p['liSum'] += li
                p['liPa'] += 1
            done += 1
            if done % 250 == 0:
                print(f"  leverage {done}/{len(games)}")


def leaders_pool(s):
    """Every hitter with a plate appearance, plus each team's games played."""
    tg = team_games(s)
    return season_rows(s, tg), tg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=datetime.date.today().year)
    args = ap.parse_args()
    s = args.season

    tg = team_games(s)
    players = season_rows(s, tg)
    print(f"{len(players)} hitters, {sum(p['q'] for p in players.values())} qualified")
    risp, games = risp_per_pa(players, s)
    print(f"{len(risp)} plate appearances across {len(games)} games")
    add_leverage(players, risp, games)
    print("leverage done")

    rows = sorted(players.values(), key=lambda r: -r['rbi'])
    for r in rows:
        r['pct'] = round(r['rbi'] / r['risp'] * 100, 1) if r['risp'] else 0.0
        r['pctx'] = round(r['rbi'] / r['rispx'] * 100, 1) if r['rispx'] else 0.0
        r['pct2'] = round(r['wRbi'] / r['wRisp'] * 100, 1) if r['wRisp'] else 0.0
        r['pct2x'] = round(r['wRbi'] / r['wRispx'] * 100, 1) if r['wRispx'] else 0.0

    qual = [r for r in rows if r['q']]
    # Out of season the leaderboard is empty or nobody has qualified yet. Leave the
    # last good page alone rather than writing a blank one.
    if not rows or not qual or not sum(r.get('risp', 0) for r in qual):
        print(f"nothing to write: {len(rows)} hitters, {len(qual)} qualified — page left as is")
        return

    meta = dict(season=s, updated=str(datetime.date.today()), n=len(rows), qual=len(qual),
                qualPa=round(3.1 * max(tg.values())) if tg else 0,
                avg=round(sum(r['rbi'] for r in qual) / sum(r['risp'] for r in qual) * 100, 1),
                avgx=round(sum(r['rbi'] for r in qual) / sum(r['rispx'] for r in qual) * 100, 1),
                avg2=round(sum(r['wRbi'] for r in qual) / sum(r['wRisp'] for r in qual) * 100, 1),
                avg2x=round(sum(r['wRbi'] for r in qual) / sum(r['wRispx'] for r in qual) * 100, 1))
    for r in rows:
        for k in ('wRbi', 'wRisp', 'wRispx', 'liSum', 'liPa'):
            del r[k]

    blob = json.dumps(dict(meta=meta, players=rows), separators=(',', ':'))
    page = os.path.join(ROOT, 'index.html')
    html = open(page).read()
    html, k = re.subn(r'window\.__RBI__=\{.*?\};',           # lambda: the blob has \u escapes
                      lambda m: 'window.__RBI__=' + blob + ';', html, count=1, flags=re.S)
    if k != 1:
        raise SystemExit('could not find the window.__RBI__ blob in index.html')
    open(page, 'w').write(html)
    print('wrote', page, '·', meta)


if __name__ == '__main__':
    main()
