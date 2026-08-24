/**
 * The Worker entrypoint. Serves the two dynamic endpoints; everything else is a static asset.
 *
 * Why a Worker and not Pages Functions: this project is deployed as a **Worker with static
 * assets** (`*.workers.dev`), not a Pages project, and a Pages `functions/` directory is simply
 * not read by the Workers runtime — the endpoints 404'd with an empty body, which is the asset
 * handler's 404 rather than ours. Same logic, correct host.
 *
 * Routing: Cloudflare serves a matching static asset FIRST and only invokes this script when
 * nothing matches. So `/api/index.json`, `/api/core.json` and friends keep being served straight
 * off disk, and only the two paths below — which have no file behind them — reach here.
 * `not_found_handling` is "none" because the app is hash-routed (`#/squad`), so every real path
 * is a real file and an SPA rewrite would swallow these endpoints.
 *
 * Bindings (see wrangler.jsonc):
 *   FM_STATE            R2 bucket holding site-data/ and state/ — a native binding, no keys
 *   FM_SHORTLIST_TOKEN  secret; set in the dashboard or `wrangler secret put`. Never in config.
 */

const ALL_KEY = "site-data/all.json";
const SHORTLIST_PREFIX = "state/shortlist/";
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...extra } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/all") return allPlayers(request, env);
    if (url.pathname === "/api/shortlist") return shortlist(request, env);
    // Not an asset and not an endpoint. Let the asset handler produce the 404 so the response
    // matches everything else on the host.
    return env.ASSETS ? env.ASSETS.fetch(request) : json({ error: "not found" }, 404);
  },
};

/**
 * Every player in the save (~4 MB). Streamed from R2 rather than committed: it rewrites
 * wholesale on every import and minified JSON deltas badly, so versioning it would put tens of
 * MB a year into git for a derived artefact — the mistake that took this repo's .git to 257 MB
 * when the DuckDB stores were tracked.
 *
 * Unauthenticated on purpose. It's the same football data the pages already render, and gating
 * it would mean shipping a token to every visitor just to read. Writes are gated; reads aren't.
 *
 * `?club=<tid>[,<tid>...]` and/or `?tid=<tid>[,<tid>...]` filter the player list server-side —
 * an agent that only needs one club or one player gets a few KB instead of the full 1.3 MB gz.
 * Deliberately narrow (two whitelisted equality filters on indexed columns, not a query
 * language) rather than accepting arbitrary SQL/JS from the caller.
 */
async function allPlayers(request, env) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return json({ error: `${request.method} not supported` }, 405);
  }
  const obj = await env.FM_STATE.get(ALL_KEY);
  if (!obj) {
    return json({
      error: `${ALL_KEY} is not in the bucket — run: `
        + "uv run python scripts/export_data.py --upload-all",
    }, 404);
  }
  const etag = obj.httpEtag;
  // Only changes when a snapshot is imported, so let the browser keep it and skip the ~1.3 MB
  // transfer on every later search. Filtered responses are deterministic per (etag, query), so
  // the same conditional check is valid for them too.
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { etag } });
  }

  const url = new URL(request.url);
  const clubFilter = parseIdList(url.searchParams.get("club"));
  const tidFilter = parseIdList(url.searchParams.get("tid"));
  if (!clubFilter && !tidFilter) {
    return new Response(obj.body, {
      headers: {
        ...JSON_HEADERS,
        "cache-control": "public, max-age=300, stale-while-revalidate=86400",
        etag,
      },
    });
  }

  const data = await obj.json();
  const clubIdx = data.fields.indexOf("club_tid");
  const tidIdx = data.fields.indexOf("tid");
  let players = data.players;
  if (clubFilter) players = players.filter((r) => clubFilter.has(r[clubIdx]));
  if (tidFilter) players = players.filter((r) => tidFilter.has(r[tidIdx]));
  return json({
    attrs: data.attrs, fields: data.fields, players, note: data.note,
    filtered_by: { club: clubFilter ? [...clubFilter] : undefined,
                   tid: tidFilter ? [...tidFilter] : undefined },
    count: players.length,
  }, 200, { etag, "cache-control": "public, max-age=300, stale-while-revalidate=86400" });
}

/** "12,34, 56" -> Set{12,34,56}; param absent/blank -> null (no filter requested — full file).
 *  Param PRESENT but every entry non-numeric -> empty Set, which matches nothing, so a typo'd id
 *  comes back as `count: 0`. It must NOT come back as null, or a typo would silently fall through
 *  to the unfiltered branch and ship the full 4 MB the filter exists to avoid. */
