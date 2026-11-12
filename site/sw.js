/**
 * Offline copy of the app. Network first, cache as the fallback: online, every request goes to
 * the server as before and its answer replaces the cached copy; offline, the cached copy answers.
 * So a fresh import shows up on the next online visit with no cache version to bump.
 *
 * The cache is filled up front (SHELL, then the open career's DATA files and its every-player
 * file), not only as pages are visited, so a section never opened online still works offline.
 * The page re-sends "warm" with its career on every online load, which re-requests the list
 * conditionally — unchanged files come back 304 and cost nothing, and all.json is kept in step
 * with the import core.json came from. Each career's data sits under `api/<career>/`, so a
 * career opened online is kept offline beside the others.
 *
 * `/api/<career>/all?tid=` and `?club=` (profile sheets, shortlist resolution) are answered
 * offline by filtering that career's cached full file, mirroring the Worker's filter in
 * site-worker/index.js.
 *
 * Writes (shortlist, registration windows) are POST/DELETE and pass straight through: offline
 * they fail as they always have. Their GETs are cached like anything else, so a shortlist seen
 * online can still be read offline.
 *
 * tests/test_site_offline.py fails when a file under site/ is missing from SHELL, or a file the
 * export writes is missing from DATA.
 */
const CACHE = "fm-offline";
const CAREERS = "api/careers.json";
const ALL = "all";                  // api/<career>/all, the Worker's filterable endpoint
const ALL_LOCAL = "all.json";       // local preview: no Worker, the file sits on disk instead
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
  "api/careers.json",
];

// One career's export, under api/<career>/.
const DATA = [
  "clubs.json",
  "core.json",
  "forecast.json",
  "index.json",
  "loans.json",
  "matches.json",
  "registration.json",
  "squad.json",
  "transfers.json",
  "world.json",
];

const abs = (path) => new URL(path, self.registration.scope).href;

/** Fetch every file and store it: the shell, then one career's data — `career`, else the
 *  default careers.json names. One failure (all.json absent from a local preview) must not stop
 *  the rest, so each is settled on its own. */
async function warm(career) {
  const cache = await caches.open(CACHE);
  const store = async (path) => {
    const r = await fetch(abs(path), { cache: "no-cache" });
    if (r.ok) await cache.put(abs(path), r.clone());
    return r.ok ? r : null;
  };
  const settled = await Promise.allSettled(SHELL.map(store));
  if (!career) {
    const listed = settled[SHELL.indexOf(CAREERS)];
    career = listed.status === "fulfilled" && listed.value
      ? (await listed.value.json().catch(() => ({}))).default : null;
  }
  if (!career || !/^[a-z0-9_]+$/.test(career)) return;
  const base = `api/${career}/`;
  await Promise.allSettled(DATA.map((n) => store(base + n)));
  if (!(await store(base + ALL).catch(() => null))) await store(base + ALL_LOCAL).catch(() => null);
}

self.addEventListener("install", (e) => {
  e.waitUntil(warm(null));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "warm") e.waitUntil(warm(e.data.career || null));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (/\/api\/[a-z0-9_]+\/all$/.test(url.pathname) && url.search) {
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

/** `/api/<career>/all?tid=..&club=..` — the network when it answers, else the same filter
 *  applied to that career's cached full file. */
async function filteredAll(req, url) {
  try {
    const r = await fetch(req);
    if (r.ok) return r;
  } catch { /* offline: fall through to the cached copy */ }
  const cache = await caches.open(CACHE);
  const base = url.pathname.replace(/all$/, "");
  const full = (await cache.match(new URL(base + ALL, url).href))
    || (await cache.match(new URL(base + ALL_LOCAL, url).href));
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
