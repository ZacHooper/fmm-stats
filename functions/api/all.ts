/**
 * Streams `site-data/all.json` — every player in the save — out of R2.
 *
 * Why a Function rather than a committed file: the payload is ~4 MB of minified JSON that
 * rewrites wholesale on every import, and minified JSON deltas badly. Committing it would put
 * tens of MB a year into git for a derived artefact — the exact mistake that took this repo's
 * .git to 257 MB when the DuckDB stores were versioned. R2 is already the tier for big derived
 * blobs, and the binding needs no credentials.
 *
 * Unauthenticated on purpose. It is the same football data the pages already show, and
 * requiring a token here would mean the token had to ship to every visitor just to read.
 * Writes (the shortlist) are gated; reads are not.
 *
 * Binding required: R2 bucket `FM_STATE` -> the bucket holding site-data/ (default fmm-stats).
 */
interface Env { FM_STATE: R2Bucket }

const KEY = "site-data/all.json";

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const obj = await env.FM_STATE.get(KEY);
  if (!obj) {
    return new Response(JSON.stringify({
      error: `${KEY} is not in the bucket — run: uv run python scripts/export_data.py --upload-all`,
    }), { status: 404, headers: { "content-type": "application/json" } });
  }
  const etag = obj.httpEtag;
  // The file only changes when a snapshot is imported, so let the browser keep it and skip the
  // ~1.3 MB transfer on every later search.
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { etag } });
  }
  return new Response(obj.body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300, stale-while-revalidate=86400",
      etag,
    },
  });
};
