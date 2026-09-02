// Daily top-up for rbipercentage.dancykier.com.
//
// The season is already in rbipct_pa (see tools/backfill.py). This only adds the
// games that finished since the last stored date, so a run is a few dozen small
// MLB API calls, not a full rebuild.
//
//   GET /rbipct-refresh            -> catch up from the last stored game date
//   GET /rbipct-refresh?days=3     -> force the last 3 days
//   GET /rbipct-refresh?date=2026-09-01

const API = 'https://statsapi.mlb.com/api/v1'
const WP_FIELDS = 'fields=atBatIndex,leverageIndex,result,rbi,matchup,batter,id'
const SB = Deno.env.get('SUPABASE_URL')!
const KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
const H = { apikey: KEY, Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' }

// Runners in scoring position for each base state. A man on first is worth nothing.
const RISP_BY_STATE: Record<string, number> = { r2: 1, r3: 1, r12: 1, r13: 1, r23: 2, r123: 2 }

const TEAM_ABBR: Record<string, string> = {
  'Arizona Diamondbacks': 'ARI', 'Atlanta Braves': 'ATL', 'Baltimore Orioles': 'BAL',
  'Boston Red Sox': 'BOS', 'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS',
  'Cincinnati Reds': 'CIN', 'Cleveland Guardians': 'CLE', 'Colorado Rockies': 'COL',
  'Detroit Tigers': 'DET', 'Houston Astros': 'HOU', 'Kansas City Royals': 'KC',
  'Los Angeles Angels': 'LAA', 'Los Angeles Dodgers': 'LAD', 'Miami Marlins': 'MIA',
  'Milwaukee Brewers': 'MIL', 'Minnesota Twins': 'MIN', 'New York Mets': 'NYM',
  'New York Yankees': 'NYY', 'Athletics': 'ATH', 'Oakland Athletics': 'ATH',
  'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT', 'San Diego Padres': 'SD',
  'San Francisco Giants': 'SF', 'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL',
  'Tampa Bay Rays': 'TB', 'Texas Rangers': 'TEX', 'Toronto Blue Jays': 'TOR',
  'Washington Nationals': 'WSH',
}

async function json(url: string, tries = 4): Promise<any> {
  let last: unknown
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return await r.json()
      last = new Error(`${r.status} ${url}`)
    } catch (e) { last = e }
    await new Promise((r) => setTimeout(r, 400 * (i + 1)))
  }
  throw last
}

/** Run jobs with a fixed number in flight. */
async function pool<T, R>(items: T[], n: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length)
  let i = 0
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (true) {
      const k = i++
      if (k >= items.length) return
      out[k] = await fn(items[k])
    }
  }))
  return out
}

async function paged(params: string): Promise<any[]> {
  const out: any[] = []
  let offset = 0
  while (true) {
    const d = await json(`${API}/stats?${params}&limit=1000&offset=${offset}`)
    const splits = d.stats?.[0]?.splits ?? []
    out.push(...splits)
    const total = d.stats?.[0]?.totalSplits ?? out.length
    offset += splits.length
    if (!splits.length || offset >= total) return out
  }
}

async function rest(path: string, init?: RequestInit) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { ...H, ...(init?.headers ?? {}) } })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r
}

/** Season totals for every hitter, plus the 3.1-PA-per-team-game qualifier. */
async function refreshPlayers(season: number) {
  const st = await json(`${API}/standings?leagueId=103,104&season=${season}&standingsTypes=regularSeason`)
  const games: Record<number, number> = {}
  for (const rec of st.records ?? []) {
    for (const t of rec.teamRecords ?? []) games[t.team.id] = t.gamesPlayed ?? 0
  }
  const maxG = Math.max(0, ...Object.values(games))

  const rows = (await paged(
    `stats=season&group=hitting&season=${season}&sportId=1&gameType=R&playerPool=All`,
  )).filter((sp) => sp.stat?.plateAppearances).map((sp) => {
    const teamName = sp.team?.name ?? ''
    const g = games[sp.team?.id] ?? maxG
    return {
      season, player_id: sp.player.id, name: sp.player.fullName,
      team: TEAM_ABBR[teamName] ?? '---', team_name: teamName,
      g: sp.stat.gamesPlayed ?? 0, pa: sp.stat.plateAppearances,
      rbi: sp.stat.rbi ?? 0, hr: sp.stat.homeRuns ?? 0,
      avg: sp.stat.avg ?? '.000', ops: sp.stat.ops ?? '.000',
      qualified: sp.stat.plateAppearances >= 3.1 * g,
      updated_at: new Date().toISOString(),
    }
  })
  await rest('rbipct_season?on_conflict=season', {
    method: 'POST',
    body: JSON.stringify([{ season, qual_pa: Math.round(3.1 * maxG), updated_at: new Date().toISOString() }]),
    headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
  })
  for (let i = 0; i < rows.length; i += 500) {
    await rest('rbipct_player?on_conflict=season,player_id', {
      method: 'POST', body: JSON.stringify(rows.slice(i, i + 500)),
      headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
    })
  }
  return rows.map((r) => r.player_id)
}

