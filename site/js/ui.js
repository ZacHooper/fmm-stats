/** Small DOM + formatting helpers. No framework on purpose: the whole point of this app is
 *  that it deploys as files, with no build step and nothing to keep up to date. */

export function el(tag, attrs = {}, children = []) {
  const parts = tag.split(".");
  const e = document.createElement(parts[0] || "div");
  if (parts.length > 1) e.className = parts.slice(1).join(" ");
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = (e.className ? e.className + " " : "") + v;
    else if (k === "html") e.innerHTML = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(e.dataset, v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}
export const frag = (children) => {
  const f = document.createDocumentFragment();
  for (const c of [].concat(children)) if (c) f.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return f;
};
export const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };

export const DASH = "—";
export function num(v, dp = 0) {
  if (v == null || Number.isNaN(v)) return DASH;
  return Number(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
export function money(v) {
  if (v == null) return DASH;
  const a = Math.abs(v);
  if (a >= 1e6) return `£${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e3) return `£${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}K`;
  return `£${v}`;
}
export const monthYear = (iso) => {
  if (!iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(+d) ? String(iso).slice(0, 7)
    : d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
};

/** A proportional bar behind a number — reads faster than the number alone in a dense table. */
export function bar(v, { max = 100, lo = 40, dp = 0 } = {}) {
  if (v == null || Number.isNaN(v)) return el("span.dim", { text: DASH });
  const pct = Math.max(0, Math.min(100, (100 * v) / max));
  return el("span.barcell", {}, [
    el("span", { class: `bar${v < (lo * max) / 100 ? " lo" : ""}`, style: `width:${(pct * 0.34).toFixed(0)}px` }),
    el("span.barnum", { text: num(v, dp) }),
  ]);
}

const PILL = [
  [/^sell/i, "bad"], [/^needs a starter/i, "bad"],
  [/^loan/i, "warn"], [/^surplus/i, "warn"], [/^thin/i, "warn"],
  [/^stocked/i, "warn"], [/^prospect/i, "warn"],
  [/^keep/i, "good"], [/^settled/i, "good"],
];
export function pill(text, cls) {
  const t = String(text ?? "");
  if (!cls) { cls = "flat"; for (const [re, c] of PILL) if (re.test(t)) { cls = c; break; } }
  return el(`span.pill.${cls}`, { text: t });
}

/** Inline SVG sparkline — a trajectory belongs in the row it describes, not on another page. */
export function sparkline(values, { w = 70, h = 18, dot = true } = {}) {
  const vs = values.filter((v) => v != null);
  if (vs.length < 2) return el("span.dim", { text: DASH });
  const lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || 1;
  const pts = vs.map((v, i) => [
    (i / (vs.length - 1)) * (w - 2) + 1,
    h - 1 - ((v - lo) / span) * (h - 2),
  ]);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("width", w); svg.setAttribute("height", h);
  svg.setAttribute("class", "spark");
  const path = document.createElementNS(svg.namespaceURI, "path");
  path.setAttribute("d", pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" "));
  path.setAttribute("class", vs[vs.length - 1] >= vs[0] ? "up" : "down");
  svg.append(path);
  if (dot) {
    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", pts[pts.length - 1][0].toFixed(1));
    c.setAttribute("cy", pts[pts.length - 1][1].toFixed(1));
    c.setAttribute("r", 1.8);
    c.setAttribute("class", vs[vs.length - 1] >= vs[0] ? "up" : "down");
    svg.append(c);
  }
  return svg;
}

/** Grouped radar. `series` = [{label, values:[0..1], cls}] over the same axes. */
export function radar(axes, series, { size = 220 } = {}) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("class", "radar");
  svg.setAttribute("width", size); svg.setAttribute("height", size);
  const cx = size / 2, cy = size / 2, r = size / 2 - 26;
  const ang = (i) => (2 * Math.PI * i) / axes.length - Math.PI / 2;
  const pt = (i, f) => [cx + r * f * Math.cos(ang(i)), cy + r * f * Math.sin(ang(i))];
  for (const f of [0.25, 0.5, 0.75, 1]) {
    const p = document.createElementNS(NS, "polygon");
    p.setAttribute("points", axes.map((_, i) => pt(i, f).map((n) => n.toFixed(1)).join(",")).join(" "));
    p.setAttribute("class", "grid");
    svg.append(p);
  }
  axes.forEach((a, i) => {
    const [x, y] = pt(i, 1.16);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", x.toFixed(1)); t.setAttribute("y", y.toFixed(1));
    t.setAttribute("class", "axis");
    t.setAttribute("text-anchor", x < cx - 4 ? "end" : x > cx + 4 ? "start" : "middle");
    t.setAttribute("dominant-baseline", y < cy ? "auto" : "hanging");
    t.textContent = a;
    svg.append(t);
  });
  series.forEach((s, si) => {
    const p = document.createElementNS(NS, "polygon");
    p.setAttribute("points", s.values.map((v, i) => pt(i, Math.max(0, Math.min(1, v ?? 0))).map((n) => n.toFixed(1)).join(",")).join(" "));
    p.setAttribute("class", `series s${si % 4}`);
    svg.append(p);
  });
  return svg;
}

/** A sheet that slides up on a phone and centres on a desktop — used for player profiles. */
export function sheet(title, body, { wide = false } = {}) {
  const close = () => back.remove();
  const back = el("div.sheetback", { onclick: (e) => { if (e.target === back) close(); } }, [
    el(`div.sheet${wide ? ".wide" : ""}`, {}, [
      el("div.sheethead", {}, [
        el("strong", { text: title }),
        el("button.x", { text: "✕", title: "Close", onclick: close }),
      ]),
      el("div.sheetbody", {}, body),
    ]),
  ]);
  document.body.append(back);
  const esc = (e) => { if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); } };
  document.addEventListener("keydown", esc);
  return back;
}

export function toast(msg, bad = false) {
  const t = el(`div.toast${bad ? ".bad" : ""}`, { text: msg });
  document.body.append(t);
  setTimeout(() => t.classList.add("go"), 10);
  setTimeout(() => t.remove(), 3800);
}

/** Debounce, for the search box: filtering 24k rows on every keystroke is wasted work. */
export function debounce(fn, ms = 180) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
