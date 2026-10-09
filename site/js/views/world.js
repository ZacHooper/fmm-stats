/**
 * World — the reputation ladders (leagues, clubs, nations), each a sortable table with a chart
 * of how the entities in it moved across every snapshot, the transfer market season by season
 * with the world record (transfers.js), plus two maps: our nation's clubs by division, and the
 * stadiums of our current squad's origin clubs.
 *
 * Leagues and clubs need no fetch of their own for the table: `D.S.leagues`/`D.S.clubs` are
 * already loaded from core.json. Nations, the maps and the history behind every chart come from
 * api/world.json, fetched only when this page is opened.
 *
 * The table and its chart are one tool: tapping a row adds it to (or takes it off) the chart,
 * plotted rows carry their line's colour in the table, and the chart's quick picks read the table
 * as filtered and sorted ("first 8 in the table", "biggest risers in the table").
 */
import * as D from "../data.js";
import { el, clear, bar, num, pill, sparkline, toast, DASH } from "../ui.js";
import { playerTable } from "../table.js";
import { lineChart, SLOTS } from "../linechart.js";
import { worldTransfersPanel } from "../transfers.js";

const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";

let leafletPromise = null;
/** Loads Leaflet from a CDN on first use only — the site has no bundler and no other page
 *  needs a mapping library, so this stays out of index.html and out of every other view's
 *  payload. Cached so switching tabs back to Maps doesn't re-fetch or re-inject. */
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      document.head.append(el("link", { rel: "stylesheet", href: LEAFLET_CSS }));
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("Leaflet failed to load"));
    document.head.append(script);
  });
  return leafletPromise;
}

const LS_TAB = "fmworld:tab";
const lsGet = (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } };

export async function view() {
  const world = await D.loadWorld();
  const H = history(world);
  const out = el("div");
  out.append(el("div.sechead", {}, [el("h2", { text: "World" })]));
  out.append(headline(world, H));

  const tabs = el("div.prow.wtabs");
  const panel = el("div");
  const TABS = [
    ["Leagues", () => leaguesPanel(H)],
    ["Clubs", () => clubsPanel(H)],
    ["Nations", () => nationsPanel(world, H)],
    ["Maps", () => mapsPanel(world)],
    // last, so a remembered tab index (LS_TAB) still opens the tab it did
    ["Transfers", () => worldTransfersPanel()],
  ];
  let active = Math.min(Math.max(+lsGet(LS_TAB) || 0, 0), TABS.length - 1);
  const drawTabs = () => {
    tabs.replaceChildren(...TABS.map(([label], i) => el(`button.chip${i === active ? ".on" : ""}`, {
      text: label,
      onclick: async () => {
        active = i; lsSet(LS_TAB, i); drawTabs();
        clear(panel).append(el("div.spinner", { text: "…" }));
        clear(panel).append(await TABS[i][1]());
      },
    })));
  };
  drawTabs();
  out.append(tabs, panel);
  panel.append(await TABS[active][1]());
  return out;
}

// --------------------------------------------------------------------------- history
/** Decodes world.json's run-length history ([i0, v0, i1, v1, ...] change points) into one
 *  value per snapshot date. An older export without history yields empty series, and every
 *  chart then says so instead of breaking the page. */
function history(world) {
  const h = world?.history;
  const dates = h?.dates || [];
  const n = dates.length;
  const expand = (flat) => {
    const out = new Array(n).fill(null);
    if (!flat) return out;
    for (let k = 0; k < flat.length; k += 2) {
      const end = k + 2 < flat.length ? flat[k + 2] : n;
      out.fill(flat[k + 1], flat[k], end);
    }
    return out;
  };
  // "a season ago": the snapshot nearest 365 days before the newest one
  const last = n ? Date.parse(dates[n - 1]) : 0;
  let ago = 0;
  dates.forEach((d, i) => {
    if (Math.abs(Date.parse(d) - last + 365 * 864e5) < Math.abs(Date.parse(dates[ago]) - last + 365 * 864e5)) ago = i;
  });
  return {
    dates, n, ago: n > 1 ? ago : null,
    league: (cid) => {
      const r = h?.leagues?.[cid];
      return { tier: r?.tier ?? null, reputation: expand(r?.reputation), skill_idx: expand(r?.skill_idx) };
    },
    club: (tid) => ({ reputation: expand(h?.clubs?.[tid]) }),
    nation: (name) => {
      const r = h?.nations?.[name];
      return { world_rank: expand(r?.world_rank), ranking_points: expand(r?.ranking_points),
               coefficient: expand(r?.coefficient), coefficient_5: expand(r?.coefficient_5),
               uefa_rank: expand(r?.uefa_rank) };
    },
  };
}

/** Change over the last season: now minus the value a year ago (null if either is missing). */
function delta(H, values) {
  if (H.ago == null || !values?.length) return null;
  const a = values[H.ago], b = values[values.length - 1];
  return a == null || b == null ? null : b - a;
}

function deltaCell(v, { dp = 0, invert = false } = {}) {
  if (v == null) return el("span.dim", { text: DASH });
  if (!v) return el("span.dim", { text: "0" });
  const good = invert ? v < 0 : v > 0;
  return el(`span.${good ? "up" : "down"}`, { text: `${v > 0 ? "+" : "−"}${num(Math.abs(v), dp)}` });
}

// --------------------------------------------------------------------------- headline
/** Where we stand: our league, our club and our nation, each ranked and with a season's move. */
function headline(world, H) {
  const ourCid = D.ourLeagueCid();
  const lgs = [...D.S.leagues.values()].filter((l) => l.reputation != null)
    .sort((a, b) => b.reputation - a.reputation);
  const lg = D.S.leagues.get(ourCid);
  const club = D.S.clubs.get(D.S.ours.managed_tid);
  const nationClubs = [...D.S.clubs.values()]
    .filter((c) => c.reputation != null && c.nation === club?.nation)
    .sort((a, b) => b.reputation - a.reputation);
  const nation = (world?.nations || []).find((n) => n.name === world?.our_nation);
  const tile = (label, value, sub, d) => el("div.kpi.wkpi", {}, [
    el("span", { text: label }),
    el("b", { text: value }),
    el("div.wsub", {}, [sub, d ? " · " : null, d]),
  ]);
  const tiles = [];
  if (lg) {
    tiles.push(tile(lg.name, `#${lgs.indexOf(lg) + 1}`,
      `of ${lgs.length} leagues · rep ${lg.reputation}`,
      deltaCell(delta(H, H.league(ourCid).reputation))));
  }
  if (club) {
    tiles.push(tile(club.name, `#${nationClubs.indexOf(club) + 1}`,
      `in ${club.nation || "nation"} · rep ${num(club.reputation)}`,
      deltaCell(delta(H, H.club(club.tid).reputation))));
  }
  if (nation) {
    // a rank's move as places climbed (+), the same way round as the tables' ± rank
    const h = H.nation(nation.name);
    const moved = (vs) => deltaCell(delta(H, vs) == null ? null : -delta(H, vs));
    tiles.push(tile(nation.name, `#${nation.rank}`,
      `in the world · ${num(nation.points)} pts`, moved(h.world_rank)));
    if (nation.uefa_rank) {
      const members = (world.nations || []).filter((n) => n.uefa_rank != null).length;
      tiles.push(tile(`${nation.name} · UEFA`, `#${nation.uefa_rank}`,
        `of ${members} · coef ${num(h.coefficient_5.at(-1), 3)}`, moved(h.uefa_rank)));
    }
  }
  return tiles.length ? el("div.kpis", {}, tiles) : el("div");
}

