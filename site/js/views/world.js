/**
 * World — the reputation ladder (leagues + nations), and two maps: our nation's clubs by
 * division, and the stadiums of our current squad's origin clubs.
 *
 * Leagues needs no fetch of its own: `D.S.leagues` is already loaded from core.json (it used to
 * live on the Opposition page as the "League reputation ladder" — moved here since it's a
 * world-wide reference table, not something specific to scouting one opponent). Nations and the
 * two maps come from api/world.json, fetched only when this page is opened.
 */
import * as D from "../data.js";
import { el, clear, bar, num, pill, DASH } from "../ui.js";

const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";

let leafletPromise = null;
/** Loads Leaflet from a CDN on first use only — the site has no bundler and no other page
 *  needs a mapping library, so this stays out of index.html and out of every other view's
 *  payload. Cached so switching tabs back to Maps doesn't re-fetch or re-inject. */
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      document.head.append(el("link", { rel: "stylesheet", href: LEAFLET_CSS }));
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("Leaflet failed to load"));
    document.head.append(script);
  });
  return leafletPromise;
}

export async function view() {
  const world = await D.loadWorld();
  const out = el("div");
  out.append(el("h2", { text: "World" }));

  const tabs = el("div.prow");
  const panel = el("div");
  const TABS = [
    ["Leagues", leaguesPanel],
    ["Clubs", clubsPanel],
    ["Nations", () => nationsPanel(world)],
    ["Maps", () => mapsPanel(world)],
  ];
  let active = 0;
  const drawTabs = () => {
    tabs.replaceChildren(...TABS.map(([label], i) => el(`button.chip${i === active ? ".on" : ""}`, {
      text: label,
      onclick: async () => {
        active = i; drawTabs();
        clear(panel).append(el("div.spinner", { text: "…" }));
        clear(panel).append(await TABS[i][1]());
      },
    })));
  };
  drawTabs();
  out.append(tabs, panel);
  panel.append(await TABS[active][1]());
  return out;
}

