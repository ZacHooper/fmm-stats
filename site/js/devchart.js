/**
 * Development chart — a player's role rating over real time, with where he was underneath it.
 *
 * The x-axis is the calendar, not the snapshot index: snapshots are unevenly spaced, and the
 * point of the chart is to line the curve up against what happened — a loan, an injury, the
 * day he signed. Under the plot run two lanes from squad.json's spells: the club he was at
 * (ours, our reserves, out on loan, somewhere else) and injuries. Moves that involve our clubs
 * are marked on the plot itself. Hovering reads out the date, the rating and where he was.
 */
import * as D from "./data.js";
import { el, num, money } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const DAY = 86400000;
const PAD_L = 52, PAD_R = 12, PLOT_T = 22;
const LANE_H = 14, LANE_GAP = 5;

const t = (iso) => Date.parse(`${iso}T00:00:00Z`);
const seasonOf = (iso) => (+iso.slice(5, 7) >= 7 ? +iso.slice(0, 4) + 1 : +iso.slice(0, 4));
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const clubName = (tid) => (tid == null ? null : D.S.clubs.get(tid)?.name || `#${tid}`);
// Generic words in Danish (and English) club names, dropped for the lane labels so a short bar
// still says which club it is: "Boldklubben Fremad Amager" -> "Fremad Amager".
const GENERIC = /\b(football|fodbold|club|boldklubben|boldklub|idrætsforening|idræts|klub|forening|og|&|if|fc|bk|af)\b/gi;
const shortName = (name) => {
  if (!name) return name;
  const s = name.replace(GENERIC, " ").replace(/\s+/g, " ").trim();
  return s.length >= 3 ? s : name;
};

function svgEl(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}

/** Spells for the lanes, with each loan's host club filled in from career history (the spell
 *  itself doesn't carry it: the save's weekly loan flag says THAT he's away, the career-history
 *  row for that season says WHERE). */
function lanes(tid) {
  const sq = D.S.squad || {};
  const rows = sq.spells?.[String(tid)] || [];
  const career = sq.career_history?.[String(tid)] || [];
  const ix = D.S.index.career;
  const kind = (s) => {
    if (s.type === "loan_out") return "loan";
    if (s.type === "loan_in") return "loanin";
    if (s.club === ix.managed_tid) return "us";
    if (s.club === ix.reserve_tid) return "res";
    return "other";
  };
  const spells = rows.map(([type, club, from, to]) => ({ type, club, from, to }));
  for (const s of spells) {
    if (s.type !== "loan_out") continue;
    const host = career.filter((c) => c.fee === "loan" && c.end_year === seasonOf(s.from));
    s.host = host.length ? host[host.length - 1].club : null;
  }
  return {
    club: spells.filter((s) => s.type !== "injured").map((s) => ({ ...s, kind: kind(s) })),
    injury: spells.filter((s) => s.type === "injured"),
  };
}

const kindLabel = (k) => ({ us: D.S.index.career.name, res: "Our reserves", loan: "Out on loan",
  loanin: "On loan with us", other: "Another club" })[k];

/** The short form drawn inside a lane bar; the full label is in its tooltip. */
function barLabel(s) {
  if (s.kind === "loan") return s.host ? shortName(s.host) : "On loan";
  if (s.kind === "us") return D.S.index.career.name;
  if (s.kind === "res") return "Reserves";
  return shortName(clubName(s.club)) || "Another club";
}

function spellLabel(s) {
  if (s.kind === "loan") return s.host ? `On loan · ${s.host}` : "Out on loan";
  if (s.kind === "loanin") return `On loan from ${clubName(s.club) || "another club"}`;
  if (s.kind === "us") return D.S.index.career.name;
  if (s.kind === "res") return `${D.S.index.career.name} reserves`;
  return clubName(s.club) || "Another club";
}

