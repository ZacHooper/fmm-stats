#!/usr/bin/env python3
"""Render the career into a static site: HTML for the phone, JSON for Claude.

    uv run python scripts/build_site.py                    # newest snapshot of the default career
    uv run python scripts/build_site.py --season 2024 --phase 2023-07-02
    uv run python scripts/build_site.py --out site --career frem

Why static. The dashboard is the right tool at a desk and the wrong one on a phone: reading it
means a laptop awake, on the same network, holding the DuckDB write lock. Everything on these
pages is a pure function of one snapshot, so it can be rendered once and served as files —
always on, no cold start, no RAM ceiling, and the store never leaves the machine that built it.
Streamlit stays local for the interactive work (sliders, what-ifs, the squad tool).

Two audiences, one build:
  - `<out>/*.html` — self-contained pages, inline CSS, no external requests, wide tables
    scrolling inside their own containers so they behave on a small screen.
  - `<out>/api/*.json` — the same data as data, so Claude can answer questions about the squad
    from a phone with both laptops shut. Scoped per club on purpose: the whole effective table
    is ~30k players and useless in a chat context, while our squad plus one opponent is a few
    hundred KB.

**Immersion rule, enforced not just intended.** Published JSON carries `level_*` percentiles and
ability *ranks* only — never the raw ability number. Everything here reads from
`db.effective_table` (which `EXCLUDE`s `ca`) and `db.ability_rank_*` (which return rank/N), so
the rule holds by construction; a hand-rolled query would be the way to break it. `--check`
greps the emitted JSON for a raw-ability key and fails the build, so a future edit that
reintroduces one doesn't ship quietly.

The analysis is NOT reimplemented here. Depth charts, verdicts and percentiles come from
`dashboard/positions.py`, shared with the Streamlit page, so the site is a second screen rather
than a second opinion.
"""
import argparse
import datetime
import html
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import _dbopen                                                          # noqa: E402

ATTR_NOTE = ("Ability is expressed as percentiles and division ranks only — this project never "
             "surfaces the raw ability number.")


# --------------------------------------------------------------------------- html plumbing
CSS = """
:root{--bg:#f7f7f8;--card:#fff;--ink:#16181d;--dim:#6b7280;--line:#e5e7eb;--accent:#0b6b3a;
      --good:#0b6b3a;--goodbg:#e7f4ec;--warn:#8a5a00;--warnbg:#fdf3e0;--bad:#9b1c1c;
      --badbg:#fdeaea;--bar:#c9d5e3;--barlo:#e3c9c9}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f1115;--card:#171a20;--ink:#e7e9ee;--dim:#9aa3b2;--line:#262b34;--accent:#4ade80;
        --good:#4ade80;--goodbg:#12301f;--warn:#fbbf24;--warnbg:#332506;--bad:#f87171;
        --badbg:#3a1414;--bar:#33445c;--barlo:#5c3333}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
     -webkit-text-size-adjust:100%}
.wrap{max-width:1100px;margin:0 auto;padding:16px 12px 56px}
header.top{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0 8px;
           border-bottom:1px solid var(--line)}
h1{font-size:19px;margin:0 0 2px}
h2{font-size:16px;margin:26px 0 8px}
h3{font-size:14px;margin:20px 0 6px;color:var(--dim);text-transform:uppercase;
   letter-spacing:.04em}
.sub{color:var(--dim);font-size:13px;margin:0}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
nav a{display:inline-block;padding:5px 10px;border:1px solid var(--line);border-radius:999px;
      background:var(--card);color:var(--ink);text-decoration:none;font-size:13px}
nav a.on{border-color:var(--accent);color:var(--accent);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;
      margin:12px 0}
.note{color:var(--dim);font-size:12.5px;margin:8px 0 0}
.kpis{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;
     min-width:108px;flex:1 1 108px}
.kpi b{display:block;font-size:19px;line-height:1.2}
.kpi span{color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);
        border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line)}
th{position:sticky;top:0;background:var(--card);font-size:11.5px;color:var(--dim);
   text-transform:uppercase;letter-spacing:.04em;z-index:1}
tbody tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.name{font-weight:600;white-space:nowrap}
.bar{display:inline-block;height:6px;border-radius:3px;background:var(--bar);vertical-align:2px;
     margin-right:6px;min-width:2px}
.bar.lo{background:var(--barlo)}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;white-space:nowrap}
.pill.good{background:var(--goodbg);color:var(--good)}
.pill.warn{background:var(--warnbg);color:var(--warn)}
.pill.bad{background:var(--badbg);color:var(--bad)}
.pill.flat{background:var(--bg);color:var(--dim)}
details{margin:8px 0}
summary{cursor:pointer;font-size:13px;color:var(--accent)}
details .body{font-size:13px;color:var(--ink);padding:8px 2px 0}
.dim{color:var(--dim)}
footer{margin-top:34px;padding-top:12px;border-top:1px solid var(--line);color:var(--dim);
       font-size:12px}
code{background:var(--bg);padding:1px 4px;border-radius:4px;font-size:12px}
"""

PAGES = [("index.html", "Overview"), ("positions.html", "Positions"), ("squad.html", "Squad"),
         ("form.html", "Form"), ("divisions.html", "Divisions"),
         ("shortlist.html", "Shortlist")]


def esc(v):
    return html.escape("" if v is None else str(v))


