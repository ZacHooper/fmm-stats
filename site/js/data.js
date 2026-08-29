/**
 * Data layer: loading, the rating engine, and match-stat aggregation.
 *
 * The engine matters more than it sounds. A role rating is just SUM(attribute x weight), and
 * the whole weight table is 5 KB, so the app ships attributes plus weights rather than
 * precomputed ratings. That is both smaller than shipping ratings for 7 tactics and strictly
 * more capable: switching tactic, tuning weights, and re-percentiling all happen here, in
 * memory, with no network and no rebuild.
 *
 * The one thing that cannot be computed here is LEVEL. Ability percentiles derive from the
 * game's overall-ability number, and that number never leaves the machine that built the
 * export (house rule). So `lvlLeague` / `lvlGlobal` arrive precomputed per player-position and
 * are the only ability that exists client-side.
 */

export const S = {          // everything loaded, one place
  index: null, core: null, squad: null, positions: null, matches: null,
  all: null,                // lazy: every player in the save, fetched from R2 on demand
  players: new Map(),       // tid -> player (core, then merged with all)
  clubs: new Map(),         // tid -> {tid,name,leagueCid,players}
  leagues: new Map(),       // cid -> {cid,name,nation,reputation,clubs}
  tactics: {}, posRole: {}, fam: { curve: "linear_floor", floor: 0.5 },
  method: null, ours: null, attrs: [],
  matchAgg: new Map(),      // tid -> aggregated match stats (computed once)
};

/** localStorage key for the shortlist write token — one constant so the three places that read
 *  or write it (Recruitment, the profile sheet, Squad) can't drift onto different keys. */
export const SHORTLIST_TOKEN_KEY = "fm_shortlist_token";

const j = async (url) => {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json();
};

function mkPlayer(row, fields, attrNames) {
  const [tid, name, clubTid, dob, value, wage, expiry, attrs, positions] = row;
  return {
    tid, name: name || `#${tid}`, unnamed: !name, clubTid, dob, value, wage, expiry,
    attrs,
    positions: (positions || []).map(([pos, fam, lvlLeague, lvlGlobal]) =>
      ({ pos, fam, lvlLeague, lvlGlobal, role: S.posRole[pos] || pos })),
  };
}

export async function boot() {
  S.index = await j("api/index.json");
  const core = await j("api/core.json");
  S.core = core;
  S.attrs = core.attrs;
  S.tactics = core.tactics;
  S.posRole = core.pos_role;
  S.fam = core.familiarity;
  S.ours = core.ours;
  S.method = S.index.snapshot.default_method;
  for (const c of core.clubs) S.clubs.set(c[0], { tid: c[0], name: c[1] || `#${c[0]}`, leagueCid: c[2], players: c[3] });
  for (const l of core.leagues) {
    S.leagues.set(l[0], { cid: l[0], name: l[1], nation: l[2], reputation: l[3],
      memberCount: l[4], skillIdx: l[5] ?? null, rated: l[6] ?? null, clubs: 0 });
  }
  // `member_count` from the competition record is unreliable — it reads 5 for a 12-team
  // division and 11 for the 20-team Premier League. Counting actual club records is exact
  // (12, 12, 20), so that's what the UI shows. A league can still undercount by clubs whose
  // squad didn't parse; `S.clubs` only holds clubs with at least one player.
  for (const c of S.clubs.values()) {
    const lg = S.leagues.get(c.leagueCid);
    if (lg) lg.clubs++;
  }
  for (const row of core.players) {
    const p = mkPlayer(row, core.fields, core.attrs);
    p.inCore = true;
    S.players.set(p.tid, p);
  }
  return S;
}

/** Squad detail (growth trajectories + career history) — small, so loaded eagerly on demand. */
export async function loadSquad() {
  if (!S.squad) S.squad = await j("api/squad.json");
  return S.squad;
}
export async function loadPositions() {
  if (!S.positions) S.positions = await j("api/positions.json");
  return S.positions;
}
export async function loadMatches() {
  if (!S.matches) {
    S.matches = await j("api/matches.json");
    buildMatchAgg();
  }
  return S.matches;
}

