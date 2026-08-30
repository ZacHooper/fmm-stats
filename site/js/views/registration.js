/**
 * Registration — the squad we are allowed to field, under a rule FMM22 does not enforce.
 *
 * The Danish rulebook (docs/danish-registration-rules.md) caps the A-list at 25 and, in the top
 * two tiers, requires 8 home-grown players on it of whom at least 4 were trained at the club
 * itself; the B-list takes an unlimited number of players who were under 21 at the last new
 * year, and does not touch the cap. None of that exists in the save, so this page is where the
 * restriction lives: pick the two lists, and it tells you what the rulebook would say.
 *
 * WHY THE PICKING IS INTERESTING, and why this is not just a checklist. The B-list is free, so
 * the obvious move is to park every U21 on it — but the home-grown minimums are counted on the
 * A-LIST, and most home-grown players are young. Leaving a club-trained 21-year-old on the B-list
 * to save a slot can cost a home-grown credit and shrink the A-list by one, which is exactly the
 * trade the summary bar is there to show while you make it.
 *
 * The assignment is per-device state (localStorage, keyed by snapshot). It is a plan, not a fact
 * about the save — nothing here is written back, and re-exporting a new snapshot starts a new
 * plan rather than silently reusing a stale one.
 */
import * as D from "../data.js";
import { playerTable } from "../table.js";
import { el, bar, num, pill, DASH, toast } from "../ui.js";
import { openProfile } from "../profile.js";

const A = "A", B = "B", OUT = "-";
// How many players per position the suggestion treats as the spine. Two is a starter plus
// his cover; the picker offers 1-3 because how deep "the squad" goes is a manager's call,
// not a rule — the rulebook only ever counts to 25.
const DEFAULT_DEPTH = 2, DEPTH_KEY = "fm:registration:depth";
// Familiarity at or above which a player is treated as able to play a position rather than
// merely listed there. Matches dashboard/positions.py's DEFAULT_MIN_FAM, so the site and the
// depth charts agree on what "he can play there" means.
const FAM_FLOOR = 15;