def page(fname, title, head_html, body_html, built):
    nav = "".join(f'<a href="{f}"{" class=on" if f == fname else ""}>{esc(l)}</a>'
                  for f, l in PAGES)
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=color-scheme content="light dark">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class=wrap>
<header class=top>{head_html}<nav>{nav}</nav></header>
{body_html}
<footer>Built {esc(built)} from the local DuckDB store. {esc(ATTR_NOTE)}<br>
Machine-readable copy of everything here: <code>api/index.json</code>.</footer>
</div></body></html>"""


def fmt_num(v, dp=0):
    if v is None or v != v:
        return "—"
    return f"{float(v):,.{dp}f}"


def bar(v, vmax=100, lo_below=40, dp=0):
    """A percentile / familiarity cell: proportional bar plus the number."""
    if v is None or v != v:
        return '<span class=dim>—</span>'
    pct = max(0.0, min(100.0, 100.0 * float(v) / vmax))
    cls = "bar lo" if float(v) < lo_below * vmax / 100 else "bar"
    return (f'<span class="{cls}" style="width:{pct * 0.42:.0f}px"></span>'
            f'{float(v):,.{dp}f}')


def pill(text):
    t = str(text or "")
    low = t.lower()
    if low.startswith("sell") or low.startswith("needs a starter"):
        cls = "bad"
    elif low.startswith("loan") or low.startswith("surplus") or low.startswith("thin") \
            or low.startswith("stocked") or low.startswith("prospect"):
        cls = "warn"
    elif low.startswith("keep") or low.startswith("settled"):
        cls = "good"
    else:
        cls = "flat"
    return f'<span class="pill {cls}">{esc(t)}</span>'


def table(rows, cols):
    """rows: list of dicts. cols: list of (key, label, kind) where kind is one of
    text / name / num / raw (pre-rendered HTML)."""
    ths = "".join(f'<th class="{"num" if k == "num" else ""}">{esc(lab)}</th>'
                  for _key, lab, k in cols)
    trs = []
    for r in rows:
        tds = []
        for key, _lab, k in cols:
            v = r.get(key)
            if k == "raw":
                tds.append(f"<td>{v if v is not None else '—'}</td>")
            elif k == "num":
                tds.append(f'<td class=num>{esc(v) if isinstance(v, str) else fmt_num(v)}</td>')
            elif k == "name":
                tds.append(f"<td class=name>{esc(v)}</td>")
            else:
                tds.append(f"<td>{esc(v) if v is not None and v == v else '—'}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div class=scroll><table><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def kpis(items):
    return '<div class=kpis>' + "".join(
        f'<div class=kpi><b>{esc(v)}</b><span>{esc(k)}</span></div>' for k, v in items) + '</div>'


# --------------------------------------------------------------------------- json plumbing
def jdefault(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()[:10] if isinstance(o, datetime.date) else o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def write_json(path, payload, db):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db._json_clean(payload), f, ensure_ascii=False, default=jdefault,
                  separators=(",", ":"))
    return os.path.getsize(path)


# --------------------------------------------------------------------------- content
def head_block(car, season, phase, our_lg, built):
    return (f"<h1>{esc(car.name)} · {esc(our_lg or 'league unknown')}</h1>"
            f"<p class=sub>Snapshot {esc(season)} · {esc(phase)} — built {esc(built[:16])}</p>")


def build_positions_page(D, db, P):
    """Depth charts, straight from the shared builder — same numbers as the dashboard."""
    our_cid, our_lg, ladder = D["our_cid"], D["our_lg"], D["ladder"]
    out = [f"<h2>Where the window money goes · {esc(our_lg)}</h2>"]
    srows = []
    for r in D["summary"].itertuples():
        rk = r.rank_ours
        srows.append({
            "role": r.role, "owned": f'{r.owned} / {r.slots}', "best": r.best,
            "pos": r.position, "fam": bar(r.fam, vmax=20, lo_below=60),
            "rank": f"{rk[0]} / {rk[1]}" if rk else "—",
            "div": bar(r.div_pct), "fit": bar(r.fit_div),
            "age": fmt_num(r.avg_age, 1), "read": pill(r.read)})
    out.append(table(srows, [
        ("role", "Role", "name"), ("owned", "Owned/slots", "text"),
        ("best", "Best available", "text"), ("pos", "Pos", "text"),
        ("fam", "Fam", "raw"), ("rank", f"Rank in {our_lg}", "num"),
        ("div", "Div %ile", "raw"), ("fit", "Fit %ile", "raw"),
        ("age", "Avg age", "num"), ("read", "Read", "raw")]))
    out.append('<p class=note>Sorted weakest first — the top row is where a signing changes '
               'most. <b>Div %ile</b> is level (ability); <b>Fit %ile</b> is tactic fit. A high '
               'Fit over a low Div %ile means the weight-set likes a player the division '
               'doesn\'t. Ability is CURRENT ability, so a teenage prospect ranks near the '
               'bottom of a senior division however good he\'ll become — those rows read '
               '<i>Prospect starting</i>, which means buy cover, not buy a replacement.</p>')

    per_role, prev, contract = D["per_role"], D["prev"], D["contract"]
    for role in D["roles_present"]:
        g = per_role[per_role["role"] == role].sort_values("eff", ascending=False)
        n_slots = D["slots"].get(role, 1)
        out.append(f"<h2>{esc(role)} <span class=dim>· {len(g)} owned · {n_slots} start</span></h2>")
        rows = []
        for _, r in g.iterrows():
            ci = contract.get(int(r["tid"]), {})
            exp = ci.get("Expiry")
            row = {"n": int(r["depth"]), "player": r["name_label"],
                   "age": fmt_num(r["age"]), "pos": r["position"],
                   "fam": bar(int(r["familiarity"]), vmax=20, lo_below=60),
                   "rating": fmt_num(r["eff"]), "fit": bar(r["fit_div"]),
                   "contract": (exp.strftime("%b %Y") if hasattr(exp, "strftime")
                                else (str(exp)[:7] if exp is not None and exp == exp else "—")),
                   "wage": ("£" + fmt_num(ci.get("Wage")) if ci.get("Wage") is not None
                            else "—"),
                   "last": P.prev_cell(prev, r["tid"]),
                   "squad": D["status"].get(int(r["tid"]), "—"),
                   "also": r["also"], "read": pill(r["read"])}
            for cid, lname in ladder:
                row[f"lg{cid}"] = P.rank_cell(D["ranks"], r["tid"], r["position"], cid)
            rows.append(row)
        cols = [("n", "#", "num"), ("player", "Player", "name"), ("age", "Age", "num"),
                ("pos", "Pos", "text"), ("fam", "Fam", "raw"), ("rating", "Rating", "num"),
                ("fit", "Fit %ile", "raw")]
        cols += [(f"lg{cid}", lname or f"#{cid}", "num") for cid, lname in ladder]
        cols += [("contract", "Contract", "text"), ("wage", "Wage/yr", "num"),
                 ("last", "Last season", "text"), ("squad", "Squad", "text"),
                 ("also", "Also", "text"), ("read", "Read", "raw")]
        out.append(table(rows, cols))

        surplus = g[g["depth"] > n_slots]
        if len(surplus) and D["lower"]:
            bits = []
            for _, r in surplus.iterrows():
                lines = []
                for cid, lname in D["lower"]:
                    h = D["best_hosts"].get((int(r["tid"]), r["position"], cid))
                    if h is None or h.empty:
                        continue
                    top3 = " · ".join(f"{esc(c.club)} <b>{int(c.rank)}/{int(c.n)}</b>"
                                      for c in h.head(3).itertuples())
                    n1 = D["starts_at"].get((int(r["tid"]), r["position"], cid), 0)
                    lines.append(f"{esc(lname)}: first choice at <b>{n1}</b> club(s) — {top3}")
                age = fmt_num(r["age"])
                head = f"<b>{esc(r['name_label'])}</b> ({age}, {esc(r['position'])})"
                bits.append(head + ("<br>" + "<br>".join(lines) if lines else
                                    " — no ranked clubs below us."))
            out.append(f"<details><summary>Loan destinations for the {len(surplus)} behind the "
                       f"starters</summary><div class=body>" + "<br><br>".join(bits) +
                       f"<p class=note>Rank inside that club's squad at his position — "
                       f"<b>1/n</b> means he'd be their first choice with n-1 bodies behind "
                       f"him, so he'd actually play. The <i>first choice at N clubs</i> count "
                       f"ignores clubs with fewer than {P.MIN_HOST_SQUAD} players at the "
                       f"position, since topping an empty depth chart proves nothing.</p>"
                       f"</div></details>")

    out.append("""<details><summary>How the Read column is decided</summary><div class=body>