function parseIdList(raw) {
  if (!raw) return null;
  const ids = raw.split(",").map((s) => Number(s.trim())).filter(Number.isFinite);
  return new Set(ids);
}

/**
 * Shortlist read/write against R2 — the one thing on this site a human authors, since a player
 * spotted in-game on the phone exists nowhere until it's recorded.
 *
 * One object per entry. R2 has no append, so a shared file would mean read-modify-write and two
 * devices adding a player at the same moment would silently lose one. Per-entry objects make
 * adds collision-free, a delete an object delete, and the laptop sync a plain union — `rclone
 * copy` each way, no merge logic to get wrong. The Python side uses the same layout.
 *
 * Auth is a shared bearer token, and it buys exactly one thing: a stranger who finds the URL
 * can't write to the bucket. It is not per-user auth and it does reach the browser.
 */
async function shortlist(request, env) {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
        "access-control-allow-headers": "content-type,x-fm-token",
      },
    });
  }
  if (!authorised(request, env)) {
    return json({
      error: env.FM_SHORTLIST_TOKEN ? "bad token" : "FM_SHORTLIST_TOKEN is not configured",
    }, 401);
  }

  if (request.method === "GET") {
    const out = [];
    let cursor;
    do {
      const page = await env.FM_STATE.list({ prefix: SHORTLIST_PREFIX, cursor, limit: 1000 });
      for (const o of page.objects) {
        const body = await env.FM_STATE.get(o.key);
        if (!body) continue;
        try {
          out.push(await body.json());
        } catch {
          // a half-written object must not take the whole list down — same rule the Python
          // side applies in state.entries()
        }
      }
      cursor = page.truncated ? page.cursor : undefined;
    } while (cursor);
    out.sort((a, b) => String(a?.name ?? "").localeCompare(String(b?.name ?? "")));
    return json({ count: out.length, entries: out });
  }

  if (request.method === "POST") {
    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "body must be JSON" }, 400);
    }
    const name = String(payload?.name ?? "").trim().slice(0, 120);
    if (!name) return json({ error: "name is required" }, 400);
    const id = newKey();
    const rec = {
      id,
      tid: payload?.tid == null || payload.tid === "" ? null : Number(payload.tid),
      name,
      positions: cleanMap(payload?.positions),
      attributes: cleanMap(payload?.attributes),
      note: String(payload?.note ?? "").slice(0, 500) || undefined,
      source: String(payload?.source ?? "phone").slice(0, 32),
      added_at: new Date().toISOString().slice(0, 19),
    };
    await env.FM_STATE.put(`${SHORTLIST_PREFIX}${id}.json`, JSON.stringify(rec, null, 1), {
      httpMetadata: { contentType: "application/json" },
    });
    return json({ ok: true, entry: rec }, 201);
  }

  if (request.method === "DELETE") {
    const id = new URL(request.url).searchParams.get("id") ?? "";
    if (!/^\d+$/.test(id)) return json({ error: "id must be the numeric entry id" }, 400);
    await env.FM_STATE.delete(`${SHORTLIST_PREFIX}${id}.json`);
    return json({ ok: true, deleted: id });
  }
  return json({ error: `${request.method} not supported` }, 405);
}

function authorised(request, env) {
  // Trim both sides. A token is typed or pasted by hand into a phone browser, and a trailing
  // space or newline riding along on a copy is otherwise indistinguishable from a wrong token —
  // you get "bad token" with no way to see why. Whitespace at either end carries no security
  // value, so accepting it costs nothing and removes a genuinely maddening failure.
  const want = (env.FM_SHORTLIST_TOKEN ?? "").trim();
  if (!want) return false;                        // unconfigured = closed, never open
  const got = (request.headers.get("x-fm-token") ?? "").trim();
  if (got.length !== want.length) return false;   // length may leak; contents may not
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}

/** Microsecond-ish id, matching dashboard/state.py's new_key(): the Streamlit Squad Tool casts
 *  the id with int(), so it has to stay all-digits. */
function newKey() {
  return String(Date.now() * 1000 + Math.floor(Math.random() * 1000));
}

function cleanMap(o) {
  const out = {};
  if (o && typeof o === "object") {
    for (const [k, v] of Object.entries(o)) {
      const n = Number(v);
      if (Number.isFinite(n)) out[String(k).slice(0, 24)] = Math.round(n);
    }
  }
  return out;
}
