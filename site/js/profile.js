/**
 * The player profile sheet — shared by every section, because "tell me about this player" is
 * the same question wherever it's asked. Tapping a row anywhere opens this.
 *
 * Attribute bars are coloured by the CURRENT tactic's weight for the role being shown, so the
 * profile answers "is he good at the things this tactic asks of him" rather than "is he good"
 * in the abstract. Switch tactic in the header and the emphasis moves.
 */
import * as D from "./data.js";
import { el, bar, num, money, monthYear, sparkline, radar, sheet, pill, DASH } from "./ui.js";

const WCLS = { 4: "w4", 3: "w3", 2: "w2", 1: "" };

export function attributeBlock(p, role, { compare = null } = {}) {
  const wrap = el("div");
  for (const [group, names] of Object.entries(D.ATTR_GROUPS)) {
    const rows = [];
    for (const a of names) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const v = p.attrs[i];
      if (v == null) continue;
      const w = role ? D.weightOf(a, role) : 1;
      const other = compare ? compare.attrs[i] : null;
      rows.push(el(`div.arow.${WCLS[w] || ""}`, {}, [
        el("span.an", { text: a, title: w > 1 ? `weight ${w} for ${role}` : a }),
        el("span", {}, [el("span.abar", { style: `width:${(100 * v) / 20}%;display:block` })]),
        el("span.av", { text: other != null ? `${v} (${other > v ? "−" : "+"}${Math.abs(v - other)})` : String(v) }),
      ]));
    }
    if (rows.length) wrap.append(el("h4", { text: group }), el("div.attrs", {}, rows));
  }
  return wrap;
}

function statTable(agg) {
  if (!agg) return el("p.note", { text: "No parsed match data for this player — only the managed club's matches are richly parsed." });
  const show = ["Apps", "Starts", "Min", "Rating", "Goals", "Assists", "G/90", "A/90",
    "KeyP/90", "Pass %", "Tackle %", "Header %", "Shot acc %", "Conversion %", "Int/90", "Mistakes/gm"];
  return el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, show.map((s) => el("th.num", { text: s })))]),
    el("tbody", {}, [el("tr", {}, show.map((s) => {
      const v = D.statValue(s, agg);
      return el("td.num", { text: v == null ? DASH : num(v, /%$|Apps|Starts|Min$|Goals|Assists/.test(s) ? 0 : 2) });
    }))]),
  ])]);
}

export function openProfile(tid, { role = null } = {}) {
  const p = D.S.players.get(tid);
  if (!p) return;
  const roles = D.playerRoles(p);
  const shown = role ? roles.find((r) => r.role === role) || roles[0] : roles[0];
  const a = D.age(p.dob);
  const ours = D.S.ours.clubs.includes(p.clubTid);
  const club = D.S.clubs.get(p.clubTid);
  const agg = D.S.matchAgg?.get(tid);
  const traj = shown ? D.trajectory(tid, shown.role) : [];
  const growth = shown ? D.growth(tid, shown.role) : null;
  const career = D.S.squad?.career_history?.[String(tid)] || [];

  const body = [];
  body.push(el("div.kpis", {}, [
    kpi("Age", a ?? DASH), kpi("Club", club?.name || DASH),
    kpi(shown ? `${shown.role} rating` : "Rating", shown ? num(shown.eff) : DASH),
    kpi("Value", money(p.value)),
    kpi("Wage/yr", money(p.wage)),
    kpi("Contract", monthYear(p.expiry)),
  ]));

  // positions and what each is worth under this tactic
  body.push(el("h4", { text: "Positions under this tactic" }));
  body.push(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Pos", "Role", "Fam", "Rating", "Level %ile (league)", "Level %ile (global)"]
      .map((h, i) => el(`th${i > 1 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, roles.map((r) => el("tr", {}, [
      el("td", { text: r.pos }), el("td", { text: r.role }),
      el("td.num", {}, [bar(r.fam, { max: 20, lo: 60 })]),
      el("td.num", { text: num(r.eff) }),
      el("td.num", {}, [bar(r.lvlLeague)]),
      el("td.num", {}, [bar(r.lvlGlobal)]),
    ]))),
  ])]));
  body.push(el("p.note", {
    html: "<b>Rating</b> is this tactic's weighted attribute sum, already discounted by "
      + "familiarity. <b>Level %ile</b> is quality — where he ranks at that position among "
      + "players in his own league, and globally. Rating follows the tactic; Level doesn't.",
  }));

  if (traj.length > 1) {
    body.push(el("h4", { text: `Growth as ${shown.role} · ${traj.length} snapshots` }));
    body.push(el("div.card", {}, [
      sparkline(traj.map((t) => t.value), { w: 260, h: 44 }),
      el("p.note", {
        text: growth
          ? `${growth.delta >= 0 ? "+" : ""}${num(growth.delta)} since ${traj[0].phase}`
            + ` (${num(growth.from)} → ${num(growth.to)}), recomputed under the current tactic.`
          : "",
      }),
    ]));
  }

  body.push(el("h4", { text: "Attributes" }));
  body.push(el("p.note", {
    text: shown ? `Coloured by importance to ${shown.role} in this tactic — red = key, amber = important, green = useful.` : "",
  }));
  body.push(attributeBlock(p, shown?.role));

  body.push(el("h4", { text: "Match record for us (all seasons)" }));
  body.push(statTable(agg));

  if (career.length) {
    body.push(el("h4", { text: "Career history" }));
    body.push(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Season", "Club", "Apps", "Goals", "Assists", "Rating", "Move"]
        .map((h, i) => el(`th${i >= 2 && i <= 5 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, career.map((c) => el("tr", {}, [
        el("td", { text: c.end_year ?? DASH }), el("td", { text: c.club ?? DASH }),
        el("td.num", { text: c.apps ?? DASH }), el("td.num", { text: c.goals ?? DASH }),
        el("td.num", { text: c.assists ?? DASH }),
        el("td.num", { text: c.rating == null ? DASH : num(c.rating, 2) }),
        el("td", { text: c.fee ?? DASH }),
      ]))),
    ])]));
  }

  const origin = D.S.ours.origin?.[String(tid)];
  if (ours) {
    const cap = D.S.ours.capital_eligible?.includes(tid);
    body.push(el("p.note", {
      html: `Squad status <b>${D.S.ours.status?.[String(tid)] || "?"}</b>`
        + (origin ? ` · origin club <b>${origin}</b>` : "")
        + (origin ? ` · ${cap ? "<b>eligible</b> under the capital-region rule" : "outside the capital region"}` : ""),
    }));
  }
  sheet(`${p.name}${a ? ` · ${a}` : ""}`, body, { wide: true });
}

