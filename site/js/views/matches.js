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
import { el, num, pill, DASH, multiSelect } from "../ui.js";
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
  // The game's own stage labels (mart.match_stages). A group's letter changes every season,
  // so filters and summaries compare "Group stage"; the results table keeps "Group D".
  const phaseOf = (m) => m.stage_kind || null;
  const roundOf = (m) => (m.stage_kind === "Group" ? "Group stage" : m.stage) || null;
  const hasStages = all.some((m) => m.stage);
  // Where in a season a stage falls, so stage lists read in the order they are played.
  const seasonDay = (m) => {
    const d = new Date(String(m.date).slice(0, 10));
    return (d - new Date(Date.UTC(m.season - 1, 6, 1))) / 864e5;
  };
  const stageOrder = new Map();
  for (const m of all) {
    const k = `${comp(m)}|${roundOf(m)}`;
    const o = stageOrder.get(k) || { n: 0, s: 0 };
    o.n++; o.s += seasonDay(m);
    stageOrder.set(k, o);
  }
  const orderOf = (m) => { const o = stageOrder.get(`${comp(m)}|${roundOf(m)}`); return o ? o.s / o.n : 0; };
  const PHASES = ["League", "Qualifying", "Group", "Knockout"];
  const oppKey = (m) => m.opp_tid ?? m.opponent;
  const oppName = (m) => m.opponent || `#${m.opp_tid}`;
  let friendlies = false;

  const out = el("div");
  out.append(el("h2", { text: "Matches" }));

  const kpiRow = el("div.kpis");
  const body = el("div");

  // Three multi-selects, each an empty-means-all Set. A list only offers what the filters
  // BEFORE it leave (season -> competition -> opponent), with a match count beside each, so
  // nothing on offer ever filters to zero.
  const count = (ms, key) => {
    const c = new Map();
    for (const m of ms) c.set(key(m), (c.get(key(m)) || 0) + 1);
    return c;
  };
  const inSeasons = (m) => !seasonMs.selected.size || seasonMs.selected.has(m.season);
  const inComps = (m) => !compMs.selected.size || compMs.selected.has(comp(m));
  const inOpps = (m) => !oppMs.selected.size || oppMs.selected.has(oppKey(m));
  const inPhases = (m) => !phaseMs.selected.size || phaseMs.selected.has(phaseOf(m));
  const inRounds = (m) => !roundMs.selected.size || roundMs.selected.has(roundOf(m));
  const friendlyOk = (m) => friendlies || !isFriendly(m);

  const seasonMs = multiSelect({
    noun: "season", plural: "seasons",
    options: () => {
      const c = count(all.filter(friendlyOk), (m) => m.season);
      return seasons.filter((s) => c.has(s)).map((s) => ({ value: s, label: s, hint: c.get(s) }));
    },
    onChange: () => draw(),
  });
  const compMs = multiSelect({
    noun: "competition", plural: "competitions",
    options: () => {
      const c = count(all.filter((m) => friendlyOk(m) && inSeasons(m)), comp);
      return [...c.keys()].sort().map((k) => ({ value: k, label: k, hint: c.get(k) }));
    },
    onChange: () => draw(),
  });
  const phaseMs = multiSelect({
    noun: "phase", plural: "phases",
    options: () => {
      const c = count(all.filter((m) => friendlyOk(m) && inSeasons(m) && inComps(m)), phaseOf);
      return PHASES.filter((k) => c.has(k)).map((k) => ({ value: k, label: k, hint: c.get(k) }));
    },
    onChange: () => draw(),
  });
  const roundMs = multiSelect({
    noun: "round", plural: "rounds",
    options: () => {
      const ms = all.filter((m) => friendlyOk(m) && inSeasons(m) && inComps(m) && inPhases(m));
      const c = count(ms, roundOf);
      const first = new Map();
      for (const m of ms) if (!first.has(roundOf(m))) first.set(roundOf(m), orderOf(m));
      return [...c.keys()].filter((k) => k != null)
        .sort((a, b) => first.get(a) - first.get(b))
        .map((k) => ({ value: k, label: k, hint: c.get(k) }));
    },
    onChange: () => draw(),
  });
  const oppMs = multiSelect({
    noun: "opponent", plural: "opponents", search: true,
    options: () => {
      const ms = all.filter((m) => friendlyOk(m) && inSeasons(m) && inComps(m)
        && inPhases(m) && inRounds(m));
      const c = count(ms, oppKey);
      const names = new Map(ms.map((m) => [oppKey(m), oppName(m)]));
      return [...c.keys()].map((k) => ({ value: k, label: names.get(k), hint: c.get(k) }))
        .sort((a, b) => b.hint - a.hint || String(a.label).localeCompare(String(b.label)));
    },
    onChange: () => draw(),
  });
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
  const filters = hasStages
    ? [seasonMs.node, compMs.node, phaseMs.node, roundMs.node, oppMs.node, friBtn]
    : [seasonMs.node, compMs.node, oppMs.node, friBtn];
  out.append(el("div.tbar", {}, filters), kpiRow, body);

  function filtered() {
    return all.filter((m) => friendlyOk(m) && inSeasons(m) && inComps(m) && inPhases(m)
      && inRounds(m) && inOpps(m));
  }

  function draw() {
    // Upstream picks can take a value off a downstream list; drop it rather than leave a
    // filter that silently matches nothing.
    seasonMs.sync(); compMs.sync(); phaseMs.sync(); roundMs.sync(); oppMs.sync();
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
    if (hasStages) {
      const staged = ms.filter((m) => m.stage_kind);
      if (staged.length) {
        body.append(el("h3", { text: "By phase" }));
        body.append(summaryTable(staged, phaseOf, "Phase", false,
          (a, b) => PHASES.indexOf(a.k) - PHASES.indexOf(b.k)));
        body.append(el("h3", { text: "By round" }));
        const firstAt = new Map();
        for (const m of staged) {
          const k = `${comp(m)} · ${roundOf(m)}`;
          if (!firstAt.has(k)) firstAt.set(k, [comp(m), orderOf(m)]);
        }
        body.append(summaryTable(staged, (m) => `${comp(m)} · ${roundOf(m)}`, "Round", false,
          (a, b) => {
            const [ca, oa] = firstAt.get(a.k), [cb, ob] = firstAt.get(b.k);
            return ca.localeCompare(cb) || oa - ob;
          }));
        body.append(el("p.note", { text: "Stages and rounds are the game's own labels, read "
          + "from each competition's rules in the save. Groups are pooled as \"Group stage\" "
          + "across seasons; the results below keep the letter." }));
      }
    }

    // ---- head to head
    body.append(el("h3", { text: "Head to head" }));
    body.append(summaryTable(ms, oppName, "Opponent", true));

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
      el("thead", {}, [el("tr", {}, ["Date", "Competition", "Stage", "H/A", "Opponent", "Score", "", "Formation"]
        .map((h, i) => el(`th${i === 5 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, [...ms].sort((a, b) => String(b.date).localeCompare(String(a.date))).map((m) =>
        el("tr", {}, [
          el("td", { text: String(m.date).slice(0, 10) }),
          el("td", { text: comp(m) }),
          el("td", { text: stageText(m) }),
          el("td", { text: m.venue }),
          el("td.name", { text: m.opponent || `#${m.opp_tid}` }),
          el("td.num", { text: scoreText(m), title: scoreTitle(m) }),
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

// "Group D · MD 3", "Quarter Final · leg 2", "Preliminary Phase · MD 12"
function stageText(m) {
  if (!m.stage) return DASH;
  const bits = [m.stage];
  if (m.leg) bits.push(`leg ${m.leg}`);
  else if (m.matchday) bits.push(`MD ${m.matchday}`);
  return bits.join(" · ");
}

// 2–2 aet · 1–3 p · agg 3–3, with a ✓/✗ on the match that settled a tie
function scoreText(m) {
  let s = `${m.gf}–${m.ga}`;
  if (m.extra_time) s += " aet";
  if (m.pens_for != null) s += ` (${m.pens_for}–${m.pens_against} p)`;
  const settles = m.went_through != null && (!m.leg || m.leg === 2);
  if (m.leg === 2 && m.tie_gf != null) s += ` · agg ${m.tie_gf}–${m.tie_ga}`;
  if (settles) s += m.went_through ? " ✓" : " ✗";
  return s;
}

function scoreTitle(m) {
  const t = [];
  if (m.extra_time) t.push("after extra time");
  if (m.pens_for != null) t.push(`penalties ${m.pens_for}–${m.pens_against}`);
  if (m.tie_gf != null) t.push(`aggregate ${m.tie_gf}–${m.tie_ga}`);
  if (m.went_through != null) t.push(m.went_through ? "went through" : "knocked out");
  return t.join(" · ");
}

function summaryTable(ms, keyFn, label, sortByPlayed = false, order = null) {
  const g = new Map();
  for (const m of ms) {
    const k = keyFn(m);
    const r = g.get(k) || { k, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
    r.p++; r.gf += m.gf || 0; r.ga += m.ga || 0; r.pts += m.pts || 0;
    if (m.result === "W") r.w++; else if (m.result === "D") r.d++; else if (m.result === "L") r.l++;
    g.set(k, r);
  }
  const rows = [...g.values()].sort(order || ((a, b) => sortByPlayed
    ? b.p - a.p || b.pts / b.p - a.pts / a.p
    : String(b.k).localeCompare(String(a.k))));
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
