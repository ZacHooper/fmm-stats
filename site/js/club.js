/**
 * The club sheet: how an opponent plays us. A fixed top of figures — who manages them and in
 * which shapes, our record against them, the quality of the two likely XIs — then tabs, one
 * open at a time and remembered across clubs: the line-up we expect, the squad, and every
 * meeting with us (filterable, each with its line-up) with who hurt us at both ends.
 *
 * Everything is computed here from matches.json (both sides' lines in our matches, each
 * opponent's manager and current squad, the formations' slots) and the player files. A club
 * outside the divisions core.json covers needs all.json, fetched the first time such a sheet
 * opens. Quality is Level %ile (`lvlLeague` / `lvlGlobal`): tactic-agnostic, and the fair
 * number for a stranger.
 */
import * as D from "./data.js";
import { el, clear, num, pill, sheet, multiSelect, DASH } from "./ui.js";
import { openPlayer } from "./profile.js";
import { scoreText } from "./views/matches.js";

const TAB_KEY = "fm:club:tab";
const RES = { W: "good", D: "flat", L: "bad" };
// The positions in pitch order, back to front, and the unit each belongs to (mart.dim_position).
const ORDER = ["GK", "DL", "DC", "DR", "DML", "DMC", "DMR", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST"];
const UNIT = { GK: "Goalkeeper", DL: "Defence", DC: "Defence", DR: "Defence", DML: "Defence",
  DMR: "Defence", DMC: "Midfield", ML: "Midfield", MC: "Midfield", MR: "Midfield",
  AML: "Attack", AMC: "Attack", AMR: "Attack", ST: "Attack" };
const NATURAL = 15;
const pref = (k, fallback) => { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } };
const setPref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private browsing */ } };
const day = (d) => String(d).slice(0, 10);
const kpi = (label, value, title, cls = "") =>
  el(`div.kpi${cls}`, { title }, [el("b", { text: String(value) }), el("span", { text: label })]);
const rowsOf = (fields, rows) => rows.map((r) => Object.fromEntries(fields.map((n, i) => [n, r[i]])));

/** The listed formation whose slots are exactly these eleven positions, else null. */
function shapeOf(positions, slots) {
  const key = [...positions].sort().join(",");
  for (const [shape, s] of Object.entries(slots)) {
    const k = Object.entries(s).flatMap(([pos, n]) => Array(n).fill(pos)).sort().join(",");
    if (k === key) return shape;
  }
  return null;
}

/** tid -> the position he started in most, over starts on or after `since`. */
function playedAs(rows, since) {
  const n = new Map();
  for (const r of rows) {
    if (!r.started || !r.position || day(r.date) < since) continue;
    const c = n.get(r.tid) || new Map();
    c.set(r.position, (c.get(r.position) || 0) + 1);
    n.set(r.tid, c);
  }
  return new Map([...n].map(([tid, c]) => [tid, [...c].sort((a, b) => b[1] - a[1])[0][0]]));
}

/** A player's home position: where he has played, else his most familiar. */
function home(p, played) {
  const there = played.get(p.tid);
  if (there && p.positions.some((q) => q.pos === there)) return there;
  return [...p.positions].sort((a, b) => b.fam - a.fam || (b.lvlGlobal ?? 0) - (a.lvlGlobal ?? 0))[0]?.pos;
}
const at = (p, pos) => p.positions.find((q) => q.pos === pos);

/**
 * The XI a squad most likely puts out in `shape`: each slot goes first to the best player whose
 * home position it is, then to the best natural (familiarity 15+) left, then to anyone who can
 * play there at all (marked makeshift). Best = Level %ile world-wide at that position. The bench
 * is the next seven by their best Level.
 */