// --------------------------------------------------------------------------- table + chart
/**
 * A sortable table and, under it, a chart of the same entities over time.
 *
 * @param {object} c
 *   H         the decoded history (history(world))
 *   key       persistence key (table sort/columns, chart metric + selection)
 *   rows      [{tid, name, _search, ...}] — `tid` is the series key
 *   series    (row) => {metricId: values[]} — its history, one value per snapshot
 *   metrics   [{id, label, dp?, invert?}] chartable metrics; the first is the default
 *   catalogue, defaults, sort, searchPlaceholder — passed to playerTable (`name` must exist)
 *   toolbar   extra filter controls for the table; `filter` the matching predicate
 *   quick     (ctx) => [{label, group?, keys: () => [tid]}] quick picks; ctx has
 *             {tableRows(), metric, top(rows, n)}
 *   initial   () => [tid] the selection the first time the panel is ever opened
 *   ours      Set of tids to emphasise
 *   note      the table's footnote
 */
function tableAndChart(c) {
  const LS = `fmworld:${c.key}`;
  const saved = lsGet(LS) || {};
  const byKey = new Map(c.rows.map((r) => [r.tid, r]));
  let metric = c.metrics.find((m) => m.id === saved.metric) || c.metrics[0];
  // tid -> colour slot. A slot sticks to its entity until it is removed, so a line never
  // changes colour because another one came or went.
  const picked = new Map((saved.picked || []).filter(([k]) => byKey.has(k)));
  if (!saved.picked) c.initial().slice(0, SLOTS).forEach((k, i) => byKey.has(k) && picked.set(k, i));
  const persist = () => lsSet(LS, { metric: metric.id, picked: [...picked] });

  const freeSlot = () => { for (let s = 0; s < SLOTS; s++) if (![...picked.values()].includes(s)) return s; return null; };
  const add = (k) => {
    if (picked.has(k) || !byKey.has(k)) return;
    const s = freeSlot();
    if (s == null) { toast(`Up to ${SLOTS} lines at once — remove one first.`); return; }
    picked.set(k, s);
  };
  const setAll = (keys) => {
    picked.clear();
    keys.filter((k) => byKey.has(k)).slice(0, SLOTS).forEach((k, i) => picked.set(k, i));
  };
  const changed = () => { persist(); table.redraw(); drawChart(); };

  // Swatch on the name, so the table doubles as the chart's key.
  const nameDef = c.catalogue.name;
  const catalogue = {
    ...c.catalogue,
    name: {
      ...nameDef,
      render: (r) => el("span.wname", {}, [
        el(`i.wsw${picked.has(r.tid) ? `.s${picked.get(r.tid)}` : ".off"}`, {
          title: picked.has(r.tid) ? "On the chart — tap the row to remove" : "Tap the row to chart it",
        }),
        nameDef.render ? nameDef.render(r) : r.name,
      ]),
    },
  };
  const table = playerTable({
    key: `world-${c.key}`, rows: c.rows, catalogue, defaults: c.defaults, sort: c.sort,
    sticky: ["name"], searchPlaceholder: c.searchPlaceholder, toolbar: c.toolbar, filter: c.filter,
    rowClass: (r) => (picked.has(r.tid) ? "picked" : null),
    onRow: (r) => { if (picked.has(r.tid)) picked.delete(r.tid); else add(r.tid); changed(); },
  });

  // ---- chart controls
  const metricSeg = el("span.seg");
  const drawSeg = () => metricSeg.replaceChildren(...c.metrics.map((m) => el(`button${m === metric ? ".on" : ""}`, {
    type: "button", text: m.label,
    onclick: () => { metric = m; drawSeg(); persist(); drawChart(); },
  })));
  drawSeg();

  const top = (rows, n = SLOTS) => rows.slice(0, n).map((r) => r.tid);
  const ctx = { tableRows: () => table.rows(), get metric() { return metric; }, top };
  const moved = (sign) => {
    const scored = table.rows().map((r) => ({ r, d: delta(c.H, c.series(r)[metric.id]) }))
      .filter((x) => x.d != null && x.d !== 0)
      .map((x) => ({ ...x, d: metric.invert ? -x.d : x.d }))
      .filter((x) => sign * x.d > 0)
      .sort((a, b) => sign * (b.d - a.d));
    return scored.slice(0, SLOTS).map((x) => x.r.tid);
  };
  const picks = [
    { label: `First ${SLOTS} in the table`, keys: () => top(table.rows()) },
    { label: "Biggest risers in the table (a season)", keys: () => moved(1) },
    { label: "Biggest fallers in the table (a season)", keys: () => moved(-1) },
    ...c.quick(ctx),
  ];
  const quick = el("select.btn.wquick", { "aria-label": "Quick pick" });
  const groups = new Map();
  quick.append(el("option", { value: "", text: "Quick pick…" }));
  picks.forEach((p, i) => {
    const o = el("option", { value: String(i), text: p.label });
    if (!p.group) { quick.append(o); return; }
    if (!groups.has(p.group)) { groups.set(p.group, el("optgroup", { label: p.group })); quick.append(groups.get(p.group)); }
    groups.get(p.group).append(o);
  });
  quick.addEventListener("change", () => {
    const p = picks[+quick.value];
    quick.value = "";
    if (!p) return;
    const keys = p.keys();
    if (!keys.length) { toast("Nothing in the table fits that pick."); return; }
    setAll(keys); changed();
  });

  // add one by name — a datalist, so it's a native picker on a phone too
  const listId = `wl-${c.key}`;
  const label = (r) => (r.sub ? `${r.name} · ${r.sub}` : r.name);
  const byLabel = new Map(c.rows.map((r) => [label(r), r.tid]));
  const finder = el("input.search.wfind", { type: "search", placeholder: "Add to chart…", list: listId, "aria-label": "Add to chart" });
  const datalist = el("datalist", { id: listId }, c.rows.map((r) => el("option", { value: label(r) })));
  finder.addEventListener("change", () => {
    const k = byLabel.get(finder.value);
    if (k == null) return;
    finder.value = "";
    add(k); changed();
  });
  const clearBtn = el("button.btn", { type: "button", text: "Clear", onclick: () => { picked.clear(); changed(); } });

  const legend = el("div.wlegend");
  const chartBox = el("div");
  const head = el("div.whead", {}, [el("h3", { text: "Over time" }), metricSeg]);
  function drawChart() {
    const sel = [...picked].map(([k, slot]) => ({ r: byKey.get(k), slot }));
    legend.replaceChildren(...sel.map(({ r, slot }) => el("span.wchip", {}, [
      el(`i.wsw.s${slot}`), r.name,
      el("button.x", { type: "button", text: "✕", title: `Remove ${r.name}`,
        onclick: () => { picked.delete(r.tid); changed(); } }),
    ])), sel.length ? el("span.dim.wcount", { text: `${sel.length}/${SLOTS}` }) : null);
    chartBox.replaceChildren(lineChart({
      dates: c.H.dates, dp: metric.dp ?? 0, invert: !!metric.invert, label: metric.label,
      series: sel.map(({ r, slot }) => ({ key: r.tid, label: r.name, slot, ours: c.ours?.has(r.tid),
        values: c.series(r)[metric.id] })),
    }));
  }
  drawChart();

  const node = el("div", {}, [
    table.node,
    c.note ? el("p.note", { html: c.note }) : null,
    el("div.card.wchart", {}, [
      head,
      el("div.tbar", {}, [quick, finder, datalist, clearBtn]),
      legend, chartBox,
      el("p.note", { text: "Tap a table row to add or remove its line. Quick picks read the table as "
        + "it stands — filter or sort it first to aim them. The x-axis is the calendar; a gap in a "
        + "line is a snapshot with no value, not a zero." }),
    ]),
  ]);
  // The filter selects belong to the caller; a change to one redraws the table through this.
  node.redrawTable = () => table.redraw();
  return node;
}
const nationOptions = (rows) => {
  const sel = el("select.btn");
  const nations = [...new Set(rows.map((r) => r.nation).filter(Boolean))].sort();
  sel.append(el("option", { value: "", text: "All nations" }), ...nations.map((n) => el("option", { value: n, text: n })));
  return sel;
};

