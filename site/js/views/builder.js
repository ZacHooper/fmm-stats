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
 * Ported from the Streamlit Team Builder page, minus its two heaviest features: live per-slot
 * weight tuning (duty is a display label only here, not an override) and the Hungarian-algorithm
 * "suggest best XI". This is the static picker — tap a slot, see who fits, assign him.
 */
import * as D from "../data.js";
import { playerTable } from "../table.js";
import { el, clear, bar, num, DASH, toast } from "../ui.js";
import { openProfile } from "../profile.js";

const LS_KEY = "fm:builder";

// Each slot: [id, role, duty]. `role` is one of core.pos_role's VALUES — the vocabulary
// S.tactics[method] looks weights up by — not a raw FM position code (there is no "CB" position
// in a player's own positions list, only DC; posRole is what turns DC into CB). Rows run
// attack (top) -> goalkeeper (bottom), matching how a pitch reads.
const FORMATIONS = {
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

const flatSlots = (key) => FORMATIONS[key].flat().map(([id, role, duty]) => ({ id, role, duty }));

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

/** Best familiarity + Level %iles a player has AT a given role (a role can be reached by more
 *  than one raw position — DL and DML both map to LB — so this is a max over whichever of his
 *  listed positions maps onto it, not a single lookup). */
function bestAt(p, role) {
  let best = null;
  for (const q of p.positions) if (q.role === role && (!best || q.fam > best.fam)) best = q;
  return best;
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
      + "role is rated. Tap a slot, then assign from the ranked list.",
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
      return p ? bestAt(p, s.role)?.lvlLeague ?? null : null;
    }).filter((v) => v != null);
    const mean = lvls.length ? Math.round(lvls.reduce((a, b) => a + b, 0) / lvls.length) : null;
    clear(kpis).append(
      el("div.kpi", {}, [el("b", { text: `${filled.length}/${slots.length}` }), el("span", { text: "XI filled" })]),
      el("div.kpi", {}, [el("b", { text: mean == null ? DASH : `${mean}%` }), el("span", { text: "Mean Level %ile" })]),
    );
  }

  function drawPitch() {
    const pitch = el("div.pitch");
    for (const row of FORMATIONS[state.formation]) {
      pitch.append(el("div.pitchrow", {}, row.map(([sid, , duty]) => {
        const tid = state.xi[sid];
        return el(`div.slot${sid === active ? ".on" : ""}${tid != null ? ".filled" : ""}`, {
          onclick: () => { active = sid; redraw(); },
        }, [el("small", { text: duty }), el("b", { text: tid != null ? surname(tid) : "—" })]);
      })));
    }
    clear(pitchHost).append(pitch);
  }

  function candidatesFor(role) {
    const rows = [];
    for (const { player: p, shortlist } of pool) {
      const best = bestAt(p, role);
      if (!best || best.fam <= 0) continue;
      const base = D.rating(p.attrs, role, D.S.method);
      const eff = base * D.famMult(best.fam);
      rows.push({
        tid: p.tid, player: p, shortlist, fam: best.fam, eff, base,
        lvl: best.lvlLeague, lvlg: best.lvlGlobal,
        _search: p.name.toLowerCase(),
      });
    }
    return rows.sort((a, b) => b.eff - a.eff);
  }

  function drawCandidates() {
    const slot = slots.find((s) => s.id === active);
    if (!slot) { clear(candHost); return; }
    const rows = candidatesFor(slot.role);
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
            el("button.link", { text: r.player.name, onclick: () => openProfile(r.tid, { role: slot.role }) }),
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
          help: "This tactic's weighted attribute sum × the familiarity multiplier, for this role",
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
      defaults: ["fam", "rating", "lvlg", "action"],
      sort: { by: "rating", dir: "desc" },
      searchPlaceholder: "Search candidates…",
      empty: "Nobody in the pool fits this role.",
    });
    clear(candHost).append(
      el("p.note", { text: `${slot.id} · ${slot.duty} (role ${slot.role}) — ${rows.length} eligible` }),
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
