#!/usr/bin/env python3
"""Refresh rbipercentage.dancykier.com with live MLB data.

Reads every 2026 plate appearance of the top-40 RBI men from the MLB Stats API
play log, scores the exact base state and out count, then rewrites the
window.__RBI__ blob inside ../index.html. Nothing else in the page changes.

    python3 tools/build.py            # current season
    python3 tools/build.py --season 2027
"""
import argparse, concurrent.futures, datetime, json, os, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = 40

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
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            err = e
    raise err


def leaders(season):
    d = get("https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting"
            f"&season={season}&sportId=1&limit={N}&sortStat=rbi")
    out = []
    for s in d['stats'][0]['splits']:
        st, p = s['stat'], s['player']
        out.append(dict(id=p['id'], name=p['fullName'],
                        team=TEAM_ABBR.get(s.get('team', {}).get('name', ''), '---'),
                        pos=s.get('position', {}).get('abbreviation', ''),
                        g=st['gamesPlayed'], pa=st['plateAppearances'],
                        rbi=st['rbi'], hr=st['homeRuns'],
                        avg=st.get('avg'), ops=st.get('ops')))
    return out


def score(pl, season):
    """Exact base state and out count for every plate appearance."""
    log = get(f"https://statsapi.mlb.com/api/v1/people/{pl['id']}/stats?stats=playLog"
              f"&group=hitting&season={season}&gameType=R")
    rob = rob2 = pa_on = pa_on2 = pa_log = risp_pa = 0
    for sp in log['stats'][0]['splits']:
        play = sp['stat']['play']
        # A play log entry is not always a completed plate appearance: an inning-ending
        # caught stealing leaves the batter mid-count and logs a non-PA row.
        if not play['details'].get('isPlateAppearance'):
            continue
        c = play['count']
        pa_log += 1
        n = c['runnerOn1b'] + c['runnerOn2b'] + c['runnerOn3b']
        rob += n
        if n:
            pa_on += 1
        if c['runnerOn2b'] or c['runnerOn3b']:
            risp_pa += 1
        if c['outs'] == 2:
            rob2 += n
            if n:
                pa_on2 += 1

    sp = get(f"https://statsapi.mlb.com/api/v1/people/{pl['id']}/stats?stats=statSplits"
             f"&sitCodes=o2,ron&group=hitting&season={season}&gameType=R")
    sits = {s['split']['code']: s['stat'] for s in sp['stats'][0]['splits']}
    o2 = sits.get('o2', {})
    ron = sits.get('ron', {})

    # Soft checks. The play log is one row per plate appearance, but a handful of
    # plate appearances a season end on an event the log does not flag (an automatic
    # intentional walk, for one), so a difference of one or two is expected.
    if abs(pa_log - pl['pa']) > 3:
        print(f"  WARN {pl['name']}: play log {pa_log} vs official PA {pl['pa']}")
    ron_pa = ron.get('plateAppearances')
    if ron_pa is not None and abs(pa_on - ron_pa) > 3:
        print(f"  WARN {pl['name']}: runners-on PA {pa_on} vs split {ron_pa}")

    di = pl['rbi'] - pl['hr']
    di2 = (o2.get('rbi') or 0) - (o2.get('homeRuns') or 0)
    r = dict(pl)
    r.update(di=di, rob=rob, conv=round(di / rob * 100, 1) if rob else 0,
             rob2=rob2, di2=di2, clutch=round(di2 / rob2 * 100, 1) if rob2 else 0,
             rbi2=o2.get('rbi'), hr2=o2.get('homeRuns'),
             paOn=pa_on, paOn2=pa_on2, rispPa=risp_pa)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=datetime.date.today().year)
    args = ap.parse_args()

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(lambda p: score(p, args.season), leaders(args.season)):
            rows.append(r)
            print('ok', r['name'], r['conv'], '%')

    tot_di = sum(r['di'] for r in rows)
    tot_rob = sum(r['rob'] for r in rows)
    tot_di2 = sum(r['di2'] for r in rows)
    tot_rob2 = sum(r['rob2'] for r in rows)
    for key in ('rbi', 'conv', 'clutch', 'rob'):
        for i, r in enumerate(sorted(rows, key=lambda r: -r[key])):
            r[key + 'Rank'] = i + 1
    for r in rows:
        r['delta'] = r['rbiRank'] - r['convRank']

    meta = dict(season=args.season, updated=str(datetime.date.today()), n=len(rows),
                avgConv=round(tot_di / tot_rob * 100, 1),
                avgClutch=round(tot_di2 / tot_rob2 * 100, 1))
    blob = json.dumps(dict(meta=meta, players=rows), separators=(',', ':'))

    page = os.path.join(ROOT, 'index.html')
    html = open(page).read()
    # lambda, not a replacement string: the JSON blob contains \u escapes.
    html, n = re.subn(r'window\.__RBI__=\{.*?\};', lambda m: 'window.__RBI__=' + blob + ';',
                      html, count=1, flags=re.S)
    if n != 1:
        raise SystemExit('could not find the window.__RBI__ blob in index.html')
    html = re.sub(r'Through [A-Z][a-z]+ \d+', 'Through ' + datetime.date.today().strftime('%B %-d'), html)
    html = re.sub(r'\d{4} Regular Season', f'{args.season} Regular Season', html)
    open(page, 'w').write(html)
    json.dump(dict(meta=meta, players=rows), open(os.path.join(ROOT, 'tools', 'final.json'), 'w'), indent=1)
    print('wrote', page, '·', meta)


if __name__ == '__main__':
    main()