/**
 * Every player in the save (~4 MB, ~1.3 MB over the wire). Deliberately lazy and deliberately
 * NOT in git: it rewrites wholesale each import and minified JSON deltas badly, which is how
 * this repo's history reached 257 MB when the DuckDB stores were committed. It lives in R2 and
 * is streamed by a Pages Function, so only a global search pays for it.
 */
export async function loadAll(onProgress) {
  if (S.all) return S.all;
  const url = S.index.files.all_players || "/api/all";
  onProgress?.("fetching every player in the save (~1.3 MB)…");
  let data;
  try {
    data = await j(url);
  } catch (e) {
    // Local preview has no Function runtime in front of it; fall back to the file on disk.
    data = await j("api/all.json").catch(() => { throw e; });
  }
  for (const row of data.players) {
    if (S.players.has(row[0])) continue;
    S.players.set(row[0], mkPlayer(row, data.fields, data.attrs));
  }
  S.all = data;
  onProgress?.(null);
  return data;
}

/**
 * Just the players named by `tids`, merged into `S.players` — for when only a handful of
 * specific players are needed (e.g. resolving the shortlist's tids) and paying for the full
 * ~1.3 MB `loadAll` would be wasteful. Already-resolved tids (in core, or from a prior call)
 * are skipped. Silently gives up on failure — callers check `S.players.has(tid)` afterwards,
 * so a network hiccup just leaves those rows unresolved rather than breaking the page.
 */
export async function loadPlayersByTid(tids) {
  const need = [...new Set(tids)].filter((t) => t != null && !S.players.has(t));
  if (!need.length) return;
  try {
    const data = await j(`/api/all?tid=${need.join(",")}`);
    for (const row of data.players) {
      if (!S.players.has(row[0])) S.players.set(row[0], mkPlayer(row, data.fields, data.attrs));
    }
  } catch { /* offline or blocked — those tids just stay unresolved */ }
}

/**
 * The shortlist, fresh every call (never cached on `S`) — it's edited from other tabs/devices
 * and is cheap to re-fetch, so staleness would cost more than the extra request. Returns []
 * with no error, both when no device token is saved and when the request fails, so a caller can
 * treat "nothing to show" and "not configured" the same way without a try/catch of its own.
 */
export async function loadShortlist() {
  const token = localStorage.getItem(SHORTLIST_TOKEN_KEY) || "";
  if (!token) return [];
  try {
    const r = await fetch("/api/shortlist", { headers: { "x-fm-token": token } });
    if (!r.ok) return [];
    const d = await r.json();
    return d.entries || [];
  } catch { return []; }
}

// --------------------------------------------------------------------------- ratings
export function famMult(fam) {
  const { curve, floor } = S.fam;
  const f = Math.max(1, Math.min(20, fam || 0));
  if (curve === "proportional") return f / 20;
  if (curve === "tiers") return f >= 18 ? 1 : f >= 15 ? 0.95 : f >= 10 ? 0.85 : f >= 5 ? 0.7 : 0.5;
  return floor + (1 - floor) * (f / 20);
}

/** SUM(attribute x weight); an attribute the role doesn't list weighs 1 (matches the SQL). */
export function rating(attrs, role, method = S.method, weightsOverride = null) {
  const w = weightsOverride || S.tactics[method]?.[role] || {};
  let s = 0;
  for (let i = 0; i < S.attrs.length; i++) {
    const v = attrs[i];
    if (v == null) continue;
    s += v * (w[S.attrs[i].toLowerCase()] ?? 1);
  }
  return s;
}

export function weightOf(attr, role, method = S.method) {
  return S.tactics[method]?.[role]?.[attr.toLowerCase()] ?? 1;
}

/** [{pos, fam, role, rating, eff, lvlLeague, lvlGlobal}] for one player, best-first. */
export function playerRoles(p, method = S.method, weightsOverride = null) {
  return p.positions.map((q) => {
    const r = rating(p.attrs, q.role, method, weightsOverride);
    return { ...q, rating: r, eff: r * famMult(q.fam) };
  }).sort((a, b) => b.eff - a.eff);
}

