#!/usr/bin/env python3
"""Load past seasons into rbipct_day, one row per hitter per day.

Every stat the page shows is derived from these rows, so a date range is just a
WHERE clause. Raw per-plate-appearance rows (rbipct_pa) are kept for the current
season only — eighteen seasons of them would add ~550 MB to a database that five
other apps share.

    SUPABASE_SERVICE_KEY=... python3 tools/history.py --from 2009 --to 2025
    SUPABASE_SERVICE_KEY=... python3 tools/history.py --from 2014 --to 2014
"""
import argparse, collections, concurrent.futures, datetime, json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import get, paged, API, WP_FIELDS, TEAM_ABBR   # noqa: E402

REST = "https://atqhfbaurrmivjarowco.supabase.co/rest/v1"
KEY = os.environ.get('SUPABASE_SERVICE_KEY') or sys.exit('set SUPABASE_SERVICE_KEY')

FREE_PASS = {'walk', 'intent_walk', 'hit_by_pitch'}
# Everything a rate stat needs, straight off the event.
BASES = {'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}
NOT_AN_AB = FREE_PASS | {'sac_fly', 'sac_bunt', 'sac_fly_double_play',
                         'sac_bunt_double_play', 'catcher_interf', 'batter_interference'}


def post(table, rows, on_conflict, chunk=4000):
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        req = urllib.request.Request(
            f"{REST}/{table}?on_conflict={on_conflict}",
            data=json.dumps(part).encode(),
            headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}',
                     'Content-Type': 'application/json',
                     'Prefer': 'resolution=merge-duplicates,return=minimal'},
            method='POST')
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=240) as r:
                    r.read()
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"    retry {table} chunk {i}: {e}", flush=True)


def season(s):
    t0 = datetime.datetime.now()
    people = {}
    for sp in paged(f"stats=season&group=hitting&season={s}&sportId=1&gameType=R&playerPool=All"):
        if not sp['stat'].get('plateAppearances'):
            continue
        p = sp['player']
        people[p['id']] = dict(player_id=p['id'], name=p['fullName'],
                               team=TEAM_ABBR.get(sp.get('team', {}).get('name', ''), '---'),
                               team_name=sp.get('team', {}).get('name', ''), last_season=s)
    if not people:
        print(f"{s}: no hitters, skipped", flush=True)
        return
    print(f"{s}: {len(people)} hitters", flush=True)

    # base state at the deciding pitch of every plate appearance
    def log(pid):
        d = get(f"{API}/people/{pid}/stats?stats=playLog&group=hitting&season={s}&gameType=R")
        out = []
        for row in (d['stats'][0]['splits'] if d.get('stats') else []):
            play = row['stat']['play']
            if not play['details'].get('isPlateAppearance'):
                continue
            c = play['count']
            out.append(((row['game']['gamePk'], play['atBatNumber'] - 1), row['date'],
                        (1 if c['runnerOn2b'] else 0) + (1 if c['runnerOn3b'] else 0)))
        return out

    risp, dates, done = {}, {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for rows in ex.map(log, list(people)):
            for key, date, n in rows:
                risp[key] = n
                dates[key[0]] = date
            done += 1
            if done % 400 == 0:
                print(f"  {s} play logs {done}/{len(people)}", flush=True)
    print(f"  {s}: {len(risp)} plate appearances over {len(dates)} games", flush=True)

    # leverage index, RBI and the event, one call per game
    agg = collections.defaultdict(lambda: collections.Counter())

    def wp(pk):
        return pk, get(f"{API}/game/{pk}/winProbability?{WP_FIELDS}")

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for pk, plays in ex.map(wp, sorted(dates)):
            for play in plays or []:
                idx = play.get('atBatIndex')
                n = risp.get((pk, idx))
                if n is None:
                    continue
                bid = play.get('matchup', {}).get('batter', {}).get('id')
                if bid not in people:
                    continue
                res = play.get('result') or {}
                ev = res.get('eventType')
                rbi = res.get('rbi') or 0
                li = play.get('leverageIndex')
                li = 1.0 if li is None else float(li)
                free = ev in FREE_PASS
                a = agg[(dates[pk], bid)]
                a['pa'] += 1
                a['rbi'] += rbi
                a['risp'] += n
                a['w_rbi'] += rbi * li
                a['w_risp'] += n * li
                if not free:
                    a['rbi_x'] += rbi
                    a['rispx'] += n
                    a['w_rbix'] += rbi * li
                    a['w_rispx'] += n * li
                if ev not in NOT_AN_AB:
                    a['ab'] += 1
                a['tb'] += BASES.get(ev, 0)
                if ev in BASES:
                    a['h'] += 1
                if ev == 'home_run':
                    a['hr'] += 1
                if ev in ('walk', 'intent_walk'):
                    a['bb'] += 1
                if ev == 'intent_walk':
                    a['ibb'] += 1
                if ev == 'hit_by_pitch':
                    a['hbp'] += 1
                if ev in ('sac_fly', 'sac_fly_double_play'):
                    a['sf'] += 1
            done += 1
            if done % 600 == 0:
                print(f"  {s} leverage {done}/{len(dates)}", flush=True)

    rows = [dict(season=s, game_date=d, batter_id=b,
                 pa=a['pa'], ab=a['ab'], h=a['h'], tb=a['tb'], hr=a['hr'],
                 bb=a['bb'], ibb=a['ibb'], hbp=a['hbp'], sf=a['sf'],
                 rbi=a['rbi'], rbi_x=a['rbi_x'], risp=a['risp'], rispx=a['rispx'],
                 w_rbi=round(a['w_rbi'], 3), w_rbix=round(a['w_rbix'], 3),
                 w_risp=round(a['w_risp'], 3), w_rispx=round(a['w_rispx'], 3))
            for (d, b), a in agg.items()]
    post('rbipct_day', rows, 'game_date,batter_id')
    post('rbipct_name', list(people.values()), 'player_id')
    mins = (datetime.datetime.now() - t0).total_seconds() / 60
    print(f"{s}: wrote {len(rows)} player-days in {mins:.1f} min", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='a', type=int, required=True)
    ap.add_argument('--to', dest='b', type=int, required=True)
    args = ap.parse_args()
    for s in range(args.a, args.b + 1):
        try:
            season(s)
        except Exception as e:
            print(f"{s}: FAILED — {e}", flush=True)


if __name__ == '__main__':
    main()