// --------------------------------------------------------------------------- leagues
function leaguesPanel(H) {
  const ourCid = D.ourLeagueCid();
  const ourNation = D.S.leagues.get(ourCid)?.nation;
  const lgs = [...D.S.leagues.values()].filter((l) => l.reputation != null)
    .sort((a, b) => b.reputation - a.reputation)
    .map((l, i) => {
      const h = H.league(l.cid);
      return { ...l, tid: l.cid, rank: i + 1, tier: h.tier, hist: h, sub: l.nation,
               dRep: delta(H, h.reputation), _search: `${l.name} ${l.nation || ""}`.toLowerCase() };
    });
  const ourLg = lgs.find((l) => l.cid === ourCid);

  const nationSel = nationOptions(lgs);
  const tierSel = el("select.btn", {}, [el("option", { value: "", text: "All tiers" }),
    ...[...new Set(lgs.map((l) => l.tier).filter((t) => t != null))].sort((a, b) => a - b)
      .map((t) => el("option", { value: String(t), text: `Tier ${t}` }))]);
  const filter = (l) => (!nationSel.value || l.nation === nationSel.value)
    && (!tierSel.value || String(l.tier) === tierSel.value);

  const byRep = (rows) => [...rows].sort((a, b) => b.reputation - a.reputation);
  const nations = [...new Set(lgs.map((l) => l.nation).filter(Boolean))]
    .map((n) => ({ n, best: Math.max(...lgs.filter((l) => l.nation === n).map((l) => l.reputation)) }))
    .sort((a, b) => b.best - a.best).map((x) => x.n);
  const tiers = [...new Set(lgs.map((l) => l.tier).filter((t) => t != null))].sort((a, b) => a - b);

  const node = tableAndChart({
    key: "leagues", H, rows: lgs, ours: new Set([ourCid]),
    series: (r) => r.hist,
    metrics: [{ id: "reputation", label: "Reputation" }, { id: "skill_idx", label: "Skill idx", dp: 1 }],
    catalogue: {
      rank: { label: "#", align: "num", get: (r) => r.rank, help: "Rank by reputation, worldwide" },
      name: { label: "League", get: (r) => r.name,
              render: (r) => el("span", {}, [r.name, r.cid === ourCid ? pill(" us", "good") : null]) },
      nation: { label: "Nation", get: (r) => r.nation },
      tier: { label: "Tier", align: "num", get: (r) => r.tier, help: "Division level in its nation, 1 = top flight" },
      reputation: { label: "Reputation", align: "num", get: (r) => r.reputation },
      dRep: { label: "± season", align: "num", get: (r) => r.dRep, render: (r) => deltaCell(r.dRep),
              help: "Reputation change over the last season" },
      trend: { label: "Trend", get: (r) => r.dRep, sort: (r) => r.dRep,
               render: (r) => sparkline(r.hist.reputation, { w: 64, h: 16 }), help: "Reputation across every snapshot" },
      skillIdx: { label: "Skill idx", align: "num", get: (r) => r.skillIdx, render: (r) => bar(r.skillIdx) },
      clubs: { label: "Clubs", align: "num", get: (r) => r.clubs || null },
      rated: { label: "Rated", align: "num", get: (r) => r.rated, help: "Rated players behind the skill index" },
    },
    defaults: ["rank", "name", "nation", "tier", "reputation", "dRep", "trend", "skillIdx", "clubs"],
    sort: { by: "reputation", dir: "desc" },
    searchPlaceholder: "Search leagues or nations…",
    toolbar: [nationSel, tierSel], filter,
    initial: () => byRep(lgs.filter((l) => l.nation === ourNation)).map((l) => l.cid),
    quick: () => [
      ...(ourNation ? [{ label: `${ourNation}'s divisions`, keys: () => byRep(lgs.filter((l) => l.nation === ourNation)).map((l) => l.cid) }] : []),
      { label: `Top ${SLOTS} in the world`, keys: () => byRep(lgs).slice(0, SLOTS).map((l) => l.cid) },
      ...(ourLg ? [{ label: "Our neighbours on the ladder", keys: () => {
        const i = ourLg.rank - 1;
        return lgs.slice(Math.max(0, i - 3), i + 5).map((l) => l.cid);
      } }] : []),
      ...tiers.map((t) => ({ group: "Top of a tier", label: `Tier ${t}`,
        keys: () => byRep(lgs.filter((l) => l.tier === t)).map((l) => l.cid) })),
      ...nations.map((n) => ({ group: "A nation's divisions", label: n,
        keys: () => byRep(lgs.filter((l) => l.nation === n)).map((l) => l.cid) })),
    ],
    note: "<b>Reputation</b> is a value parsed straight from each competition record. "
      + "<b>Skill idx</b> is the average player ability in that league normalised 0-100 across "
      + "ranked leagues — a CA-derived index in the same sanctioned form as a Level percentile, "
      + "never the number itself. Only leagues with 20+ rated players get one. "
      + "<b>Clubs</b> counts actual club records, not the competition record's member count — "
      + "that field is unreliable (it reads 5 for a 12-team division), so it isn't shown. "
      + "<b>± season</b> compares the newest snapshot with the one nearest a year earlier.",
  });
  [nationSel, tierSel].forEach((s) => s.addEventListener("change", () => node.redrawTable()));
  return panelWrap(`League reputation · ${lgs.length} leagues`, node);
}

