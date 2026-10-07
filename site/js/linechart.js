/**
 * A multi-series line chart over the snapshot calendar — the World page's "over time" view.
 *
 * The x-axis is the calendar, not the snapshot index, for the same reason as the development
 * chart: snapshots are unevenly spaced (three in one June, none for six months), and an index
 * axis would make a quiet half-season look as long as a busy week. Each series keeps the colour
 * slot it was given (`s.slot`, 0-7), so adding or removing one never repaints the others.
 *
 * Gaps are real: a value of null (a league with too few rated players for a skill index that
 * season) breaks the line rather than being bridged.
 */
import { el, num } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
export const SLOTS = 8;
const PAD_L = 46, PLOT_T = 10;
const t = (iso) => Date.parse(`${iso}T00:00:00Z`);
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-GB",
  { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function svgEl(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}

/** Round-number ticks spanning [lo, hi], about `n` of them. */
function ticks(lo, hi, n) {
  const span = hi - lo || 1;
  const raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/**
 * @param {object} o
 *   dates   ['YYYY-MM-DD'] the x positions, oldest first
 *   series  [{key, label, slot, values: [v|null] (one per date), ours?}]
 *   dp      decimals for readouts
 *   invert  true for a rank (1 drawn at the top)
 *   label   the metric's name, for the aria label and the tooltip
 */
export function lineChart({ dates, series, dp = 0, invert = false, label = "Value" }) {
  const xs = dates.map(t);
  const wrap = el("div.lcwrap");
  if (!series.length) {
    wrap.append(el("div.lcempty", { text: "Pick something to plot — tap a table row, use Quick pick, or add one below." }));
    return wrap;
  }
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  if (!all.length) {
    wrap.append(el("div.lcempty", { text: `No ${label.toLowerCase()} on record for this selection.` }));
    return wrap;
  }
  // Only label line-ends directly when there are few enough lines for the labels to stay apart.
  const direct = series.length <= 4;
  let drawnW = 0;
  const redraw = () => {
    const W = Math.round(wrap.clientWidth);
    if (!W || W === drawnW) return;
    drawnW = W;
    wrap.replaceChildren(...draw(W));
  };
  new ResizeObserver(redraw).observe(wrap);

  function draw(W) {
    const narrow = W < 520;
    const PAD_R = direct ? (narrow ? 76 : 116) : 12;
    const PLOT_H = narrow ? 200 : 260;
    const H = PLOT_T + PLOT_H + 26;
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = (hi - lo || Math.abs(hi) * 0.1 || 1) * 0.08;
    lo -= pad; hi += pad;
    if (invert) lo = Math.max(lo, 0.5);
    const x0 = xs[0], x1 = xs[xs.length - 1];
    const X = (ms) => PAD_L + ((ms - x0) / (x1 - x0 || 1)) * (W - PAD_L - PAD_R);
    const Y = (v) => (invert
      ? PLOT_T + ((v - lo) / (hi - lo)) * PLOT_H
      : PLOT_T + PLOT_H - ((v - lo) / (hi - lo)) * PLOT_H);

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "lchart",
      role: "img", "aria-label": `${label} over time: ${series.map((s) => s.label).join(", ")}` });

    for (const v of ticks(lo, hi, narrow ? 4 : 5)) {
      if (invert && !Number.isInteger(v)) continue;
      svg.append(svgEl("line", { x1: PAD_L, x2: W - PAD_R, y1: Y(v), y2: Y(v), class: "grid" }),
        svgEl("text", { x: PAD_L - 6, y: Y(v) + 3.5, class: "ylab", "text-anchor": "end" },
          invert ? `#${v}` : num(v, Math.abs(hi - lo) < 5 ? 1 : 0)));
    }
    // season lines at 1 July, labelled with the season they open
    const y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear();
    const every = narrow && y1 - y0 > 6 ? 2 : 1;
    for (let y = y0; y <= y1; y++) {
      const ms = Date.UTC(y, 6, 1);
      if (ms < x0 || ms > x1) continue;
      svg.append(svgEl("line", { x1: X(ms), x2: X(ms), y1: PLOT_T, y2: PLOT_T + PLOT_H, class: "tick" }));
      if ((y - y0) % every === 0) {
        svg.append(svgEl("text", { x: X(ms), y: PLOT_T + PLOT_H + 16, class: "xlab", "text-anchor": "middle" },
          `${String(y).slice(2)}/${String(y + 1).slice(2)}`));
      }
    }
    svg.append(svgEl("line", { x1: PAD_L, x2: W - PAD_R, y1: PLOT_T + PLOT_H, y2: PLOT_T + PLOT_H, class: "base" }));

    // lines: ours drawn last so it sits on top
    const order = [...series].sort((a, b) => (a.ours ? 1 : 0) - (b.ours ? 1 : 0));
    for (const s of order) {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        d += `${pen ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`;
        pen = true;
      });
      svg.append(svgEl("path", { d, class: `ln s${s.slot}${s.ours ? " ours" : ""}` }));
      // isolated points (a value with a gap either side) would otherwise be invisible
      s.values.forEach((v, i) => {
        if (v != null && s.values[i - 1] == null && s.values[i + 1] == null) {
          svg.append(svgEl("circle", { cx: X(xs[i]), cy: Y(v), r: 2.5, class: `dot s${s.slot}` }));
        }
      });
    }

    // direct labels at each line's last value, nudged apart vertically
    if (direct) {
      const ends = series.map((s) => {
        let i = s.values.length - 1;
        while (i >= 0 && s.values[i] == null) i--;
        return i < 0 ? null : { s, i, y: Y(s.values[i]) };
      }).filter(Boolean).sort((a, b) => a.y - b.y);
      for (let k = 1; k < ends.length; k++) ends[k].y = Math.max(ends[k].y, ends[k - 1].y + 13);
      const over = ends.length ? ends[ends.length - 1].y - (PLOT_T + PLOT_H) : 0;
      if (over > 0) ends.forEach((e) => { e.y -= over; });
      const room = Math.floor((PAD_R - 14) / 6);
      for (const e of ends) {
        const txt = e.s.label.length > room ? `${e.s.label.slice(0, room - 1)}…` : e.s.label;
        svg.append(svgEl("circle", { cx: X(xs[e.i]), cy: Y(e.s.values[e.i]), r: 3, class: `dot s${e.s.slot}` }),
          svgEl("text", { x: W - PAD_R + 8, y: e.y + 3.5, class: "endlab" }, txt));
      }
    }

    // hover: crosshair on the nearest snapshot, every series' value there in one readout
    const cross = svgEl("line", { y1: PLOT_T, y2: PLOT_T + PLOT_H, class: "cross", visibility: "hidden" });
    const hots = svgEl("g", { visibility: "hidden" });
    const hit = svgEl("rect", { x: PAD_L, y: 0, width: W - PAD_L - PAD_R, height: PLOT_T + PLOT_H, class: "hit" });
    svg.append(cross, hots, hit);
    const tip = el("div.lctip");
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const vx = ((e.clientX - r.left) / r.width) * W;
      let i = 0;
      xs.forEach((ms, k) => { if (Math.abs(X(ms) - vx) < Math.abs(X(xs[i]) - vx)) i = k; });
      cross.setAttribute("x1", X(xs[i])); cross.setAttribute("x2", X(xs[i]));
      cross.setAttribute("visibility", "visible");
      hots.replaceChildren(...series.filter((s) => s.values[i] != null).map((s) =>
        svgEl("circle", { cx: X(xs[i]), cy: Y(s.values[i]), r: 4, class: `hot s${s.slot}` })));
      hots.setAttribute("visibility", "visible");
      const rows = series.map((s) => ({ s, v: s.values[i] }))
        .sort((a, b) => (a.v == null) - (b.v == null) || (invert ? a.v - b.v : b.v - a.v));
      tip.replaceChildren(el("b", { text: fmtDate(xs[i]) }), ...rows.map(({ s, v }) => el("div.lcrow", {}, [
        el(`i.sw.s${s.slot}`), el("span", { text: s.label }),
        el("span.v", { text: v == null ? "—" : invert ? `#${v}` : num(v, dp) }),
      ])));
      tip.style.display = "block";
      const px = (X(xs[i]) / W) * r.width;
      const tw = tip.offsetWidth;
      // beside the crosshair, on whichever side has room
      tip.style.left = `${px + 12 + tw <= r.width ? px + 12 : Math.max(4, px - tw - 12)}px`;
    });
    hit.addEventListener("pointerleave", () => {
      tip.style.display = "none";
      cross.setAttribute("visibility", "hidden"); hots.setAttribute("visibility", "hidden");
    });
    return [svg, tip];
  }
  return wrap;
}
