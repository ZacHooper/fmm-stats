/**
 * Matches — one filter bar over every match we have played, and six tabs that each answer one
 * question about the matches it leaves:
 *
 *   Overview    how are we doing?          KPIs + form, latest results, who's delivering, highlights
 *   Players     who delivers here?         the configurable player grid, each player against his norm
 *   Results     what happened?             every match, under its season
 *   Splits      where do we do well?       ONE table, split by season/competition/phase/round/...
 *   Opponents   who are our bogey teams?   head to head
 *   Team stats  how do we play?            ours against theirs, per match
 *
 * Everything is computed in the browser from `matches.json`, which ships the raw per-match and
 * per-player-per-match rows: any new question is another aggregation rather than another
 * export. The open tab (and the Splits dimension) lives in the URL, so a reload or a shared
 * link lands on the same view.
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, num, pill, bar, DASH, multiSelect, hashParams, setHashParams } from "../ui.js";
import { openPlayer } from "../profile.js";
import { openClub } from "../club.js";

const RES = { W: "good", D: "flat", L: "bad" };

// Tab order is a design choice still being tried out — reorder here and nothing else moves.
const TABS = [
  ["overview", "Overview"],
  ["players", "Players"],
  ["results", "Results"],
  ["splits", "Splits"],
  ["opponents", "Opponents"],
  ["stats", "Team stats"],
];
const LS_TAB = "fm:matches:tab";
const LS_MINMIN = "fm:matches:minmin";
const LS_NORM = "fm:matches:norm";
const LS_MINP = "fm:matches:minp";
const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

// `#/matches?tab=splits&split=round` (ui.js hashParams).
const params = hashParams;
const setParams = setHashParams;

// Match stats that are COUNTS. Comparing a count over a filtered set with the same count over
// every match is meaningless (fewer matches, fewer goals), so "vs his norm" only marks rates.
const TOTALS = new Set(["Apps", "Starts", "Sub", "Min", "Goals", "Assists", "G+A", "POTM",
  "Key passes", "Pass att", "Tackle att", "Shot att", "Interceptions", "Dribbles"]);
const MIN_MINUTES = [0, 90, 180, 450, 900];

export async function view() {
  const M = await D.loadMatches();
  if (!M.matches?.length) {
    return el("div.card", {}, [el("b", { text: "No matches parsed" }), el("p.note", { text: M.note })]);
  }
  const f = M.match_fields;
  const all = M.matches.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])));
  const comp = (m) => m.competition || "?";
  const isFriendly = (m) => D.isFriendly(m.competition);

  const seasons = [...new Set(all.map((m) => m.season))].sort((a, b) => b - a);
  // The game's own stage labels (mart.match_stages). A group's letter changes every season,
  // so filters and summaries compare "Group stage"; the results table keeps "Group D". The
  // access path ("League Path · ") is dropped too, so a round is the same round in either
  // European cup — the Results tab keeps the full label.
  const phaseOf = (m) => m.stage_kind || null;
  const roundOf = (m) => (m.stage_kind === "Group" ? "Group stage"
    : m.stage ? String(m.stage).split(" · ").pop() : null);
  const hasStages = all.some((m) => m.stage);
  // Where in a season a match falls, so round lists read in the order they are played.
  const seasonDay = (m) => {
    const d = new Date(String(m.date).slice(0, 10));
    return (d - new Date(Date.UTC(m.season - 1, 6, 1))) / 864e5;
  };
  const PHASES = ["League", "Qualifying", "Group", "Knockout"];
  const roundAt = new Map();          // round -> {ph, n, s}: phase, then mean day in the season
  for (const m of all) {
    const k = roundOf(m);
    if (k == null) continue;
    const o = roundAt.get(k) || { ph: PHASES.indexOf(m.stage_kind), n: 0, s: 0 };
    o.n++; o.s += seasonDay(m);
    roundAt.set(k, o);
  }
  const roundCmp = (a, b) => {
    const x = roundAt.get(a), y = roundAt.get(b);
    return x.ph - y.ph || x.s / x.n - y.s / y.n;
  };
  const oppKey = (m) => m.opp_tid ?? m.opponent;
  const oppName = (m) => m.opponent || `#${m.opp_tid}`;
  const VENUE = { H: "Home", A: "Away", N: "Neutral" };
  let friendlies = false;

  // ---------------------------------------------------------------- filters
  // Multi-selects, each an empty-means-all Set. A list only offers what the filters BEFORE it
  // leave (season -> competition -> phase -> round -> opponent), with a match count beside each,
  // so nothing on offer ever filters to zero.
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
  // Pins: the dimensions with no dropdown of their own (a formation, home or away), set by
  // clicking a Splits row and shown as removable chips.
  const PIN_TEST = { formation: (m, v) => m.formation === v, venue: (m, v) => m.venue === v };
  const PIN_LABEL = { formation: (v) => `Kick-off ${v}`, venue: (v) => VENUE[v] || v };
  const pins = new Map();
  const inPins = (m) => [...pins].every(([k, v]) => PIN_TEST[k](m, v));

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
      return [...c.keys()].filter((k) => k != null).sort(roundCmp)
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
  const pinRow = el("span.pins");
  const DIMS = { season: seasonMs, competition: compMs, phase: phaseMs, round: roundMs, opponent: oppMs };
  const filters = hasStages
    ? [seasonMs.node, compMs.node, phaseMs.node, roundMs.node, oppMs.node, friBtn, pinRow]
    : [seasonMs.node, compMs.node, oppMs.node, friBtn, pinRow];

  function filtered() {
    return all.filter((m) => friendlyOk(m) && inSeasons(m) && inComps(m) && inPhases(m)
      && inRounds(m) && inOpps(m) && inPins(m));
  }

  /** Narrow one dimension to one value and open a tab — the jump from a Splits or Opponents
   *  row into "our players in exactly these matches". Other dimensions are left as they are. */
  function focus(dim, value, tab = "players") {
    if (PIN_TEST[dim]) pins.set(dim, value);
    else { const ms = DIMS[dim]; ms.selected.clear(); ms.selected.add(value); }
    show(tab);
  }

  // ---------------------------------------------------------------- shell
  const out = el("div");
  out.append(el("h2", { text: "Matches" }));
  const kpiRow = el("div.kpis");
  const tabRow = el("div.prow.mtabs", { role: "tablist" });
  const panel = el("div");
  out.append(el("div.tbar", {}, filters), kpiRow, tabRow, panel);

  const known = (t) => TABS.some(([k]) => k === t);
  let tab = [params().get("tab"), lsGet(LS_TAB)].find(known) || TABS[0][0];
  function show(t) {
    tab = t; lsSet(LS_TAB, t); setParams({ tab: t });
    draw();
  }

  function draw() {
    // Upstream picks can take a value off a downstream list; drop it rather than leave a
    // filter that silently matches nothing.
    seasonMs.sync(); compMs.sync(); phaseMs.sync(); roundMs.sync(); oppMs.sync();
    pinRow.replaceChildren(...[...pins].map(([k, v]) => el("span.wchip", {}, [
      PIN_LABEL[k](v),
      el("button.x", { text: "✕", title: "Remove", onclick: () => { pins.delete(k); draw(); } }),
    ])));
    const ms = filtered();
    drawKpis(ms);
    tabRow.replaceChildren(...TABS.map(([k, label]) => el(`button.chip${k === tab ? ".on" : ""}`, {
      text: label, role: "tab", "aria-selected": k === tab ? "true" : "false",
      onclick: () => show(k),
    })));
    const PANELS = { overview, players, results, splits, opponents, stats };
    panel.replaceChildren(PANELS[tab](ms));
  }

  function drawKpis(ms) {
    const w = ms.filter((m) => m.result === "W").length;
    const d = ms.filter((m) => m.result === "D").length;
    const l = ms.filter((m) => m.result === "L").length;
    const gf = ms.reduce((a, m) => a + (m.gf || 0), 0);
    const ga = ms.reduce((a, m) => a + (m.ga || 0), 0);
    const recent = byDate(ms);                     // newest first
    const last = recent.slice(0, 10).reverse();    // the guide reads left to right, oldest first
    const st = streak(recent);
    kpiRow.replaceChildren(
      kpi("Played", ms.length), kpi("W-D-L", `${w}-${d}-${l}`),
      kpi("Goals", `${gf}:${ga}`), kpi("GD", signed(gf - ga)),
      kpi("Pts/game", ms.length ? num(ms.reduce((a, m) => a + (m.pts || 0), 0) / ms.length, 2) : DASH),
      el("div.kpi.formkpi", { title: st.title }, [
        el("b", {}, last.length ? last.map((m) => el(`span.fdot.${RES[m.result] || "flat"}`, {
          text: m.result || "?", title: `${String(m.date).slice(0, 10)} · ${m.venue} ${oppName(m)} ${scoreText(m)}`,
        })) : DASH),
        el("span", { text: st.text ? `Form · ${st.text}` : "Form" }),
      ]),
    );
  }

  // ---------------------------------------------------------------- player aggregation
  // A player's numbers over the filtered matches, and the same over every match the friendlies
  // toggle allows (his norm). Keyed by tid. Recomputed per draw: a few thousand rows.
  const matchKey = (season, date) => `${season}|${String(date).slice(0, 10)}`;
  function playerAggs(ms) {
    const keep = new Set(ms.map((m) => matchKey(m.season, m.date)));
    const base = new Set(all.filter(friendlyOk).map((m) => matchKey(m.season, m.date)));
    const rows = D.matchRows();
    return {
      agg: D.aggregate(rows.filter((r) => keep.has(matchKey(r.season, r.date)))),
      norm: D.aggregate(rows.filter((r) => base.has(matchKey(r.season, r.date)))),
    };
  }
  const minMinutes = () => {
    const raw = lsGet(LS_MINMIN);
    return raw != null && MIN_MINUTES.includes(Number(raw)) ? Number(raw) : 180;
  };
  const ratingOf = (a) => a?.ratingAdj ?? a?.rating ?? null;

  // ---------------------------------------------------------------- Overview
  function overview(ms) {
    const box = el("div");
    if (!ms.length) return el("p.note", { text: "No matches in this filter." });
    const recent = byDate(ms);

    // latest results + who's delivering, side by side on a wide screen
    const latest = el("div.card", {}, [
      el("div.sechead", {}, [el("h3", { text: "Latest results" }),
        el("button.link", { text: `All ${ms.length} results ›`, onclick: () => show("results") })]),
      el("div.scroll.fit", {}, [el("table.latest", {}, [el("tbody", {}, recent.slice(0, 8).map((m) =>
        el("tr", {}, [
          el("td.dim", { text: shortDate(m.date), title: String(m.date).slice(0, 10) }),
          el("td", { text: m.venue }),
          el("td.name", {}, [clubLink(m)]),
          el("td.num", { text: scoreText(m), title: scoreTitle(m) }),
          el("td", {}, [pill(m.result, RES[m.result] || "flat")]),
          el("td.dim.wide", { text: comp(m) }),
        ])))])]),
    ]);

    const { agg } = playerAggs(ms);
    const minMin = minMinutes();
    const top = [...agg.values()].filter((a) => a.min >= minMin && ratingOf(a) != null)
      .sort((a, b) => ratingOf(b) - ratingOf(a)).slice(0, 6);
    const delivering = el("div.card", {}, [
      el("div.sechead", {}, [el("h3", { text: "Who's delivering" }),
        el("button.link", { text: "All players ›", onclick: () => show("players") })]),
      top.length ? el("div.scroll.fit", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Player", "Apps", "Min", "Rating", "G+A"].map((h, i) =>
          el(`th${i ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, top.map((a) => el("tr.click", {
          onclick: () => openPlayer(a.tid),
        }, [
          el("td.name", { text: D.matchName(a.tid) }),
          el("td.num", { text: a.apps }), el("td.num", { text: num(a.min) }),
          el("td.num", { text: num(ratingOf(a), 2) }),
          el("td.num", { text: a.goals + a.assists }),
        ]))),
      ])]) : el("p.note", { text: `Nobody has ${minMin}+ minutes in these matches.` }),
      el("p.note", { text: `Position-adjusted rating, ${minMin}+ minutes.` }),
    ]);
    box.append(el("div.grid2", {}, [latest, delivering]));

    // highlights
    const hl = highlights(ms, recent);
    if (hl.length) {
      box.append(el("h3", { text: "Highlights" }));
      box.append(el("div.kpis.hl", {}, hl.map(([label, value, detail, onclick]) =>
        el(`div.kpi${onclick ? ".click" : ""}`, { title: detail, onclick }, [
          el("b", { text: value }), el("span", { text: label }),
          detail ? el("small", { text: detail }) : null,
        ]))));
    }

    // season by season, only worth a table when the filter spans more than one
    if (new Set(ms.map((m) => m.season)).size > 1) {
      box.append(el("h3", { text: "Season by season" }));
      box.append(summaryTable(ms, (m) => m.season, "Season", {
        order: (a, b) => b.k - a.k,
        action: (r) => focus("season", r.k),
      }));
    }
    return box;
  }

  function highlights(ms, recent) {
    const out = [];
    const margin = (m) => (m.gf || 0) - (m.ga || 0);
    const line = (m) => `${m.venue === "H" ? "v" : "at"} ${oppName(m)} · ${String(m.date).slice(0, 10)}`;
    const won = ms.filter((m) => m.result === "W").sort((a, b) => margin(b) - margin(a) || b.gf - a.gf);
    const lost = ms.filter((m) => m.result === "L").sort((a, b) => margin(a) - margin(b) || b.ga - a.ga);
    if (won.length) out.push(["Biggest win", `${won[0].gf}–${won[0].ga}`, line(won[0]),
      () => openClub(won[0].opp_tid)]);
    if (lost.length) out.push(["Heaviest defeat", `${lost[0].gf}–${lost[0].ga}`, line(lost[0]),
      () => openClub(lost[0].opp_tid)]);
    // Best and bogey: points per game against a side we have met at least three times, so one
    // lucky win can't top the list.
    const vs = new Map();
    for (const m of ms) {
      const k = oppKey(m);
      const o = vs.get(k) || { m, p: 0, pts: 0, w: 0, d: 0, l: 0 };
      o.p++; o.pts += m.pts || 0; o[m.result?.toLowerCase()] = (o[m.result?.toLowerCase()] || 0) + 1;
      vs.set(k, o);
    }
    const met = [...vs.values()].filter((o) => o.p >= 3).sort((a, b) => b.pts / b.p - a.pts / a.p || b.p - a.p);
    if (met.length >= 2) {
      const best = met[0], worst = met[met.length - 1];
      const rec = (o) => `${o.w}-${o.d}-${o.l} in ${o.p} · ${num(o.pts / o.p, 2)} pts/gm`;
      out.push(["Favourite opponent", oppName(best.m), rec(best), () => focus("opponent", oppKey(best.m))]);
      out.push(["Bogey team", oppName(worst.m), rec(worst), () => focus("opponent", oppKey(worst.m))]);
    }
    // longest unbeaten run, in date order
    let run = 0, bestRun = 0, end = null;
    for (const m of [...recent].reverse()) {
      run = m.result === "L" ? 0 : run + 1;
      if (run > bestRun) { bestRun = run; end = m; }
    }
    if (bestRun >= 3) out.push(["Longest unbeaten", `${bestRun} games`, `ending ${String(end.date).slice(0, 10)}`]);
    return out;
  }

  // ---------------------------------------------------------------- Players
  function players(ms) {
    const { agg, norm } = playerAggs(ms);
    const minMin = minMinutes();
    const vsNorm = lsGet(LS_NORM) === "1";
    const rows = [...agg.values()].map((a) => {
      const p = D.S.players.get(a.tid);
      const best = p ? D.bestRole(p) : null;
      const name = p?.name || D.matchName(a.tid);
      return { tid: a.tid, player: p || { name, attrs: [] }, r: best, _search: name.toLowerCase() };
    });
    const cat = {
      player: { label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name, get: (r) => r.player.name },
      pos: { label: "Pos", group: "Identity", get: (r) => r.r?.pos ?? DASH },
      ...metricColumns(D, { agg }),
    };
    // "vs his norm": every rate column shows the filtered value with the difference from his
    // own average over all matches, and sorts and filters on that difference. Counts are left
    // alone (see TOTALS).
    if (vsNorm) {
      for (const [id, c] of Object.entries(cat)) {
        const n = id.startsWith("stat:") ? id.slice(5) : null;
        if (!n || TOTALS.has(n)) continue;
        const delta = (r) => {
          const v = D.statValue(n, agg.get(r.tid)), b = D.statValue(n, norm.get(r.tid));
          return v == null || b == null ? null : v - b;
        };
        cat[id] = {
          ...c, label: `${c.label} Δ`, sort: delta, filterValue: delta,
          help: `${c.help} — sorted on the difference from his own average over every match`,
          render: (r) => {
            const v = c.get(r);
            if (v == null) return null;
            const dv = delta(r);
            const dp = c.dp ?? 0;
            const flat = dv == null || Math.abs(dv) < 0.5 * 10 ** -dp;
            return el("span.normcell", {}, [num(v, dp), dv == null ? null
              : el(`span.delta${flat ? "" : dv > 0 ? ".up" : ".down"}`, {
                text: flat ? "=" : `${dv > 0 ? "▲" : "▼"}${num(Math.abs(dv), dp)}`,
                title: `His norm: ${num(D.statValue(n, norm.get(r.tid)), dp)}`,
              })]);
          },
        };
      }
    }
    const minSel = el("select.btn", {
      title: "Hide players with fewer minutes in these matches — a 20-minute cameo tops every rate",
      onchange: (e) => { lsSet(LS_MINMIN, e.target.value); draw(); },
    }, MIN_MINUTES.map((v) => el("option", { value: v, text: v ? `${v}+ min` : "Any minutes", selected: v === minMin })));
    const normBtn = el(`button.btn${vsNorm ? ".on" : ""}`, {
      text: "vs his norm",
      title: "Mark each rate stat against the player's own average over every match, and sort on the difference",
      onclick: () => { lsSet(LS_NORM, vsNorm ? "0" : "1"); draw(); },
    });
    const box = el("div");
    box.append(playerTable({
      key: "matchgrid", rows, catalogue: cat,
      presets: Object.fromEntries(Object.entries(D.STAT_PRESETS).map(([k, v]) => [k, v.map((s) => `stat:${s}`)])),
      sticky: ["player"],
      defaults: ["pos", "stat:Apps", "stat:Starts", "stat:Min", "stat:Rating (adj)", "stat:Goals",
        "stat:Assists", "stat:Pass %", "stat:Tackle %"],
      sort: { by: "stat:Min", dir: "desc" },
      filter: (r) => (agg.get(r.tid)?.min || 0) >= minMin,
      toolbar: [minSel, normBtn],
      searchPlaceholder: "Search players…",
      onRow: (r) => openPlayer(r.tid),
      empty: minMin ? `Nobody has ${minMin}+ minutes in these matches.` : "Nobody appeared in the filtered matches.",
    }).node);
    box.append(el("p.note", { text: vsNorm
      ? "▲/▼ is the difference from his own average over every match (friendlies follow the toggle). "
        + "Narrow the filters — a competition, a round, an opponent — and sort a Δ column to see who steps up."
      : M.note }));
    return box;
  }

  // ---------------------------------------------------------------- Results
  function results(ms) {
    const rows = [];
    let season = null;
    const bySeason = new Map();
    for (const m of ms) {
      const o = bySeason.get(m.season) || { w: 0, d: 0, l: 0, pts: 0, p: 0 };
      o.p++; o.pts += m.pts || 0;
      if (m.result) o[m.result.toLowerCase()]++;
      bySeason.set(m.season, o);
    }
    for (const m of byDate(ms)) {
      if (m.season !== season) {
        season = m.season;
        const o = bySeason.get(season);
        rows.push(el("tr.grp", {}, [el("td", { colspan: 8 }, [
          el("b", { text: `${season - 1}/${String(season).slice(2)}` }),
          el("span.dim", { text: ` · ${o.p} played · ${o.w}-${o.d}-${o.l} · ${num(o.pts / o.p, 2)} pts/gm` }),
        ])]));
      }
      rows.push(el("tr", {}, [
        el("td", { text: String(m.date).slice(0, 10) }),
        el("td", { text: comp(m) }),
        el("td", { text: stageText(m) }),
        el("td", { text: m.venue }),
        el("td.name", {}, [clubLink(m)]),
        el("td.num", { text: scoreText(m), title: scoreTitle(m) }),
        el("td", {}, [pill(m.result, RES[m.result] || "flat")]),
        el("td", { text: m.formation || DASH }),
      ]));
    }
    return el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Date", "Competition", "Stage", "H/A", "Opponent", "Score", "", "Started in"]
        .map((h, i) => el(`th${i === 5 ? ".num" : ""}`, {
          text: h, title: i === 7 ? "Our kick-off shape — the slots as they stood at kick-off" : null,
        })))]),
      el("tbody", {}, rows.length ? rows : [el("tr", {}, [el("td.empty", { colspan: 8, text: "No matches in this filter." })])]),
    ])]);
  }

  // ---------------------------------------------------------------- Splits
  // One table, one "split by" control — the season, competition, phase, round and formation
  // tables were the same P/W/D/L table keyed five ways.
  const SPLITS = [
    ["season", "Season", (m) => m.season, (a, b) => b.k - a.k],
    ["competition", "Competition", comp, null],
    ...(hasStages ? [
      ["phase", "Phase", phaseOf, (a, b) => PHASES.indexOf(a.k) - PHASES.indexOf(b.k)],
      ["round", "Round", roundOf, (a, b) => roundCmp(a.k, b.k)],
    ] : []),
    ["formation", "Formation", (m) => m.formation || null, null],
    ["venue", "Home / away", (m) => m.venue || null, (a, b) => "HAN".indexOf(a.k) - "HAN".indexOf(b.k)],
  ];
  function splits(ms) {
    const want = params().get("split");
    const cur = SPLITS.find((s) => s[0] === want) || SPLITS[0];
    const [dim, label, key, order] = cur;
    const seg = el("span.mseg", {}, SPLITS.map(([k, l]) => el(`button.chip${k === dim ? ".on" : ""}`, {
      text: l, onclick: () => { setParams({ split: k }); draw(); },
    })));
    const rows = ms.filter((m) => key(m) != null);
    const notes = {
      formation: "Our kick-off shape, as the game records it: the count of players in each line "
        + "at kick-off, so a preset with a slot moved reads as a different shape.",
      round: "Rounds are the game's own labels, pooled across competitions — a Third Qualifying "
        + "Round is the same round in either cup. Groups pool as \"Group stage\".",
      phase: "League, qualifying, group and knockout matches, from each competition's rules in the save.",
    };
    return el("div", {}, [
      el("div.prow", {}, [el("span.dim", { text: "Split by" }), seg]),
      summaryTable(rows, key, label, {
        order: order || ((a, b) => b.p - a.p || b.pts / b.p - a.pts / a.p),
        fmt: dim === "venue" ? (k) => VENUE[k] || k
          : dim === "season" ? (k) => `${k - 1}/${String(k).slice(2)}` : null,
        action: (r) => focus(dim, r.k),
      }),
      el("p.note", { text: (notes[dim] ? notes[dim] + " " : "")
        + "\"Players ›\" narrows the filters to that row and opens the Players tab." }),
    ]);
  }

  // ---------------------------------------------------------------- Opponents
  function opponents(ms) {
    const minP = [1, 2, 3, 5].includes(Number(lsGet(LS_MINP))) ? Number(lsGet(LS_MINP)) : 1;
    const seg = el("span.mseg", {}, [1, 2, 3, 5].map((n) => el(`button.chip${n === minP ? ".on" : ""}`, {
      text: n === 1 ? "All" : `${n}+`, onclick: () => { lsSet(LS_MINP, n); draw(); },
    })));
    return el("div", {}, [
      el("div.prow", {}, [el("span.dim", { text: "Met at least" }), seg]),
      summaryTable(ms, oppKey, "Opponent", {
        order: (a, b) => b.p - a.p || b.pts / b.p - a.pts / a.p,
        minP, fmt: (k, r) => oppName(r.m),
        open: (r) => openClub(r.m.opp_tid),
        action: (r) => focus("opponent", r.k),
      }),
      el("p.note", { text: "Click a club for its sheet — manager, shapes, every meeting. "
        + "\"Players ›\" shows how our players did against them." }),
    ]);
  }

  // ---------------------------------------------------------------- Team stats
  function stats(ms) {
    const names = f.filter((n) => n.startsWith("our_")).map((n) => n.slice(4));
    if (!names.length) return el("p.note", { text: "No team stats in this export." });
    const rows = names.map((s) => ({ s, us: avg(ms, `our_${s}`), them: avg(ms, `opp_${s}`) }));
    return el("div", {}, [
      el("div.scroll.fit", {}, [el("table.edge", {}, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Per match" }), el("th.num", { text: "Us" }),
          el("th.edgecol", { text: "Edge" }), el("th", { text: "Them" }),
        ])]),
        el("tbody", {}, rows.map(({ s, us, them }) => {
          const edge = us == null || them == null ? null : us - them;
          const share = edge == null || !Math.max(us, them) ? 0 : edge / Math.max(us, them);
          const w = Math.min(50, Math.abs(share) * 100);
          return el("tr", {}, [
            el("td", { text: s.replace(/_/g, " ") }),
            el("td.num", { text: us == null ? DASH : num(us, 1) }),
            el("td.edgecol", { title: edge == null ? "" : `${edge >= 0 ? "+" : ""}${num(edge, 1)} per match` }, [
              el("span.edgetrack", {}, [el(`span.edgebar.${edge >= 0 ? "good" : "bad"}`, {
                style: `width:${w.toFixed(1)}%;${edge >= 0 ? "left:50%" : `left:${(50 - w).toFixed(1)}%`}`,
              })]),
            ]),
            el("td", { text: them == null ? DASH : num(them, 1) }),
          ]);
        })),
      ])]),
      el("p.note", { text: "Averages per match over the filtered set. The bar is our edge as a share "
        + "of the larger side: right and green where we out-do them, left and red where they out-do us." }),
    ]);
  }

  draw();
  return out;
}

/** P/W/D/L by any key, with a points-per-game bar.
 *  order(a, b) sorts rows; fmt(key, row) labels them; minP hides rows played fewer times;
 *  open(row) makes the row a link; action(row) adds a trailing "Players ›" jump. */
function summaryTable(ms, keyFn, label, { order = null, fmt = null, minP = 1, open = null, action = null } = {}) {
  const g = new Map();
  for (const m of ms) {
    const k = keyFn(m);
    const r = g.get(k) || { k, m, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
    r.p++; r.gf += m.gf || 0; r.ga += m.ga || 0; r.pts += m.pts || 0;
    if (m.result === "W") r.w++; else if (m.result === "D") r.d++; else if (m.result === "L") r.l++;
    g.set(k, r);
  }
  const rows = [...g.values()].filter((r) => r.p >= minP)
    .sort(order || ((a, b) => String(a.k).localeCompare(String(b.k))));
  const heads = [label, "P", "W", "D", "L", "GF", "GA", "GD", "Pts/gm"];
  return el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, [...heads.map((h, i) => el(`th${i ? ".num" : ""}`, { text: h })),
      action ? el("th", { text: "" }) : null])]),
    el("tbody", {}, rows.length ? rows.map((r) => el(open ? "tr.click" : "tr", open ? { onclick: () => open(r) } : {}, [
      el("td.name", { text: String(fmt ? fmt(r.k, r) : r.k) }), el("td.num", { text: r.p }),
      el("td.num", { text: r.w }), el("td.num", { text: r.d }), el("td.num", { text: r.l }),
      el("td.num", { text: r.gf }), el("td.num", { text: r.ga }),
      el("td.num", { text: signed(r.gf - r.ga) }),
      el("td.num", {}, [bar(r.pts / r.p, { max: 3, lo: 34, dp: 2 })]),
      action ? el("td", {}, [el("button.link", {
        text: "Players ›", title: "Our players in exactly these matches",
        onclick: (e) => { e.stopPropagation(); action(r); },
      })]) : null,
    ])) : [el("tr", {}, [el("td.empty", { colspan: heads.length + (action ? 1 : 0), text: "Nothing to show." })])]),
  ])]);
}

const shortDate = (d) => {
  const t = new Date(String(d).slice(0, 10));
  return Number.isNaN(+t) ? String(d).slice(0, 10)
    : t.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "2-digit", timeZone: "UTC" });
};
const byDate = (ms) => [...ms].sort((a, b) => String(b.date).localeCompare(String(a.date)));
const signed = (n) => (n >= 0 ? "+" : "") + n;

/** The current run, newest first: "W3", plus the unbeaten / winless run when it is longer. */
function streak(recent) {
  if (!recent.length || !recent[0].result) return { text: "", title: "" };
  const first = recent[0].result;
  let same = 0;
  while (same < recent.length && recent[same].result === first) same++;
  const unbeaten = first !== "L";
  let run = 0;
  while (run < recent.length && (unbeaten ? recent[run].result !== "L" : recent[run].result !== "W")) run++;
  const text = run > same ? `${first}${same} · ${unbeaten ? "unbeaten" : "winless"} in ${run}` : `${first}${same}`;
  return { text, title: `Last 10 results, oldest to newest. Current run: ${text}.` };
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
export function scoreText(m) {
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

/** An opponent's name that opens its club sheet. */
function clubLink(m) {
  const name = m.opponent || `#${m.opp_tid}`;
  return m.opp_tid == null ? name : el("a", {
    href: "#", text: name, onclick: (e) => { e.preventDefault(); openClub(m.opp_tid); },
  });
}

const avg = (ms, k) => {
  const vs = ms.map((m) => m[k]).filter((v) => v != null);
  return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
};
const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
