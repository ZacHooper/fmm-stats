"""Player development — squad-wide growth (who's improving, is it slowing) + per-player detail.

Squad growth: each player's weighted-rating trajectory across snapshots as an in-table sparkline,
the rating gain (Δ) since their first snapshot, age/value/loan, and a contract-watch panel for the
22-24 band. Per-player: rating + attribute trajectories. No CA/PA reveal — growth is shown via the
weighted rating and the tactic-agnostic Level %ile only.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Development", page_icon="📈", layout="wide")
st.title("📈 Player development")

method = db.select_method()
posmap = db.pos_role_map()

_ph = ",".join(str(int(t)) for t in db.OUR_CLUBS)
allsq = db.q(f"SELECT tid, any_value(name) AS name FROM staging.players "
             f"WHERE club_tid IN ({_ph}) AND NOT is_staff GROUP BY tid")
if allsq.empty:
    st.info("No managed-club players loaded.")
    st.stop()
allsq["label"] = allsq.apply(lambda r: db.player_label(r.tid, r["name"]), axis=1)
allsq = db.by_surname(allsq, "label")

snaps = list(db.labels_df()[["season", "phase"]].itertuples(index=False, name=None))

tab_team, tab_player = st.tabs(["🏆 Squad growth", "👤 Player detail"])

# ============================================================ SQUAD GROWTH
with tab_team:
    if len(snaps) < 2:
        st.info("Only one snapshot loaded — growth needs at least two. The trajectory sparklines "
                "and Δ will populate as more saves are imported.")
    ls, lp = snaps[-1]                                   # latest snapshot
    sq = db.squad(ls, lp)
    tids = [int(t) for t in sq["tid"]]

    # primary role (latest snapshot) → the rating series we track per player
    pos = db.q("SELECT tid, arg_max(position, familiarity) AS pp FROM staging.player_positions "
               "WHERE season=? AND phase=? GROUP BY tid", [ls, lp])
    prole = {int(r.tid): posmap.get(r.pp, "CM") for r in pos.itertuples()}

    rt = db.q("SELECT tid, season, phase, role, rating FROM v_player_ratings WHERE method=?",
              [method])
    rt = rt[rt["tid"].isin(tids)].copy()
    rt["ord"] = rt["season"] * 10 + rt["phase"].map(db.PHASE_ORDER)

    bio = db.attach_bio(pd.DataFrame({"tid": tids}), ls, lp)
    age = dict(zip(bio["tid"], bio["Age"])); val = dict(zip(bio["tid"], bio["Value"]))
    contracts = db.contract_info(ls, lp, tids)   # {tid: {Wage £/yr, Expiry date}} (may be empty)
    eff = db.effective_table(ls, lp, method)
    eff = eff[eff["club_tid"].isin(list(db.OUR_CLUBS))] if not eff.empty else eff
    level = {}
    if not eff.empty:
        for r in eff.sort_values("familiarity", ascending=False).itertuples():
            level.setdefault(int(r.tid), r.level_league)

    def band(a):
        if a is None or a != a:
            return "?"
        return "U21" if a < 21 else "21-24" if a <= 24 else "25-28" if a <= 28 else "29+"

    rows = []
    for t in tids:
        role = prole.get(t, "CM")
        s = rt[(rt["tid"] == t) & (rt["role"] == role)].sort_values("ord")
        if s.empty:
            continue
        series = [round(x) for x in s["rating"].tolist()]
        delta = series[-1] - series[0] if len(series) > 1 else 0
        recent = series[-1] - series[-2] if len(series) > 1 else 0
        prior = series[-2] - series[-3] if len(series) > 2 else None
        rows.append({
            "tid": t, "Player": db.player_label(t, sq.set_index("tid").loc[t, "name"]),
            "Role": role, "Age": age.get(t), "Band": band(age.get(t)),
            "Value": val.get(t), "Wage": (contracts.get(t) or {}).get("Wage"),
            "Expiry": (contracts.get(t) or {}).get("Expiry"),
            "Level %ile": level.get(t), "Rating": series[-1],
            "Δ Rating": delta, "Recent Δ": recent, "Prior Δ": prior, "trend": series})
    growth = pd.DataFrame(rows)

    if growth.empty:
        st.info("No rating series for the squad yet.")
    else:
        growth = growth.sort_values("Δ Rating", ascending=False).reset_index(drop=True)
        has_wage = "Wage" in growth and growth["Wage"].notna().any()
        if has_wage:                       # squad-relative wage percentile (immersion-safe)
            growth["Wage %ile"] = growth["Wage"].rank(pct=True) * 100

        # ---- who's improving the most ----
        st.subheader("Who's improving the most")
        st.caption(f"Change in **{method}** weighted rating from first → latest snapshot "
                   f"({snaps[0][0]} {snaps[0][1]} → {ls} {lp}), coloured by age band. "
                   "Note: loan status doesn't parse reliably for this Denmark save, so a flat ~0 "
                   "gain *may* just be a player away on loan whose attributes didn't refresh — "
                   "cross-check against who's actually out.")
        fig = px.bar(growth, x="Player", y="Δ Rating", color="Band",
                     category_orders={"Band": ["U21", "21-24", "25-28", "29+", "?"]},
                     labels={"Δ Rating": "Rating gain"})
        fig.update_layout(height=330, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis={"categoryorder": "total descending"})
        st.plotly_chart(fig, width="stretch")

        # ---- trajectory table with sparklines ----
        st.subheader("Trajectories")
        cols = (["Player", "Role", "Age", "Value"]
                + (["Wage", "Expiry"] if has_wage else [])
                + ["Level %ile", "Rating", "Δ Rating", "Recent Δ", "trend"])
        st.dataframe(
            growth[cols], hide_index=True, width="stretch", height=430,
            column_config={
                "Age": st.column_config.NumberColumn(width="small"),
                "Value": st.column_config.NumberColumn(format="%d"),
                "Wage": st.column_config.NumberColumn("Wage £/yr", format="£%d",
                    help="decoded from the contract record (≈±2%)"),
                "Expiry": st.column_config.DateColumn("Expiry", format="MMM YYYY"),
                "Level %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0,
                                                              max_value=100),
                "Δ Rating": st.column_config.NumberColumn("Δ Rating", help="rating gained since "
                    "first snapshot"),
                "Recent Δ": st.column_config.NumberColumn("Recent Δ", help="gain in the most "
                    "recent step — compare to Δ Rating to see if growth is slowing"),
                "trend": st.column_config.LineChartColumn("Trajectory", help="weighted rating "
                    "across snapshots")})
        if len(snaps) < 3:
            st.caption("With more snapshots the **Recent Δ** vs earlier gains (and the sparkline "
                       "shape) will show whether a player's improvement is slowing.")

        # ---- contract watch ----
        st.subheader("Contract watch")
        lo, hi = st.slider("Age band to review", 16, 40, (22, 24),
                           help="Widen to pull in older squad players (e.g. a 28-year-old) too.")
        st.caption("Players you're deciding whether to keep (hope they grow) or move on. Sorted by "
                   "rating gain — low/zero gainers are the axe candidates, most so when they're on a "
                   "high **Wage** and not in your XI. **Expiry** shows whether the decision is even "
                   "yours yet (a deal running down walks for free). Growth + Level %ile + age + wage "
                   "are the signals; loan status still isn't reliable here.")
        cw = growth[growth["Age"].between(lo, hi)].sort_values("Δ Rating")
        if cw.empty:
            st.caption(f"No {lo}-{hi} year-olds in the squad snapshot.")
        else:
            cwcols = (["Player", "Role", "Age", "Value"]
                      + (["Wage", "Wage %ile", "Expiry"] if has_wage else [])
                      + ["Level %ile", "Δ Rating", "trend"])
            st.dataframe(
                cw[cwcols], hide_index=True, width="stretch",
                column_config={
                    "Value": st.column_config.NumberColumn(format="%d"),
                    "Wage": st.column_config.NumberColumn("Wage £/yr", format="£%d"),
                    "Expiry": st.column_config.DateColumn("Expiry", format="MMM YYYY"),
                    "Level %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0,
                                                                  max_value=100),
                    "trend": st.column_config.LineChartColumn("Trajectory")})

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

    rt = db.q("SELECT season, phase, role, rating FROM v_player_ratings "
              "WHERE tid=? AND method=?", [tid, method])
    if rt.empty:
        st.warning("No attribute snapshots for this player.")
        st.stop()
    rt["t"] = rt["season"].astype(str) + " " + rt["phase"]
    rt["ord"] = rt["season"] * 10 + rt["phase"].map(db.PHASE_ORDER)
    rt = rt.sort_values("ord")

    st.subheader("Weighted rating over time")
    roles = db.roles()
    sel_roles = st.multiselect("Roles to plot", roles, default=[primary_role],
                               key=f"roles_{tid}")
    plot = rt[rt["role"].isin(sel_roles)] if sel_roles else rt
    if not plot.empty:
        fig = px.line(plot, x="t", y="rating", color="role", markers=True,
                      labels={"t": "", "rating": "Rating", "role": "Role"})
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Attribute trajectories")
    st.caption(
        f"Grouped; titles colour-coded by {primary_role} importance: "
        f"<span style='color:{db.WEIGHT_COLOR[4]}'>key</span>, "
        f"<span style='color:{db.WEIGHT_COLOR[3]}'>important</span>, "
        f"<span style='color:{db.WEIGHT_COLOR[2]}'>useful</span>.", unsafe_allow_html=True)
    cols = ", ".join(f'"{a}"' for a in db.ATTR_ORDER)
    aw = db.q(f"SELECT season, phase, {cols} FROM staging.player_attributes WHERE tid=?", [tid])
    aw["t"] = aw["season"].astype(str) + " " + aw["phase"]
    aw["ord"] = aw["season"] * 10 + aw["phase"].map(db.PHASE_ORDER)
    aw = aw.sort_values("ord")
    colour_of = {a: db.WEIGHT_COLOR[wmap.get(a.lower(), 1)] for a in db.ATTR_ORDER}

    for group, members in db.ATTR_GROUPS.items():
        if group == "Goalkeeping" and primary_role != "GK":
            continue
        long = aw.melt(id_vars=["t", "ord"], value_vars=members,
                       var_name="attribute", value_name="value").sort_values("ord")
        st.markdown(f"**{group}**")
        fig = px.line(long, x="t", y="value", facet_col="attribute",
                      facet_col_wrap=7, markers=True, height=230)
        fig.update_yaxes(range=[0, 20])
        fig.for_each_annotation(lambda a: a.update(
            text=a.text.split("=")[-1],
            font=dict(color=colour_of.get(a.text.split("=")[-1], "#444444"))))
        fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), showlegend=False)
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, width="stretch")
