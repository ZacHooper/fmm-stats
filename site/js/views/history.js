/**
 * History — the club's own story, in five tabs that each answer one question:
 *
 *   Seasons        what happened each year?      one entry per season, newest first (or the full table)
 *   Hall of Fame   who are our greats?           one leaderboard at a time, with each player's career line
 *   Transfers      who came and went?            every move in or out, by season, with key figures
 *   Records        what are the bests?           the record book: single-match bests and runs
 *   Awards         who won what?                 the honours board (season × award), or one season in full
 *
 * Its own section rather than a tab on Matches, because Matches answers "how are we playing"
 * and this answers "what have we done". Everything is computed in the browser from the same
 * match rows, so a new superlative is a few lines here rather than an exporter change.
 *
 * Only the managed club's matches are richly parsed, so these are OUR records — not the
 * league's. And match detail lives in a ring buffer the game overwrites as a season runs, so a
 * long-ago game may simply not be in the save any more.
 *
 * Some winners here — especially in the Hall of Fame, which spans a player's whole time at the
 * club — are no longer on the current squad. `D.matchName` still names them (matches.json's
 * `player_names`, for anyone who ever played for us), and `openPlayer` still opens them: the full
 * profile when the save holds him, otherwise his record for us.
 */
import * as D from "../data.js";
import { el, num, money, pill, bar, DASH, hashParams, setHashParams } from "../ui.js";
import { openPlayer } from "../profile.js";
import { openClub } from "../club.js";
import { ourMoves, seasonMoney, feeText, netText, playerLink, clubLink } from "../transfers.js";

// How far a season got in one competition: the stage of its last match there.
// "3F Superliga (Championship Group)", "Sydbank Pokalen (Fourth Round, out)".
function reached(ms, comp) {
  const staged = ms.filter((m) => m.stage).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (!staged.length) return comp;
  const last = staged[staged.length - 1];
  const where = last.stage_kind === "Group" ? "Group stage" : last.stage;
  const isFinal = /(^|· )Final$/.test(last.stage);
  const tail = last.went_through === false ? ", out"
    : isFinal && last.went_through ? ", winners" : "";
  return `${comp} (${where}${tail})`;
}

// Appearances needed to qualify for an AVERAGE-RATING award over a full fixture list.
// Mirrors dashboard/pages/11_Awards.py's RATING_AWARD_APPS — keep the two in step.
const RATING_AWARD_APPS = 20;

// Tab order is one constant — reorder here and nothing else moves.
const TABS = [
  ["seasons", "Seasons"],
  ["fame", "Hall of Fame"],
  ["transfers", "Transfers"],
  ["records", "Records"],
  ["awards", "Awards"],
];
const LS_TAB = "fm:history:tab";
const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
// A tap anywhere but an award header, or any scroll, closes an open award tip (the honours
// board on a no-hover device): the tip is placed on the screen, so it would drift otherwise.
const closeTips = (e) => {
  if (e?.target?.closest?.("th.tipped")) return;
  for (const th of document.querySelectorAll("table.board th.open")) th.classList.remove("open");
};
document.addEventListener("click", closeTips);
document.addEventListener("scroll", () => closeTips(), true);
const seasonLabel = (s) => `${s - 1}/${String(s).slice(2)}`;
const day = (d) => String(d).slice(0, 10);

