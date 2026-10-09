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
  "index.html",
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

/** Fetch every file and store it. One failure (all.json absent from a local preview) must not
 *  stop the rest, so each is settled on its own. */
async function warm() {
  const cache = await caches.open(CACHE);
  const store = async (path) => {
    const r = await fetch(abs(path), { cache: "no-cache" });
    if (r.ok) await cache.put(abs(path), r);
    return r.ok;
  };
  await Promise.allSettled(SHELL.map(store));
  if (!(await store(ALL).catch(() => false))) await store(ALL_LOCAL).catch(() => false);
}

self.addEventListener("install", (e) => {
  e.waitUntil(warm());
  self.skipWaiting();
});

self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "warm") e.waitUntil(warm());
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
  const cached = await cache.match(req, { ignoreVary: true });
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