Deno.serve(async (req) => {
  const t0 = Date.now()
  try {
    const u = new URL(req.url)
    const season = Number(u.searchParams.get('season') ?? new Date().getUTCFullYear())

    // which dates to (re)ingest
    let from: string
    if (u.searchParams.get('date')) {
      from = u.searchParams.get('date')!
    } else if (u.searchParams.get('days')) {
      const d = new Date(); d.setUTCDate(d.getUTCDate() - Number(u.searchParams.get('days')))
      from = d.toISOString().slice(0, 10)
    } else {
      const r = await rest(`rbipct_pa?season=eq.${season}&select=game_date&order=game_date.desc&limit=1`)
      const last = (await r.json())[0]?.game_date
      // Re-do the last stored day: a game can finish after the previous run.
      from = last ?? `${season}-03-01`
    }
    const to = u.searchParams.get('date') ?? new Date().toISOString().slice(0, 10)

    const playerIds = await refreshPlayers(season)

    const sched = await json(
      `${API}/schedule?sportId=1&gameType=R&startDate=${from}&endDate=${to}&fields=dates,date,games,gamePk,status,codedGameState`,
    )
    const gameDate: Record<number, string> = {}
    for (const d of sched.dates ?? []) {
      for (const g of d.games ?? []) {
        if (g.status?.codedGameState === 'F') gameDate[g.gamePk] = d.date
      }
    }
    const pks = Object.keys(gameDate).map(Number)
    if (!pks.length) {
      return Response.json({ ok: true, from, to, games: 0, rows: 0, ms: Date.now() - t0 })
    }

    // Base state at the deciding pitch. The play log is the only exact source, and
    // it takes a date range, so a day's worth is a handful of rows per hitter.
    const risp = new Map<string, number>()
    await pool(playerIds, 24, async (id) => {
      const d = await json(
        `${API}/people/${id}/stats?stats=playLog&group=hitting&season=${season}` +
        `&gameType=R&startDate=${from}&endDate=${to}`,
      )
      for (const sp of d.stats?.[0]?.splits ?? []) {
        const play = sp.stat.play
        if (!play.details?.isPlateAppearance) continue
        const c = play.count
        risp.set(`${sp.game.gamePk}:${play.atBatNumber - 1}`,
          (c.runnerOn2b ? 1 : 0) + (c.runnerOn3b ? 1 : 0))
      }
    })

    // Leverage index and RBI, one call per game.
    const rows: any[] = []
    await pool(pks, 12, async (pk) => {
      const plays = await json(`${API}/game/${pk}/winProbability?${WP_FIELDS}`)
      for (const p of plays ?? []) {
        const key = `${pk}:${p.atBatIndex}`
        if (!risp.has(key)) continue
        const bid = p.matchup?.batter?.id
        if (!bid) continue
        rows.push({
          season, game_pk: pk, ab_index: p.atBatIndex, game_date: gameDate[pk],
          batter_id: bid, risp: risp.get(key), rbi: p.result?.rbi ?? 0,
          li: p.leverageIndex ?? 1.0,
        })
      }
    })

    for (let i = 0; i < rows.length; i += 2000) {
      await rest('rbipct_pa?on_conflict=game_pk,ab_index', {
        method: 'POST', body: JSON.stringify(rows.slice(i, i + 2000)),
        headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
      })
    }

    return Response.json({ ok: true, season, from, to, games: pks.length, rows: rows.length, ms: Date.now() - t0 })
  } catch (e) {
    return Response.json({ ok: false, error: String(e), ms: Date.now() - t0 }, { status: 500 })
  }
})
