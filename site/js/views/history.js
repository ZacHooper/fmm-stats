/**
 * History — the club's own story: season progression, records, the Hall of Fame, and the
 * awards roll.
 *
 * Its own section rather than a tab on Matches, because Matches answers "how are we playing"
 * and this answers "what have we done". Everything is computed in the browser from the same
 * match rows, so a new superlative is a few lines here rather than an exporter change.
 *
 * Only the managed club's matches are richly parsed, so these are OUR records — not the
 * league's. And match detail lives in a ring buffer the game overwrites as a season runs, so a
 * long-ago game may simply not be in the save any more.
 *
 * Some winners here — especially in the Hall of Fame, which spans a player's whole time at the
 * club — are no longer on the current squad. `D.matchName`/`D.hasProfile` cover that: a
 * departed player still gets a real name (matches.json's `player_names`, resolved for anyone
 * who ever played for us) but his row isn't clickable, since there's no profile left to open.
 */
import * as D from "../data.js";
import { el, num, pill, DASH } from "../ui.js";
import { openProfile } from "../profile.js";

export async function view() {
  const M = await D.loadMatches();
  await D.loadSquad();
  if (!M.matches?.length) {
    return el("div.card", {}, [el("b", { text: "No matches parsed" }), el("p.note", { text: M.note })]);
  }
  const f = M.match_fields;
  const matches = M.matches.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])))
    .filter((m) => !/friend/i.test(m.competition || ""));
  const rows = D.matchRows();
  const seasons = [...new Set(matches.map((m) => m.season))].sort((a, b) => b - a);
  const oppName = (m) => m.opponent || `#${m.opp_tid}`;

  const out = el("div");
  out.append(el("h2", { text: "History" }));

  // ---------------------------------------------------------------- progression
  out.append(el("h3", { text: "Season by season" }));
  const prog = seasons.map((s) => {
    const ms = matches.filter((m) => m.season === s);
    const snap = D.S.index.snapshots.filter((x) => x.season === s);
    return {
      season: s, p: ms.length,
      w: ms.filter((m) => m.result === "W").length,
      d: ms.filter((m) => m.result === "D").length,
      l: ms.filter((m) => m.result === "L").length,
      gf: ms.reduce((a, m) => a + (m.gf || 0), 0),
      ga: ms.reduce((a, m) => a + (m.ga || 0), 0),
      ppg: ms.length ? ms.reduce((a, m) => a + (m.pts || 0), 0) / ms.length : null,
      comps: [...new Set(ms.map((m) => m.competition))].filter(Boolean),
      snaps: snap.length,
    };
  });
  out.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Season", "P", "W", "D", "L", "GF", "GA", "GD", "Pts/gm", "Competitions", "Snapshots"]
      .map((h, i) => el(`th${i && i < 9 ? ".num" : i === 10 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, prog.map((r) => el("tr", {}, [
      el("td.name", { text: r.season }), el("td.num", { text: r.p }), el("td.num", { text: r.w }),
      el("td.num", { text: r.d }), el("td.num", { text: r.l }), el("td.num", { text: r.gf }),
      el("td.num", { text: r.ga }),
      el("td.num", { text: (r.gf - r.ga >= 0 ? "+" : "") + (r.gf - r.ga) }),
      el("td.num", { text: r.ppg == null ? DASH : num(r.ppg, 2) }),
      el("td", { text: r.comps.join(", ") || DASH }),
      el("td.num", { text: r.snaps }),
    ]))),
  ])]));
  out.append(el("p.note", {
    text: "Friendlies excluded. Counts come from the newest snapshot of each season and can fall "
      + "short of the true fixture list — match detail sits in a fixed-size ring buffer the game "
      + "overwrites as a season runs, so treat a short season as missing games, not lost ones.",
  }));

  // ---------------------------------------------------------------- Hall of Fame
  out.append(el("h3", { text: "Hall of Fame" }));
  out.append(el("p.note", {
    text: "Career totals across every parsed match, all seasons combined — including players "
      + "no longer at the club.",
  }));
  const aggPool = [...D.S.matchAgg.values()];
  const topAgg = (fn, n = 10) => aggPool.map((a) => ({ tid: a.tid, v: fn(a) }))
    .filter((x) => x.v != null && Number.isFinite(x.v) && x.v > 0)
    .sort((a, b) => b.v - a.v).slice(0, n);
  const topRatingAgg = (n = 10) => aggPool.filter((a) => a.apps >= 10)
    .map((a) => ({ tid: a.tid, v: a.rating })).filter((x) => x.v != null)
    .sort((a, b) => b.v - a.v).slice(0, n);
  const topHatTricks = (n = 10) => {
    const m = new Map();
    for (const r of rows) if (r.goals >= 3) m.set(r.tid, (m.get(r.tid) || 0) + 1);
    return [...m.entries()].map(([tid, v]) => ({ tid, v })).sort((a, b) => b.v - a.v).slice(0, n);
  };
  const hofTable = (title, list, dp = 0) => list.length ? el("div", {}, [
    el("h4", { text: title }),
    el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["#", "Player", "Value"].map((h, i) =>
        el(`th${i === 2 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, list.map((x, i) => playerRow(x.tid, [
        el("td.num", { text: i + 1 }), el("td.name", { text: D.matchName(x.tid) }),
        el("td.num", { text: num(x.v, dp) }),
      ]))),
    ])]),
  ]) : null;
  out.append(el("div.grid2", {}, [
    hofTable("Most Appearances", topAgg((a) => a.apps)),
    hofTable("Top Scorer", topAgg((a) => a.goals)),
    hofTable("Most Assists", topAgg((a) => a.assists)),
    hofTable("Most Goal Involvements", topAgg((a) => a.goals + a.assists)),
    hofTable("Most Minutes Played", topAgg((a) => a.min)),
    hofTable("Highest Average Rating (min 10 apps)", topRatingAgg(), 2),
    hofTable("Most Hat-tricks", topHatTricks()),
  ].filter(Boolean)));

  // ---------------------------------------------------------------- team records (all-time, single match)
  out.append(el("h3", { text: "Team records" }));
  const byMargin = [...matches].sort((a, b) => (b.gf - b.ga) - (a.gf - a.ga));
  const recs = [
    ["Biggest win", byMargin[0]],
    ["Heaviest defeat", byMargin[byMargin.length - 1]],
    ["Most goals scored", [...matches].sort((a, b) => b.gf - a.gf)[0]],
    ["Most conceded", [...matches].sort((a, b) => b.ga - a.ga)[0]],
  ].filter(([, m]) => m);
  out.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Record", "Score", "Opponent", "H/A", "Competition", "Date"]
      .map((h, i) => el(`th${i === 1 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, recs.map(([label, m]) => el("tr", {}, [
      el("td.name", { text: label }),
      el("td.num", { text: `${m.gf}–${m.ga}` }),
      el("td", { text: oppName(m) }),
      el("td", { text: m.venue }), el("td", { text: m.competition || DASH }),
      el("td", { text: String(m.date).slice(0, 10) }),
    ]))),
  ])]));

  // longest runs, in date order
  const chron = [...matches].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const runs = { unbeaten: streak(chron, (m) => m.result !== "L"), wins: streak(chron, (m) => m.result === "W"),
    winless: streak(chron, (m) => m.result !== "W"), cleanSheets: streak(chron, (m) => m.ga === 0) };
  out.append(el("div.kpis", {}, [
    kpi("Longest unbeaten", runs.unbeaten.len), kpi("Longest win run", runs.wins.len),
    kpi("Longest winless", runs.winless.len), kpi("Clean sheets in a row", runs.cleanSheets.len),
  ]));

  // ---------------------------------------------------------------- player records (all-time, single match)
  out.append(el("h3", { text: "Player records" }));
  const single = (key, label, dp = 0) => {
    const best = rows.filter((r) => r[key] != null).sort((a, b) => b[key] - a[key])[0];
    return best ? { label, who: best.tid, value: num(best[key], dp),
      when: `${String(best.date).slice(0, 10)} · ${best.competition || ""}` } : null;
  };
  const singles = [
    single("goals", "Most goals in a match"), single("assists", "Most assists in a match"),
    single("rating", "Highest match rating", 2), single("keyPass", "Most key passes"),
    single("tackW", "Most tackles won"), single("intercept", "Most interceptions"),
    single("passC", "Most completed passes"), single("dribbles", "Most dribbles"),
  ].filter(Boolean);
  out.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Record", "Player", "Value", "When"].map((h, i) =>
      el(`th${i === 2 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, singles.map((s) => playerRow(s.who, [
      el("td.name", { text: s.label }), el("td", { text: D.matchName(s.who) }),
      el("td.num", { text: s.value }), el("td", { text: s.when }),
    ]))),
  ])]));

  // ---------------------------------------------------------------- awards per season
  out.append(el("h3", { text: "Awards" }));
  const seasonSel = el("select.btn");
  for (const s of seasons) seasonSel.append(el("option", { value: String(s), text: String(s) }));
  const sillyToggle = el("label", {}, [
    el("input", { type: "checkbox", checked: true }), " Show silly awards",
  ]);
  const sillyBox = sillyToggle.querySelector("input");
  const awards = el("div");
  seasonSel.addEventListener("change", () => drawAwards(Number(seasonSel.value)));
  sillyBox.addEventListener("change", () => drawAwards(Number(seasonSel.value)));
  out.append(el("div.tbar", {}, [seasonSel, sillyToggle]), awards);

  function drawAwards(s) {
    const sm = matches.filter((m) => m.season === s);
    const items = seasonPlayerAwards(rows, matches, s);
    const list = sillyBox.checked ? items : items.filter((a) => !a.silly);
    const team = seasonTeamAwards(sm);
    const games = sm.length;
    const minApps = Math.max(3, Math.round(games * 0.3));
    awards.replaceChildren(
      el("h4", { text: "Player awards" }),
      el("div.scroll", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Award", "Winner", "Figure", "Decided by"].map((h, i) =>
          el(`th${i === 2 ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, list.map((a) => playerRow(a.who, [
          el("td.name", {}, [a.label, a.silly ? pill("silly", "flat") : null]),
          el("td", { text: D.matchName(a.who) }),
          el("td.num", { text: a.value }), el("td.dim", { text: a.note }),
        ]))),
      ])]),
      el("p.note", {
        text: `Season ${s}: ${games} parsed matches, minimum ${minApps} appearances to qualify — `
          + "the bar scales with games played so a two-game cameo can't win anything. "
          + "Appearances count substitutes, not just starts.",
      }),
      el("h4", { text: "Team awards" }),
      team.length ? teamAwardsTable(team) : el("p.note", { text: "No managed-club matches this season." }),
    );
  }
  drawAwards(seasons[0]);

  // ---------------------------------------------------------------- roll of honour (all years)
  out.append(el("h3", { text: "Roll of honour" }));
  out.append(el("p.note", { text: "Every award's winner across all seasons — the club's honours board." }));
  const seasonsAsc = [...seasons].sort((a, b) => a - b);
  out.append(honoursTable("Player awards", seasonsAsc, (s) =>
    seasonPlayerAwards(rows, matches, s).map((a) => [a.label, `${D.matchName(a.who)} — ${a.value}`])));
  out.append(honoursTable("Team awards", seasonsAsc, (s) =>
    seasonTeamAwards(matches.filter((m) => m.season === s)).map((a) => [a.label, `${a.value} — ${a.note}`])));

  out.append(el("p.note", { text: M.note }));
  return out;
}

/** A table row for a player, clickable only when a profile actually exists to open — a row
 *  resolved solely through matches.json's `player_names` fallback has no profile behind it. */
function playerRow(tid, cells) {
  return D.hasProfile(tid)
    ? el("tr.click", { onclick: () => openProfile(tid) }, cells)
    : el("tr", {}, cells);
}

/** Every player award for one season — the full list, including silly ones (the interactive
 *  view filters those with a toggle; the Roll of Honour always shows everything, same as the
 *  dashboard's default). Shared by the per-season display and the all-years matrix. */
function seasonPlayerAwards(rows, matches, s) {
  const sr = rows.filter((r) => r.season === s);
  if (!sr.length) return [];
  const agg = D.aggregate(sr);
  const games = new Set(sr.map((r) => String(r.date))).size;
  const minApps = Math.max(3, Math.round(games * 0.3));
  const pool = [...agg.values()].filter((a) => a.apps >= minApps);
  const top = (fn, label, dp = 2, note = "", silly = false) => {
    const best = pool.map((a) => ({ a, v: fn(a) })).filter((x) => x.v != null && Number.isFinite(x.v))
      .sort((x, y) => y.v - x.v)[0];
    return best ? { label, who: best.a.tid, value: num(best.v, dp), note, silly } : null;
  };

  // Young Gun: age at the season's last new year, the same cutoff the registration rules use.
  const ageAt = (tid) => D.age(D.S.players.get(tid)?.dob, `${s}-01-01`);

  // Hat-trick Hero: best single-game goal haul this season.
  const hattrick = sr.filter((r) => r.goals >= 1).sort((a, b) => b.goals - a.goals)[0];
  const hattrickAward = hattrick ? {
    label: "Hat-trick Hero", who: hattrick.tid, value: num(hattrick.goals),
    note: `vs ${D.S.clubs.get(hattrick.opponent_tid)?.name || `#${hattrick.opponent_tid}`} · `
      + `${String(hattrick.date).slice(0, 10)}`,
  } : null;

  // Golden Glove: GK starts in a game that finished as a clean sheet (ga from the team's own
  // match rows, joined by date — the same technique the dashboard uses).
  const gaByDate = new Map(matches.filter((m) => m.season === s).map((m) => [String(m.date), m.ga]));
  const csCount = new Map();
  for (const r of sr) {
    if (r.position !== "GK" || !r.started) continue;
    if (gaByDate.get(String(r.date)) === 0) csCount.set(r.tid, (csCount.get(r.tid) || 0) + 1);
  }
  const glove = [...csCount.entries()].sort((a, b) => b[1] - a[1])[0];
  const goldenGlove = glove ? { label: "Golden Glove", who: glove[0], value: num(glove[1]),
    note: "clean sheets started" } : null;

  // Supersub: goals+assists in matches he didn't start.
  const subAgg = D.aggregate(sr.filter((r) => !r.started));
  const bestSub = [...subAgg.values()].map((a) => ({ a, v: a.goals + a.assists }))
    .filter((x) => x.v > 0).sort((x, y) => y.v - x.v)[0];
  const superSub = bestSub ? { label: "Supersub", who: bestSub.a.tid, value: num(bestSub.v),
    note: "goals+assists off the bench" } : null;

  return [
    top((a) => a.rating, "Player of the season", 2, "highest average match rating"),
    top((a) => (ageAt(a.tid) != null && ageAt(a.tid) <= 21 ? a.rating : null),
      "Young Gun (U21)", 2, "highest average rating, U21"),
    top((a) => a.goals, "Golden boot", 0, "most goals"),
    hattrickAward,
    top((a) => a.assists, "Playmaker", 0, "most assists"),
    top((a) => a.keyPass, "The Maestro", 0, "most key passes"),
    top((a) => a.crossC, "The Crosser", 0, "most crosses completed"),
    top((a) => a.headW, "Aerial Dominator", 0, "most headers won"),
    top((a) => a.dribbles, "Quick Feet", 0, "most dribbles"),
    top((a) => (a.min ? (90 * a.goals) / a.min : null), "Most lethal", 2, "goals per 90"),
    top((a) => (a.passA ? (100 * a.passC) / a.passA : null), "Metronome", 0, "pass completion %"),
    top((a) => a.tackW + a.intercept + a.headW, "Destroyer", 0, "tackles won + interceptions + headers won"),
    goldenGlove,
    top((a) => (a.shotA >= 10 ? (100 * a.goals) / a.shotA : null), "Deadeye", 0,
      "shots -> goals %, min 10 shots"),
    top((a) => a.min, "Iron man", 0, "most minutes"),
    superSub,
    top((a) => (a.apps ? a.mistakes / a.apps : null), "Butterfingers", 2,
      "mistakes per game — the one you don't want", true),
    top((a) => (a.apps ? a.yellow / a.apps : null), "Most booked", 2, "yellows per game", true),
    top((a) => (a.shotA >= 10 && a.goals === 0 ? a.shotA : null), "Wasteful", 0,
      "most shots without scoring (10+ shots)", true),
  ].filter(Boolean);
}

/** Team-level awards for one season's matches — mirrors dashboard/pages/11_Awards.py's
 *  TEAM_AWARDS, built from columns already in matches.json (our_/opp_ pairs, venue, result, date). */
function seasonTeamAwards(sm) {
  if (!sm.length) return [];
  const t = sm.map((m) => ({
    ...m,
    margin: (m.gf ?? 0) - (m.ga ?? 0),
    total: (m.gf ?? 0) + (m.ga ?? 0),
    passpct: m.our_passes >= 100 ? (100 * m.our_passes_completed) / m.our_passes : null,
  }));
  const W = t.filter((m) => m.result === "W").length;
  const Dd = t.filter((m) => m.result === "D").length;
  const L = t.filter((m) => m.result === "L").length;
  const gf = t.reduce((a, m) => a + (m.gf || 0), 0);
  const ga = t.reduce((a, m) => a + (m.ga || 0), 0);
  const ppg = (3 * W + Dd) / t.length;

  const mrow = (key, fmt, filterFn = null) => {
    let d = t.filter((m) => m[key] != null);
    if (filterFn) d = d.filter(filterFn);
    if (!d.length) return null;
    const r = [...d].sort((a, b) => b[key] - a[key])[0];
    return { value: fmt(r), note: `vs ${r.opponent || `#${r.opp_tid}`} · ${String(r.date).slice(0, 10)} (${r.venue})` };
  };
  const rec = (x) => {
    if (!x.length) return null;
    const w = x.filter((m) => m.result === "W").length;
    const d = x.filter((m) => m.result === "D").length;
    const l = x.filter((m) => m.result === "L").length;
    return { value: `${w}W ${d}D ${l}L`, note: `${((3 * w + d) / x.length).toFixed(2)} PPG (${x.length} games)` };
  };
  const chron = [...t].sort((a, b) => String(a.date).localeCompare(String(b.date)));

  const byMonth = new Map();
  for (const m of t) {
    const ym = String(m.date).slice(0, 7);
    if (!byMonth.has(ym)) byMonth.set(ym, []);
    byMonth.get(ym).push(m);
  }
  let bestMonth = null;
  for (const [ym, ms] of byMonth) {
    if (ms.length < 2) continue;
    const w = ms.filter((m) => m.result === "W").length;
    const d = ms.filter((m) => m.result === "D").length;
    const l = ms.filter((m) => m.result === "L").length;
    const ppgM = (3 * w + d) / ms.length;
    if (!bestMonth || ppgM > bestMonth.ppg) bestMonth = { ppg: ppgM, ym, w, d, l, n: ms.length };
  }

  const crowd = mrow("attendance", (r) => Number(r.attendance).toLocaleString());

  // Cup Run: no competition-type flag ships to the client, so this is a heuristic — the
  // season's most-played competition is treated as the league (true for any real fixture
  // list), and the deepest run in any other named competition is the cup run.
  const byComp = new Map();
  for (const m of t) { const c = m.competition || ""; byComp.set(c, (byComp.get(c) || 0) + 1); }
  const leagueComp = [...byComp.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const cupGames = t.filter((m) => m.competition && m.competition !== leagueComp);
  let cupRun = null;
  if (cupGames.length) {
    const byCup = new Map();
    for (const m of cupGames) {
      if (!byCup.has(m.competition)) byCup.set(m.competition, []);
      byCup.get(m.competition).push(m);
    }
    const [cupName, games] = [...byCup.entries()].sort((a, b) => b[1].length - a[1].length)[0];
    const last = [...games].sort((a, b) => String(a.date).localeCompare(String(b.date))).at(-1);
    const status = last.result === "W" ? "won it" : `out ${last.gf}–${last.ga} vs ${last.opponent || `#${last.opp_tid}`}`;
    cupRun = { value: `${games.length} matches`, note: `${cupName} · last: ${status}` };
  }

  return [
    ["Season Record", { value: `${W}W ${Dd}D ${L}L`, note: `${gf} for / ${ga} against · ${ppg.toFixed(2)} PPG` }],
    ["Biggest Win", mrow("margin", (r) => `${r.gf}–${r.ga} (+${r.margin})`, (m) => m.result === "W")],
    ["Highest-scoring Game", mrow("total", (r) => `${r.gf}–${r.ga} (${r.total} goals)`)],
    ["Best Passing Display", mrow("passpct", (r) => `${r.passpct.toFixed(0)}% pass completion`)],
    ["Most Shots in a Game", mrow("our_shots", (r) => `${r.our_shots} shots`)],
    ["Clean Sheets", { value: `${t.filter((m) => m.ga === 0).length} of ${t.length}`, note: "shut-outs this season" }],
    ["Longest Clean-sheet Streak",
      { value: `${streak(chron, (m) => m.ga === 0).len} in a row`, note: "consecutive shut-outs" }],
    ["Longest Win Streak",
      { value: `${streak(chron, (m) => m.result === "W").len} in a row`, note: "consecutive wins" }],
    ["Longest Unbeaten Run",
      { value: `${streak(chron, (m) => m.result !== "L").len} games`, note: "without defeat" }],
    ["Home Fortress", rec(t.filter((m) => m.venue === "H"))],
    ["Road Warriors", rec(t.filter((m) => m.venue === "A"))],
    bestMonth ? ["Best Month", { value: `${bestMonth.ppg.toFixed(2)} PPG`,
      note: `${bestMonth.ym} (${bestMonth.w}W ${bestMonth.d}D ${bestMonth.l}L, ${bestMonth.n} games)` }] : null,
    crowd ? ["Biggest Crowd", crowd] : null,
    cupRun ? ["Cup Run", cupRun] : null,
  ].filter(Boolean).map(([label, v]) => (v ? { label, value: v.value, note: v.note } : null)).filter(Boolean);
}

function teamAwardsTable(items) {
  return el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Award", "Figure", "Detail"].map((h, i) =>
      el(`th${i === 1 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, items.map((a) => el("tr", {}, [
      el("td.name", { text: a.label }), el("td.num", { text: a.value }), el("td.dim", { text: a.note }),
    ]))),
  ])]);
}

