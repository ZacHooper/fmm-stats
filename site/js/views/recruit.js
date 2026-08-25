/**
 * Recruitment — find players, and keep the shortlist.
 *
 * Three things that belonged together and were on two different pages plus a tab: searching the
 * save for a player, the capital-region origin rule that decides who we're allowed to sign, and
 * the shortlist itself. The shortlist is also the only thing in this app that WRITES — it goes
 * to R2 through a Pages Function, because a player you spot in-game on the phone exists nowhere
 * until it's recorded.
 *
 * The full player set (~1.3 MB over the wire) is fetched only when you search beyond our own
 * pyramid, so the common case stays cheap.
 */
import * as D from "../data.js";
import { playerTable, metricColumns } from "../table.js";
import { el, bar, num, money, monthYear, pill, toast, DASH, debounce } from "../ui.js";
import { openProfile, openCompare } from "../profile.js";

const API = "/api/shortlist";
const tok = () => localStorage.getItem(D.SHORTLIST_TOKEN_KEY) || "";

export async function view() {
  await D.loadMatches();
  const out = el("div");
  out.append(el("h2", { text: "Recruitment" }));

  const tabs = el("div.prow");
  const panel = el("div");
  const TABS = [
    ["Shortlist", shortlistPanel],
    ["Search the save", searchPanel],
    ["Capital region", capitalPanel],
  ];
  // Open on Search until a device token exists: the shortlist can't be read without one, so
  // landing there shows an empty table and looks broken rather than unconfigured.
  let active = tok() ? 0 : 1;
  const drawTabs = () => {
    tabs.replaceChildren(...TABS.map(([label], i) => el(`button.chip${i === active ? ".on" : ""}`, {
      text: label,
      onclick: async () => { active = i; drawTabs(); panel.replaceChildren(el("div.spinner", { text: "…" })); panel.replaceChildren(await TABS[i][1]()); },
    })));
  };
  drawTabs();
  out.append(tabs, panel);
  panel.append(await TABS[active][1]());
  return out;
}

// --------------------------------------------------------------------------- shortlist
async function shortlistPanel() {
  const wrap = el("div");
  const list = el("div");
  const status = el("span.count");

  const form = el("form.card", {
    onsubmit: async (e) => {
      e.preventDefault();
      const name = q("#sl-name").value.trim();
      if (!name) return toast("A name is required", true);
      if (!tok()) return toast("Save your device token first", true);
      const body = {
        name, tid: q("#sl-tid").value.trim() || null,
        positions: parsePositions(q("#sl-pos").value),
        note: q("#sl-note").value.trim(), source: "phone",
      };
      try {
        const r = await fetch(API, {
          method: "POST",
          headers: { "x-fm-token": tok(), "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json();
        if (!r.ok) return toast(d.error || `HTTP ${r.status}`, true);
        for (const id of ["#sl-name", "#sl-tid", "#sl-pos", "#sl-note"]) q(id).value = "";
        toast(`${name} added`);
        load();
      } catch (err) { toast(`Network error: ${err.message}`, true); }
    },
  }, [
    el("h4", { text: "Add a player" }),
    el("input.search", { id: "sl-name", placeholder: "Player name", required: true }),
    el("input.search", { id: "sl-tid", placeholder: "tid (optional)", inputmode: "numeric" }),
    el("input.search", { id: "sl-pos", placeholder: "Positions and familiarity — e.g. DL 18, DC 12" }),
    el("input.search", { id: "sl-note", placeholder: "Note — why he's worth a look" }),
    el("div.prow", {}, [el("button.btn", { type: "submit", text: "Add to shortlist" }),
      el("button.btn", { type: "button", text: "Reload", onclick: () => load() }), status]),
  ]);
  const q = (sel) => form.querySelector(sel);

  const search = el("input.search", { type: "search", placeholder: "Filter the shortlist…" });
  let rows = [];
  const drawList = () => {
    const f = search.value.trim().toLowerCase();
    const shown = rows.filter((r) => !f || JSON.stringify(r).toLowerCase().includes(f));
    list.replaceChildren(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Player", "tid", "Positions", "Note", "Added", "Source", ""]
        .map((h) => el("th", { text: h })))]),
      el("tbody", {}, shown.length ? shown.map((e2) => el("tr", {}, [
        el("td.name", {}, [e2.tid && D.S.players.has(Number(e2.tid))
          ? el("button.link", { text: e2.name, onclick: () => openProfile(Number(e2.tid)) })
          : el("span", { text: e2.name })]),
        el("td", { text: e2.tid ?? DASH }),
        el("td", { text: Object.entries(e2.positions || {}).map(([k, v]) => `${k} ${v}`).join(", ") || DASH }),
        el("td", { text: e2.note || DASH }),
        el("td", { text: (e2.added_at || "").slice(0, 10) || DASH }),
        el("td", { text: e2.source || DASH }),
        el("td", {}, [el("button.link", {
          text: "remove",
          onclick: async () => {
            if (!confirm(`Remove ${e2.name}?`)) return;
            const r = await fetch(`${API}?id=${encodeURIComponent(e2.id)}`,
              { method: "DELETE", headers: { "x-fm-token": tok() } });
            if (!r.ok) return toast("Delete failed", true);
            toast("Removed"); load();
          },
        })]),
      ])) : [el("tr", {}, [el("td.empty", { colspan: 7, text: "Nothing on the shortlist yet." })])]),
    ])]));
  };
  search.addEventListener("input", debounce(drawList, 140));

  async function load() {
    if (!tok()) { status.textContent = "no token"; drawList(); return; }
    status.textContent = "loading…";
    try {
      const r = await fetch(API, { headers: { "x-fm-token": tok() } });
      const d = await r.json();
      if (!r.ok) { status.textContent = d.error || `HTTP ${r.status}`; return; }
      rows = d.entries || [];
      status.textContent = `${d.count} shortlisted`;
      drawList();
    } catch (e) { status.textContent = `offline (${e.message})`; drawList(); }
  }

  wrap.append(form, el("div.tbar", {}, [search]), list, tokenCard(load));
  load();
  return wrap;
}