// --------------------------------------------------------------------------- clubs
function clubsPanel(H) {
  const ourTids = new Set(D.S.ours.clubs || []);
  const ourCid = D.ourLeagueCid();
  const us = D.S.clubs.get(D.S.ours.managed_tid);
  const clubs = [...D.S.clubs.values()].filter((c) => c.reputation != null)
    .sort((a, b) => b.reputation - a.reputation)
    .map((c, i) => {
      const h = H.club(c.tid);
      const leagueName = D.S.leagues.get(c.leagueCid)?.name || null;
      return { ...c, rank: i + 1, leagueName, hist: h, sub: [leagueName, c.nation].filter(Boolean).join(", "),
               dRep: delta(H, h.reputation),
               _search: `${c.name} ${c.nation || ""} ${leagueName || ""}`.toLowerCase() };
    });

  const nationSel = nationOptions(clubs);
  const leagueSel = el("select.btn");
  const drawLeagueOptions = () => {
    const want = nationSel.value;
    const inScope = want ? clubs.filter((c) => c.nation === want) : clubs;
    const lgs = [...new Map(inScope.filter((c) => c.leagueName)
      .map((c) => [c.leagueCid, c.leagueName])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    const prev = leagueSel.value;
    leagueSel.replaceChildren(el("option", { value: "", text: "All leagues" }),
      ...lgs.map(([cid, name]) => el("option", { value: cid, text: name })));
    leagueSel.value = lgs.some(([cid]) => String(cid) === prev) ? prev : "";
  };
  drawLeagueOptions();
  const filter = (c) => (!nationSel.value || c.nation === nationSel.value)
    && (!leagueSel.value || String(c.leagueCid) === leagueSel.value);

  const byRep = (rows) => [...rows].sort((a, b) => b.reputation - a.reputation);
  // Quick picks by league follow the league ladder: ours and its nation first, then the rest by
  // reputation, so the useful options are at the top of a long list.
  const leagues = [...new Set(clubs.map((c) => c.leagueCid).filter((x) => x != null))]
    .map((cid) => D.S.leagues.get(cid)).filter(Boolean)
    .sort((a, b) => (b.nation === us?.nation) - (a.nation === us?.nation) || (b.reputation ?? 0) - (a.reputation ?? 0));
  const nations = [...new Set(clubs.map((c) => c.nation).filter(Boolean))].sort();

  const node = tableAndChart({
    key: "clubs", H, rows: clubs, ours: ourTids,
    series: (r) => r.hist,
    metrics: [{ id: "reputation", label: "Reputation" }],
    catalogue: {
      rank: { label: "#", align: "num", get: (r) => r.rank, help: "Rank by reputation, worldwide" },
      name: { label: "Club", get: (r) => r.name,
              render: (r) => el("span", {}, [r.name, ourTids.has(r.tid) ? pill(" us", "good") : null]) },
      nation: { label: "Nation", get: (r) => r.nation },
      league: { label: "League", get: (r) => r.leagueName },
      reputation: { label: "Reputation", align: "num", get: (r) => r.reputation },
      dRep: { label: "± season", align: "num", get: (r) => r.dRep, render: (r) => deltaCell(r.dRep),
              help: "Reputation change over the last season" },
      trend: { label: "Trend", get: (r) => r.dRep, sort: (r) => r.dRep,
               render: (r) => sparkline(r.hist.reputation, { w: 64, h: 16 }), help: "Reputation across every snapshot" },
      players: { label: "Squad", align: "num", get: (r) => r.players },
    },
    defaults: ["rank", "name", "nation", "league", "reputation", "dRep", "trend", "players"],
    sort: { by: "reputation", dir: "desc" },
    searchPlaceholder: "Search clubs, leagues or nations…",
    toolbar: [nationSel, leagueSel], filter,
    initial: () => {
      const mine = byRep(clubs.filter((c) => c.leagueCid === ourCid)).map((c) => c.tid);
      return [...(us ? [us.tid] : []), ...mine.filter((t) => t !== us?.tid)];
    },
    quick: () => [
      ...(ourCid != null ? [{ label: "Our league's top clubs (and us)", keys: () => {
        const mine = byRep(clubs.filter((c) => c.leagueCid === ourCid)).map((c) => c.tid);
        return [...(us ? [us.tid] : []), ...mine.filter((t) => t !== us?.tid)];
      } }] : []),
      { label: `Top ${SLOTS} in the world`, keys: () => byRep(clubs).slice(0, SLOTS).map((c) => c.tid) },
      ...leagues.map((l) => ({ group: "A league's top clubs", label: `${l.name}${l.nation ? ` (${l.nation})` : ""}`,
        keys: () => byRep(clubs.filter((c) => c.leagueCid === l.cid)).map((c) => c.tid) })),
      ...nations.map((n) => ({ group: "A nation's top clubs", label: n,
        keys: () => byRep(clubs.filter((c) => c.nation === n)).map((c) => c.tid) })),
    ],
    note: "Reputation is parsed straight from each club's own record (distinct from its league's "
      + "reputation, on the Leagues tab). Only clubs with a parsed squad appear at all — an empty "
      + "club can't be rendered anywhere on the site. League and nation are where the club is "
      + "<i>now</i>; its line on the chart runs through every division it has been in.",
  });
  nationSel.addEventListener("change", () => { drawLeagueOptions(); node.redrawTable(); });
  leagueSel.addEventListener("change", () => node.redrawTable());
  return panelWrap(`Club reputation · ${clubs.length} clubs`, node);
}

// --------------------------------------------------------------------------- nations
const LS_NATIONS = "fmworld:nations-view";
/** Nations: the world ranking, or the UEFA association ranking — two tables, one switch. */
function nationsPanel(world, H) {
  const src = world?.nations || [];
  if (!src.length) return el("p.note", { text: "No nation data in this export." });
  const uefa = src.some((n) => n.uefa_rank != null);
  const views = [["world", "World ranking", () => worldRanking(world, H)],
                 ...(uefa ? [["uefa", "UEFA coefficients", () => uefaRanking(world, H)]] : [])];
  let view = views.find(([k]) => k === lsGet(LS_NATIONS)) || views[0];
  const seg = el("span.seg");
  const box = el("div");
  const draw = () => {
    seg.replaceChildren(...views.map((v) => el(`button${v === view ? ".on" : ""}`, {
      type: "button", text: v[1], onclick: () => { view = v; lsSet(LS_NATIONS, v[0]); draw(); },
    })));
    box.replaceChildren(view[2]());
  };
  draw();
  return el("div", {}, [views.length > 1 ? el("div.prow", {}, [seg]) : null, box]);
}

function worldRanking(world, H) {
  const src = world.nations;
  const ourName = world?.our_nation;
  const rows = src.map((n) => {
    const h = H.nation(n.name);
    return { ...n, tid: n.name, hist: h, dRank: delta(H, h.world_rank),
             dPts: delta(H, h.ranking_points), dCoef: delta(H, h.coefficient),
             _search: `${n.name} ${n.rival || ""}`.toLowerCase() };
  });
  const ours = rows.find((n) => n.name === ourName);
  const byRank = (rs) => [...rs].sort((a, b) => a.rank - b.rank);

  const node = tableAndChart({
    key: "nations", H, rows, ours: new Set([ourName]),
    series: (r) => r.hist,
    metrics: [{ id: "ranking_points", label: "Points" }, { id: "coefficient", label: "Coefficient", dp: 1 },
              { id: "world_rank", label: "Rank", invert: true }],
    catalogue: {
      rank: { label: "#", align: "num", get: (r) => r.rank, help: "World ranking" },
      dRank: { label: "± rank", align: "num", get: (r) => (r.dRank == null ? null : -r.dRank),
               render: (r) => deltaCell(r.dRank == null ? null : -r.dRank),
               help: "Places climbed (+) or dropped (−) over the last season" },
      name: { label: "Nation", get: (r) => r.name,
              render: (r) => el("span", {}, [r.name, r.name === ourName ? pill(" us", "good") : null, coefInfo(r)]) },
      points: { label: "Points", align: "num", get: (r) => r.points },
      dPts: { label: "± pts", align: "num", get: (r) => r.dPts, render: (r) => deltaCell(r.dPts),
              help: "Ranking points change over the last season" },
      coefficient: { label: "Coefficient", align: "num", get: (r) => r.coefficient,
                     render: (r) => coefCell(r, r.coefficient), help: "Sum of every season the save keeps (ten, plus the one in progress) — hover or tap for the seasons" },
      coef5: { label: "5 seasons", align: "num", get: (r) => coefSum(r, 5),
               render: (r) => coefCell(r, coefSum(r, 5)), help: "Coefficient over the last five completed seasons — hover or tap for the seasons" },
      dCoef: { label: "± coef", align: "num", get: (r) => r.dCoef, render: (r) => deltaCell(r.dCoef, { dp: 1 }),
               help: "Coefficient change over the last season" },
      trend: { label: "Trend", get: (r) => r.dPts, sort: (r) => r.dPts,
               render: (r) => sparkline(r.hist.ranking_points, { w: 64, h: 16 }), help: "Ranking points across every snapshot" },
      rival: { label: "Rival", get: (r) => r.rival },
    },
    defaults: ["rank", "dRank", "name", "points", "dPts", "trend", "coef5", "coefficient", "dCoef", "rival"],
    sort: { by: "rank", dir: "asc" },
    searchPlaceholder: "Search nations…",
    initial: () => {
      const top = byRank(rows).slice(0, SLOTS - 1).map((n) => n.name);
      return ours && !top.includes(ourName) ? [ourName, ...top] : top;
    },
    quick: () => [
      { label: `Top ${SLOTS} in the world`, keys: () => byRank(rows).slice(0, SLOTS).map((n) => n.name) },
      ...(ours ? [
        { label: `Around ${ourName} in the ranking`, keys: () => {
          const r = byRank(rows), i = r.indexOf(ours);
          return [ourName, ...r.slice(Math.max(0, i - 3), i + 5).map((n) => n.name).filter((n) => n !== ourName)];
        } },
        ...(ours.rival ? [{ label: `${ourName} and ${ours.rival}`, keys: () => [ourName, ours.rival] }] : []),
      ] : []),
    ],
    note: "World ranking + UEFA-style coefficient (sum of the nation's own competition history), "
      + "parsed from the save's national-team records. Only ranked nations are shown. "
      + "<b>5 seasons</b> sums the last five completed seasons; hover or tap either coefficient, "
      + "or the ⓘ beside a nation's name, for the season-by-season breakdown. Only European coefficients move during the save — "
      + "every other nation's is the game's starting value, never updated. "
      + "On the chart, <b>Rank</b> is drawn with #1 at the top.",
  });
  return panelWrap(`World ranking · ${rows.length} nations`, node);
}

/**
 * The UEFA association ranking, as the game ranks it: members only, by the sum of their five
 * newest completed seasons (`uefa_rank` comes ranked from site.nations). One column per season,
 * oldest on the left, so a row reads like the in-game table.
 */
function uefaRanking(world, H) {
  const ourName = world?.our_nation;
  const rows = world.nations.filter((n) => n.uefa_rank != null).map((n) => {
    const h = H.nation(n.name);
    const done = completedSeasons(n);           // newest first
    // the total the ranking is on, unrounded upstream — summing the rounded seasons can be a
    // thousandth out (Spain: 92.999 against the ranking's 93.000)
    const exact = h.coefficient_5.at(-1);
    return { ...n, tid: n.name, hist: h, last5: done.slice(0, 5).reverse(), coef5: exact ?? coefSum(n, 5),
             dUefa: delta(H, h.uefa_rank), dCoef5: delta(H, h.coefficient_5),
             _search: n.name.toLowerCase() };
  });
  const ours = rows.find((n) => n.name === ourName);
  const byRank = (rs) => [...rs].sort((a, b) => a.uefa_rank - b.uefa_rank);
  // every member's history moves together, so the first row's labels name every row's seasons
  const labels = (rows.find((r) => r.season != null) || rows[0])?.last5.map((x) => x.label) || [];
  const seasonCols = Object.fromEntries(labels.map((label, i) => [`s${i}`, {
    label, align: "num", get: (r) => r.last5[i]?.v ?? null, render: (r) => coefFmt(r.last5[i]?.v),
    help: `Coefficient earned in ${label}`,
  }]));

  const node = tableAndChart({
    key: "uefa", H, rows, ours: new Set([ourName]),
    series: (r) => r.hist,
    metrics: [{ id: "coefficient_5", label: "Coefficient", dp: 3 }, { id: "uefa_rank", label: "Rank", invert: true }],
    catalogue: {
      rank: { label: "#", align: "num", get: (r) => r.uefa_rank, help: "UEFA association ranking" },
      dRank: { label: "± rank", align: "num", get: (r) => (r.dUefa == null ? null : -r.dUefa),
               render: (r) => deltaCell(r.dUefa == null ? null : -r.dUefa),
               help: "Places climbed (+) or dropped (−) over the last season" },
      name: { label: "Nation", get: (r) => r.name,
              render: (r) => el("span", {}, [r.name, r.name === ourName ? pill(" us", "good") : null, coefInfo(r)]) },
      ...seasonCols,
      coef5: { label: "Total", align: "num", get: (r) => r.coef5, cls: "strong",
               render: (r) => coefCell(r, r.coef5, 3), help: "The five seasons summed — what the ranking is on" },
      dCoef5: { label: "± total", align: "num", get: (r) => r.dCoef5, render: (r) => deltaCell(r.dCoef5, { dp: 1 }),
                help: "Change in the five-season total over the last season" },
      trend: { label: "Trend", get: (r) => r.dCoef5, sort: (r) => r.dCoef5,
               render: (r) => sparkline(r.hist.coefficient_5, { w: 64, h: 16 }), help: "Five-season total across every snapshot" },
      coefficient: { label: "10 seasons", align: "num", get: (r) => coefSum(r, 10),
                     render: (r) => coefCell(r, coefSum(r, 10)), help: "The ten completed seasons the save keeps, summed" },
    },
    // the total before the seasons: on a phone only the first few columns are on screen
    defaults: ["rank", "dRank", "name", "coef5", "dCoef5", ...Object.keys(seasonCols), "trend"],
    sort: { by: "rank", dir: "asc" },
    searchPlaceholder: "Search UEFA nations…",
    initial: () => {
      const top = byRank(rows).slice(0, SLOTS - 1).map((n) => n.name);
      return ours && !top.includes(ourName) ? [ourName, ...top] : top;
    },
    quick: () => [
      { label: `Top ${SLOTS} in Europe`, keys: () => byRank(rows).slice(0, SLOTS).map((n) => n.name) },
      ...(ours ? [{ label: `Around ${ourName} in the ranking`, keys: () => {
        const r = byRank(rows), i = r.indexOf(ours);
        return [ourName, ...r.slice(Math.max(0, i - 3), i + 5).map((n) => n.name).filter((n) => n !== ourName)];
      } }] : []),
      ...(ours?.rival && rows.some((r) => r.name === ours.rival)
        ? [{ label: `${ourName} and ${ours.rival}`, keys: () => [ourName, ours.rival] }] : []),
    ],
    note: "UEFA's association ranking as the game keeps it: each member's coefficient from its "
      + "clubs' European results, ranked on the <b>five newest completed seasons</b> (ties to the "
      + "better newest season). The season in progress isn't counted — the save holds it at 0 "
      + "until the season closes in June, when the oldest season drops off and the ranking moves. "
      + "Hover or tap a total, or the ⓘ, for all ten seasons the save keeps.",
  });
  return panelWrap(`UEFA coefficients · ${rows.length} nations`, node);
}

// --------------------------------------------------------------------------- coefficients
/** The completed seasons of a nation's coefficient history, newest first: [{label, v}].
 *  `seasons` is oldest first with the season in progress last; `season` is the end year of the
 *  newest completed one (null where the history never moves, so no season can be named). */
function completedSeasons(n) {
  const s = n.seasons || [];
  const done = s.slice(0, -1).reverse();
  return done.map((v, k) => {
    const end = n.season != null ? n.season - k : null;
    return { v, label: end != null ? `${String(end - 1).slice(2)}/${String(end).slice(2)}` : `${k + 1} back` };
  });
}
/** A coefficient as UEFA prints one: three decimals. */
const coefFmt = (v) => (v == null ? DASH : num(v, 3));
const coefSum = (n, k) => (n.seasons ? completedSeasons(n).slice(0, k).reduce((a, x) => a + x.v, 0) : null);

/** A coefficient that opens its season-by-season breakdown: on hover where there is hover, on a
 *  tap everywhere. The tap is kept from the row, which would otherwise toggle its chart line. */
function coefCell(n, v, dp = 1) {
  if (v == null) return el("span.dim", { text: DASH });
  const node = el("span.hc", { text: dp === 3 ? coefFmt(v) : num(v, dp), tabindex: "0" });
  if (n.seasons) hoverCard(node, () => coefCard(n));
  return node;
}

/** The same breakdown from a button beside the nation's name — on a phone the coefficient
 *  columns sit off-screen to the right, and the rest of the row toggles the chart. */
function coefInfo(n) {
  if (!n.seasons) return null;
  const b = el("button.hcinfo", { type: "button", text: "i", title: `${n.name}: coefficient by season`,
    "aria-label": `${n.name}: coefficient by season` });
  hoverCard(b, () => coefCard(n));
  return b;
}

function coefCard(n) {
  const done = completedSeasons(n).slice(0, 10);
  const live = (n.seasons || []).at(-1);
  const max = Math.max(...done.map((x) => x.v), live || 0) || 1;
  const row = (label, v, cls = "") => el(`tr${cls}`, {}, [
    el("td", { text: label }),
    el("td.cbar", {}, [el("span", { style: `width:${((100 * v) / max).toFixed(0)}%` })]),
    el("td.num", { text: coefFmt(v) }),
  ]);
  const tot = (k) => el("div.ctot", {}, [el("span", { text: `Last ${k} seasons` }),
    el("b", { text: coefFmt(done.slice(0, k).reduce((a, x) => a + x.v, 0)) })]);
  return [
    el("strong", { text: `${n.name} · coefficient` }),
    el("div.ctots", {}, [tot(5), tot(10)]),
    el("table.ctable", {}, [el("tbody", {}, [
      live ? row(n.season != null ? `${String(n.season).slice(2)}/${String(n.season + 1).slice(2)} so far` : "In progress", live, ".now") : null,
      ...done.map((x, k) => row(x.label, x.v, k === 4 ? ".cut" : "")),
    ])]),
    n.live ? null : el("p.note", { text: "The game's starting values — this nation's coefficient never changes in the save." }),
  ];
}

let openCard = null;
/** A small floating card for `anchor`, built by `build()` each time it opens. Fixed-position on
 *  the page rather than inside the anchor, so a table's scroll box can't clip it. */
function hoverCard(anchor, build) {
  let card = null, pinned = false;
  const close = () => {
    card?.remove(); card = null; pinned = false;
    anchor.classList.remove("on");
    if (openCard?.anchor === anchor) openCard = null;
  };
  const open = () => {
    if (card) return;
    if (openCard) openCard.close();
    card = el("div.hcard", {}, [...build(), el("i.hcarrow")]);
    document.body.append(card);
    anchor.classList.add("on");   // which cell the card belongs to, when it opens over others
    openCard = { anchor, close, place };
    place();
  };
  // Beside the anchor, below it if it fits; follows it on scroll, and closes once it's gone.
  function place() {
    if (!card) return;
    const r = anchor.getBoundingClientRect(), w = card.offsetWidth, h = card.offsetHeight;
    const vw = document.documentElement.clientWidth, vh = window.innerHeight;
    if (r.bottom < 0 || r.top > vh || !anchor.isConnected) { close(); return; }
    const left = Math.max(8, Math.min(r.right - w, vw - w - 8));
    const below = r.bottom + 8 + h <= vh;
    card.style.left = `${left}px`;
    card.style.top = `${below ? r.bottom + 8 : Math.max(8, r.top - h - 8)}px`;
    // the pointer sits over the anchor's middle, on whichever edge faces it
    card.classList.toggle("above", !below);
    card.style.setProperty("--ax", `${Math.min(Math.max(r.left + r.width / 2 - left, 14), w - 14)}px`);
  }
  if (matchMedia("(hover: hover)").matches) {
    anchor.addEventListener("pointerenter", open);
    anchor.addEventListener("pointerleave", () => { if (!pinned) close(); });
  }
  anchor.addEventListener("click", (e) => {
    e.stopPropagation();
    if (card && pinned) { close(); return; }
    open(); pinned = true;
  });
  anchor.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); anchor.click(); } });
}
// One card at a time; a tap elsewhere or Escape closes it.
document.addEventListener("click", (e) => { if (openCard && !e.target.closest(".hcard")) openCard.close(); });
addEventListener("scroll", () => openCard?.place(), { passive: true, capture: true });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") openCard?.close(); });