/** One wide table: rows = award label, columns = season, cell = that season's winner. */
function honoursTable(title, seasonsAsc, itemsFor) {
  const matrix = new Map(); // label -> Map(season -> text)
  const order = [];
  for (const s of seasonsAsc) {
    for (const [label, cell] of itemsFor(s)) {
      if (!matrix.has(label)) { matrix.set(label, new Map()); order.push(label); }
      matrix.get(label).set(s, cell);
    }
  }
  if (!order.length) return el("div");
  return el("div", {}, [
    el("h4", { text: title }),
    el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, [el("th", { text: "Award" }),
        ...seasonsAsc.map((s) => el("th", { text: String(s) }))])]),
      el("tbody", {}, order.map((label) => el("tr", {}, [
        el("td.name", { text: label }),
        ...seasonsAsc.map((s) => el("td.dim", { text: matrix.get(label).get(s) || DASH })),
      ]))),
    ])]),
  ]);
}

function streak(chron, pred) {
  let best = 0, cur = 0, from = null, bestFrom = null, bestTo = null;
  for (const m of chron) {
    if (pred(m)) {
      if (!cur) from = m.date;
      cur++;
      if (cur > best) { best = cur; bestFrom = from; bestTo = m.date; }
    } else cur = 0;
  }
  return { len: best, from: bestFrom, to: bestTo };
}
const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
