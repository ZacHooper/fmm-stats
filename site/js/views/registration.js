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
  let plan = load(KEY);
  if (!plan) { plan = suggest(rows, rules); save(KEY, plan); }
  // A player who arrived since the plan was saved has no entry yet; default him rather than
  // dropping him, so a mid-window signing shows up as a decision to make instead of vanishing.
  for (const r of rows) if (!(r.tid in plan)) plan[r.tid] = r.h.b_list ? B : OUT;

  const summary = el("div");
  const warnings = el("div");

  const setList = (tid, list) => {
    plan[tid] = list;
    save(KEY, plan);
    drawSummary();
  };

  function drawSummary() {
    const t = tally(rows, plan, rules);
    summary.replaceChildren(
      el("div.kpis", {}, [
        kpi("A-list", `${t.a} / ${t.cap}`, t.a > t.cap ? "bad" : t.a === t.cap ? "warn" : "good"),
        kpi("Home grown (A)", `${t.hgCounted} / ${rules.hg_min}`,
            t.hgCounted >= rules.hg_min ? "good" : "bad"),
        kpi("Club-trained (A)", `${t.club} / ${rules.hg_club_min}`,
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

  const hgCell = (r) => {
    if (r.h.hg_club) {
      return pill(r.h.hg_basis === "clock" ? "Club (36mo)" : "Club (youth)", "good");
    }
    if (r.h.hg_association) return pill("Danish", "warn");
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
      label: "Home grown", group: "Registration",
      help: "Club = trained here (counts toward both minimums). Danish = trained at another club of the association (counts toward the 8 only).",
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

  const toolbar = [
    el("button.chip.ghost", {
      text: "Suggest a legal squad",
      title: "B-list everyone eligible, A-list the rest by rating, then promote home-grown "
        + "players until the minimums are met",
      onclick: () => {
        plan = suggest(rows, rules);
        save(KEY, plan);
        toast("Rebuilt from scratch");
        table.redraw();
        drawSummary();
      },
    }),
    el("button.chip.ghost", {
      text: "Clear",
      onclick: () => {
        for (const r of rows) plan[r.tid] = OUT;
        save(KEY, plan);
        table.redraw();
        drawSummary();
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
    onRow: (r) => openProfile(r.tid, { role: r.r?.role }),
    searchPlaceholder: "Search the squad…",
    empty: "No squad players in this export.",
  });

  out.append(
    el("div.card", {}, [
      el("b", { text: `${rules.league_name} · tier ${rules.tier}` }),
      el("p.note", {
        html: rules.hg_min
          ? `A-list ${rules.a_list_max} players, including <b>${rules.hg_min} home grown</b> of `
            + `whom at least <b>${rules.hg_club_min} trained here</b>. B-list unlimited, for `
            + `players under ${rules.b_list_under_age} on ${rules.u21_on}. `
            + `<a href="guides/registration.md">How home-grown status is derived</a>.`
          : `A-list ${rules.a_list_max} players, no home-grown requirement in tier ${rules.tier}. `
            + `B-list unlimited, for players under ${rules.b_list_under_age} on ${rules.u21_on}.`,
      }),
    ]),
    summary, warnings, table.node,
  );
  drawSummary();
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
 * A legal-as-possible starting plan.
 *
 * Everyone B-list eligible goes to the B-list first, because it costs nothing and preserves
 * A-list capacity (which is DBU's own advice). That can leave the A-list short of home-grown
 * players — most of ours are young — so the second pass PROMOTES home-grown B-listers back onto
 * the A-list until the minimums are met, cheapest by rating first: a promoted player can still
 * play either way, so the one to spend a slot on is the one you would otherwise leave out.
 */
export function suggest(rows, rules) {
  const plan = {};
  const byRating = [...rows].sort((x, y) => y.eff - x.eff);
  const seniors = byRating.filter((r) => !r.h.b_list);
  const youth = byRating.filter((r) => r.h.b_list);

  for (const r of youth) plan[r.tid] = B;
  let a = 0;
  for (const r of seniors) {
    plan[r.tid] = a < rules.a_list_max ? A : OUT;
    if (plan[r.tid] === A) a++;
  }

  if (rules.hg_min) {
    // Promote from the back of the B-list (weakest first): the strong ones are playing
    // regardless, so spending an A-list slot on one of them buys nothing.
    const promote = [...youth].reverse();
    for (const wantClub of [true, false]) {
      for (const r of promote) {
        const t = tally(rows, plan, rules);
        if (t.hgCounted >= rules.hg_min && t.club >= rules.hg_club_min) break;
        if (plan[r.tid] !== B) continue;
        if (wantClub ? !r.h.hg_club : !r.h.hg_association) continue;
        if (wantClub && t.club >= rules.hg_club_min) continue;
        if (a >= rules.a_list_max) break;
        plan[r.tid] = A;
        a++;
      }
    }
  }
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
