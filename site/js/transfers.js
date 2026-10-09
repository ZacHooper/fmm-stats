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

/**
 * World › Transfers: one season's market (the season review's blocks — totals, windows, the
 * biggest deals, who spent and who sold, by league nation, our nation's market) and the world
 * record as it stood, season by season.
 */
export async function worldTransfersPanel() {
  const T = await D.loadTransfers();
  if (!T) return el("p.note", { text: "No transfer data in this export." });
  const seasons = Object.keys(T.markets).map(Number).sort((a, b) => b - a);
  const box = el("div");
  let cur = Number((() => { try { return localStorage.getItem(LS_SEASON); } catch { return null; } })());
  if (!seasons.includes(cur)) cur = seasons[0];
  const career0 = seasons[seasons.length - 1];

  let allTop = false;
  function draw() {
    const m = T.markets[String(cur)];
    const deal = (rows) => rowsOf(T.deal_fields, rows);
    const top = deal(m.top);
    const club = (rows) => rowsOf(T.spender_fields, rows);
    const tbl = (head, body) => el("div.scroll", {}, [el("table.book", {}, [
      el("thead", {}, [el("tr", {}, head.map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, body),
    ])]);
    const clubTable = (rows, label) => tbl([[label, 0], ["Fee", 1], ["Paid moves", 1]], club(rows).map((c) => el("tr", {}, [
      el("td.name", {}, [clubLink(c.club_tid, c.club)]), el("td.num.hl", { text: money(c.fee) }), el("td.num", { text: c.paid_moves }),
    ])));
    const nations = rowsOf(T.nation_fields, m.nations);
    const windows = rowsOf(T.window_fields, m.windows);
    const record = top[0];
    const progression = rowsOf(T.deal_fields, T.records).slice().reverse();
    box.replaceChildren(
      el("div.prow", {}, [el("span.mseg", {}, seasons.map((y) => el(`button.chip${y === cur ? ".on" : ""}`, {
        text: seasonLabel(y),
        onclick: () => { cur = y; allTop = false; try { localStorage.setItem(LS_SEASON, String(y)); } catch { /* ignore */ } draw(); },
      })))]),
      el("div.kpis", {}, [
        kpi("Spent on fees", money(m.total)),
        kpi("Paid moves", num(m.paid), `${num(m.free)} free`),
        kpi("£10M+ deals", num(m.over_10m)),
        record ? kpi("Biggest deal", money(record.fee), `${record.name} · ${record.from_club} → ${record.to_club}`) : null,
        ...windows.filter((w) => w.window !== "undated").map((w) => kpi(`${w.window[0].toUpperCase()}${w.window.slice(1)} window`, money(w.total), `${num(w.paid)} paid`)),
      ]),
      el("h3", { text: `Biggest deals · ${seasonLabel(cur)}` }),
      dealsTable(allTop ? top : top.slice(0, 10)),
      top.length > 10 ? el("button.link", { text: allTop ? "Show the top 10" : `Show all ${top.length}`,
        onclick: () => { allTop = !allTop; draw(); } }) : null,
      el("div.grid2", {}, [
        el("div", {}, [el("h3", { text: "Biggest spenders" }), clubTable(m.spenders, "Club")]),
        el("div", {}, [el("h3", { text: "Biggest sellers" }), clubTable(m.sellers, "Club")]),
      ]),
      el("h3", { text: "By league nation" }),
      tbl([["Nation", 0], ["Spent", 1], ["Received", 1], ["Net", 1]], nations.map((n) => el("tr", {}, [
        el("td.name", { text: n.nation }), el("td.num", { text: n.spent ? money(n.spent) : DASH }),
        el("td.num", { text: n.received ? money(n.received) : DASH }),
        el("td.num", { text: netText((n.received || 0) - (n.spent || 0)) }),
      ]))),
      el("h3", { text: `${T.home_nation || "Our nation"}: biggest deals in or out` }),
      dealsTable(deal(m.home_top)),
      el("h3", { text: "Biggest deal each season" }),
      el("div.scroll", {}, [el("table.book", {}, [
        el("thead", {}, [el("tr", {}, [["Season", 0], ["Player", 0], ["Age", 1], ["From", 0], ["To", 0], ["Fee", 1]]
          .map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, seasons.map((y) => [y, rowsOf(T.deal_fields, T.markets[String(y)].top)[0]]).filter(([, d]) => d)
          .map(([y, d]) => el(`tr${y === cur ? ".picked" : ""}`, {}, [
            el("td.name", { text: seasonLabel(y) }), el("td", {}, [playerLink(d.tid, d.name)]),
            el("td.num", { text: d.age ?? DASH }), el("td", {}, [clubLink(d.from_tid, d.from_club)]),
            el("td", {}, [clubLink(d.to_tid, d.to_club)]), el("td.num.hl", { text: money(d.fee) }),
          ]))),
      ])]),
      el("h3", { text: "World record progression" }),
      el("p.note", { text: "Each paid move that beat every fee before it. Seasons before "
        + `${seasonLabel(career0)} come from the history the save keeps for players still in it, `
        + "so the early record is only as complete as that." }),
      el("div.scroll", {}, [el("table.book", {}, [
        el("thead", {}, [el("tr", {}, [["Season", 0], ["Player", 0], ["Age", 1], ["From", 0], ["To", 0], ["Fee", 1]]
          .map(([h, n]) => el(`th${n ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, progression.map((d, i) => el(`tr${d.season < career0 ? ".pre" : ""}`, {}, [
          el("td.name", {}, [seasonLabel(d.season), i === 0 ? pill("record", "good") : null]),
          el("td", {}, [playerLink(d.tid, d.name)]), el("td.num", { text: d.age ?? DASH }),
          el("td", {}, [clubLink(d.from_tid, d.from_club)]), el("td", {}, [clubLink(d.to_tid, d.to_club)]),
          el("td.num.hl", { text: money(d.fee) }),
        ]))),
      ])]),
      el("p.note", { text: T.note }),
    );
  }
  draw();
  return box;
}
