"""Player development — squad-wide growth (who's improving, is it slowing) + per-player detail.

Squad growth: each player's weighted-rating trajectory as an in-table sparkline, the rating gain
(Δ) since their first snapshot, Fit/Level percentiles, contract detail, and a contract-watch
panel. Both tables run on the shared `stat_table.player_table`, so every column — plus any
attribute or match stat — is add/remove from one picker; unit / position / age-band / loaned-in
filters sit above them and apply to the chart and both tables. Players loaned IN are EXCLUDED by
default (someone else's asset — their growth isn't ours to bank, and they were topping the
"who's improving" chart). Per-player: rating + attribute trajectories.

Player detail also carries an availability timeline — injury spells and loan moves unioned
across every snapshot (no single save holds a player's whole history) — shaded behind the
rating trace and listed underneath. The trace can be read against per-snapshot benchmarks
(our best / squad median / division median at the role) and against named teammates, so a
trajectory is judged relative to the standard he competes with rather than in isolation.

Everything time-based is plotted against the save's in-game DATE, not snapshot ordinal, so
clustered saves don't read as a stall (that's also what Δ/yr and Gap (d) are for).
No CA/PA reveal — growth is shown via the weighted rating and the percentiles only.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import stat_table

st.set_page_config(page_title="Development", page_icon="📈", layout="wide")
st.title("📈 Player development")

method = db.select_method()
posmap = db.pos_role_map()

AGE_BANDS = ["U21", "21-24", "25-28", "29+"]

# Rating-chart palette. One hue per KIND of line so the eye separates them instantly:
#   RED   = the player you're looking at (always the most prominent thing on the chart)
#   BLUE  = benchmarks   — medians at 80% opacity, the "best" line at 50% (it's context)
#   GREEN = teammates    — best at 80%, next at 50%, any further additions fainter still
# Dash style separates the three benchmarks from each other without adding a fourth hue.
SUBJECT_COLOURS = ["#d62728", "#ff8a8a", "#7f1416"]     # extra shades if several roles plotted
BENCHMARKS = {                       # label: (column, scope, colour, dash)
    "Division median": ("median", "league", "rgba(31,119,180,0.80)", "dash"),
    "Squad median": ("median", "squad", "rgba(31,119,180,0.80)", "dot"),
    "Our best at role": ("best", "squad", "rgba(31,119,180,0.50)", "dashdot"),
}
MATE_COLOURS = ["rgba(44,160,44,0.80)", "rgba(44,160,44,0.50)",
                "rgba(44,160,44,0.35)", "rgba(44,160,44,0.25)"]

# Availability bands sit BEHIND everything, in neutral hues — red/blue/green are all spoken
# for by the lines now, so a red injury band would smear the player's own trace.
BAND_INJURY = "rgba(255, 159, 64, 0.20)"     # amber — out injured
BAND_LOAN = "rgba(130, 130, 130, 0.18)"      # grey  — on loan


def add_spell_bands(fig, spells, colour, x0="start", x1="end"):
    """Shade each (x0, x1) spell behind the traces. Returns how many were drawn."""
    n = 0
    for r in spells.itertuples():
        a, b = getattr(r, x0), getattr(r, x1)
        if pd.isna(a) or pd.isna(b):
            continue
        fig.add_vrect(x0=a, x1=b, fillcolor=colour, line_width=0, layer="below")
        n += 1
    return n

# Every column the squad-growth tables can show, in display order. Both tables offer the
# whole list through the shared picker — these are just the options and their formatting;
# `default_cols` at each call site decides what's visible on first render.
COL_ORDER = ["Player", "Pos", "Unit", "Role", "Age", "Band", "Value", "Wage", "Wage %ile",
             "Expiry", "Loan", "Fit %ile", "Level %ile", "Fam", "Δ Fam", "Rating", "Δ Rating",
             "Δ/yr", "Recent Δ", "Prior Δ", "Gap (d)", "Trajectory"]

# '…%ile' columns become progress bars automatically (stat_table._auto_column_config).
COL_CONFIG = {
    "Age": st.column_config.NumberColumn(width="small"),
    "Value": st.column_config.NumberColumn(format="%d"),
    "Wage": st.column_config.NumberColumn("Wage £/yr", format="£%d",
        help="decoded from the contract record (≈±2%)"),
    "Expiry": st.column_config.DateColumn("Expiry", format="MMM YYYY"),
    "Loan": st.column_config.TextColumn("Loan from",
        help="parent club for players loaned IN — blank means we own them"),
    "Fit %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100,
        help="how well they suit this tactic's role at their best position, vs the league"),
    "Level %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100,
        help="tactic-agnostic quality vs the league — read the gap to Fit %ile"),
    "Fam": st.column_config.NumberColumn("Fam", width="small",
        help="familiarity (1-20) at their primary position, latest snapshot"),
    "Δ Fam": st.column_config.NumberColumn("Δ Fam", width="small",
        help="familiarity gained since their first snapshot — part of Δ Rating is learning "
             "the position rather than gaining attributes"),
    "Δ Rating": st.column_config.NumberColumn("Δ Rating",
        help="rating gained since their first snapshot, familiarity included"),
    "Δ/yr": st.column_config.NumberColumn("Δ/yr", format="%.1f",
        help="Δ Rating annualised over the in-game days actually elapsed — the fair way to "
             "compare players whose snapshots are spaced differently"),
    "Recent Δ": st.column_config.NumberColumn("Recent Δ",
        help="gain in the most recent step — read it next to Gap (d): a small gain over a "
             "short gap is not a stall"),
    "Prior Δ": st.column_config.NumberColumn("Prior Δ", help="gain in the step before that"),
    "Gap (d)": st.column_config.NumberColumn("Gap (d)", width="small",
        help="in-game days between the last two snapshots"),
    "Trajectory": st.column_config.LineChartColumn("Trajectory",
        help="weighted rating resampled onto a real time axis — width is proportional to "
             "elapsed in-game time, so clustered saves no longer stretch the line"),
}

_ph = ",".join(str(int(t)) for t in db.OUR_CLUBS)
allsq = db.q(f"SELECT tid, any_value(name) AS name FROM staging.players "
             f"WHERE club_tid IN ({_ph}) AND NOT is_staff GROUP BY tid")
if allsq.empty:
    st.info("No managed-club players loaded.")
    st.stop()
allsq["label"] = allsq.apply(lambda r: db.player_label(r.tid, r["name"]), axis=1)
allsq = db.by_surname(allsq, "label")

_labels = db.labels_df()
snaps = list(_labels[["season", "phase"]].itertuples(index=False, name=None))
# snapshot -> real in-game date, so every trajectory is plotted on a true time axis
# (saves taken days apart no longer read as a full development step)
snap_date = {(int(r.season), r.phase): r.date for r in _labels.itertuples()}

tab_team, tab_player = st.tabs(["🏆 Squad growth", "👤 Player detail"])

# ============================================================ SQUAD GROWTH
with tab_team:
    if len(snaps) < 2:
        st.info("Only one snapshot loaded — growth needs at least two. The trajectory sparklines "
                "and Δ will populate as more saves are imported.")
    ls, lp = snaps[-1]                                   # latest snapshot
    sq = db.squad(ls, lp)
    tids = [int(t) for t in sq["tid"]]

    # primary position (latest snapshot) → the role whose rating series we track per player,
    # and the pitch unit it belongs to (both are filterable below)
    pos = db.q("SELECT tid, arg_max(position, familiarity) AS pp FROM staging.player_positions "
               "WHERE season=? AND phase=? GROUP BY tid", [ls, lp])
    ppos = {int(r.tid): r.pp for r in pos.itertuples()}
    prole = {t: posmap.get(p, "CM") for t, p in ppos.items()}

    # familiarity-ADJUSTED ratings: a player who learns his position gains here even with flat
    # attributes, which is real development the raw weighted rating hides entirely
    rt = db.squad_role_series(tids, method)

    bio = db.attach_bio(pd.DataFrame({"tid": tids}), ls, lp)
    age = dict(zip(bio["tid"], bio["Age"])); val = dict(zip(bio["tid"], bio["Value"]))
    # Loan = parent club for players loaned IN (None if owned). This is the reliable flag —
    # it comes from the squad-snapshot region, NOT the stale contract-status `loaned_out`.
    loan = dict(zip(bio["tid"], bio["Loan"]))
    contracts = db.contract_info(ls, lp, tids)   # {tid: {Wage £/yr, Expiry date}} (may be empty)
    eff = db.effective_table(ls, lp, method)
    eff = eff[eff["club_tid"].isin(list(db.OUR_CLUBS))] if not eff.empty else eff
    # both percentiles are read at the player's most-familiar position, league-scoped:
    # Fit %ile = how well they suit THIS tactic's role; Level %ile = tactic-agnostic quality.
    level, fit = {}, {}
    if not eff.empty:
        for r in eff.sort_values("familiarity", ascending=False).itertuples():
            level.setdefault(int(r.tid), r.level_league)
            fit.setdefault(int(r.tid), r.pctile_league)

    def band(a):
        if a is None or a != a:
            return "?"
        return AGE_BANDS[0] if a < 21 else AGE_BANDS[1] if a <= 24 \
            else AGE_BANDS[2] if a <= 28 else AGE_BANDS[3]

    rows = []
    for t in tids:
        role = prole.get(t, "CM")
        s = rt[(rt["tid"] == t) & (rt["role"] == role)].sort_values("date")
        if s.empty:
            continue
        series = [round(x) for x in s["rating"].tolist()]
        dates = list(s["date"])
        fams = [int(f) for f in s["fam"].tolist()]
        d_fam = fams[-1] - fams[0] if len(fams) > 1 else 0
        delta = series[-1] - series[0] if len(series) > 1 else 0
        recent = series[-1] - series[-2] if len(series) > 1 else 0
        prior = series[-2] - series[-3] if len(series) > 2 else None
        # rate-of-growth, not raw step size: two saves a week apart can't show much gain,
        # so annualise it before judging whether a player has stalled.
        span_days = (dates[-1] - dates[0]).days if len(dates) > 1 else 0
        gap_days = (dates[-1] - dates[-2]).days if len(dates) > 1 else 0
        per_yr = round(delta * 365 / span_days, 1) if span_days >= 14 else None
        rows.append({
            "key": t, "tid": t,
            "Player": db.player_label(t, sq.set_index("tid").loc[t, "name"]),
            "Pos": ppos.get(t), "Unit": db.POSITION_UNIT.get(ppos.get(t)),
            "Role": role, "Age": age.get(t), "Band": band(age.get(t)),
            "Value": val.get(t), "Wage": (contracts.get(t) or {}).get("Wage"),
            "Expiry": (contracts.get(t) or {}).get("Expiry"), "Loan": loan.get(t),
            "Fit %ile": fit.get(t), "Level %ile": level.get(t),
            "Fam": fams[-1], "Δ Fam": d_fam or None, "Rating": series[-1],
            "Δ Rating": delta, "Δ/yr": per_yr, "Recent Δ": recent, "Prior Δ": prior,
            "Gap (d)": gap_days if gap_days else None,
            "Trajectory": db.even_time_series(dates, series)})
    growth = pd.DataFrame(rows)
    if not growth.empty:      # int|None -> float|NaN, so the column sorts and renders blank
        growth["Δ Fam"] = pd.to_numeric(growth["Δ Fam"], errors="coerce")

    if growth.empty:
        st.info("No rating series for the squad yet.")
    else:
        growth = growth.sort_values("Δ Rating", ascending=False).reset_index(drop=True)
        has_wage = "Wage" in growth and growth["Wage"].notna().any()
        # Familiarity only earns table space when it actually moves. At a player's PRIMARY role
        # it's almost always already 20 — the column fires when someone retrains and a new
        # position becomes their best, which is exactly the case worth catching.
        fam_moved = growth["Δ Fam"].notna().any()
        fam_varies = fam_moved or growth["Fam"].nunique() > 1
        if has_wage:                       # squad-relative wage percentile (immersion-safe)
            growth["Wage %ile"] = growth["Wage"].rank(pct=True) * 100

        # ---- filters (apply to everything below) ----
        # loaned-IN players default to hidden: they're someone else's asset, so their growth
        # isn't ours to bank and they distort the squad-wide picture. The control only appears
        # when the snapshot actually knows about loanees (older stores have no loaned_in).
        has_loanees = growth["Loan"].notna().any()
        # the loan mode is read from session_state BEFORE its widget renders, so the position
        # options below only offer positions someone in the loan-filtered pool actually plays
        loan_mode = st.session_state.get("dev_loan", "Exclude") if has_loanees else "Include"
        pool = growth[growth["Loan"].isna()] if loan_mode == "Exclude" else \
               growth[growth["Loan"].notna()] if loan_mode == "Only" else growth

        f1, f2, f3, f4 = st.columns(4) if has_loanees else (*st.columns(3), None)
        f_units = f1.multiselect("Unit", db.UNIT_ORDER, key="dev_units")
        pos_opts = [p for p in db.POSITION_UNIT
                    if p in set(pool["Pos"].dropna())
                    and (not f_units or db.POSITION_UNIT.get(p) in f_units)]
        # a position already picked can fall out of range when the unit filter narrows —
        # prune it before the widget re-instantiates, or Streamlit errors on the stale value
        st.session_state["dev_pos"] = [p for p in st.session_state.get("dev_pos", [])
                                       if p in pos_opts]
        f_pos = f2.multiselect("Position", pos_opts, key="dev_pos",
                               help="Narrows within the chosen unit(s).")
        f_bands = f3.multiselect("Age band", AGE_BANDS, key="dev_bands")
        if has_loanees:
            f4.segmented_control(
                "Loaned-in players", ["Exclude", "Include", "Only"], default="Exclude",
                key="dev_loan", help="Players loaned IN from another club. (Loaned-OUT status "
                                     "isn't trustworthy in these saves and is not filtered on.)")

        view = pool
        if f_units:
            view = view[view["Unit"].isin(f_units)]
        if f_pos:
            view = view[view["Pos"].isin(f_pos)]
        if f_bands:
            view = view[view["Band"].isin(f_bands)]
        if view.empty:
            st.info("No players match these filters.")
        else:
            if len(view) < len(growth):
                st.caption(f"Filtered to **{len(view)}** of {len(growth)} squad players.")

            # ---- who's improving the most ----
            st.subheader("Who's improving the most")
            _d0, _d1 = snap_date.get((snaps[0][0], snaps[0][1])), snap_date.get((ls, lp))
            _span = f" — {(_d1 - _d0).days} in-game days" if pd.notna(_d0) and pd.notna(_d1) else ""
            st.caption(f"Change in **{method}** weighted rating from first → latest snapshot "
                       f"({snaps[0][0]} {snaps[0][1]} → {ls} {lp}{_span}), coloured by age band. "
                       "Note: loan status doesn't parse reliably for this Denmark save, so a flat ~0 "
                       "gain *may* just be a player away on loan whose attributes didn't refresh — "
                       "cross-check against who's actually out.")
            fig = px.bar(view, x="Player", y="Δ Rating", color="Band",
                         category_orders={"Band": AGE_BANDS + ["?"]},
                         labels={"Δ Rating": "Rating gain"})
            fig.update_layout(height=330, margin=dict(l=0, r=0, t=10, b=0),
                              xaxis={"categoryorder": "total descending"})
            st.plotly_chart(fig, width="stretch")

            # ---- trajectory table (shared player_table: add/remove any column) ----
            st.subheader("Trajectories")
            st.caption(
                "Ratings are **familiarity-adjusted**, so learning a position counts as growth: "
                "a player who converts to a new best position gains rating here even with flat "
                "attributes (**Δ Fam** shows how much of Δ Rating came from that). "
                + ("" if fam_moved else
                   "No one has changed familiarity at their primary position in these "
                   "snapshots yet, so that column is hidden."))
            st.caption("Trajectories are plotted against the save's **in-game date**, so "
                       "snapshots taken close together take up proportionally little width — a "
                       "flat stretch now means time passed without growth, not two saves in a "
                       "row.")
            opts = [c for c in COL_ORDER if c in view.columns
                    and (c != "Loan" or has_loanees)]
            # switching the loan mode toggles the "Loan from" column in/out of both pickers —
            # only ON CHANGE, so it never overrides a column the user added or removed itself
            if st.session_state.get("_dev_loan_prev") != loan_mode:
                st.session_state["_dev_loan_prev"] = loan_mode
                for k in ("dev_growth_pick", "dev_contract_pick"):
                    cur = st.session_state.get(k)
                    if cur is None:
                        continue                      # not seeded yet (first render)
                    if loan_mode == "Exclude":
                        st.session_state[k] = [c for c in cur if c != "Loan"]
                    elif "Loan" not in cur:
                        st.session_state[k] = cur + ["Loan"]
            stat_table.player_table(
                "dev_growth", view,
                id_options=opts,
                default_cols=[c for c in ["Player", "Pos", "Age", "Value", "Wage", "Expiry",
                                          "Loan", "Fit %ile", "Level %ile", "Fam", "Δ Fam",
                                          "Rating", "Δ Rating", "Δ/yr", "Recent Δ", "Gap (d)",
                                          "Trajectory"]
                              if c in opts
                              and (c != "Loan" or loan_mode != "Exclude")
                              and (c != "Fam" or fam_varies)
                              and (c != "Δ Fam" or fam_moved)],
                agg_provider=lambda keys: db.player_match_agg([int(k) for k in keys]),
                attrs_provider=lambda keys: db.attributes_rows(ls, lp, [int(k) for k in keys]),
                column_config=COL_CONFIG, height=430,
                picker_label="Columns — add/remove any field, attribute or match stat")
            if len(snaps) < 3:
                st.caption("With more snapshots the **Recent Δ** vs earlier gains (and the sparkline "
                           "shape) will show whether a player's improvement is slowing.")

            # ---- contract watch ----
            st.subheader("Contract watch")
            lo, hi = st.slider("Age band to review", 16, 40, (22, 24),
                               help="Widen to pull in older squad players (e.g. a 28-year-old) too. "
                                    "Applies on top of the filters above.")
            st.caption("Players you're deciding whether to keep (hope they grow) or move on. Sorted by "
                       "rating gain — low/zero gainers are the axe candidates, most so when they're on a "
                       "high **Wage** and not in your XI. **Expiry** shows whether the decision is even "
                       "yours yet (a deal running down walks for free). Growth + Level %ile + age + wage "
                       "are the signals; loan status still isn't reliable here.")
            cw = view[view["Age"].between(lo, hi)].sort_values("Δ Rating")
            if cw.empty:
                st.caption(f"No {lo}-{hi} year-olds match the current filters.")
            else:
                stat_table.player_table(
                    "dev_contract", cw,
                    id_options=opts,
                    default_cols=[c for c in ["Player", "Pos", "Age", "Value", "Wage", "Wage %ile",
                                              "Expiry", "Loan", "Fit %ile", "Level %ile",
                                              "Δ Rating", "Δ/yr", "Trajectory"]
                                  if c in opts and (c != "Loan" or loan_mode != "Exclude")],
                    agg_provider=lambda keys: db.player_match_agg([int(k) for k in keys]),
                    attrs_provider=lambda keys: db.attributes_rows(ls, lp, [int(k) for k in keys]),
                    column_config=COL_CONFIG,
                    picker_label="Columns (contract watch)")

# ============================================================ PLAYER DETAIL
with tab_player:
    pick = st.selectbox("Player", allsq["label"].tolist())
    tid = int(allsq.loc[allsq["label"] == pick, "tid"].iloc[0])

    pp = db.q("SELECT position, MAX(familiarity) f FROM staging.player_positions "
              "WHERE tid=? GROUP BY position ORDER BY f DESC, position", [tid])
    primary_pos = pp.iloc[0]["position"] if not pp.empty else None
    primary_role = posmap.get(primary_pos, "CM")
    wmap = db.role_weight_map(method, primary_role)
    st.caption(f"Primary position: **{primary_pos}** → role **{primary_role}**")

    if db.q("SELECT 1 FROM staging.player_attributes WHERE tid=? LIMIT 1", [tid]).empty:
        st.warning("No attribute snapshots for this player.")
        st.stop()

    # availability history — unioned across every snapshot (see db.player_injury_spells:
    # each save's weekly series only spans two calendar years, so no single save has it all)
    inj = db.player_injury_spells(tid)
    loans = db.player_loan_spells(tid)

    st.subheader("Weighted rating over time")
    st.caption("Ratings here are **familiarity-adjusted** (rating × the position's familiarity "
               "multiplier), the same measure the benchmarks below use — otherwise a player "
               "outranks specialists in a position he can barely play.")
    # only roles he has a position for: a line for a role he can't play isn't a trajectory
    his_roles = sorted({posmap[p] for p in pp["position"] if p in posmap})
    sel_roles = st.multiselect("Roles to plot", his_roles or db.roles(),
                               default=[primary_role] if primary_role in his_roles else [],
                               key=f"roles_{tid}")
    plot = pd.concat([db.player_role_series([tid], r, method) for r in sel_roles]) \
        if sel_roles else pd.DataFrame()
    if not plot.empty:
        plot["t"] = plot["season"].astype(str) + " " + plot["phase"]

    # --- what to measure him against ---
    bench_role = sel_roles[0] if sel_roles else primary_role
    ls2, lp2 = snaps[-1]
    rank = db.squad_role_ranking(ls2, lp2, bench_role, method)
    rank = rank[rank["tid"] != tid]
    mate_label = {db.player_label(int(r.tid), r.name): int(r.tid) for r in rank.itertuples()}

    leagues = db.league_options()
    div_opts = ["Our division (follows promotion)"] + [
        f"{r.name} · {int(r.clubs)} clubs" for r in leagues.itertuples()]
    div_cid = {f"{r.name} · {int(r.clubs)} clubs": int(r.cid) for r in leagues.itertuples()}

    c1, c2 = st.columns(2)
    sel_div = c1.selectbox(
        "Benchmark division", div_opts, key="dev_bench_div",
        help="Pin the division line to a specific tier to ask a different question: is he "
             "already at the standard of the league above (a step up / promotion), or would "
             "he be a big fish somewhere below (where to loan him)? The default follows our "
             "own division, so it steps up when we're promoted.")
    # benchmark choice is a preference — one key, so it persists as you browse players
    sel_bench = c1.multiselect(
        "Benchmarks", list(BENCHMARKS), default=["Our best at role", "Division median"],
        key="dev_bench",
        help=f"Aggregates at **{bench_role}**, recomputed per snapshot and familiarity-adjusted. "
             f"Peers need familiarity ≥ {db.MIN_ROLE_FAMILIARITY} at the position. The division "
             f"lines take ONE player per club — that club's best — so the median is the typical "
             f"STARTING {bench_role} in the division, not its bench depth.")
    # keyed on (player, role): changing either reseeds to that role's top two rather than
    # leaving stale names Streamlit would silently drop
    sel_mates = c2.multiselect(
        "Compare with teammates", list(mate_label), default=list(mate_label)[:2],
        key=f"mates_{tid}_{bench_role}",
        help=f"Their own {bench_role} trajectory, drawn as thin lines. Defaults to the two "
             f"best in the squad at this role — with him, that's the top three.")
    if not plot.empty:
        legend = [":red[**— this player**]", ":blue[- - benchmarks]", ":green[— teammates]",
                  "x-axis is the save's **in-game date**"]
        fig = px.line(plot, x="date", y="rating", color="role", markers=True,
                      color_discrete_sequence=SUBJECT_COLOURS,
                      hover_data={"t": True, "date": False},
                      labels={"date": "", "rating": "Rating", "role": "Role", "t": "Snapshot"})
        fig.update_traces(line_width=3.5, marker_size=8)      # the subject leads the chart
        # only band what's inside the plotted window, else one old loan rescales the axis
        lo_d, hi_d = plot["date"].min(), plot["date"].max()

        def _in_window(df, a="spell_start", b="spell_end"):
            if df.empty:
                return df
            return df[(pd.to_datetime(df[b]) >= lo_d) & (pd.to_datetime(df[a]) <= hi_d)]

        if add_spell_bands(fig, _in_window(inj), BAND_INJURY, "spell_start", "spell_end"):
            legend.append(":orange[▮ injured]")
        if add_spell_bands(fig, _in_window(loans, "start", "end"), BAND_LOAN, "start", "end"):
            legend.append(":gray[▮ on loan]")

        peers = None
        for name in sel_bench:                       # dashed aggregate benchmark lines
            col, scope, colour, dash = BENCHMARKS[name]
            cid = div_cid.get(sel_div) if scope == "league" else None
            b = db.role_benchmarks(bench_role, method, scope, league_cid=cid)
            if b.empty:
                continue
            label = name if scope == "squad" else f"{name} — {sel_div.split(' · ')[0]}"
            if scope == "league":
                peers = int(b["n"].iloc[-1])
            fig.add_scatter(x=b["date"], y=b[col], mode="lines",
                            name=f"{label} ({bench_role})",
                            line=dict(color=colour, dash=dash, width=2),
                            hovertemplate="%{y:.0f}<extra>" + label + "</extra>")
        if sel_mates:                                # thin solid lines per named teammate
            mates = db.player_role_series([mate_label[m] for m in sel_mates], bench_role, method)
            for i, m in enumerate(sel_mates):
                one = mates[mates["tid"] == mate_label[m]]
                if one.empty:
                    continue
                colour = MATE_COLOURS[i % len(MATE_COLOURS)]
                fig.add_scatter(x=one["date"], y=one["rating"], mode="lines+markers", name=m,
                                line=dict(color=colour, width=2),
                                marker=dict(size=5, color=colour),
                                hovertemplate="%{y:.0f}<extra>" + m + "</extra>")
        if peers:
            legend.append(f"division line = median of **{peers} clubs'** best {bench_role} "
                          f"(familiarity ≥ {db.MIN_ROLE_FAMILIARITY})")
        st.caption("  ·  ".join(legend))
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
        fig.update_xaxes(showgrid=True, tickformat="%b %Y", range=[lo_d, hi_d])
        st.plotly_chart(fig, width="stretch")

    # ---- availability & loan timeline ----
    st.subheader("Availability & loans")
    if inj.empty and loans.empty:
        st.caption("No injury spells or loan moves recorded for this player. Injury history "
                   "only exists for seasons in which they were in our squad at some snapshot, "
                   "and loan history needs the career-history parse.")
    else:
        m = st.columns(4)
        m[0].metric("Injury spells", len(inj))
        m[1].metric("Weeks out", int(inj["weeks_out"].sum()) if not inj.empty else 0)
        m[2].metric("Longest spell", f"{int(inj['weeks_out'].max())} wk" if not inj.empty else "—")
        m[3].metric("Loan moves", len(loans))
        st.caption(
            "Built by unioning **every** snapshot: a save's weekly Player-Progress series only "
            "spans two calendar years, so a spell an early save recorded is missing from later "
            "ones — and a loanee's data leaves with them when the loan ends. Injuries include "
            "training injuries (match events only catch in-match ones). Loans marked *approx* "
            "are bounded by the dates of the saves that observed them, not the real transfer "
            "dates.")

        tl = []
        for r in inj.itertuples():
            tl.append({"Type": "🟧 Injured", "From": r.spell_start, "To": r.spell_end,
                       "Length": f"{r.weeks_out} wk", "Club / detail": "", "Approx": False})
        for r in loans.itertuples():
            where = {"in": " (loaned to us)", "out": " (out on loan)"}.get(r.kind, "")
            detail = (r.club or ("club not recorded" if r.kind == "out" else "—")) + where
            if pd.notna(r.apps) and r.apps is not None:
                detail += f" · {int(r.apps)} apps, {int(r.goals or 0)} goals"
            if r.ongoing:
                detail += " · ongoing"
            tl.append({"Type": "⬜ On loan", "From": r.start, "To": r.end,
                       "Length": f"{max(1, round((r.end - r.start).days / 30))} mo",
                       "Club / detail": detail, "Approx": bool(r.bounded)})
        tl = pd.DataFrame(tl).sort_values("From", ascending=False)
        st.dataframe(
            tl, hide_index=True, width="stretch",
            column_config={
                "From": st.column_config.DateColumn(format="D MMM YYYY"),
                "To": st.column_config.DateColumn(format="D MMM YYYY"),
                "Approx": st.column_config.CheckboxColumn("Approx",
                    help="dates are bounded by save snapshots / the season window, not exact")})

    st.subheader("Attribute trajectories")
    st.caption(
        f"Grouped; titles colour-coded by {primary_role} importance: "
        f"<span style='color:{db.WEIGHT_COLOR[4]}'>key</span>, "
        f"<span style='color:{db.WEIGHT_COLOR[3]}'>important</span>, "
        f"<span style='color:{db.WEIGHT_COLOR[2]}'>useful</span>.", unsafe_allow_html=True)
    cols = ", ".join(f'"{a}"' for a in db.ATTR_ORDER)
    # tid alone spans every snapshot, INCLUDING ones where this tid belonged to a different
    # person before FM recycled the slot — without this the chart plots the predecessor's
    # attributes as the current player's early history (see docs/IDS.md).
    aw = db.keep_current_person(
        db.q(f"SELECT season, phase, tid, {cols} FROM staging.player_attributes WHERE tid=?",
             [tid]))
    aw["t"] = aw["season"].astype(str) + " " + aw["phase"]
    aw = db.add_phase_date(aw)
    colour_of = {a: db.WEIGHT_COLOR[wmap.get(a.lower(), 1)] for a in db.ATTR_ORDER}

    for group, members in db.ATTR_GROUPS.items():
        if group == "Goalkeeping" and primary_role != "GK":
            continue
        long = aw.melt(id_vars=["t", "date"], value_vars=members,
                       var_name="attribute", value_name="value").sort_values("date")
        st.markdown(f"**{group}**")
        fig = px.line(long, x="date", y="value", facet_col="attribute",
                      facet_col_wrap=7, markers=True, height=230,
                      hover_data={"t": True, "date": False},
                      labels={"date": "", "t": "Snapshot"})
        fig.update_yaxes(range=[0, 20])
        fig.for_each_annotation(lambda a: a.update(
            text=a.text.split("=")[-1],
            font=dict(color=colour_of.get(a.text.split("=")[-1], "#444444"))))
        fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), showlegend=False)
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, width="stretch")
