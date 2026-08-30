/**
 * The player profile sheet — shared by every section, because "tell me about this player" is
 * the same question wherever it's asked. Tapping a row anywhere opens this.
 *
 * Attribute bars are coloured by the CURRENT tactic's weight for the role being shown, so the
 * profile answers "is he good at the things this tactic asks of him" rather than "is he good"
 * in the abstract. Switch tactic in the header and the emphasis moves.
 */
import * as D from "./data.js";
import { el, clear, bar, num, money, monthYear, sparkline, radar, sheet, pill, toast, attrValue,
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

/** "AJ" from "Adam Jakobsen"; one word gets its first two letters. */
function initialsOf(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Initials for a compared set, disambiguated (AJ, AJ2, ...) if two players collide. */
function initialsFor(names) {
  const base = names.map(initialsOf);
  const counts = {};
  for (const b of base) counts[b] = (counts[b] || 0) + 1;
  const seen = {};
  return base.map((b) => {
    if (counts[b] <= 1) return b;
    seen[b] = (seen[b] || 0) + 1;
    return `${b}${seen[b]}`;
  });
}

/**
 * Side-by-side comparison of 2-4 players: a role picker, a radar per attribute group, and a
 * sortable attribute-by-attribute table.
 *
 * Comparing a DR against a DMR (or a clutch of CM/AM/DM types) only means something if
 * everyone's rated under the SAME named role — a right-back's own best position isn't the
 * question, "how do they stack up at DMR" is. So the role is a single picker at the top,
 * defaulting to whichever role the most of the selected players actually list, and every
 * role-dependent bit (rating, the radar's bold axes, the W column) re-renders on change. The
 * raw attribute VALUES don't depend on role at all, so the table body is built once and only
 * re-sorted/re-weighted, not rebuilt from scratch.
 */
export function openCompare(tids, role = null) {
  const ps = tids.map((t) => D.S.players.get(t)).filter(Boolean);
  if (ps.length < 2) return;
  const inits = initialsFor(ps.map((p) => p.name));

  const roleInfo = new Map();
  for (const p of ps) {
    for (const q of D.playerRoles(p)) {
      if (!roleInfo.has(q.role)) roleInfo.set(q.role, { role: q.role, n: 0 });
      roleInfo.get(q.role).n++;
    }
  }
  const roleOptions = [...roleInfo.values()].sort((a, b) => b.n - a.n || a.role.localeCompare(b.role));
  let r = (role && roleInfo.has(role)) ? role : (roleOptions[0]?.role || D.bestRole(ps[0])?.role);

  // static: which attributes appear as rows, and each player's raw value — none of this moves
  // when the role picker changes, only the W column and best-value ring do
  const attrRows = [];
  for (const [group, names] of Object.entries(D.ATTR_GROUPS)) {
    for (const a of names) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const vals = ps.map((p) => p.attrs[i]);
      if (vals.every((v) => v == null)) continue;
      attrRows.push({ group, attr: a, vals });
    }
  }
  let sortKey = null; // null = grouped default order; else "attr" | "w" | a player's tid
  let sortDir = "desc";

  // a player who doesn't actually list this role (comparing a natural DR against a natural
  // DMR, say) still gets an unfamiliarity-blind rating rather than silently falling back to
  // his own best role, which would make the column look like it answers a question it doesn't
  function ratingFor(p) {
    const rr = D.playerRoles(p).find((x) => x.role === r);
    if (rr) return { eff: rr.eff, label: `${rr.pos} fam ${rr.fam}` };
    return { eff: D.rating(p.attrs, r), label: "not a listed position" };
  }

  function sortedRows() {
    if (!sortKey) return null;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...attrRows].sort((a, b) => {
      let x, y;
      if (sortKey === "attr") { x = a.attr; y = b.attr; }
      else if (sortKey === "w") { x = D.weightOf(a.attr, r); y = D.weightOf(b.attr, r); }
      else {
        const idx = ps.findIndex((p) => p.tid === sortKey);
        x = a.vals[idx]; y = b.vals[idx];
      }
      const xn = x == null, yn = y == null;
      if (xn && yn) return 0;
      if (xn) return 1;
      if (yn) return -1;
      return typeof x === "string" ? dir * x.localeCompare(y) : dir * (x - y);
    });
  }

  function sortTh(key, label, { num: isNum = false, title = label } = {}) {
    const on = sortKey === key;
    return el(`th${isNum ? ".num" : ""}${on ? ".sorted" : ""}`, {
      title,
      onclick: () => {
        if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
        else { sortKey = key; sortDir = key === "attr" ? "asc" : "desc"; }
        renderAll();
      },
    }, [label, on ? el("span.arrow", { text: sortDir === "asc" ? "▲" : "▼" }) : null]);
  }

  function attrTr(row) {
    const best = Math.max(...row.vals.filter((v) => v != null));
    const w = D.weightOf(row.attr, r);
    return el("tr", {}, [
      el("td", { text: row.attr, title: row.group }),
      el("td.num", {}, [w > 1 ? pill(String(w), w >= 4 ? "bad" : w >= 3 ? "warn" : "good") : el("span.dim", { text: DASH })]),
      ...row.vals.map((v) => el("td.num", {}, [attrValue(v, { best: v != null && v === best && row.vals.length > 1 })])),
    ]);
  }

  const roleSel = el("select.btn", {
    onchange: (e) => { r = e.target.value; renderAll(); },
  }, roleOptions.map((o) => el("option", {
    value: o.role, text: `${o.role}${o.n < ps.length ? ` (${o.n}/${ps.length})` : ""}`,
  })));
  roleSel.value = r;

  // initials read faster side by side than full names once you're scanning 3-4 columns, but
  // the mapping has to stay one glance away rather than living only in a hover title
  const legend = el("div.cmplegend", {}, ps.map((p, i) => el("div.cmpkey", {}, [
    el("i", {}), el("span", { text: `${inits[i]} ${p.name}` }),
  ])));

  const content = el("div");

  function renderAll() {
    clear(content);

    const kpis = el("div.kpis", {}, ps.map((p, i) => {
      const rf = ratingFor(p);
      return el("div.kpi", { title: p.name }, [
        el("b", { text: num(rf.eff) }),
        el("span", { text: `${inits[i]} · ${rf.label}` }),
      ]);
    }));

    // one small radar per attribute group (Technical/Mental/Physical, +Goalkeeping if every
    // player shown is a keeper) instead of one crowded wheel — it's both what fixes the mobile
    // cutoff (fewer axes per chart) and what makes the section a spike belongs to obvious
    const groups = ["Technical", "Mental", "Physical"];
    if (ps.every((p) => p.positions.some((q) => q.pos === "GK"))) groups.push("Goalkeeping");
    const radars = el("div.radargrid", {}, groups.map((g) => {
      const axes = D.ATTR_GROUPS[g].filter((a) => D.S.attrs.indexOf(a) >= 0);
      const keyed = axes.map((a) => D.weightOf(a, r) >= 2);
      return el("div.radarcard", {}, [
        el("h5", { text: g }),
        radar(axes, ps.map((p) => ({
          values: axes.map((a) => (p.attrs[D.S.attrs.indexOf(a)] ?? 0) / 20),
        })), { size: 200, keyed }),
      ]);
    }));

    const rows = [];
    const sorted = sortedRows();
    if (sorted) {
      for (const row of sorted) rows.push(attrTr(row));
    } else {
      for (const group of Object.keys(D.ATTR_GROUPS)) {
        const inGroup = attrRows.filter((row) => row.group === group);
        if (!inGroup.length) continue;
        rows.push(el("tr", {}, [el("td", { colspan: ps.length + 2 }, [el("span.dim", { text: group })])]));
        for (const row of inGroup) rows.push(attrTr(row));
      }
    }
    const table = el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, [
        sortTh("attr", "Attribute"),
        sortTh("w", "W", { num: true, title: "This tactic's weight for the role — click to sort" }),
        ...ps.map((p, i) => sortTh(p.tid, inits[i], { num: true, title: `${p.name} — click to sort` })),
      ])]),
      el("tbody", {}, rows),
    ])]);

    content.append(
      kpis,
      el("h4", { text: `Attribute profile · ${r}` }), radars,
      el("p.note", { text: `Bold axis labels are attributes this tactic weights at 2 or more for ${r}.` }),
      el("h4", { text: "Attribute by attribute" }), table,
      el("p.note", { text: "W = this tactic's weight for the role (blank = 1, the default). Ringed = highest of the players shown. Click a column header to sort." }),
    );
  }

  renderAll();
  sheet("Compare", [
    el("div.prow", {}, [el("span.dim", { text: "Compare as:" }), roleSel]),
    legend,
    content,
  ], { wide: true });
}
