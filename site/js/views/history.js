/**
 * History — the club's own story: season progression, records, and the awards roll.
 *
 * Its own section rather than a tab on Matches, because Matches answers "how are we playing"
 * and this answers "what have we done". Everything is computed in the browser from the same
 * match rows, so a new superlative is a few lines here rather than an exporter change.
 *
 * Only the managed club's matches are richly parsed, so these are OUR records — not the
 * league's. And match detail lives in a ring buffer the game overwrites as a season runs, so a
 * long-ago game may simply not be in the save any more.
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
  const name = (tid) => D.S.players.get(tid)?.name || `#${tid}`;

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

  // ---------------------------------------------------------------- team records
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
      el("td", { text: m.opponent || `#${m.opp_tid}` }),
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

  // ---------------------------------------------------------------- player records
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
    el("tbody", {}, singles.map((s) => el("tr.click", { onclick: () => openProfile(s.who) }, [
      el("td.name", { text: s.label }), el("td", { text: name(s.who) }),
      el("td.num", { text: s.value }), el("td", { text: s.when }),
    ]))),
  ])]));

  // ---------------------------------------------------------------- awards per season
  out.append(el("h3", { text: "Awards" }));
  const seasonSel = el("select.btn");
  for (const s of seasons) seasonSel.append(el("option", { value: String(s), text: String(s) }));
  const awards = el("div");
  seasonSel.addEventListener("change", () => drawAwards(Number(seasonSel.value)));
  out.append(el("div.tbar", {}, [seasonSel]), awards);

  function drawAwards(s) {
    const sr = rows.filter((r) => r.season === s);
    const agg = D.aggregate(sr);
    const games = new Set(sr.map((r) => String(r.date))).size;
    const minApps = Math.max(3, Math.round(games * 0.3));
    const pool = [...agg.values()].filter((a) => a.apps >= minApps);
    const top = (fn, label, dp = 2, note = "") => {
      const best = pool.map((a) => ({ a, v: fn(a) })).filter((x) => x.v != null && Number.isFinite(x.v))
        .sort((x, y) => y.v - x.v)[0];
      return best ? { label, who: best.a.tid, value: num(best.v, dp), note } : null;
    };
    const list = [
      top((a) => a.rating, "Player of the season", 2, "highest average match rating"),
      top((a) => a.goals, "Golden boot", 0, "most goals"),
      top((a) => a.assists, "Playmaker", 0, "most assists"),
      top((a) => (a.min ? (90 * a.goals) / a.min : null), "Most lethal", 2, "goals per 90"),
      top((a) => (a.passA ? (100 * a.passC) / a.passA : null), "Metronome", 0, "pass completion %"),
      top((a) => a.tackW + a.intercept + a.headW, "Destroyer", 0, "tackles won + interceptions + headers won"),
      top((a) => a.min, "Iron man", 0, "most minutes"),
      top((a) => (a.apps ? a.mistakes / a.apps : null), "Butterfingers", 2, "mistakes per game — the one you don't want"),
      top((a) => (a.apps ? a.yellow / a.apps : null), "Most booked", 2, "yellows per game"),
      // needs a real volume of shots or the "winner" is whoever had three and missed, which
      // reads as a broken stat rather than a joke
      top((a) => (a.shotA >= 10 && a.goals === 0 ? a.shotA : null), "Wasteful", 0,
        "most shots without scoring (10+ shots)"),
    ].filter(Boolean);
    awards.replaceChildren(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Award", "Winner", "Figure", "Decided by"].map((h, i) =>
        el(`th${i === 2 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, list.map((a) => el("tr.click", { onclick: () => openProfile(a.who) }, [
        el("td.name", { text: a.label }), el("td", { text: name(a.who) }),
        el("td.num", { text: a.value }), el("td.dim", { text: a.note }),
      ]))),
    ])]), el("p.note", {
      text: `Season ${s}: ${games} parsed matches, minimum ${minApps} appearances to qualify — `
        + "the bar scales with games played so a two-game cameo can't win anything. "
        + "Appearances count substitutes, not just starts.",
    }));
  }
  drawAwards(seasons[0]);

  out.append(el("p.note", { text: M.note }));
  return out;
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
