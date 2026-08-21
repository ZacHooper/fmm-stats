/**
 * Matches — results, head-to-head, per-competition splits, team stat differentials, and the
 * whole-squad match grid with configurable columns.
 *
 * Everything here is computed in the browser from `matches.json`, which ships the raw per-match
 * and per-player-per-match rows. That's why the old Matches and Player Stats pages could merge:
 * they were two aggregations of one dataset, and any new question is another aggregation rather
 * than another export.
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, num, pill, DASH } from "../ui.js";
import { openProfile } from "../profile.js";

const RES = { W: "good", D: "flat", L: "bad" };

export async function view() {
  const M = await D.loadMatches();
  if (!M.matches?.length) {
    return el("div.card", {}, [el("b", { text: "No matches parsed" }), el("p.note", { text: M.note })]);
  }
  const f = M.match_fields;
  const ix = Object.fromEntries(f.map((n, i) => [n, i]));
  const all = M.matches.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])));
  const comp = (m) => m.competition || "?";
  const isFriendly = (m) => /friend/i.test(comp(m));

  const seasons = [...new Set(all.map((m) => m.season))].sort((a, b) => b - a);
  let season = "all", competition = "all", friendlies = false;

  const out = el("div");
  out.append(el("h2", { text: "Matches" }));

  const kpiRow = el("div.kpis");
  const body = el("div");

  const seasonSel = el("select.btn", { onchange: (e) => { season = e.target.value; draw(); } },
    [el("option", { value: "all", text: "All seasons" }),
      ...seasons.map((s) => el("option", { value: String(s), text: String(s) }))]);
  const compSel = el("select.btn", { onchange: (e) => { competition = e.target.value; draw(); } });
  const friBtn = el("button.btn", {
    text: "Friendlies off",
    title: "Friendlies aren't meaningful for form or a bogey read, so they're excluded by default",
    onclick: () => {
      friendlies = !friendlies;
      friBtn.textContent = friendlies ? "Friendlies on" : "Friendlies off";
      friBtn.classList.toggle("on", friendlies);
      draw();
    },
  });
  out.append(el("div.tbar", {}, [seasonSel, compSel, friBtn]), kpiRow, body);

  function filtered() {
    return all.filter((m) => (season === "all" || String(m.season) === season)
      && (competition === "all" || comp(m) === competition)
      && (friendlies || !isFriendly(m)));
  }

  function rebuildCompSel() {
    const inSeason = all.filter((m) => season === "all" || String(m.season) === season);
    const comps = [...new Set(inSeason.map(comp))].sort();
    compSel.replaceChildren(el("option", { value: "all", text: "All competitions" }),
      ...comps.map((c) => el("option", { value: c, text: c, selected: c === competition })));
    if (!comps.includes(competition)) competition = "all";
  }

  function draw() {
    rebuildCompSel();
    const ms = filtered();
    const w = ms.filter((m) => m.result === "W").length;
    const d = ms.filter((m) => m.result === "D").length;
    const l = ms.filter((m) => m.result === "L").length;
    const gf = ms.reduce((a, m) => a + (m.gf || 0), 0);
    const ga = ms.reduce((a, m) => a + (m.ga || 0), 0);
    kpiRow.replaceChildren(
      kpi("Played", ms.length), kpi("W-D-L", `${w}-${d}-${l}`),
      kpi("Goals", `${gf}:${ga}`), kpi("GD", (gf - ga >= 0 ? "+" : "") + (gf - ga)),
      kpi("Pts/game", ms.length ? num(ms.reduce((a, m) => a + (m.pts || 0), 0) / ms.length, 2) : DASH),
    );

    body.replaceChildren();

    // ---- season / competition summary
    body.append(el("h3", { text: "By season" }));
    body.append(summaryTable(ms, (m) => m.season, "Season"));
    body.append(el("h3", { text: "By competition" }));
    body.append(summaryTable(ms, comp, "Competition"));

    // ---- head to head
    body.append(el("h3", { text: "Head to head" }));
    body.append(summaryTable(ms, (m) => m.opponent || `#${m.opp_tid}`, "Opponent", true));

    // ---- team stat differentials: ours vs theirs, per match average
    const stats = f.filter((n) => n.startsWith("our_")).map((n) => n.slice(4));
    if (stats.length) {
      body.append(el("h3", { text: "Team stats per match" }));
      body.append(el("div.scroll", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Stat", "Us", "Them", "Edge"].map((h, i) =>
          el(`th${i ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, stats.map((s) => {
          const us = avg(ms, `our_${s}`), them = avg(ms, `opp_${s}`);
          const edge = us == null || them == null ? null : us - them;
          return el("tr", {}, [
            el("td", { text: s.replace(/_/g, " ") }),
            el("td.num", { text: us == null ? DASH : num(us, 1) }),
            el("td.num", { text: them == null ? DASH : num(them, 1) }),
            el("td.num", {}, [edge == null ? DASH
              : pill(`${edge >= 0 ? "+" : ""}${num(edge, 1)}`, edge >= 0 ? "good" : "bad")]),
          ]);
        })),
      ])]));
      body.append(el("p.note", { text: "Averages per match over the filtered set. Opponent formation isn't in the save, so shape analysis is our-side only." }));
    }

    // ---- formations we used
    const forms = new Map();
    for (const m of ms) {
      if (!m.formation) continue;
      const g = forms.get(m.formation) || { p: 0, pts: 0 };
      g.p++; g.pts += m.pts || 0;
      forms.set(m.formation, g);
    }
    if (forms.size) {
      body.append(el("h3", { text: "Our formations" }));
      body.append(el("div.scroll", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Formation", "Played", "Pts/game"].map((h, i) =>
          el(`th${i ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, [...forms.entries()].sort((a, b) => b[1].p - a[1].p).map(([k, v]) =>
          el("tr", {}, [el("td.name", { text: k }), el("td.num", { text: v.p }),
            el("td.num", { text: num(v.pts / v.p, 2) })]))),
      ])]));
    }

    // ---- results
    body.append(el("h3", { text: `Results · ${ms.length}` }));
    body.append(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Date", "Competition", "H/A", "Opponent", "Score", "", "Formation"]
        .map((h, i) => el(`th${i === 4 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, [...ms].sort((a, b) => String(b.date).localeCompare(String(a.date))).map((m) =>
        el("tr", {}, [
          el("td", { text: String(m.date).slice(0, 10) }),
          el("td", { text: comp(m) }), el("td", { text: m.venue }),
          el("td.name", { text: m.opponent || `#${m.opp_tid}` }),
          el("td.num", { text: `${m.gf}–${m.ga}` }),
          el("td", {}, [pill(m.result, RES[m.result] || "flat")]),
          el("td", { text: m.formation || DASH }),
        ]))),
    ])]));

    // ---- per-player grid, re-aggregated for the current filter
    const keep = new Set(ms.map((m) => `${m.season}|${String(m.date).slice(0, 10)}`));
    const rows = D.matchRows().filter((r) => keep.has(`${r.season}|${String(r.date).slice(0, 10)}`));
    const agg = D.aggregate(rows);
    body.append(el("h3", { text: "Players over the filtered matches" }));
    const prows = [...agg.values()].map((a) => {
      const p = D.S.players.get(a.tid);
      const best = p ? D.bestRole(p) : null;
      return {
        tid: a.tid, player: p || { name: `#${a.tid}`, attrs: [] }, r: best,
        _search: (p?.name || `#${a.tid}`).toLowerCase(),
      };
    });
    const cat = {
      player: { label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name, get: (r) => r.player.name },
      pos: { label: "Pos", group: "Identity", get: (r) => r.r?.pos ?? DASH },
      ...metricColumns(D, { agg }),
    };
    body.append(playerTable({
      key: "matchgrid", rows: prows, catalogue: cat,
      presets: Object.fromEntries(Object.entries(D.STAT_PRESETS).map(([k, v]) => [k, v.map((s) => `stat:${s}`)])),
      sticky: ["player"],
      defaults: ["pos", "stat:Apps", "stat:Starts", "stat:Min", "stat:Rating", "stat:Goals",
        "stat:Assists", "stat:Pass %", "stat:Tackle %"],
      sort: { by: "stat:Min", dir: "desc" },
      searchPlaceholder: "Search players…",
      onRow: (r) => openProfile(r.tid),
      empty: "Nobody appeared in the filtered matches.",
    }).node);
    body.append(el("p.note", { text: M.note }));
  }

  draw();
  return out;
}

function summaryTable(ms, keyFn, label, sortByPlayed = false) {
  const g = new Map();
  for (const m of ms) {
    const k = keyFn(m);
    const r = g.get(k) || { k, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
    r.p++; r.gf += m.gf || 0; r.ga += m.ga || 0; r.pts += m.pts || 0;
    if (m.result === "W") r.w++; else if (m.result === "D") r.d++; else if (m.result === "L") r.l++;
    g.set(k, r);
  }
  const rows = [...g.values()].sort((a, b) => sortByPlayed
    ? b.p - a.p || b.pts / b.p - a.pts / a.p
    : String(b.k).localeCompare(String(a.k)));
  return el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, [label, "P", "W", "D", "L", "GF", "GA", "GD", "Pts/gm"]
      .map((h, i) => el(`th${i ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, rows.map((r) => el("tr", {}, [
      el("td.name", { text: r.k }), el("td.num", { text: r.p }), el("td.num", { text: r.w }),
      el("td.num", { text: r.d }), el("td.num", { text: r.l }), el("td.num", { text: r.gf }),
      el("td.num", { text: r.ga }),
      el("td.num", { text: (r.gf - r.ga >= 0 ? "+" : "") + (r.gf - r.ga) }),
      el("td.num", { text: num(r.pts / r.p, 2) }),
    ]))),
  ])]);
}

const avg = (ms, k) => {
  const vs = ms.map((m) => m[k]).filter((v) => v != null);
  return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
};
const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
