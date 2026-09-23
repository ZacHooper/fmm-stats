/**
 * Saved registrations — the A/B lists as submitted for one transfer window, kept so a past
 * window can be looked back on and a new one can start from the last.
 *
 * One record per WINDOW (`2027-summer`, `2028-winter`): saving a window again replaces it. With
 * the device token (the shortlist's) records go to R2 through `/api/registrations` and are
 * shared across devices; without it they stay in this browser's localStorage. Both are listed
 * together, the R2 copy winning when a window exists in both, so a window saved before the
 * token was set is not lost — it shows as "this device" and can be uploaded.
 *
 * A record carries each player's name and list, not just his tid, because the export only holds
 * the CURRENT squad: a window from two seasons ago names players who have since left.
 */
import * as D from "./data.js";

const API = "/api/registrations";
const LOCAL_KEY = "fm:registration:windows";
const ID = /^(\d{4})-(summer|winter)$/;

const tok = () => {
  try { return localStorage.getItem(D.SHORTLIST_TOKEN_KEY) || ""; } catch { return ""; }
};
export const hasToken = () => !!tok();

/** Chronological order: a year's winter window opens before its summer one. */
export const windowOrd = (id) => {
  const m = ID.exec(id || "");
  return m ? Number(m[1]) * 2 + (m[2] === "summer" ? 1 : 0) : -1;
};
export const windowId = (year, window) => `${year}-${window}`;
export function windowLabel(id) {
  const m = ID.exec(id || "");
  return m ? `${m[2] === "summer" ? "Summer" : "Winter"} ${m[1]}` : String(id);
}

/**
 * The window a snapshot dated `phase` is registering for: the one open now, or the next to open.
 * Danish windows are summer (July–August) and winter (January–February); from September the
 * next one is the following January, and from March it is the coming summer.
 */
export function guessWindow(phase) {
  const [y, m] = String(phase || "").split("-").map(Number);
  if (!y || !m) return { year: new Date().getFullYear(), window: "summer" };
  if (m <= 2) return { year: y, window: "winter" };
  if (m <= 8) return { year: y, window: "summer" };
  return { year: y + 1, window: "winter" };
}

function readLocal() {
  try { return JSON.parse(localStorage.getItem(LOCAL_KEY) || "{}") || {}; } catch { return {}; }
}
function writeLocal(map) {
  try { localStorage.setItem(LOCAL_KEY, JSON.stringify(map)); } catch { /* private mode */ }
}

/** Every saved window, newest first. `error` is set when R2 was asked and did not answer —
 *  the local ones are still returned, so a bad token never hides what this device has. */
export async function list() {
  const byId = new Map();
  for (const rec of Object.values(readLocal())) {
    if (rec && ID.test(rec.id)) byId.set(rec.id, { ...rec, where: "local" });
  }
  let error = null;
  if (tok()) {
    try {
      const r = await fetch(API, { headers: { "x-fm-token": tok() }, cache: "no-cache" });
      const d = await r.json();
      if (!r.ok) error = d.error || `HTTP ${r.status}`;
      else for (const rec of d.entries || []) byId.set(rec.id, { ...rec, where: "r2" });
    } catch (err) { error = `network error: ${err.message}`; }
  }
  const entries = [...byId.values()].sort((a, b) => windowOrd(b.id) - windowOrd(a.id));
  return { entries, error };
}

/** Save one window. Returns where it landed; falls back to this device if R2 refuses, and says
 *  so through `error` rather than pretending the upload happened. */
export async function put(rec) {
  if (tok()) {
    try {
      const r = await fetch(`${API}?id=${encodeURIComponent(rec.id)}`, {
        method: "PUT",
        headers: { "x-fm-token": tok(), "content-type": "application/json" },
        body: JSON.stringify(rec),
      });
      const d = await r.json();
      if (r.ok) {
        const local = readLocal();
        if (rec.id in local) { delete local[rec.id]; writeLocal(local); }
        return { where: "r2", entry: d.entry };
      }
      const local = readLocal();
      local[rec.id] = { ...rec, saved_at: new Date().toISOString().slice(0, 19) };
      writeLocal(local);
      return { where: "local", error: d.error || `HTTP ${r.status}` };
    } catch (err) {
      const local = readLocal();
      local[rec.id] = { ...rec, saved_at: new Date().toISOString().slice(0, 19) };
      writeLocal(local);
      return { where: "local", error: `network error: ${err.message}` };
    }
  }
  const local = readLocal();
  local[rec.id] = { ...rec, saved_at: new Date().toISOString().slice(0, 19) };
  writeLocal(local);
  return { where: "local" };
}

export async function remove(rec) {
  if (rec.where === "r2") {
    const r = await fetch(`${API}?id=${encodeURIComponent(rec.id)}`, {
      method: "DELETE", headers: { "x-fm-token": tok() },
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.error || `HTTP ${r.status}`);
    }
  }
  const local = readLocal();
  if (rec.id in local) { delete local[rec.id]; writeLocal(local); }
}
