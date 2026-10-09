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
  ["builder", "Builder", () => import("./views/builder.js")],
  ["recruit", "Recruitment", () => import("./views/recruit.js")],
  ["matches", "Matches", () => import("./views/matches.js")],
  ["history", "History", () => import("./views/history.js")],
  ["world", "World", () => import("./views/world.js")],
];

const main = () => document.getElementById("main");
let current = null;

// Sections folded into another one, kept so an old bookmark lands somewhere sensible:
// Development's projections and Registration's lists are columns on Squad now, and the
// Positions loan read is the Loan outlook on every owned player's profile. Opposition was
// retired outright.
const MOVED = { development: "squad", registration: "squad", positions: "squad", opposition: "squad" };

function route() {
  let h = (location.hash || "#/squad").replace(/^#\/?/, "").split("?")[0];
  if (MOVED[h]) {
    h = MOVED[h];
    history.replaceState(null, "", `#/${h}`);
  }
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
  offline();                     // first, so a failed boot still leaves the copy registered
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

/** Keep a copy on this device (site/sw.js) so the app, every-player file included, works with no
 *  connection. Each online load asks the worker to refresh that copy, and the footer says when it
 *  last finished — the signal that it is safe to go offline. Offline, a toast says the data is
 *  the copy, since the shortlist and registration windows can't be saved until reconnected. */
function offline() {
  const KEY = "fm:offline-saved";
  const status = el("div", { id: "offline" });
  document.getElementById("foot").append(status);
  const show = () => {
    let at = null;
    try { at = localStorage.getItem(KEY); } catch { /* storage blocked: just no timestamp */ }
    status.textContent = !navigator.onLine
      ? `Offline · showing the copy saved ${at || "earlier"}`
      : at ? `Saved for offline ${at}` : "Saving for offline…";
  };
  show();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (e) => {
      if (e.data?.type !== "warmed") return;
      if (e.data.shell < e.data.total || !e.data.all) {
        status.textContent = `Offline copy incomplete (${e.data.shell}/${e.data.total} files`
          + `${e.data.all ? "" : ", every-player file missing"}) — reload while online to retry`;
        return;
      }
      let first = true;
      try {
        first = !localStorage.getItem(KEY);
        localStorage.setItem(KEY, new Date().toLocaleString([], { dateStyle: "short", timeStyle: "short" }));
      } catch { /* storage blocked */ }
      show();
      if (first) toast("Saved for offline — this site now works without a connection");
    });
    navigator.serviceWorker.register("sw.js").then(async () => {
      const reg = await navigator.serviceWorker.ready;
      if (navigator.onLine) reg.active?.postMessage({ type: "warm" });
    }).catch((e) => { status.textContent = "Offline copy unavailable in this browser"; console.warn(e); });
  }
  const say = () => {
    show();
    toast(navigator.onLine ? "Back online"
      : "Offline — showing this device's saved copy. Shortlist edits wait for a connection.", !navigator.onLine);
  };
  addEventListener("online", say);
  addEventListener("offline", say);
  if (!navigator.onLine) say();
}
