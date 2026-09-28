/**
 * Squad — one table, every question. This is where the old Squad list, Development, Player
 * Stats and Registration pages collapse into a single thing: identity, tactic fit, level,
 * growth, projections, contract, registration, any of the 23 attributes and any match stat are
 * all columns in the same grid, added and removed from one picker.
 *
 * Why one table rather than three pages: they were three views of the same rows differing only
 * in which columns were on screen, so the split was arbitrary — and it meant you could never
 * ask a question that crossed two of them ("who's growing AND has pace AND plays minutes").
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, bar, num, money, monthYear, sparkline, pill, attrValue, DASH, toast } from "../ui.js";
import { openProfile, openCompare } from "../profile.js";
import { registrationKit } from "../registration.js";

// mart.player_development's words, most growth left first.
const DEV_WORDS = ["Lots to come", "Developing", "Nearly there", "At his ceiling"];

// Projection target age (21 or 24 — the two horizons api/forecast.json publishes). Same key the
// old Development page used, so a saved choice carries over.
const DEV_KEY = "fm:development";
const loadToAge = () => {
  try { return JSON.parse(localStorage.getItem(DEV_KEY) || "{}").toAge === 21 ? 21 : 24; } catch { return 24; }
};

export async function view() {
  const [, M, forecast] = await Promise.all([D.loadSquad(), D.loadMatches(), D.loadForecast()]);
  let toAge = loadToAge();
  let t = null;                                  // the table; assigned once built, below
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
    // Projection at the target age, rated at the SAME scoped role — his projected attributes
    // under this tactic, discounted by the same familiarity.
    row.projEff = row.fc ? D.rating(row.fc.attrs, r.role, method) * D.famMult(r.fam) : null;
    row.projDelta = row.projEff != null ? row.projEff - r.eff : null;
    return row;
  }

  // Shared by squad members and shortlist entries alike, so a shortlisted player slots into
  // exactly the same row shape and every column, filter and the compare picker just work on him
  // — no separate "compare a shortlist player" path to keep in sync with this one.
  function buildRow(p, extra = {}) {
    // Every listed position rated, primary (most familiar) first — bestRole() is just its [0], so
    // holding the whole list costs nothing extra and is what lets the row re-scope to a Position
    // filter.
    const roles = D.playerRoles(p, method).filter((r) => r.fam >= minFam);
    if (!roles.length) return null;
    const status = extra.status ?? (D.S.ours.status?.[String(p.tid)] || DASH);
    return scopeRow(project({
      tid: p.tid, player: p, roles,
      age: D.age(p.dob),
      status,
      loanedIn: loanedIn.has(p.tid),
      origin: D.S.ours.origin?.[String(p.tid)] || null,
      capital: (D.S.ours.capital_eligible || []).includes(p.tid),
      dev: D.S.ours.development?.[String(p.tid)] || null,
      // The profile tail: in core.json for our squad; a shortlisted player has it only once his
      // profile row has been fetched, so his columns read blank until then.
      prof: p.profile || null,
      alsoRoles: roles.map((x) => x.role).filter((x, i, a) => a.indexOf(x) === i),
      shortlist: !!extra.shortlist,
      // Searchable on every position he's listed at, not just the one on show — the row's
      // identity doesn't change when the Position filter re-points it.
      _search: [p.name, ...roles.map((x) => `${x.pos} ${x.role}`), status].join(" ").toLowerCase(),
    }));
  }

  /** The forecast half of a row: projected attributes at `toAge` and the points still to come.
   *  Independent of role, so it's redone only when the target age changes, not on re-scoping. */
  function project(row) {
    const p = row.player;
    row.fc = forecast ? D.forecastAttrs(p, toAge) : null;
    row.remain = forecast ? D.pointsRemaining(p, toAge) : null;
    row.curTotal = p.attrs.reduce((a, v) => a + (v || 0), 0);
    row.projTotal = row.fc ? row.fc.attrs.reduce((a, v) => a + (v || 0), 0) : null;
    return row;
  }

  const rows = [];
  for (const p of ours) {
    const row = buildRow(p);
    if (row) rows.push(row);
  }

  // Registration: list column, the squad card and the saved windows. `t` is resolved lazily —
  // the kit only calls redraw after the table exists.
  const regKit = await registrationKit({ squadRows: rows, redraw: () => t.redraw() });

  const forecastable = forecast ? D.S.attrs.filter((n) => forecast.buckets[n] === "forecastable") : [];
  const fixedAttrs = forecast ? D.S.attrs.filter((n) => forecast.buckets[n] === "fixed") : [];

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
      help: "Where he actually plays — his most familiar position, best-rated among equals. "
        + "Filtering on it matches any position he can play, and re-rates the whole row there.",
      // The COLUMN shows the position the row is scoped to; the FILTER offers every position he
      // is listed at, because "show me the left-backs" means everyone who can play there — and
      // picking one is what scopes the row to it in the first place (see scopeRow).
      filterValue: (r) => r.player.positions.map((q) => q.pos),
    },
    role: { label: "Role", group: "Identity", get: (r) => r.r.role },
    height: {
      label: "Height", group: "Identity", align: "num",
      help: "Height in cm", get: (r) => r.player.height || null,
    },
    weight: {
      label: "Weight", group: "Identity", align: "num",
      help: "Weight in kg", get: (r) => r.player.weight || null,
    },
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
      help: "Where this rating places him among our own players at the position in Pos, best to "
        + "worst — the table's default sort, because a rank is comparable across positions in a "
        + "way a rating isn't. Ties break on Fit %ile. For a shortlisted player this is "
        + "hypothetical — where he'd slot in if he joined.",
      // Negated so best-first reads as descending, plus Fit %ile as a thousandths-scale
      // tie-break: a rank alone puts every position's first choice in one undifferentiated
      // block, and squad order is not an interesting way to break that. Fit is 0-100, so the
      // fraction can never reach 1 and reorder the ranks themselves.
      sort: (r) => -r.teamRank + (r.fit ?? 0) / 1e4,
      render: (r) => el("span", { text: `${r.teamRank}/${r.teamPoolSize}` }),
      // A filter must still be asked in the numbers on screen ("1-3" = our top three there),
      // not in that composite sort key.
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
    dev: {
      label: "Development", group: "Growth",
      help: "How far he is from his ceiling, in words: Lots to come · Developing · Nearly there · "
        + "At his ceiling. Deliberately wide bands — whether there is growth left, not how much. "
        + "Read from HIS OWN ceiling in the save, so where it disagrees with the Projection "
        + "columns (which are what typical players like him went on to reach), this one is "
        + "about him. Our squad only.",
      get: (r) => DEV_WORDS.includes(r.dev) ? r.dev : null,
      // Ordered by growth left, not alphabetically, so descending reads "most to come" first.
      sort: (r) => (DEV_WORDS.includes(r.dev) ? DEV_WORDS.length - DEV_WORDS.indexOf(r.dev) : null),
      filterType: "set",
      filterValue: (r) => r.dev || null,
    },
    // ---- everything the profile sheet shows, one column per field
    ...profileColumns(),
    // ---- projection: what he looks like at the target age (population expectation, not a
    // per-player prediction — see api/forecast.json's note). Labels read the live target age.
    projRating: {
      get label() { return `Rating at ${toAge}`; }, group: "Projection", align: "num",
      help: "Rating recomputed on his projected attributes at the target age, at the position in "
        + "Pos under this tactic. Pick 21 or 24 with the Project-to control.",
      sort: (r) => r.projEff ?? r.r.eff, render: (r) => (r.fc ? num(r.projEff) : null),
    },
    projDelta: {
      get label() { return `Δ to ${toAge}`; }, group: "Projection", align: "num",
      help: "Projected rating minus rating now",
      sort: (r) => r.projDelta ?? null,
      render: (r) => (r.projDelta != null
        ? el("span", { class: r.projDelta >= 0 ? "" : "dim", text: `${r.projDelta >= 0 ? "+" : ""}${num(r.projDelta)}` })
        : null),
    },
    remain: {
      label: "Points left", group: "Projection", align: "num",
      help: "Total attribute points expected to be gained by the target age — median (p25-p75 band), from the whole save's age curve",
      sort: (r) => r.remain?.median ?? null,
      render: (r) => (r.remain
        ? el("span", {}, [num(r.remain.median), el("span.dim", { text: ` (${r.remain.p25}-${r.remain.p75})` })])
        : (r.age != null && r.age >= toAge ? el("span.dim", { text: "at target" }) : null)),
    },
    totals: {
      label: "Total now → target", group: "Projection", align: "num",
      sort: (r) => (r.projTotal ?? r.curTotal) - r.curTotal,
      render: (r) => (r.fc ? `${r.curTotal} → ${r.projTotal}` : String(r.curTotal)),
    },
    ...Object.fromEntries(forecastable.map((name) => {
      const i = D.S.attrs.indexOf(name);
      return [`fc:${name}`, {
        label: `${name} →`, group: "Projection · attribute now → projected", align: "num",
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
    ...(regKit ? regKit.columns : {}),
    ...metricColumns(D, { agg: D.S.matchAgg }),
  };

  const presets = {
    "Development": ["age", "dev", "growth", "traj", "rating", "projRating", "projDelta", "remain", "fit"],
    ...(regKit ? regKit.presets : {}),
    "Contracts": ["wage", "expiry", "value", "age", "status"],
    "Recruitment rule": ["origin", "capital", "age", "lvl"],
    "Reputation": ["age", "repHome", "repCurrent", "repWorld", "value", "lvl"],
    "Bio": ["age", "nation", "height", "weight", "foot", "footL", "footR", "shirt", "joined", "caps"],
    "Personality": PERSONALITY.map(([k]) => `pers:${k}`),
    "Hidden": HIDDEN.map(([k]) => `hid:${k}`),
    "Physical": ["height", "weight", "attr:Pace", "attr:Stamina", "attr:Strength", "attr:Agility"],
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

  // Only on show while a projection column is, so it isn't one more control to read past.
  const PROJ_COLS = new Set(["projRating", "projDelta", "remain", "totals"]);
  const targetSel = el("select.btn", {
    title: "Target age for the Projection columns",
    onchange: (e) => {
      toAge = Number(e.target.value);
      try { localStorage.setItem(DEV_KEY, JSON.stringify({ toAge })); } catch { /* private mode */ }
      rows.forEach((r) => scopeRow(project(r)));
      t.redraw();
    },
  }, [21, 24].map((y) => el("option", { value: y, text: `Project to ${y}`, selected: y === toAge })));
  const syncTarget = () => {
    targetSel.hidden = !forecast
      || !(t?.state.cols || []).some((c) => PROJ_COLS.has(c) || c.startsWith("fc:"));
  };

  t = playerTable({
    key: "squad",
    rows,
    catalogue,
    presets,
    sticky: ["player"],
    defaults: ["age", "pos", "fam", "rating", "fit", "teamRank", "lvl", "growth", "traj", "expiry", "status"],
    // Squad Rank, not Rating: a rating only means something against the same position, so
    // ranking the whole squad by it sorted our midfielders to the top on the size of the CM
    // weight block. A rank is per-position by construction, so the table opens on every
    // position's first choice, then every second choice. `v` bumped so the retune actually
    // reaches a browser holding the old saved sort.
    sort: { by: "teamRank", dir: "desc", v: 2 },
    searchPlaceholder: "Search our squad…",
    toolbar: [unitSel, posSel, targetSel, loanBtn, slBtn, armBtn, cmpBtn],
    // Range and set filters on every column, attributes and match stats included — the same panel
    // Recruitment's search table has. Squad is only ~50 rows, so this isn't about cutting a list
    // down to a readable size: it's about asking a question with more than one clause ("under 23,
    // Pace 14+, contract inside two years") without eyeballing eleven columns for the overlap.
    filters: true,
    // Runs before the filters it is handed are applied, so the values they test are the scoped
    // ones. Cheap to re-derive, but it is the join-key of the whole view, so only redo the work
    // when the selection actually changed — a draw also fires on every sort and keystroke.
    prepare: (fs) => {
      if (t) syncTarget();
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

  syncTarget();
  const owned = rows.filter((r) => !r.loanedIn && !r.shortlist);
  const ageAvg = owned.filter((r) => r.age != null);
  const grew = owned.filter((r) => r.growth && r.growth.delta > 0).length;

  // Value and wage bill come from mart.squad_finances for THIS snapshot — the same numbers the
  // History table shows per season, owned players only. Summing the rows is the fallback for an
  // export that predates it (and then counts stated values only).
  const snap = D.S.index.snapshot;
  const fin = (M.finances || []).map((r) => Object.fromEntries((M.finance_fields || []).map((n, i) => [n, r[i]])))
    .find((f) => f.season === snap.season && f.phase === snap.phase);
  const value = fin ? fin.value_gbp : owned.reduce((a, r) => a + (r.player.value || 0), 0);
  const wage = fin ? fin.wage_gbp : owned.reduce((a, r) => a + (r.player.wage || 0), 0);
  const valueTitle = fin?.n_value_est
    ? `${fin.n_value_est} of ${fin.n_owned} owned players have no value in the save and are valued by the model. Loanees excluded.`
    : "Owned players only — loanees excluded.";

  return el("div", {}, [
    el("h2", { text: `Squad · ${D.S.method}` }),
    el("div.kpis", {}, [
      regKit ? regKit.card : kpi("Owned", owned.length),
      kpi("Squad value", money(value), valueTitle),
      kpi("Wage bill/yr", money(wage), "Owned players only — a loanee's wage share isn't in the save"),
      kpi("Avg age", ageAvg.length ? num(ageAvg.reduce((a, r) => a + r.age, 0) / ageAvg.length, 1) : DASH),
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
        + "players happens to be listed at AML\". <b>Pos</b> is otherwise his primary position — "
        + "the one he's most familiar at — and a Rating only compares like with like within a "
        + "position, because each role weights a different number of attributes; across "
        + "positions, read <b>Fit %ile</b>. Every "
        + "rating recomputes when you change tactic in the header; <b>Level %ile</b> doesn't, "
        + "because it measures quality rather than fit. The <b>Projection</b> columns (Development "
        + "preset) are a population expectation with a band, not a per-player prediction — current "
        + "value and age predict a future value well, but one attribute does not predict how fast "
        + "another grows."
        + (fixedAttrs.length ? ` ${fixedAttrs.join(" and ")} never move in real play.` : "")
        + (regKit ? " The <b>Squad</b> card is registration under the Danish rules (a house "
          + "rule — the save has no A/B lists): hover or tap it for the breakdown, and set lists "
          + "in the <b>List</b> column (Registration preset)." : ""),
    }),
    regKit ? regKit.windowsPanel : null,
  ]);
}

const kpi = (label, value, title) => el("div.kpi", { title }, [el("b", { text: String(value) }), el("span", { text: label })]);

// The profile sheet's personality and hidden-attribute blocks, as [key, label] in the order the
// sheet lists them — one Squad column each.
const PERSONALITY = [["adaptability", "Adaptability"], ["ambition", "Ambition"],
  ["determination", "Determination"], ["loyalty", "Loyalty"], ["pressure", "Pressure"],
  ["professionalism", "Professionalism"], ["sportsmanship", "Sportsmanship"],
  ["temperament", "Temperament"]];
const HIDDEN = [["jumping", "Jumping"], ["consistency", "Consistency"], ["bigMatch", "Big match"],
  ["injuryProne", "Injury proneness"], ["versatility", "Versatility"], ["setPieces", "Set pieces"],
  ["penalty", "Penalties"], ["workRate", "Work rate"], ["flair", "Flair"]];

/** Stronger foot as a word: the better-rated foot, "Both" when they're within 2 of each other. */
const strongFoot = (l, r) => (l == null || r == null ? null
  : Math.abs(l - r) <= 2 ? "Both" : l > r ? "Left" : "Right");

/** One column per field of the profile tail (`row.prof`, null for a shortlisted player whose
 *  profile hasn't been fetched), so anything the profile sheet shows can be sorted and filtered. */
function profileColumns() {
  const pv = (f) => (r) => (r.prof ? f(r.prof) ?? null : null);
  const numCol = (label, group, f, help) => ({ label, group, align: "num", help, get: pv(f) });
  const attrCol = (label, group, f, help) => ({
    label, group, align: "num", help,
    sort: pv(f), render: (r) => { const v = pv(f)(r); return v == null ? null : attrValue(v); },
    filterValue: pv(f),
  });
  return {
    nation: { label: "Nationality", group: "Bio", get: pv((p) => p.nationality) },
    foot: {
      label: "Foot", group: "Bio",
      help: "Stronger foot — 'Both' when the two are within 2 of each other",
      get: pv((p) => strongFoot(p.footLeft, p.footRight)),
    },
    footL: attrCol("Left foot", "Bio", (p) => p.footLeft, "Left foot, 1-20"),
    footR: attrCol("Right foot", "Bio", (p) => p.footRight, "Right foot, 1-20"),
    shirt: { label: "No.", group: "Bio", align: "num", help: "Squad number", get: (r) => r.player.shirt || null },
    prefShirt: numCol("Pref. no.", "Bio", (p) => p.preferredShirt || null, "The squad number he'd prefer"),
    joined: {
      label: "Joined", group: "Bio", help: "When he joined the club",
      sort: pv((p) => p.joinedDate), render: (r) => (r.prof?.joinedDate ? monthYear(r.prof.joinedDate) : null),
      filterType: "none",
    },
    caps: numCol("Caps", "Bio", (p) => p.caps, "Senior international caps"),
    intGoals: numCol("Int. goals", "Bio", (p) => p.goals, "Senior international goals"),
    u21Caps: numCol("U21 caps", "Bio", (p) => p.u21Caps),
    u21Goals: numCol("U21 goals", "Bio", (p) => p.u21Goals),
    repHome: numCol("Home rep", "Reputation", (p) => p.reputation.home, "Reputation in his home nation"),
    repCurrent: numCol("Current rep", "Reputation", (p) => p.reputation.current, "Current reputation"),
    repWorld: numCol("World rep", "Reputation", (p) => p.reputation.world, "Worldwide reputation"),
    ...Object.fromEntries(PERSONALITY.map(([k, label]) =>
      [`pers:${k}`, attrCol(label, "Personality", (p) => p.personality[k])])),
    ...Object.fromEntries(HIDDEN.map(([k, label]) =>
      [`hid:${k}`, attrCol(label, "Hidden attributes", (p) => p.hidden[k],
        `${label} — one of the attributes the in-game screen doesn't show`)])),
  };
}
