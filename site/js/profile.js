/**
 * The player profile sheet — shared by every section, because "tell me about this player" is
 * the same question wherever it's asked. Tapping a row anywhere opens this.
 *
 * Attribute bars are coloured by the CURRENT tactic's weight for the role being shown, so the
 * profile answers "is he good at the things this tactic asks of him" rather than "is he good"
 * in the abstract. Switch tactic in the header and the emphasis moves.
 */
import * as D from "./data.js";
import { el, bar, num, money, monthYear, sparkline, radar, sheet, pill, toast, attrValue,
  ATTR_BANDS, DASH } from "./ui.js";

/**
 * Attribute order as the GAME lists it — alphabetical within each group, three columns side by
 * side, keepers separate. Matching it means a value you just read off the phone lands in the
 * same place here, which is the whole point of a reference screen.
 */
const GAME_ORDER = {
  Technical: ["Aerial", "Crossing", "Dribbling", "Passing", "Shooting", "Tackling", "Technique"],
  Mental: ["Aggression", "Creativity", "Decisions", "Leadership", "Movement", "Positioning", "Teamwork"],
  Physical: ["Pace", "Stamina", "Strength"],
  Goalkeeping: ["Agility", "Communication", "Handling", "Kicking", "Reflexes", "Throwing"],
};

export function attributeBlock(p, role, { compare = null } = {}) {
  const isGk = p.positions.some((q) => q.pos === "GK");
  const groups = ["Technical", "Mental", "Physical"];
  const cols = groups.map((g) => {
    const col = el("div.attrcol", {}, [el("h4", { text: g })]);
    for (const a of GAME_ORDER[g]) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const v = p.attrs[i];
      const w = role ? D.weightOf(a, role) : 1;
      const other = compare ? compare.attrs[i] : null;
      col.append(el(`div.arow${w >= 2 ? ".keyed" : ""}`, {
        title: w > 1 ? `${a} — weight ${w} for ${role}` : a,
      }, [
        el("span.an", {}, [a, w >= 3 ? el("span.wdot", { text: w >= 4 ? "key" : "imp" }) : null]),
        el("span", {}, [
          other != null && other !== v
            ? el("span.dim", { text: `${v > other ? "+" : ""}${v - other}  ` }) : null,
          attrValue(v),
        ]),
      ]));
    }
    return col;
  });
  const wrap = el("div", {}, [el("div.attrcols", {}, cols)]);
  // Keepers keep their own block, as the game does — six attributes that mean nothing for an
  // outfielder shouldn't pad out everyone else's profile.
  if (isGk) {
    const gk = el("div.attrcol", {}, [el("h4", { text: "Goalkeeping" })]);
    for (const a of GAME_ORDER.Goalkeeping) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const w = role ? D.weightOf(a, role) : 1;
      gk.append(el(`div.arow${w >= 2 ? ".keyed" : ""}`, {}, [
        el("span.an", { text: a }), attrValue(p.attrs[i]),
      ]));
    }
    wrap.append(el("div.attrcols", {}, [gk]));
  }
  wrap.append(el("div.avlegend", {},
    [el("span.dim", { text: "Scale:" }),
      ...ATTR_BANDS.map(([b, label]) => el(`span.av.v${b}`, { text: label.split(" ")[0], title: label })),
      el("span.dim", { text: role ? `· tinted rows are weighted for ${role}` : "" })]));
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
  const ours = D.isOurs(p);
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
  // Fit percentile against our own division, and against his own league. Level %ile is a
  // team-shaped measure — useful for "is this division better than ours", wrong for "is this
  // player better than that one", which is what a profile is for.
  const ourCid = D.ourLeagueCid();
  const divPlayers = D.leaguePlayers(ourCid);
  const hisCid = D.S.clubs.get(p.clubTid)?.leagueCid;
  const hisPlayers = hisCid != null && hisCid !== ourCid ? D.leaguePlayers(hisCid) : null;
  const ourName = D.S.leagues.get(ourCid)?.name || "our division";
  const hisName = hisCid != null ? D.S.leagues.get(hisCid)?.name : null;
  const oursList = D.ourPlayers();

  body.push(el("h4", { text: "Positions under this tactic" }));
  const heads = ["Pos", "Role", "Fam", "Rating", `Fit %ile · ${ourName}`];
  if (hisPlayers) heads.push(`Fit %ile · ${hisName}`);
  heads.push("Squad rank");
  body.push(el("div.scroll.fit", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, heads.map((h, i) => el(`th${i > 1 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, roles.map((r) => {
      const cells = [
        el("td", { text: r.pos }), el("td", { text: r.role }),
        el("td.num", {}, [bar(r.fam, { max: 20, lo: 60 })]),
        el("td.num", { text: num(r.eff) }),
        el("td.num", {}, [bar(D.pctile(D.poolAt(divPlayers, r.pos), r.eff))]),
      ];
      if (hisPlayers) cells.push(el("td.num", {}, [bar(D.pctile(D.poolAt(hisPlayers, r.pos), r.eff))]));
      const tpool = D.teamPool(oursList, r.pos);
      cells.push(el("td.num", { text: tpool.length ? `${D.rankIn(tpool, r.eff)}/${tpool.length}` : DASH }));
      return el("tr", {}, cells);
    })),
  ])]));
  body.push(el("p.note", {
    html: "<b>Rating</b> is this tactic's weighted attribute sum, already discounted by "
      + "familiarity. <b>Fit %ile</b> is where that rating places him at that position "
      + "against everyone in the division — so it answers <i>is he good enough here</i>, and it "
      + "moves when you change tactic. (Level %ile, which measures division quality rather than "
      + "a player, is on the Squad table and in Opposition.) <b>Squad rank</b> is where he'd "
      + "stand among our own players at that position if he were part of the squad.",
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

  // Add to shortlist straight from the profile — the moment you've decided he's interesting is
  // while you're looking at him, not after navigating to another section.
  if (!ours) body.push(shortlistButton(p, shown));

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

function shortlistButton(p, shown) {
  const note = el("input.search", { placeholder: "Note (optional) — why he's worth a look" });
  const btn = el("button.btn", { text: "Add to shortlist" });
  const wrap = el("div.card", {}, [el("h4", { text: "Shortlist" }), note,
    el("div.prow", {}, [btn])]);
  btn.addEventListener("click", async () => {
    const token = localStorage.getItem(D.SHORTLIST_TOKEN_KEY) || "";
    if (!token) return toast("Save your device token in Recruitment → Shortlist first", true);
    btn.disabled = true;
    btn.textContent = "Adding…";
    try {
      const r = await fetch("/api/shortlist", {
        method: "POST",
        headers: { "x-fm-token": token, "content-type": "application/json" },
        body: JSON.stringify({
          name: p.name, tid: p.tid,
          // carry his real positions and familiarity, so the entry is usable without
          // re-typing what we already know
          positions: Object.fromEntries(p.positions.map((q) => [q.pos, q.fam])),
          note: note.value.trim()
            || `${shown ? `${shown.role} ${Math.round(shown.eff)}` : ""}`.trim() || undefined,
          source: "profile",
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      btn.textContent = "On the shortlist ✓";
      btn.classList.add("on");
      toast(`${p.name} added to the shortlist`);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Add to shortlist";
      toast(`Couldn't add: ${e.message}`, true);
    }
  });
  return wrap;
}

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
