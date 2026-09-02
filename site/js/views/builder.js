/**
 * Builder — assemble a starting XI slot-by-slot against a formation shape, ranked by whichever
 * tactic is picked in the header.
 *
 * A formation here is a pitch SHAPE (4-3-3, 4-2-3-1, …) — a different axis from the header's
 * tactic selector, which is a WEIGHT SET. The shape says which slots exist and what role each
 * one is (the vocabulary `core.pos_role` maps positions onto — CB, LB, RB, DM, CM, AML, AMR,
 * AMC, ST, GK); the header's tactic says how that role is rated. Switching tactic re-ranks every
 * slot's candidates without touching the shape, the same way it re-rates every other view.
 *
 * "General" is a fourth, DIFFERENT kind of shape: instead of merging positions into roles (DL
 * and DML both count as one LB slot in a named formation), each slot matches one exact raw FM
 * position, laid out like the game's own position grid — so you can check a player at the exact
 * position rather than the role it collapses to. Central columns get several independently
 * assignable slots sharing one position (three separate midfielders to compare, not one merged
 * box), the same way a named formation already reuses one role across CB1/CB2. Everything
 * downstream (`lookupAt`) just branches on which kind of key a slot carries; candidate ranking
 * and assignment don't care how many slots share it.
 *
 * Ported from the Streamlit Team Builder page, minus its two heaviest features: live per-slot
 * weight tuning (duty is a display label only here, not an override) and the Hungarian-algorithm
 * "suggest best XI". This is the static picker — tap a slot, see who fits, assign him.
 */
import * as D from "../data.js";
import { playerTable } from "../table.js";
import { el, clear, bar, num, DASH, toast } from "../ui.js";
import { openProfile } from "../profile.js";

const LS_KEY = "fm:builder";

// Named formations: rows of [id, role, duty]. `role` is one of core.pos_role's VALUES — the
// vocabulary S.tactics[method] looks weights up by — not a raw FM position code (there is no
// "CB" position in a player's own positions list, only DC; posRole is what turns DC into CB).
// Rows run attack (top) -> goalkeeper (bottom), matching how a pitch reads.
const NAMED = {
  "4-1-2-3 (SS)": [
    [["AML", "AML", "IF"], ["AMC", "AMC", "SS"], ["AMR", "AMR", "IF"]],
    [["CM1", "CM", "RP"], ["CM2", "CM", "BBM"]],
    [["DM", "DM", "BWM"]],
    [["LB", "LB", "WB"], ["CB1", "CB", "CD"], ["CB2", "CB", "CD"], ["RB", "RB", "WB"]],
    [["GK", "GK", "SK"]],
  ],
  "4-2-3-1": [
    [["ST", "ST", "PF"]],
    [["AML", "AML", "IF"], ["AMC", "AMC", "AP"], ["AMR", "AMR", "IF"]],
    [["DM1", "DM", "DLP"], ["DM2", "DM", "BWM"]],
    [["LB", "LB", "WB"], ["CB1", "CB", "CD"], ["CB2", "CB", "CD"], ["RB", "RB", "WB"]],
    [["GK", "GK", "SK"]],
  ],
  "4-3-3": [
    [["AML", "AML", "IF"], ["ST", "ST", "PF"], ["AMR", "AMR", "IF"]],
    [["CM1", "CM", "RP"], ["CM2", "CM", "B2B"], ["CM3", "CM", "B2B"]],
    [["LB", "LB", "WB"], ["CB1", "CB", "CD"], ["CB2", "CB", "CD"], ["RB", "RB", "WB"]],
    [["GK", "GK", "SK"]],
  ],
};
// General grid: laid out on an explicit 5-column x 6-row CSS grid, the same shape the game's own
// position screen uses — five outfield lines (Forward / AM / CM / DM / Defence) plus GK on its
// own row. Every position the game has is on offer regardless of what any formation or tactic
// actually fields (see D.POS_ORDER's own reasoning for why).
//
// The 3 central columns of each outfield line are 3 SEPARATE slots (id ST1/ST2/ST3, etc.), not
// one merged box — same pattern a named formation already uses for CB1/CB2: several slots can
// share one rating `key` (there's only one raw "MC" position to judge them all against) while
// still being assigned independently, because a squad can have three midfielders worth comparing
// side by side. AML/AMR are the one real exception: they span BOTH the Forward and AM rows,
// because unlike the center there genuinely is only one of them — FMM has no separate
// wide-forward position, so duplicating "AML" into two independent slots would just be two boxes
// racing to describe the same player. DML/DMR and DL/DR stay on separate rows with separate
// labels (WB vs FB) because those, unlike the center columns, ARE different raw positions.
const GENERAL_CELLS = [
  { id: "AML", key: "AML", duty: "AML", row: 1, col: 1, rowSpan: 2 },
  { id: "ST1", key: "ST", duty: "ST", row: 1, col: 2 },
  { id: "ST2", key: "ST", duty: "ST", row: 1, col: 3 },
  { id: "ST3", key: "ST", duty: "ST", row: 1, col: 4 },
  { id: "AMR", key: "AMR", duty: "AMR", row: 1, col: 5, rowSpan: 2 },
  { id: "AMC1", key: "AMC", duty: "AMC", row: 2, col: 2 },
  { id: "AMC2", key: "AMC", duty: "AMC", row: 2, col: 3 },
  { id: "AMC3", key: "AMC", duty: "AMC", row: 2, col: 4 },
  { id: "ML", key: "ML", duty: "ML", row: 3, col: 1 },
  { id: "MC1", key: "MC", duty: "CM", row: 3, col: 2 },
  { id: "MC2", key: "MC", duty: "CM", row: 3, col: 3 },
  { id: "MC3", key: "MC", duty: "CM", row: 3, col: 4 },
  { id: "MR", key: "MR", duty: "MR", row: 3, col: 5 },
  { id: "DML", key: "DML", duty: "WBL", row: 4, col: 1 },
  { id: "DMC1", key: "DMC", duty: "DM", row: 4, col: 2 },
  { id: "DMC2", key: "DMC", duty: "DM", row: 4, col: 3 },
  { id: "DMC3", key: "DMC", duty: "DM", row: 4, col: 4 },
  { id: "DMR", key: "DMR", duty: "WBR", row: 4, col: 5 },
  { id: "DL", key: "DL", duty: "FBL", row: 5, col: 1 },
  { id: "DC1", key: "DC", duty: "CB", row: 5, col: 2 },
  { id: "DC2", key: "DC", duty: "CB", row: 5, col: 3 },
  { id: "DC3", key: "DC", duty: "CB", row: 5, col: 4 },
  { id: "DR", key: "DR", duty: "FBR", row: 5, col: 5 },
  { id: "GK", key: "GK", duty: "GK", row: 6, col: 3 },
];
const GENERAL_LABEL = "General (any position)";

