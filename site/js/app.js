/**
 * Router + shell. One page, hash routes, no build step.
 *
 * The tactic and snapshot selectors live in the header rather than inside a view, because they
 * change the meaning of every number on every screen — every rating in the app is recomputed
 * from attributes x the selected weight-set, so switching tactic re-renders the current view.
 */
import * as D from "./data.js";
import { el, clear, toast } from "./ui.js";

const ROUTES = [
  ["squad", "Squad", () => import("./views/squad.js")],
  ["positions", "Positions", () => import("./views/positions.js")],
  ["builder", "Builder", () => import("./views/builder.js")],
  ["recruit", "Recruitment", () => import("./views/recruit.js")],
  ["registration", "Registration", () => import("./views/registration.js")],
  ["opposition", "Opposition", () => import("./views/opposition.js")],
  ["matches", "Matches", () => import("./views/matches.js")],
  ["history", "History", () => import("./views/history.js")],
];

const main = () => document.getElementById("main");
let current = null;

function route() {
  const h = (location.hash || "#/squad").replace(/^#\/?/, "").split("?")[0];
  return ROUTES.find((r) => r[0] === h) || ROUTES[0];
}

async function render() {
  const [key, title, load] = route();
  current = key;
  for (const a of document.querySelectorAll("nav.tabs a")) {
    a.classList.toggle("on", a.dataset.route === key);
  }
  clear(main()).append(el("div.spinner", { text: `Loading ${title.toLowerCase()}…` }));
  try {
    const mod = await load();
    const node = await mod.view();
    if (current !== key) return;                 // navigated away while loading
    clear(main()).append(node);
    window.scrollTo(0, 0);
  } catch (e) {
    clear(main()).append(el("div.card", {}, [
      el("b", { text: `${title} failed to load` }),
      el("p.note", { text: String(e && e.message ? e.message : e) }),
    ]));
    console.error(e);
  }
}

function buildChrome() {
  const ix = D.S.index;
  document.getElementById("clubname").textContent = ix.career.name;
  const div = D.S.leagues.get(D.ourLeagueCid())?.name;
  document.getElementById("snapline").textContent =
    `${div ? div + " · " : ""}${ix.snapshot.season} · ${ix.snapshot.phase}`;
  document.title = `${ix.career.name} · ${div || "squad"}`;

  const tabs = document.getElementById("tabs");
  clear(tabs);
  for (const [k, label] of ROUTES) {
    tabs.append(el("a", { href: `#/${k}`, text: label, dataset: { route: k } }));
  }

  const tsel = document.getElementById("tacticsel");
  clear(tsel);
  for (const m of Object.keys(D.S.tactics).sort()) {
    tsel.append(el("option", { value: m, text: m, selected: m === D.S.method }));
  }
  tsel.addEventListener("change", (e) => {
    D.S.method = e.target.value;
    localStorage.setItem("fm:method", D.S.method);
    toast(`Ratings recomputed for ${D.S.method}`);
    render();
  });
  const saved = localStorage.getItem("fm:method");
  if (saved && D.S.tactics[saved]) { D.S.method = saved; tsel.value = saved; }

  // Snapshot selector: the export is one snapshot, so this points out that switching needs a
  // rebuild rather than pretending it's live. Better than hiding the other 11 snapshots.
  const ssel = document.getElementById("snapsel");
  clear(ssel);
  for (const s of ix.snapshots) {
    const cur = s.season === ix.snapshot.season && s.phase === ix.snapshot.phase;
    ssel.append(el("option", { value: `${s.season}|${s.phase}`, text: `${s.season} · ${s.phase}`, selected: cur }));
  }
  ssel.addEventListener("change", (e) => {
    const [season, phase] = e.target.value.split("|");
    ssel.value = `${ix.snapshot.season}|${ix.snapshot.phase}`;
    toast(`This site is built from ${ix.snapshot.phase}. Re-export with --season ${season} --phase ${phase} to switch.`, true);
  });

  document.getElementById("foot").append(el("div", {}, [
    `Built ${ix.generated_at.slice(0, 16).replace("T", " ")} · ratings computed in the browser from `
    + `attributes × the selected weight-set. ${ix.immersion_rule}`,
  ]));
}

(async function start() {
  try {
    await D.boot();
  } catch (e) {
    clear(main()).append(el("div.card", {}, [
      el("b", { text: "Couldn't load the data" }),
      el("p.note", { text: String(e.message || e) }),
      el("p.note", { text: "Run: uv run python scripts/export_data.py" }),
    ]));
    return;
  }
  buildChrome();
  addEventListener("hashchange", render);
  render();
})();