export async function view() {
  const R = await D.loadRegistration();
  const out = el("div");
  out.append(el("h2", { text: "Registration" }));
  if (!R || !R.rules || !R.players?.length) {
    out.append(el("div.card", {}, [
      el("b", { text: "No registration data in this export" }),
      el("p.note", {
        html: "Re-run <code>uv run python scripts/export_data.py</code> — the registration "
          + "family arrived in <code>fmparser/mart.py</code> after this export was built.",
      }),
    ]));
    return out;
  }

  const rules = R.rules;
  const reg = new Map();                       // tid -> the derived registration facts
  for (const row of R.players) {
    const o = {};
    R.fields.forEach((f, i) => { o[f] = row[i]; });
    reg.set(o.tid, o);
  }

  const method = D.S.method;
  const ourCid = D.ourLeagueCid();
  const divPlayers = D.leaguePlayers(ourCid);
  const pools = new Map();
  const poolFor = (pos) => {
    if (!pools.has(pos)) pools.set(pos, D.poolAt(divPlayers, pos, method, 0));
    return pools.get(pos);
  };

  const rows = [];
  for (const p of D.ourPlayers()) {
    const h = reg.get(p.tid);
    if (!h) continue;                          // no dob, so no window and no verdict
    const best = D.bestRole(p, method, 0);
    rows.push({
      tid: p.tid, player: p, r: best, h,
      age: h.age ?? D.age(p.dob),
      status: D.S.ours.status?.[String(p.tid)] || DASH,
      loanedIn: (D.S.ours.loaned_in || []).includes(p.tid),
      eff: best ? best.eff : 0,
      fit: best ? D.pctile(poolFor(best.pos), best.eff) : null,
      _search: [p.name, best?.pos, best?.role, h.hg_club ? "homegrown club" : "",
                h.hg_association ? "homegrown" : "", h.b_list ? "b-list u21" : ""]
        .join(" ").toLowerCase(),
    });
  }

  // ---- the plan itself ------------------------------------------------------------
  const KEY = `fm:registration:${D.S.index.snapshot.season}:${D.S.index.snapshot.phase}`;
  let depth = Number(localStorage.getItem(DEPTH_KEY)) || DEFAULT_DEPTH;
  if (![1, 2, 3].includes(depth)) depth = DEFAULT_DEPTH;
  let plan = load(KEY);
  if (!plan) { plan = suggest(rows, rules, depth, method); save(KEY, plan); }
  // A player who arrived since the plan was saved has no entry yet; default him rather than
  // dropping him, so a mid-window signing shows up as a decision to make instead of vanishing.
  for (const r of rows) if (!(r.tid in plan)) plan[r.tid] = r.h.b_list ? B : OUT;

  const summary = el("div");
  const warnings = el("div");

  const setList = (tid, list) => {
    plan[tid] = list;
    save(KEY, plan);
    drawSummary();
    drawDepth();
  };

  function drawSummary() {
    const t = tally(rows, plan, rules);
    summary.replaceChildren(
      el("div.kpis", {}, [
        // The denominator stays the rulebook's 25 whatever the penalty does. Showing "24 / 24"
        // read as "the cap is 24", when 25 is the cap and 24 is this list's reduced allowance —
        // so the reduction is named in the label instead of hidden in the denominator.
        kpi(t.missing ? `A-list · ${t.cap} allowed` : "A-list",
            `${t.a} / ${rules.a_list_max}`,
            t.a > t.cap ? "bad" : t.missing ? "warn" : "good"),
        kpi("Home grown on A", `${t.hgCounted} / ${rules.hg_min}`,
            t.hgCounted >= rules.hg_min ? "good" : "bad"),
        kpi("…of them club-trained", `${t.club} / ${rules.hg_club_min}`,
            t.club >= rules.hg_club_min ? "good" : "bad"),
        kpi("B-list", String(t.b)),
        kpi("Unregistered", String(t.out), t.out ? "warn" : "good"),
      ]),
      el("p.note", {
        html: t.missing
          ? `<b>${t.missing} home-grown place${t.missing === 1 ? "" : "s"} short</b> — the A-list `
            + `is reduced to ${t.cap} rather than ${rules.a_list_max}. No fine and no points `
            + `deduction; you simply register fewer players.`
          : `Home-grown minimums met, so the full ${rules.a_list_max}-man A-list is available.`,
      }),
    );

    const cannotPlay = rows.filter((r) => plan[r.tid] === OUT);
    const swappable = rows.filter((r) => plan[r.tid] === A && r.h.b_list).length;
    const overCap = Math.max(0, t.a - t.cap);
    warnings.replaceChildren(...[
      overCap ? el("div.card", {}, [
        el("b", { text: `${overCap} player${overCap === 1 ? "" : "s"} over the A-list cap` }),
        el("p.note", { text: "Everyone above the cap would be rejected by the administrator — "
          + "move someone to the B-list or leave him unregistered." }),
      ]) : null,
      cannotPlay.length ? el("div.card", {}, [
        el("b", { text: `${cannotPlay.length} unregistered — ineligible to play` }),
        el("p.note", {
          html: cannotPlay.map((r) => `${r.player.name} (${r.age})`).join(" · ")
            + ". Fielding one of these is normally a forfeit if the team won or drew.",
        }),
        // The way out is never obvious from the table: the A-list is full of players who would
        // still be available from the B-list, so a slot is one click away rather than a sale.
        swappable ? el("p.note", {
          html: `A slot can be freed without losing anyone — <b>${swappable}</b> player`
            + `${swappable === 1 ? "" : "s"} on the A-list ${swappable === 1 ? "is" : "are"} `
            + "B-list eligible and would still be available from there.",
        }) : null,
      ]) : null,
    ].filter(Boolean));
  }

  // A compact horizontal segmented control, not three stacked chips: this sits in a table cell,
  // and anything that wraps makes every row in the table as tall as the tallest cell.
  const listCell = (r) => {
    const wrap = el("span.seg", { onclick: (e) => e.stopPropagation() });
    const buttons = [[A, "A"], [B, "B"], [OUT, "—"]].map(([v, label]) => el(
      `button${plan[r.tid] === v ? ".on" : ""}`, {
        text: label,
        disabled: v === B && !r.h.b_list,
        title: v === B && !r.h.b_list
          ? `Not B-list eligible — he was 21 or older on ${rules.u21_on}`
          : `Put ${r.player.name} on the ${v === OUT ? "no" : v} list`,
        onclick: () => {
          setList(r.tid, v);
          for (const [i, b] of buttons.entries()) {
            b.classList.toggle("on", [A, B, OUT][i] === v);
          }
        },
      }));
    wrap.append(...buttons);
    return wrap;
  };

  // "Home grown" is the rulebook's UMBRELLA term — it covers both trained-here and trained-at-
  // another-Danish-club, and the quota counts them together. Naming this column after it made it
  // read as a definition ("home grown = Danish"), so the column asks the plainer question of
  // WHERE he trained and leaves "home grown" to the summary tiles, which is where the quota lives.
  const hgCell = (r) => {
    if (r.h.hg_club) {
      return pill(r.h.hg_basis === "clock" ? "Us (36mo)" : "Us (youth)", "good");
    }
    if (r.h.hg_association) return pill(r.h.origin_nation || "Association", "warn");
    return el("span.dim", { text: DASH });
  };

  const catalogue = {
    player: {
      label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name,
      render: (r) => el("span", {}, [r.player.name,
        r.loanedIn ? el("span.dim", { text: "  (loan in)" }) : null]),
    },
    list: {
      label: "List", group: "Registration",
      help: "A-list (capped, needs the home-grown minimums), B-list (unlimited, U21 only), or unregistered",
      sort: (r) => ({ A: 0, B: 1, "-": 2 })[plan[r.tid]], render: listCell,
    },
    hg: {
      label: "Trained at", group: "Registration",
      help: "Both count as HOME GROWN toward the 8. 'Us' also counts toward the 4 who must be "
        + "trained at the club itself; a Danish club does not.",
      sort: (r) => (r.h.hg_club ? 2 : r.h.hg_association ? 1 : 0), render: hgCell,
    },
    basis: {
      label: "Basis", group: "Registration",
      help: "academy = came through our youth side · youth-origin = his first recorded club was us, young enough to count · clock = 36 months with us inside the age-15-to-21 window",
      get: (r) => r.h.hg_basis || DASH,
    },
    months: {
      label: "Months", group: "Registration", align: "num",
      help: "Months registered with us inside his age-15-to-21 window. 36 makes him club-trained.",
      sort: (r) => r.h.months_club,
      render: (r) => bar(Math.min(36, r.h.months_club ?? 0), { max: 36, lo: 99, dp: 1 }),
    },
    eta: {
      label: "Home-grown date", group: "Registration",
      help: "When he becomes club-trained: the date he reaches 36 months with us if he stays. "
        + "'Already' = he counts now. Otherwise he cannot get there — either his age-21 window "
        + "has closed, or he cannot clock 36 months before it does.",
      sort: (r) => r.h.hg_eta || (r.h.hg_club ? "0000" : "9999"),
      render: (r) => (r.h.hg_club ? pill("Already", "good")
        : r.h.hg_eta ? el("span", { text: r.h.hg_eta })
        : el("span.dim", { text: r.h.window_open ? "Out of time" : "Window closed" })),
    },
    blist: {
      label: "B-list", group: "Registration",
      help: `Under 21 on ${rules.u21_on} — the fixed date the rule uses, so a player who turns 21 in the autumn keeps his place all season`,
      sort: (r) => (r.h.b_list ? 1 : 0),
      render: (r) => (r.h.b_list ? pill("Eligible", "good") : el("span.dim", { text: DASH })),
    },
    age: { label: "Age", group: "Identity", align: "num", get: (r) => r.age },
    pos: { label: "Pos", group: "Identity", get: (r) => r.r?.pos || DASH },
    status: { label: "Squad", group: "Identity", get: (r) => r.status },
    rating: {
      label: "Rating", group: "Rating", align: "num",
      help: "This tactic's weighted attribute sum × the familiarity multiplier",
      sort: (r) => r.eff, render: (r) => (r.r ? num(r.eff) : DASH),
    },
    fit: {
      label: "Fit %ile", group: "Rating", align: "num",
      help: "Where he sits among players in our division at his position, under this tactic",
      sort: (r) => r.fit, render: (r) => (r.fit == null ? DASH : bar(r.fit)),
    },
    origin: { label: "Origin club", group: "Origin", get: (r) => r.h.origin_club || DASH },
    originNation: { label: "Origin nation", group: "Origin", get: (r) => r.h.origin_nation || DASH },
  };

  const depthSel = el("select.btn", {
    title: "How many players per position the suggestion protects as the spine",
    onchange: (e) => {
      depth = Number(e.target.value);
      try { localStorage.setItem(DEPTH_KEY, String(depth)); } catch { /* private mode */ }
      rebuild();
    },
  }, [1, 2, 3].map((n) => el("option", {
    value: String(n), text: `Top ${n} per position`, selected: n === depth,
  })));

  const rebuild = () => {
    plan = suggest(rows, rules, depth, method);
    save(KEY, plan);
    const t = tally(rows, plan, rules);
    toast(t.out ? `${t.a} on the A-list · ${t.out} unregistered` : `${t.a} on the A-list`);
    table.redraw();
    drawSummary();
    drawDepth();
  };

  const toolbar = [
    depthSel,
    el("button.chip.ghost", {
      text: "Suggest a squad",
      title: "Loan-ins first, then the best players at each position, then the home-grown "
        + "top-up, then whoever is too old for the B-list and would otherwise be unable to play",
      onclick: rebuild,
    }),
    el("button.chip.ghost", {
      text: "Clear",
      onclick: () => {
        for (const r of rows) plan[r.tid] = OUT;
        save(KEY, plan);
        table.redraw();
        drawSummary();
        drawDepth();
      },
    }),
  ];

  const table = playerTable({
    key: "registration",
    rows,
    catalogue,
    sticky: ["player"],
    defaults: ["list", "hg", "age", "pos", "rating", "blist", "months", "eta"],
    presets: {
      Plan: ["list", "hg", "age", "pos", "rating", "blist"],
      "Home grown": ["hg", "basis", "months", "eta", "origin", "originNation"],
      Quality: ["list", "age", "pos", "rating", "fit", "status"],
    },
    sort: { by: "rating", dir: "desc" },
    toolbar,
    onRow: (r) => openProfile(r.tid, { role: r.r?.role }),
    searchPlaceholder: "Search the squad…",
    empty: "No squad players in this export.",
  });

  // ---- how the two lists cover the pitch ------------------------------------------
  // The table above answers "what did I do with this player"; this answers "what have I got at
  // right-back", which is the question a 25-man cap actually turns into. A player is counted at
  // EVERY position he lists, so the columns do not sum to the squad — depth is per position, and
  // a player covering three of them really is depth at three of them.
  const POS_ORDER = ["GK", "DL", "DC", "DR", "DML", "DMC", "DMR",
                     "ML", "MC", "MR", "AML", "AMC", "AMR", "ST"];
  const posRank = (p) => {
    const i = POS_ORDER.indexOf(p);
    return i === -1 ? POS_ORDER.length : i;
  };
  const depthTable = el("div");

  function drawDepth() {
    // ONLY fam-FAM_FLOOR-and-above is counted. Listing a position at familiarity 3 is not cover,
    // and counting it made every row look healthy — MR read 10 deep when two players could
    // actually play there. The position KEYS still come from every listed position, so a
    // position nobody is familiar with appears as a row of zeros rather than vanishing, which
    // is exactly the hole worth seeing.
    const by = new Map();
    for (const r of rows) {
      for (const q of r.player.positions) {
        if (!by.has(q.pos)) by.set(q.pos, { a: 0, b: 0, out: 0 });
        if (q.fam < FAM_FLOOR) continue;
        const c = by.get(q.pos);
        const l = plan[r.tid];
        if (l === A) c.a++; else if (l === B) c.b++; else c.out++;
      }
    }
    const list = [...by.entries()].sort((x, y) => posRank(x[0]) - posRank(y[0])
                                                  || x[0].localeCompare(y[0]));
    depthTable.replaceChildren(
      el("h3", { text: `Cover by position · familiarity ${FAM_FLOOR}+` }),
      el("div.scroll.fit", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Pos" }),
          el("th.num", { text: "A" }), el("th.num", { text: "B" }),
          el("th.num", { text: "Can field", title:
            `On either list and familiar enough to play there — the number that matters on a matchday` }),
          el("th.num", { text: "Unreg", title:
            "Familiar at this position but on neither list, so unavailable" }),
        ])]),
        el("tbody", {}, list.map(([pos, c]) => {
          const available = c.a + c.b;
          return el("tr", {}, [
            el("td.name", { text: pos }),
            el("td.num", { text: String(c.a) }),
            el("td.num", { text: String(c.b) }),
            el("td.num", {}, [
              available === 0 ? pill("none", "bad")
                : available === 1 ? pill("1", "warn")
                : el("span", { text: String(available) }),
            ]),
            el("td.num", {}, [c.out ? el("span.dim", { text: String(c.out) }) : DASH]),
          ]);
        })),
      ])]),
      el("p.note", {
        html: `Only players at familiarity <b>${FAM_FLOOR}+</b> are counted — a position listed at `
          + "3 is not cover. A player counts at every position he is familiar with, so these do "
          + "not sum to the squad. A position nobody qualifies at still appears, as "
          + "<b>none</b>; <b>Unreg</b> is cover you own but cannot field.",
      }),
    );
  }

  out.append(
    el("div.card", {}, [
      el("b", { text: `${rules.league_name} · tier ${rules.tier}` }),
      el("p.note", {
        html: rules.hg_min
          ? `A-list ${rules.a_list_max} players, including <b>${rules.hg_min} home grown</b> of `
            + `whom at least <b>${rules.hg_club_min} trained here</b>. B-list unlimited, for `
            + `players under ${rules.b_list_under_age} on ${rules.u21_on}.<br>`
            + `<b>&ldquo;Home grown&rdquo; is the umbrella</b>: it means trained at <i>us</i> OR at `
            + `another ${rules.nation || "domestic"} club. Only the first kind counts toward the `
            + `${rules.hg_club_min}. `
            + `<a href="guides/registration.md">How it is derived</a>.`
          : `A-list ${rules.a_list_max} players, no home-grown requirement in tier ${rules.tier}. `
            + `B-list unlimited, for players under ${rules.b_list_under_age} on ${rules.u21_on}.`,
      }),
    ]),
    summary, warnings, table.node, depthTable,
  );
  drawSummary();
  drawDepth();
  return out;
}