// FORMATIONS: name -> {kind, rows | cells}. kind "role" slots are looked up by merging every raw
// position that maps onto that role (a named formation's LB slot matches DL or DML, whichever
// fits better); kind "pos" slots match one exact raw position and nothing else. Named formations
// lay out as simple flex rows (`rows`); the General grid needs explicit placement (`cells`) for
// its spans, so it gets its own renderer — see drawPitch().
const FORMATIONS = {
  ...Object.fromEntries(Object.entries(NAMED).map(([name, rows]) => [name, { kind: "role", rows }])),
  [GENERAL_LABEL]: { kind: "pos", cells: GENERAL_CELLS },
};

const flatSlots = (name) => {
  const f = FORMATIONS[name];
  if (f.cells) return f.cells.map((c) => ({ id: c.id, key: c.key, duty: c.duty, kind: f.kind }));
  return f.rows.flat().map(([id, key, duty]) => ({ id, key, duty, kind: f.kind }));
};

function loadState() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { s = {}; }
  return {
    formation: FORMATIONS[s.formation] ? s.formation : Object.keys(FORMATIONS)[0],
    xi: s.xi && typeof s.xi === "object" ? { ...s.xi } : {},
    shortlist: s.shortlist === true,
  };
}
const saveState = (s) => {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ formation: s.formation, xi: s.xi, shortlist: s.shortlist }));
  } catch { /* private browsing — the XI just won't survive a reload */ }
};

/** Shortlist entries resolved to real players — same rule Squad's "Show shortlist" uses: an
 *  entry with no tid, or one the save can't resolve, has no attributes to rate him with. */
async function shortlistPlayers() {
  const entries = await D.loadShortlist();
  const tids = entries.map((e) => e.tid).filter((t) => t != null);
  await D.loadPlayersByTid(tids);
  return tids.map((t) => D.S.players.get(t)).filter(Boolean);
}

/** The position entry a player would be judged on for `slot`. A "pos" slot (the General grid)
 *  matches that exact raw position and nothing else. A "role" slot (a named formation) matches
 *  whichever of his listed positions maps onto that role, best familiarity first — a role can be
 *  reached by more than one raw position (DL and DML both map to LB). */
function lookupAt(p, slot) {
  if (slot.kind === "pos") return p.positions.find((q) => q.pos === slot.key) || null;
  let best = null;
  for (const q of p.positions) if (q.role === slot.key && (!best || q.fam > best.fam)) best = q;
  return best;
}

