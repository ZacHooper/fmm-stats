/**
 * The configurable player table — one component, every section.
 *
 * This is the piece the pre-rendered version was missing. A finished HTML table can't be
 * re-columned, searched or sorted, which made the first site a screenshot rather than a tool.
 * Here the caller supplies a column CATALOGUE (id -> definition) and a default selection, and
 * the user adds or removes any of them, including all 23 attributes and every match stat, from
 * one picker with presets.
 *
 * Deliberately the same column vocabulary as `dashboard/stat_table.py`. Two vocabularies for
 * the same numbers would be two products.
 */
import { el, clear, frag, num, DASH, debounce } from "./ui.js";

const LS = (key) => `fmtable:${key}`;

/**
 * @param {object} o
 *   key       persistence key (column choice + sort survive reloads and navigation)
 *   rows      array of row objects (each must have .tid and ._search)
 *   catalogue {id: {label, group, get(row), render?(row), align?, sort?, help?, width?}}
 *   defaults  [id] initially-shown columns, in order
 *   presets   {name: [id]} one-click column sets
 *   sticky    [id] columns that can never be removed (identity)
 *   onRow     click handler for a row
 *   toolbar   extra controls to place beside the search box
 *   empty     message when nothing matches
 */
export function playerTable(o) {
  const state = loadState(o.key, o.defaults, o.sort);
  const host = el("div.tablewrap");
  const search = el("input.search", {
    type: "search", placeholder: o.searchPlaceholder || "Search players…",
    value: state.q || "", "aria-label": "Search",
  });
  const count = el("span.count");
  const picker = columnPicker(o, state, () => { save(o.key, state); draw(); });
  const bar = el("div.tbar", {}, [
    search, picker.button, ...(o.toolbar || []), count,
  ]);
  const scroll = el("div.scroll");
  host.append(bar, picker.panel, scroll);

  const onSearch = debounce((v) => { state.q = v; save(o.key, state); draw(); }, 160);
  search.addEventListener("input", (e) => onSearch(e.target.value));

  function visibleCols() {
    const ids = [...(o.sticky || []), ...state.cols.filter((c) => !(o.sticky || []).includes(c))];
    return ids.filter((id) => o.catalogue[id]).map((id) => ({ id, ...o.catalogue[id] }));
  }

  function sortRows(rows, cols) {
    if (!state.sortBy) return rows;
    const def = o.catalogue[state.sortBy];
    if (!def) return rows;
    const key = def.sort || def.get;
    const dir = state.sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = key(a), y = key(b);
      const xn = x == null || Number.isNaN(x), yn = y == null || Number.isNaN(y);
      if (xn && yn) return 0;
      if (xn) return 1;              // blanks always last, whichever direction
      if (yn) return -1;
      if (typeof x === "string" || typeof y === "string") {
        return dir * String(x).localeCompare(String(y));
      }
      return dir * (x - y);
    });
  }

  function draw() {
    const cols = visibleCols();
    const q = (state.q || "").trim().toLowerCase();
    let rows = o.rows;
    if (q) {
      const terms = q.split(/\s+/);
      rows = rows.filter((r) => terms.every((t) => (r._search || "").includes(t)));
    }
    if (o.filter) rows = rows.filter(o.filter);
    rows = sortRows(rows, cols);
    count.textContent = `${rows.length}${rows.length === o.rows.length ? "" : ` of ${o.rows.length}`}`;

    const thead = el("thead", {}, [el("tr", {}, cols.map((c) => {
      const on = state.sortBy === c.id;
      return el(`th${c.align === "num" ? ".num" : ""}${on ? ".sorted" : ""}`, {
        title: c.help || c.label,
        onclick: () => {
          if (state.sortBy === c.id) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
          else { state.sortBy = c.id; state.sortDir = c.align === "num" ? "desc" : "asc"; }
          save(o.key, state); draw();
        },
      }, [c.label, on ? el("span.arrow", { text: state.sortDir === "asc" ? "▲" : "▼" }) : null]);
    }))]);

    const tbody = el("tbody");
    if (!rows.length) {
      tbody.append(el("tr", {}, [el("td.empty", { colspan: cols.length, text: o.empty || "Nothing matches." })]));
    }
    for (const r of rows.slice(0, state.limit || 400)) {
      const extra = o.rowClass ? o.rowClass(r) : null;
      const tr = el("tr", {
        ...(o.onRow ? { class: "click", onclick: () => o.onRow(r) } : {}),
        ...(extra ? { class: (o.onRow ? "click " : "") + extra } : {}),
      });
      for (const c of cols) {
        const td = el(`td${c.align === "num" ? ".num" : ""}${c.cls ? "." + c.cls : ""}`);
        if (c.render) {
          const v = c.render(r);
          if (v != null) td.append(v instanceof Node ? v : document.createTextNode(String(v)));
          else td.append(document.createTextNode(DASH));
        } else {
          const v = c.get(r);
          td.textContent = v == null || Number.isNaN(v) ? DASH
            : (typeof v === "number" ? num(v, c.dp ?? 0) : String(v));
        }
        tr.append(td);
      }
      tbody.append(tr);
    }
    scroll.classList.toggle("fit", rows.length <= 12);
    clear(scroll).append(el("table", {}, [thead, tbody]));
    if (rows.length > (state.limit || 400)) {
      scroll.append(el("div.more", {}, [
        `Showing ${state.limit || 400} of ${rows.length}. `,
        el("button.link", {
          text: "Show all", onclick: () => { state.limit = rows.length; draw(); },
        }),
      ]));
    }
  }

  draw();
  return { node: host, redraw: draw, state };
}

