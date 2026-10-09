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
import { loanOutlook } from "./loans.js";
import { devChart } from "./devchart.js";

// A per-viewer preference, not per-player state — once you've picked "+ growth + trend" you
// want it on every profile you open from then on, not reset back to the plain grid each time.
const DETAIL_KEY = "fm:profile:detail";
const loadDetail = () => {
  try {
    const v = localStorage.getItem(DETAIL_KEY);
    return v === "more" || v === "most" || v === "proj" ? v : "simple";
  } catch { return "simple"; }
};
const saveDetail = (v) => { try { localStorage.setItem(DETAIL_KEY, v); } catch { /* private browsing */ } };

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

/**
 * @param {object} [opts]
 * @param {object} [opts.compare] another player, to show a per-attribute delta against him.
 * @param {Array} [opts.attrTraj] this player's snapshot history (D.attrTrajectory(tid)), oldest
 *   first — enables growth annotation, gated by `detail`.
 * @param {"simple"|"proj"|"more"|"most"} [opts.detail] "simple" (default) is the plain
 *   current-value grid; "proj" adds the projection from `forecast`; "more" adds the net change
 *   since the first snapshot next to the value; "most" also prepends a small trend sparkline.
 *   Kept off by default — every annotation is opt-in, not everyone wants a busier grid.
 * @param {object} [opts.forecast] D.forecastAttrs(p, toAge) result, shown only at detail
 *   "proj" — answers "will his X come": a 'fixed' attribute (Agility, Technique) is marked as
 *   never moving; a 'forecastable' one whose projection differs from today's value shows
 *   `-> projected`. Silent for 'unmodelled' attributes and for a value already at the target.
 * @param {boolean} [opts.legend] append the colour-scale legend under the grid (default true).
 */
export function attributeBlock(p, role, { compare = null, attrTraj = null, detail = "simple", forecast = null, legend = true } = {}) {
  const isGk = p.positions.some((q) => q.pos === "GK");

  function row(a, i, w, title) {
    const v = p.attrs[i];
    const other = compare ? compare.attrs[i] : null;
    let spark = null, delta = null;
    if (attrTraj && (detail === "more" || detail === "most")) {
      const known = attrTraj.map((t) => t.attrs[i]).filter((x) => x != null);
      if (known.length >= 2) {
        delta = v - known[0];
        if (detail === "most") spark = attrTraj.map((t) => t.attrs[i]);
      }
    }
    const tier = w >= 4 ? "key" : w === 3 ? "imp" : w === 2 ? "useful" : null;
    const bucket = detail === "proj" ? forecast?.buckets?.[i] : null;
    const fcVal = bucket === "forecastable" ? forecast.attrs[i] : null;
    return el(`div.arow${tier ? `.keyed.${tier}` : ""}`, { title }, [
      el("span.an", {}, [a, tier ? el("span.wdot", { text: tier }) : null]),
      el("span", {}, [
        spark ? sparkline(spark, { w: 40, h: 14, dot: false }) : null,
        other != null && other !== v
          ? el("span.dim", { text: `${v > other ? "+" : ""}${v - other}  ` }) : null,
        attrValue(v),
        delta != null
          ? el("span.dim", { text: ` ${delta === 0 ? "±0" : `${delta > 0 ? "+" : ""}${delta}`}` }) : null,
        bucket === "fixed" ? el("span.dim", { text: " (fixed)" }) : null,
        fcVal != null && fcVal !== v ? el("span.dim", { text: ` → ${fcVal}` }) : null,
      ]),
    ]);
  }

  const groups = ["Technical", "Mental", "Physical"];
  const cols = groups.map((g) => {
    const col = el("div.attrcol", {}, [el("h4", { text: g })]);
    for (const a of GAME_ORDER[g]) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      const w = role ? D.weightOf(a, role) : 1;
      col.append(row(a, i, w, w > 1 ? `${a} — weight ${w} for ${role}` : a));
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
      gk.append(row(a, i, w, a));
    }
    wrap.append(el("div.attrcols", {}, [gk]));
  }
  if (legend) wrap.append(el("div.avlegend", {},
    [el("span.dim", { text: "Scale:" }),
      ...ATTR_BANDS.map(([b, label]) => el(`span.av.v${b}`, { text: label.split(" ")[0], title: label })),
      el("span.dim", { text: role ? `· tinted rows are weighted for ${role}` : "" })]));
  return wrap;
}