function expectedXI(players, shape, slots, played) {
  const left = { ...(slots[shape] || {}) };
  const used = new Set();
  const xi = [];
  const fill = (ok, makeshift = false) => {
    for (const pos of ORDER) {
      while (left[pos] > 0) {
        const best = players.filter((p) => !used.has(p.tid) && at(p, pos) && ok(p, pos))
          .sort((a, b) => (at(b, pos).lvlGlobal ?? 0) - (at(a, pos).lvlGlobal ?? 0))[0];
        if (!best) break;
        xi.push({ p: best, pos, q: at(best, pos), there: played.get(best.tid) === pos, makeshift });
        used.add(best.tid);
        left[pos]--;
      }
    }
  };
  fill((p, pos) => home(p, played) === pos);
  fill((p, pos) => at(p, pos).fam >= NATURAL);
  fill(() => true, true);
  xi.sort((a, b) => ORDER.indexOf(a.pos) - ORDER.indexOf(b.pos));
  const bench = players.filter((p) => !used.has(p.tid))
    .map((p) => ({ p, q: [...p.positions].sort((a, b) => (b.lvlGlobal ?? 0) - (a.lvlGlobal ?? 0))[0] }))
    .filter((x) => x.q).sort((a, b) => b.q.lvlGlobal - a.q.lvlGlobal).slice(0, 7);
  return { xi, bench, level: xi.length ? xi.reduce((s, x) => s + (x.q.lvlGlobal ?? 0), 0) / xi.length : null };
}