export async function view() {
  const M = await D.loadMatches();
  await D.loadSquad();
  if (!M.matches?.length) {
    return el("div.card", {}, [el("b", { text: "No matches parsed" }), el("p.note", { text: M.note })]);
  }
  const f = M.match_fields;
  const matches = M.matches.map((r) => Object.fromEntries(f.map((n, i) => [n, r[i]])))
    .filter((m) => !D.isFriendly(m.competition));
  // Competitive matches only, like `matches` above: a pre-season friendly hat-trick is not a
  // Golden Boot goal.
  const rows = D.matchRows().filter((r) => !D.isFriendly(r.competition));
  const seasons = [...new Set(matches.map((m) => m.season))].sort((a, b) => b - a);
  const oppName = (m) => m.opponent || `#${m.opp_tid}`;
  const oppByTid = new Map(matches.map((m) => [m.opp_tid, oppName(m)]));

  // Real home-game attendance per season, from mart.club_attendance (same source as "Biggest
  // Crowd" — raw.matches.attendance — just aggregated once server-side).
  const af = M.attendance_fields || [];
  const attBySeason = new Map((M.attendance || [])
    .map((r) => Object.fromEntries(af.map((n, i) => [n, r[i]])))
    .map((a) => [a.season, a]));
  // Squad value + wage bill at the season's LAST snapshot (mart.squad_finances, owned players
  // only — a loanee's value is his parent club's, and his wage share under the loan isn't known).
  const ff = M.finance_fields || [];
  const finBySeason = new Map();
  for (const r of M.finances || []) {
    const o = Object.fromEntries(ff.map((n, i) => [n, r[i]]));
    const prev = finBySeason.get(o.season);
    if (!prev || String(o.phase) > String(prev.phase)) finBySeason.set(o.season, o);
  }

  // Awards are computed once per season and shared by the season cards, the Awards tab and
  // the Honours board.
  const awardCache = new Map();
  const playerAwards = (s) => {
    if (!awardCache.has(s)) awardCache.set(s, seasonPlayerAwards(rows, matches, s));
    return awardCache.get(s);
  };

  // Our transfers (transfers.js): the Transfers tab, the Signings and Sales boards, and each
  // season's spent / received / net. Absent from an older export: those parts just don't show.
  const moves = ourMoves(await D.loadTransfers());
  const moneyBySeason = seasonMoney(moves);

  // ---------------------------------------------------------------- per-season summary
  const prog = seasons.map((s) => {
    const ms = matches.filter((m) => m.season === s);
    // The league is the season's most-played competition (no competition-type flag ships to
    // the client — the same rule seasonTeamAwards' Cup Run uses); every other one is a cup run.
    const byComp = new Map();
    for (const m of ms) if (m.competition) byComp.set(m.competition, (byComp.get(m.competition) || 0) + 1);
    const order = [...byComp.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
    const runs = order.map((c) => ({ comp: c, ...reachedParts(ms.filter((m) => m.competition === c)) }));
    return {
      season: s, p: ms.length,
      w: ms.filter((m) => m.result === "W").length,
      d: ms.filter((m) => m.result === "D").length,
      l: ms.filter((m) => m.result === "L").length,
      gf: ms.reduce((a, m) => a + (m.gf || 0), 0),
      ga: ms.reduce((a, m) => a + (m.ga || 0), 0),
      ppg: ms.length ? ms.reduce((a, m) => a + (m.pts || 0), 0) / ms.length : null,
      league: runs[0] || null, cups: runs.slice(1),
      comps: order.map((c) => reached(ms.filter((m) => m.competition === c), c)),
      snaps: D.S.index.snapshots.filter((x) => x.season === s).length,
      att: attBySeason.get(s) || null,
      fin: finBySeason.get(s) || null,
      tx: moneyBySeason.get(s) || null,
    };
  });

  // ---------------------------------------------------------------- shell
  const out = el("div");
  out.append(el("h2", { text: "History" }));
  const all = { p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
  for (const m of matches) {
    all.p++; all.gf += m.gf || 0; all.ga += m.ga || 0; all.pts += m.pts || 0;
    if (m.result) all[m.result.toLowerCase()]++;
  }
  const leagues = [...prog].reverse().map((r) => r.league?.comp).filter(Boolean);
  const journey = leagues.length ? (leagues[0] === leagues.at(-1) ? leagues[0] : `${leagues[0]} → ${leagues.at(-1)}`) : DASH;
  const won = prog.flatMap((r) => [r.league, ...r.cups].filter((x) => x?.winners).map((x) => `${x.comp} ${seasonLabel(r.season)}`));
  out.append(el("div.kpis", {}, [
    el("div.kpi", { title: `${seasonLabel(seasons.at(-1))} to ${seasonLabel(seasons[0])}` },
      [el("b", { text: String(seasons.length) }), el("span", { text: "Seasons" })]),
    kpi("All-time W-D-L", `${all.w}-${all.d}-${all.l}`),
    kpi("Goals", `${all.gf}:${all.ga}`),
    kpi("Pts/game", all.p ? num(all.pts / all.p, 2) : DASH),
    el("div.kpi.wide", { title: won.length ? `Won: ${won.join(", ")}` : "No knockout competition won in the parsed matches" }, [
      el("b", { text: journey }), el("span", { text: won.length ? `Journey · ${won.length} trophy${won.length === 1 ? "" : "ies"}` : "Journey" }),
    ]),
  ]));
  const tabRow = el("div.prow.mtabs", { role: "tablist" });
  const panel = el("div");
  out.append(tabRow, panel);

  const known = (t) => TABS.some(([k]) => k === t);
  // "honours" was its own tab before the board moved into Awards; an old link still lands there.
  if (hashParams().get("tab") === "honours") setHashParams({ tab: "awards", board: null, view: "board" });
  let tab = [hashParams().get("tab"), lsGet(LS_TAB)].find(known) || TABS[0][0];
  function show(t, extra = {}) {
    tab = t; lsSet(LS_TAB, t); setHashParams({ tab: t, ...extra });
    draw();
    tabRow.scrollIntoView({ block: "nearest" });
  }
  function draw() {
    tabRow.replaceChildren(...TABS.map(([k, label]) => el(`button.chip${k === tab ? ".on" : ""}`, {
      text: label, role: "tab", "aria-selected": k === tab ? "true" : "false", onclick: () => show(k),
    })));
    const PANELS = { seasons: seasonsTab, fame, transfers, records, awards };
    panel.replaceChildren(PANELS[tab]());
  }

  // A player's name as a link — every name on the page opens something (openPlayer).
  const who = (tid) => el("a.plink", { href: "#", text: D.matchName(tid),
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); openPlayer(tid); } });
  const club = (tid, name) => (tid == null ? name : el("a.plink", { href: "#", text: name,
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); openClub(tid); } }));

  // ---------------------------------------------------------------- Seasons
  // Per season: the two headline awards, each with its figure, and how each competition went.
  const seasonStars = (s) => {
    const aw = playerAwards(s);
    const get = (label) => aw.find((a) => a.label === label) || null;
    return { pots: get("Player of the season"), boot: get("Golden boot") };
  };
  const runText = (x) => (x.winners ? "Winners" : x.where ? `${x.where}${x.out ? " · out" : ""}` : DASH);
  const runCls = (x) => (x.winners ? "win" : x.out ? "out" : "");

  // The timeline reads; the full table is for comparing every figure at once.
  const LAYOUTS = [["timeline", "Timeline"], ["full", "Full table"]];
  function seasonsTab() {
    const want = hashParams().get("layout");
    const layout = (LAYOUTS.find(([k]) => k === want) || LAYOUTS[0])[0];
    const seg = el("span.mseg", {}, LAYOUTS.map(([k, l]) => el(`button.chip${k === layout ? ".on" : ""}`, {
      text: l, onclick: () => { setHashParams({ layout: k === LAYOUTS[0][0] ? null : k }); draw(); },
    })));
    const body = layout === "timeline" ? el("div.tl", {}, prog.map(timelineEntry)) : seasonTable();
    return el("div", {}, [
      el("div.prow", {}, [el("span.dim", { text: "Layout" }), seg]),
      body,
      el("p.note", { text: "Friendlies excluded. Match counts come from the newest snapshot of each "
        + "season and can fall short of the true fixture list (match detail sits in a ring buffer "
        + "the game overwrites). How far a run got is the stage of its last match, in the game's own "
        + "words; \"out\" is a tie lost. Crowds are home games only; squad value and wage bill are "
        + "at the season's last snapshot, owned players only. Spent and received are transfer fees "
        + "for the campaign a player moved FOR, so a June signing counts toward the next season." }),
    ]);
  }

  // Timeline: a rail down the left, each season a short story. On a wide screen the story
  // sits on the left (league, record, cups) and the season's people and figures on the right.
  function timelineEntry(r) {
    const { pots, boot } = seasonStars(r.season);
    const fig = (label, value, title, cls = "") => el(`div.tlfig${cls}`, { title }, [el("b", { text: value }), el("span", { text: label })]);
    // Four figures: results, goals, crowd, transfers. Squad value and wages are a dim line
    // under the story — the full table has them as columns.
    const tx = r.tx;
    const figs = [
      fig("Pts/gm", r.ppg == null ? DASH : num(r.ppg, 2)),
      fig("Goals", `${r.gf}:${r.ga}`),
      r.att ? fig("Avg crowd", r.att.avg_att.toLocaleString(), `Biggest: ${r.att.max_att.toLocaleString()}`) : null,
      tx ? el(`div.tlfig${tx.net > 0 ? ".up" : tx.net < 0 ? ".down" : ""}`, {
        title: `Received less spent on fees · ${tx.nIn} in, ${tx.nOut} out (paid and free)`,
      }, [el("b", { text: netText(tx.net) }), el("span", { text: "Transfers" }),
        el("small", { text: `${money(tx.spent)} in · ${money(tx.received)} out` })]) : null,
    ].filter(Boolean);
    const money2 = [
      r.fin ? `Squad value ${money(r.fin.value_gbp)}` : null,
      r.fin ? `wage bill ${money(r.fin.wage_gbp)}` : null,
    ].filter(Boolean).join(" · ");
    return el("div.tlitem", {}, [
      el("div.tldot"),
      el("div.tlhead", {}, [
        el("b", { text: seasonLabel(r.season) }),
        el("span", { text: r.league?.comp || "" }),
        r.league ? el(`span.run.${runCls(r.league) || "plain"}`, { text: runText(r.league) }) : null,
        el("span.tlwdl", {}, [el("b", { text: `${r.w}-${r.d}-${r.l}` }), el("span.dim", { text: " W-D-L" })]),
      ]),
      el("div.tlgrid", {}, [
        el("div.tlstory", {}, [
          r.cups.length ? el("ul.tlcups", {}, r.cups.map((c) => el("li", {}, [
            el("span", { text: c.comp }), el(`span.run.${runCls(c) || "plain"}`, { text: runText(c) }),
          ]))) : el("div.dim", { text: "No cup matches parsed" }),
          el("div.tlstars", {}, [
            pots ? el("div", {}, [el("span.dim", { text: "Player of the season " }), who(pots.who), el("span.dim", { text: ` ${pots.value}` })]) : null,
            boot ? el("div", {}, [el("span.dim", { text: "Golden boot " }), who(boot.who), el("span.dim", { text: ` ${boot.value}` })]) : null,
          ]),
          money2 ? el("div.dim.tlmoney", { text: money2, title: r.fin ? `At ${r.fin.phase}, owned players` : null }) : null,
          el("button.link.tlawards", { text: "All awards ›", onclick: () => show("awards", { season: r.season, view: "season" }) }),
        ]),
        el("div.tlfigs", {}, figs),
      ]),
    ]);
  }

  function seasonTable() {
    const HEAD = ["Season", "P", "W", "D", "L", "GF", "GA", "GD", "Pts/gm",
      "Avg crowd", "Max crowd", "Squad value", "Wage bill", "Spent", "Received", "Net",
      "Competitions · how far", "Snapshots"];
    const TEXT_COLS = new Set([0, HEAD.indexOf("Competitions · how far")]);
    const finTitle = (f) => `At ${f.phase} · ${f.n_owned} owned players`
      + (f.n_value_est ? ` · ${f.n_value_est} valued by the model (no value in the save)` : "")
      + (f.n_loan_in ? ` · ${f.n_loan_in} loanee${f.n_loan_in === 1 ? "" : "s"} excluded` : "");
    return el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, HEAD
        .map((h, i) => el(`th${TEXT_COLS.has(i) ? "" : ".num"}`, { text: h })))]),
      el("tbody", {}, prog.map((r) => el("tr", {}, [
        el("td.name", { text: seasonLabel(r.season) }), el("td.num", { text: r.p }), el("td.num", { text: r.w }),
        el("td.num", { text: r.d }), el("td.num", { text: r.l }), el("td.num", { text: r.gf }),
        el("td.num", { text: r.ga }),
        el("td.num", { text: (r.gf - r.ga >= 0 ? "+" : "") + (r.gf - r.ga) }),
        el("td.num", { text: r.ppg == null ? DASH : num(r.ppg, 2) }),
        el("td.num", { text: r.att ? r.att.avg_att.toLocaleString() : DASH }),
        el("td.num", { text: r.att ? r.att.max_att.toLocaleString() : DASH }),
        el("td.num", r.fin ? { text: money(r.fin.value_gbp), title: finTitle(r.fin) } : { text: DASH }),
        el("td.num", r.fin ? { text: money(r.fin.wage_gbp), title: finTitle(r.fin) } : { text: DASH }),
        el("td.num", { text: r.tx ? money(r.tx.spent) : DASH }),
        el("td.num", { text: r.tx ? money(r.tx.received) : DASH }),
        el(`td.num${r.tx?.net > 0 ? ".gain" : r.tx?.net < 0 ? ".loss" : ""}`, { text: r.tx ? netText(r.tx.net) : DASH }),
        el("td", { text: r.comps.join(", ") || DASH }),
        el("td.num", { text: r.snaps }),
      ]))),
    ])]);
  }

  // ---------------------------------------------------------------- Hall of Fame
  // One leaderboard at a time, picked with chips, each row carrying the player's whole career
  // line for us — so "top scorer" also says how many games it took and whether he is still here.
  // A board for a count also carries its rate (goals -> G/90), which is what separates a
  // prolific striker from one who simply stayed a long time.
  const career = D.aggregate(rows);
  const span = new Map();            // tid -> [first season, last season]
  for (const r of rows) {
    const s = span.get(r.tid);
    if (!s) span.set(r.tid, [r.season, r.season]);
    else { if (r.season < s[0]) s[0] = r.season; if (r.season > s[1]) s[1] = r.season; }
  }
  const hatTricks = new Map();
  for (const r of rows) if (r.goals >= 3) hatTricks.set(r.tid, (hatTricks.get(r.tid) || 0) + 1);
  const p90 = (n, a) => (a.min ? (90 * n) / a.min : null);
  const BOARDS = [
    // key, label, value, dp, [rate label, rate(a), dp]
    ["apps", "Appearances", (a) => a.apps, 0, ["Min/gm", (a) => (a.apps ? a.min / a.apps : null), 0]],
    ["goals", "Goals", (a) => a.goals, 0, ["G/90", (a) => p90(a.goals, a), 2]],
    ["assists", "Assists", (a) => a.assists, 0, ["A/90", (a) => p90(a.assists, a), 2]],
    ["ga", "Goal involvements", (a) => a.goals + a.assists, 0, ["G+A/90", (a) => p90(a.goals + a.assists, a), 2]],
    ["min", "Minutes", (a) => a.min, 0, ["Min/gm", (a) => (a.apps ? a.min / a.apps : null), 0]],
    ["rating", `Average rating`, (a) => (a.apps >= RATING_AWARD_APPS ? a.rating : null), 2, null],
    ["hat", "Hat-tricks", (a) => hatTricks.get(a.tid) || null, 0, ["Games per", (a) => (hatTricks.get(a.tid) ? a.apps / hatTricks.get(a.tid) : null), 0]],
    ["potm", "Player of the Match", (a) => a.potm, 0, ["Per 10 apps", (a) => (a.apps ? (10 * a.potm) / a.apps : null), 1]],
  ];
  // Signings and Sales: the biggest fees we have paid and been paid, each with what the player
  // did for us and the other end of his time here — a signing's later sale, a sale's fee in.
  const TX_BOARDS = moves.length ? [["signings", "Signings", "in"], ["sales", "Sales", "out"]] : [];
  function transferBoard(dir) {
    const paid = moves.filter((m) => m.direction === dir && m.type === "permanent" && m.fee)
      .sort((a, b) => b.fee - a.fee).slice(0, 15);
    // the other end of his time here: for a signing his next sale, for a sale his last signing
    const other = (m) => {
      const ends = moves.filter((x) => x.tid === m.tid && x.direction !== dir && x.type !== "graduation");
      return dir === "in" ? ends.filter((x) => x.season >= m.season).sort((a, b) => a.season - b.season)[0]
        : ends.filter((x) => x.season <= m.season).sort((a, b) => b.season - a.season)[0];
    };
    return el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, [["#", 1], ["Player", 0], ["Fee", 1], [dir === "in" ? "From" : "To", 0], ["Season", 0],
        ["Age", 1], ["Apps", 1], ["Goals", 1], ["Rating (adj)", 1], [dir === "in" ? "Sold for" : "Bought for", 1], ["", 0]]
        .map(([h, n], i) => el(`th${n ? ".num" : ""}${i === 2 ? ".sorted" : ""}`, { text: h })))]),
      el("tbody", {}, paid.map((m, i) => {
        const a = career.get(m.tid);
        const o = other(m);
        const here = (() => { const p = D.S.players.get(m.tid); return !!p && D.isOurs(p); })();
        return el("tr.click", { onclick: () => openPlayer(m.tid) }, [
          el("td.num.dim", { text: i + 1 }), el("td.name", { text: m.name }),
          el("td.num.hl", { text: money(m.fee) }),
          el("td", {}, [dir === "in" ? clubLink(m.from_tid, m.from_club) : clubLink(m.to_tid, m.to_club)]),
          el("td", { text: seasonLabel(m.season) }), el("td.num", { text: m.age ?? DASH }),
          el("td.num", { text: a ? a.apps : 0 }), el("td.num", { text: a ? a.goals : 0 }),
          el("td.num", { text: a?.ratingAdj != null ? num(a.ratingAdj, 2) : DASH }),
          el("td.num", { text: o ? feeText(o) : DASH, title: o ? `${seasonLabel(o.season)} · ${o.direction === "in" ? o.from_club || "free agent" : o.to_club}` : null }),
          el("td", {}, [dir === "in" ? (here ? pill("At the club", "good") : pill("Left", "flat")) : null]),
        ]);
      })),
    ])]);
  }

  function fame() {
    const want = hashParams().get("board");
    const tx = TX_BOARDS.find((b) => b[0] === want);
    const [, label, fn, dp, rate] = BOARDS.find((b) => b[0] === want) || BOARDS[0];
    const key = (BOARDS.find((b) => b[0] === want) || BOARDS[0])[0];
    const list = [...career.values()].map((a) => ({ a, v: fn(a) }))
      .filter((x) => x.v != null && Number.isFinite(x.v) && x.v > 0)
      .sort((x, y) => y.v - x.v).slice(0, 15);
    const chips = el("div.prow", {}, [el("span.mseg", {}, [...BOARDS, ...TX_BOARDS].map(([k, l]) => el(`button.chip${k === (tx ? tx[0] : key) ? ".on" : ""}`, {
      text: l, onclick: () => { setHashParams({ board: k }); draw(); },
    })))]);
    if (tx) {
      return el("div", {}, [chips, transferBoard(tx[2]), el("p.note", { text: "Paid moves only, by fee. "
        + "Apps, goals and Rating (adj) are his competitive career for us. "
        + `${tx[2] === "in" ? "Sold for" : "Bought for"} is the other end of his time here, where there was one.` })]);
    }
    const here = (tid) => { const p = D.S.players.get(tid); return !!p && D.isOurs(p); };
    // The career line, less the column the board already shows.
    const line = [["apps", "Apps", (a) => a.apps], ["goals", "Goals", (a) => a.goals],
      ["assists", "Assists", (a) => a.assists], ["rating", "Rating", (a) => (a.rating == null ? DASH : num(a.rating, 2))]]
      .filter(([k]) => k !== key);
    const cols = [["#", 1], ["Player", 0], [label, 1], ...(rate ? [[rate[0], 1]] : []),
      ...line.map(([, h]) => [h, 1]), ["Seasons", 0], ["", 0]];
    return el("div", {}, [
      chips,
      el("div.scroll", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, cols.map(([h, n], i) => el(`th${n ? ".num" : ""}${i === 2 ? ".sorted" : ""}`, { text: h })))]),
        el("tbody", {}, list.map(({ a, v }, i) => {
          const sp = span.get(a.tid);
          return el("tr.click", { onclick: () => openPlayer(a.tid) }, [
            el("td.num.dim", { text: i + 1 }), el("td.name", { text: D.matchName(a.tid) }),
            el("td.num.hl", { text: num(v, dp) }),
            ...(rate ? [el("td.num", { text: rate[1](a) == null ? DASH : num(rate[1](a), rate[2]) })] : []),
            ...line.map(([, , f]) => el("td.num", { text: f(a) })),
            el("td", { text: sp ? (sp[0] === sp[1] ? seasonLabel(sp[0]) : `${seasonLabel(sp[0])} – ${seasonLabel(sp[1])}`) : DASH }),
            el("td", {}, [here(a.tid) ? pill("At the club", "good") : pill("Left", "flat")]),
          ]);
        })),
      ])]),
      el("p.note", { text: "Career totals for us across every parsed match, all seasons combined, "
        + `including players who have left. Average rating needs ${RATING_AWARD_APPS}+ appearances.` }),
    ]);
  }

  // ---------------------------------------------------------------- Transfers
  // Every move in or out, all seasons or one, with the key figures for the span as tiles.
  // Free moves and academy graduates are moves too, so they're listed; only paid moves carry
  // money into the tiles.
  function transfers() {
    if (!moves.length) return el("p.note", { text: "No transfer data in this export." });
    const q = hashParams();
    const tSeasons = [...new Set(moves.map((m) => m.season))].sort((a, b) => b - a);
    const want = Number(q.get("tseason"));
    const yr = tSeasons.includes(want) ? want : null;
    const dir = ["in", "out"].includes(q.get("dir")) ? q.get("dir") : null;
    const inSpan = moves.filter((m) => yr == null || m.season === yr);
    const shown = inSpan.filter((m) => dir == null || m.direction === dir)
      .sort((a, b) => b.season - a.season || String(b.date || "").localeCompare(String(a.date || "")));
    const chip = (label, on, kv) => el(`button.chip${on ? ".on" : ""}`, { text: label, onclick: () => { setHashParams(kv); draw(); } });
    const ins = inSpan.filter((m) => m.direction === "in" && m.type !== "graduation");
    const outs = inSpan.filter((m) => m.direction === "out");
    const sum = (xs) => xs.reduce((t, m) => t + (m.fee || 0), 0);
    const spent = sum(ins), received = sum(outs);
    const best = (xs) => xs.filter((m) => m.fee).sort((a, b) => b.fee - a.fee)[0];
    const recIn = best(ins), recOut = best(outs);
    const grads = inSpan.filter((m) => m.type === "graduation").length;
    const tile = (label, value, sub, cls = "") => el(`div.kpi${cls}`, {}, [el("b", { text: value }), el("span", { text: label }), sub ? el("small", { text: sub }) : null]);
    return el("div", {}, [
      el("div.prow", {}, [
        el("span.mseg", {}, [chip("All seasons", yr == null, { tseason: null }),
          ...tSeasons.map((y) => chip(seasonLabel(y), y === yr, { tseason: y }))]),
      ]),
      el("div.prow", {}, [el("span.mseg", {}, [chip("In and out", dir == null, { dir: null }),
        chip("Signings", dir === "in", { dir: "in" }), chip("Departures", dir === "out", { dir: "out" })])]),
      el("div.kpis.hl", {}, [
        tile("Spent", money(spent), `${ins.filter((m) => m.fee).length} paid of ${ins.length} signings`),
        tile("Received", money(received), `${outs.filter((m) => m.fee).length} paid of ${outs.length} departures`),
        tile("Transfer net", netText(received - spent), "received less spent", received - spent > 0 ? ".good" : received - spent < 0 ? ".bad" : ""),
        recIn ? tile("Record signing", money(recIn.fee), `${recIn.name} · ${recIn.from_club}`) : null,
        recOut ? tile("Record sale", money(recOut.fee), `${recOut.name} · ${recOut.to_club}`) : null,
        tile("Academy graduates", String(grads), "into the first team or reserves"),
      ]),
      el("div.scroll", {}, [el("table.book", {}, [
        // [label, numeric?, hidden on a phone?]
        el("thead", {}, [el("tr", {}, [["Season", 0], ["Date", 0, 1], ["", 0], ["Player", 0], ["Age", 1, 1], ["Club", 0],
          ["Fee", 1], ["Apps", 1], ["Goals", 1, 1], ["Rating (adj)", 1]].map(([h, n, sm]) => el(`th${n ? ".num" : ""}${sm ? ".hide-sm" : ""}`, { text: h })))]),
        el("tbody", {}, shown.length ? shown.map((m) => {
          const a = career.get(m.tid);
          return el("tr", {}, [
            el("td", { text: seasonLabel(m.season) }), el("td.dim.hide-sm", { text: m.date || DASH }),
            el("td", {}, [m.type === "graduation" ? pill("Academy", "flat") : pill(m.direction === "in" ? "In" : "Out", m.direction === "in" ? "good" : "bad")]),
            el("td.name", {}, [playerLink(m.tid, m.name)]), el("td.num.hide-sm", { text: m.age ?? DASH }),
            el("td", {}, [m.type === "graduation" ? el("span.dim", { text: "Youth side" })
              : m.direction === "in" ? clubLink(m.from_tid, m.from_club) : clubLink(m.to_tid, m.to_club)]),
            el(`td.num${m.fee ? ".hl" : ".dim"}`, { text: feeText(m) }),
            el("td.num", { text: a ? a.apps : 0 }), el("td.num.hide-sm", { text: a ? a.goals : 0 }),
            el("td.num", { text: a?.ratingAdj != null ? num(a.ratingAdj, 2) : DASH }),
          ]);
        }) : [el("tr", {}, [el("td.empty", { colspan: 10, text: "No moves." })])]),
      ])]),
      el("p.note", { text: "Season is the campaign he moved FOR: a June signing counts toward the "
        + "next season. Apps, goals and Rating (adj) are his whole competitive career for us. "
        + "Loans aren't transfers and aren't listed." }),
    ]);
  }

  // ---------------------------------------------------------------- Records
  // The record book: three plain tables, every opponent and every player a link.
  function records() {
    const margin = (m) => (m.gf || 0) - (m.ga || 0);
    const first = (xs, cmp) => [...xs].sort(cmp)[0];
    // [label, numeric?, hide on a phone?]
    const book = (head, list) => el("div.scroll", {}, [el("table.book", {}, [
      el("thead", {}, [el("tr", {}, head.map(([h, n, sm]) => el(`th${n ? ".num" : ""}${sm ? ".hide-sm" : ""}`, { text: h })))]),
      el("tbody", {}, list),
    ])]);
    const matchRow = (label, value, m) => el("tr", {}, [
      el("td.name", { text: label }), el("td.num.hl", { text: value }),
      el("td", {}, [m.venue === "H" ? "v " : "at ", club(m.opp_tid, oppName(m))]),
      el("td.dim.hide-sm", { text: m.competition || DASH }), el("td.dim", { text: day(m.date) }),
    ]);
    const team = [
      ["Biggest win", first(matches, (a, b) => margin(b) - margin(a) || b.gf - a.gf)],
      ["Heaviest defeat", first(matches, (a, b) => margin(a) - margin(b) || b.ga - a.ga)],
      ["Most goals scored", first(matches, (a, b) => b.gf - a.gf)],
      ["Most goals conceded", first(matches, (a, b) => b.ga - a.ga)],
    ].filter(([, m]) => m).map(([label, m]) => matchRow(label, `${m.gf}–${m.ga}`, m));
    const gate = first(matches.filter((m) => m.venue === "H" && m.attendance), (a, b) => b.attendance - a.attendance);
    if (gate) team.push(matchRow("Biggest home crowd", Number(gate.attendance).toLocaleString(), gate));

    const chron = [...matches].sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const runs = [
      ["Longest unbeaten run", streak(chron, (m) => m.result !== "L")],
      ["Longest winning run", streak(chron, (m) => m.result === "W")],
      ["Clean sheets in a row", streak(chron, (m) => m.ga === 0)],
      ["Longest winless run", streak(chron, (m) => m.result !== "W")],
    ].map(([label, r]) => el("tr", {}, [
      el("td.name", { text: label }), el("td.num.hl", { text: `${r.len}` }),
      el("td.dim", { text: r.len ? `${day(r.from)} → ${day(r.to)}` : DASH }),
    ]));

    const single = (key, label, dp = 0) => {
      const best = rows.filter((r) => r[key] != null).sort((a, b) => b[key] - a[key])[0];
      if (!best) return null;
      const opp = oppByTid.get(best.opponent_tid) || D.S.clubs.get(best.opponent_tid)?.name || `#${best.opponent_tid}`;
      return el("tr", {}, [
        el("td.name", { text: label }), el("td.num.hl", { text: num(best[key], dp) }),
        el("td", {}, [who(best.tid)]),
        el("td", {}, ["v ", club(best.opponent_tid, opp)]),
        el("td.dim.hide-sm", { text: day(best.date) }),
      ]);
    };
    const players = [
      single("goals", "Goals in a match"), single("assists", "Assists in a match"),
      single("rating", "Match rating", 2), single("keyPass", "Key passes"),
      single("tackW", "Tackles won"), single("intercept", "Interceptions"),
      single("passC", "Completed passes"), single("dribbles", "Dribbles"),
    ].filter(Boolean);
    return el("div", {}, [
      el("h3", { text: "Team · single match" }),
      book([["Record", 0], ["", 1], ["Opponent", 0], ["Competition", 0, 1], ["Date", 0]], team),
      el("h3", { text: "Team · runs" }),
      book([["Run", 0], ["Games", 1], ["When", 0]], runs),
      el("h3", { text: "Players · single match" }),
      book([["Most …", 0], ["", 1], ["Player", 0], ["Opponent", 0], ["Date", 0, 1]], players),
      el("p.note", { text: "All competitive matches in the save, all seasons. A run counts consecutive "
        + "parsed matches, so a gap in the ring buffer can join or split one." }),
    ]);
  }

  // ---------------------------------------------------------------- Awards
  // Two views of one set of awards. The board is the honours board on the clubhouse wall:
  // seasons down the side, an award per column, the winner in each cell — and the figure
  // under it when "Figures" is on. "One season" lists a season's awards in full, with how each
  // was decided.
  function awards() {
    const q = hashParams();
    const view = q.get("view") === "season" ? "season" : "board";
    const kind = q.get("kind") === "team" ? "team" : "player";
    const figures = q.get("fig") === "1";
    const silly = q.get("silly") === "1";
    const toggle = (label, on, kv, title) => el(`button.chip${on ? ".on" : ""}`, { text: label, title, onclick: () => { setHashParams(kv); draw(); } });
    const views = el("span.mseg", {}, [
      toggle("Honours board", view === "board", { view: null }),
      toggle("One season", view === "season", { view: "season" }),
    ]);
    if (view === "season") return el("div", {}, [el("div.prow", {}, [views]), seasonAwards(q)]);
    const opts = el("span.mseg", {}, [
      toggle("Player", kind === "player", { kind: null }),
      toggle("Team", kind === "team", { kind: "team" }),
      toggle("Figures", figures, { fig: figures ? null : "1" }, "Show each winner's figure under his name"),
      ...(kind === "player" ? [toggle("Silly awards", silly, { silly: silly ? null : "1" })] : []),
    ]);
    const cells = new Map();          // season -> Map(award -> {text, fig, tid})
    const order = [];
    for (const s of seasons) {
      const items = kind === "player"
        ? playerAwards(s).filter((a) => silly || !a.silly).map((a) => ({ label: a.label, text: D.matchName(a.who), fig: a.value, note: a.note, means: a.means, tid: a.who }))
        : seasonTeamAwards(matches.filter((m) => m.season === s)).map((a) => ({ label: a.label, text: a.value, fig: a.note, note: a.note }));
      const m = new Map();
      for (const it of items) { m.set(it.label, it); if (!order.includes(it.label)) order.push(it.label); }
      cells.set(s, m);
    }
    // repeat winners: a running count, oldest season first
    const times = new Map();
    for (const label of order) {
      const seen = new Map();
      for (const s of [...seasons].reverse()) {
        const c = cells.get(s).get(label);
        if (c?.tid == null) continue;
        const n = (seen.get(c.tid) || 0) + 1;
        seen.set(c.tid, n);
        times.set(`${s}|${label}`, n);
      }
    }
    const meaning = awardMeanings(cells);
    return el("div", {}, [
      el("div.prow", {}, [views, opts]),
      el("div.scroll", {}, [el(`table.board${figures ? ".withfig" : ""}`, {}, [
        el("thead", {}, [el("tr", {}, [el("th", { text: "Season" }), ...order.map((l, i) => {
          // What the award is for: shown on hover, or on a tap where there is no hover. The
          // last couple of columns open their tip leftward so it stays inside the table.
          const tip = kind === "player" ? meaning.get(l) : null;
          if (!tip) return el("th", { text: l });
          // A tapped tip is placed on the screen (fixed) rather than in the table, so the
          // scroll box can't clip it and it never runs off the edge of a phone.
          return el(`th.tipped${i >= order.length - 2 ? ".tipleft" : ""}`, {
            "aria-label": `${l}: ${tip}`,
            onclick: (e) => {
              const th = e.currentTarget, open = !th.classList.contains("open");
              for (const o of th.parentNode.querySelectorAll("th.open")) o.classList.remove("open");
              if (!open) return;
              const r = th.getBoundingClientRect(), box = th.querySelector(".thtip");
              const w = Math.min(230, document.documentElement.clientWidth - 16);
              box.style.width = `${w}px`;
              box.style.left = `${Math.max(8, Math.min(r.left, document.documentElement.clientWidth - w - 8))}px`;
              box.style.top = `${r.bottom + 4}px`;
              th.classList.add("open");
            },
          }, [el("span.thlbl", { text: l }), el("span.thtip", { text: tip })]);
        })])]),
        el("tbody", {}, seasons.map((s) => el("tr", {}, [
          el("td.name", {}, [el("button.link", { text: seasonLabel(s), title: "This season's awards in full",
            onclick: () => { setHashParams({ view: "season", season: s }); draw(); } })]),
          ...order.map((label) => {
            const c = cells.get(s).get(label);
            if (!c) return el("td.dim", { text: DASH });
            const n = times.get(`${s}|${label}`) || 0;
            const open = c.tid != null;
            return el(`td${open ? ".click" : ""}`, { title: `${c.fig} — ${c.note}`, onclick: open ? () => openPlayer(c.tid) : null }, [
              el("span.who", {}, [c.text, n > 1 ? el("span.times", { text: ` ×${n}` }) : null]),
              figures && kind === "player" ? el("span.bfig", { text: c.fig }) : null,
              figures && kind === "team" ? el("span.bfig", { text: c.note }) : null,
            ]);
          }),
        ]))),
      ])]),
      el("p.note", { text: "Newest season first. ×2, ×3 … counts a player's repeat wins of the same "
        + "award. Hover or tap a cell for how it was decided; a season opens that season in full." }),
      kind === "player" ? el("p.note", { text: "Hover an award (tap on a phone) for what it rewards. "
        + "To qualify a player needs about 30% of the season's matches (at least 3); Player of the "
        + `season and Young Gun, both average ratings, need about 60% (up to ${RATING_AWARD_APPS}). `
        + "Appearances count substitutes; Young Gun is U21 at the season's 1 January." }) : null,
    ]);
  }

  // What each player award rewards. The wording is the award's own "decided by" note (or its
  // `means`, where the note describes the winning match), so the tip can't drift from the
  // computation. The appearance bar changes season to season, so it is stated once under the
  // board instead.
  function awardMeanings(cells) {
    const meaning = new Map();
    for (const s of seasons) {
      for (const [label, c] of cells.get(s)) {
        const text = c.means || c.note;
        if (!meaning.has(label) && text) meaning.set(label, text.replace(/,? ?min \d+ apps/, ""));
      }
    }
    return meaning;
  }

  function seasonAwards(q) {
    const want = Number(q.get("season"));
    const s = seasons.includes(want) ? want : seasons[0];
    const silly = q.get("silly") === "1";
    const sm = matches.filter((m) => m.season === s);
    const items = playerAwards(s).filter((a) => silly || !a.silly);
    const team = seasonTeamAwards(sm);
    const games = sm.length;
    const minApps = Math.max(3, Math.round(games * 0.3));
    const table = (head, body) => el("div.scroll", {}, [el("table.book", {}, [
      el("thead", {}, [el("tr", {}, head.map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, body),
    ])]);
    return el("div", {}, [
      el("div.prow", {}, [
        el("span.mseg", {}, seasons.map((x) => el(`button.chip${x === s ? ".on" : ""}`, {
          text: seasonLabel(x), onclick: () => { setHashParams({ season: x }); draw(); },
        }))),
        el(`button.chip${silly ? ".on" : ""}`, { text: "Silly awards",
          onclick: () => { setHashParams({ silly: silly ? null : "1" }); draw(); } }),
      ]),
      el("h3", { text: `Player awards · ${seasonLabel(s)}` }),
      items.length ? table([["Award", 0], ["Winner", 0], ["", 1], ["Decided by", 0]], items.map((a) =>
        el("tr.click", { onclick: () => openPlayer(a.who) }, [
          el("td.name", {}, [a.label, a.silly ? el("span.dim", { text: " · silly" }) : null]),
          el("td", {}, [who(a.who)]), el("td.num.hl", { text: a.value }), el("td.dim", { text: a.note }),
        ]))) : el("p.note", { text: "No player data this season." }),
      el("h3", { text: "Team awards" }),
      team.length ? table([["Award", 0], ["", 1], ["Detail", 0]], team.map((a) => el("tr", {}, [
        el("td.name", { text: a.label }), el("td.num.hl", { text: a.value }), el("td.dim", { text: a.note }),
      ]))) : el("p.note", { text: "No managed-club matches this season." }),
      el("p.note", { text: `${games} parsed matches; minimum ${minApps} appearances to qualify (the bar `
        + "scales with games played, so a two-game cameo can't win anything). The two average-rating "
        + "awards set it higher again, since an average over a dozen games is noise. Appearances "
        + "count substitutes." }),
    ]);
  }

  draw();
  return out;
}

/** How far a run got: the stage of the competition's last match, and whether it ended there. */
function reachedParts(ms) {
  const staged = ms.filter((m) => m.stage).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (!staged.length) return { where: "", out: false, winners: false };
  const last = staged[staged.length - 1];
  const where = last.stage_kind === "Group" ? "Group stage" : String(last.stage).split(" · ").pop();
  const isFinal = /(^|· )Final$/.test(last.stage);
  return { where, out: last.went_through === false, winners: isFinal && !!last.went_through };
}

/** Every player award for one season — the full list, including silly ones (the interactive
 *  view filters those with a toggle; the Roll of Honour always shows everything, same as the
 *  dashboard's default). Shared by the per-season display and the all-years matrix. */
function seasonPlayerAwards(rows, matches, s) {
  const sr = rows.filter((r) => r.season === s);
  if (!sr.length) return [];
  const agg = D.aggregate(sr);
  const games = new Set(sr.map((r) => String(r.date))).size;
  const minApps = Math.max(3, Math.round(games * 0.3));
  const pool = [...agg.values()].filter((a) => a.apps >= minApps);
  const top = (fn, label, dp = 2, note = "", silly = false, from = pool) => {
    const best = from.map((a) => ({ a, v: fn(a) })).filter((x) => x.v != null && Number.isFinite(x.v))
      .sort((x, y) => y.v - x.v)[0];
    return best ? { label, who: best.a.tid, value: num(best.v, dp), note, silly } : null;
  };

  // Player of the Season and Young Gun are AVERAGE-RATING awards, and an average over a
  // handful of games is mostly noise: a fringe player's dozen-game purple patch outranks a
  // full campaign, which is how one player ends up winning both. They need a real season's
  // work — RATING_AWARD_APPS over a normal fixture list — where every other award keeps the
  // lower `minApps` bar, because a counting stat (goals, key passes, minutes) already
  // rewards playing more. The bar scales down only if the season itself is short, so a
  // half-season store or a career's opening months still crowns someone.
  const ratingMinApps = Math.max(minApps, Math.min(RATING_AWARD_APPS, Math.round(games * 0.6)));
  const ratingPool = pool.filter((a) => a.apps >= ratingMinApps);

  // Young Gun: age at the season's last new year, the same cutoff the registration rules use.
  const ageAt = (tid) => D.age(D.S.players.get(tid)?.dob, `${s}-01-01`);

  // Hat-trick Hero: best single-game goal haul this season.
  const hattrick = sr.filter((r) => r.goals >= 1).sort((a, b) => b.goals - a.goals)[0];
  const hattrickAward = hattrick ? {
    label: "Hat-trick Hero", who: hattrick.tid, value: num(hattrick.goals),
    means: "most goals in a single match",
    note: `vs ${D.S.clubs.get(hattrick.opponent_tid)?.name || `#${hattrick.opponent_tid}`} · `
      + `${String(hattrick.date).slice(0, 10)}`,
  } : null;

  // Golden Glove: GK starts in a game that finished as a clean sheet (ga from the team's own
  // match rows, joined by date — the same technique the dashboard uses).
  const gaByDate = new Map(matches.filter((m) => m.season === s).map((m) => [String(m.date), m.ga]));
  const csCount = new Map();
  for (const r of sr) {
    if (r.position !== "GK" || !r.started) continue;
    if (gaByDate.get(String(r.date)) === 0) csCount.set(r.tid, (csCount.get(r.tid) || 0) + 1);
  }
  const glove = [...csCount.entries()].sort((a, b) => b[1] - a[1])[0];
  const goldenGlove = glove ? { label: "Golden Glove", who: glove[0], value: num(glove[1]),
    note: "clean sheets started" } : null;

  // Supersub: goals+assists in matches he didn't start.
  const subAgg = D.aggregate(sr.filter((r) => !r.started));
  const bestSub = [...subAgg.values()].map((a) => ({ a, v: a.goals + a.assists }))
    .filter((x) => x.v > 0).sort((x, y) => y.v - x.v)[0];
  const superSub = bestSub ? { label: "Supersub", who: bestSub.a.tid, value: num(bestSub.v),
    note: "goals+assists off the bench" } : null;

  // The Stormtrooper: one match where he couldn't hit a barn door — the most shots off target
  // in a single game (a season of it is Wasteful's job). Ties go to the one who didn't score,
  // then to the one who shot more. Any appearance counts: it is one bad afternoon, not a season.
  const off = (r) => (r.shotA || 0) - (r.shotO || 0);
  const trooper = sr.filter((r) => off(r) > 0)
    .sort((x, y) => off(y) - off(x) || (x.goals || 0) - (y.goals || 0) || (y.shotA || 0) - (x.shotA || 0))[0];
  const stormtrooper = trooper ? {
    label: "The Stormtrooper", who: trooper.tid, value: `${off(trooper)} of ${trooper.shotA} off target`,
    note: `vs ${D.S.clubs.get(trooper.opponent_tid)?.name || `#${trooper.opponent_tid}`} · `
      + `${String(trooper.date).slice(0, 10)}${trooper.goals ? ` (scored ${trooper.goals})` : ""}`,
    means: "most shots off target in a single match", silly: true,
  } : null;

  return [
    top((a) => a.rating, "Player of the season", 2,
      `highest average match rating, min ${ratingMinApps} apps`, false, ratingPool),
    top((a) => (ageAt(a.tid) != null && ageAt(a.tid) <= 21 ? a.rating : null),
      "Young Gun (U21)", 2, `highest average rating, U21, min ${ratingMinApps} apps`,
      false, ratingPool),
    top((a) => a.potm || null, "Man of the Match", 0, "most Player of the Match awards, competitive matches"),
    top((a) => a.goals, "Golden boot", 0, "most goals"),
    hattrickAward,
    top((a) => a.assists, "Playmaker", 0, "most assists"),
    top((a) => a.keyPass, "The Maestro", 0, "most key passes"),
    top((a) => a.crossC, "The Crosser", 0, "most crosses completed"),
    top((a) => a.headW, "Aerial Dominator", 0, "most headers won"),
    top((a) => a.dribbles, "Quick Feet", 0, "most dribbles"),
    top((a) => (a.min ? (90 * a.goals) / a.min : null), "Most lethal", 2, "goals per 90"),
    top((a) => (a.passA ? (100 * a.passC) / a.passA : null), "Metronome", 0, "pass completion %"),
    top((a) => a.tackW + a.intercept + a.headW, "Destroyer", 0, "tackles won + interceptions + headers won"),
    goldenGlove,
    top((a) => (a.shotA >= 10 ? (100 * a.goals) / a.shotA : null), "Deadeye", 0,
      "shots -> goals %, min 10 shots"),
    top((a) => a.min, "Iron man", 0, "most minutes"),
    superSub,
    top((a) => (a.min ? (90 * a.mistakes) / a.min : null), "Butterfingers", 2,
      "mistakes per 90 — the one you don't want", true),
    top((a) => (a.min ? (90 * a.yellow) / a.min : null), "Most booked", 2, "yellows per 90", true),
    top((a) => (a.shotA >= 10 && a.goals === 0 ? a.shotA : null), "Wasteful", 0,
      "most shots without scoring (10+ shots)", true),
    stormtrooper,
  ].filter(Boolean);
}

/** Team-level awards for one season's matches — mirrors dashboard/pages/11_Awards.py's
 *  TEAM_AWARDS, built from columns already in matches.json (our_/opp_ pairs, venue, result, date). */
function seasonTeamAwards(sm) {
  if (!sm.length) return [];
  const t = sm.map((m) => ({
    ...m,
    margin: (m.gf ?? 0) - (m.ga ?? 0),
    total: (m.gf ?? 0) + (m.ga ?? 0),
    passpct: m.our_passes >= 100 ? (100 * m.our_passes_completed) / m.our_passes : null,
  }));
  const W = t.filter((m) => m.result === "W").length;
  const Dd = t.filter((m) => m.result === "D").length;
  const L = t.filter((m) => m.result === "L").length;
  const gf = t.reduce((a, m) => a + (m.gf || 0), 0);
  const ga = t.reduce((a, m) => a + (m.ga || 0), 0);
  const ppg = (3 * W + Dd) / t.length;

  const mrow = (key, fmt, filterFn = null) => {
    let d = t.filter((m) => m[key] != null);
    if (filterFn) d = d.filter(filterFn);
    if (!d.length) return null;
    const r = [...d].sort((a, b) => b[key] - a[key])[0];
    return { value: fmt(r), note: `vs ${r.opponent || `#${r.opp_tid}`} · ${String(r.date).slice(0, 10)} (${r.venue})` };
  };
  const rec = (x) => {
    if (!x.length) return null;
    const w = x.filter((m) => m.result === "W").length;
    const d = x.filter((m) => m.result === "D").length;
    const l = x.filter((m) => m.result === "L").length;
    return { value: `${w}W ${d}D ${l}L`, note: `${((3 * w + d) / x.length).toFixed(2)} PPG (${x.length} games)` };
  };
  const chron = [...t].sort((a, b) => String(a.date).localeCompare(String(b.date)));

  const byMonth = new Map();
  for (const m of t) {
    const ym = String(m.date).slice(0, 7);
    if (!byMonth.has(ym)) byMonth.set(ym, []);
    byMonth.get(ym).push(m);
  }
  let bestMonth = null;
  for (const [ym, ms] of byMonth) {
    if (ms.length < 2) continue;
    const w = ms.filter((m) => m.result === "W").length;
    const d = ms.filter((m) => m.result === "D").length;
    const l = ms.filter((m) => m.result === "L").length;
    const ppgM = (3 * w + d) / ms.length;
    if (!bestMonth || ppgM > bestMonth.ppg) bestMonth = { ppg: ppgM, ym, w, d, l, n: ms.length };
  }

  // Biggest Crowd is OUR gate, so only home games count — the 32,962 at Parken is
  // København's crowd, not ours, and it outdrew every home game we ever played.
  const crowd = mrow("attendance", (r) => Number(r.attendance).toLocaleString(),
    (m) => m.venue === "H");

  // Cup Run: no competition-type flag ships to the client, so this is a heuristic — the
  // season's most-played competition is treated as the league (true for any real fixture
  // list), and the deepest run in any other named competition is the cup run.
  const byComp = new Map();
  for (const m of t) { const c = m.competition || ""; byComp.set(c, (byComp.get(c) || 0) + 1); }
  const leagueComp = [...byComp.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const cupGames = t.filter((m) => m.competition && m.competition !== leagueComp);
  let cupRun = null;
  if (cupGames.length) {
    const byCup = new Map();
    for (const m of cupGames) {
      if (!byCup.has(m.competition)) byCup.set(m.competition, []);
      byCup.get(m.competition).push(m);
    }
    const [cupName, games] = [...byCup.entries()].sort((a, b) => b[1].length - a[1].length)[0];
    const last = [...games].sort((a, b) => String(a.date).localeCompare(String(b.date))).at(-1);
    const status = last.result === "W" ? "won it" : `out ${last.gf}–${last.ga} vs ${last.opponent || `#${last.opp_tid}`}`;
    cupRun = { value: `${games.length} matches`, note: `${cupName} · last: ${status}` };
  }

  return [
    ["Season Record", { value: `${W}W ${Dd}D ${L}L`, note: `${gf} for / ${ga} against · ${ppg.toFixed(2)} PPG` }],
    ["Biggest Win", mrow("margin", (r) => `${r.gf}–${r.ga} (+${r.margin})`, (m) => m.result === "W")],
    ["Highest-scoring Game", mrow("total", (r) => `${r.gf}–${r.ga} (${r.total} goals)`)],
    ["Best Passing Display", mrow("passpct", (r) => `${r.passpct.toFixed(0)}% pass completion`)],
    ["Most Shots in a Game", mrow("our_shots", (r) => `${r.our_shots} shots`)],
    ["Clean Sheets", { value: `${t.filter((m) => m.ga === 0).length} of ${t.length}`, note: "shut-outs this season" }],
    ["Longest Clean-sheet Streak",
      { value: `${streak(chron, (m) => m.ga === 0).len} in a row`, note: "consecutive shut-outs" }],
    ["Longest Win Streak",
      { value: `${streak(chron, (m) => m.result === "W").len} in a row`, note: "consecutive wins" }],
    ["Longest Unbeaten Run",
      { value: `${streak(chron, (m) => m.result !== "L").len} games`, note: "without defeat" }],
    ["Home Fortress", rec(t.filter((m) => m.venue === "H"))],
    ["Road Warriors", rec(t.filter((m) => m.venue === "A"))],
    bestMonth ? ["Best Month", { value: `${bestMonth.ppg.toFixed(2)} PPG`,
      note: `${bestMonth.ym} (${bestMonth.w}W ${bestMonth.d}D ${bestMonth.l}L, ${bestMonth.n} games)` }] : null,
    crowd ? ["Biggest Crowd", crowd] : null,
    cupRun ? ["Cup Run", cupRun] : null,
  ].filter(Boolean).map(([label, v]) => (v ? { label, value: v.value, note: v.note } : null)).filter(Boolean);
}

function streak(chron, pred) {
  let best = 0, cur = 0, from = null, bestFrom = null, bestTo = null;
  for (const m of chron) {
    if (pred(m)) {
      if (!cur) from = m.date;
      cur++;
      if (cur > best) { best = cur; bestFrom = from; bestTo = m.date; }
    } else cur = 0;
  }
  return { len: best, from: bestFrom, to: bestTo };
}
const kpi = (label, value) => el("div.kpi", {}, [el("b", { text: String(value) }), el("span", { text: label })]);
