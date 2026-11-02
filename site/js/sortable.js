/**
 * Every static table sorts on a header click — one listener for the whole app.
 *
 * The configurable player table (table.js) sorts itself; this is for the rest: the hand-built
 * tables on History, Matches, the club sheet, the profile and so on. A view builds its table as
 * plain DOM and does nothing; clicking a header reorders that table's rows in place.
 *
 *   - A `.num` column sorts high to low on the first click, any other column A to Z; a second
 *     click reverses it. Money ("£7.4M", "£600K"), signs, commas and "%" read as numbers.
 *   - A cell can carry `data-sort` to give its own key (a fee cell whose text is "Free").
 *   - Blank cells (—, empty) go last in either direction.
 *   - A sort is remembered per table LAYOUT (its header labels) for the session, and re-applied
 *     when a view redraws the same table — switching season on History keeps the fee order.
 *   - Opt a table out with the class `nosort`. Tables it can't sort safely are left alone:
 *     no thead, a header cell spanning columns, or a body row whose cell count differs from the
 *     header's (a sub-header or an expanded detail row would be torn from its parent).
 */
const BLANK = new Set(["", "—", "–", "-"]);
const memory = new Map();            // header signature -> {col, dir}

const headCells = (table) => [...(table.tHead?.rows[0]?.cells || [])];
const label = (th) => [...th.childNodes].filter((n) => !n.classList?.contains("arrow"))
  .map((n) => n.textContent).join("").trim();
const signature = (table) => headCells(table).map(label).join("|");

function sortable(table) {
  if (!table.tHead || table.classList.contains("nosort") || table.closest(".tablewrap")) return false;
  const head = headCells(table);
  if (!head.length || head.some((th) => th.colSpan > 1)) return false;
  return [...table.tBodies].every((tb) => [...tb.rows].every((tr) => tr.cells.length === head.length));
}

function key(td, numeric) {
  const raw = td.dataset.sort ?? td.textContent.trim();
  if (td.dataset.sort === "") return null;
  if (BLANK.has(raw)) return null;
  if (!numeric) return raw;
  const m = raw.replace(/[,\s£$€]/g, "").replace("−", "-").match(/^([+-]?\d*\.?\d+)([kKmMbB]?)%?$/);
  if (!m) return raw;                // text in a number column ("Academy"): after the numbers
  return Number(m[1]) * ({ k: 1e3, m: 1e6, b: 1e9 }[m[2].toLowerCase()] || 1);
}

function compare(a, b, dir) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  const an = typeof a === "number", bn = typeof b === "number";
  if (an && bn) return dir * (a - b);
  if (an !== bn) return an ? -1 : 1;  // numbers before stray text, either direction
  return dir * a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

function apply(table, col, dir) {
  const head = headCells(table);
  const th = head[col];
  if (!th) return;
  const numeric = th.classList.contains("num");
  for (const tb of table.tBodies) {
    const rows = [...tb.rows].map((tr, i) => ({ tr, i, k: key(tr.cells[col], numeric) }));
    rows.sort((x, y) => compare(x.k, y.k, dir) || x.i - y.i);
    tb.append(...rows.map((r) => r.tr));
  }
  head.forEach((h) => {
    h.classList.toggle("sorted", h === th);
    h.querySelector(":scope > .arrow.auto")?.remove();
  });
  const arrow = document.createElement("span");
  arrow.className = "arrow auto";
  arrow.textContent = dir > 0 ? "▲" : "▼";
  th.append(arrow);
}

function onClick(e) {
  const th = e.target.closest("thead th");
  if (!th || e.target.closest("a, button, input, select")) return;
  const table = th.closest("table");
  if (!table || !sortable(table) || th.parentElement !== table.tHead.rows[0]) return;
  const col = th.cellIndex;
  const sig = signature(table);
  const prev = memory.get(sig);
  const dir = prev && prev.col === col ? -prev.dir : th.classList.contains("num") ? -1 : 1;
  memory.set(sig, { col, dir });
  apply(table, col, dir);
}

/** Re-apply a remembered sort to tables a view has just (re)drawn. */
function restore(root) {
  const tables = root.matches?.("table") ? [root] : [...(root.querySelectorAll?.("table") || [])];
  for (const t of tables) {
    const s = memory.size && sortable(t) ? memory.get(signature(t)) : null;
    if (s) apply(t, s.col, s.dir);
  }
}

export function installSortableTables(root = document.body) {
  root.addEventListener("click", onClick);
  new MutationObserver((muts) => {
    if (!memory.size) return;
    for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1) restore(n);
  }).observe(root, { childList: true, subtree: true });
}