/** The player's strongest role under the current tactic — his row in any one-row-per-player table. */
export function bestRole(p, method = S.method, minFam = 0, weightsOverride = null) {
  const rs = playerRoles(p, method, weightsOverride).filter((r) => r.fam >= minFam);
  return rs[0] || null;
}

/**
 * Fit percentile: where `value` sits in a pool at the same position. Percentile of the pool
 * BELOW him, which is what the dashboard reports. Needs >= 8 comparators or it's noise.
 */
export function pctile(pool, value) {
  if (!pool || pool.length < 8) return null;
  let below = 0;
  for (const v of pool) if (v < value) below++;
  return Math.round((1000 * below) / pool.length) / 10;
}

/** eff values at `pos` for a set of players — the comparison pool for a fit percentile. */
export function poolAt(players, pos, method = S.method, minFam = 0) {
  const out = [];
  for (const p of players) {
    for (const q of p.positions) {
      if (q.pos !== pos || q.fam < minFam) continue;
      out.push(rating(p.attrs, q.role, method) * famMult(q.fam));
    }
  }
  return out;
}

/** Sorted (desc) [{tid, eff}] for one position from a set of players — the pool a player's
 *  team-rank is read off, whether he's already in it (a squad row ranking itself) or not (a
 *  shortlisted or scouted player asking "where would he slot in if he joined"). */
export function teamPool(players, pos, method = S.method) {
  const out = [];
  for (const p of players) {
    for (const q of p.positions) {
      if (q.pos !== pos) continue;
      out.push({ tid: p.tid, eff: rating(p.attrs, q.role, method) * famMult(q.fam) });
    }
  }
  return out.sort((a, b) => b.eff - a.eff);
}

/** 1-based rank `eff` would occupy inside a teamPool() (ties share the better rank). */
export function rankIn(pool, eff) {
  let rank = 1;
  for (const item of pool) if (item.eff > eff) rank++;
  return rank;
}

/** Position index: eff standardised within position (100 = pool mean, 15 = 1 s.d.), so a
 *  keeper and a striker are comparable — raw role ratings are not (GK~324 vs ST~404). */
export function posIndexer(players, method = S.method) {
  const by = new Map();
  for (const p of players) {
    for (const q of p.positions) {
      const e = rating(p.attrs, q.role, method) * famMult(q.fam);
      if (!by.has(q.pos)) by.set(q.pos, []);
      by.get(q.pos).push(e);
    }
  }
  const stats = new Map();
  for (const [pos, arr] of by) {
    const m = arr.reduce((a, b) => a + b, 0) / arr.length;
    const sd = Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, arr.length - 1));
    stats.set(pos, { m, sd });
  }
  return (pos, eff) => {
    const st = stats.get(pos);
    if (!st || !(st.sd > 0)) return 100;
    return Math.round((100 + (15 * (eff - st.m)) / st.sd) * 10) / 10;
  };
}

// squad_tids (mart.squad_on(phase)-derived), not raw club_tid membership: a loan-in whose
// loaned_in flag stuck in the save still carries clubTid === one of ours in the per-snapshot
// player rows (that row is accurate — the marker really does still list him there), but he is
// not actually on the books. Fall back to the old club_tid test for an older export that
// predates this field, so a stale core.json degrades rather than breaking.
export const isOurs = (p) =>
  S.ours.squad_tids ? S.ours.squad_tids.includes(p.tid) : S.ours.clubs.includes(p.clubTid);
export const ourPlayers = () =>
  S.ours.squad_tids
    ? S.ours.squad_tids.map((t) => S.players.get(t)).filter(Boolean)
    : [...S.players.values()].filter((p) => S.ours.clubs.includes(p.clubTid));
export const clubPlayers = (tid) =>
  [...S.players.values()].filter((p) => p.clubTid === tid);
