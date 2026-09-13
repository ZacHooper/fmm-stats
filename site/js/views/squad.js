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

  // Rank within the squad itself, not the division — a separate pool because "who's our best
  // right-back" and "how good is our right-back situation vs the league" are different questions.
  // Built from `ours` only (never the shortlist), so a shortlisted or scouted player's row asks
  // "where would he slot in if he joined" rather than moving the goalposts he's judged against.
  const teamPools = new Map();
  const teamPoolFor = (pos) => {
    if (!teamPools.has(pos)) teamPools.set(pos, D.teamPool(ours, pos, method));
    return teamPools.get(pos);
  };

  // The positions the table is currently scoped to — [] for "all". Owned by the Pos COLUMN
  // FILTER (the dropdown just writes into it, see posSel), because it doesn't merely hide rows:
  // every rating-shaped column is READ AT these positions (see scopeRow), so one source of truth
  // is the only way the number in a cell and the number a filter tested can't disagree.
  let scopePos = [];

  /**
   * Point a row at the role it should describe: his best at a scoped position, or his overall
   * best when Position isn't filtered (unchanged from before this existed). Everything derived
   * from a role travels with it — Fam, Rating, Base, Fit, Squad Rank, Level and the growth pair
   * are all "at that position" numbers, and leaving any of them on the best role would put two
   * different positions side by side in one row. Several positions scope to the best of them, so
   * "AML or AMR" reads each player at his better flank. A row that can't play any of them keeps
   * his best role; the table filter has already dropped him.
   */
  function scopeRow(row) {
    let r = null;
    if (scopePos.length) {
      for (const q of row.roles) if (scopePos.includes(q.pos) && (!r || q.eff > r.eff)) r = q;
    }
    r = r || row.roles[0];
    const teamPool = teamPoolFor(r.pos);
    row.r = r;
    row.growth = D.growth(row.tid, r.role, method);
    row.traj = D.trajectory(row.tid, r.role, method);
    row.fit = D.pctile(poolFor(r.pos), r.eff);
    row.teamRank = D.rankIn(teamPool, r.eff);
    row.teamPoolSize = teamPool.length;
    return row;
  }

  // Shared by squad members and shortlist entries alike, so a shortlisted player slots into
  // exactly the same row shape and every column, filter and the compare picker just work on him
  // — no separate "compare a shortlist player" path to keep in sync with this one.
  function buildRow(p, extra = {}) {
    // Every listed position rated, best-first — bestRole() is just its [0], so holding the whole
    // list costs nothing extra and is what lets the row re-scope to a Position filter.
    const roles = D.playerRoles(p, method).filter((r) => r.fam >= minFam);
    if (!roles.length) return null;
    const status = extra.status ?? (D.S.ours.status?.[String(p.tid)] || DASH);
    return scopeRow({
      tid: p.tid, player: p, roles,
      age: D.age(p.dob),
      status,
      loanedIn: loanedIn.has(p.tid),
      origin: D.S.ours.origin?.[String(p.tid)] || null,
      capital: (D.S.ours.capital_eligible || []).includes(p.tid),
      alsoRoles: roles.map((x) => x.role).filter((x, i, a) => a.indexOf(x) === i),
      shortlist: !!extra.shortlist,
      // Searchable on every position he's listed at, not just the one on show — the row's
      // identity doesn't change when the Position filter re-points it.
      _search: [p.name, ...roles.map((x) => `${x.pos} ${x.role}`), status].join(" ").toLowerCase(),
    });
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
    pos: {
      label: "Pos", group: "Identity", get: (r) => r.r.pos,
      help: "His best position under this tactic. Filtering on it matches any position he can "
        + "play, and re-rates the whole row there.",
      // The COLUMN shows the position the row is scoped to; the FILTER offers every position he
      // is listed at, because "show me the left-backs" means everyone who can play there — and
      // picking one is what scopes the row to it in the first place (see scopeRow).
      filterValue: (r) => r.player.positions.map((q) => q.pos),
    },
    role: { label: "Role", group: "Identity", get: (r) => r.r.role },
    fam: {
      label: "Fam", group: "Identity", align: "num",
      help: "Position familiarity 0-20, at the position in Pos. The rating is already discounted by it, so a high rating on a low Fam means raw attributes are carrying him somewhere he doesn't play.",
      sort: (r) => r.r.fam, render: (r) => bar(r.r.fam, { max: 20, lo: 60 }),
      // Reads the scoped role like every other rating column, so a Pos filter answers "Fam 18+
      // AT DR" rather than letting an unrelated best role qualify him — the trap recruit.js's
      // scoped() filterValue exists to avoid, closed here by scoping the row itself instead.
    },
    also: {
      label: "Also", group: "Identity",
      help: "Other roles he rates in under this tactic",
      get: (r) => r.alsoRoles.filter((x) => x !== r.r.role).join(", ") || DASH,
    },
    status: { label: "Squad", group: "Identity", get: (r) => r.status },
    rating: {
      label: "Rating", group: "Rating", align: "num",
      help: "This tactic's weighted attribute sum × the familiarity multiplier, at the position in "
        + "Pos — filter by Position to rate everyone there instead of at their own best role",
      sort: (r) => r.r.eff, render: (r) => num(r.r.eff),
    },
    base: {
      label: "Base", group: "Rating", align: "num",
      help: "Rating before the familiarity discount",
      sort: (r) => r.r.rating, render: (r) => num(r.r.rating),
    },
    fit: {
      label: "Fit %ile", group: "Rating", align: "num",
      help: "Where he sits at the position in Pos in OUR division under this tactic — fit, not level",
      sort: (r) => r.fit, render: (r) => bar(r.fit),
    },
    teamRank: {
      label: "Squad Rank", group: "Rating", align: "num",
      help: "Where this rating places him among our own players at the position in Pos, best to worst. "
        + "For a shortlisted player this is hypothetical — where he'd slot in if he joined.",
      sort: (r) => -r.teamRank, render: (r) => el("span", { text: `${r.teamRank}/${r.teamPoolSize}` }),
      // `sort` is negated so that best-first reads as descending; a filter must still be asked
      // in the numbers on screen ("1-3" = our top three there), not in their sort rank.
      filterValue: (r) => r.teamRank,
    },
    lvl: {
      label: "Level %ile", group: "Rating", align: "num",
      help: "Quality at the position in Pos within his own league — tactic-agnostic, derived from the game's ability rating",
      sort: (r) => r.r.lvlLeague, render: (r) => bar(r.r.lvlLeague),
    },
    lvlg: {
      label: "Level %ile (world)", group: "Rating", align: "num",
      help: "Quality at the position in Pos across every league in the save",
      sort: (r) => r.r.lvlGlobal, render: (r) => bar(r.r.lvlGlobal),
    },
    growth: {
      label: "Δ", group: "Growth", align: "num",
      help: "Rating change since his first snapshot, recomputed under this tactic at the position in Pos",
      sort: (r) => r.growth?.delta ?? null,
      render: (r) => (r.growth
        ? el("span", { class: r.growth.delta >= 0 ? "" : "dim", text: `${r.growth.delta >= 0 ? "+" : ""}${num(r.growth.delta)}` })
        : null),
    },
    traj: {
      label: "Trend", group: "Growth",
      help: "Rating across every loaded snapshot, under this tactic at the position in Pos",
      sort: (r) => r.growth?.delta ?? null,
      render: (r) => sparkline(r.traj.map((t) => t.value)),
      filterType: "none",                          // a shape, not a value — Δ is how you filter it
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
      // Render-only, and its `sort` is a display rank rather than a value, so the filter has to
      // be told what it is actually choosing between — same shape recruit.js's column uses.
      filterType: "set",
      filterValue: (r) => (r.capital ? "Eligible" : "Outside"),
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
  // Unit reads his OWN best position (roles[0]), not the scoped one the rest of the row shows, so
  // the two filters stay independent instead of Unit becoming a tautology the moment a Position is
  // picked: "AML" + "Defence" then means our full-backs judged at AML, which is a real question.
  // With no Position filter the two are the same position anyway.
  const home = (r) => r.roles[0].pos;
  const UNITS = {
    all: () => true,
    GK: (r) => home(r) === "GK",
    Defence: (r) => /^D/.test(home(r)) && home(r) !== "DMC",
    Midfield: (r) => ["DMC", "MC", "ML", "MR"].includes(home(r)),
    Attack: (r) => ["AMC", "AML", "AMR", "ST"].includes(home(r)),
  };
  // Every position the game has is on offer, not just the ones that happen to be someone's
  // tactic-best: under a strikerless tactic nobody rates ST as their best role, but "who could I
  // play at ST if I switched" is still a real question — and with the row scoped to it, the
  // answer is his ST rating rather than his best-role one. Matches how the same filter behaves on
  // Recruitment's search table.
  const POSITIONS = D.POS_ORDER.filter((p) => rows.some((r) => r.player.positions.some((q) => q.pos === p)));
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
    Object.keys(UNITS).map((u) => el("option", { value: u, text: u === "all" ? "All units" : u })));
  // A one-tap shortcut that WRITES THE POS COLUMN FILTER rather than keeping a second position
  // state of its own — two controls doing the same job is how a dropdown and a chip end up
  // disagreeing about what the table is showing. Picking several positions is only expressible
  // in the chip, so the dropdown shows "Several" and hands over rather than silently dropping
  // the extras.
  const MULTI = "__multi";
  const posSel = el("select.btn", {
    title: "Filter to players who can play there — and read every rating column AT that position "
      + "rather than at whichever role each player rates best overall. Same filter as the Pos "
      + "chip under Filters, which can take more than one position.",
    onchange: (e) => {
      if (e.target.value === MULTI) return;        // a label, not a choice
      setPosFilter(e.target.value === "all" ? [] : [e.target.value]);
      t.persist();
      t.redraw();
    },
  }, [el("option", { value: "all", text: "All positions" }),
    ...POSITIONS.map((p) => el("option", { value: p, text: p })),
    el("option", { value: MULTI, text: "Several — see the Pos chip", hidden: true })]);

  /** Point the table's own Pos filter at `list`, adding or dropping the chip as needed. */
  function setPosFilter(list) {
    const fs = (t.state.filters || []).filter((f) => f.col !== "pos");
    if (list.length) fs.push({ col: "pos", type: "set", values: list, nulls: false });
    t.state.filters = fs;
  }
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
    defaults: ["age", "pos", "fam", "rating", "fit", "teamRank", "lvl", "growth", "traj", "expiry", "status"],
    sort: { by: "rating", dir: "desc" },
    searchPlaceholder: "Search our squad…",
    toolbar: [unitSel, posSel, loanBtn, slBtn, armBtn, cmpBtn],
    // Range and set filters on every column, attributes and match stats included — the same panel
    // Recruitment's search table has. Squad is only ~50 rows, so this isn't about cutting a list
    // down to a readable size: it's about asking a question with more than one clause ("under 23,
    // Pace 14+, contract inside two years") without eyeballing eleven columns for the overlap.
    filters: true,
    // Runs before the filters it is handed are applied, so the values they test are the scoped
    // ones. Cheap to re-derive, but it is the join-key of the whole view, so only redo the work
    // when the selection actually changed — a draw also fires on every sort and keystroke.
    prepare: (fs) => {
      const sel = (fs.find((f) => f.col === "pos")?.values || []).filter((p) => POSITIONS.includes(p));
      if (sel.join() === scopePos.join()) return;
      scopePos = sel;
      rows.forEach(scopeRow);
      posSel.value = sel.length === 0 ? "all" : sel.length === 1 ? sel[0] : MULTI;
    },
    // The column filters compose with this, never replace it: Unit and the loan/shortlist toggles
    // are groupings of the squad rather than columns, so they stay here. Position left on purpose
    // — it is the Pos column filter now, which is what lets it re-rate the row as well as hide it.
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
        + "multi-select so you can <b>Compare</b> 2-4 players — squad and shortlist alike. "
        + "<b>Filters</b> stacks range and set conditions on any column, attributes and match "
        + "stats included. Picking a <b>Position</b> — from the dropdown or the same filter's Pos "
        + "chip — doesn't just hide rows: every rating column is then read AT that position, so "
        + "the table answers \"who's our best AML\" rather than \"which of our best-elsewhere "
        + "players happens to be listed at AML\". <b>Pos</b> is otherwise his highest-RATED "
        + "position, which needn't be his most familiar one, and a Rating only compares like "
        + "with like within a position — across positions, read <b>Fit %ile</b>. Every "
        + "rating recomputes when you change tactic in the header; <b>Level %ile</b> doesn't, "
        + "because it measures quality rather than fit.",
    }),
  ]);
}

const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