<b>Keep — starter</b> — inside the role's slot count. Flagged <b>upgrade target</b> if his
ability percentile in our own division is under 40, i.e. he starts but shouldn't at this level.<br>
<b>Keep — cover</b> — first man outside the XI.<br>
<b>Cover only — primary X</b> — not his main role, so no transfer verdict here; read him in the
<b>X</b> table.<br>
<b>Keep — reserves</b> — 18 or younger; too early to judge either way.<br>
<b>Loan out</b> — under 24 and at least one club in a lower division would play him first
choice.<br>
<b>Sell / release</b> — 23 or older and in the bottom third of our division by ability, or
nobody below us would start him.<br>
<b>Surplus — loan or sell</b> — behind the cover man with no clear destination.
<p class=note>It only knows depth, level, age and whether a lower division would start him —
not morale, personality, form, or what you're being offered. Overrule it freely.</p>
</div></details>""")
    return "\n".join(out)


def build_squad_page(D, db, P, season, phase, method):
    """One row per player at his primary role — the whole squad on a single screen."""
    per_role = D["per_role"]
    prim = per_role.loc[per_role.groupby("tid")["eff"].idxmax()].sort_values(
        ["role", "eff"], ascending=[True, False])
    elig = db.eligibility_frame(season, phase)
    origin = dict(zip(elig["tid"], elig["origin_club"])) if not elig.empty else {}
    eligible = dict(zip(elig["tid"], elig["eligible"])) if not elig.empty else {}

    def contract_cells(tid):
        ci = D["contract"].get(int(tid), {})
        exp = ci.get("Expiry")
        shown = (exp.strftime("%b %Y") if hasattr(exp, "strftime")
                 else (str(exp)[:7] if exp is not None and exp == exp else "—"))
        wage = "£" + fmt_num(ci.get("Wage")) if ci.get("Wage") is not None else "—"
        return shown, wage

    rows = []
    for _, r in prim.iterrows():
        exp, wage = contract_cells(r["tid"])
        rows.append({
            "player": r["name_label"], "age": fmt_num(r["age"]), "role": r["role"],
            "pos": r["position"], "fam": bar(int(r["familiarity"]), vmax=20, lo_below=60),
            "rating": fmt_num(r["eff"]), "fit": bar(r["fit_div"]), "div": bar(r["div_pct"]),
            "depth": int(r["depth"]), "contract": exp, "wage": wage,
            "last": P.prev_cell(D["prev"], r["tid"]),
            "squad": D["status"].get(int(r["tid"]), "—"),
            "origin": origin.get(int(r["tid"])),
            "elig": "\u2713" if eligible.get(int(r["tid"])) else "",
            "read": pill(r["read"])})

    wage_bill = sum((D["contract"].get(int(t), {}).get("Wage") or 0) for t in prim["tid"])
    n_first = sum(1 for v in D["status"].values() if v == "First team")
    body = [kpis([("In depth charts", len(rows)), ("Owned", len(D["status"])),
                  ("First team", n_first),
                  ("Avg age", fmt_num(prim["age"].mean(), 1)),
                  ("Wage bill / yr", "£" + fmt_num(wage_bill))]),
            f"<h2>Squad · primary role · {esc(method)}</h2>",
            table(rows, [
                ("player", "Player", "name"), ("age", "Age", "num"), ("role", "Role", "text"),
                ("pos", "Pos", "text"), ("fam", "Fam", "raw"), ("depth", "Depth", "num"),
                ("rating", "Rating", "num"), ("fit", "Fit %ile", "raw"),
                ("div", "Div %ile", "raw"), ("contract", "Contract", "text"),
                ("wage", "Wage/yr", "num"), ("last", "Last season", "text"),
                ("squad", "Squad", "text"), ("origin", "Origin club", "text"),
                ("elig", "Capital", "text"), ("read", "Read", "raw")]),
            '<p class=note>One row per player at his strongest role — the depth charts on the '
            '<a href="positions.html">Positions</a> page list every role he rates in. '
            '<b>Capital</b> \u2713 marks a career-origin club inside Region Hovedstaden, the '
            'self-imposed signing rule; existing squad members are grandfathered. '
            '<b>Last season</b> is starts/apps \u00b7 minutes \u00b7 avg rating.</p>']

    # Owned players the depth charts leave out — loaned-in bodies and anyone with no position
    # above the familiarity floor. Listed rather than dropped: a squad page that shows 38 of
    # 46 without saying so is a page that lies quietly.
    rated = {int(t) for t in per_role["tid"].unique()}
    sq_all = db.squad(season, phase)
    missing = sq_all[~sq_all["tid"].astype(int).isin(rated)]
    if not missing.empty:
        li = set()
        if not db.q("SELECT 1 AS ok FROM information_schema.columns "
                    "WHERE table_schema='staging' AND table_name='players' "
                    "AND column_name='loaned_in'").empty:
            li = {int(t) for t in db.q("SELECT tid FROM staging.players "
                                       "WHERE season=? AND phase=? AND loaned_in",
                                       [season, phase])["tid"]}
        bio = db.player_bio(season, phase, [int(t) for t in missing["tid"]])
        mrows = []
        for r in missing.itertuples():
            tid = int(r.tid)
            pos = db.player_positions_map(season, phase, tid)
            best = max(pos, key=pos.get) if pos else None
            exp, wage = contract_cells(tid)
            mrows.append({
                "player": db.player_label(tid, r.name), "age": fmt_num(bio.get(tid, {}).get("Age")),
                "pos": (f"{best} ({pos[best]})" if best else "—"),
                "squad": r.status, "contract": exp, "wage": wage,
                "why": ("Loaned in — goes back" if tid in li
                        else f"No position at Fam {D['min_fam']}+")})
        body += [f"<h2>Not in the depth charts \u00b7 {len(mrows)}</h2>",
                 table(mrows, [("player", "Player", "name"), ("age", "Age", "num"),
                               ("pos", "Best position (Fam)", "text"),
                               ("squad", "Squad", "text"), ("contract", "Contract", "text"),
                               ("wage", "Wage/yr", "num"), ("why", "Why", "text")]),
                 '<p class=note>Loaned-IN players are excluded from the depth charts because '
                 'they go back \u2014 planning around them overstates the squad. The rest have '
                 'no position they know well enough to be ranked in.</p>']
    return "\n".join(body)


def build_form_page(db, season):
    hist = db.our_match_history()
    if hist.empty:
        return "<h2>Form</h2><p class=note>No matches parsed in this store yet.</p>"
    out = []
    per_season = []
    for s, g in hist.groupby("season"):
        comp = g[~g["competition"].str.contains("friend", case=False, na=False)]
        base = comp if not comp.empty else g
        per_season.append({
            "season": int(s), "p": len(base),
            "w": int((base["result"] == "W").sum()), "d": int((base["result"] == "D").sum()),
            "l": int((base["result"] == "L").sum()),
            "gf": int(base["gf"].sum()), "ga": int(base["ga"].sum()),
            "gd": int(base["gf"].sum() - base["ga"].sum()),
            "ppg": round(base["pts"].mean(), 2)})
    per_season.sort(key=lambda r: -r["season"])
    out.append("<h2>Season by season</h2>")
    out.append(table(per_season, [
        ("season", "Season", "num"), ("p", "P", "num"), ("w", "W", "num"), ("d", "D", "num"),
        ("l", "L", "num"), ("gf", "GF", "num"), ("ga", "GA", "num"), ("gd", "GD", "num"),
        ("ppg", "Pts/game", "num")]))
    out.append('<p class=note>Friendlies excluded where the season has competitive matches. '
               'Counts come from the newest snapshot of each season and can fall short of the '
               'true fixture list: match detail lives in a fixed-size ring buffer the game '
               'overwrites as the season runs, so a save late in a campaign no longer holds '
               'its opening games. The managed club keeps far more of its own history than the '
               'simulated ones, but treat a short season as missing games, not lost ones.</p>')

    recent = hist.sort_values(["season", "date"], ascending=False).head(20)
    res_cls = {"W": "good", "D": "flat", "L": "bad"}
    rrows = [{"date": str(r.date)[:10], "comp": r.competition, "venue": r.venue,
              "opp": r.opponent, "score": f"{int(r.gf)}–{int(r.ga)}",
              "res": f'<span class="pill {res_cls.get(r.result, "flat")}">{esc(r.result)}</span>',
              "form": r.formation}
             for r in recent.itertuples()]
    out.append("<h2>Last 20 matches</h2>")
    out.append(table(rrows, [
        ("date", "Date", "text"), ("comp", "Competition", "text"), ("venue", "H/A", "text"),
        ("opp", "Opponent", "name"), ("score", "Score", "num"), ("res", "", "raw"),
        ("form", "Formation", "text")]))

    rows = db.match_stats_rows(db.OUR_CLUBS)
    if rows is not None and not rows.empty:
        last = rows[(rows["season"] == season - 1) & rows["appeared"]]
        if not last.empty:
            agg = last.groupby("tid").agg(
                apps=("rating", "size"), starts=("started", "sum"), mins=("minutes", "sum"),
                goals=("goals", "sum"), assists=("assists", "sum"), rat=("rating", "mean"))
            agg = agg[agg["mins"] > 0].sort_values("mins", ascending=False)
            names = db.q("SELECT tid, any_value(name) AS name FROM staging.players "
                         "WHERE tid IN (" + ",".join(str(int(t)) for t in agg.index) +
                         ") GROUP BY tid")
            nm = dict(zip(names["tid"], names["name"]))
            prows = [{"player": db.player_label(t, nm.get(t)), "apps": int(r.apps),
                      "starts": int(r.starts), "mins": int(r.mins), "goals": int(r.goals),
                      "assists": int(r.assists), "rat": round(float(r.rat), 2)}
                     for t, r in agg.iterrows()]
            out.append(f"<h2>Season {season - 1} — minutes and output</h2>")
            out.append(table(prows, [
                ("player", "Player", "name"), ("apps", "Apps", "num"),
                ("starts", "Starts", "num"), ("mins", "Minutes", "num"),
                ("goals", "Goals", "num"), ("assists", "Assists", "num"),
                ("rat", "Avg rating", "num")]))
            out.append('<p class=note>Minutes are modelled from the sub-on / sub-off fields '
                       '(255 = played to the whistle), so they are the selection signal — '
                       'squad status and loan flags in the save are not reliable.</p>')
    return "\n".join(out)


def build_divisions_page(db, D, season, phase, method):
    """Squad strength of every club in our division and the ones below.

    Deliberately NOT a league table: `staging.standings` parses only partially for this career
    (a 22-game division comes back with max played 12), so a table built from it would be
    quietly wrong. Squad strength is a clean read of the same question — who is actually good.
    """
    out = []
    for cid, lname in D["ladder"]:
        teams = db.teams_in_league(season, phase, cid)
        if teams.empty:
            continue
        tids = [int(t) for t in teams["tid"]]
        frame = db.squad_frame(season, phase, method, tids)
        if frame.empty:
            continue
        rows = []
        for tid in tids:
            units, team = db.team_strength(frame, tid)
            if team["index"] is None:
                continue
            u = dict(zip(units["unit"], units["index"]))
            rows.append({"club": teams.loc[teams["tid"] == tid, "name"].iloc[0],
                         "tid": tid, "index": team["index"], "gk": u.get("GK"),
                         "def": u.get("Defense"), "mid": u.get("Midfield"),
                         "att": u.get("Attack"), "rated": team["n"]})
        rows.sort(key=lambda r: -(r["index"] or 0))
        for i, r in enumerate(rows, 1):
            r["pos"] = i
            r["us"] = "◀ us" if r["tid"] in db.OUR_CLUBS else ""
            for k in ("index", "gk", "def", "mid", "att"):
                r[k] = fmt_num(r[k], 1)
        out.append(f"<h2>{esc(lname or f'#{cid}')}</h2>")
        out.append(table(rows, [
            ("pos", "#", "num"), ("club", "Club", "name"), ("us", "", "text"),
            ("index", "Squad index", "num"), ("gk", "GK", "num"), ("def", "Defence", "num"),
            ("mid", "Midfield", "num"), ("att", "Attack", "num"),
            ("rated", "In best XI", "num")]))
    out.append('<p class=note><b>Squad index</b> averages the best XI\'s position index, where '
               '100 = an average player for that position across the whole loaded population '
               'and 15 = one standard deviation. It is cross-position comparable, which a raw '
               'role rating is not (a keeper and a striker score on different scales). Two '
               'things it is not: it is not results, and it is not raw quality — every club '
               'here is scored under <b>our</b> weight-set, so it reads as <i>how well their '
               'players fit the way we play</i>. For level, use the ability ranks on the '
               '<a href="positions.html">Positions</a> page, which are tactic-agnostic.</p>')
    return "\n".join(out)


def build_index_page(D, db, car, season, phase, method, sizes):
    our_lg = D["our_lg"]
    weakest = D["summary"].head(3)
    strongest = D["summary"].dropna(subset=["div_pct"]).tail(3).iloc[::-1]
    per_role = D["per_role"]
    reads = per_role["read"].value_counts()
    n_sell = int(sum(v for k, v in reads.items() if k.lower().startswith("sell")))
    n_loan = int(sum(v for k, v in reads.items() if k.lower().startswith("loan")))
    out = [kpis([("Division", our_lg or "?"), ("Squad", len(D["status"])),
                 ("Sell / release", n_sell), ("Loan out", n_loan),
                 ("Tactic", method)])]
    out.append("<h2>Priorities this window</h2>")
    wrows = [{"role": r.role, "best": r.best, "div": bar(r.div_pct),
              "fam": bar(r.fam, vmax=20, lo_below=60), "read": pill(r.read)}
             for r in weakest.itertuples()]
    out.append(table(wrows, [("role", "Weakest role", "name"), ("best", "Best we have", "text"),
                             ("div", "Div %ile", "raw"), ("fam", "Fam", "raw"),
                             ("read", "Read", "raw")]))
    srows = [{"role": r.role, "best": r.best, "div": bar(r.div_pct), "read": pill(r.read)}
             for r in strongest.itertuples()]
    out.append(table(srows, [("role", "Strongest role", "name"), ("best", "Best we have", "text"),
                             ("div", "Div %ile", "raw"), ("read", "Read", "raw")]))
    out.append('<p class=note>Ranked by our best available player\'s ability percentile in our '
               'own division. Full depth charts on <a href="positions.html">Positions</a>.</p>')

    movers = per_role[per_role["read"].str.lower().str.startswith(("sell", "loan", "surplus"))]
    movers = movers.loc[movers.groupby("tid")["eff"].idxmax()].sort_values("age")
    if not movers.empty:
        mrows = [{"player": r["name_label"], "age": fmt_num(r["age"]), "role": r["role"],
                  "pos": r["position"], "div": bar(r["div_pct"]), "read": pill(r["read"])}
                 for _, r in movers.iterrows()]
        out.append(f"<h2>Moving on · {len(mrows)}</h2>")
        out.append(table(mrows, [("player", "Player", "name"), ("age", "Age", "num"),
                                 ("role", "Role", "text"), ("pos", "Pos", "text"),
                                 ("div", "Div %ile", "raw"), ("read", "Read", "raw")]))

    api = "".join(f'<li><code>{esc(k)}</code> — {esc(v)}</li>' for k, v in sizes)
    out.append(f"""<h2>For Claude</h2><div class=card>
