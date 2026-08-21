/**
 * Opposition — scout a club, rank the divisions, see the league ladder.
 *
 * Three questions about other people's teams that were on three pages. The scout comparison is
 * computed in the browser, so it follows the selected tactic: "their attack vs our defence"
 * changes meaning when the weight-set changes, and it should.
 *
 * Deliberately NOT a league table: `staging.standings` parses only partially for this career (a
 * 22-game division comes back with max played 12), so a table built from it would be quietly
 * wrong. Squad index answers the same question honestly.
 */
import * as D from "../data.js";
import { el, bar, num, pill, DASH } from "../ui.js";
import { openProfile } from "../profile.js";

const UNIT = {
  GK: ["GK"], Defence: ["DC", "DL", "DR", "DML", "DMR"],
  Midfield: ["DMC", "MC", "ML", "MR"], Attack: ["AMC", "AML", "AMR", "ST"],
};
const XI = { GK: 1, Defence: 4, Midfield: 3, Attack: 3 };
const unitOf = (pos) => Object.entries(UNIT).find(([, ps]) => ps.includes(pos))?.[0] || "Midfield";

export async function view() {
  const ourCid = D.ourLeagueCid();
  const ladder = D.S.index.ladder;
  const out = el("div");
  out.append(el("h2", { text: "Opposition" }));

  // index over every player we have loaded, so positions are comparable across clubs
  const loaded = [...D.S.players.values()];
  const idx = D.posIndexer(loaded);
  const bestFor = (p) => {
    const r = D.bestRole(p);
    return r ? { ...r, index: idx(r.pos, r.eff), unit: unitOf(r.pos) } : null;
  };
  const byClub = new Map();
  for (const p of loaded) {
    const b = bestFor(p);
    if (!b) continue;
    if (!byClub.has(p.clubTid)) byClub.set(p.clubTid, []);
    byClub.get(p.clubTid).push({ p, b });
  }
  const strength = (tid) => {
    const squad = byClub.get(tid) || [];
    const xi = [];
    for (const [u, k] of Object.entries(XI)) {
      xi.push(...squad.filter((x) => x.b.unit === u).sort((a, b) => b.b.index - a.b.index).slice(0, k));
    }
    if (!xi.length) return null;
    const mean = (arr) => (arr.length ? arr.reduce((a, x) => a + x.b.index, 0) / arr.length : null);
    return {
      index: mean(xi), n: xi.length,
      units: Object.fromEntries(Object.keys(XI).map((u) => [u, mean(xi.filter((x) => x.b.unit === u))])),
      xi,
    };
  };

  // ---------------------------------------------------------------- scout one club
  const clubsInLadder = [...D.S.clubs.values()]
    .filter((c) => ladder.some((l) => l.cid === c.leagueCid) && c.players > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  const sel = el("select.btn");
  sel.append(el("option", { value: "", text: "Pick a club to scout…" }));
  for (const l of ladder) {
    const grp = el("optgroup", { label: l.name });
    for (const c of clubsInLadder.filter((c) => c.leagueCid === l.cid)) {
      if (D.S.ours.clubs.includes(c.tid)) continue;
      grp.append(el("option", { value: String(c.tid), text: c.name }));
    }
    sel.append(grp);
  }
  const scout = el("div");
  sel.addEventListener("change", (e) => drawScout(Number(e.target.value)));
  out.append(el("div.tbar", {}, [sel]), scout);

  function drawScout(tid) {
    scout.replaceChildren();
    if (!tid) return;
    const us = strength(D.S.ours.managed_tid);
    const them = strength(tid);
    const club = D.S.clubs.get(tid);
    if (!them || !us) {
      scout.append(el("p.note", { text: "Not enough rated players on one side to compare." }));
      return;
    }
    scout.append(el("h3", { text: `${club.name} · ${D.S.leagues.get(club.leagueCid)?.name || ""}` }));
    scout.append(el("div.kpis", {}, [
      kpi("Us", num(us.index, 1)), kpi("Them", num(them.index, 1)),
      kpi("Edge", edgeText(us.index - them.index)),
      kpi("Their squad", club.players),
    ]));
    scout.append(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Unit", "Us", "Them", "Edge"].map((h, i) =>
        el(`th${i ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, Object.keys(XI).map((u) => {
        const a = us.units[u], b = them.units[u];
        const e2 = a == null || b == null ? null : a - b;
        return el("tr", {}, [
          el("td.name", { text: u }),
          el("td.num", { text: a == null ? DASH : num(a, 1) }),
          el("td.num", { text: b == null ? DASH : num(b, 1) }),
          el("td.num", {}, [e2 == null ? DASH : pill(edgeText(e2), e2 >= 0 ? "good" : "bad")]),
        ]);
      })),
    ])]));
    scout.append(el("p.note", {
      html: "Position index: 100 = an average player for that position across every player "
        + `loaded, 15 = one standard deviation. It follows the selected tactic (<b>${D.S.method}</b>), `
        + "so this reads as how well each side's players fit <i>the way we play</i>. "
        + "<b>Their formation and style are not in the save</b> — get those from the in-game scout.",
    }));

    scout.append(el("h3", { text: "Their danger men" }));
    scout.append(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Player", "Age", "Pos", "Fam", "Index", "Level %ile", "Standout"]
        .map((h, i) => el(`th${i >= 1 && i <= 5 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, (byClub.get(tid) || []).sort((a, b) => b.b.index - a.b.index).slice(0, 14)
        .map(({ p, b }) => el("tr.click", { onclick: () => openProfile(p.tid, { role: b.role }) }, [
          el("td.name", { text: p.name }),
          el("td.num", { text: D.age(p.dob) ?? DASH }),
          el("td", { text: b.pos }),
          el("td.num", {}, [bar(b.fam, { max: 20, lo: 60 })]),
          el("td.num", { text: num(b.index, 1) }),
          el("td.num", {}, [bar(b.lvlLeague)]),
          el("td", { text: standout(p, b.role) }),
        ]))),
    ])]));
    scout.append(el("p.note", {
      text: "Standout = his highest attributes among those this tactic weights for his role. "
        + "Opponent attribute values are model estimates (±1) except pace and physicals.",
    }));
  }

  // ---------------------------------------------------------------- divisions
  out.append(el("h3", { text: "Divisions by squad strength" }));
  for (const l of ladder) {
    const rows = [...D.S.clubs.values()].filter((c) => c.leagueCid === l.cid && c.players > 0)
      .map((c) => ({ c, s: strength(c.tid) })).filter((x) => x.s)
      .sort((a, b) => b.s.index - a.s.index);
    if (!rows.length) continue;
    out.append(el("h4", { text: l.name }));
    out.append(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["#", "Club", "", "Squad index", "GK", "Defence", "Midfield", "Attack", "Squad"]
        .map((h, i) => el(`th${i === 0 || i >= 3 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, rows.map((x, i) => el("tr", {}, [
        el("td.num", { text: i + 1 }),
        el("td.name", { text: x.c.name }),
        el("td", {}, [D.S.ours.clubs.includes(x.c.tid) ? pill("us", "good") : null]),
        el("td.num", { text: num(x.s.index, 1) }),
        ...Object.keys(XI).map((u) => el("td.num", { text: x.s.units[u] == null ? DASH : num(x.s.units[u], 1) })),
        el("td.num", { text: x.c.players }),
      ]))),
    ])]));
  }
  out.append(el("p.note", {
    html: "Squad quality, not results — it says who <i>should</i> finish where. Scored under the "
      + "selected tactic, so it measures fit to our style rather than raw quality; for level, use "
      + "the ability ranks on <a href=\"#/positions\">Positions</a>. There is no league table here "
      + "because <code>staging.standings</code> parses only partially for this career.",
  }));

  // ---------------------------------------------------------------- league ladder
  const lgs = [...D.S.leagues.values()].filter((l) => l.reputation != null)
    .sort((a, b) => b.reputation - a.reputation);
  const ourLg = D.S.leagues.get(ourCid);
  out.append(el("h3", { text: "League reputation ladder" }));
  out.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["#", "League", "Nation", "Reputation", "Clubs"]
      .map((h, i) => el(`th${i === 0 || i >= 3 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, lgs.slice(0, 60).map((l, i) => el("tr", {}, [
      el("td.num", { text: i + 1 }),
      el("td.name", {}, [l.name, l.cid === ourCid ? pill(" us", "good") : null]),
      el("td", { text: l.nation || DASH }),
      el("td.num", { text: l.reputation }),
      el("td.num", { text: l.clubs ?? DASH }),
    ]))),
  ])]));
  out.append(el("p.note", {
    text: `Reputation is a value parsed straight from each competition record. `
      + (ourLg ? `${ourLg.name} sits at ${ourLg.reputation}, ranked ${lgs.findIndex((l) => l.cid === ourCid) + 1} of ${lgs.length} loaded leagues.` : ""),
  }));
  return out;
}

function standout(p, role) {
  const keyed = D.S.attrs
    .map((a, i) => ({ a, v: p.attrs[i], w: D.weightOf(a, role) }))
    .filter((x) => x.v != null && x.w >= 2)
    .sort((x, y) => y.v * y.w - x.v * x.w).slice(0, 3);
  return keyed.length ? keyed.map((x) => `${x.a} ${x.v}`).join(", ") : DASH;
}
const edgeText = (v) => (v == null ? DASH : `${v >= 0 ? "+" : ""}${num(v, 1)}`);
const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
