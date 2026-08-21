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
  await D.loadMatches();                    // for the head-to-head record against a scouted club
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

    // Record against them. Friendlies excluded: they say nothing about a bogey side.
    const h2h = ourMatchesVs(tid);
    if (h2h.length) {
      const w = h2h.filter((m) => m.result === "W").length;
      const d = h2h.filter((m) => m.result === "D").length;
      const l = h2h.filter((m) => m.result === "L").length;
      const gf = h2h.reduce((a, m) => a + (m.gf || 0), 0);
      const ga = h2h.reduce((a, m) => a + (m.ga || 0), 0);
      scout.append(el("h3", { text: `Our record against them · ${h2h.length} played` }));
      scout.append(el("div.kpis", {}, [
        kpi("W-D-L", `${w}-${d}-${l}`), kpi("Goals", `${gf}:${ga}`),
        kpi("Pts/game", num(h2h.reduce((a, m) => a + (m.pts || 0), 0) / h2h.length, 2)),
      ]));
      scout.append(el("div.scroll.fit", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Date", "Competition", "H/A", "Score", "", "Formation"]
          .map((h, i) => el(`th${i === 3 ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, [...h2h].sort((a, b) => String(b.date).localeCompare(String(a.date)))
          .map((m) => el("tr", {}, [
            el("td", { text: String(m.date).slice(0, 10) }),
            el("td", { text: m.competition || DASH }), el("td", { text: m.venue }),
            el("td.num", { text: `${m.gf}–${m.ga}` }),
            el("td", {}, [pill(m.result, { W: "good", D: "flat", L: "bad" }[m.result] || "flat")]),
            el("td", { text: m.formation || DASH }),
          ]))),
      ])]));
    } else {
      scout.append(el("p.note", { text: "No competitive meetings on record — either we've never played them, or the games predate what the save still holds." }));
    }

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
  const ourRank = lgs.findIndex((l) => l.cid === ourCid) + 1;
  out.append(el("h3", { text: `League reputation ladder · ${lgs.length} leagues` }));
  // No cutoff. The previous top-60 hid most of the pyramid, including divisions we could
  // plausibly loan into — and a silently truncated list reads as a complete one.
  const nationFilter = el("select.btn");
  const nations = [...new Set(lgs.map((l) => l.nation).filter(Boolean))].sort();
  nationFilter.append(el("option", { value: "", text: "All nations" }),
    ...nations.map((n) => el("option", { value: n, text: n })));
  const ladderBox = el("div");
  const drawLadder = () => {
    const want = nationFilter.value;
    const rows = lgs.filter((l) => !want || l.nation === want);
    ladderBox.replaceChildren(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["#", "League", "Nation", "Reputation", "Skill idx", "Clubs", "Rated"]
        .map((h, i) => el(`th${i === 0 || i >= 3 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, rows.map((l) => el("tr", {}, [
        el("td.num", { text: lgs.indexOf(l) + 1 }),
        el("td.name", {}, [l.name, l.cid === ourCid ? pill(" us", "good") : null]),
        el("td", { text: l.nation || DASH }),
        el("td.num", { text: l.reputation }),
        el("td.num", {}, [bar(l.skillIdx)]),
        el("td.num", { text: l.clubs || DASH }),
        el("td.num", { text: l.rated ?? DASH }),
      ]))),
    ])]), el("p.note", {
      html: "<b>Reputation</b> is a value parsed straight from each competition record. "
        + "<b>Skill idx</b> is the average player ability in that league normalised 0-100 across "
        + "ranked leagues — a CA-derived index in the same sanctioned form as a Level percentile, "
        + "never the number itself. Only leagues with 20+ rated players get one. "
        + "<b>Clubs</b> counts actual club records, not the competition record's member count — "
        + "that field is unreliable (it reads 5 for a 12-team division), so it isn't shown. "
        + (ourLg ? `<br>${ourLg.name}: reputation ${ourLg.reputation}, `
          + `skill idx ${ourLg.skillIdx ?? "—"}, ranked ${ourRank} of ${lgs.length} loaded leagues.` : ""),
    }));
  };
  nationFilter.addEventListener("change", drawLadder);
  drawLadder();
  out.append(el("div.tbar", {}, [nationFilter]), ladderBox);
  return out;
}

/** Our competitive matches against one club. */
function ourMatchesVs(tid) {
  const M = D.S.matches;
  if (!M?.matches?.length) return [];
  const f = M.match_fields;
  return M.matches.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])))
    .filter((m) => m.opp_tid === tid && !/friend/i.test(m.competition || ""));
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