/** [{eff}] for our own squad at `slot` — the pool a candidate's Squad Rank is read off. Never
 *  the shortlist: "where would he rank in the squad" only means something against players
 *  actually in it. */
function squadPoolAt(slot) {
  const out = [];
  for (const p of D.ourPlayers()) {
    const best = lookupAt(p, slot);
    if (best && best.fam > 0) out.push({ eff: D.rating(p.attrs, best.role, D.S.method) * D.famMult(best.fam) });
  }
  return out;
}

export async function view() {
  const state = loadState();
  let slots = flatSlots(state.formation);
  state.xi = Object.fromEntries(Object.entries(state.xi).filter(([sid]) => slots.some((s) => s.id === sid)));
  let active = slots[0]?.id;
  let pool = [];        // [{player, shortlist}] — rebuilt on load and whenever the pool toggles

  async function loadPool() {
    const ours = D.ourPlayers();
    const ourTids = new Set(ours.map((p) => p.tid));
    pool = ours.map((p) => ({ player: p, shortlist: false }));
    if (state.shortlist) {
      const extra = (await shortlistPlayers()).filter((p) => !ourTids.has(p.tid));
      pool.push(...extra.map((p) => ({ player: p, shortlist: true })));
    }
  }

  const wrap = el("div");
  wrap.append(el("h2", { text: "Builder" }));
  wrap.append(el("p.note", {
    text: "Formation is the pitch shape; the tactic selected up top decides how each slot's "
      + `role is rated. "${GENERAL_LABEL}" swaps merged roles for the raw FM positions — several `
      + "slots down the middle of each line, so you can compare more than one player at once. "
      + "Tap a slot, then assign from the ranked list.",
  }));

  const formSel = el("select.btn", {
    onchange: async (e) => {
      state.formation = e.target.value;
      state.xi = {};
      slots = flatSlots(state.formation);
      active = slots[0]?.id;
      saveState(state);
      redraw();
    },
  }, Object.keys(FORMATIONS).map((f) => el("option", { value: f, text: f, selected: f === state.formation })));

  const poolBtn = el("button.btn", {
    text: state.shortlist ? "Squad + shortlist" : "Squad only",
    title: "Include shortlisted players with a resolvable tid in the candidate pool",
    onclick: async () => {
      state.shortlist = !state.shortlist;
      poolBtn.textContent = state.shortlist ? "Squad + shortlist" : "Squad only";
      poolBtn.classList.toggle("on", state.shortlist);
      saveState(state);
      await loadPool();
      redraw();
    },
  });
  poolBtn.classList.toggle("on", state.shortlist);

  const clearBtn = el("button.btn", {
    text: "Clear XI",
    onclick: () => { state.xi = {}; saveState(state); redraw(); },
  });

  const kpis = el("div.kpis");
  const pitchHost = el("div");
  const candHost = el("div");
  // grid2: pitch (left) and candidates (right) on a wide screen, stacked on a phone.
  wrap.append(el("div.prow", {}, [formSel, poolBtn, clearBtn]), kpis,
    el("div.grid2", {}, [pitchHost, candHost]));

  const surname = (tid) => {
    const p = D.S.players.get(tid);
    return p ? String(p.name).trim().split(/\s+/).slice(-1)[0] : "—";
  };

  function drawKpis() {
    const filled = slots.filter((s) => state.xi[s.id] != null);
    const lvls = filled.map((s) => {
      const p = D.S.players.get(state.xi[s.id]);
      return p ? lookupAt(p, s)?.lvlLeague ?? null : null;
    }).filter((v) => v != null);
    const mean = lvls.length ? Math.round(lvls.reduce((a, b) => a + b, 0) / lvls.length) : null;
    clear(kpis).append(
      el("div.kpi", {}, [el("b", { text: `${filled.length}/${slots.length}` }), el("span", { text: "XI filled" })]),
      el("div.kpi", {}, [el("b", { text: mean == null ? DASH : `${mean}%` }), el("span", { text: "Mean Level %ile" })]),
    );
  }

  const slotEl = (sid, key, duty) => {
    const tid = state.xi[sid];
    return el(`div.slot${sid === active ? ".on" : ""}${tid != null ? ".filled" : ""}`, {
      onclick: () => { active = sid; redraw(); },
    }, [el("small", { text: duty || key }), el("b", { text: tid != null ? surname(tid) : "—" })]);
  };

  function drawPitch() {
    const f = FORMATIONS[state.formation];
    let pitch;
    if (f.cells) {
      pitch = el("div.pitch.grid5");
      for (const c of f.cells) {
        const node = slotEl(c.id, c.key, c.duty);
        node.style.gridRow = `${c.row} / span ${c.rowSpan || 1}`;
        node.style.gridColumn = `${c.col} / span ${c.colSpan || 1}`;
        pitch.append(node);
      }
    } else {
      pitch = el("div.pitch");
      for (const row of f.rows) {
        pitch.append(el("div.pitchrow", {}, row.map(([sid, key, duty]) => slotEl(sid, key, duty))));
      }
    }
    clear(pitchHost).append(pitch);
  }

  function candidatesFor(slot) {
    const rows = [];
    for (const { player: p, shortlist } of pool) {
      const best = lookupAt(p, slot);
      if (!best || best.fam <= 0) continue;
      const base = D.rating(p.attrs, best.role, D.S.method);
      const eff = base * D.famMult(best.fam);
      rows.push({
        tid: p.tid, player: p, shortlist, fam: best.fam, eff, base, role: best.role,
        lvl: best.lvlLeague, lvlg: best.lvlGlobal,
        _search: p.name.toLowerCase(),
      });
    }
    return rows.sort((a, b) => b.eff - a.eff);
  }

  function drawCandidates() {
    const slot = slots.find((s) => s.id === active);
    if (!slot) { clear(candHost); return; }
    const rows = candidatesFor(slot);
    const squadPool = squadPoolAt(slot);
    for (const r of rows) {
      r.teamRank = D.rankIn(squadPool, r.eff);
      r.teamPoolSize = squadPool.length;
    }
    const assignedElsewhere = new Set(Object.entries(state.xi)
      .filter(([sid]) => sid !== active).map(([, tid]) => tid));

    const assign = (tid) => {
      for (const sid of Object.keys(state.xi)) if (state.xi[sid] === tid) delete state.xi[sid];
      state.xi[active] = tid;
      saveState(state); redraw();
    };
    const unassign = () => { delete state.xi[active]; saveState(state); redraw(); };

    const table = playerTable({
      key: "builder-cand",
      rows,
      catalogue: {
        player: {
          label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name,
          render: (r) => el("span", {}, [
            el("button.link", { text: r.player.name, onclick: () => openProfile(r.tid, { role: r.role }) }),
            state.xi[active] === r.tid ? el("span.dim", { text: "  ✓ this slot" }) : null,
            r.shortlist ? el("span.dim", { text: "  (shortlist)" }) : null,
          ]),
        },
        fam: {
          label: "Fam", group: "Identity", align: "num", sort: (r) => r.fam,
          render: (r) => bar(r.fam, { max: 20, lo: 60 }),
        },
        rating: {
          label: "Rating", group: "Rating", align: "num", sort: (r) => r.eff, render: (r) => num(r.eff),
          help: "This tactic's weighted attribute sum × the familiarity multiplier, for this position",
        },
        teamRank: {
          label: "Squad Rank", group: "Rating", align: "num",
          help: "Where this rating places him among our own players at this position, best to "
            + "worst. For a shortlisted player this is hypothetical — where he'd slot in if he joined.",
          sort: (r) => -r.teamRank, render: (r) => el("span", { text: `${r.teamRank}/${r.teamPoolSize}` }),
        },
        lvl: {
          label: "Level %ile", group: "Rating", align: "num", sort: (r) => r.lvl, render: (r) => bar(r.lvl),
          help: "Quality at that position within his own league — tactic-agnostic",
        },
        lvlg: {
          label: "Level %ile (world)", group: "Rating", align: "num", sort: (r) => r.lvlg, render: (r) => bar(r.lvlg),
          help: "Quality across every league in the save — the fair way to compare a shortlist target from another division",
        },
        action: {
          label: "", group: "Identity",
          render: (r) => (state.xi[active] === r.tid
            ? el("button.link", { text: "remove", onclick: () => unassign() })
            : el("button.link", {
              text: assignedElsewhere.has(r.tid) ? "move here" : "assign",
              onclick: () => assign(r.tid),
            })),
        },
      },
      sticky: ["player"],
      defaults: ["fam", "rating", "teamRank", "action"],
      sort: { by: "rating", dir: "desc" },
      searchPlaceholder: "Search candidates…",
      empty: "Nobody in the pool fits this position.",
    });
    const label = slot.kind === "pos" ? `position ${slot.key}` : `role ${slot.key}`;
    // The General grid's duty is a display nickname for the pitch cell (WBL, CB…), not a real
    // tactical instruction, so it's redundant next to "position X" here — only named formations
    // show it.
    const dutyPart = slot.kind === "role" && slot.duty ? ` · ${slot.duty}` : "";
    clear(candHost).append(
      el("p.note", { text: `${slot.id}${dutyPart} (${label}) — ${rows.length} eligible` }),
      table.node,
    );
  }

  function redraw() {
    drawKpis();
    drawPitch();
    drawCandidates();
  }

  await loadPool();
  redraw();
  return wrap;
}