const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);

/** Side-by-side comparison of 2-4 players: radar over role weights + attribute diffs. */
export function openCompare(tids, role = null) {
  const ps = tids.map((t) => D.S.players.get(t)).filter(Boolean);
  if (ps.length < 2) return;
  const r = role || D.bestRole(ps[0])?.role;
  const body = [];
  body.push(el("div.kpis", {}, ps.map((p) => {
    const rr = D.playerRoles(p).find((x) => x.role === r) || D.playerRoles(p)[0];
    return el("div.kpi", {}, [
      el("b", { text: rr ? num(rr.eff) : DASH }),
      el("span", { text: `${p.name} · ${rr ? `${rr.pos} fam ${rr.fam}` : ""}` }),
    ]);
  })));

  // radar over the attributes this role actually cares about — comparing on 23 axes hides
  // the answer, comparing on the weighted ones shows it
  const keyAttrs = D.S.attrs.filter((a) => D.weightOf(a, r) >= 2);
  const axes = (keyAttrs.length >= 4 ? keyAttrs : D.S.attrs.slice(0, 8));
  body.push(el("h4", { text: `Weighted profile · ${r}` }));
  body.push(radar(axes, ps.map((p) => ({
    label: p.name,
    values: axes.map((a) => (p.attrs[D.S.attrs.indexOf(a)] ?? 0) / 20),
  })), { size: 260 }));
  body.push(el("p.note", {
    text: `Axes are the attributes this tactic weights at 2 or more for ${r}. `
      + ps.map((p, i) => `${["●", "▲", "■", "◆"][i]} ${p.name}`).join("   "),
  }));

  body.push(el("h4", { text: "Attribute by attribute" }));
  const rows = [];
  for (const [group, names] of Object.entries(D.ATTR_GROUPS)) {
    rows.push(el("tr", {}, [el("td", { colspan: ps.length + 2 }, [el("span.dim", { text: group })])]));
    for (const a of names) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const vals = ps.map((p) => p.attrs[i]);
      if (vals.every((v) => v == null)) continue;
      const best = Math.max(...vals.filter((v) => v != null));
      const w = D.weightOf(a, r);
      rows.push(el("tr", {}, [
        el("td", { text: a }),
        el("td.num", {}, [w > 1 ? pill(String(w), w >= 4 ? "bad" : w >= 3 ? "warn" : "good") : el("span.dim", { text: DASH })]),
        ...vals.map((v) => el("td.num", {}, [
          el(v === best && vals.length > 1 ? "b" : "span", { text: v == null ? DASH : String(v) }),
        ])),
      ]));
    }
  }
  body.push(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, [el("th", { text: "Attribute" }), el("th.num", { text: "W" }),
      ...ps.map((p) => el("th.num", { text: p.name }))])]),
    el("tbody", {}, rows),
  ])]));
  body.push(el("p.note", { text: "W = this tactic's weight for the role (blank = 1, the default). Bold = highest of the players shown." }));
  sheet(`Compare · ${r}`, body, { wide: true });
}