export const leaguePlayers = (cid) => {
  const tids = new Set([...S.clubs.values()].filter((c) => c.leagueCid === cid).map((c) => c.tid));
  return [...S.players.values()].filter((p) => tids.has(p.clubTid));
};
export const ourLeagueCid = () => S.clubs.get(S.ours.managed_tid)?.leagueCid ?? null;

export function age(dob, asOf) {
  if (!dob) return null;
  const ref = new Date(asOf || S.index.snapshot.phase);
  const d = new Date(dob);
  let a = ref.getFullYear() - d.getFullYear();
  if (ref.getMonth() < d.getMonth() || (ref.getMonth() === d.getMonth() && ref.getDate() < d.getDate())) a--;
  return a;
}

// --------------------------------------------------------------------------- growth
/**
 * Rating change since a player's first snapshot, under the current tactic and at a given
 * role. Recomputed rather than exported because it has to follow the tactic — a player who
 * grew into a different shape gains under one weight-set and not another.
 */
export function growth(tid, role, method = S.method) {
  const t = S.squad?.trajectories?.[String(tid)];
  if (!t || t.length < 2) return null;
  const first = rating(t[0][2], role, method);
  const last = rating(t[t.length - 1][2], role, method);
  return { delta: last - first, from: first, to: last, snapshots: t.length };
}
export function trajectory(tid, role, method = S.method) {
  const t = S.squad?.trajectories?.[String(tid)] || [];
  return t.map(([season, phase, attrs]) => ({ season, phase, value: rating(attrs, role, method) }));
}

// --------------------------------------------------------------------------- match stats
export const MATCH_SUMS = ["goals", "assists", "passA", "passC", "keyPass", "tackA", "tackW",
  "intercept", "headA", "headW", "crossA", "crossC", "dribbles", "shotA", "shotO",
  "mistakes", "yellow"];

/** Display name -> how to derive it. Mirrors db.MATCH_STAT_DEFS so the column vocabulary is
 *  the same one the Streamlit pages use; a second vocabulary would be a second product. */
export const STAT_DEFS = {
  "Apps": (a) => a.apps, "Starts": (a) => a.starts, "Sub": (a) => a.apps - a.starts,
  "Min": (a) => a.min, "Min/gm": (a) => a.apps ? a.min / a.apps : null,
  "Rating": (a) => a.rating,
  "Goals": (a) => a.goals, "Assists": (a) => a.assists, "G+A": (a) => a.goals + a.assists,
  "Key passes": (a) => a.keyPass, "Pass att": (a) => a.passA, "Tackle att": (a) => a.tackA,
  "Shot att": (a) => a.shotA, "Interceptions": (a) => a.intercept, "Dribbles": (a) => a.dribbles,
  "G/90": (a) => per90(a, "goals"), "A/90": (a) => per90(a, "assists"),
  "G+A/90": (a) => a.min ? (90 * (a.goals + a.assists)) / a.min : null,
  "KeyP/90": (a) => per90(a, "keyPass"), "Passes/90": (a) => per90(a, "passA"),
  "Tackles/90": (a) => per90(a, "tackA"), "TackW/90": (a) => per90(a, "tackW"),
  "Int/90": (a) => per90(a, "intercept"), "HeadW/90": (a) => per90(a, "headW"),
  "Shots/90": (a) => per90(a, "shotA"),
  "DefAct/90": (a) => a.min ? (90 * (a.tackW + a.intercept + a.headW)) / a.min : null,
  "G/gm": (a) => perGm(a, "goals"), "A/gm": (a) => perGm(a, "assists"),
  "G+A/gm": (a) => a.apps ? (a.goals + a.assists) / a.apps : null,
  "KeyP/gm": (a) => perGm(a, "keyPass"), "Passes/gm": (a) => perGm(a, "passA"),
  "Tackles/gm": (a) => perGm(a, "tackA"), "TackW/gm": (a) => perGm(a, "tackW"),
  "Int/gm": (a) => perGm(a, "intercept"), "HeadW/gm": (a) => perGm(a, "headW"),
  "Crosses/gm": (a) => perGm(a, "crossA"), "Dribbles/gm": (a) => perGm(a, "dribbles"),
  "Shots/gm": (a) => perGm(a, "shotA"), "SoT/gm": (a) => perGm(a, "shotO"),
  "DefAct/gm": (a) => a.apps ? (a.tackW + a.intercept + a.headW) / a.apps : null,
  "Mistakes/gm": (a) => perGm(a, "mistakes"), "Yellows/gm": (a) => perGm(a, "yellow"),
  "Pass %": (a) => rate(a.passC, a.passA), "Tackle %": (a) => rate(a.tackW, a.tackA),
  "Header %": (a) => rate(a.headW, a.headA), "Cross %": (a) => rate(a.crossC, a.crossA),
  "Shot acc %": (a) => rate(a.shotO, a.shotA), "Conversion %": (a) => rate(a.goals, a.shotA),
};
const per90 = (a, k) => (a.min ? (90 * a[k]) / a.min : null);
const perGm = (a, k) => (a.apps ? a[k] / a.apps : null);
const rate = (n, d) => (d ? (100 * n) / d : null);

