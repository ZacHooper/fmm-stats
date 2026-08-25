/**
 * Squad — one table, every question. This is where the old Squad list, Development and Player
 * Stats pages collapse into a single thing: identity, tactic fit, level, growth, contract, any
 * of the 23 attributes and any match stat are all columns in the same grid, added and removed
 * from one picker.
 *
 * Why one table rather than three pages: they were three views of the same rows differing only
 * in which columns were on screen, so the split was arbitrary — and it meant you could never
 * ask a question that crossed two of them ("who's growing AND has pace AND plays minutes").
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, bar, num, money, monthYear, sparkline, pill, DASH, toast } from "../ui.js";
import { openProfile, openCompare } from "../profile.js";

export async function view() {
  await Promise.all([D.loadSquad(), D.loadMatches()]);
  const ourCid = D.ourLeagueCid();
  const method = D.S.method;
  const minFam = 0;
  const ours = D.ourPlayers();
  const loanedIn = new Set(D.S.ours.loaned_in || []);

  // Fit percentile is measured against OUR OWN DIVISION at that position — a reserve-team
  // player's own league would be the reserve league, which ranks him against other reserve
  // sides and flatters him. Pools are built once per position, not per row.
  const divPlayers = D.leaguePlayers(ourCid);
  const pools = new Map();
  const poolFor = (pos) => {
    if (!pools.has(pos)) pools.set(pos, D.poolAt(divPlayers, pos, method, 0));
    return pools.get(pos);
  };

  // Shared by squad members and shortlist entries alike, so a shortlisted player slots into
  // exactly the same row shape and every column, filter and the compare picker just work on him
  // — no separate "compare a shortlist player" path to keep in sync with this one.
  function buildRow(p, extra = {}) {
    const best = D.bestRole(p, method, minFam);
    if (!best) return null;
    const g = D.growth(p.tid, best.role, method);
    const traj = D.trajectory(p.tid, best.role, method);
    const status = extra.status ?? (D.S.ours.status?.[String(p.tid)] || DASH);
    return {
      tid: p.tid, player: p, r: best, growth: g, traj,
      age: D.age(p.dob),
      status,
      loanedIn: loanedIn.has(p.tid),
      origin: D.S.ours.origin?.[String(p.tid)] || null,
      capital: (D.S.ours.capital_eligible || []).includes(p.tid),
      fit: D.pctile(poolFor(best.pos), best.eff),
      alsoRoles: D.playerRoles(p, method).map((x) => x.role).filter((x, i, a) => a.indexOf(x) === i),
      shortlist: !!extra.shortlist,
      _search: [p.name, best.pos, best.role, status].join(" ").toLowerCase(),
    };
  }

  const rows = [];
  for (const p of ours) {
    const row = buildRow(p);
    if (row) rows.push(row);
  }

  /** Resolve shortlist entries with a tid into full rows, rated exactly like a squad member. An
   *  entry with no tid, or one the save can't resolve, has no attributes to rate him with — it's
   *  excluded rather than shown as a dashed-out row, and the caller reports how many that was. */
  async function buildShortlistRows() {
    const entries = await D.loadShortlist();
    const withTid = entries.filter((e) => e.tid != null);
    await D.loadPlayersByTid(withTid.map((e) => e.tid));
    const out = [];
    for (const e of withTid) {
      const p = D.S.players.get(e.tid);
      const row = p && buildRow(p, { status: "Shortlist", shortlist: true });
      if (row) out.push(row);
    }
    return { rows: out, missing: entries.length - out.length };
  }

  const catalogue = {
    player: {
      label: "Player", group: "Identity", cls: "name",
      sort: (r) => r.player.name,
      render: (r) => el("span", {}, [r.player.name,
        r.loanedIn ? el("span.dim", { text: "  (loan in)" }) : null,
        r.shortlist ? el("span.dim", { text: "  (shortlist)" }) : null]),
    },
    age: { label: "Age", group: "Identity", align: "num", get: (r) => r.age },
    pos: { label: "Pos", group: "Identity", get: (r) => r.r.pos },
    role: { label: "Role", group: "Identity", get: (r) => r.r.role },
    fam: {
      label: "Fam", group: "Identity", align: "num",
      help: "Position familiarity 0-20. The rating is already discounted by it, so a high rating on a low Fam means raw attributes are carrying him somewhere he doesn't play.",
      sort: (r) => r.r.fam, render: (r) => bar(r.r.fam, { max: 20, lo: 60 }),
    },
    also: {
      label: "Also", group: "Identity",
      help: "Other roles he rates in under this tactic",
      get: (r) => r.alsoRoles.filter((x) => x !== r.r.role).join(", ") || DASH,
    },
    status: { label: "Squad", group: "Identity", get: (r) => r.status },
    rating: {
      label: "Rating", group: "Rating", align: "num",
      help: "This tactic's weighted attribute sum × the familiarity multiplier",
      sort: (r) => r.r.eff, render: (r) => num(r.r.eff),
    },
    base: {
      label: "Base", group: "Rating", align: "num",
      help: "Rating before the familiarity discount",
      sort: (r) => r.r.rating, render: (r) => num(r.r.rating),
    },
    fit: {
      label: "Fit %ile", group: "Rating", align: "num",
      help: "Where he sits at that position in OUR division under this tactic — fit, not level",
      sort: (r) => r.fit, render: (r) => bar(r.fit),
    },
    lvl: {
      label: "Level %ile", group: "Rating", align: "num",
      help: "Quality at that position within his own league — tactic-agnostic, derived from the game's ability rating",
      sort: (r) => r.r.lvlLeague, render: (r) => bar(r.r.lvlLeague),
    },
    lvlg: {
      label: "Level %ile (world)", group: "Rating", align: "num",
      help: "Quality at that position across every league in the save",
      sort: (r) => r.r.lvlGlobal, render: (r) => bar(r.r.lvlGlobal),
    },
    growth: {
      label: "Δ", group: "Growth", align: "num",
      help: "Rating change since his first snapshot, recomputed under this tactic",
      sort: (r) => r.growth?.delta ?? null,
      render: (r) => (r.growth
        ? el("span", { class: r.growth.delta >= 0 ? "" : "dim", text: `${r.growth.delta >= 0 ? "+" : ""}${num(r.growth.delta)}` })
        : null),
    },
    traj: {
      label: "Trend", group: "Growth",
      help: "Rating across every loaded snapshot, under this tactic",
      sort: (r) => r.growth?.delta ?? null,
      render: (r) => sparkline(r.traj.map((t) => t.value)),
    },
    snaps: { label: "Snapshots", group: "Growth", align: "num", get: (r) => r.traj.length || null },
    wage: {
      label: "Wage/yr", group: "Contract", align: "num",
      sort: (r) => r.player.wage, render: (r) => money(r.player.wage),
    },
    expiry: {
      label: "Contract", group: "Contract",
      sort: (r) => r.player.expiry || "9999", render: (r) => monthYear(r.player.expiry),
    },
    value: {
      label: "Value", group: "Contract", align: "num",
      sort: (r) => r.player.value, render: (r) => money(r.player.value),
    },
    origin: { label: "Origin club", group: "Contract", get: (r) => r.origin },
    capital: {
      label: "Capital", group: "Contract",
      help: "Career-origin club inside Region Hovedstaden — the self-imposed signing rule. Existing squad members are grandfathered.",
      sort: (r) => (r.capital ? 1 : 0), render: (r) => (r.capital ? pill("✓", "good") : null),
    },
    ...metricColumns(D, { agg: D.S.matchAgg }),
  };

  const presets = {
    "Development": ["growth", "traj", "snaps", "rating", "fit"],
    "Contracts": ["wage", "expiry", "value", "age", "status"],
    "Recruitment rule": ["origin", "capital", "age", "lvl"],
    "Physical": ["attr:Pace", "attr:Stamina", "attr:Strength", "attr:Agility"],
    ...Object.fromEntries(Object.entries(D.STAT_PRESETS).map(([k, v]) => [k, v.map((s) => `stat:${s}`)])),
  };

  // ---- filters that sit above the table
  let showLoanIn = false;
  let showShortlist = false;
  let unit = "all";
  const UNITS = {
    all: () => true,
    GK: (r) => r.r.pos === "GK",
    Defence: (r) => /^D/.test(r.r.pos) && r.r.pos !== "DMC",
    Midfield: (r) => ["DMC", "MC", "ML", "MR"].includes(r.r.pos),
    Attack: (r) => ["AMC", "AML", "AMR", "ST"].includes(r.r.pos),
  };
  const selected = new Set();

  const loanBtn = el("button.btn", {
    text: "Hide loanees", title: "Loaned-IN players go back at the end of the spell, so counting them makes the squad look deeper than it is",
    onclick: () => {
      showLoanIn = !showLoanIn;
      loanBtn.textContent = showLoanIn ? "Showing loanees" : "Hide loanees";
      loanBtn.classList.toggle("on", showLoanIn);
      t.redraw();
    },
  });
  const unitSel = el("select.btn", { onchange: (e) => { unit = e.target.value; t.redraw(); } },
    Object.keys(UNITS).map((u) => el("option", { value: u, text: u === "all" ? "All positions" : u })));
  const slBtn = el("button.btn", {
    text: "Show shortlist",
    title: "Add shortlisted players to the table alongside the squad, rated and filtered exactly the same way, so they can be picked for Compare",
    onclick: async () => {
      showShortlist = !showShortlist;
      slBtn.classList.toggle("on", showShortlist);
      if (showShortlist) {
        if (!localStorage.getItem(D.SHORTLIST_TOKEN_KEY)) {
          showShortlist = false;
          slBtn.classList.remove("on");
          return toast("Save your shortlist device token in Recruitment → Shortlist first", true);
        }
        slBtn.textContent = "Loading shortlist…";
        // Drop any rows from a previous toggle before adding fresh ones, so re-showing after an
        // edit elsewhere doesn't duplicate a player who's still on the list.
        for (let i = rows.length - 1; i >= 0; i--) if (rows[i].shortlist) rows.splice(i, 1);
        const { rows: slRows, missing } = await buildShortlistRows();
        rows.push(...slRows);
        if (missing) {
          toast(`${missing} shortlist ${missing === 1 ? "entry has" : "entries have"} no tid, `
            + "or aren't in this save, so they can't be rated here", true);
        }
      }
      slBtn.textContent = showShortlist ? "Showing shortlist" : "Show shortlist";
      t.redraw();
    },
  });
  const cmpBtn = el("button.btn", {
    text: "Compare (0)", title: "Tap rows with Compare armed to pick 2-4 players",
    onclick: () => {
      if (selected.size >= 2) openCompare([...selected]);
      else toast("Tap 2 or more rows to compare them", true);
    },
  });
  const armBtn = el("button.btn", {
    text: "Pick", title: "Arm row-tapping to select players for comparison instead of opening a profile",
    onclick: () => {
      arm = !arm;
      armBtn.classList.toggle("on", arm);
      armBtn.textContent = arm ? "Picking" : "Pick";
      if (!arm) { selected.clear(); cmpBtn.textContent = "Compare (0)"; t.redraw(); }
    },
  });
  let arm = false;

  const t = playerTable({
    key: "squad",
    rows,
    catalogue,
    presets,
    sticky: ["player"],
    defaults: ["age", "pos", "fam", "rating", "fit", "lvl", "growth", "traj", "expiry", "status"],
    sort: { by: "rating", dir: "desc" },
    searchPlaceholder: "Search our squad…",
    toolbar: [unitSel, loanBtn, slBtn, armBtn, cmpBtn],
    filter: (r) => (showLoanIn || !r.loanedIn) && (showShortlist || !r.shortlist) && UNITS[unit](r),
    rowClass: (r) => (selected.has(r.tid) ? "picked" : null),
    empty: "No player matches those filters.",
    onRow: (r) => {
      if (!arm) return openProfile(r.tid, { role: r.r.role });
      if (selected.has(r.tid)) selected.delete(r.tid);
      else if (selected.size < 4) selected.add(r.tid);
      else return toast("Four at a time is the useful maximum", true);
      cmpBtn.textContent = `Compare (${selected.size})`;
      t.redraw();                                  // paint the selection back onto the rows
    },
  });

  const owned = rows.filter((r) => !r.loanedIn && !r.shortlist);
  const wage = owned.reduce((a, r) => a + (r.player.wage || 0), 0);
  const ageAvg = owned.filter((r) => r.age != null);
  const grew = owned.filter((r) => r.growth && r.growth.delta > 0).length;

  return el("div", {}, [
    el("h2", { text: `Squad · ${D.S.method}` }),
    el("div.kpis", {}, [
      kpi("Owned", owned.length), kpi("On loan in", rows.length - owned.length),
      kpi("Avg age", ageAvg.length ? num(ageAvg.reduce((a, r) => a + r.age, 0) / ageAvg.length, 1) : DASH),
      kpi("Wage bill/yr", money(wage)),
      kpi("Improving", `${grew}/${owned.length}`),
    ]),
    t.node,
    el("p.note", {
      html: "Tap a row for the full profile — attributes weighted by this tactic, growth, match "
        + "record and career history. <b>Show shortlist</b> adds shortlisted players to the table "
        + "under the same columns and filters as the squad. <b>Pick</b> turns tapping into "
        + "multi-select so you can <b>Compare</b> 2-4 players — squad and shortlist alike. Every "
        + "rating recomputes when you change tactic in the header; <b>Level %ile</b> doesn't, "
        + "because it measures quality rather than fit.",
    }),
  ]);
}

const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
