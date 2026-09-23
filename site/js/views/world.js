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

// One colour per division tier, top flight hottest. The bottom tier ("Danish Lower Division", ~80
// clubs — more than the other five combined) is a muted grey on purpose: it would otherwise
// drown out the divisions a manager actually reads this map for.
const TIER_COLOURS = { 1: "#c0262d", 2: "#e8701a", 3: "#d4a300", 4: "#2e9e4f", 5: "#2f6fd0", 6: "#8a8f98" };
const tierColour = (t) => TIER_COLOURS[t] || "#555b66";

function baseMap(container) {
  const L = window.L;
  const map = L.map(container, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);
  return map;
}

/**
 * A map of round pins that never hide one another.
 *
 * The save places a club through club -> stadium -> CITY, and only the city has coordinates, so
 * every club in a city lands on exactly the same spot (FCK sits precisely under Frem; 84 of the
 * 162 Danish clubs share a point with another), and at country zoom clubs a few kilometres apart
 * overlap as well (Frem, FCK, Brøndby, Lyngby and Nordsjælland are one knot around Copenhagen).
 *
 * So after every zoom the pins are laid out in SCREEN pixels: clubs on the same point are seeded
 * around it on a sunflower spiral (`order` decides who takes the centre), then overlapping pairs
 * are pushed apart. Not fully apart: at country zoom that turns Denmark into a honeycomb that no
 * longer looks like the map, so pins also shrink when zoomed out and may overlap by up to
 * OVERLAP of their size — every pin stays visible and clickable, and the map keeps its shape.
 * The offset goes into the marker's icon anchor, so the pin's latlng stays the true one.
 */
const OVERLAP = 0.3;
const pinScale = (zoom) => (zoom >= 9 ? 1 : zoom >= 8 ? 0.85 : zoom >= 7 ? 0.72 : 0.6);
function pinLayer(map, { order }) {
  const L = window.L;
  const layer = L.featureGroup().addTo(map);
  let pins = [];                                  // { p, style, marker }

  const iconFor = (style, dx, dy, k = 1) => {
    const size = Math.round(2 * (style.r * k + style.ringW));
    return L.divIcon({
      className: "mapdot",
      html: `<span style="display:block;box-sizing:border-box;width:${size}px;height:${size}px;`
        + `border-radius:50%;background:${style.fill};border:${style.ringW}px solid ${style.ring};`
        + `opacity:.95"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2 - dx, size / 2 - dy],
      popupAnchor: [dx, dy - size / 2],
    });
  };

  function relayout() {
    if (!pins.length) return;
    const k = pinScale(map.getZoom());
    const pos = pins.map((x) => map.latLngToLayerPoint([x.p.lat, x.p.lon]));
    const base = pos.map((q) => ({ x: q.x, y: q.y }));
    const rad = pins.map((x) => x.style.r * k + x.style.ringW);
    // seed: same-point groups on a spiral, so the push below has a direction to work with
    const groups = new Map();
    pins.forEach((x, i) => {
      const k = `${x.p.lat},${x.p.lon}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(i);
    });
    const cur = base.map((q) => ({ ...q }));
    for (const g of groups.values()) {
      if (g.length < 2) continue;
      g.sort((i, j) => order(pins[i].p, pins[j].p));
      g.forEach((i, n) => {
        const r = 9 * k * Math.sqrt(n + 0.6), a = n * 2.39996;
        cur[i].x += r * Math.cos(a); cur[i].y += r * Math.sin(a);
      });
    }
    // push overlapping pairs apart; the higher-ranked pin (by `order`) moves less
    const rank = pins.map((_, i) => i).sort((i, j) => order(pins[i].p, pins[j].p));
    const weight = new Array(pins.length);
    rank.forEach((i, n) => { weight[i] = 0.35 + 0.3 * (n / Math.max(1, pins.length - 1)); });
    for (let it = 0; it < 60; it++) {
      let moved = false;
      for (let i = 0; i < pins.length; i++) {
        for (let j = i + 1; j < pins.length; j++) {
          const dx = cur[j].x - cur[i].x, dy = cur[j].y - cur[i].y;
          // Same point: always fully apart, or one pin sits exactly under the other. Otherwise
          // a partial overlap is allowed, which is what keeps the map's shape.
          const same = pins[i].p.lat === pins[j].p.lat && pins[i].p.lon === pins[j].p.lon;
          const need = (rad[i] + rad[j]) * (same ? 1 : 1 - OVERLAP) + 1;
          const d2 = dx * dx + dy * dy;
          if (d2 >= need * need) continue;
          const d = Math.sqrt(d2) || 0.01;
          const ux = d2 ? dx / d : Math.cos(i + j), uy = d2 ? dy / d : Math.sin(i + j);
          const push = need - d;
          const wi = weight[i] / (weight[i] + weight[j]), wj = 1 - wi;
          cur[i].x -= ux * push * wi; cur[i].y -= uy * push * wi;
          cur[j].x += ux * push * wj; cur[j].y += uy * push * wj;
          moved = true;
        }
      }
      if (!moved) break;
    }
    pins.forEach((x, i) => x.marker.setIcon(iconFor(x.style, cur[i].x - base[i].x, cur[i].y - base[i].y, k)));
  }
  map.on("zoomend", relayout);

  return {
    layer,
    /** Replace every pin. `entries` is [{ p, style: {fill, r, ring, ringW, z}, popup }]. */
    set(entries) {
      layer.clearLayers();
      pins = entries.map(({ p, style, popup }) => ({
        p, style,
        marker: L.marker([p.lat, p.lon], {
          icon: iconFor(style, 0, 0), zIndexOffset: style.z || 0, title: p.club,
        }).bindPopup(popup).addTo(layer),
      }));
    },
    relayout,
  };
}