export const STAT_PRESETS = {
  "Forward": ["G/90", "A/90", "Shots/90", "Shot acc %", "Conversion %", "SoT/gm", "KeyP/90", "Dribbles/gm"],
  "Winger": ["G/90", "A/90", "KeyP/90", "Crosses/gm", "Cross %", "Dribbles/gm", "Shots/90", "Shot acc %"],
  "Midfielder": ["Passes/90", "Pass %", "KeyP/90", "A/90", "Tackles/gm", "TackW/90", "Int/90", "DefAct/90"],
  "Defender": ["TackW/90", "Tackle %", "Int/90", "HeadW/90", "Header %", "DefAct/90", "Pass %", "Mistakes/gm"],
  "Goalkeeper": ["Pass %", "Passes/90", "Mistakes/gm", "Yellows/gm"],
  "Playing time": ["Apps", "Starts", "Sub", "Min", "Min/gm", "Rating"],
};

export const ATTR_GROUPS = {
  Technical: ["Crossing", "Dribbling", "Shooting", "Passing", "Tackling", "Technique", "Aerial"],
  Mental: ["Aggression", "Creativity", "Decisions", "Leadership", "Movement", "Positioning", "Teamwork"],
  Physical: ["Pace", "Stamina", "Strength"],
  Goalkeeping: ["Agility", "Handling", "Kicking", "Reflexes", "Throwing", "Communication"],
};

/** Aggregate the per-match rows once into per-player totals, keyed by tid. Filterable
 *  re-aggregation (by season/competition) goes through matchRows() instead. */
function buildMatchAgg() {
  S.matchAgg = aggregate(matchRows());
}

export function matchRows(filter = null) {
  const m = S.matches;
  if (!m || !m.player_rows) return [];
  const f = m.player_fields;
  const ix = Object.fromEntries(f.map((n, i) => [n, i]));
  let rows = m.player_rows;
  if (filter) rows = rows.filter((r) => filter(r, ix));
  return rows.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])));
}

export function aggregate(rows) {
  const out = new Map();
  for (const r of rows) {
    let a = out.get(r.tid);
    if (!a) {
      a = { tid: r.tid, apps: 0, starts: 0, min: 0, _rsum: 0, _rn: 0 };
      for (const k of MATCH_SUMS) a[k] = 0;
      out.set(r.tid, a);
    }
    a.apps++;
    if (r.started) a.starts++;
    a.min += r.minutes || 0;
    if (r.rating != null) { a._rsum += r.rating; a._rn++; }
    for (const k of MATCH_SUMS) a[k] += r[k] || 0;
  }
  for (const a of out.values()) a.rating = a._rn ? a._rsum / a._rn : null;
  return out;
}

export function statValue(name, agg) {
  if (!agg) return null;
  const fn = STAT_DEFS[name];
  if (!fn) return null;
  const v = fn(agg);
  return v == null || Number.isNaN(v) ? null : v;
}