Point Claude at <code>api/index.json</code> on this host and it can answer squad questions with
both laptops off. Files:<ul style="margin:6px 0 0;padding-left:20px">{api}</ul>
<p class=note>{esc(ATTR_NOTE)}</p></div>""")
    return "\n".join(out)


# --------------------------------------------------------------------------- api payloads
def player_api_rows(eff_club, attrs, pos_by_tid, bio):
    """Per-player JSON for one club — primary position row, all positions, attributes."""
    prim = eff_club.loc[eff_club.groupby("tid")["familiarity"].idxmax()]
    amap = {int(r["tid"]): {k: (None if r[k] != r[k] else int(r[k]))
                            for k in attrs.columns if k not in ("tid", "club_tid")}
            for _, r in attrs.iterrows()} if not attrs.empty else {}
    out = []
    for _, r in prim.sort_values("eff", ascending=False).iterrows():
        tid = int(r["tid"])
        out.append({
            "tid": tid, "name": r["name"] if isinstance(r["name"], str) else None,
            "age": bio.get(tid, {}).get("Age"),
            "position": r["position"], "role": r["role"],
            "familiarity": int(r["familiarity"]),
            "positions": pos_by_tid.get(tid, {}),
            "rating": round(float(r["eff"]), 1),
            "fit_pctile_league": r.get("pctile_league"),
            "fit_pctile_nation": r.get("pctile_nation"),
            "level_pctile_league": r.get("level_league"),
            "level_pctile_nation": r.get("level_nation"),
            "attributes": amap.get(tid, {})})
    return out


SHORTLIST_JS = r"""
const API = "/api/shortlist";
const tokKey = "fm_shortlist_token";
const $ = (id) => document.getElementById(id);
function tok() { return localStorage.getItem(tokKey) || ""; }
function setStatus(msg, bad) {
  const el = $("status");
  el.textContent = msg;
  el.className = bad ? "pill bad" : "pill good";
}
function saveToken() {
  const v = $("token").value.trim();
  if (!v) { localStorage.removeItem(tokKey); setStatus("token cleared", true); return; }
  localStorage.setItem(tokKey, v);
  $("token").value = "";
  setStatus("token saved on this device");
  load();
}
function parseMap(text) {
  const out = {};
  for (const part of (text || "").split(/[,;]/)) {
    const m = part.trim().match(/^([A-Za-z]+)\s*[:= ]\s*(\d+)$/);
    if (m) out[m[1].toUpperCase()] = parseInt(m[2], 10);
  }
  return out;
}
async function load() {
  if (!tok()) { setStatus("paste your token to load the shortlist", true); return; }
  setStatus("loading…");
  try {
    const r = await fetch(API, { headers: { "x-fm-token": tok() } });
    const d = await r.json();
    if (!r.ok) { setStatus(d.error || ("HTTP " + r.status), true); return; }
    render(d.entries || []);
    setStatus(d.count + " on the shortlist");
  } catch (e) { setStatus("network error: " + e.message, true); }
}
function render(rows) {
  const tb = $("rows");
  tb.innerHTML = "";
  for (const e of rows) {
    const pos = Object.entries(e.positions || {}).map(([k, v]) => k + " " + v).join(", ");
    const tr = document.createElement("tr");
    const cells = [e.name || "", e.tid == null ? "" : e.tid, pos, e.note || "",
                   (e.added_at || "").slice(0, 10), e.source || ""];
    for (const c of cells) {
      const td = document.createElement("td");
      td.textContent = c;
      tr.appendChild(td);
    }
    const td = document.createElement("td");
    const b = document.createElement("button");
    b.textContent = "remove";
    b.onclick = () => remove(e.id);
    td.appendChild(b);
    tr.appendChild(td);
    tb.appendChild(tr);
  }
}
async function add(ev) {
  ev.preventDefault();
  if (!tok()) { setStatus("paste your token first", true); return; }
  const body = { name: $("name").value.trim(), tid: $("tid").value.trim() || null,
                 positions: parseMap($("positions").value),
                 note: $("note").value.trim(), source: "phone" };
  if (!body.name) { setStatus("a name is required", true); return; }
  setStatus("saving…");
  try {
    const r = await fetch(API, { method: "POST",
      headers: { "x-fm-token": tok(), "content-type": "application/json" },
      body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) { setStatus(d.error || ("HTTP " + r.status), true); return; }
    $("name").value = ""; $("tid").value = ""; $("positions").value = ""; $("note").value = "";
    load();
  } catch (e) { setStatus("network error: " + e.message, true); }
}
async function remove(id) {
  if (!confirm("Remove this entry?")) return;
  const r = await fetch(API + "?id=" + encodeURIComponent(id),
                        { method: "DELETE", headers: { "x-fm-token": tok() } });
  if (!r.ok) { const d = await r.json(); setStatus(d.error || ("HTTP " + r.status), true); return; }
  load();
}
window.addEventListener("DOMContentLoaded", () => {
  $("addform").addEventListener("submit", add);
  $("savetok").addEventListener("click", saveToken);
  $("reload").addEventListener("click", load);
  if (tok()) load(); else setStatus("paste your token to load the shortlist", true);
});
"""


def build_shortlist_page():
    """The only page that WRITES. Everything else here is a pre-rendered read of one snapshot;
    a player you spot in-game on the phone exists nowhere until it's recorded, so this one
    talks to `functions/api/shortlist.ts` over the same R2 bucket the laptops sync against.

    The token is pasted once and kept in localStorage rather than baked into the page: a
    committed secret is a published secret. It gates writes to a football save — it is not
    per-user auth, and the page says so.
    """
    return """<h2>Shortlist</h2>
<div class=card>
  <form id=addform>
    <p><input id=name placeholder="Player name" style="width:100%;padding:8px" required></p>
    <p><input id=tid placeholder="tid (optional, if you know it)"
              style="width:100%;padding:8px" inputmode=numeric></p>
    <p><input id=positions placeholder="Positions and familiarity — e.g. DL 18, DC 12"
              style="width:100%;padding:8px"></p>
    <p><input id=note placeholder="Note (why he's worth a look)" style="width:100%;padding:8px"></p>
    <p><button type=submit style="padding:8px 16px">Add to shortlist</button>
       <button type=button id=reload style="padding:8px 16px">Reload</button>
       <span id=status class="pill flat">—</span></p>
  </form>
</div>
<div class=scroll><table><thead><tr>
  <th>Player</th><th>tid</th><th>Positions</th><th>Note</th><th>Added</th><th>Source</th><th></th>
</tr></thead><tbody id=rows></tbody></table></div>
<p class=note>Entries are written straight to R2 as one object each, so an add from the phone
can never collide with an add from a laptop. Both laptops pick it up on their next sync and it
shows in the Streamlit Squad Tool.</p>
<h3>Device token</h3>
<div class=card>
  <p><input id=token type=password placeholder="Paste FM_SHORTLIST_TOKEN"
            style="width:100%;padding:8px" autocomplete=off>
  <button type=button id=savetok style="padding:8px 16px">Save on this device</button></p>
  <p class=note>Stored in this browser's localStorage, never in the page source — a committed
  secret is a published one. It gates writes so a stranger who finds the URL can't add to your
  shortlist; it is not per-user auth, and it does reach the browser. Save it once per device.</p>
</div>
<script>""" + SHORTLIST_JS + """</script>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career", help="career key (default: the configured/newest store)")
    ap.add_argument("--season", type=int, help="snapshot season (default: newest)")
    ap.add_argument("--phase", help="snapshot phase / in-game date (default: newest)")
    ap.add_argument("--method", help="role-weight method (default: config default_method)")
    ap.add_argument("--min-fam", type=int, default=None,
                    help="familiarity floor for depth charts and comparison pools")
    ap.add_argument("--out", default=os.path.join(REPO, "site"), help="output directory")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the immersion-rule grep over the emitted JSON")
    ap.add_argument("--clean", action="store_true", help="wipe the output dir first")
    a = ap.parse_args()

    if a.career:
        os.environ["FM_CAREER"] = a.career
    # Resolve the store through the shared guard: it refuses to byte-copy a store with a live
    # writer, and falls back to a copy when only an idle dashboard holds the lock.
    from fmparser import careers as C
    car = C.resolve_career(a.career) if a.career else C.resolve_career(C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if not os.path.exists(store):
        raise SystemExit(f"no store at {store} — build it with scripts/rebuild.py")
    con, used = _dbopen.open_readonly(store, tag="site")
    con.close()
    if used != os.path.abspath(store):
        print(f"(live store is locked — building from a copy at {used})")
    os.environ["FM_DUCKDB"] = used
    os.environ["FM_DUCKDB_READONLY"] = "1"

    sys.path.insert(0, os.path.join(REPO, "dashboard"))
    import logging

    # Streamlit re-applies its configured level every time it hands out a logger, so raising
    # the level doesn't stick. Filter the one message instead: `st.cache_data` warns "No
    # runtime found" for every cached function outside a Streamlit server — which is exactly
    # what this script is — and a screenful of it buries the build report. Installed BEFORE
    # importing db (and so streamlit's cached functions) or the first batch is already out.
    class _NoRuntimeFilter(logging.Filter):
        def filter(self, rec):
            return "No runtime found" not in rec.getMessage()

    _f = _NoRuntimeFilter()

    def _quieten():
        for _name in [n for n in logging.root.manager.loggerDict if n.startswith("streamlit")]:
            _lg = logging.getLogger(_name)      # streamlit attaches a handler per logger, and
            _lg.addFilter(_f)                   # a child handler never sees the parent's filter
            for _h in _lg.handlers:
                _h.addFilter(_f)

    import streamlit                                                   # noqa: E402,F401
    _quieten()
    import db                                                          # noqa: E402
    import positions as P                                              # noqa: E402
    _quieten()

    season = a.season
    phase = a.phase
    if season is None or phase is None:
        s, p = db.latest_snapshot()
        season, phase = season or s, phase or p
    if season is None:
        raise SystemExit("no snapshots loaded in this store")
    method = a.method or db.config().get("default_method") or db.methods()[0]
    min_fam = P.DEFAULT_MIN_FAM if a.min_fam is None else a.min_fam
    built = datetime.datetime.now().isoformat(timespec="seconds")

    out = os.path.abspath(a.out)
    if a.clean and os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "api", "club"), exist_ok=True)

    print(f"building {car.key} {season}/{phase} · {method} · fam>={min_fam} -> {out}")

    D = P.build(season, phase, method, min_fam=min_fam, excl_loanees=True)
    if "error" in D:
        raise SystemExit(f"cannot build: {D['error']}")

    # ---------------------------------------------------------------- api
    eff = db.effective_table(season, phase, method)
    eff = db._add_position_index(eff)
    ladder = D["ladder"]
    club_files, api_written = [], []

    league_clubs = {}
    for cid, lname in ladder:
        t = db.teams_in_league(season, phase, cid)
        league_clubs[cid] = [] if t.empty else [(int(r.tid), r.name) for r in t.itertuples()]
    # our reserve side sits in its own league, so add our clubs explicitly
    known = {tid for v in league_clubs.values() for tid, _ in v}
    extra = [(int(t), None) for t in db.OUR_CLUBS if t and int(t) not in known]

    all_clubs = [(cid, lname, tid, cname)
                 for cid, lname in ladder for tid, cname in league_clubs[cid]]
    all_clubs += [(None, None, tid, cname) for tid, cname in extra]

    pos_all = db.q("SELECT tid, position, familiarity FROM staging.player_positions "
                   "WHERE season=? AND phase=?", [season, phase])
    pos_by_tid = {}
    for r in pos_all.itertuples():
        pos_by_tid.setdefault(int(r.tid), {})[r.position] = int(r.familiarity)

    empty_clubs = []
    for cid, lname, tid, cname in all_clubs:
        ec = eff[eff["club_tid"] == tid]
        if ec.empty:
            # A club with no rated players has nothing to publish, but dropping it without
            # saying so makes a 12-team division read as 11 — the exact trap that made an
            # earlier verification claim the wrong division size.
            empty_clubs.append({"tid": tid, "name": cname, "league_cid": cid, "league": lname})
            continue
        attrs = db.club_attributes(season, phase, [tid])
        bio = db.player_bio(season, phase, [int(t) for t in ec["tid"].unique()])
        frame = db.squad_frame(season, phase, method, [tid])
        units, team = db.team_strength(frame, tid) if not frame.empty else (None, {"index": None,
                                                                                  "pctile": None,
                                                                                  "n": 0})
        name = cname or (ec["club"].dropna().iloc[0] if ec["club"].notna().any() else f"#{tid}")
        payload = {
            "club": {"tid": tid, "name": name, "league_cid": cid, "league": lname,
                     "is_us": tid in db.OUR_CLUBS},
            "snapshot": {"career": car.key, "season": season, "phase": phase, "method": method},
            "strength": {"index": team["index"], "pctile": team["pctile"],
                         "best_xi_n": team["n"],
                         "units": (units.to_dict("records") if units is not None else [])},
            "players": player_api_rows(ec, attrs, pos_by_tid, bio),
            "note": ATTR_NOTE}
        p = os.path.join(out, "api", "club", f"{tid}.json")
        size = write_json(p, payload, db)
        club_files.append({"tid": tid, "name": name, "league_cid": cid, "league": lname,
                           "file": f"api/club/{tid}.json", "players": len(payload["players"]),
                           "bytes": size, "is_us": tid in db.OUR_CLUBS})

    # our squad, in full
    per_role = D["per_role"]
    elig = db.eligibility_frame(season, phase)
    origin = dict(zip(elig["tid"], elig["origin_club"])) if not elig.empty else {}
    eligible = dict(zip(elig["tid"], elig["eligible"])) if not elig.empty else {}
    attrs_ours = db.club_attributes(season, phase, list(db.OUR_CLUBS))
    amap = {int(r["tid"]): {k: (None if r[k] != r[k] else int(r[k]))
                            for k in attrs_ours.columns if k not in ("tid", "club_tid")}
            for _, r in attrs_ours.iterrows()} if not attrs_ours.empty else {}
    squad_players = []
    for tid, g in per_role.groupby("tid"):
        tid = int(tid)
        best = g.loc[g["eff"].idxmax()]
        ci = D["contract"].get(tid, {})
        prev = D["prev"]
        ls = None
        if prev is not None and not prev.empty and tid in prev.index:
            r = prev.loc[tid]
            ls = {"season": season - 1, "starts": int(r.starts), "apps": int(r.apps),
                  "minutes": int(r.mins), "avg_rating": round(float(r.rat), 2)}
        squad_players.append({
            "tid": tid, "name": best["name_label"], "age": best["age"],
            "primary_role": best["role"], "primary_position": best["position"],
            "squad_status": D["status"].get(tid), "positions": pos_by_tid.get(tid, {}),
            "contract": {"expiry": ci.get("Expiry"), "wage_gbp_per_year": ci.get("Wage")},
            "origin_club": origin.get(tid), "capital_eligible": bool(eligible.get(tid, False)),
            "last_season": ls,
            "attributes": amap.get(tid, {}),
            "roles": [{
                "role": r["role"], "position": r["position"],
                "familiarity": int(r["familiarity"]), "depth": int(r["depth"]),
                "rating": round(float(r["eff"]), 1),
                "fit_pctile_division": r["fit_div"],
                "ability_pctile_division": r["div_pct"],
                "ability_rank": {str(cid): (list(D["ranks"][(tid, r["position"], cid)])
                                            if (tid, r["position"], cid) in D["ranks"] else None)
                                 for cid, _ in ladder},
                "first_choice_at_clubs_below": {
                    str(cid): D["starts_at"].get((tid, r["position"], cid), 0)
                    for cid, _ in D["lower"]},
                "read": r["read"], "also": r["also"]}
                for _, r in g.sort_values("eff", ascending=False).iterrows()]})
    # Everyone we own, not just the depth-chart population. The depth charts exclude
    # loaned-IN players (they go back) and anyone with no position above the familiarity
    # floor — correct for planning, wrong for a file that claims to be the squad. They are
    # carried here with `in_depth_charts: false` and the reason, so nothing is silently missing.
    rated = {int(t) for t in per_role["tid"].unique()}
    loaned_in_tids = set()
    if not db.q("SELECT 1 AS ok FROM information_schema.columns WHERE table_schema='staging' "
                "AND table_name='players' AND column_name='loaned_in'").empty:
        loaned_in_tids = {int(t) for t in db.q(
            "SELECT tid FROM staging.players WHERE season=? AND phase=? AND loaned_in",
            [season, phase])["tid"]}
    for p_ in squad_players:
        p_["loaned_in"] = p_["tid"] in loaned_in_tids
        p_["in_depth_charts"] = True
    sq_all = db.squad(season, phase)
    bio_all = db.player_bio(season, phase, [int(t) for t in sq_all["tid"]])
    for r in sq_all.itertuples():
        tid = int(r.tid)
        if tid in rated:
            continue
        pos = pos_by_tid.get(tid, {})
        best_pos = max(pos, key=pos.get) if pos else None
        ci = D["contract"].get(tid, {})
        squad_players.append({
            "tid": tid, "name": db.player_label(tid, r.name),
            "age": bio_all.get(tid, {}).get("Age"),
            "primary_role": db.pos_role_map().get(best_pos), "primary_position": best_pos,
            "squad_status": r.status, "positions": pos,
            "contract": {"expiry": ci.get("Expiry"), "wage_gbp_per_year": ci.get("Wage")},
            "origin_club": origin.get(tid), "capital_eligible": bool(eligible.get(tid, False)),
            "last_season": None, "attributes": amap.get(tid, {}), "roles": [],
            "loaned_in": tid in loaned_in_tids, "in_depth_charts": False,
            "excluded_because": ("loaned in — goes back at the end of the spell"
                                 if tid in loaned_in_tids else
                                 f"no position at familiarity {min_fam} or above")})
    squad_players.sort(key=lambda p: (not p["in_depth_charts"], p["primary_role"] or "zz",
                                      -(p["roles"][0]["rating"] if p["roles"] else 0)))
    api_written.append(("api/squad.json", write_json(
        os.path.join(out, "api", "squad.json"),
        {"snapshot": {"career": car.key, "season": season, "phase": phase, "method": method,
                      "min_familiarity": min_fam, "division": D["our_lg"],
                      "division_cid": D["our_cid"],
                      "ladder": [{"cid": c, "name": n} for c, n in ladder]},
         "club": {"tid": db.MANAGED_CLUB_TID, "name": car.name,
                  "reserve_tid": db.RESERVE_CLUB_TID},
         "counts": {"owned": len(squad_players), "in_depth_charts": len(rated),
                    "loaned_in": len(loaned_in_tids)},
         "players": squad_players, "note": ATTR_NOTE}, db)))

    # the position review, as data
    api_written.append(("api/positions.json", write_json(
        os.path.join(out, "api", "positions.json"),
        {"snapshot": {"career": car.key, "season": season, "phase": phase, "method": method,
                      "min_familiarity": min_fam, "slots": D["slots"],
                      "division": D["our_lg"], "division_cid": D["our_cid"],
                      "ladder": [{"cid": c, "name": n} for c, n in ladder]},
         "summary": [{**{k: v for k, v in r._asdict().items() if k != "Index"},
                      "rank_ours": (list(r.rank_ours) if r.rank_ours else None)}
                     for r in D["summary"].itertuples()],
         "depth": [{"role": role,
                    "slots": D["slots"].get(role, 1),
                    "players": [{
                        "tid": int(r["tid"]), "name": r["name_label"], "age": r["age"],
                        "depth": int(r["depth"]), "position": r["position"],
                        "familiarity": int(r["familiarity"]),
                        "rating": round(float(r["eff"]), 1),
                        "fit_pctile_division": r["fit_div"],
                        "ability_pctile_division": r["div_pct"],
                        "read": r["read"]}
                        for _, r in D["per_role"][D["per_role"]["role"] == role]
                        .sort_values("eff", ascending=False).iterrows()]}
                   for role in D["roles_present"]],
         "read_rules": "keep/cover/loan/sell verdicts from depth, division ability percentile, "
                       "age, and whether a club below us would play him first choice",
         "note": ATTR_NOTE}, db)))

    # results + per-player season output
    hist = db.our_match_history()
    form_payload = {"snapshot": {"career": car.key, "season": season, "phase": phase},
                    "matches": [], "note": ATTR_NOTE}
    if not hist.empty:
        keep = ["season", "date", "competition", "venue", "opponent", "opp_tid", "gf", "ga",
                "result", "pts", "formation"]
        form_payload["matches"] = hist[keep].sort_values(
            ["season", "date"], ascending=False).to_dict("records")
    api_written.append(("api/form.json", write_json(
        os.path.join(out, "api", "form.json"), form_payload, db)))

    index_payload = {
        "generated_at": built,
        "career": {"key": car.key, "name": car.name, "managed_tid": db.MANAGED_CLUB_TID,
                   "reserve_tid": db.RESERVE_CLUB_TID},
        "snapshot": {"season": season, "phase": phase, "method": method,
                     "min_familiarity": min_fam, "division": D["our_lg"],
                     "division_cid": D["our_cid"]},
        "snapshots_available": db.labels_df()[["season", "phase", "label"]].to_dict("records"),
        "ladder": [{"cid": c, "name": n} for c, n in ladder],
        "files": {"squad": "api/squad.json", "positions": "api/positions.json",
                  "form": "api/form.json", "clubs": "api/club/<tid>.json"},
        "clubs": club_files,
        "clubs_without_rated_players": empty_clubs,
        "pages": [{"file": f, "title": t} for f, t in PAGES],
        "immersion_rule": ATTR_NOTE,
        "caveats": [
            "Opponent tactics and formation are NOT in the save file — ask the manager for the "
            "in-game scout's formation and style before advising on a match.",
            "Opponent attribute values are model estimates (±1) except pace and physicals.",
            "Squad status and loan flags in the save are unreliable; rank by minutes played.",
            "staging.standings parses only partially for this career, so there is no league "
            "table here — divisions.html ranks clubs by squad strength instead."]}
    api_written.append(("api/index.json", write_json(
        os.path.join(out, "api", "index.json"), index_payload, db)))

    # ---------------------------------------------------------------- html
    head = head_block(car, season, phase, D["our_lg"], built)
    sizes = [(f, f"{n / 1024:.0f} KB") for f, n in api_written]
    sizes.append((f"api/club/*.json", f"{len(club_files)} clubs, "
                                      f"{sum(c['bytes'] for c in club_files) / 1024:.0f} KB"))
    bodies = {
        "index.html": build_index_page(D, db, car, season, phase, method, sizes),
        "positions.html": build_positions_page(D, db, P),
        "squad.html": build_squad_page(D, db, P, season, phase, method),
        "form.html": build_form_page(db, season),
        "divisions.html": build_divisions_page(db, D, season, phase, method),
        "shortlist.html": build_shortlist_page()}
    for fname, title in PAGES:
        with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
            f.write(page(fname, f"{car.name} · {title}", head, bodies[fname], built))

    # ---------------------------------------------------------------- report + guard
    total = 0
    for root, _d, files in os.walk(out):
        for fn in files:
            total += os.path.getsize(os.path.join(root, fn))
    print(f"  {len(PAGES)} html pages, {len(api_written)} api files, "
          f"{len(club_files)} club files — {total / 1024:.0f} KB total")

    if not a.no_check:
        bad = check_immersion(os.path.join(out, "api"))
        if bad:
            print("\nIMMERSION RULE VIOLATED — raw ability leaked into published JSON:")
            for f, k in bad:
                print(f"  {f}: key {k!r}")
            return 1
        print("  immersion check: no raw ability keys in api/ ✓")
    return 0


BANNED_KEYS = {"ca", "pa", "current_ability", "potential_ability", "aca"}


def check_immersion(api_dir):
    """Walk every emitted JSON and refuse any raw-ability key, at any depth.

    A grep would miss `{"CA": ...}` and false-positive on the word inside prose; parsing and
    checking keys is exact. Percentile/rank fields are the only sanctioned ability exposure,
    and they never use these names."""
    bad = []

    def walk(o, f):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).strip().lower() in BANNED_KEYS:
                    bad.append((f, k))
                walk(v, f)
        elif isinstance(o, list):
            for v in o:
                walk(v, f)

    for root, _d, files in os.walk(api_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as fh:
                walk(json.load(fh), os.path.relpath(p, os.path.dirname(api_dir)))
    return bad


if __name__ == "__main__":
    sys.exit(main())