const FOOT_LABEL = (l, r) => {
  if (l == null && r == null) return null;
  if (l != null && r != null) return el("span", {}, ["Left ", attrValue(l), "  Right ", attrValue(r)]);
  return el("span", {}, [l != null ? "Left " : "Right ", attrValue(l ?? r)]);
};

// Per-viewer preferences, not per-player state: you tend to do one job across many players
// (checking loans, then reading personalities), so the sheet reopens where you left it.
const TAB_KEY = "fm:profile:tab";
const EXTRA_KEY = "fm:profile:extra";
const pref = (k, fallback) => { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } };
const setPref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private browsing */ } };

/** An explanation folded behind a small ⓘ — worth reading once, clutter every time after. */
const info = (children) => el("details.info", {}, [el("summary", { text: "ⓘ How to read this" }),
  el("div.note", {}, children)]);

/** Personality + the nine hidden attributes, as extra columns in the attribute grid. They come
 *  from the profile-only tail (`D.loadProfile`), so null until that has loaded. */
function extraAttrColumns(prof) {
  if (!prof) return null;
  const col = (title, pairs) => {
    const known = pairs.filter(([, v]) => v != null);
    return known.length ? el("div.attrcol", {}, [el("h4", { text: title }),
      ...known.map(([label, v]) => el("div.arow", {}, [el("span.an", { text: label }), el("span", {}, [attrValue(v)])]))]) : null;
  };
  const cols = [
    col("Personality", [
      ["Adaptability", prof.personality.adaptability], ["Ambition", prof.personality.ambition],
      ["Determination", prof.personality.determination], ["Loyalty", prof.personality.loyalty],
      ["Pressure", prof.personality.pressure], ["Professionalism", prof.personality.professionalism],
      ["Sportsmanship", prof.personality.sportsmanship], ["Temperament", prof.personality.temperament],
    ]),
    col("Hidden", [
      ["Jumping", prof.hidden.jumping], ["Consistency", prof.hidden.consistency],
      ["Big match", prof.hidden.bigMatch], ["Injury proneness", prof.hidden.injuryProne],
      ["Versatility", prof.hidden.versatility], ["Set pieces", prof.hidden.setPieces],
      ["Penalties", prof.hidden.penalty], ["Work rate", prof.hidden.workRate],
      ["Flair", prof.hidden.flair],
    ]),
  ].filter(Boolean);
  return cols.length ? el("div.attrcols.extra", {}, cols) : null;
}