function tokenCard(after) {
  const input = el("input.search", { type: "password", placeholder: "Paste FM_SHORTLIST_TOKEN", autocomplete: "off" });
  return el("details.card", {}, [
    el("summary", { text: tok() ? "Device token saved ✓" : "Device token needed to read or write the shortlist" }),
    el("div", {}, [
      el("div.prow", {}, [input, el("button.btn", {
        text: "Save on this device",
        onclick: () => {
          const v = input.value.trim();
          if (!v) { localStorage.removeItem(D.SHORTLIST_TOKEN_KEY); return toast("Token cleared", true); }
          localStorage.setItem(D.SHORTLIST_TOKEN_KEY, v);
          input.value = "";
          toast("Token saved on this device");
          after?.();
        },
      })]),
      el("p.note", {
        html: "Kept in this browser's localStorage, never in the page source — a committed secret "
          + "is a published one. It gates writes so a stranger who finds the URL can't edit your "
          + "shortlist; it is not per-user auth, and it does reach the browser.",
      }),
    ]),
  ]);
}

const parsePositions = (text) => {
  const out = {};
  for (const part of String(text || "").split(/[,;]/)) {
    const m = part.trim().match(/^([A-Za-z]+)\s*[:= ]\s*(\d+)$/);
    if (m) out[m[1].toUpperCase()] = parseInt(m[2], 10);
  }
  return out;
};

