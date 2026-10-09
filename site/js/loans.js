/**
 * Loan outlook — the profile sheet's answer to "where would he actually play?".
 *
 * AI managers pick their XI mostly on ability, so the ordering here is ability throughout, and
 * it arrives pre-rendered in api/loans.json (percentiles and ranks only — the number behind
 * them never leaves the build machine). One strip per division, from ours down to the third
 * below: every tick is one club's STARTER LINE at the position — the Level %ile of the weakest
 * player it would start there in its manager's preferred formation — and the dot is him. A
 * tick left of the dot is a club he'd walk into; clubs whose shape has no slot for the position
 * (a winger at a 5-3-2 club) have no tick at all.
 */
import * as D from "./data.js";
import { el, clear, pill, clubName, DASH } from "./ui.js";

const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
const starts = (c) => c.rank <= c.slots;

/** Unpack one position's rows into {cid, name, lvl, n, clubs[{tid,rank,slots,line}]}. */
function divisions(L, rows) {
  return rows.map(([cid, lvl, n, clubs], tier) => ({
    cid, tier, lvl, n,
    name: L.ladder.find((l) => l.cid === cid)?.name || D.S.leagues.get(cid)?.name || `#${cid}`,
    clubs: clubs.map(([tid, rank, slots, line]) => ({ tid, rank, slots, line })),
  }));
}

/** The highest division with at least one club he'd start for — the loan to aim at. */
const bestDivision = (divs) => divs.find((d) => d.clubs.some(starts)) || null;

function strip(d, { picked, best, onPick }) {
  const n = d.clubs.length, k = d.clubs.filter(starts).length;
  const track = el("div.ltrack", {}, [
    ...d.clubs.map((c) => el(`span.ltick${starts(c) ? ".on" : ""}`, {
      style: `left:${c.line ?? 0}%`,
      title: `${D.S.clubs.get(c.tid)?.name || `#${c.tid}`} — ${c.line == null ? "open slot" : `starter line ${c.line}`}`,
    })),
    d.lvl == null ? null : el("span.ldot", { style: `left:${d.lvl}%`, title: `His Level %ile here: ${d.lvl}` }),
  ]);
  return el(`div.lrow${picked ? ".on" : ""}${best ? ".best" : ""}`, { onclick: onPick, role: "button", tabindex: "0" }, [
    el("div.lname", {}, [el("b", { text: d.name }), el("span.dim", { text: d.tier === 0 ? "our division" : `${d.tier} below` })]),
    n ? track : el("div.ltrack.none", { text: "no club here plays this position" }),
    el("div.lstat", {}, [
      el("b", { text: n ? `${k}/${n}` : DASH }),
      el("span.dim", { text: d.lvl == null ? "" : `${d.lvl} %ile` }),
    ]),
  ]);
}

function clubTable(d, loanedTo, pos) {
  if (!d.clubs.length) return el("p.note", { text: `No club in ${d.name} lines up with a ${pos}.` });
  const rows = [...d.clubs].sort((a, b) =>
    (starts(b) - starts(a))
    || (starts(a) ? (b.line ?? 101) - (a.line ?? 101) : a.rank - b.rank)
    || a.tid - b.tid);
  return el("div.scroll.fit", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Club", "Shape", "His place", "Starter line", ""]
      .map((h, i) => el(`th${i === 3 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, rows.map((c) => {
      const verdict = c.line == null ? pill("Open slot", "good") : starts(c) ? pill("Starts", "good")
        : c.rank === c.slots + 1 ? pill("Next in", "warn") : pill("Bench", "flat");
      const shape = D.S.loans.formations[String(c.tid)];
      return el(`tr${c.tid === loanedTo ? ".picked" : ""}`, {}, [
        el("td.name", {}, [clubName(c.tid, D.S), c.tid === loanedTo ? " · on loan here" : null]),
        el("td", { text: shape || `${D.S.loans.fallback_formation}?`,
          title: shape ? "The manager's preferred formation" : "Manager's formation unknown — read as the most common shape" }),
        el("td", { text: `${ordinal(c.rank)} choice · ${c.slots} start` }),
        el("td.num", { text: c.line == null ? DASH : String(c.line),
          title: c.line == null ? "No natural player for this slot at the club" : null }),
        el("td", {}, [verdict]),
      ]);
    })),
  ])]);
}

/**
 * The profile sheet's Loan tab for one owned player. Renders a placeholder and fills in once
 * loans.json arrives; says so when the export has nothing for him. The club list opens when a
 * division is tapped — the strips answer the question, the list is the detail.
 * @param {object} p      the player
 * @param {string} [pos]  position to open on (the one the sheet is showing), if he has it
 */
export function loanOutlook(p, pos) {
  const box = el("div", {}, [el("p.note", { text: "Loading…" })]);
  D.loadLoans().then((L) => {
    const mine = L?.players?.[String(p.tid)];
    clear(box);
    if (!mine || !Object.keys(mine.positions).length) {
      box.append(el("p.note", { text: L?.error
        ? `Loan outlook unavailable: ${L.error}.`
        : "No position he's natural at (familiarity 15+), so there's nothing to place him by." }));
      return;
    }
    const positions = Object.keys(mine.positions);
    let cur = positions.includes(pos) ? pos : positions[0];
    let pickedCid = null;
    const chips = el("div.prow");
    const body = el("div");

    function render() {
      const divs = divisions(L, mine.positions[cur]);
      const best = bestDivision(divs);
      const picked = divs.find((d) => d.cid === pickedCid) || null;
      clear(chips).append(el("span.dim", { text: "At:" }), ...positions.map((q) =>
        el(`button.chip${q === cur ? ".on" : ""}`, { text: q, onclick: () => { cur = q; pickedCid = null; render(); } })));
      const loanedTo = mine.loaned_to;
      // Native append() writes a null argument as the text "null" — drop the absent parts.
      clear(body).append(...[
        el("p.lhead", { html: (loanedTo
          ? `On loan at <b>${D.S.clubs.get(loanedTo)?.name || `#${loanedTo}`}</b>. ` : "")
          + (best
            ? `Highest level he'd start at ${cur}: <b>${best.name}</b> — ${best.clubs.filter(starts).length} of ${best.clubs.length} clubs.`
            : `He wouldn't start at ${cur} for any club down to ${divs[divs.length - 1].name} — a reserves player.`) }),
        el("div.lstrips", {}, divs.map((d) => strip(d, {
          picked: d === picked, best: d === best, onPick: () => { pickedCid = pickedCid === d.cid ? null : d.cid; render(); },
        }))),
        el("div.llegend.dim", {}, [el("span.ldot.key"), " him  ", el("span.ltick.on.key"), " a club he'd start for  ",
          el("span.ltick.key"), " one he wouldn't — tap a division for its clubs"]),
        picked ? el("h4", { text: `${picked.name} · ${cur}` }) : null,
        picked ? clubTable(picked, loanedTo, cur) : null,
      ].filter(Boolean));
    }
    render();
    box.append(chips, body, el("details.info", {}, [el("summary", { text: "ⓘ How to read this" }), el("p.note", {
      html: "The AI picks its XI mostly on ability, so this ranks on it. The dot is his "
        + "<b>Level %ile</b> at the position in that division. Each tick is a club's "
        + "<b>starter line</b>: the Level %ile of the weakest player it would start there, with "
        + "the number of starters taken from its manager's preferred formation — so a winger "
        + "has no tick at a 5-3-2 club. A club with no natural player for a slot is an open "
        + "door: its tick sits at 0 and he walks in. Morale, form and match fitness aren't in it.",
    })]));
  });
  return box;
}