/** Moves worth a marker: anything into or out of our clubs. */
function markers(tid) {
  const ix = D.S.index.career;
  const ours = new Set([ix.managed_tid, ix.reserve_tid]);
  return (D.S.squad?.moves?.[String(tid)] || [])
    .map(([date, from, to, type, feeType, fee]) => ({ date, from, to, type, feeType, fee }))
    .filter((m) => ours.has(m.to) || ours.has(m.from))
    .map((m) => {
      let label;
      if (m.type === "internal") label = m.to === ix.managed_tid ? "Promoted" : "To reserves";
      else if (ours.has(m.to)) label = m.feeType === "fee" && m.fee ? `Signed · ${money(m.fee)}` : "Signed · free";
      else if (m.type === "released") label = "Released";
      else label = m.feeType === "fee" && m.fee ? `Sold · ${money(m.fee)}` : `Left · ${clubName(m.to) || ""}`.trim();
      const detail = `${fmtDate(t(m.date))} — ${label}`
        + (m.type !== "internal" ? ` (${clubName(m.from) || "?"} → ${clubName(m.to) || "?"})` : "");
      return { ms: t(m.date), label, detail };
    });
}

/**
 * @param {object} p           the player
 * @param {Array}  traj        D.trajectory(tid, role) — [{season, phase, value}], oldest first
 * @param {object} [forecast]  {points, band, lastAge} at ages 21/24, as the profile computes it
 */