// --------------------------------------------------------------------------- leagues
function leaguesPanel() {
  const ourCid = D.ourLeagueCid();
  const lgs = [...D.S.leagues.values()].filter((l) => l.reputation != null)
    .sort((a, b) => b.reputation - a.reputation);
  const ourLg = D.S.leagues.get(ourCid);
  const ourRank = lgs.findIndex((l) => l.cid === ourCid) + 1;
  const wrap = el("div");
  wrap.append(el("h3", { text: `League reputation ladder · ${lgs.length} leagues` }));
  // No cutoff. A top-60 truncation hid most of the pyramid, including divisions we could
  // plausibly loan into — and a silently truncated list reads as a complete one.
  const nationFilter = el("select.btn");
  const nations = [...new Set(lgs.map((l) => l.nation).filter(Boolean))].sort();
  nationFilter.append(el("option", { value: "", text: "All nations" }),
    ...nations.map((n) => el("option", { value: n, text: n })));
  const ladderBox = el("div");
  const drawLadder = () => {
    const want = nationFilter.value;
    const rows = lgs.filter((l) => !want || l.nation === want);
    ladderBox.replaceChildren(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["#", "League", "Nation", "Reputation", "Skill idx", "Clubs", "Rated"]
        .map((h, i) => el(`th${i === 0 || i >= 3 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, rows.map((l) => el("tr", {}, [
        el("td.num", { text: lgs.indexOf(l) + 1 }),
        el("td.name", {}, [l.name, l.cid === ourCid ? pill(" us", "good") : null]),
        el("td", { text: l.nation || DASH }),
        el("td.num", { text: l.reputation }),
        el("td.num", {}, [bar(l.skillIdx)]),
        el("td.num", { text: l.clubs || DASH }),
        el("td.num", { text: l.rated ?? DASH }),
      ]))),
    ])]), el("p.note", {
      html: "<b>Reputation</b> is a value parsed straight from each competition record. "
        + "<b>Skill idx</b> is the average player ability in that league normalised 0-100 across "
        + "ranked leagues — a CA-derived index in the same sanctioned form as a Level percentile, "
        + "never the number itself. Only leagues with 20+ rated players get one. "
        + "<b>Clubs</b> counts actual club records, not the competition record's member count — "
        + "that field is unreliable (it reads 5 for a 12-team division), so it isn't shown. "
        + (ourLg ? `<br>${ourLg.name}: reputation ${ourLg.reputation}, `
          + `skill idx ${ourLg.skillIdx ?? "—"}, ranked ${ourRank} of ${lgs.length} loaded leagues.` : ""),
    }));
  };
  nationFilter.addEventListener("change", drawLadder);
  drawLadder();
  wrap.append(el("div.tbar", {}, [nationFilter]), ladderBox);
  return wrap;
}

// --------------------------------------------------------------------------- clubs
function clubsPanel() {
  const ourTids = new Set(D.S.ours.clubs || []);
  const clubs = [...D.S.clubs.values()].filter((c) => c.reputation != null)
    .map((c) => ({ ...c, leagueName: D.S.leagues.get(c.leagueCid)?.name || null }))
    .sort((a, b) => b.reputation - a.reputation);
  const wrap = el("div");
  wrap.append(el("h3", { text: `Club reputation · ${clubs.length} clubs` }));

  const nationFilter = el("select.btn");
  const nations = [...new Set(clubs.map((c) => c.nation).filter(Boolean))].sort();
  nationFilter.append(el("option", { value: "", text: "All nations" }),
    ...nations.map((n) => el("option", { value: n, text: n })));

  const leagueFilter = el("select.btn");
  const drawLeagueOptions = () => {
    const want = nationFilter.value;
    const inScope = want ? clubs.filter((c) => c.nation === want) : clubs;
    const lgs = [...new Map(inScope.filter((c) => c.leagueName)
      .map((c) => [c.leagueCid, c.leagueName])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    const prev = leagueFilter.value;
    leagueFilter.replaceChildren(el("option", { value: "", text: "All leagues" }),
      ...lgs.map(([cid, name]) => el("option", { value: cid, text: name })));
    leagueFilter.value = lgs.some(([cid]) => String(cid) === prev) ? prev : "";
  };

  const clubBox = el("div");
  const drawClubs = () => {
    const wantNation = nationFilter.value;
    const wantLeague = leagueFilter.value;
    const rows = clubs.filter((c) => (!wantNation || c.nation === wantNation)
      && (!wantLeague || String(c.leagueCid) === wantLeague));
    clubBox.replaceChildren(el("div.scroll", {}, [el("table", {}, [
      el("thead", {}, [el("tr", {}, ["#", "Club", "Nation", "League", "Reputation", "Squad"]
        .map((h, i) => el(`th${i === 0 || i === 4 || i === 5 ? ".num" : ""}`, { text: h })))]),
      el("tbody", {}, rows.map((c) => el("tr", {}, [
        el("td.num", { text: clubs.indexOf(c) + 1 }),
        el("td.name", {}, [c.name, ourTids.has(c.tid) ? pill(" us", "good") : null]),
        el("td", { text: c.nation || DASH }),
        el("td", { text: c.leagueName || DASH }),
        el("td.num", { text: c.reputation }),
        el("td.num", { text: c.players }),
      ]))),
    ])]), el("p.note", {
      text: `${rows.length} of ${clubs.length} clubs shown. Reputation is parsed straight from `
        + "each club's own record (distinct from its league's reputation, on the Leagues tab). "
        + "Only clubs with a parsed squad appear at all — an empty club can't be rendered "
        + "anywhere on the site.",
    }));
  };
  nationFilter.addEventListener("change", () => { drawLeagueOptions(); drawClubs(); });
  leagueFilter.addEventListener("change", drawClubs);
  drawLeagueOptions();
  drawClubs();
  wrap.append(el("div.tbar", {}, [nationFilter, leagueFilter]), clubBox);
  return wrap;
}

// --------------------------------------------------------------------------- nations
function nationsPanel(world) {
  const wrap = el("div");
  const rows = world?.nations || [];
  if (!rows.length) {
    wrap.append(el("p.note", { text: "No nation data in this export." }));
    return wrap;
  }
  wrap.append(el("h3", { text: `World ranking · ${rows.length} nations` }));
  wrap.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["#", "Nation", "Points", "Coefficient", "Rival"]
      .map((h, i) => el(`th${i === 0 || i === 2 || i === 3 ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, rows.map((n) => el("tr", {}, [
      el("td.num", { text: n.rank }),
      el("td.name", { text: n.name }),
      el("td.num", { text: n.points == null ? DASH : num(n.points, 0) }),
      el("td.num", { text: n.coefficient == null ? DASH : num(n.coefficient, 1) }),
      el("td", { text: n.rival || DASH }),
    ]))),
  ])]));
  wrap.append(el("p.note", {
    text: "World ranking + UEFA-style coefficient (sum of the nation's own competition history), "
      + "parsed from the save's national-team records. Only ranked nations are shown.",
  }));
  return wrap;
}

