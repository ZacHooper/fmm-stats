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
const PAGE = 400;                  // rows painted per step — see the paging note in draw()

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
 *   filters   true to offer the "Filters" button (see filterPanel below)
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
  const filters = o.filters
    ? filterPanel(o, state, () => { state.limit = 400; save(o.key, state); draw(); })
    : null;
  const bar = el("div.tbar", {}, [
    search, picker.button, ...(filters ? [filters.button] : []), ...(o.toolbar || []), count,
  ]);
  const scroll = el("div.scroll");
  host.append(bar, picker.panel,
    ...(filters ? [filters.chips, filters.panel, filters.valuePanel] : []), scroll);

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
    // The caller's own predicate runs first and is left exactly as it was — squad.js passes one
    // for its loan/shortlist/unit toggles. The column filters compose with it, never replace it.
    if (o.filter) rows = rows.filter(o.filter);
    rows = applyFilters(rows, state.filters, o.catalogue);
    filters?.sync();
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
    // Paged in PAGE-sized steps rather than "show all". The search table holds ~23,000 rows once
    // every player is loaded, and painting them in one go builds a quarter of a million cells
    // synchronously — enough to lock up a phone. "Show all" stays, but only where it can't hurt.
    const shown = state.limit || PAGE;
    if (rows.length > shown) {
      scroll.append(el("div.more", {}, [
        `Showing ${shown} of ${rows.length}. `,
        el("button.link", {
          text: `Show ${Math.min(PAGE, rows.length - shown)} more`,
          onclick: () => { state.limit = shown + PAGE; draw(); },
        }),
        ...(rows.length - shown <= PAGE * 5 ? [
          document.createTextNode(" · "),
          el("button.link", { text: "Show all", onclick: () => { state.limit = rows.length; draw(); } }),
        ] : [
          document.createTextNode(" · narrow it with Filters to see the rest."),
        ]),
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

/* ------------------------------------------------------------------ filtering
 *
 * Filtering is GENERIC over the column catalogue rather than a hand-written set of facets, and
 * that is the whole trick: every catalogue entry already carries {label, group, get, align}, and
 * `align: "num"` already says whether a field is a range or a set. So filtering needs no new
 * per-column configuration, it covers all ~57 fields the search table offers (23 attributes and
 * 25 match stats included), and any column added later is filterable the day it is added. A
 * fixed facet set would have been more code covering a tenth of the fields.
 *
 * Two escape hatches exist for the columns that don't describe themselves properly:
 *   filterType   "range" | "set" | "none"  — override the align-based guess
 *   filterValue  (row) => primitive | array — override the accessor (for render-only columns
 *                whose `sort` key is a display rank rather than a real value, and for
 *                multi-valued fields like "every position he can play")
 */

/** Range or set? `align: "num"` is already the answer for all but a couple of columns. */
function filterKind(def) {
  return def.filterType || (def.align === "num" ? "range" : "set");
}

/**
 * The value a filter reads. For a range this is deliberately the SAME resolution `sortRows`
 * uses (`sort || get`), so a column sorts and filters on one number; for a set it prefers `get`,
 * because what you want to pick from a list is the displayed value ("DL", a club name), not a
 * sort rank.
 *
 * `filters` — the full active filter list — is passed to a custom `filterValue`, not just the
 * row. A column can be scoped by a SIBLING filter: recruit.js's Fam/Rating/Level %ile all read
 * a player's single best-rated role by default, but when a Position filter is also active they
 * need to answer "at the position(s) selected", not "at whichever role rates highest overall" —
 * otherwise "Pos=DR, Fam 18-20" can pass a player whose DR familiarity is nowhere near that
 * range, because his unrelated best role happened to qualify.
 */
function filterKey(def, kind, filters) {
  if (def.filterValue) return (row) => def.filterValue(row, filters);
  return kind === "range" ? (def.sort || def.get) : (def.get || def.sort);
}

const isBlank = (v) => v == null || v === "" || (typeof v === "number" && Number.isNaN(v));

/** Read a filter value as a list — a field may legitimately hold several (every position a
 *  player can fill), and then the filter matches if ANY of them does. */
function readValues(key, row) {
  let v;
  try { v = key(row); } catch { return []; }
  const list = Array.isArray(v) ? v : [v];
  return list.filter((x) => !isBlank(x));
}

/**
 * Apply the active column filters. Null policy: a field with no value FAILS an active filter
 * unless that filter opted into `nulls` — asking for Pace 15-20 should not hand you players
 * whose Pace is unknown. 25 of the search table's fields are match stats that are null for every
 * player outside our own club, so this rule is load-bearing, not pedantry.
 *
 * A set filter with nothing selected constrains only presence, not value, so adding "Club" and
 * not yet picking one doesn't blank the table.
 */
function applyFilters(rows, filters, catalogue) {
  const active = (filters || []).filter((f) => catalogue[f.col] && filterKind(catalogue[f.col]) !== "none");
  if (!active.length) return rows;
  const tests = active.map((f) => {
    const def = catalogue[f.col];
    const kind = filterKind(def);
    const key = filterKey(def, kind, filters);
    if (kind === "range") {
      const lo = isBlank(f.min) ? null : Number(f.min);
      const hi = isBlank(f.max) ? null : Number(f.max);
      return (r) => {
        const vs = readValues(key, r);
        if (!vs.length) return !!f.nulls;
        return vs.some((x) => {
          const n = Number(x);
          if (Number.isNaN(n)) return false;
          return (lo == null || n >= lo) && (hi == null || n <= hi);
        });
      };
    }
    const want = new Set((f.values || []).map(String));
    return (r) => {
      const vs = readValues(key, r);
      if (!vs.length) return !!f.nulls;
      return want.size === 0 || vs.some((x) => want.has(String(x)));
    };
  });
  return rows.filter((r) => tests.every((t) => t(r)));
}

/**
 * The filter UI: a field picker (the column picker's chrome, pointed at a different payload), a
 * row of active-filter chips, and one shared value picker for whichever set filter is open.
 *
 * Candidate values and range hints come from the UNFILTERED rows on purpose — a facet whose
 * options disappear as you narrow is one you can't widen again without clearing it first.
 */
function filterPanel(o, state, changed) {
  const stats = new Map();          // id -> {values[], min, max}  (full scan, one field at a time)
  const populated = new Map();      // id -> bool                  (sampled, for greying the picker)
  const panel = el("div.picker.hide");
  const valuePanel = el("div.picker.hide");
  const chips = el("div.frow.hide");
  const button = el("button.btn", {
    text: "Filters", title: "Filter on any column — attributes and match stats included",
    onclick: () => { buildFields(); valuePanel.classList.add("hide"); panel.classList.toggle("hide"); },
  });

  /** Does this field hold anything at all here? Sampled, because asking all ~57 fields for a
   *  real answer over 23,000 rows costs more than the hint is worth. It only greys a chip — the
   *  field stays pickable, so a sample that misses a rare value costs nothing. */
  function hasData(id) {
    if (populated.has(id)) return populated.get(id);
    const def = o.catalogue[id];
    const key = filterKey(def, filterKind(def), state.filters);
    const n = Math.min(o.rows.length, 2000);
    let found = false;
    for (let i = 0; i < n && !found; i++) found = readValues(key, o.rows[i]).length > 0;
    populated.set(id, found);
    return found;
  }

  /** Full scan for ONE field, once — the distinct values for a set, the observed bounds for a
   *  range. Only ever runs for a field you actually filtered on. */
  function statsFor(id) {
    if (stats.has(id)) return stats.get(id);
    const def = o.catalogue[id];
    const kind = filterKind(def);
    const key = filterKey(def, kind, state.filters);
    const values = new Set();
    let min = Infinity, max = -Infinity;
    for (const r of o.rows) {
      for (const x of readValues(key, r)) {
        if (kind === "range") {
          const n = Number(x);
          if (!Number.isNaN(n)) { if (n < min) min = n; if (n > max) max = n; }
        } else if (values.size < 5000) values.add(String(x));
      }
    }
    const out = {
      values: [...values].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
      min: min === Infinity ? null : min,
      max: max === -Infinity ? null : max,
    };
    stats.set(id, out);
    return out;
  }

  const find = (id) => (state.filters || []).find((f) => f.col === id);

  function add(id) {
    if (find(id)) return;
    const kind = filterKind(o.catalogue[id]);
    state.filters = [...(state.filters || []),
      kind === "range" ? { col: id, type: "range", min: null, max: null, nulls: false }
        : { col: id, type: "set", values: [], nulls: false }];
    changed();
    if (kind === "set") openValues(find(id));
  }

  function remove(id) {
    state.filters = (state.filters || []).filter((f) => f.col !== id);
    valuePanel.classList.add("hide");
    changed();
  }

  function buildFields() {
    clear(panel);
    const q = el("input.pfilter", { type: "search", placeholder: "Filter on… — try \"pace\", \"age\", \"league\"" });
    panel.append(el("div.prow", {}, [q]));
    const body = el("div.pbody");
    const groups = {};
    for (const [id, def] of Object.entries(o.catalogue)) {
      if (filterKind(def) === "none") continue;
      (groups[def.group || "Other"] ||= []).push({ id, ...def });
    }
    for (const [g, defs] of Object.entries(groups)) {
      const sect = el("div.pgroup", {}, [el("h4", { text: g })]);
      for (const d of defs) {
        const on = !!find(d.id);
        const empty = !hasData(d.id);
        sect.append(el(`button.chip${on ? ".on" : ""}${empty ? ".ghost" : ""}`, {
          text: d.label,
          title: empty ? `${d.label} — nothing to filter on in this table` : (d.help || d.label),
          dataset: { label: d.label.toLowerCase() },
          onclick: () => {
            if (on) remove(d.id); else add(d.id);
            buildFields();
          },
        }));
      }
      body.append(sect);
    }
    panel.append(body);
    q.addEventListener("input", (e) => {
      const t = e.target.value.trim().toLowerCase();
      for (const c of body.querySelectorAll(".chip")) {
        c.style.display = !t || c.dataset.label.includes(t) ? "" : "none";
      }
      for (const g of body.querySelectorAll(".pgroup")) {
        const any = [...g.querySelectorAll(".chip")].some((c) => c.style.display !== "none");
        g.style.display = any ? "" : "none";
      }
    });
  }

  function openValues(f) {
    if (!f) return;
    const def = o.catalogue[f.col];
    const st = statsFor(f.col);
    clear(valuePanel);
    panel.classList.add("hide");
    valuePanel.classList.remove("hide");
    const q = el("input.pfilter", { type: "search", placeholder: `Find a ${def.label.toLowerCase()}…` });
    const note = el("p.note");
    const body = el("div.pbody");
    const render = () => {
      const t = q.value.trim().toLowerCase();
      const hits = t ? st.values.filter((v) => v.toLowerCase().includes(t)) : st.values;
      const show = hits.slice(0, 60);
      clear(body).append(...show.map((v) => el(`button.chip${(f.values || []).includes(v) ? ".on" : ""}`, {
        text: v,
        onclick: () => {
          f.values = (f.values || []).includes(v)
            ? f.values.filter((x) => x !== v) : [...(f.values || []), v];
          changed(); render();
        },
      })));
      // Club runs to a few thousand distinct values on the full save, so the list is capped and
      // you type to narrow — the same escape the column picker uses for 57 columns.
      note.textContent = hits.length > show.length
        ? `Showing ${show.length} of ${hits.length} — type to narrow.`
        : `${hits.length} value${hits.length === 1 ? "" : "s"}.`;
    };
    q.addEventListener("input", debounce(render, 120));
    valuePanel.append(el("div.prow", {}, [
      el("b", { text: def.label }), q,
      el("button.chip.ghost", { text: "Clear", onclick: () => { f.values = []; changed(); render(); } }),
      el("button.chip.ghost", { text: "Done", onclick: () => valuePanel.classList.add("hide") }),
    ]), body, note);
    render();
  }

  /** Re-render the active-filter chips. Called from draw(), so it never triggers a draw itself. */
  function sync() {
    const fs = (state.filters || []).filter((f) => o.catalogue[f.col]);
    clear(chips);
    chips.classList.toggle("hide", !fs.length);
    if (!fs.length) { valuePanel.classList.add("hide"); return; }
    for (const f of fs) {
      const def = o.catalogue[f.col];
      const st = statsFor(f.col);
      const parts = [el("b", { text: def.label })];
      if (filterKind(def) === "range") {
        const onNum = debounce(() => changed(), 260);
        const mk = (which, ph) => el("input.fnum", {
          type: "number", inputmode: "decimal", value: f[which] ?? "",
          placeholder: ph == null ? which : String(Math.round(ph * 100) / 100),
          "aria-label": `${def.label} ${which}`,
          oninput: (e) => { f[which] = e.target.value === "" ? null : Number(e.target.value); onNum(); },
        });
        // The placeholders are the field's real range over these rows, so the empty state
        // doubles as a hint about what you can usefully ask for.
        parts.push(mk("min", st.min), el("span.fsep", { text: "–" }), mk("max", st.max));
      } else {
        const n = (f.values || []).length;
        parts.push(el("button.fval", {
          text: n === 0 ? "any" : n <= 2 ? f.values.join(", ") : `${n} selected`,
          onclick: () => openValues(f),
        }));
      }
      parts.push(el(`button.chip${f.nulls ? ".on" : ""}`, {
        text: "?", title: "Also include rows where this is unknown",
        onclick: () => { f.nulls = !f.nulls; changed(); },
      }));
      parts.push(el("button.fx", {
        text: "×", title: `Remove the ${def.label} filter`, onclick: () => remove(f.col),
      }));
      chips.append(el("span.fchip", {}, parts));
    }
    chips.append(el("button.chip.ghost", {
      text: "Clear all", onclick: () => { state.filters = []; valuePanel.classList.add("hide"); changed(); },
    }));
  }

  return { button, panel, valuePanel, chips, sync };
}

function loadState(key, defaults, sort) {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS(key)) || "{}"); } catch { s = {}; }
  return {
    cols: Array.isArray(s.cols) && s.cols.length ? s.cols : [...defaults],
    sortBy: s.sortBy ?? sort?.by ?? null,
    sortDir: s.sortDir ?? sort?.dir ?? "desc",
    // Filters persist with the columns: a saved search you have to rebuild every visit is one
    // you stop using. Unknown column ids are dropped at apply time, so a catalogue that loses a
    // column can't strand a filter nobody can see or remove.
    filters: Array.isArray(s.filters) ? s.filters : [],
    q: s.q || "", limit: PAGE,
  };
}
function save(key, s) {
  try {
    localStorage.setItem(LS(key), JSON.stringify({
      cols: s.cols, sortBy: s.sortBy, sortDir: s.sortDir, q: s.q, filters: s.filters,
    }));
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
