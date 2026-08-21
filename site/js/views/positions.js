/**
 * Positions — depth chart per role with a keep / loan / sell read.
 *
 * The one view whose numbers are computed on the SERVER (`dashboard/positions.py`, shared with
 * the Streamlit page). Ability ranks need the game's overall-ability number, and that number
 * never leaves the build machine — so unlike everywhere else in this app, these figures are
 * pinned to the tactic the export was built with rather than the one selected in the header.
 * The banner says so rather than letting the header quietly lie.
 */
import * as D from "../data.js";
import { el, bar, num, money, monthYear, pill, DASH } from "../ui.js";
import { openProfile } from "../profile.js";

export async function view() {
  const P = await D.loadPositions();
  await D.loadMatches();
  if (P.error) return el("div.card", {}, [el("b", { text: "No position review" }), el("p.note", { text: P.error })]);
  const snap = P.snapshot;
  const ladder = snap.ladder;
  const name = (tid) => D.S.players.get(tid)?.name || `#${tid}`;
  const out = el("div");

  out.append(el("h2", { text: `Position review · ${snap.division}` }));
  if (snap.method !== D.S.method) {
    out.append(el("div.card", {}, [el("p.note", {
      html: `These figures were computed for <b>${snap.method}</b>, not the ${D.S.method} you have `
        + `selected. Ability ranks need the raw ability number, which stays on the machine that `
        + `built this export — so re-export with <code>--method ${D.S.method}</code> to see this `
        + `page under that tactic. Everything else in the app follows the header.`,
    })]));
  }

  // ---- where the window money goes
  out.append(el("h3", { text: "Where the window money goes" }));
  out.append(el("div.scroll", {}, [el("table", {}, [
    el("thead", {}, [el("tr", {}, ["Role", "Owned/slots", "Best available", "Pos", "Fam",
      `Rank in ${snap.division}`, "Div %ile", "Fit %ile", "Avg age", "Read"]
      .map((h, i) => el(`th${[1, 4, 5, 6, 7, 8].includes(i) ? ".num" : ""}`, { text: h })))]),
    el("tbody", {}, P.summary.map((r) => el("tr.click", {
      onclick: () => openProfile(r.best_tid, { role: r.role }),
    }, [
      el("td.name", { text: r.role }),
      el("td.num", { text: `${r.owned} / ${r.slots}` }),
      el("td", { text: r.best }), el("td", { text: r.position }),
      el("td.num", {}, [bar(r.fam, { max: 20, lo: 60 })]),
      el("td.num", { text: r.rank_ours ? `${r.rank_ours[0]} / ${r.rank_ours[1]}` : DASH }),
      el("td.num", {}, [bar(r.div_pct)]), el("td.num", {}, [bar(r.fit_div)]),
      el("td.num", { text: r.avg_age == null ? DASH : num(r.avg_age, 1) }),
      el("td", {}, [pill(r.read)]),
    ]))),
  ])]));
  out.append(el("p.note", {
    html: "Sorted weakest first — the top row is where a signing changes most. <b>Div %ile</b> is "
      + "level (ability); <b>Fit %ile</b> is tactic fit. Ability is CURRENT ability, so a teenage "
      + "prospect ranks near the bottom of a senior division however good he'll become — those rows "
      + "read <i>Prospect starting</i>, which means buy cover, not buy a replacement.",
  }));

  // ---- role pills to filter the depth charts
  let only = null;
  const charts = el("div");
  const pills = el("div.prow", {}, [
    el("button.chip.on", { text: "All", onclick: (e) => setOnly(null, e.target) }),
    ...P.depth.map((d) => el("button.chip", { text: d.role, onclick: (e) => setOnly(d.role, e.target) })),
  ]);
  function setOnly(role, btn) {
    only = role;
    for (const c of pills.querySelectorAll(".chip")) c.classList.toggle("on", c === btn);
    drawCharts();
  }

  function drawCharts() {
    charts.replaceChildren();
    for (const d of P.depth) {
      if (only && d.role !== only) continue;
      charts.append(el("h3", { text: `${d.role} · ${d.players.length} owned · ${d.slots} start` }));
      charts.append(el("div.scroll", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, ["#", "Player", "Age", "Pos", "Fam", "Rating", "Fit %ile",
          ...ladder.map((l) => l.name), "Contract", "Wage/yr", "Last season", "Also", "Read"]
          .map((h, i) => el(`th${i === 0 || (i >= 2 && i <= 6 + ladder.length) || h === "Wage/yr" ? ".num" : ""}`, { text: h })))]),
        el("tbody", {}, d.players.map((pl) => {
          const p = D.S.players.get(pl.tid);
          const roles = p ? D.playerRoles(p) : [];
          const rr = roles.find((x) => x.pos === pl.position);
          const agg = D.S.matchAgg?.get(pl.tid);
          return el("tr.click", { onclick: () => openProfile(pl.tid, { role: d.role }) }, [
            el("td.num", { text: pl.depth }),
            el("td.name", { text: name(pl.tid) }),
            el("td.num", { text: p ? (D.age(p.dob) ?? DASH) : DASH }),
            el("td", { text: pl.position }),
            el("td.num", {}, [bar(pl.familiarity, { max: 20, lo: 60 })]),
            el("td.num", { text: rr ? num(rr.eff) : DASH }),
            el("td.num", {}, [bar(pl.fit_pctile_division)]),
            ...ladder.map((l) => {
              const v = pl.ability_rank?.[String(l.cid)];
              return el("td.num", { text: v ? `${v[0]} / ${v[1]}` : DASH });
            }),
            el("td", { text: p ? monthYear(p.expiry) : DASH }),
            el("td.num", { text: p ? money(p.wage) : DASH }),
            el("td", { text: agg ? `${agg.starts}/${agg.apps} · ${agg.min}m · ${agg.rating ? num(agg.rating, 2) : DASH}` : DASH }),
            el("td", { text: pl.also }),
            el("td", {}, [pill(pl.read)]),
          ]);
        })),
      ])]));

      // loan destinations for anyone behind the starters
      const surplus = d.players.filter((pl) => pl.depth > d.slots && Object.keys(pl.hosts || {}).length);
      if (surplus.length) {
        const body = el("div", {}, surplus.map((pl) => el("p", {}, [
          el("b", { text: name(pl.tid) }), ` (${pl.position})`,
          ...Object.entries(pl.hosts).flatMap(([cid, hosts]) => {
            const lg = ladder.find((l) => String(l.cid) === cid)?.name || `#${cid}`;
            const n1 = pl.first_choice_below?.[cid] ?? 0;
            return [el("br"), el("span.dim", { text: `${lg}: first choice at ${n1} club(s) — ` }),
              hosts.slice(0, 3).map((h) => `${h[0]} ${h[1]}/${h[2]}`).join(" · ")];
          }),
        ])));
        charts.append(el("details", {}, [
          el("summary", { text: `Loan destinations for the ${surplus.length} behind the starters` }),
          el("div.card", {}, [body, el("p.note", {
            text: "Rank inside that club's squad at his position — 1/n means he'd be their first "
              + "choice with n-1 bodies behind him, so he'd actually play.",
          })]),
        ]));
      }
    }
  }
  drawCharts();
  out.append(pills, charts);

  out.append(el("details", {}, [
    el("summary", { text: "How the Read column is decided" }),
    el("div.card", {}, [el("p.note", {
      html: "<b>Keep — starter</b>: inside the role's slot count; flagged <i>upgrade target</i> if "
        + "his division ability percentile is under 40. <b>Keep — cover</b>: first man outside the "
        + "XI. <b>Cover only — primary X</b>: not his main role, so read him in the X table. "
        + "<b>Keep — reserves</b>: 18 or younger. <b>Loan out</b>: under 24 and a lower division "
        + "would start him. <b>Sell / release</b>: 23+ and bottom third of our division, or nobody "
        + "below us would start him. It can't see morale, form or what you're being offered — "
        + "overrule it freely.",
    })]),
  ]));
  return out;
}