/** A panel's title over its table + chart. */
function panelWrap(title, node) {
  return el("div", {}, [el("h3", { text: title }), node]);
}

// --------------------------------------------------------------------------- maps
function popupHtml(p, extra) {
  const bits = [`<b>${p.club}</b>`];
  if (p.stadium) bits.push(p.stadium);
  if (p.capacity) bits.push(`${p.capacity.toLocaleString()} capacity`);
  if (extra) bits.push(extra);
  return bits.join("<br>");
}

// One colour per division tier, top flight hottest. The bottom tier ("Danish Lower Division", ~80
// clubs — more than the other five combined) is a muted grey on purpose: it would otherwise
// drown out the divisions a manager actually reads this map for.
const TIER_COLOURS = { 1: "#c0262d", 2: "#e8701a", 3: "#d4a300", 4: "#2e9e4f", 5: "#2f6fd0", 6: "#8a8f98" };
const tierColour = (t) => TIER_COLOURS[t] || "#555b66";

function baseMap(container) {
  const L = window.L;
  const map = L.map(container, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);
  return map;
}

/**
 * A map of round pins that never hide one another.
 *
 * The save places a club through club -> stadium -> CITY, and only the city has coordinates, so
 * every club in a city lands on exactly the same spot (FCK sits precisely under Frem; 84 of the
 * 162 Danish clubs share a point with another), and at country zoom clubs a few kilometres apart
 * overlap as well (Frem, FCK, Brøndby, Lyngby and Nordsjælland are one knot around Copenhagen).
 *
 * So after every zoom the pins are laid out in SCREEN pixels: clubs on the same point are seeded
 * around it on a sunflower spiral (`order` decides who takes the centre), then overlapping pairs
 * are pushed apart. Not fully apart: at country zoom that turns Denmark into a honeycomb that no
 * longer looks like the map, so pins also shrink when zoomed out and may overlap by up to
 * OVERLAP of their size — every pin stays visible and clickable, and the map keeps its shape.
 * The offset goes into the marker's icon anchor, so the pin's latlng stays the true one.
 */