export function devChart(p, traj, forecast = null) {
  const pts = traj.filter((x) => /^\d{4}-\d{2}-\d{2}$/.test(x.phase) && x.value != null)
    .map((x) => ({ ms: t(x.phase), v: x.value }));
  if (pts.length < 2) return null;
  const { club, injury } = lanes(p.tid);
  const marks = markers(p.tid);

  // forecast points sit on the dates he reaches each horizon age
  const fc = [];
  if (forecast && p.dob) {
    const horizons = [21, 24].slice(-forecast.points.length);
    horizons.forEach((age, i) => {
      const d = new Date(t(p.dob)); d.setUTCFullYear(d.getUTCFullYear() + age);
      if (+d > pts[pts.length - 1].ms) fc.push({ ms: +d, v: forecast.points[i], band: forecast.band[i] });
    });
  }

  const x0 = pts[0].ms, x1 = Math.max(pts[pts.length - 1].ms, ...fc.map((f) => f.ms));
  // an ongoing spell ends at the latest snapshot — "now" — not at the end of the projection
  const now = pts[pts.length - 1].ms;
  const clip = (s) => ({ a: Math.max(t(s.from), x0), b: Math.min(s.to ? t(s.to) + DAY : now, x1) });
  const hasInj = injury.some((s) => clip(s).b > clip(s).a);
  // Drawn at the container's real pixel width (and redrawn when it changes) rather than
  // scaled from a fixed viewBox, so text stays the same size on a phone and a desktop.
  const wrap = el("div.devwrap");
  let drawnW = 0;
  const redraw = () => {
    const W = Math.round(wrap.clientWidth);
    if (!W || W === drawnW) return;
    drawnW = W;
    wrap.replaceChildren(...draw(W));
  };
  new ResizeObserver(redraw).observe(wrap);

  function draw(W) {
    const PLOT_H = W < 500 ? 100 : 130;
    const vals = [...pts.map((q) => q.v), ...fc.flatMap((f) => [f.v, ...(f.band || [])])];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const padV = (hi - lo || 10) * 0.12; lo -= padV; hi += padV;
    const X = (ms) => PAD_L + ((ms - x0) / (x1 - x0 || 1)) * (W - PAD_L - PAD_R);
    const Y = (v) => PLOT_T + PLOT_H - ((v - lo) / (hi - lo)) * PLOT_H;

    const laneY1 = PLOT_T + PLOT_H + 16;
    const laneY2 = laneY1 + LANE_H + LANE_GAP;
    const axisY = (hasInj ? laneY2 + LANE_H : laneY1 + LANE_H) + 4;
    const H = axisY + 16;

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "devchart", role: "img",
      "aria-label": `${p.name}: rating over time with club, loan and injury spells` });

    // recessive grid: min / max rating lines with labels
    for (const v of [Math.min(...pts.map((q) => q.v)), Math.max(...pts.map((q) => q.v))]) {
      svg.append(svgEl("line", { x1: PAD_L, x2: W - PAD_R, y1: Y(v), y2: Y(v), class: "grid" }),
        svgEl("text", { x: PAD_L - 6, y: Y(v) + 4, class: "ylab", "text-anchor": "end" }, num(v)));
    }
    // year ticks at 1 July, the season line
    for (let y = new Date(x0).getUTCFullYear(); y <= new Date(x1).getUTCFullYear() + 1; y++) {
      const ms = Date.UTC(y, 6, 1);
      if (ms < x0 || ms > x1) continue;
      svg.append(svgEl("line", { x1: X(ms), x2: X(ms), y1: PLOT_T, y2: axisY - 2, class: "tick" }),
        svgEl("text", { x: X(ms), y: axisY + 10, class: "xlab", "text-anchor": "middle" }, `${String(y).slice(2)}/${String(y + 1).slice(2)}`));
    }

    // moves: a dashed rule through the plot, labelled along the top
    for (const m of marks) {
      if (m.ms < x0 || m.ms > x1) continue;
      const g = svgEl("g", { class: "move" });
      g.append(svgEl("line", { x1: X(m.ms), x2: X(m.ms), y1: PLOT_T - 4, y2: laneY1 + LANE_H }),
        svgEl("text", { x: Math.min(Math.max(X(m.ms), PAD_L + 30), W - PAD_R - 30), y: PLOT_T - 8, "text-anchor": "middle" }, m.label),
        svgEl("title", {}, m.detail));
      svg.append(g);
    }

    // projection: band + dashed line from the last real point
    if (fc.length) {
      const last = pts[pts.length - 1];
      const up = fc.map((f) => `${X(f.ms).toFixed(1)},${Y(f.band[1]).toFixed(1)}`);
      const dn = fc.map((f) => `${X(f.ms).toFixed(1)},${Y(f.band[0]).toFixed(1)}`).reverse();
      svg.append(svgEl("polygon", { points: [`${X(last.ms).toFixed(1)},${Y(last.v).toFixed(1)}`, ...up, ...dn].join(" "), class: "band" }),
        svgEl("path", { d: [last, ...fc].map((q, i) => `${i ? "L" : "M"}${X(q.ms).toFixed(1)},${Y(q.v).toFixed(1)}`).join(" "), class: "fc" }));
    }
    svg.append(svgEl("path", { d: pts.map((q, i) => `${i ? "L" : "M"}${X(q.ms).toFixed(1)},${Y(q.v).toFixed(1)}`).join(" "), class: "line" }));
    for (const q of pts) svg.append(svgEl("circle", { cx: X(q.ms), cy: Y(q.v), r: 2.6, class: "pt" }));

    // lanes: club underneath, loans drawn over the parent-club spell they sit inside
    const laneLabel = (y, text) => svg.append(svgEl("text", { x: PAD_L - 6, y: y + LANE_H - 3, class: "lanelab", "text-anchor": "end" }, text));
    laneLabel(laneY1, "Club");
    const order = { other: 0, res: 1, us: 2, loanin: 3, loan: 4 };
    for (const s of [...club].sort((a, b) => order[a.kind] - order[b.kind])) {
      const { a, b } = clip(s);
      if (b <= a) continue;
      const w = Math.max(2, X(b) - X(a));
      const g = svgEl("g", { class: `seg ${s.kind}` });
      g.append(svgEl("rect", { x: X(a), y: laneY1, width: w, height: LANE_H, rx: 3 }));
      const label = barLabel(s);
      const fits = Math.floor((w - 8) / 6);
      if (fits >= 4) g.append(svgEl("text", { x: X(a) + 4, y: laneY1 + LANE_H - 3.5 }, label.length > fits ? `${label.slice(0, fits - 1)}…` : label));
      g.append(svgEl("title", {}, `${spellLabel(s)}: ${fmtDate(t(s.from))} – ${s.to ? fmtDate(t(s.to)) : "now"}`));
      svg.append(g);
    }
    if (hasInj) {
      laneLabel(laneY2, "Injured");
      for (const s of injury) {
        const { a, b } = clip(s);
        if (b <= a) continue;
        const days = Math.round((t(s.to || s.from) - t(s.from)) / DAY) + 1;
        const g = svgEl("g", { class: "seg inj" });
        g.append(svgEl("rect", { x: X(a), y: laneY2, width: Math.max(3, X(b) - X(a)), height: LANE_H, rx: 3 }),
          svgEl("title", {}, `Injured ${fmtDate(t(s.from))}${s.to && s.to !== s.from ? ` – ${fmtDate(t(s.to))}` : ""} (${days} day${days === 1 ? "" : "s"})`));
        svg.append(g);
      }
    }

    // hover: crosshair on the nearest snapshot, readout of where he was that day
    const cross = svgEl("line", { y1: PLOT_T, y2: axisY - 2, class: "cross", visibility: "hidden" });
    const hot = svgEl("circle", { r: 5, class: "hot", visibility: "hidden" });
    const hit = svgEl("rect", { x: PAD_L, y: 0, width: W - PAD_L - PAD_R, height: axisY, class: "hit" });
    svg.append(cross, hot, hit);
    const tip = el("div.devtip");
    const at = (ms, list) => list.filter((s) => t(s.from) <= ms && (!s.to || ms <= t(s.to) + DAY));
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const vx = ((e.clientX - r.left) / r.width) * W;
      const q = pts.reduce((best, c) => (Math.abs(X(c.ms) - vx) < Math.abs(X(best.ms) - vx) ? c : best), pts[0]);
      cross.setAttribute("x1", X(q.ms)); cross.setAttribute("x2", X(q.ms));
      hot.setAttribute("cx", X(q.ms)); hot.setAttribute("cy", Y(q.v));
      cross.setAttribute("visibility", "visible"); hot.setAttribute("visibility", "visible");
      const where = at(q.ms, club).sort((a, b) => order[b.kind] - order[a.kind])[0];
      const hurt = at(q.ms, injury).length > 0;
      tip.replaceChildren(...[el("b", { text: fmtDate(q.ms) }), el("div", { text: `Rating ${num(q.v)}` }),
        where ? el("div.dim", { text: spellLabel(where) }) : null,
        hurt ? el("div.hurt", { text: "✚ Injured" }) : null].filter(Boolean));
      tip.style.display = "block";
      const left = (X(q.ms) / W) * r.width;
      tip.style.left = `${Math.min(Math.max(left, 70), r.width - 70)}px`;
    });
    hit.addEventListener("pointerleave", () => {
      tip.style.display = "none";
      cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden");
    });
    return [svg, tip];
  }
  const kinds = new Set(club.map((s) => s.kind));
  const legend = el("div.devlegend", {}, [
    el("span", {}, [el("i.ln"), "Rating"]),
    fc.length ? el("span", {}, [el("i.ln.fc"), `Projected to ${forecast.lastAge}`]) : null,
    ...["us", "res", "loan", "loanin", "other"].filter((k) => kinds.has(k))
      .map((k) => el("span", {}, [el(`i.sw.${k}`), kindLabel(k)])),
    hasInj ? el("span", {}, [el("i.sw.inj"), "Injured"]) : null,
    marks.length ? el("span", {}, [el("i.ln.mv"), "Move"]) : null,
  ]);
  return el("div", {}, [wrap, legend]);
}