/** Bio + reputation, from the same profile-only tail. */
function bioBlock(p) {
  const prof = p.profile;
  if (!prof) return null;
  const tiles = (rows) => el("div.kpis.sm", {}, rows.map(([label, value]) =>
    el("div.kpi", {}, [el("b", {}, [value instanceof Node ? value : String(value)]), el("span", { text: label })])));
  return el("div", {}, [
    tiles([
      ["Nationality", prof.nationality || DASH],
      ["Foot", FOOT_LABEL(prof.footLeft, prof.footRight) || DASH],
      ["Height", p.height ? `${p.height} cm` : DASH],
      ["Weight", p.weight ? `${p.weight} kg` : DASH],
      ["Squad number", p.shirt != null
        // 0 reads as "no preference set" rather than a real shirt number — only show it when
        // it names an actual, different number.
        ? `#${p.shirt}${prof.preferredShirt && prof.preferredShirt !== p.shirt ? ` (prefers #${prof.preferredShirt})` : ""}`
        : DASH],
      ["Joined", prof.joinedDate ? monthYear(prof.joinedDate) : DASH],
      ["Caps / goals", `${prof.caps ?? DASH} / ${prof.goals ?? DASH}`],
      ["U21 caps / goals", `${prof.u21Caps ?? DASH} / ${prof.u21Goals ?? DASH}`],
    ]),
    el("h4", { text: "Reputation" }),
    tiles([["Home", prof.reputation.home], ["Current", prof.reputation.current], ["World", prof.reputation.world]]
      .map(([label, v]) => [label, v == null ? DASH : v.toLocaleString()])),
  ]);
}

/** Match record in three small groups rather than one sixteen-column row. */
const STAT_GROUPS = [
  ["Output", ["Apps", "Starts", "Min", "Rating", "Goals", "Assists", "G/90", "A/90"]],
  ["On the ball", ["KeyP/90", "Pass %", "Shot acc %", "Conversion %"]],
  ["Defending", ["Tackle %", "Header %", "Int/90", "Mistakes/gm"]],
];
function statBlock(agg) {
  if (!agg) return el("p.note", { text: "No parsed match data for this player — only the managed club's matches are richly parsed." });
  return el("div", {}, STAT_GROUPS.map(([title, names]) => el("div.statgrp", {}, [
    el("span.dim", { text: title }),
    el("div.kpis.sm", {}, names.map((s) => {
      const v = D.statValue(s, agg);
      return el("div.kpi", {}, [el("b", { text: v == null ? DASH : num(v, /%$|Apps|Starts|Min$|Goals|Assists/.test(s) ? 0 : 2) }),
        el("span", { text: s })]);
    })),
  ])));
}

/**
 * His record for us split two ways — by competition, and against the opponents he has met
 * most — so "how does he do in Europe" or "against Brøndby" is answered from his own sheet.
 * The Matches page's Players tab answers the same question for the whole squad at once.
 */
function splitBlock(tid) {
  const rows = D.matchRows().filter((r) => r.tid === tid);
  if (!rows.length) return el("span");
  const M = D.S.matches;
  const fi = Object.fromEntries(M.match_fields.map((n, i) => [n, i]));
  const oppNames = new Map(M.matches.map((m) => [m[fi.opp_tid], m[fi.opponent]]));
  const table = (keyFn, label, { min = 1, limit = 99, name = (k) => k } = {}) => {
    const g = new Map();
    for (const r of rows) {
      const k = keyFn(r);
      if (!g.has(k)) g.set(k, []);
      g.get(k).push(r);
    }
    const aggs = [...g].map(([k, rs]) => [k, D.aggregate(rs).get(tid)])
      .filter(([, a]) => a.apps >= min).sort((a, b) => b[1].apps - a[1].apps).slice(0, limit);
    if (!aggs.length) return null;
    return el("div.scroll.fit", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, [label, "Apps", "Min", "Rating", "Adj", "G", "A"]
        .map((h, i) => el(`th${i ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, aggs.map(([k, a]) => el("tr", {}, [
        el("td.name", { text: name(k) }), el("td.num", { text: a.apps }), el("td.num", { text: num(a.min) }),
        el("td.num", { text: a.rating == null ? DASH : num(a.rating, 2) }),
        el("td.num", { text: a.ratingAdj == null ? DASH : num(a.ratingAdj, 2) }),
        el("td.num", { text: a.goals }), el("td.num", { text: a.assists }),
      ]))),
    ])]);
  };
  const byComp = table((r) => r.competition || "?", "Competition");
  const byOpp = table((r) => r.opponent_tid, "Opponent",
    { min: 2, limit: 12, name: (k) => oppNames.get(k) || `#${k}` });
  return el("div", {}, [
    byComp ? el("h4", { text: "By competition" }) : null, byComp,
    byOpp ? el("h4", { text: "Against the sides he has met most (2+ apps)" }) : null, byOpp,
  ]);
}

function careerTable(career) {
  return el("div.scroll.fit", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Season", "Club", "Apps", "Goals", "Assists", "Rating", "Move"]
      .map((h, i) => el(`th${i >= 2 && i <= 5 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, career.map((c) => el("tr", {}, [
      el("td", { text: c.end_year ?? DASH }), el("td", { text: c.club ?? DASH }),
      el("td.num", { text: c.apps ?? DASH }), el("td.num", { text: c.goals ?? DASH }),
      el("td.num", { text: c.assists ?? DASH }),
      el("td.num", { text: c.rating == null ? DASH : num(c.rating, 2) }),
      el("td", { text: c.fee ?? DASH }),
    ]))),
  ])]);
}

/**
 * The profile sheet: a fixed top — who he is, then his attributes, which is what the sheet is
 * opened for — and everything else in tabs below, one open at a time. The tab and the
 * personality/hidden toggle are remembered across players.
 */
let squadTried = false;
/**
 * Open whatever we know about a player — the one entry point for every clickable name.
 *
 * The full profile needs the player in `S.players`, which boot() fills only with our squad and
 * the division-ladder clubs. Anyone else who is still in the save (a player who left us for
 * another club) is fetched on demand from all.json. Someone the save no longer holds at all —
 * retired, or gone abroad out of the database — still has every match he played for us, so he
 * gets a "former player" sheet built from those rows: his seasons, his record, and his splits.
 */
export async function openPlayer(tid) {
  if (tid == null) return;
  if (D.S.players.has(tid)) return openProfile(tid);
  const p = await D.loadProfile(tid);
  if (p) return openProfile(tid);
  await D.loadMatches().catch(() => null);
  const rows = D.matchRows().filter((r) => r.tid === tid);
  const agg = D.S.matchAgg?.get(tid) || null;
  const seasons = [...new Set(rows.map((r) => r.season))].sort((a, b) => a - b);
  const lbl = (y) => `${y - 1}/${String(y).slice(2)}`;
  sheet(D.matchName(tid), [
    el("p.note", { text: seasons.length
      ? `Played for us ${seasons.length === 1 ? `in ${lbl(seasons[0])}` : `from ${lbl(seasons[0])} to ${lbl(seasons.at(-1))}`}. `
        + "There's no profile to show for him (he has left the save, or it couldn't be fetched), "
        + "so this is his record for us only — no attributes or ratings."
      : "Not in this export." }),
    el("h4", { text: "Match record for us (all seasons)" }),
    statBlock(agg),
    splitBlock(tid),
  ]);
}

export function openProfile(tid, { role = null } = {}) {
  const p = D.S.players.get(tid);
  if (!p) return;
  // The development chart, the attribute growth options and career history all read
  // squad.json. Pages other than Squad don't load it, so fetch it (once, ~20 KB) before the
  // first sheet rather than showing a profile with those parts silently missing.
  if (!D.S.squad && !squadTried) {
    squadTried = true;
    D.loadSquad().catch(() => null).then(() => openProfile(tid, { role }));
    return;
  }
  const roles = D.playerRoles(p);
  const shown = role ? roles.find((r) => r.role === role) || roles[0] : roles[0];
  const a = D.age(p.dob);
  const ours = D.isOurs(p);
  const loanedIn = D.S.ours.loaned_in?.includes(tid);
  const club = D.S.clubs.get(p.clubTid);
  const traj = shown ? D.trajectory(tid, shown.role) : [];
  const growth = shown ? D.growth(tid, shown.role) : null;
  const attrTraj = D.attrTrajectory(tid);
  const career = D.S.squad?.career_history?.[String(tid)] || [];
  // Attribute-level forecast at 24 (the attribute grid's "will his X come" answer) and, for the
  // growth sparkline, the SAME per-attribute lookup rated at each horizon still ahead of him —
  // the p25/p75 attribute band rated through the role gives an (approximate — it ignores
  // cross-attribute correlation) rating band rather than just a point projection.
  const forecast = D.S.forecast ? D.forecastAttrs(p, 24) : null;
  const roleForecast = (() => {
    if (!shown || !D.S.forecast || a == null) return null;
    const horizons = [21, 24].filter((h) => a < h);
    if (!horizons.length) return null;
    const points = [], band = [];
    for (const h of horizons) {
      const fc = D.forecastAttrs(p, h);
      const lo = fc.attrs.map((v, i) => (fc.band[i] ? fc.band[i][0] : v));
      const hi = fc.attrs.map((v, i) => (fc.band[i] ? fc.band[i][1] : v));
      points.push(D.rating(fc.attrs, shown.role) * D.famMult(shown.fam));
      band.push([D.rating(lo, shown.role) * D.famMult(shown.fam), D.rating(hi, shown.role) * D.famMult(shown.fam)]);
    }
    return { points, band, lastAge: horizons[horizons.length - 1] };
  })();

  const body = [];

  // ---- who he is: club, status, positions, then the money in one compact line
  const origin = D.S.ours.origin?.[String(tid)];
  const status = ours ? D.S.ours.status?.[String(tid)] : null;
  const natural = [...p.positions].filter((q) => q.fam >= 15).sort((x, y) => y.fam - x.fam);
  body.push(el("div.phead", {}, [
    el("div.pline", {}, [
      el("b", { text: club?.name || DASH }),
      status ? pill(status, "flat") : null,
      loanedIn ? pill("On loan here", "warn") : null,
      ...natural.map((q) => el("span.pos", { text: `${q.pos} ${q.fam}`, title: `${q.pos} — familiarity ${q.fam}` })),
    ]),
    el("div.figs", {}, [
      shown ? fig(`${shown.role} rating`, num(shown.eff), `${D.S.method}, familiarity-adjusted`) : null,
      fig("Value", money(p.value)), fig("Wage/yr", money(p.wage)), fig("Contract", monthYear(p.expiry)),
      origin ? fig("Origin", origin, D.S.ours.capital_eligible?.includes(tid)
        ? "Eligible under the capital-region rule" : "Outside the capital region") : null,
    ]),
  ]));

  // ---- attributes: always shown, the reason the sheet is opened
  const attrBox = el("div");
  const extraBox = el("div");
  let curRole = shown?.role;
  let curDetail = loadDetail();
  let showExtra = pref(EXTRA_KEY, "0") === "1";
  let profileFailed = false;
  // The projection is only worth offering while he is still short of 24; growth needs at least
  // two snapshots to have anything to say.
  const canProject = !!forecast && a != null && a < 24;
  function rerenderAttrs() {
    clear(attrBox).append(attributeBlock(p, curRole, { attrTraj, detail: curDetail,
      forecast: canProject ? forecast : null, legend: false }));
  }
  function rerenderExtra() {
    clear(extraBox);
    if (!showExtra) return;
    extraBox.append(extraAttrColumns(p.profile) || el("p.note", { text: profileFailed ? "Unavailable right now." : "Loading…" }));
  }
  rerenderAttrs();
  rerenderExtra();

  const controls = [];
  // Only offer the highlight picker when he actually has more than one distinct role to
  // highlight for — a player who lists a single position has nothing to switch between.
  const seenRoles = new Set();
  const roleOptions = roles.filter((r) => (seenRoles.has(r.role) ? false : seenRoles.add(r.role)));
  if (roleOptions.length > 1) {
    const roleSel = el("select.btn.sm", {
      onchange: (e) => { curRole = e.target.value; rerenderAttrs(); },
    }, roleOptions.map((r) => el("option", { value: r.role, text: `${r.pos} · ${r.role}` })));
    roleSel.value = curRole;
    controls.push(roleSel);
  }
  if (traj.length > 1 || canProject) {
    // Detail defaults to whatever level you last picked; a saved level this player can't show
    // falls back to the plain grid.
    const detailSel = el("select.btn.sm", {
      onchange: (e) => { curDetail = e.target.value; saveDetail(curDetail); rerenderAttrs(); },
    }, [
      el("option", { value: "simple", text: "Current only" }),
      canProject ? el("option", { value: "proj", text: "+ projection at 24" }) : null,
      traj.length > 1 ? el("option", { value: "more", text: "+ growth since first snapshot" }) : null,
      traj.length > 1 ? el("option", { value: "most", text: "+ growth + trend" }) : null,
    ]);
    detailSel.value = curDetail;
    if (detailSel.value !== curDetail) { detailSel.value = "simple"; curDetail = "simple"; rerenderAttrs(); }
    controls.push(detailSel);
  }
  const extraBtn = el(`button.chip${showExtra ? ".on" : ""}`, {
    text: "+ personality & hidden",
    onclick: () => {
      showExtra = !showExtra;
      setPref(EXTRA_KEY, showExtra ? "1" : "0");
      extraBtn.classList.toggle("on", showExtra);
      rerenderExtra();
    },
  });
  controls.push(extraBtn);
  body.push(el("div.prow.attrbar", {}, [el("h4", { text: "Attributes" }), ...controls]));
  body.push(attrBox, extraBox);
  body.push(info([
    el("div.avlegend", {}, [el("span.dim", { text: "Scale:" }),
      ...ATTR_BANDS.map(([bnd, label]) => el(`span.av.v${bnd}`, { text: label.split(" ")[0], title: label }))]),
    el("p", { text: "Tinted rows are the attributes the selected tactic weights for the highlighted role — "
      + "green = key, amber = important, red = useful. Switch tactic in the header and the emphasis moves." }),
  ]));

  // Bio/personality/hidden tail — fetched lazily for players outside core.json, so the sheet
  // opens immediately and the pieces that need it fill in when it lands.
  const onProfile = [];
  D.loadProfile(tid).then((p2) => {
    if (p2 && p2 !== p && p2.profile) p.profile = p2.profile;
    profileFailed = !p.profile;
    rerenderExtra();
    for (const f of onProfile) f();
  });

  // ---- tabs
  const TABS = [
    ["fit", "Fit", () => fitTab()],
    ["stats", "Stats", () => statsTab()],
    ours && !loanedIn ? ["loan", "Loan", () => loanOutlook(p, shown?.pos)] : null,
    ["bio", "Bio", () => bioTab()],
  ].filter(Boolean);
  let curTab = pref(TAB_KEY, "fit");
  if (!TABS.some((t) => t[0] === curTab)) curTab = "fit";
  const tabBar = el("div.ptabs", { role: "tablist" });
  const tabBody = el("div.ptab");
  function showTab(key, remember) {
    curTab = key;
    if (remember) setPref(TAB_KEY, key);
    for (const b of tabBar.children) b.classList.toggle("on", b.dataset.tab === key);
    clear(tabBody).append(TABS.find((t) => t[0] === key)[2]());
  }
  for (const [key, label] of TABS) {
    tabBar.append(el("button", { text: label, role: "tab", dataset: { tab: key }, onclick: () => showTab(key, true) }));
  }
  body.push(tabBar, tabBody);
  showTab(curTab, false);

  function fitTab() {
    // Fit percentile against our own division, and against his own league — "is he good
    // enough here", under the selected tactic.
    const ourCid = D.ourLeagueCid();
    const divPlayers = D.leaguePlayers(ourCid);
    const hisCid = D.S.clubs.get(p.clubTid)?.leagueCid;
    const hisPlayers = hisCid != null && hisCid !== ourCid ? D.leaguePlayers(hisCid) : null;
    const ourName = D.S.leagues.get(ourCid)?.name || "our division";
    const hisName = hisCid != null ? D.S.leagues.get(hisCid)?.name : null;
    const oursList = D.ourPlayers();
    const heads = ["Pos", "Role", "Fam", "Rating", `Fit %ile · ${ourName}`];
    if (hisPlayers) heads.push(`Fit %ile · ${hisName}`);
    heads.push("Squad rank");
    const out = el("div", {}, [el("div.scroll.fit", {}, [el("table", {}, [
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
    ])])]);
    if (traj.length > 1) {
      out.append(el("h4", { text: `Development as ${shown.role} · ${traj.length} snapshots` }),
        devChart(p, traj, roleForecast) || sparkline(traj.map((t) => t.value), { w: 260, h: 44, forecast: roleForecast }),
        el("p.note", {
          text: (growth
            ? `${growth.delta >= 0 ? "+" : ""}${num(growth.delta)} since ${traj[0].phase}`
              + ` (${num(growth.from)} → ${num(growth.to)}), recomputed under the current tactic.`
            : "")
            + (roleForecast
              ? ` Dashed: projected to age ${roleForecast.lastAge}` +
                ` (${num(roleForecast.points[roleForecast.points.length - 1])}), from the` +
                " whole-save attribute lookup, not this player's own trend."
              : ""),
        }));
    }
    out.append(info([el("p", {
      html: "<b>Rating</b> is this tactic's weighted attribute sum, already discounted by "
        + "familiarity. <b>Fit %ile</b> is where that rating places him at that position "
        + "against everyone in the division — so it answers <i>is he good enough here</i>, and it "
        + "moves when you change tactic. (Level %ile, which ranks ability rather than tactical "
        + "fit, is on the Squad table and drives the Loan tab.) <b>Squad rank</b> is where he'd "
        + "stand among our own players at that position if he were part of the squad.",
    })]));
    return out;
  }

  function statsTab() {
    const box = el("div", {}, [el("h4", { text: "Match record for us (all seasons)" })]);
    const statsBox = el("div", {}, [el("p.note", { text: "Loading matches…" })]);
    box.append(statsBox);
    D.loadMatches().then(() => clear(statsBox).append(statBlock(D.S.matchAgg?.get(tid)), splitBlock(tid)))
      .catch(() => clear(statsBox).append(statBlock(null)));
    if (career.length) box.append(el("h4", { text: "Career history" }), careerTable(career));
    return box;
  }

  function bioTab() {
    const box = el("div");
    const fill = () => {
      clear(box).append(bioBlock(p) || el("p.note", { text: profileFailed ? "Bio unavailable right now." : "Loading bio…" }));
      // Add to shortlist straight from the profile — the moment you've decided he's
      // interesting is while you're looking at him.
      if (!ours) box.append(shortlistButton(p, shown));
    };
    fill();
    onProfile.push(() => { if (curTab === "bio" && box.isConnected) fill(); });
    return box;
  }

  sheet(`${p.name}${a ? ` · ${a}` : ""}`, body, { wide: true });
}

const fig = (label, value, title) => el("span.fig", { title }, [el("span.dim", { text: label }), el("b", { text: String(value) })]);

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
