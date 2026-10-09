/**
 * Transfers — api/transfers.json read for the pages that show it: History (our signings and
 * sales, the season ledger) and World (the market, season by season, and the world record).
 *
 * The file ships our own moves whole and the world market already summarised per season (the
 * career holds ~4,500 moves a season; no page lists them all). `season` everywhere is the
 * campaign a player moved FOR: a June signing belongs to the next season's market.
 */
import * as D from "./data.js";
import { el, num, money, pill, DASH } from "./ui.js";
import { openPlayer } from "./profile.js";
import { openClub } from "./club.js";

export const seasonLabel = (s) => `${s - 1}/${String(s).slice(2)}`;
const rowsOf = (fields, rows) => (rows || []).map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])));

/** Our moves, one object each, competitive history only (in_career rows). */
export function ourMoves(T) {
  return T ? rowsOf(T.ours_fields, T.ours) : [];
}

/** A move's fee as people say it: a sum, "Free", or "Academy" for a youth graduate. */
export function feeText(m) {
  if (m.type === "graduation") return "Academy";
  if (m.type === "free" || !m.fee) return "Free";
  return money(m.fee);
}

/** Spent, received and net per season from our moves (paid moves only carry money). */
export function seasonMoney(moves) {
  const out = new Map();
  for (const m of moves) {
    const o = out.get(m.season) || { spent: 0, received: 0, nIn: 0, nOut: 0, grads: 0 };
    if (m.type === "graduation") o.grads++;
    else if (m.direction === "in") { o.nIn++; o.spent += m.fee || 0; }
    else if (m.direction === "out") { o.nOut++; o.received += m.fee || 0; }
    out.set(m.season, o);
  }
  for (const o of out.values()) o.net = o.received - o.spent;
  return out;
}

/** A signed sum: +£3.2M for money in, −£1.1M for money out. */
export const netText = (v) => (v == null ? DASH : v === 0 ? "£0" : `${v > 0 ? "+" : "−"}${money(Math.abs(v))}`);

/** A player's name that opens him. */
export const playerLink = (tid, name) => el("a.plink", {
  href: "#", text: name, onclick: (e) => { e.preventDefault(); e.stopPropagation(); openPlayer(tid); },
});

/** A club's name — a link to its sheet when the app already holds the club (our division
 *  ladder), plain text otherwise, so a foreign club doesn't pull every player in the save. */
export function clubLink(tid, name) {
  if (tid == null) return el("span.dim", { text: name || "Free agent" });
  if (!D.S.clubs.has(tid)) return document.createTextNode(name || `#${tid}`);
  return el("a.plink", {
    href: "#", text: name, onclick: (e) => { e.preventDefault(); e.stopPropagation(); openClub(tid); },
  });
}

const kpi = (label, value, sub = null) => el("div.kpi", {}, [
  el("b", { text: String(value) }), el("span", { text: label }), sub ? el("small", { text: sub }) : null,
]);