const OVERLAP = 0.3;
const pinScale = (zoom) => (zoom >= 9 ? 1 : zoom >= 8 ? 0.85 : zoom >= 7 ? 0.72 : 0.6);
function pinLayer(map, { order }) {
  const L = window.L;
  const layer = L.featureGroup().addTo(map);
  let pins = [];                                  // { p, style, marker }

  const iconFor = (style, dx, dy, k = 1) => {
    const size = Math.round(2 * (style.r * k + style.ringW));
    return L.divIcon({
      className: "mapdot",
      html: `<span style="display:block;box-sizing:border-box;width:${size}px;height:${size}px;`
        + `border-radius:50%;background:${style.fill};border:${style.ringW}px solid ${style.ring};`
        + `opacity:.95"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2 - dx, size / 2 - dy],
      popupAnchor: [dx, dy - size / 2],
    });
  };

  function relayout() {
    if (!pins.length) return;
    const k = pinScale(map.getZoom());
    const pos = pins.map((x) => map.latLngToLayerPoint([x.p.lat, x.p.lon]));
    const base = pos.map((q) => ({ x: q.x, y: q.y }));
    const rad = pins.map((x) => x.style.r * k + x.style.ringW);
    // seed: same-point groups on a spiral, so the push below has a direction to work with
    const groups = new Map();
    pins.forEach((x, i) => {
      const k = `${x.p.lat},${x.p.lon}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(i);
    });
    const cur = base.map((q) => ({ ...q }));
    for (const g of groups.values()) {
      if (g.length < 2) continue;
      g.sort((i, j) => order(pins[i].p, pins[j].p));
      g.forEach((i, n) => {
        const r = 9 * k * Math.sqrt(n + 0.6), a = n * 2.39996;
        cur[i].x += r * Math.cos(a); cur[i].y += r * Math.sin(a);
      });
    }
    // push overlapping pairs apart; the higher-ranked pin (by `order`) moves less
    const rank = pins.map((_, i) => i).sort((i, j) => order(pins[i].p, pins[j].p));
    const weight = new Array(pins.length);
    rank.forEach((i, n) => { weight[i] = 0.35 + 0.3 * (n / Math.max(1, pins.length - 1)); });
    for (let it = 0; it < 60; it++) {
      let moved = false;
      for (let i = 0; i < pins.length; i++) {
        for (let j = i + 1; j < pins.length; j++) {
          const dx = cur[j].x - cur[i].x, dy = cur[j].y - cur[i].y;
          // Same point: always fully apart, or one pin sits exactly under the other. Otherwise
          // a partial overlap is allowed, which is what keeps the map's shape.
          const same = pins[i].p.lat === pins[j].p.lat && pins[i].p.lon === pins[j].p.lon;
          const need = (rad[i] + rad[j]) * (same ? 1 : 1 - OVERLAP) + 1;
          const d2 = dx * dx + dy * dy;
          if (d2 >= need * need) continue;
          const d = Math.sqrt(d2) || 0.01;
          const ux = d2 ? dx / d : Math.cos(i + j), uy = d2 ? dy / d : Math.sin(i + j);
          const push = need - d;
          const wi = weight[i] / (weight[i] + weight[j]), wj = 1 - wi;
          cur[i].x -= ux * push * wi; cur[i].y -= uy * push * wi;
          cur[j].x += ux * push * wj; cur[j].y += uy * push * wj;
          moved = true;
        }
      }
      if (!moved) break;
    }
    pins.forEach((x, i) => x.marker.setIcon(iconFor(x.style, cur[i].x - base[i].x, cur[i].y - base[i].y, k)));
  }
  map.on("zoomend", relayout);

  return {
    layer,
    /** Replace every pin. `entries` is [{ p, style: {fill, r, ring, ringW, z}, popup }]. */
    set(entries) {
      layer.clearLayers();
      pins = entries.map(({ p, style, popup }) => ({
        p, style,
        marker: L.marker([p.lat, p.lon], {
          icon: iconFor(style, 0, 0), zIndexOffset: style.z || 0, title: p.club,
        }).bindPopup(popup).addTo(layer),
      }));
    },
    relayout,
  };
}

