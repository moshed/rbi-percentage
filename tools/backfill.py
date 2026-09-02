#!/usr/bin/env python3
"""One-time load of a whole season of plate appearances into Supabase (Misc project).

The daily job only adds new games. Run this once per season, or to repair.

    SUPABASE_SERVICE_KEY=... python3 tools/backfill.py --season 2026
"""
import argparse, concurrent.futures, datetime, json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import get, paged, leaders_pool, TEAM_ABBR, API   # noqa: E402

REF = 'atqhfbaurrmivjarowco'
REST = f"https://{REF}.supabase.co/rest/v1"
KEY = os.environ.get('SUPABASE_SERVICE_KEY') or sys.exit('set SUPABASE_SERVICE_KEY')
WP_FIELDS = "fields=atBatIndex,leverageIndex,result,rbi,matchup,batter,id"


def post(table, rows, on_conflict):
    for i in range(0, len(rows), 4000):
        chunk = rows[i:i + 4000]
        req = urllib.request.Request(
            f"{REST}/{table}?on_conflict={on_conflict}",
            data=json.dumps(chunk).encode(),
            headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}',
                     'Content-Type': 'application/json',
                     'Prefer': 'resolution=merge-duplicates,return=minimal'},
            method='POST')
        with urllib.request.urlopen(req, timeout=180) as r:
            r.read()
        print(f"  {table}: {i + len(chunk)}/{len(rows)}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=datetime.date.today().year)
    args = ap.parse_args()
    s = args.season

    players, tg = leaders_pool(s)
    print(f"{len(players)} hitters")
    post('rbipct_player', [dict(
        season=s, player_id=p['id'], name=p['n'], team=p['t'], team_name=p.get('tn', ''),
        g=p['g'], pa=p['pa'], rbi=p['rbi'], hr=p['hr'], avg=p['avg'], ops=p['ops'],
        qualified=bool(p['q'])) for p in players.values()], 'season,player_id')

    # base state at the deciding pitch of every plate appearance
    def log(p):
        d = get(f"{API}/people/{p['id']}/stats?stats=playLog&group=hitting"
                f"&season={s}&gameType=R")
        out = []
        for row in (d['stats'][0]['splits'] if d['stats'] else []):
            play = row['stat']['play']
            if not play['details'].get('isPlateAppearance'):
                continue
            c = play['count']
            out.append(((row['game']['gamePk'], play['atBatNumber'] - 1), row['date'],
                        (1 if c['runnerOn2b'] else 0) + (1 if c['runnerOn3b'] else 0)))
        return out

    risp, dates, done = {}, {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for rows in ex.map(log, list(players.values())):
            for key, date, n in rows:
                risp[key] = n
                dates[key[0]] = date
            done += 1
            if done % 150 == 0:
                print(f"  play logs {done}/{len(players)}", flush=True)
    print(f"{len(risp)} plate appearances, {len(dates)} games")

    # leverage index and RBI, one call per game
    def wp(pk):
        return pk, get(f"{API}/game/{pk}/winProbability?{WP_FIELDS}")

    out, done = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for pk, plays in ex.map(wp, sorted(dates)):
            for play in plays:
                idx = play.get('atBatIndex')
                n = risp.get((pk, idx))
                if n is None:
                    continue
                bid = play.get('matchup', {}).get('batter', {}).get('id')
                if bid not in players:
                    continue
                li = play.get('leverageIndex')
                out.append(dict(season=s, game_pk=pk, ab_index=idx, game_date=dates[pk],
                                batter_id=bid, risp=n,
                                rbi=play.get('result', {}).get('rbi') or 0,
                                li=1.0 if li is None else float(li)))
            done += 1
            if done % 400 == 0:
                print(f"  leverage {done}/{len(dates)}", flush=True)

    print(f"uploading {len(out)} plate appearances")
    post('rbipct_pa', out, 'game_pk,ab_index')
    print("done")


if __name__ == '__main__':
    main()
