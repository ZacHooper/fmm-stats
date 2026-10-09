/**
 * Offline copy of the app. Network first, cache as the fallback: online, every request goes to
 * the server as before and its answer replaces the cached copy; offline, the cached copy answers.
 * So a fresh import shows up on the next online visit with no cache version to bump.
 *
 * The cache is filled up front (SHELL + the every-player file), not only as pages are visited,
 * so a section never opened online still works offline. The page re-sends "warm" on every
 * online load, which re-requests the list conditionally — unchanged files come back 304 and cost
 * nothing, and all.json is kept in step with the import core.json came from.
 *
 * `/api/all?tid=` and `?club=` (profile sheets, shortlist resolution) are answered offline by
 * filtering the cached full file, mirroring the Worker's filter in site-worker/index.js.
 *
 * Writes (shortlist, registration windows) are POST/DELETE and pass straight through: offline
 * they fail as they always have. Their GETs are cached like anything else, so a shortlist seen
 * online can still be read offline.
 *
 * tests/test_site_offline.py fails when a file under site/ is missing from SHELL.
 */
const CACHE = "fm-offline";
const ALL = "api/all";
const ALL_LOCAL = "api/all.json";   // local preview: no Worker, the file sits on disk instead
const TIMEOUT_MS = 4000;            // a slow network with a cached copy available falls back to it

const SHELL = [
  "./",
  "app.css",
  "manifest.webmanifest",
  "icon.svg",
  "icon-180.png",
  "guides/registration.md",
  "guides/scout.md",
  "js/app.js",
  "js/club.js",
  "js/data.js",
  "js/devchart.js",
  "js/linechart.js",
  "js/loans.js",
  "js/profile.js",
  "js/registration.js",
  "js/regwindows.js",
  "js/table.js",
  "js/transfers.js",
  "js/ui.js",
  "js/views/builder.js",
  "js/views/history.js",
  "js/views/matches.js",
  "js/views/recruit.js",
  "js/views/squad.js",
  "js/views/world.js",
  "api/clubs.json",
  "api/core.json",
  "api/forecast.json",
  "api/index.json",
  "api/loans.json",
  "api/matches.json",
  "api/registration.json",
  "api/squad.json",
  "api/transfers.json",
  "api/world.json",
];

const abs = (path) => new URL(path, self.registration.scope).href;

/** Fetch files and store them. One failure (all.json absent from a local preview) must not stop
 *  the rest, so each is settled on its own. Returns how many of the app's files are stored and
 *  whether the every-player file is. */
async function warm(withAll) {
  const cache = await caches.open(CACHE);
  const store = async (path) => {
    const r = await fetch(abs(path), { cache: "no-cache" });
    if (r.ok) await cache.put(abs(path), r);
    return r.ok;
  };
  const got = await Promise.allSettled(SHELL.map(store));
  const shell = got.filter((g) => g.value === true).length;
  if (!withAll) return { shell, total: SHELL.length };
  const all = (await store(ALL).catch(() => false)) || (await store(ALL_LOCAL).catch(() => false));
  return { shell, total: SHELL.length, all };
}

// Install stores only the app (a few hundred KB gzipped), so it finishes in seconds and the
// worker takes control. The 7.7 MB every-player file follows on the page's "warm" message:
// waiting for it here meant a phone that closed the app or lost signal mid-download threw the
// whole install away and had no offline copy at all.
self.addEventListener("install", (e) => {
  e.waitUntil(warm(false));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("message", (e) => {
  if (!(e.data && e.data.type === "warm")) return;
  e.waitUntil(warm(true).then((r) => e.source && e.source.postMessage({ type: "warmed", ...r })));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/api/all") && url.search) {
    e.respondWith(filteredAll(req, url));
  } else {
    e.respondWith(networkFirst(req));
  }
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  // A page load is always the app (it is hash-routed), whatever URL the home-screen icon or a
  // bookmark carries — so any navigation falls back to the cached page itself.
  const cached = (await cache.match(req, { ignoreVary: true }))
    || (req.mode === "navigate" ? await cache.match(abs("./")) : undefined);
  const net = fetch(req).then(async (r) => {
    if (r.ok && r.status === 200) await cache.put(req, r.clone());
    return r;
  });
  if (!cached) return net;          // nothing to fall back on: wait for the network, errors and all
  const timeout = new Promise((res) => setTimeout(() => res(cached), TIMEOUT_MS));
  return Promise.race([net.catch(() => cached), timeout]);
}

/** `/api/all?tid=..&club=..` — the network when it answers, else the same filter applied to the
 *  cached full file. */
async function filteredAll(req, url) {
  try {
    const r = await fetch(req);
    if (r.ok) return r;
  } catch { /* offline: fall through to the cached copy */ }
  const cache = await caches.open(CACHE);
  const full = (await cache.match(abs(ALL))) || (await cache.match(abs(ALL_LOCAL)));
  if (!full) return new Response(JSON.stringify({ error: "offline, and every-player file not cached" }),
    { status: 503, headers: { "content-type": "application/json" } });
  const data = await full.json();
  const ids = (k) => {
    const raw = url.searchParams.get(k);
    return raw ? new Set(raw.split(",").map((s) => Number(s.trim())).filter(Number.isFinite)) : null;
  };
  const clubs = ids("club"), tids = ids("tid");
  const clubIdx = data.fields.indexOf("club_tid"), tidIdx = data.fields.indexOf("tid");
  let players = data.players;
  if (clubs) players = players.filter((p) => clubs.has(p[clubIdx]));
  if (tids) players = players.filter((p) => tids.has(p[tidIdx]));
  return new Response(JSON.stringify({ attrs: data.attrs, fields: data.fields, players,
    note: data.note, count: players.length }), { headers: { "content-type": "application/json" } });
}