// --------------------------------------------------------------------------- the rule maths

/**
 * How many home-grown players the A-list actually gets credit for.
 *
 * Not simply "count the home-grown players": the rule is 8 in total, at least 4 trained at the
 * club, and the REMAINDER up to 4 from elsewhere in the association. So a list with 3
 * club-trained and 5 association-trained is credited 7, not 8 — the fifth association player has
 * no place left to fill. That asymmetry is the whole reason the club-trained column matters more
 * than the total.
 */
export function hgCredit(club, association, rules) {
  const c = Math.min(club, rules.hg_min);
  return c + Math.min(association, rules.hg_min - c, rules.hg_min - rules.hg_club_min);
}

function tally(rows, plan, rules) {
  let a = 0, b = 0, out = 0, club = 0, assoc = 0;
  for (const r of rows) {
    const l = plan[r.tid];
    if (l === A) {
      a++;
      if (r.h.hg_club) club++;
      else if (r.h.hg_association) assoc++;
    } else if (l === B) b++;
    else out++;
  }
  const hgCounted = rules.hg_min ? hgCredit(club, assoc, rules) : 0;
  const missing = Math.max(0, rules.hg_min - hgCounted);
  return { a, b, out, club, assoc, hgCounted, missing, cap: rules.a_list_max - missing };
}