function fitTo(map, pins, pts) {
  if (pts.length) map.fitBounds(window.L.latLngBounds(pts.map((p) => [p.lat, p.lon])).pad(0.2), { maxZoom: 10 });
  else map.setView([56.0, 10.0], 6);   // Denmark, roughly — a reasonable empty-map default
  pins.relayout();                     // fitBounds may not change zoom, and then no zoomend fires
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
  // League filter, ordered down the pyramid. Tier 5 is split into regional series groups, so
  // each tier that has more than one league also gets an "all of tier N" option.
  const leagues = [...new Map(dk.map((p) => [p.league, p.tier])).entries()]
    .sort((a, b) => (a[1] ?? 99) - (b[1] ?? 99) || String(a[0]).localeCompare(String(b[0])));
  const tiers = [...new Set(leagues.map(([, t]) => t))];
  const leagueSel = el("select.btn", {}, [
    el("option", { value: "", text: "All divisions" }),
    ...tiers.flatMap((t) => {
      const inTier = leagues.filter(([, lt]) => lt === t);
      return [
        inTier.length > 1 ? el("option", { value: `tier:${t}`, text: `Tier ${t} — all ${inTier.length} groups` }) : null,
        ...inTier.map(([name]) => el("option", { value: `league:${name}`, text: `${t ? `${t} · ` : ""}${name}` })),
      ].filter(Boolean);
    }),
  ]);
  const legend = el("div.prow", { style: "font-size:12.5px" }, tiers.map((t) => el("span", {
    style: "display:inline-flex;align-items:center;gap:5px;margin-right:8px",
  }, [
    el("span", { style: `display:inline-block;width:11px;height:11px;border-radius:50%;`
      + `background:${tierColour(t)};border:1px solid #fff;box-shadow:0 0 0 1px ${tierColour(t)}` }),
    `Tier ${t}`,
  ])));
  const dkDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  const dkNote = el("p.note");
  wrap.append(el("div.tbar", {}, [leagueSel]), legend, dkDiv, dkNote);

  wrap.append(el("h3", { text: "Our squad's origin clubs" }));
  const originDiv = el("div", { style: "height:380px;border-radius:8px;overflow:hidden" });
  wrap.append(originDiv);
  wrap.append(el("p.note", {
    text: `${origins.length} origin clubs shown for the current squad; overlapping pins are `
      + "nudged apart, and our own academy has the dark ring."
      + (unresolved ? ` ${unresolved} player(s)' origin club couldn't be placed on the map — ` +
        "that means our data can't resolve it, not that they don't have one." : ""),
  }));

  // Deferred to the next frame: `baseMap` needs the container's real on-page size (Leaflet
  // measures it at construction time), and these divs aren't attached to the document until
  // AFTER this function's promise resolves and the caller replaces the panel's children with
  // it — so building the map inline here would measure a detached, zero-size node.
  requestAnimationFrame(() => {
    const L = window.L;
    const ourTids = new Set(D.S.ours.clubs || []);
    const map = baseMap(dkDiv);
    const byTier = (a, b) => (a.tier ?? 99) - (b.tier ?? 99) || String(a.club).localeCompare(String(b.club));
    const dkPins = pinLayer(map, {
      order: (a, b) => (ourTids.has(b.tid) - ourTids.has(a.tid)) || byTier(a, b),
    });
    const drawDk = () => {
      const want = leagueSel.value;
      const shown = dk.filter((p) => !want
        || (want.startsWith("tier:") ? String(p.tier) === want.slice(5) : p.league === want.slice(7)));
      dkPins.set(shown.map((p) => {
        const ours = ourTids.has(p.tid);
        return {
          p,
          style: { fill: tierColour(p.tier), r: ours ? 8 : 7, ring: ours ? "#111" : "#fff",
                   ringW: ours ? 3 : 1.5, z: ours ? 1000 : (10 - (p.tier ?? 9)) * 100 },
          popup: popupHtml(p, p.tier ? `Tier ${p.tier} · ${p.league}` : p.league),
        };
      }));
      fitTo(map, dkPins, shown);
      dkNote.textContent = `${shown.length} of ${dk.length} clubs with a resolvable stadium `
        + "location, coloured by division tier (1 = top flight); our club has the dark ring. "
        + "Pins mark each club's CITY (the save has no ground coordinates), and pins that would "
        + "overlap are nudged apart so none hides another; zoom in and they settle back towards "
        + "their city. Tap a pin for the club, ground and capacity.";
    };
    leagueSel.addEventListener("change", drawDk);
    drawDk();
    const omap = baseMap(originDiv);
    const oPins = pinLayer(omap, {
      order: (a, b) => (ourTids.has(b.tid) - ourTids.has(a.tid))
        || b.players.length - a.players.length || a.club.localeCompare(b.club),
    });
    oPins.set(origins.map((p) => {
      const ours = ourTids.has(p.tid);
      return {
        p,
        style: { fill: "#2f6fd0", r: ours ? 8 : 7, ring: ours ? "#111" : "#fff",
                 ringW: ours ? 3 : 1.5, z: ours ? 1000 : 0 },
        popup: popupHtml(p, p.players.join(", ")),
      };
    }));
    fitTo(omap, oPins, origins);
  });

  return wrap;
}
