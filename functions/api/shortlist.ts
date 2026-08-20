/**
 * Shortlist reads and writes from the phone — a Cloudflare Pages Function over the same R2
 * bucket the laptops sync against.
 *
 * Why this exists. Everything else on the site is a pre-rendered read of one snapshot, so it
 * needs no server. The shortlist is the one thing a human authors on the phone: spotting a
 * player in-game and wanting him recorded before the thought is gone. It cannot be a build
 * artefact, and it must not be a file only one laptop has.
 *
 * Why one object per entry (`state/shortlist/<id>.json`). R2 has no append, so a shared file
 * would mean read-modify-write and two devices adding a player at the same moment would
 * silently lose one. Per-entry objects make adds collision-free, a delete an object delete,
 * and the laptop sync a plain union — `rclone copy` each way, no merge logic to get wrong.
 * That is why the Python side moved to this layout too (see dashboard/state.py).
 *
 * Bindings to configure in the Pages project (Settings -> Functions):
 *   R2 bucket binding   FM_STATE            -> the bucket holding state/ (default: fmm-stats)
 *   Environment secret  FM_SHORTLIST_TOKEN  -> any long random string
 *
 * Auth is a shared bearer token, and it is honest about what it buys: it stops a stranger who
 * finds the URL from writing to the bucket. It is not per-user auth, and the token reaches the
 * browser, so treat it as a write gate on a football save rather than a security boundary.
 * The page never ships it — it is pasted once and kept in localStorage.
 */
interface Env {
  FM_STATE: R2Bucket;
  FM_SHORTLIST_TOKEN?: string;
}

const PREFIX = "state/shortlist/";
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function authorised(request: Request, env: Env): boolean {
  const want = env.FM_SHORTLIST_TOKEN;
  if (!want) return false;                       // unconfigured = closed, never open
  const got = request.headers.get("x-fm-token") ?? "";
  // Constant-time-ish compare. Length is allowed to leak; the contents aren't.
  if (got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}

/** Microsecond-ish timestamp id, matching dashboard/state.py's new_key(): the Squad Tool
 *  casts the id with int(), so it has to stay all-digits. */
function newKey(): string {
  return String(Date.now() * 1000 + Math.floor(Math.random() * 1000));
}

function cleanMap(o: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  if (o && typeof o === "object") {
    for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
      const n = Number(v);
      if (Number.isFinite(n)) out[String(k).slice(0, 24)] = Math.round(n);
    }
  }
  return out;
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204,
      headers: { "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
                 "access-control-allow-headers": "content-type,x-fm-token" } });
  }
  if (!authorised(request, env)) {
    return json({ error: env.FM_SHORTLIST_TOKEN ? "bad token"
                                                : "FM_SHORTLIST_TOKEN is not configured" }, 401);
  }

  // ---- list
  if (request.method === "GET") {
    const out: unknown[] = [];
    let cursor: string | undefined;
    do {
      const page = await env.FM_STATE.list({ prefix: PREFIX, cursor, limit: 1000 });
      for (const obj of page.objects) {
        const body = await env.FM_STATE.get(obj.key);
        if (!body) continue;
        try {
          out.push(await body.json());
        } catch {
          // a half-written object must not take the whole list down — same rule as
          // state.entries() on the Python side
        }
      }
      cursor = page.truncated ? page.cursor : undefined;
    } while (cursor);
    out.sort((a: any, b: any) => String(a?.name ?? "").localeCompare(String(b?.name ?? "")));
    return json({ count: out.length, entries: out });
  }

  // ---- add
  if (request.method === "POST") {
    let payload: any;
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
    await env.FM_STATE.put(`${PREFIX}${id}.json`, JSON.stringify(rec, null, 1), {
      httpMetadata: { contentType: "application/json" },
    });
    return json({ ok: true, entry: rec }, 201);
  }

  // ---- remove
  if (request.method === "DELETE") {
    const id = new URL(request.url).searchParams.get("id") ?? "";
    if (!/^\d+$/.test(id)) return json({ error: "id must be the numeric entry id" }, 400);
    await env.FM_STATE.delete(`${PREFIX}${id}.json`);
    return json({ ok: true, deleted: id });
  }

  return json({ error: `${request.method} not supported` }, 405);
};