function fitTo(map, pins, pts) {
  if (pts.length) map.fitBounds(window.L.latLngBounds(pts.map((p) => [p.lat, p.lon])).pad(0.2), { maxZoom: 10 });
  else map.setView([56.0, 10.0], 6);   // Denmark, roughly — a reasonable empty-map default
  pins.relayout();                     // fitBounds may not change zoom, and then no zoomend fires
}

async function mapsPanel(world) {
  const wrap = el("div");
  try {
    await loadLeaflet();
  } catch (e) {
    wrap.append(el("p.note", { text: `Maps unavailable: ${e.message}` }));
    return wrap;
  }

  const dk = world?.places?.denmark || [];
  const origins = world?.places?.origins || [];
  const unresolved = world?.origins_unresolved ?? 0;

  wrap.append(el("h3", { text: `${world?.our_nation || "Our nation"}'s clubs by division` }));
  // League filter, ordered down the pyramid. Tier 5 is split into regional series groups, so
  // each tier that has more than one league also gets an "all of tier N" option.
  const leagues = [...new Map(dk.map((p) => [p.league, p.tier])).entries()]
    .sort((a, b) => (a[1] ?? 99) - (b[1] ?? 99) || String(a[0]).localeCompare(String(b[0])));
  const tiers = [...new Set(leagues.map(([, t]) => t))];
  const leagueSel = el("select.btn", {}, [
    el("option", { value: "", text: "All divisions" }),
    ...tiers.flatMap((t) => {
      const inTier = leagues.filter(([, lt]) => lt === t);
      return [
        inTier.length > 1 ? el("option", { value: `tier:${t}`, text: `Tier ${t} — all ${inTier.length} groups` }) : null,
        ...inTier.map(([name]) => el("option", { value: `league:${name}`, text: `${t ? `${t} · ` : ""}${name}` })),
      ].filter(Boolean);
    }),
  ]);
  const legend = el("div.prow", { style: "font-size:12.5px" }, tiers.map((t) => el("span", {
    style: "display:inline-flex;align-items:center;gap:5px;margin-right:8px",
  }, [
    el("span", { style: `display:inline-block;width:11px;height:11px;border-radius:50%;`
      + `background:${tierColour(t)};border:1px solid #fff;box-shadow:0 0 0 1px ${tierColour(t)}` }),
    `Tier ${t}`,
  ])));
  const dkDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  const dkNote = el("p.note");
  wrap.append(el("div.tbar", {}, [leagueSel]), legend, dkDiv, dkNote);

  wrap.append(el("h3", { text: "Our squad's origin clubs" }));
  const originDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  wrap.append(originDiv);
  wrap.append(el("p.note", {
    text: `${origins.length} origin clubs shown for the current squad; overlapping pins are `
      + "nudged apart, and our own academy has the dark ring."
      + (unresolved ? ` ${unresolved} player(s)' origin club couldn't be placed on the map — ` +
        "that means our data can't resolve it, not that they don't have one." : ""),
  }));

  // Deferred to the next frame: `baseMap` needs the container's real on-page size (Leaflet
  // measures it at construction time), and these divs aren't attached to the document until
  // AFTER this function's promise resolves and the caller replaces the panel's children with
  // it — so building the map inline here would measure a detached, zero-size node.
  requestAnimationFrame(() => {
    const L = window.L;
    const ourTids = new Set(D.S.ours.clubs || []);
    const map = baseMap(dkDiv);
    const byTier = (a, b) => (a.tier ?? 99) - (b.tier ?? 99) || String(a.club).localeCompare(String(b.club));
    const dkPins = pinLayer(map, {
      order: (a, b) => (ourTids.has(b.tid) - ourTids.has(a.tid)) || byTier(a, b),
    });
    const drawDk = () => {
      const want = leagueSel.value;
      const shown = dk.filter((p) => !want
        || (want.startsWith("tier:") ? String(p.tier) === want.slice(5) : p.league === want.slice(7)));
      dkPins.set(shown.map((p) => {
        const ours = ourTids.has(p.tid);
        return {
          p,
          style: { fill: tierColour(p.tier), r: ours ? 8 : 7, ring: ours ? "#111" : "#fff",
                   ringW: ours ? 3 : 1.5, z: ours ? 1000 : (10 - (p.tier ?? 9)) * 100 },
          popup: popupHtml(p, p.tier ? `Tier ${p.tier} · ${p.league}` : p.league),
        };
      }));
      fitTo(map, dkPins, shown);
      dkNote.textContent = `${shown.length} of ${dk.length} clubs with a resolvable stadium `
        + "location, coloured by division tier (1 = top flight); our club has the dark ring. "
        + "Pins mark each club's CITY (the save has no ground coordinates), and pins that would "
        + "overlap are nudged apart so none hides another; zoom in and they settle back towards "
        + "their city. Tap a pin for the club, ground and capacity.";
    };
    leagueSel.addEventListener("change", drawDk);
    drawDk();
    const omap = baseMap(originDiv);
    const oPins = pinLayer(omap, {
      order: (a, b) => (ourTids.has(b.tid) - ourTids.has(a.tid))
        || b.players.length - a.players.length || a.club.localeCompare(b.club),
    });
    oPins.set(origins.map((p) => {
      const ours = ourTids.has(p.tid);
      return {
        p,
        style: { fill: "#2f6fd0", r: ours ? 8 : 7, ring: ours ? "#111" : "#fff",
                 ringW: ours ? 3 : 1.5, z: ours ? 1000 : 0 },
        popup: popupHtml(p, p.players.join(", ")),
      };
    }));
    fitTo(omap, oPins, origins);
  });

  return wrap;
}