/**
 * The best `depth` players at every position we field, by this tactic's rating.
 *
 * Keyed on POSITION, not on a player's best role, because "top 2 at DL" is the question a squad
 * list has to answer and a player who is third-choice everywhere is in nobody's top 2. A player
 * covering three positions is picked up by each of them; `rank` keeps the best placing he earned,
 * so when slots are tight every position's first choice is registered before anybody's second.
 */
function spineOf(rows, depth, method) {
  const byPos = new Map();
  for (const r of rows) {
    for (const q of D.playerRoles(r.player, method)) {
      if (!byPos.has(q.pos)) byPos.set(q.pos, []);
      byPos.get(q.pos).push({ tid: r.tid, eff: q.eff });
    }
  }
  const rank = new Map();
  for (const arr of byPos.values()) {
    arr.sort((x, y) => y.eff - x.eff);
    arr.slice(0, depth).forEach((x, i) => {
      rank.set(x.tid, Math.min(rank.get(x.tid) ?? Infinity, i));
    });
  }
  return rank;
}

/**
 * A legal-as-possible starting plan.
 *
 * THE A-LIST CANNOT HOLD EVERYONE, and that is the whole difficulty. This squad is 40: 19 of them
 * are too old for the B-list, 5 are on loan to us, and the spine is another 19 at depth 2. Any two
 * of those three groups already overflow 25, so the suggestion is a priority order, not a filter:
 *
 *   1. **Loan-ins.** We spent a loan slot to have him available; an unregistered loanee is a
 *      wasted one.
 *   2. **The spine** — the best `depth` at each position, first choices before second choices.
 *      These are the players the season actually runs on.
 *   3. **The home-grown top-up**, strongest first: the spine is already registered, so whoever is
 *      left is outside it, and the slot should hold the best of them.
 *   4. **Everyone else too old for the B-list.** Not because they are better than the youth left
 *      over, but because registration is the only thing standing between them and being unable to
 *      play at all — a B-list-eligible player left off the A-list still plays.
 *
 * Whoever misses out is reported as unregistered rather than quietly dropped, because that is a
 * real squad decision (those are the players to sell or loan out) and not a rounding error.
 */