/** A deals table: player, age, from, to, fee. */
function dealsTable(deals, { rank = true } = {}) {
  if (!deals.length) return el("p.note", { text: "No paid moves." });
  return el("div.scroll", {}, [el("table.book", {}, [
    el("thead", {}, [el("tr", {}, [...(rank ? [["#", 1]] : []), ["Player", 0], ["Age", 1], ["From", 0], ["To", 0], ["Fee", 1]]
      .map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, deals.map((d, i) => el("tr", {}, [
      ...(rank ? [el("td.num.dim", { text: i + 1 })] : []),
      el("td.name", {}, [playerLink(d.tid, d.name)]),
      el("td.num", { text: d.age ?? DASH }),
      el("td", {}, [clubLink(d.from_tid, d.from_club), d.from_nation ? el("span.dim", { text: ` · ${d.from_nation}` }) : null]),
      el("td", {}, [clubLink(d.to_tid, d.to_club), d.to_nation ? el("span.dim", { text: ` · ${d.to_nation}` }) : null]),
      el("td.num.hl", { text: feeText(d) }),
    ]))),
  ])]);
}

const LS_SEASON = "fm:world:transfer-season";
const LS_VIEW = "fm:world:transfer-view";
const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

/**
 * World › Transfers: one season's market — four tiles, then ONE table at a time, picked like
 * the Matches page's tabs: the biggest deals (the world's or our nation's), the clubs that
 * spent or sold most, the market by league nation, and the records (the biggest deal each
 * season and the world record as it stood).
 */
export async function worldTransfersPanel() {
  const T = await D.loadTransfers();
  if (!T) return el("p.note", { text: "No transfer data in this export." });
  const seasons = Object.keys(T.markets).map(Number).sort((a, b) => b - a);
  const box = el("div");
  let cur = Number(lsGet(LS_SEASON));
  if (!seasons.includes(cur)) cur = seasons[0];
  const career0 = seasons[seasons.length - 1];
  const home = T.home_nation || "Our nation";
  const VIEWS = [["deals", "Deals"], ["clubs", "Clubs"], ["nations", "Nations"], ["records", "Records"]];
  let view = VIEWS.some(([k]) => k === lsGet(LS_VIEW)) ? lsGet(LS_VIEW) : "deals";
  let scope = "world";              // deals: the world's, or our nation's
  let side = "spenders";            // clubs: who spent most, or who sold most
  let allTop = false;

  const deal = (rows) => rowsOf(T.deal_fields, rows);
  const chips = (opts, on, set) => el("span.mseg", {}, opts.map(([k, l]) => el(`button.chip${k === on ? ".on" : ""}`, {
    text: l, onclick: () => { set(k); draw(); },
  })));
  const tbl = (head, body) => el("div.scroll", {}, [el("table.book", {}, [
    el("thead", {}, [el("tr", {}, head.map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, body),
  ])]);

  function deals(m) {
    const rows = scope === "world" ? deal(m.top) : deal(m.home_top);
    const shown = allTop ? rows : rows.slice(0, 10);
    return [
      el("div.prow", {}, [chips([["world", "World"], ["home", home]], scope, (k) => { scope = k; allTop = false; })]),
      dealsTable(shown),
      rows.length > 10 ? el("button.link", { text: allTop ? "Show the top 10" : `Show all ${rows.length}`,
        onclick: () => { allTop = !allTop; draw(); } }) : null,
    ];
  }

  function clubs(m) {
    const rows = rowsOf(T.spender_fields, side === "spenders" ? m.spenders : m.sellers);
    return [
      el("div.prow", {}, [chips([["spenders", "Biggest spenders"], ["sellers", "Biggest sellers"]], side, (k) => { side = k; })]),
      tbl([["Club", 0], [side === "spenders" ? "Spent" : "Received", 1], ["Paid moves", 1]], rows.map((c) => el("tr", {}, [
        el("td.name", {}, [clubLink(c.club_tid, c.club)]), el("td.num.hl", { text: money(c.fee) }),
        el("td.num", { text: c.paid_moves }),
      ]))),
    ];
  }

  function nations(m) {
    const rows = rowsOf(T.nation_fields, m.nations);
    return [tbl([["Nation", 0], ["Spent", 1], ["Received", 1], ["Net", 1]], rows.map((n) => {
      const net = (n.received || 0) - (n.spent || 0);
      return el(`tr${n.nation === home ? ".picked" : ""}`, {}, [
        el("td.name", { text: n.nation }), el("td.num", { text: n.spent ? money(n.spent) : DASH }),
        el("td.num", { text: n.received ? money(n.received) : DASH }),
        el(`td.num${net > 0 ? ".gain" : net < 0 ? ".loss" : ""}`, { text: netText(net) }),
      ]);
    })), el("p.note", { text: "Spent by the league nation's clubs, received for their players; the 12 biggest markets." })];
  }

  function records() {
    const head = [["Season", 0], ["Player", 0], ["Age", 1], ["From", 0], ["To", 0], ["Fee", 1]];
    const row = (d, cls, first) => el(`tr${cls}`, {}, [
      el("td.name", {}, [seasonLabel(d.season), first ? pill("record", "good") : null]),
      el("td", {}, [playerLink(d.tid, d.name)]), el("td.num", { text: d.age ?? DASH }),
      el("td", {}, [clubLink(d.from_tid, d.from_club)]), el("td", {}, [clubLink(d.to_tid, d.to_club)]),
      el("td.num.hl", { text: money(d.fee) }),
    ]);
    const best = seasons.map((y) => deal(T.markets[String(y)].top)[0]).filter(Boolean);
    const progression = deal(T.records).slice().reverse();
    return [
      el("h3", { text: "Biggest deal each season" }),
      tbl(head, best.map((d) => row(d, d.season === cur ? ".picked" : "", false))),
      el("h3", { text: "World record progression" }),
      tbl(head, progression.map((d, i) => row(d, d.season < career0 ? ".pre" : "", i === 0))),
      el("p.note", { text: "Each paid move that beat every fee before it. Seasons before "
        + `${seasonLabel(career0)} come from the history the save keeps for players still in it, `
        + "so the early record is only as complete as that." }),
    ];
  }

  function draw() {
    const m = T.markets[String(cur)];
    const record = deal(m.top)[0];
    const windows = rowsOf(T.window_fields, m.windows).filter((w) => w.window !== "undated" && w.total);
    const PANELS = { deals, clubs, nations, records };
    box.replaceChildren(...[
      el("div.prow", {}, [chips(seasons.map((y) => [y, seasonLabel(y)]), cur, (y) => {
        cur = y; allTop = false; lsSet(LS_SEASON, String(y));
      })]),
      el("div.kpis", {}, [
        kpi("Spent on fees", money(m.total), windows.map((w) => `${w.window} ${money(w.total)}`).join(" · ") || null),
        kpi("Paid moves", num(m.paid), `${num(m.free)} free`),
        kpi("£10M+ deals", num(m.over_10m)),
        record ? kpi("Biggest deal", money(record.fee), `${record.name} · ${record.from_club} → ${record.to_club}`) : null,
      ]),
      el("div.prow.mtabs", {}, VIEWS.map(([k, l]) => el(`button.chip${k === view ? ".on" : ""}`, {
        text: l, onclick: () => { view = k; lsSet(LS_VIEW, k); draw(); },
      }))),
      ...PANELS[view](m),
      el("p.note", { text: T.note }),
    ].filter(Boolean));
  }
  draw();
  return box;
}