// --------------------------------------------------------------------------- search
async function searchPanel() {
  const wrap = el("div");
  const msg = el("p.note");
  const holder = el("div");
  wrap.append(el("div.card", {}, [
    el("p.note", {
      html: "Our own pyramid is already loaded. Searching wider fetches every player in the save "
        + "(~1.3 MB) once — it's kept out of git and streamed from R2, so only this pays for it.",
    }),
    el("button.btn", { text: "Load every player in the save", onclick: () => go(true) }),
    msg,
  ]), holder);

  async function go(all) {
    if (all) {
      msg.textContent = "loading…";
      try { await D.loadAll((s) => { msg.textContent = s || ""; }); } catch (e) {
        msg.textContent = `couldn't load: ${e.message}`;
        return;
      }
      msg.textContent = `${D.S.players.size.toLocaleString()} players available`;
    }
    holder.replaceChildren(buildTable());
  }

  function buildTable() {
    const ourCid = D.ourLeagueCid();
    const pools = new Map();
    const rows = [];
    for (const p of D.S.players.values()) {
      const best = D.bestRole(p);
      if (!best) continue;
      const club = D.S.clubs.get(p.clubTid);
      const lg = club ? D.S.leagues.get(club.leagueCid) : null;
      rows.push({
        tid: p.tid, player: p, r: best, age: D.age(p.dob),
        club: club?.name || DASH, league: lg?.name || DASH,
        rep: lg?.reputation ?? null,
        ours: D.isOurs(p),
        _search: [p.name, club?.name, lg?.name, best.pos, best.role].filter(Boolean).join(" ").toLowerCase(),
      });
    }
    const selected = new Set();
    const cmp = el("button.btn", {
      text: "Compare (0)",
      onclick: () => (selected.size >= 2 ? openCompare([...selected]) : toast("Pick 2 or more", true)),
    });
    let arm = false;
    const armBtn = el("button.btn", {
      text: "Pick",
      onclick: () => {
        arm = !arm; armBtn.classList.toggle("on", arm);
        armBtn.textContent = arm ? "Picking" : "Pick";
        if (!arm) { selected.clear(); cmp.textContent = "Compare (0)"; tbl.redraw(); }
      },
    });
    const tbl = playerTable({
      key: "search",
      rows,
      catalogue: {
        player: { label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name, get: (r) => r.player.name },
        age: { label: "Age", group: "Identity", align: "num", get: (r) => r.age },
        pos: { label: "Pos", group: "Identity", get: (r) => r.r.pos },
        fam: { label: "Fam", group: "Identity", align: "num", sort: (r) => r.r.fam, render: (r) => bar(r.r.fam, { max: 20, lo: 60 }) },
        club: { label: "Club", group: "Identity", get: (r) => r.club },
        league: { label: "League", group: "Identity", get: (r) => r.league },
        rep: { label: "League rep", group: "Identity", align: "num", get: (r) => r.rep },
        rating: { label: "Rating", group: "Rating", align: "num", sort: (r) => r.r.eff, render: (r) => num(r.r.eff) },
        lvl: {
          label: "Level %ile", group: "Rating", align: "num",
          help: "Quality at that position in his own league",
          sort: (r) => r.r.lvlLeague, render: (r) => bar(r.r.lvlLeague),
        },
        lvlg: {
          label: "Level %ile (world)", group: "Rating", align: "num",
          help: "Quality at that position across every league in the save — the fair way to compare across divisions",
          sort: (r) => r.r.lvlGlobal, render: (r) => bar(r.r.lvlGlobal),
        },
        value: { label: "Value", group: "Contract", align: "num", sort: (r) => r.player.value, render: (r) => money(r.player.value) },
        wage: { label: "Wage/yr", group: "Contract", align: "num", sort: (r) => r.player.wage, render: (r) => money(r.player.wage) },
        expiry: { label: "Contract", group: "Contract", sort: (r) => r.player.expiry || "9999", render: (r) => monthYear(r.player.expiry) },
        ...metricColumns(D, { agg: D.S.matchAgg }),
      },
      presets: { "Scouting": ["age", "club", "league", "rating", "lvlg", "value", "expiry"] },
      sticky: ["player"],
      defaults: ["age", "pos", "fam", "club", "league", "rating", "lvlg", "value", "expiry"],
      sort: { by: "lvlg", dir: "desc" },
      searchPlaceholder: "Search by name, club or league…",
      toolbar: [armBtn, cmp],
      rowClass: (r) => (selected.has(r.tid) ? "picked" : null),
      onRow: (r) => {
        if (!arm) return openProfile(r.tid);
        if (selected.has(r.tid)) selected.delete(r.tid);
        else if (selected.size < 4) selected.add(r.tid);
        else return toast("Four at a time", true);
        cmp.textContent = `Compare (${selected.size})`;
        tbl.redraw();                              // paint the selection back onto the rows
      },
      empty: "Nobody matches. Load every player if you're looking outside our pyramid.",
    });
    return tbl.node;
  }

  go(false);
  return wrap;
}

// --------------------------------------------------------------------------- capital rule
async function capitalPanel() {
  const wrap = el("div");
  wrap.append(el("div.card", {}, [el("p.note", {
    html: "The self-imposed rule: a new signing's <b>career-origin club</b> must be in Region "
      + "Hovedstaden. Existing squad members are grandfathered and academy products always "
      + "qualify. Origin is exact — a player's career-history chain head is a stored pointer in "
      + "his attribute record, not a positional guess.",
  })]));
  const eligible = new Set(D.S.ours.capital_eligible || []);
  const rows = [];
  for (const p of D.ourPlayers()) {
    const best = D.bestRole(p);
    if (!best) continue;
    rows.push({
      tid: p.tid, player: p, r: best, age: D.age(p.dob),
      origin: D.S.ours.origin?.[String(p.tid)] || null,
      ok: eligible.has(p.tid),
      _search: [p.name, D.S.ours.origin?.[String(p.tid)] || ""].join(" ").toLowerCase(),
    });
  }
  wrap.append(playerTable({
    key: "capital", rows,
    catalogue: {
      player: { label: "Player", group: "Identity", cls: "name", sort: (r) => r.player.name, get: (r) => r.player.name },
      age: { label: "Age", group: "Identity", align: "num", get: (r) => r.age },
      pos: { label: "Pos", group: "Identity", get: (r) => r.r.pos },
      origin: { label: "Origin club", group: "Identity", get: (r) => r.origin },
      ok: { label: "Capital", group: "Identity", sort: (r) => (r.ok ? 1 : 0), render: (r) => (r.ok ? pill("✓", "good") : pill("outside", "flat")) },
      rating: { label: "Rating", group: "Rating", align: "num", sort: (r) => r.r.eff, render: (r) => num(r.r.eff) },
      lvl: { label: "Level %ile", group: "Rating", align: "num", sort: (r) => r.r.lvlLeague, render: (r) => bar(r.r.lvlLeague) },
    },
    sticky: ["player"],
    defaults: ["age", "pos", "origin", "ok", "rating", "lvl"],
    sort: { by: "ok", dir: "desc" },
    onRow: (r) => openProfile(r.tid),
  }).node);
  wrap.append(el("p.note", {
    text: `${eligible.size} of our ${rows.length} rated players have a capital-region origin club.`,
  }));
  return wrap;
}