export function suggest(rows, rules, depth = DEFAULT_DEPTH, method = D.S.method) {
  const plan = {};
  for (const r of rows) plan[r.tid] = r.h.b_list ? B : OUT;

  const byTid = new Map(rows.map((r) => [r.tid, r]));
  const rank = spineOf(rows, depth, method);
  const cap = () => rules.a_list_max - tally(rows, plan, rules).missing;
  let a = 0;
  const put = (tid) => {
    if (plan[tid] === A) return true;
    if (a >= cap()) return false;
    plan[tid] = A;
    a++;
    return true;
  };

  // 1 + 2: the loanees and the spine, in that order
  const queue = [
    ...rows.filter((r) => r.loanedIn).sort((x, y) => y.eff - x.eff),
    ...rows.filter((r) => rank.has(r.tid))
      .sort((x, y) => rank.get(x.tid) - rank.get(y.tid) || y.eff - x.eff),
  ];
  for (const r of queue) put(r.tid);

  // 3: the home-grown minimums, club-trained first — it is the half that binds, and an
  // association-trained player cannot substitute for it. STRONGEST first: step 2 has already
  // registered the spine, so everyone still available here is outside it, and taking the best
  // of them puts a useful player in the slot rather than a 16-year-old with four months on the
  // clock who will not feature. (An earlier version promoted the weakest, on the grounds that
  // a B-lister plays either way — true, but it made the quota a place to hide the squad's
  // least useful player instead of its best reserve.)
  if (rules.hg_min) {
    const spare = rows.filter((r) => plan[r.tid] !== A).sort((x, y) => y.eff - x.eff);
    for (const wantClub of [true, false]) {
      for (const r of spare) {
        const t = tally(rows, plan, rules);
        if (t.hgCounted >= rules.hg_min && t.club >= rules.hg_club_min) break;
        if (wantClub ? !r.h.hg_club : !r.h.hg_association) continue;
        if (wantClub && t.club >= rules.hg_club_min) continue;
        // The cap grows as the shortfall shrinks, so this can succeed where `put` would have
        // refused a moment ago — hence the recomputed cap() rather than a fixed one.
        put(r.tid);
      }
    }
  }

  // 4: the rest of the players who have no B-list to fall back on
  for (const r of rows.filter((r) => !r.h.b_list && plan[r.tid] !== A)
                      .sort((x, y) => y.eff - x.eff)) put(r.tid);

  // Anyone still unplaced sits on the B-list if he can, and is unregistered if he cannot.
  for (const r of rows) if (plan[r.tid] !== A) plan[r.tid] = r.h.b_list ? B : OUT;
  return plan;
}

// --------------------------------------------------------------------------- plumbing
const load = (key) => {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
};
const save = (key, plan) => {
  try { localStorage.setItem(key, JSON.stringify(plan)); } catch { /* private mode */ }
};
const kpi = (label, value, cls) => el(`div.kpi${cls ? "." + cls : ""}`, {}, [
  el("b", { text: String(value) }), el("span", { text: label }),
]);
