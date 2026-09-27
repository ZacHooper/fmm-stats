/**
 * Registration — the squad we are allowed to field, under a rule FMM22 does not enforce. Lives
 * on the Squad page: the list each player is on is one more column there (filterable, so "show
 * me the B-list" is a column filter), the quotas are one KPI card, and the saved windows sit
 * under the table.
 *
 * The Danish rulebook (docs/danish-registration-rules.md) caps the A-list at 25 and, in the top
 * two tiers, requires 8 home-grown players on it of whom at least 4 were trained at the club
 * itself; the B-list takes an unlimited number of players who were under 21 at the last new
 * year, and does not touch the cap. None of that exists in the save.
 *
 * The B-list is free, so the obvious move is to park every U21 on it — but the home-grown
 * minimums are counted on the A-LIST, and most home-grown players are young. Leaving a
 * club-trained 21-year-old on the B-list to save a slot can cost a home-grown credit and shrink
 * the A-list by one, which is the trade the card's colour shows while you make it.
 *
 * The assignment is per-device state (localStorage, keyed by snapshot). It is a plan, not a fact
 * about the save — nothing here is written back. A snapshot with no plan of its own starts from
 * the newest plan this browser holds for an earlier snapshot, so a new export carries your lists
 * forward instead of starting blank.
 *
 * A plan can be SAVED AGAINST A TRANSFER WINDOW (regwindows.js) — the record of what was actually
 * registered, and the natural starting point for the next window's plan ("Load into plan").
 */
import * as D from "./data.js";
import { el, bar, pill, DASH, toast, sheet } from "./ui.js";
import * as W from "./regwindows.js";

const A = "A", B = "B", OUT = "-";
const LIST_LABEL = { A: "A-list", B: "B-list", "-": "Unregistered" };
const PLAN_KEY = /^fm:registration:(\d{4}):(.+)$/;

/**
 * Everything registration contributes to the Squad page, or null when this export has no
 * registration data. `squadRows` are the Squad table's own rows (never shortlist rows); each
 * one we hold registration facts for gets `row.h`. `redraw` repaints the host table.
 */