// --------------------------------------------------------------------------- maps
function popupHtml(p, extra) {
  const bits = [`<b>${p.club}</b>`];
  if (p.stadium) bits.push(p.stadium);
  if (p.capacity) bits.push(`${p.capacity.toLocaleString()} capacity`);
  if (extra) bits.push(extra);
  return bits.join("<br>");
}

function buildMap(container, points, popupFor) {
  const L = window.L;
  const map = L.map(container, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);
  const markers = points.map((p) => L.marker([p.lat, p.lon]).bindPopup(popupFor(p)));
  if (markers.length) {
    const group = L.featureGroup(markers).addTo(map);
    map.fitBounds(group.getBounds().pad(0.2));
  } else {
    map.setView([56.0, 10.0], 6);   // Denmark, roughly — a reasonable empty-map default
  }
  return map;
}

async function mapsPanel(world) {
  const wrap = el("div");
  try {
    await loadLeaflet();
  } catch (e) {
    wrap.append(el("p.note", { text: `Maps unavailable: ${e.message}` }));
    return wrap;
  }

  const dk = world?.places?.denmark || [];
  const origins = world?.places?.origins || [];
  const unresolved = world?.origins_unresolved ?? 0;

  wrap.append(el("h3", { text: `${world?.our_nation || "Our nation"}'s clubs by division` }));
  const dkDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  wrap.append(dkDiv);
  wrap.append(el("p.note", {
    text: `${dk.length} clubs with a resolvable stadium location, coloured by division tier `
      + "(1 = top flight). Tap a pin for the club, ground and capacity.",
  }));

  wrap.append(el("h3", { text: "Our squad's origin clubs" }));
  const originDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  wrap.append(originDiv);
  wrap.append(el("p.note", {
    text: `${origins.length} origin clubs shown for the current squad.`
      + (unresolved ? ` ${unresolved} player(s)' origin club couldn't be placed on the map — ` +
        "that means our data can't resolve it, not that they don't have one." : ""),
  }));

  // Deferred to the next frame: `buildMap` needs the container's real on-page size (Leaflet
  // measures it at construction time), and these divs aren't attached to the document until
  // AFTER this function's promise resolves and the caller replaces the panel's children with
  // it — so building the map inline here would measure a detached, zero-size node.
  requestAnimationFrame(() => {
    buildMap(dkDiv, dk, (p) => popupHtml(p, p.tier ? `Tier ${p.tier} · ${p.league}` : p.league));
    buildMap(originDiv, origins, (p) => popupHtml(p, p.players.join(", ")));
  });

  return wrap;
}