function nameCell(tid) {
  return el("td.name", { text: D.matchName(tid) });
}
function playerRow(tid, cells) {
  return el("tr.click", { onclick: () => openPlayer(tid) }, cells);
}
function table(head, rows, numFrom = 2) {
  return el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, head.map((h, i) => el(`th${i >= numFrom ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, rows),
  ])]);
}

export async function openClub(tid) {
  const M = await D.loadMatches();
  const ourTid = D.S.ours.managed_tid;
  const squads = M.team_squads || {};
  const theirTids = squads[String(tid)] || [];
  const ourTids = squads[String(ourTid)] || [];
  const meetings = rowsOf(M.match_fields, M.matches).filter((m) => m.opp_tid === tid);
  const title = D.S.clubs.get(tid)?.name || meetings[0]?.opponent || `#${tid}`;

  // A club outside core.json's divisions: its players are only in all.json.
  if (!D.S.all && [...theirTids, ...ourTids].some((t) => !D.S.players.has(t))) {
    const wait = sheet(title, [el("p.note", { text: "Loading every player in the save…" })], { wide: true });
    await D.loadAll().catch(() => null);
    wait.remove();
  }

  const slots = M.formation_slots || {};
  const theirRows = rowsOf(M.opponent_player_fields, M.opponent_player_rows).filter((r) => r.team_tid === tid);
  const ourRows = D.matchRows();
  const ourVs = ourRows.filter((r) => r.opponent_tid === tid);
  const byDate = (rows) => {
    const g = new Map();
    for (const r of rows) { const k = day(r.date); g.set(k, [...(g.get(k) || []), r]); }
    return g;
  };
  const theirByDate = byDate(theirRows);
  const ourByDate = byDate(ourVs);
  const shapeOn = (d) => shapeOf((theirByDate.get(d) || []).filter((r) => r.started && r.position)
    .map((r) => r.position), slots);

  const latest = [...meetings].sort((a, b) => day(b.date).localeCompare(day(a.date)))[0];
  const yearBefore = (d) => `${+d.slice(0, 4) - 1}${d.slice(4)}`;
  const theirPlayed = latest ? playedAs(theirRows, yearBefore(day(latest.date))) : new Map();
  const ourLast = ourRows.reduce((a, r) => (day(r.date) > a ? day(r.date) : a), "");
  const ourPlayed = playedAs(ourRows, yearBefore(ourLast));
  const theirPlayers = theirTids.map((t) => D.S.players.get(t)).filter(Boolean);
  const ourPlayers = ourTids.map((t) => D.S.players.get(t)).filter(Boolean);

  const mgr = M.managers?.[String(tid)];
  const manager = mgr ? Object.fromEntries(M.manager_fields.map((k, i) => [k, mgr[i]])) : null;
  const lastShape = latest ? shapeOn(day(latest.date)) : null;
  const shapes = [];
  const addShape = (key, label, shape) => {
    if (!shape || !slots[shape]) return;
    const seen = shapes.find((s) => s.shape === shape);
    if (seen) { if (key !== "default") seen.label += ` · ${label}`; } else shapes.push({ key, label, shape });
  };
  addShape("last", "last v us", lastShape);
  addShape("preferred", "preferred", manager?.formation_preferred);
  addShape("attacking", "attacking", manager?.formation_attacking);
  addShape("defensive", "defensive", manager?.formation_defensive);
  addShape("default", "no manager shape known", "4-2-3-1");
  const ourShape = "4-2-3-1";

  // ---- the top: who they are, then the figures
  const body = [];
  const club = D.S.clubs.get(tid);
  const league = club ? D.S.leagues.get(club.leagueCid)?.name : null;
  const comp = meetings.filter((m) => !/friend/i.test(m.competition || ""));
  const w = comp.filter((m) => m.result === "W").length;
  const dr = comp.filter((m) => m.result === "D").length;
  const l = comp.filter((m) => m.result === "L").length;
  const gf = comp.reduce((a, m) => a + (m.gf || 0), 0);
  const ga = comp.reduce((a, m) => a + (m.ga || 0), 0);
  // A club outside the save's playable leagues keeps only the few players it has signed from
  // them, so there is no squad to pick an XI from.
  const fullSquad = theirPlayers.length >= 11;
  const thinNote = () => el("p.note", { text: theirPlayers.length
    ? `The save holds only ${theirPlayers.length} of this club's players: a club outside the save's `
      + "playable leagues keeps no full squad. Their line-ups against us are under Against us."
    : "The save holds no squad for this club. Their line-ups against us are under Against us." });
  const theirXI = shapes.length && fullSquad ? expectedXI(theirPlayers, shapes[0].shape, slots, theirPlayed) : null;
  const ourXI = expectedXI(ourPlayers, ourShape, slots, ourPlayed);
  const gap = theirXI?.level != null && ourXI.level != null ? ourXI.level - theirXI.level : null;
  body.push(el("div.phead", {}, [
    league ? el("div.pline", {}, [el("span.dim", { text: league })]) : null,
    el("div.kpis.sm", {}, [
      manager ? kpi("Manager", manager.name || DASH, `Style: ${manager.style || "unknown"}`) : null,
      manager?.style ? kpi("Style", manager.style) : null,
      manager?.formation_preferred ? kpi("Prefers", manager.formation_preferred,
        `Attacking ${manager.formation_attacking || DASH} · defensive ${manager.formation_defensive || DASH}`) : null,
      lastShape && lastShape !== manager?.formation_preferred
        ? kpi("Last v us", lastShape, `Their full-time shape on ${day(latest.date)}`, ".warn") : null,
      kpi("W-D-L v us", comp.length ? `${w}-${dr}-${l}` : DASH, "Competitive matches"),
      comp.length ? kpi("Goals", `${gf}:${ga}`, "Ours first, competitive matches") : null,
      latest ? kpi("Last met", `${scoreText(latest)} ${latest.result}`, `${day(latest.date)} · ${latest.competition}`,
        `.${RES[latest.result] || "flat"}`) : null,
      gap != null ? kpi("XI Level", `${num(ourXI.level)} v ${num(theirXI.level)}`,
        "Average Level %ile (world) of the expected XIs: ours in 4-2-3-1, theirs in the shape below",
        gap >= 5 ? ".good" : gap <= -5 ? ".bad" : "") : null,
    ]),
  ]));

  // ---- tabs
  const TABS = [
    ["lineup", "Line-up", () => lineupTab()],
    ["squad", "Squad", () => squadTab()],
    ["vs", "Against us", () => vsTab()],
  ];
  let cur = pref(TAB_KEY, "lineup");
  if (!TABS.some((t) => t[0] === cur)) cur = "lineup";
  const tabBar = el("div.ptabs", { role: "tablist" });
  const tabBody = el("div.ptab");
  const show = (key, remember) => {
    cur = key;
    if (remember) setPref(TAB_KEY, key);
    for (const b of tabBar.children) b.classList.toggle("on", b.dataset.tab === key);
    clear(tabBody).append(TABS.find((t) => t[0] === key)[2]());
  };
  for (const [key, label] of TABS) {
    tabBar.append(el("button", { text: label, role: "tab", dataset: { tab: key }, onclick: () => show(key, true) }));
  }
  body.push(tabBar, tabBody);

  // per player, against us: appearances, goals, assists
  const vsTotals = new Map();
  for (const r of theirRows) {
    const t = vsTotals.get(r.tid) || { apps: 0, goals: 0, assists: 0 };
    t.apps++; t.goals += r.goals || 0; t.assists += r.assists || 0;
    vsTotals.set(r.tid, t);
  }
  const vsCell = (tid2) => {
    const t = vsTotals.get(tid2);
    return el("td.num", { text: t ? `${t.apps} · ${t.goals}G ${t.assists}A` : DASH,
      title: "Appearances against us · goals · assists" });
  };
  const age = (p) => D.age(p.dob) ?? DASH;

  function lineupTab() {
    const box = el("div");
    if (!fullSquad) return thinNote();
    const sel = el("select.btn.sm", { title: "The shape to pick their XI in: as they last lined up "
      + "against us, or their manager's preferred, attacking or defensive formation" },
    shapes.map((s) => el("option", { value: s.shape, text: `${s.shape} (${s.label})` })));
    const out = el("div");
    const draw = () => {
      const { xi, bench } = expectedXI(theirPlayers, sel.value, slots, theirPlayed);
      clear(out).append(
        table(["Pos", "Player", "Age", "Level (league)", "Level (world)", "v us"], xi.map((x) => playerRow(x.p.tid, [
          el("td", { text: x.pos + (x.there ? " ★" : "") + (x.makeshift ? " ⚠" : ""),
            title: x.makeshift ? "Out of position: nobody natural left for this slot"
              : x.there ? "Where he has started against us" : "" }),
          nameCell(x.p.tid), el("td.num", { text: age(x.p) }),
          el("td.num", { text: num(x.q.lvlLeague) }), el("td.num", { text: num(x.q.lvlGlobal) }),
          vsCell(x.p.tid),
        ]))),
        el("h4", { text: "Bench" }),
        table(["Best", "Player", "Age", "Level (league)", "Level (world)", "v us"], bench.map((b) => playerRow(b.p.tid, [
          el("td", { text: b.q.pos }), nameCell(b.p.tid), el("td.num", { text: age(b.p) }),
          el("td.num", { text: num(b.q.lvlLeague) }), el("td.num", { text: num(b.q.lvlGlobal) }),
          vsCell(b.p.tid),
        ]))),
      );
    };
    sel.addEventListener("change", draw);
    box.append(el("div.prow", {}, [sel]), out,
      el("p.note", { text: "Each slot goes to the best player by Level %ile whose usual position it is — "
        + "where he has started against us in the last year (★), else his most familiar — then to "
        + "the best natural left. ⚠ = nobody natural left. Their current squad from the save; "
        + "this week's injuries and suspensions are not in it." }));
    draw();
    return box;
  }

  function squadTab() {
    const rows = theirPlayers.map((p) => {
      const pos = home(p, theirPlayed);
      return { p, pos, q: at(p, pos) };
    }).filter((x) => x.q)
      .sort((a, b) => ORDER.indexOf(a.pos) - ORDER.indexOf(b.pos) || b.q.lvlGlobal - a.q.lvlGlobal);
    if (!rows.length) return thinNote();
    return el("div", {}, [
      fullSquad ? null : thinNote(),
      table(["Pos", "Player", "Age", "Natural", "Level (league)", "Level (world)", "v us"], rows.map((x) =>
        playerRow(x.p.tid, [
          el("td", { text: x.pos + (theirPlayed.get(x.p.tid) === x.pos ? " ★" : "") }),
          nameCell(x.p.tid), el("td.num", { text: age(x.p) }),
          el("td.num", { text: x.p.positions.filter((q) => q.fam >= NATURAL).map((q) => q.pos).join(" ") || DASH }),
          el("td.num", { text: num(x.q.lvlLeague) }), el("td.num", { text: num(x.q.lvlGlobal) }),
          vsCell(x.p.tid),
        ]))),
      el("p.note", { text: "Each player at his usual position: where he has started against us in the "
        + "last year (★), else his most familiar. Level %ile is at that position." }),
    ]);
  }

  function vsTab() {
    const box = el("div");
    if (!meetings.length) return el("p.note", { text: "We have not played them in a match the save details." });
    let friendlies = false;
    const friendlyOk = (m) => friendlies || !/friend/i.test(m.competition || "");
    const count = (ms, key) => { const c = new Map(); for (const m of ms) c.set(key(m), (c.get(key(m)) || 0) + 1); return c; };
    const seasonMs = multiSelect({
      noun: "season", plural: "seasons",
      options: () => {
        const c = count(meetings.filter(friendlyOk), (m) => m.season);
        return [...c.keys()].sort((a, b) => b - a).map((s) => ({ value: s, label: s, hint: c.get(s) }));
      },
      onChange: () => draw(),
    });
    const compMs = multiSelect({
      noun: "competition", plural: "competitions",
      options: () => {
        const c = count(meetings.filter((m) => friendlyOk(m)
          && (!seasonMs.selected.size || seasonMs.selected.has(m.season))), (m) => m.competition);
        return [...c.keys()].sort().map((k) => ({ value: k, label: k, hint: c.get(k) }));
      },
      onChange: () => draw(),
    });
    const friBtn = el("button.btn", {
      text: "Friendlies off",
      onclick: () => {
        friendlies = !friendlies;
        friBtn.textContent = friendlies ? "Friendlies on" : "Friendlies off";
        friBtn.classList.toggle("on", friendlies);
        draw();
      },
    });
    const out = el("div");
    box.append(el("div.prow", {}, [seasonMs.node, compMs.node, friBtn]), out);

    function lineup(d) {
      const ours = ourByDate.get(d) || [];
      const theirs = theirByDate.get(d) || [];
      const potm = [...ours, ...theirs].find((r) => r.potm);
      const lines = theirs.filter((r) => r.started || r.minutes > 0)
        .sort((a, b) => (b.started - a.started) || ORDER.indexOf(a.position) - ORDER.indexOf(b.position));
      return el("div", {}, [
        potm ? el("p.note", { text: `Player of the Match: ${D.matchName(potm.tid)}` }) : null,
        table(["Pos", "Player", "Min", "Rating", "G", "A", "KP", "Tkl", "Int", "Hdr"], lines.map((r) => playerRow(r.tid, [
          el("td", { text: r.started ? r.position || DASH : "sub" }), nameCell(r.tid),
          el("td.num", { text: r.minutes }), el("td.num", { text: r.rating ?? DASH }),
          el("td.num", { text: r.goals }), el("td.num", { text: r.assists }), el("td.num", { text: r.keyPass }),
          el("td.num", { text: r.tackW }), el("td.num", { text: r.intercept }), el("td.num", { text: r.headW }),
        ]))),
      ]);
    }

    function hurtTables(dates) {
      const keep = theirRows.filter((r) => dates.has(day(r.date)) && (r.started || r.minutes > 0));
      const agg = new Map();
      for (const r of keep) {
        const a = agg.get(r.tid) || { tid: r.tid, apps: 0, min: 0, goals: 0, assists: 0, keyPass: 0,
          shotO: 0, tackW: 0, intercept: 0, headW: 0, headA: 0, rating: 0 };
        a.apps++; a.min += r.minutes || 0; a.rating += r.rating || 0;
        for (const k of ["goals", "assists", "keyPass", "shotO", "tackW", "intercept", "headW", "headA"]) a[k] += r[k] || 0;
        agg.set(r.tid, a);
      }
      const still = new Set(theirTids);
      const there = (t) => el("td", { text: still.has(t) ? "✓" : "", title: "Still in their squad" });
      const all = [...agg.values()];
      const att = all.filter((a) => a.goals + a.assists + a.keyPass > 0)
        .sort((a, b) => b.goals + b.assists - a.goals - a.assists || b.keyPass - a.keyPass).slice(0, 10);
      const def = all.filter((a) => a.tackW + a.intercept + a.headW > 0)
        .sort((a, b) => (b.tackW + b.intercept + b.headW) / b.apps - (a.tackW + a.intercept + a.headW) / a.apps)
        .slice(0, 10);
      return [
        el("h4", { text: "Who hurt us — going forward" }),
        att.length ? table(["Player", "Still there", "Apps", "G", "A", "Key passes", "On target", "Avg rating"],
          att.map((a) => playerRow(a.tid, [nameCell(a.tid), there(a.tid), el("td.num", { text: a.apps }),
            el("td.num", { text: a.goals }), el("td.num", { text: a.assists }), el("td.num", { text: a.keyPass }),
            el("td.num", { text: a.shotO }), el("td.num", { text: num(a.rating / a.apps, 2) })])), 2)
          : el("p.note", { text: "Nobody has scored, assisted or made a key pass against us here." }),
        el("h4", { text: "Who stopped us — at the back" }),
        def.length ? table(["Player", "Still there", "Apps", "Tackles won", "Interceptions", "Headers won",
          "Per game", "Avg rating"],
        def.map((a) => playerRow(a.tid, [nameCell(a.tid), there(a.tid), el("td.num", { text: a.apps }),
          el("td.num", { text: a.tackW }), el("td.num", { text: a.intercept }),
          el("td.num", { text: `${a.headW}/${a.headA}`, title: "Headers won / contested" }),
          el("td.num", { text: num((a.tackW + a.intercept + a.headW) / a.apps, 1),
            title: "Tackles won + interceptions + headers won, per appearance" }),
          el("td.num", { text: num(a.rating / a.apps, 2) })])), 2)
          : el("p.note", { text: "No defensive actions recorded against us here." }),
        el("p.note", { text: "Over the filtered meetings. Defenders rank on actions per game, so a man "
          + "who won everything in one match sits above one who was busy over five — check Apps." }),
      ];
    }

    function draw() {
      seasonMs.sync(); compMs.sync();
      const ms = meetings.filter((m) => friendlyOk(m)
        && (!seasonMs.selected.size || seasonMs.selected.has(m.season))
        && (!compMs.selected.size || compMs.selected.has(m.competition)))
        .sort((a, b) => day(b.date).localeCompare(day(a.date)));
      const rows = [];
      for (const m of ms) {
        const d = day(m.date);
        const detail = el("tr.detail", { hidden: true }, [el("td", { colSpan: 7 })]);
        const potm = [...(ourByDate.get(d) || []), ...(theirByDate.get(d) || [])].find((r) => r.potm);
        rows.push(el("tr.click", {
          title: "Show their line-up",
          onclick: () => {
            detail.hidden = !detail.hidden;
            if (!detail.hidden && !detail.firstChild.firstChild) detail.firstChild.append(lineup(d));
          },
        }, [
          el("td", { text: d }), el("td", { text: m.competition || DASH }), el("td", { text: m.venue }),
          el("td.num", { text: scoreText(m) }), el("td", {}, [pill(m.result, RES[m.result] || "flat")]),
          el("td", { text: shapeOn(d) || DASH }),
          el("td.name", { text: potm ? D.matchName(potm.tid) : DASH }),
        ]), detail);
      }
      clear(out).append(
        el("h4", { text: `Meetings · ${ms.length}` }),
        table(["Date", "Competition", "H/A", "Score", "", "Their shape", "Player of the Match"], rows, 3),
        el("p.note", { text: "Tap a match for their line-up that day." }),
        ...hurtTables(new Set(ms.map((m) => day(m.date)))),
      );
    }
    draw();
    return box;
  }

  show(cur, false);
  sheet(title, body, { wide: true });
}