export async function registrationKit({ squadRows, redraw }) {
  const R = await D.loadRegistration();
  if (!R || !R.rules || !R.players?.length) return null;

  const rules = R.rules;
  const reg = new Map();
  for (const row of R.players) {
    const o = {};
    R.fields.forEach((f, i) => { o[f] = row[i]; });
    reg.set(o.tid, o);
  }
  const rows = [];
  for (const r of squadRows) {
    const h = reg.get(r.tid);
    if (!h) continue;                          // no dob, so no window and no verdict
    r.h = h;
    rows.push(r);
  }
  const byTid = new Map(rows.map((r) => [r.tid, r]));
  const posOf = (r) => r.roles?.[0]?.pos || null;

  // ---- the plan ------------------------------------------------------------------
  const snap = D.S.index.snapshot;
  const KEY = `fm:registration:${snap.season}:${snap.phase}`;
  let plan = load(KEY);
  if (!plan) {
    const prev = previousPlan(KEY);
    plan = {};
    for (const r of rows) {
      const l = prev?.[r.tid];
      // Carried forward: still here keeps his list, unless he has aged out of the B-list —
      // then he is unregistered, which the card flags as a decision to make.
      if (l != null) plan[r.tid] = l === B && !r.h.b_list ? OUT : l;
      else plan[r.tid] = r.h.b_list ? B : (prev ? OUT : A);
    }
    save(KEY, plan);
  }
  // A player who arrived since the plan was saved has no entry yet; default him rather than
  // dropping him, so a mid-window signing shows up as a decision to make instead of vanishing.
  for (const r of rows) if (!(r.tid in plan)) plan[r.tid] = r.h.b_list ? B : OUT;

  const card = el("div.kpi.pop", { tabindex: "0" });
  const windowsPanel = el("div");
  const repaint = () => { drawCard(); redraw(); };

  const setList = (tid, list) => {
    plan[tid] = list;
    save(KEY, plan);
    drawCard();
  };

  // ---- the card --------------------------------------------------------------------
  // One KPI rather than five: the number is the squad size, the colour is the worst rule
  // breach, and the breakdown opens on hover (desktop) or tap (phone).
  let open = false;
  card.addEventListener("click", (e) => {
    if (e.target.closest(".popbody")) return;  // links and text inside the breakdown
    open = !open;
    card.classList.toggle("open", open);
  });
  document.addEventListener("click", (e) => {
    if (open && !card.contains(e.target)) { open = false; card.classList.remove("open"); }
  });

  function drawCard() {
    const t = tally(rows, plan, rules);
    const loanIn = rows.filter((r) => r.loanedIn).length;
    const overCap = Math.max(0, t.a - t.cap);
    const hgShort = rules.hg_min && (t.hgCounted < rules.hg_min || t.club < rules.hg_club_min);
    const cls = overCap ? "bad" : (t.missing || t.out || hgShort) ? "warn" : "good";
    card.className = `kpi pop ${cls}${open ? " open" : ""}`;

    const line = (label, value, c) => el("tr", {}, [
      el("td", { text: label }),
      el(`td.num${c ? "." + c : ""}`, { text: String(value) }),
    ]);
    const unreg = rows.filter((r) => plan[r.tid] === OUT);
    const swappable = rows.filter((r) => plan[r.tid] === A && r.h.b_list).length;
    const notes = [
      overCap ? `<b>${overCap} over the A-list cap</b> — move someone to the B-list or leave `
        + "him unregistered." : null,
      t.missing ? `<b>${t.missing} home-grown place${t.missing === 1 ? "" : "s"} short</b> — `
        + `the A-list is reduced to ${t.cap}. No fine, you simply register fewer players.` : null,
      unreg.length ? `<b>Unregistered, can't play:</b> `
        + unreg.map((r) => `${r.player.name} (${r.age ?? "?"})`).join(" · ") : null,
      unreg.length && swappable ? `A slot can be freed without losing anyone — <b>${swappable}</b> `
        + `on the A-list ${swappable === 1 ? "is" : "are"} B-list eligible.` : null,
    ].filter(Boolean);

    card.replaceChildren(
      el("b", { text: String(rows.length) }),
      el("span", { text: `Squad · A ${t.a}/${t.cap}` }),
      el("div.popwrap", {}, [el("div.popbody", {}, [
        el("table.poptable", {}, [el("tbody", {}, [
          line("Owned", rows.length - loanIn),
          line("On loan in", loanIn),
          line(t.missing ? `A-list (${t.cap} allowed)` : "A-list", `${t.a} / ${rules.a_list_max}`,
            overCap ? "bad" : null),
          rules.hg_min ? line("Home grown on A", `${t.hgCounted} / ${rules.hg_min}`,
            t.hgCounted >= rules.hg_min ? "good" : "bad") : null,
          rules.hg_min ? line("…of them club-trained", `${t.club} / ${rules.hg_club_min}`,
            t.club >= rules.hg_club_min ? "good" : "bad") : null,
          line("B-list", t.b),
          line("Unregistered", t.out, t.out ? "warn" : null),
        ])]),
        ...notes.map((html) => el("p.note", { html })),
        el("p.note", {
          html: `${rules.league_name} · tier ${rules.tier}. ` + (rules.hg_min
            ? `A-list ${rules.a_list_max}, including ${rules.hg_min} home grown of whom `
              + `${rules.hg_club_min} trained here; B-list unlimited, under `
              + `${rules.b_list_under_age} on ${rules.u21_on}. `
            : `A-list ${rules.a_list_max}, no home-grown requirement; B-list unlimited, under `
              + `${rules.b_list_under_age} on ${rules.u21_on}. `)
            + `Set lists in the <b>List</b> column (Registration preset). `
            + `<a href="guides/registration.md">How it is derived</a>.`,
        }),
      ])]),
    );
  }

  // ---- columns ---------------------------------------------------------------------
  // A compact horizontal segmented control, not three stacked chips: this sits in a table cell,
  // and anything that wraps makes every row in the table as tall as the tallest cell. Clicking
  // repaints only the buttons, not the table, so the row doesn't jump out from under the
  // pointer when the table is sorted or filtered on this column.
  const listCell = (r) => {
    if (!r.h) return null;
    const wrap = el("span.seg", { onclick: (e) => e.stopPropagation() });
    const buttons = [[A, "A"], [B, "B"], [OUT, "—"]].map(([v, label]) => el(
      `button${plan[r.tid] === v ? ".on" : ""}`, {
        text: label,
        disabled: v === B && !r.h.b_list,
        title: v === B && !r.h.b_list
          ? `Not B-list eligible — he was 21 or older on ${rules.u21_on}`
          : `Put ${r.player.name} on the ${v === OUT ? "no" : v} list`,
        onclick: () => {
          setList(r.tid, v);
          for (const [i, b] of buttons.entries()) b.classList.toggle("on", [A, B, OUT][i] === v);
        },
      }));
    wrap.append(...buttons);
    return wrap;
  };

  // "Home grown" is the rulebook's UMBRELLA term — it covers both trained-here and trained-at-
  // another-Danish-club, and the quota counts them together. So the column asks the plainer
  // question of WHERE he trained and leaves "home grown" to the card, where the quota lives.
  const hgLabel = (r) => (!r.h ? null : r.h.hg_club ? "Us"
    : r.h.hg_association ? (r.h.origin_nation || "Association") : "—");
  const hgCell = (r) => {
    if (!r.h) return null;
    if (r.h.hg_club) return pill(r.h.hg_basis === "clock" ? "Us (36mo)" : "Us (youth)", "good");
    if (r.h.hg_association) return pill(r.h.origin_nation || "Association", "warn");
    return el("span.dim", { text: DASH });
  };

  const columns = {
    list: {
      label: "List", group: "Registration",
      help: "A-list (capped, needs the home-grown minimums), B-list (unlimited, U21 only), or "
        + "unregistered. Your plan, kept on this device — the save has no such thing.",
      sort: (r) => (r.h ? ({ A: 0, B: 1, "-": 2 })[plan[r.tid]] : null),
      render: listCell,
      filterType: "set",
      filterValue: (r) => (r.h ? LIST_LABEL[plan[r.tid]] : null),
    },
    hg: {
      label: "Trained at", group: "Registration",
      help: "Both count as HOME GROWN toward the 8. 'Us' also counts toward the 4 who must be "
        + "trained at the club itself; a Danish club does not.",
      sort: (r) => (!r.h ? null : r.h.hg_club ? 2 : r.h.hg_association ? 1 : 0),
      render: hgCell,
      filterType: "set",
      filterValue: hgLabel,
    },
    basis: {
      label: "HG basis", group: "Registration",
      help: "academy = came through our youth side · youth-origin = the save names us as the club "
        + "he came out of · clock = 36 months with us inside his eligibility window",
      get: (r) => (r.h ? r.h.hg_basis || DASH : null),
    },
    months: {
      label: "HG months", group: "Registration", align: "num",
      help: "Months registered with us between the start of the season he turned 15 and the end "
        + "of the last season he is 21. 36 of them makes him club-trained.",
      sort: (r) => r.h?.months_club ?? null,
      render: (r) => (r.h ? bar(Math.min(36, r.h.months_club ?? 0), { max: 36, lo: 99, dp: 1 }) : null),
    },
    eta: {
      label: "Home-grown date", group: "Registration",
      help: "When he becomes club-trained: the date he reaches 36 months with us if he stays. "
        + "'Already' = he counts now. Otherwise he cannot get there — either his age-21 window "
        + "has closed, or he cannot clock 36 months before it does.",
      sort: (r) => (!r.h ? null : r.h.hg_eta || (r.h.hg_club ? "0000" : "9999")),
      render: (r) => (!r.h ? null : r.h.hg_club ? pill("Already", "good")
        : r.h.hg_eta ? el("span", { text: r.h.hg_eta })
        : el("span.dim", { text: r.h.window_open ? "Out of time" : "Window closed" })),
      filterType: "none",
    },
    blist: {
      label: "B-list", group: "Registration",
      help: `Under 21 on ${rules.u21_on} — the fixed date the rule uses, so a player who turns 21 in the autumn keeps his place all season`,
      sort: (r) => (r.h ? (r.h.b_list ? 1 : 0) : null),
      render: (r) => (!r.h ? null : r.h.b_list ? pill("Eligible", "good") : el("span.dim", { text: DASH })),
      filterType: "set",
      filterValue: (r) => (!r.h ? null : r.h.b_list ? "Eligible" : "Not eligible"),
    },
    originNation: {
      label: "Origin nation", group: "Registration",
      help: "The nation of the club he came through — what decides association-trained",
      get: (r) => (r.h ? r.h.origin_nation || DASH : null),
    },
  };

  const presets = {
    Registration: ["list", "hg", "age", "pos", "rating", "blist", "months", "eta"],
    "Home grown": ["hg", "basis", "months", "eta", "originNation", "age"],
  };

  // ---- saved windows ------------------------------------------------------------------
  // The history of what was registered. The table above is always the plan for the CURRENT
  // squad; a saved window is frozen, names and all, so it still reads correctly once the players
  // on it have left.

  function record(id, note) {
    const t = tally(rows, plan, rules);
    return {
      id,
      snapshot: { season: snap.season, phase: snap.phase },
      league: rules.league_name ? `${rules.league_name} · tier ${rules.tier}` : undefined,
      note: note || undefined,
      summary: {
        a: t.a, b: t.b, out: t.out, cap: t.cap, a_list_max: rules.a_list_max,
        hg_counted: t.hgCounted, hg_min: rules.hg_min, club: t.club, hg_club_min: rules.hg_club_min,
      },
      players: rows.map((r) => ({
        tid: r.tid, name: r.player.name, list: plan[r.tid], age: r.age, pos: posOf(r),
        hg: r.h.hg_club ? "club" : r.h.hg_association ? "association" : null,
        b_list: !!r.h.b_list, loaned_in: !!r.loanedIn,
      })),
    };
  }

  async function saveDialog() {
    const { entries } = await W.list();
    const saved = new Map(entries.map((e) => [e.id, e]));
    const guess = W.guessWindow(snap.phase);
    const winSel = el("select.btn", {}, [["summer", "Summer window"], ["winter", "Winter window"]]
      .map(([v, text]) => el("option", { value: v, text, selected: v === guess.window })));
    const yearIn = el("input.search", {
      type: "number", value: String(guess.year), min: "2000", max: "2100", style: "width:7em",
    });
    const noteIn = el("input.search", { placeholder: "Note — e.g. what changed and why (optional)" });
    const warn = el("p.note");
    const idNow = () => W.windowId(Number(yearIn.value), winSel.value);
    const check = () => {
      const prev = saved.get(idNow());
      warn.innerHTML = prev
        ? `<b>Replaces</b> the saved ${W.windowLabel(prev.id)} (from the ${prev.snapshot?.phase || "?"} `
          + `snapshot, saved ${String(prev.saved_at || "").slice(0, 10)}).`
        : `Saves as <b>${W.windowLabel(idNow())}</b>.`;
      noteIn.value = noteIn.value || prev?.note || "";
    };
    winSel.addEventListener("change", check);
    yearIn.addEventListener("input", check);
    check();
    const t = tally(rows, plan, rules);
    let back;
    const go = el("button.btn", {
      text: "Save",
      onclick: async () => {
        const year = Number(yearIn.value);
        if (!Number.isInteger(year) || year < 2000 || year > 2100) return toast("Pick a year", true);
        go.disabled = true;
        const res = await W.put(record(idNow(), noteIn.value.trim()));
        back.remove();
        toast(res.error
          ? `Saved on this device only — R2 refused it (${res.error})`
          : `${W.windowLabel(idNow())} saved${res.where === "local" ? " on this device" : ""}`,
          !!res.error);
        drawWindows();
      },
    });
    back = sheet("Save registration for a window", [
      el("p.note", {
        text: `${t.a} on the A-list, ${t.b} on the B-list, ${t.out} unregistered — `
          + `saved exactly as the lists stand in the Squad table.`,
      }),
      el("div.prow", {}, [winSel, yearIn]),
      el("div.prow", {}, [noteIn]),
      warn,
      el("div.prow", {}, [go]),
      el("p.note", {
        html: W.hasToken()
          ? "Goes to R2 with your device token, so every device sees it."
          : "No device token on this browser, so it is kept <b>on this device only</b>. Add the "
            + "token under Recruitment → Shortlist to share windows across devices.",
      }),
    ]);
  }

  const header = () => el("div.sechead", {}, [
    el("h3", { text: "Saved registration windows" }),
    el("button.chip.ghost", {
      text: "Save window…",
      title: "Keep the current lists as the registration for a transfer window, to look back on "
        + "and to start the next window from",
      onclick: () => saveDialog(),
    }),
  ]);

  async function drawWindows() {
    windowsPanel.replaceChildren(header(), el("p.note", { text: "Loading…" }));
    const { entries, error } = await W.list();
    windowsPanel.replaceChildren(...[
      header(),
      error ? el("p.note", { html: `<b>Could not read R2</b> (${error}) — showing this device's only.` }) : null,
      entries.length ? el("div.scroll.fit", {}, [el("table", {}, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Window" }), el("th", { text: "Snapshot" }),
          el("th.num", { text: "A" }), el("th.num", { text: "B" }),
          el("th.num", { text: "Unreg" }), el("th.num", { text: "HG / club" }), el("th", { text: "" }),
        ])]),
        el("tbody", {}, entries.map((e) => {
          const s = e.summary || {};
          return el("tr", { style: "cursor:pointer", onclick: () => viewWindow(e) }, [
            el("td.name", {}, [W.windowLabel(e.id),
              e.where === "local" ? el("span.dim", { text: "  (this device)" }) : null]),
            el("td", { text: e.snapshot?.phase || DASH }),
            el("td.num", { text: `${s.a ?? DASH}` }),
            el("td.num", { text: `${s.b ?? DASH}` }),
            el("td.num", {}, [s.out ? pill(String(s.out), "warn") : el("span.dim", { text: "0" })]),
            el("td.num", { text: s.hg_min ? `${s.hg_counted} / ${s.club}` : DASH }),
            el("td", {}, [el("span.dim", { text: e.note ? e.note.slice(0, 60) : "" })]),
          ]);
        })),
      ])]) : null,
      el("p.note", {
        text: entries.length
          ? "Tap a window to see who was on each list, what has changed since, and to load it as "
            + "the starting point for the next window."
          : "Nothing saved yet. Set the lists in the table's List column, then press Save window… "
            + "to keep them as the registration for a transfer window.",
      }),
    ].filter(Boolean));
  }

  /** What has happened to a saved window's squad since, measured against the current plan. */
  function changesSince(rec) {
    const then = new Map(rec.players.map((p) => [p.tid, p]));
    return {
      left: rec.players.filter((p) => !byTid.has(p.tid) && p.list !== OUT),
      joined: rows.filter((r) => !then.has(r.tid)),
      moved: rows.filter((r) => then.has(r.tid) && then.get(r.tid).list !== plan[r.tid])
        .map((r) => ({ r, from: then.get(r.tid).list, to: plan[r.tid] })),
      agedOut: rows.filter((r) => then.get(r.tid)?.list === B && !r.h.b_list),
    };
  }

  function applyWindow(rec) {
    const then = new Map(rec.players.map((p) => [p.tid, p.list]));
    let agedOut = 0, fresh = 0;
    for (const r of rows) {
      let l = then.get(r.tid);
      if (l == null) { fresh++; l = r.h.b_list ? B : OUT; }
      else if (l === B && !r.h.b_list) { agedOut++; l = OUT; }
      plan[r.tid] = l;
    }
    save(KEY, plan);
    repaint();
    const gone = rec.players.filter((p) => !byTid.has(p.tid) && p.list !== OUT).length;
    toast([`Loaded ${W.windowLabel(rec.id)}`,
      gone ? `${gone} since left` : null,
      fresh ? `${fresh} new to place` : null,
      agedOut ? `${agedOut} aged out of the B-list — now unregistered` : null,
    ].filter(Boolean).join(" · "));
  }

  function viewWindow(rec) {
    const s = rec.summary || {};
    const posRank = (p) => {
      const i = D.POS_ORDER.indexOf(p);
      return i === -1 ? D.POS_ORDER.length : i;
    };
    const listOf = (l) => rec.players.filter((p) => p.list === l)
      .sort((x, y) => posRank(x.pos) - posRank(y.pos) || x.name.localeCompare(y.name));
    const hgPill = (p) => (p.hg === "club" ? pill("Us", "good")
      : p.hg === "association" ? pill(rules.nation || "Association", "warn") : null);
    const block = (title, players) => el("div", {}, [
      el("h3", { text: `${title} · ${players.length}` }),
      players.length ? el("div.scroll.fit", {}, [el("table", {}, [el("tbody", {}, players.map((p) =>
        el("tr", {}, [
          el("td", { text: p.pos || DASH }),
          el("td.name", {}, [p.name,
            p.loaned_in ? el("span.dim", { text: "  (loan in)" }) : null,
            byTid.has(p.tid) ? null : el("span.dim", { text: "  · left" })]),
          el("td.num", { text: p.age == null ? DASH : String(p.age) }),
          el("td", {}, [hgPill(p)]),
        ])))])]) : el("p.note", { text: "Nobody." }),
    ]);

    const c = changesSince(rec);
    const names = (arr, f = (x) => x.name) => arr.map(f).join(" · ");
    const changes = [
      c.left.length ? el("p.note", { html: `<b>Left the club</b> (${c.left.length}): ${names(c.left)}` }) : null,
      c.joined.length ? el("p.note", {
        html: `<b>Not in this window</b> (${c.joined.length}) — joined or promoted since: `
          + names(c.joined, (r) => r.player.name),
      }) : null,
      c.agedOut.length ? el("p.note", {
        html: `<b>Aged out of the B-list</b> (${c.agedOut.length}) — need an A-list place now: `
          + names(c.agedOut, (r) => r.player.name),
      }) : null,
      // Grouped by transition: one line per "A → B", not one arrow per player, so a plan that
      // differs by thirty moves still reads as three or four decisions.
      ...[...c.moved.reduce((g, m) => {
        const k = `${m.from}>${m.to}`;
        return g.set(k, [...(g.get(k) || []), m]);
      }, new Map())].map(([k, ms]) => {
        const [from, to] = k.split(">");
        return el("p.note", {
          html: `<b>${LIST_LABEL[from]} → ${LIST_LABEL[to]} in the current plan</b> (${ms.length}): `
            + names(ms, (m) => m.r.player.name),
        });
      }),
    ].filter(Boolean);

    let back;
    back = sheet(`Registration · ${W.windowLabel(rec.id)}`, [
      el("div.kpis", {}, [
        kpi("A-list", `${s.a ?? DASH} / ${s.a_list_max ?? rules.a_list_max}`),
        s.hg_min ? kpi("Home grown on A", `${s.hg_counted} / ${s.hg_min}`,
          s.hg_counted >= s.hg_min ? "good" : "bad") : null,
        s.hg_min ? kpi("…club-trained", `${s.club} / ${s.hg_club_min}`,
          s.club >= s.hg_club_min ? "good" : "bad") : null,
        kpi("B-list", String(s.b ?? DASH)),
        kpi("Unregistered", String(s.out ?? DASH), s.out ? "warn" : "good"),
      ].filter(Boolean)),
      el("p.note", {
        html: `From the <b>${rec.snapshot?.phase || "?"}</b> snapshot`
          + (rec.league ? ` · ${rec.league}` : "")
          + ` · saved ${String(rec.saved_at || "").slice(0, 10)}`
          + (rec.where === "local" ? " · <b>this device only</b>" : "")
          + (rec.note ? `<br>${escapeHtml(rec.note)}` : ""),
      }),
      el("div.prow", {}, [
        el("button.btn", {
          text: "Load into plan",
          title: "Set the lists from this window: players still here keep their list, new players "
            + "get the default, and anyone who has aged out of the B-list is flagged",
          onclick: () => {
            if (!confirm(`Replace the current plan with ${W.windowLabel(rec.id)}'s lists?`)) return;
            applyWindow(rec);
            back.remove();
          },
        }),
        rec.where === "local" && W.hasToken() ? el("button.btn", {
          text: "Upload to R2",
          onclick: async () => {
            const res = await W.put(rec);
            toast(res.error ? `Upload failed: ${res.error}` : "Uploaded", !!res.error);
            back.remove();
            drawWindows();
          },
        }) : null,
        el("button.btn", {
          text: "Delete",
          onclick: async () => {
            if (!confirm(`Delete the saved ${W.windowLabel(rec.id)}? This cannot be undone.`)) return;
            try {
              await W.remove(rec);
              toast(`${W.windowLabel(rec.id)} deleted`);
              back.remove();
              drawWindows();
            } catch (err) { toast(`Delete failed: ${err.message}`, true); }
          },
        }),
      ]),
      el("h3", { text: "Since then" }),
      ...(changes.length ? changes
        : [el("p.note", { text: "Nothing has changed — the current plan matches this window." })]),
      block("A-list", listOf(A)),
      block("B-list", listOf(B)),
      block("Unregistered", listOf(OUT)),
    ], { wide: true });
  }

  drawCard();
  drawWindows();
  return { card, columns, presets, windowsPanel };
}

