#!/usr/bin/env python3
"""Rebuild rbipercentage.dancykier.com from live MLB Stats API data.

Every hitter in the majors, one row each: RBI, the runners he actually had on
base, and RBI% = (RBI - HR) / runners on base.

    python3 tools/build.py
    python3 tools/build.py --season 2027
"""
import argparse, concurrent.futures, datetime, json, os, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://statsapi.mlb.com/api/v1/stats"

# Runners on base for each base state. This is the whole idea of the page.
BASE_STATES = {'r1': 1, 'r2': 1, 'r3': 1, 'r12': 2, 'r13': 2, 'r23': 2, 'r123': 3}

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
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            err = e
    raise err


def paged(params):
    """Every split for a league-wide query, following the offset pages."""
    out, offset = [], 0
    while True:
        d = get(f"{API}?{params}&limit=1000&offset={offset}")
        splits = d['stats'][0]['splits']
        out += splits
        total = d['stats'][0].get('totalSplits', len(out))
        offset += len(splits)
        if not splits or offset >= total:
            return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=datetime.date.today().year)
    args = ap.parse_args()
    s = args.season

    players = {}
    for sp in paged(f"stats=season&group=hitting&season={s}&sportId=1&gameType=R&playerPool=All"):
        st, p = sp['stat'], sp['player']
        if not st.get('plateAppearances'):
            continue
        players[p['id']] = dict(
            id=p['id'], n=p['fullName'],
            t=TEAM_ABBR.get(sp.get('team', {}).get('name', ''), '---'),
            g=st.get('gamesPlayed', 0), pa=st['plateAppearances'], ab=st.get('atBats', 0),
            rbi=st.get('rbi', 0), hr=st.get('homeRuns', 0), h=st.get('hits', 0),
            avg=st.get('avg', '.000'), ops=st.get('ops', '.000'),
            rob=0, paOn=0, rob2=0, paOn2=0, rbi2=0, hr2=0)
    print(f"{len(players)} hitters")

    # One league-wide call per base state instead of one call per player.
    for code, runners in BASE_STATES.items():
        n = 0
        for sp in paged(f"stats=statSplits&sitCodes={code}&group=hitting"
                        f"&season={s}&sportId=1&gameType=R&playerPool=All"):
            p = players.get(sp['player']['id'])
            if not p:
                continue
            pa = sp['stat'].get('plateAppearances') or 0
            p['rob'] += pa * runners
            p['paOn'] += pa
            n += 1
        print(f"  {code}: {n} hitters, {runners} runner(s) each")

    # Two outs. The RBI and HR come from one league-wide split call, but the
    # denominator — runners on base with two outs — cannot be had from the splits
    # API at all: it will not cross base state with out count, and the sitCode
    # "ron2" returns an empty array for hitting. So read the play log per hitter,
    # which gives one row per plate appearance with both the bases and the outs.
    for sp in paged(f"stats=statSplits&sitCodes=o2&group=hitting"
                    f"&season={s}&sportId=1&gameType=R&playerPool=All"):
        p = players.get(sp['player']['id'])
        if p:
            p['rbi2'] = sp['stat'].get('rbi') or 0
            p['hr2'] = sp['stat'].get('homeRuns') or 0

    def two_out_rob(p):
        log = get(f"https://statsapi.mlb.com/api/v1/people/{p['id']}/stats?stats=playLog"
                  f"&group=hitting&season={s}&gameType=R")
        splits = log['stats'][0]['splits'] if log['stats'] else []
        rob2 = pa2 = 0
        for row in splits:
            play = row['stat']['play']
            # An inning-ending caught stealing logs a row that is not a completed PA.
            if not play['details'].get('isPlateAppearance'):
                continue
            c = play['count']
            if c['outs'] == 2:
                n = c['runnerOn1b'] + c['runnerOn2b'] + c['runnerOn3b']
                rob2 += n
                if n:
                    pa2 += 1
        return p['id'], rob2, pa2

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for pid, rob2, pa2 in ex.map(two_out_rob, list(players.values())):
            players[pid]['rob2'] = rob2
            players[pid]['paOn2'] = pa2
            done += 1
            if done % 50 == 0:
                print(f"  play logs {done}/{len(players)}")

    rows = sorted(players.values(), key=lambda r: -r['rbi'])
    for r in rows:
        r['di'] = r['rbi'] - r['hr']                      # runners he drove in
        r['pct'] = round(r['di'] / r['rob'] * 100, 1) if r['rob'] else 0.0
        r['di2'] = r.get('rbi2', 0) - r.get('hr2', 0)     # runners driven in with two outs
        r['pct2'] = round(r['di2'] / r['rob2'] * 100, 1) if r.get('rob2') else 0.0

    qual = [r for r in rows if r['pa'] >= 300]
    meta = dict(season=s, updated=str(datetime.date.today()), n=len(rows),
                avg=round(sum(r['di'] for r in qual) / sum(r['rob'] for r in qual) * 100, 1),
                avg2=round(sum(r['di2'] for r in qual) / sum(r['rob2'] for r in qual) * 100, 1),
                qual=len(qual))

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
