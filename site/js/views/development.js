/**
 * Development — given a player's age and CURRENT attributes, what will he look like at 21 or
 * 24? Squad and shortlist together, so a target reads against what we already have.
 *
 * The model is a lookup, not a fitted curve, because growth turned out to be a LEVEL
 * phenomenon rather than a rate one: a starting attribute like Technique adds +0.000 R^2 to a
 * player's future value once you already know his current one (see api/forecast.json's own
 * note, and docs/agent-context/player-analysis-methods.md). A technical player is already
 * ahead at 17 and stays ahead — growth doesn't re-sort the field. So "what will his Crossing
 * be" is answered by "what did players with his current Crossing, at his age, actually have
 * later", not by projecting Technique forward.
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, bar, num, DASH } from "../ui.js";
import { openProfile } from "../profile.js";

const LS_KEY = "fm:development";

function loadState() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { s = {}; }
  return { toAge: s.toAge === 21 ? 21 : 24 };
}
const saveState = (s) => {
  try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch { /* private browsing */ }
};

export async function view() {
  const [, forecast] = await Promise.all([D.loadSquad(), D.loadForecast()]);
  const state = loadState();
  const method = D.S.method;

  const entries = await D.loadShortlist();
  const shortlistTids = entries.map((e) => e.tid).filter((t) => t != null);
  await D.loadPlayersByTid(shortlistTids);
  const ourTids = new Set(D.ourPlayers().map((p) => p.tid));
  const pool = [
    ...D.ourPlayers().map((p) => ({ player: p, source: "Squad" })),
    ...shortlistTids.map((t) => D.S.players.get(t)).filter((p) => p && !ourTids.has(p.tid))
      .map((p) => ({ player: p, source: "Shortlist" })),
  ];

  function buildRow({ player: p, source }) {
    const best = D.bestRole(p, method, 0);
    if (!best) return null;
    const age = D.age(p.dob);
    const fc = forecast ? D.forecastAttrs(p, state.toAge) : null;
    const remain = forecast ? D.pointsRemaining(p, state.toAge) : null;
    const projEff = fc ? D.rating(fc.attrs, best.role, method) * D.famMult(best.fam) : null;
    return {
      tid: p.tid, player: p, r: best, age, source, fc, remain,
      projEff,
      projDelta: projEff != null ? projEff - best.eff : null,
      curTotal: p.attrs.reduce((s, v) => s + (v || 0), 0),
      projTotal: fc ? fc.attrs.reduce((s, v) => s + (v || 0), 0) : null,
      _search: [p.name, best.pos, best.role, source].join(" ").toLowerCase(),
    };
  }

  // A plain array, mutated in place (never reassigned): playerTable captures `rows` by
  // reference at construction, so a target-age change has to splice new rows into the SAME
  // array — squad.js's shortlist toggle does the same for the same reason.
  const rows = pool.map(buildRow).filter(Boolean);
  const rebuildRows = () => rows.splice(0, rows.length, ...pool.map(buildRow).filter(Boolean));

  const forecastableAttrs = forecast
    ? D.S.attrs.filter((name) => forecast.buckets[name] === "forecastable") : [];
  const fixedAttrs = forecast
    ? D.S.attrs.filter((name) => forecast.buckets[name] === "fixed") : [];

  const catalogue = {
    player: {
      label: "Player", group: "Identity", cls: "name",
      sort: (r) => r.player.name,
      render: (r) => el("span", {}, [r.player.name,
        r.source === "Shortlist" ? el("span.dim", { text: "  (shortlist)" }) : null]),
    },
    source: { label: "Source", group: "Identity", get: (r) => r.source },
    age: { label: "Age", group: "Identity", align: "num", get: (r) => r.age },
    pos: { label: "Pos", group: "Identity", get: (r) => r.r.pos },
    role: { label: "Role", group: "Identity", get: (r) => r.r.role },
    fam: {
      label: "Fam", group: "Identity", align: "num",
      sort: (r) => r.r.fam, render: (r) => bar(r.r.fam, { max: 20, lo: 60 }),
    },
    rating: {
      label: "Rating now", group: "Development", align: "num",
      help: "This tactic's weighted attribute sum × the familiarity multiplier, at his current attributes",
      sort: (r) => r.r.eff, render: (r) => num(r.r.eff),
    },
    projRating: {
      label: "Projected rating", group: "Development", align: "num",
      help: "Rating recomputed on his projected attributes at the target age, under this tactic",
      sort: (r) => r.projEff ?? r.r.eff, render: (r) => (r.fc ? num(r.projEff) : null),
    },
    projDelta: {
      label: "Δ to target", group: "Development", align: "num",
      help: "Projected rating minus rating now",
      sort: (r) => r.projDelta ?? null,
      render: (r) => (r.projDelta != null
        ? el("span", { class: r.projDelta >= 0 ? "" : "dim", text: `${r.projDelta >= 0 ? "+" : ""}${num(r.projDelta)}` })
        : null),
    },
    remain: {
      label: "Points left", group: "Development", align: "num",
      help: "Total attribute points expected to be gained by the target age — median (p25-p75 band), from the whole save's age curve",
      sort: (r) => r.remain?.median ?? null,
      render: (r) => (r.remain
        ? el("span", {}, [num(r.remain.median), el("span.dim", { text: ` (${r.remain.p25}-${r.remain.p75})` })])
        : (r.age != null && r.age >= state.toAge ? el("span.dim", { text: "at target" }) : null)),
    },
    totals: {
      label: "Total now → target", group: "Development", align: "num",
      sort: (r) => (r.projTotal ?? r.curTotal) - r.curTotal,
      render: (r) => (r.fc ? `${r.curTotal} → ${r.projTotal}` : String(r.curTotal)),
    },
    ...Object.fromEntries(forecastableAttrs.map((name) => {
      const i = D.S.attrs.indexOf(name);
      return [`fc:${name}`, {
        label: name, group: "Forecast · current → projected", align: "num",
        help: `${name}: current value → projected value at the target age (p25-p75 band)`,
        sort: (r) => (r.fc ? r.fc.attrs[i] - (r.player.attrs[i] ?? 0) : null),
        render: (r) => {
          if (!r.fc || r.player.attrs[i] == null) return DASH;
          const cur = r.player.attrs[i], proj = r.fc.attrs[i], b = r.fc.band[i];
          return el("span", {}, [
            String(cur), " → ",
            el(proj > cur ? "b" : "span", { text: String(proj) }),
            b ? el("span.dim", { text: ` (${b[0]}-${b[1]})` }) : null,
          ]);
        },
      }];
    })),
    ...metricColumns(D),
  };

  const targetSel = el("select.btn", {
    onchange: (e) => {
      state.toAge = Number(e.target.value);
      saveState(state);
      rebuildRows();
      t.redraw();
    },
  }, [21, 24].map((y) => el("option", { value: y, text: `Project to ${y}`, selected: y === state.toAge })));

  const t = playerTable({
    key: "development",
    rows,
    catalogue,
    sticky: ["player"],
    defaults: ["source", "age", "pos", "fam", "rating", "projRating", "projDelta", "remain"],
    sort: { by: "projRating", dir: "desc" },
    searchPlaceholder: "Search squad + shortlist…",
    toolbar: [targetSel],
    empty: "No player matches those filters.",
    onRow: (r) => openProfile(r.tid, { role: r.r.role }),
  });

  const noteParts = [
    "Growth here is a population expectation with a band, not a per-player prediction — "
    + "current value and age predict a future value well, but a starting attribute does not "
    + "predict how fast ANOTHER attribute grows (tested: Technique adds +0.000 R² to a future "
    + "Crossing value once you know the current one).",
  ];
  if (fixedAttrs.length) {
    noteParts.push(`${fixedAttrs.join(" and ")} never move in real play — what you see is what you get.`);
  }
  if (!forecast) {
    noteParts.unshift("forecast.json is missing from this export, so no projections are available — showing current ratings only.");
  }

  return el("div", {}, [
    el("h2", { text: `Development · ${D.S.method}` }),
    t.node,
    el("p.note", { text: noteParts.join(" ") }),
  ]);
}