function columnPicker(o, state, changed) {
  const groups = {};
  for (const [id, def] of Object.entries(o.catalogue)) {
    (groups[def.group || "Other"] ||= []).push({ id, ...def });
  }
  const panel = el("div.picker.hide");
  const button = el("button.btn", {
    text: "Columns", title: "Add or remove any column — attributes and match stats included",
    onclick: () => panel.classList.toggle("hide"),
  });

  const rebuild = () => {
    clear(panel);
    const filter = el("input.pfilter", { type: "search", placeholder: "Filter columns — try \"pace\", \"%\", \"/90\"" });
    panel.append(el("div.prow", {}, [
      filter,
      ...Object.entries(o.presets || {}).map(([name, ids]) =>
        el("button.chip", {
          text: name,
          onclick: () => {
            const add = ids.filter((i) => o.catalogue[i]);
            const keep = state.cols.filter((c) => !add.includes(c));
            state.cols = [...keep, ...add];
            changed(); rebuild();
          },
        })),
      el("button.chip.ghost", {
        text: "Reset", onclick: () => { state.cols = [...o.defaults]; changed(); rebuild(); },
      }),
    ]));
    const body = el("div.pbody");
    for (const [g, defs] of Object.entries(groups)) {
      const sect = el("div.pgroup", {}, [el("h4", { text: g })]);
      for (const d of defs) {
        if ((o.sticky || []).includes(d.id)) continue;
        const on = state.cols.includes(d.id);
        sect.append(el(`button.chip${on ? ".on" : ""}`, {
          text: d.label, title: d.help || d.label, dataset: { label: d.label.toLowerCase() },
          onclick: () => {
            state.cols = on ? state.cols.filter((c) => c !== d.id) : [...state.cols, d.id];
            changed(); rebuild();
          },
        }));
      }
      body.append(sect);
    }
    panel.append(body);
    filter.addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      for (const c of body.querySelectorAll(".chip")) {
        c.style.display = !q || c.dataset.label.includes(q) ? "" : "none";
      }
      for (const g of body.querySelectorAll(".pgroup")) {
        const any = [...g.querySelectorAll(".chip")].some((c) => c.style.display !== "none");
        g.style.display = any ? "" : "none";
      }
    });
  };
  rebuild();
  return { button, panel };
}

function loadState(key, defaults, sort) {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS(key)) || "{}"); } catch { s = {}; }
  return {
    cols: Array.isArray(s.cols) && s.cols.length ? s.cols : [...defaults],
    sortBy: s.sortBy ?? sort?.by ?? null,
    sortDir: s.sortDir ?? sort?.dir ?? "desc",
    q: s.q || "", limit: 400,
  };
}
function save(key, s) {
  try {
    localStorage.setItem(LS(key), JSON.stringify({ cols: s.cols, sortBy: s.sortBy, sortDir: s.sortDir, q: s.q }));
  } catch { /* private browsing — column choice just won't persist */ }
}

/** Build attribute + match-stat column definitions from the data layer's vocabularies, so
 *  every table gets the same catalogue without repeating it. */
export function metricColumns(D, { agg = null, role = null } = {}) {
  const cat = {};
  for (const [group, names] of Object.entries(D.ATTR_GROUPS)) {
    for (const a of names) {
      const i = D.S.attrs.indexOf(a);
      if (i < 0) continue;
      cat[`attr:${a}`] = {
        label: a, group: `Attributes · ${group}`, align: "num",
        help: `${a} (1-20)${role ? "" : ""}`,
        get: (r) => r.player?.attrs?.[i] ?? null,
      };
    }
  }
  if (agg) {
    const order = ["Apps", "Starts", "Sub", "Min", "Min/gm", "Rating", "Goals", "Assists",
      "G+A", "Key passes", "Pass att", "Tackle att", "Shot att", "Interceptions", "Dribbles"];
    const per = Object.keys(D.STAT_DEFS).filter((k) => /\/90$/.test(k));
    const pg = Object.keys(D.STAT_DEFS).filter((k) => /\/gm$/.test(k));
    const pct = Object.keys(D.STAT_DEFS).filter((k) => /%$/.test(k));
    const put = (names, group, dp) => names.forEach((n) => {
      cat[`stat:${n}`] = {
        label: n, group, align: "num", dp,
        help: `${n} — from parsed match data for our club`,
        get: (r) => D.statValue(n, agg.get(r.tid)),
      };
    });
    put(order, "Match · totals", 0);
    put(per, "Match · per 90", 2);
    put(pg, "Match · per game", 2);
    put(pct, "Match · success %", 0);
  }
  return cat;
}