// --------------------------------------------------------------------------- the rule maths

/**
 * How many home-grown players the A-list actually gets credit for.
 *
 * Not simply "count the home-grown players": the rule is 8 in total, at least 4 trained at the
 * club, and the REMAINDER up to 4 from elsewhere in the association. So a list with 3
 * club-trained and 5 association-trained is credited 7, not 8 — the fifth association player has
 * no place left to fill. That asymmetry is the whole reason the club-trained column matters more
 * than the total.
 */
export function hgCredit(club, association, rules) {
  const c = Math.min(club, rules.hg_min);
  return c + Math.min(association, rules.hg_min - c, rules.hg_min - rules.hg_club_min);
}

function tally(rows, plan, rules) {
  let a = 0, b = 0, out = 0, club = 0, assoc = 0;
  for (const r of rows) {
    const l = plan[r.tid];
    if (l === A) {
      a++;
      if (r.h.hg_club) club++;
      else if (r.h.hg_association) assoc++;
    } else if (l === B) b++;
    else out++;
  }
  const hgCounted = rules.hg_min ? hgCredit(club, assoc, rules) : 0;
  const missing = Math.max(0, rules.hg_min - hgCounted);
  return { a, b, out, club, assoc, hgCounted, missing, cap: rules.a_list_max - missing };
}

// --------------------------------------------------------------------------- plumbing
const load = (key) => {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
};
const save = (key, plan) => {
  try { localStorage.setItem(key, JSON.stringify(plan)); } catch { /* private mode */ }
};
/** The newest plan this browser holds for a snapshot before `key`, or null. Plan keys are
 *  `fm:registration:<season>:<phase>` and both parts sort as strings. */
function previousPlan(key) {
  const [, season, phase] = PLAN_KEY.exec(key) || [];
  let best = null;
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const m = PLAN_KEY.exec(localStorage.key(i) || "");
      if (!m) continue;
      const ord = `${m[1]}:${m[2]}`;
      if (ord >= `${season}:${phase}`) continue;
      if (!best || ord > best.ord) best = { ord, k: localStorage.key(i) };
    }
  } catch { return null; }
  return best ? load(best.k) : null;
}
const escapeHtml = (t) => String(t).replace(/[&<>"]/g,
  (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
const kpi = (label, value, cls) => el(`div.kpi${cls ? "." + cls : ""}`, {}, [
  el("b", { text: String(value) }), el("span", { text: label }),
]);
