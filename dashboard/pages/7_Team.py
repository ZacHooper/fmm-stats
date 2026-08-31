"""Team analysis — how our squad stacks up against the league, and 1-to-1 scouting.

Filter by unit (GK/Defense/Midfield/Attack) and/or specific positions. The scout tab lets
you pick a DIFFERENT subset for each side — e.g. our strikers' Pace vs their defenders' —
so you can probe specific matchups rather than only whole-squad averages."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Team", page_icon="🏟️", layout="wide")
st.title("🏟️ Team analysis")

season, phase = db.select_label()
method = db.select_method()
US = db.MANAGED_CLUB_TID
GROUPS = [g for g in db.ATTR_GROUPS if g != "Goalkeeping"]   # GK covered by GK unit
PALETTE = {"us": "#1f77b4", "them": "#e45756"}

lg = db.leagues_list(season, phase)
lg_names = dict(zip(lg["cid"], lg["name"]))
lg_opts = lg["cid"].tolist()
mine = db.my_league(season, phase)
league_cid = st.sidebar.selectbox("League", lg_opts,
                                  index=lg_opts.index(mine) if mine in lg_opts else 0,
                                  format_func=lambda c: f"{lg_names.get(c) or c}")

if not lg_opts:
    st.info("No league data for this snapshot yet — e.g. a **day-1 save** before any "
            "matches are simulated, so club→league membership hasn't been established. "
            "Your squad's attributes and ratings are on the other pages (Squad Tool, "
            "Player Stats); the vs-league and scouting views here populate once results exist.")
    st.stop()

teams = db.teams_in_league(season, phase, league_cid)
team_tids = [int(t) for t in teams["tid"]]
tname = dict(zip(teams["tid"], teams["name"]))


@st.cache_data(show_spinner=False)
def base_frame(season, phase, method, team_tids, ver):
    """Per-player: club_tid, tid, position, unit, eff, pos_index (cross-position normalised),
    pctile_league + 23 attributes (unfiltered)."""
    return db.squad_frame(season, phase, method, list(team_tids))


base = base_frame(season, phase, method, tuple(sorted(team_tids)), db._dbver())
if base.empty or US not in set(base["club_tid"]):
    st.info("No rated players for your club in this league.")
    st.stop()

ALL_POS = sorted(base["position"].dropna().unique())


def subset_filter(label, key, container=st):
    """Unit + position multiselects, stacked (no inner columns, so it stays responsive
    even when placed inside a column). Returns ((units, positions), human_label)."""
    units = container.multiselect(f"{label} — units", db.UNIT_ORDER, key=f"{key}_u")
    positions = container.multiselect(f"{label} — positions", ALL_POS, key=f"{key}_p",
                                      help="Specific positions (e.g. DC only). Overrides "
                                           "units when both set — refines to these positions.")
    parts = positions or units
    return (units, positions), (", ".join(parts) if parts else "All")


def apply_subset(frame, units, positions):
    f = frame
    if units:
        f = f[f["unit"].isin(units)]
    if positions:
        f = f[f["position"].isin(positions)]
    return f


def group_means(f):
    """(group-means-by-club, per-attribute-means-by-club) for a filtered frame. 'Overall'
    is the mean position-index (cross-position fair), NOT raw eff, so mixed-position subsets
    aren't skewed by which roles score higher on the weighting scale."""
    f = f.copy()
    for g, members in db.ATTR_GROUPS.items():
        f[g] = f[members].mean(axis=1)
    grp = f.groupby("club_tid")[list(db.ATTR_GROUPS)].mean()
    overall = f.groupby("club_tid")["pos_index"].mean().rename("Overall")
    attr = f.groupby("club_tid")[db.ATTR_ORDER].mean()
    return grp.join(overall), attr


with st.expander("💡 How to use this for tactics", expanded=False):
    st.markdown(
        "- **Overall shape:** where your squad beats / trails the league tells you which "
        "phase to lean on. Strong **Dribbling + Pace** but weak **Passing** → carry the ball "
        "and run at defenders rather than build through possession.\n"
        "- **Per unit:** filter to *Attack* / *Midfield* / *Defense* to see which line is your "
        "edge or your liability — set team mentality and where to take risks accordingly.\n"
        "- **Per match (scout tab):** compare **your attackers vs their defenders** — if your "
        "Pace clears their Pace, play in behind; if you win Aerial, target crosses; if they're "
        "quick but weak in the air, keep it low. Do the reverse for **your defenders vs their "
        "attackers** to spot what to protect against.")

tab_league, tab_scout = st.tabs(["📊 Vs league", "🔎 Scout a team"])


def summary_table(cols, index):
    rows = []
    for mcol in cols:
        if mcol not in index.columns:
            continue
        s = index[mcol].dropna()
        if US not in s.index:
            continue
        rows.append({"Metric": "Overall (index)" if mcol == "Overall" else mcol,
                     "Ours": round(s[US], 1), "League avg": round(s.mean(), 1),
                     "Rank": f"{int((s > s[US]).sum() + 1)} / {len(s)}",
                     "%ile": round(100 * (s < s[US]).mean(), 0)})
    return pd.DataFrame(rows)


def box_with_ours(long, ours_row, title):
    fig = px.box(long, x="attribute", y="value", points=False, height=380)
    fig.add_trace(go.Scatter(
        x=ours_row.index, y=ours_row.values, mode="markers", name="Us",
        marker=dict(color=PALETTE["them"], size=11, symbol="diamond")))
    fig.update_layout(title=title, showlegend=True, margin=dict(l=0, r=0, t=40, b=0),
                      xaxis_title="")
    return fig


with tab_league:
    # ---- headline: our best-XI strength vs the league (cross-position normalised) ----
    us_units, us_team = db.team_strength(base, US)
    if us_team["index"] is not None:
        st.markdown("#### Our strength vs the league")
        by_unit = {r["unit"]: r for _, r in us_units.iterrows()}
        m = st.columns(5)
        m[0].metric("Team index", f"{us_team['index']:.0f}",
                    help="Best XI, position-normalised. 100 = league-average player per position.")
        m[1].metric("League %ile", f"{us_team['pctile']:.0f}")
        for i, unit in enumerate(["Defense", "Midfield", "Attack"]):
            r = by_unit.get(unit)
            if r is not None and pd.notna(r["index"]):
                m[i + 2].metric(unit, f"{r['index']:.0f}",
                                help=f"{r['pctile']:.0f}th %ile in the league")
        disp = us_units.rename(columns={"unit": "Unit", "index": "Index", "pctile": "League %ile"})
        disp = pd.concat([disp[["Unit", "Index", "League %ile"]],
                          pd.DataFrame([{"Unit": "TEAM", "Index": us_team["index"],
                                         "League %ile": us_team["pctile"]}])], ignore_index=True)
        st.dataframe(disp, hide_index=True, width="stretch", column_config={
            "League %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0,
                                                           max_value=100)})
        st.caption("Best XI (GK + 4 def + 3 mid + 3 att), each player normalised against his "
                   "position so a centre-back and a striker compare fairly. Index 100 = a "
                   "league-average player for the position; %ile = our rank in the league.")

        with st.expander("⭐ Our standout players — by position index, with top attributes"):
            kp = db.squad_key_players(base, US, method)
            if kp.empty:
                st.caption("No rated players.")
            else:
                names = dict(db.q("SELECT tid, any_value(name) FROM staging.players "
                                  "WHERE season=? AND phase=? AND club_tid=? GROUP BY tid",
                                  [season, phase, US]).itertuples(index=False, name=None))
                show = kp.head(14).copy()
                show["Player"] = show["tid"].map(names).fillna("—")
                show = show.rename(columns={"position": "Pos", "pos_index": "Index",
                                            "pctile_league": "Fit %ile",
                                            "level_league": "Level %ile",
                                            "top_attrs": "Top attributes"})
                show["Index"] = show["Index"].round(0)
                cols = ["Player", "Pos", "Index", "Fit %ile"]
                if "Level %ile" in show.columns:
                    cols.append("Level %ile")
                cols.append("Top attributes")
                st.dataframe(show[cols],
                             hide_index=True, width="stretch", column_config={
                                 "Fit %ile": st.column_config.ProgressColumn(
                                     format="%.0f", min_value=0, max_value=100),
                                 "Level %ile": st.column_config.ProgressColumn(
                                     format="%.0f", min_value=0, max_value=100),
                                 "Top attributes": st.column_config.TextColumn(width="large")})
    st.divider()
    st.markdown("#### Drill into attributes")

    (u, p), lbl = subset_filter("Filter", "lg", st)
    f = apply_subset(base, u, p)
    grp, attr = group_means(f)
    n_ours = int((f["club_tid"] == US).sum())
    st.caption(f"League: **{lg_names.get(league_cid)}** · {f['club_tid'].nunique()} clubs "
               f"with players in **{lbl}** · your matching players: {n_ours}")
    if US not in grp.index:
        st.info(f"None of your players fall in **{lbl}**.")
    else:
        metric_cols = GROUPS + ["Overall"]
        st.dataframe(summary_table(metric_cols, grp), width="stretch", hide_index=True,
                     column_config={"%ile": st.column_config.ProgressColumn(
                         format="%.0f", min_value=0, max_value=100)})
        st.caption("Rank/%ile compare your club's average against the other clubs' averages "
                   "for the same subset (so 'Defense' vs everyone's defenders).")

        st.markdown("**Per-attribute detail** — league spread (box) with our club marked.")
        grp_pick = st.selectbox("Attribute group", GROUPS + ["Goalkeeping"])
        members = db.ATTR_GROUPS[grp_pick]
        long = attr[members].reset_index().melt("club_tid", var_name="attribute", value_name="value")
        st.plotly_chart(box_with_ours(long, attr.loc[US, members], grp_pick), width="stretch")


def side_means(f):
    """{group/Overall: mean}, {attr: mean}, n — or (None, None, 0) if empty."""
    if f.empty:
        return None, None, 0
    f = f.copy()
    for g, members in db.ATTR_GROUPS.items():
        f[g] = f[members].mean(axis=1)
    g = {k: round(f[k].mean(), 1) for k in list(db.ATTR_GROUPS)}
    g["Overall"] = round(f["eff"].mean(), 1)
    a = {c: round(f[c].mean(), 1) for c in db.ATTR_ORDER}
    return g, a, len(f)


with tab_scout:
    others = [t for t in team_tids if t != US]
    if not others:
        st.info("No other clubs in this league.")
        st.stop()
    opp = st.selectbox("Scout club", others, format_func=lambda t: tname.get(t) or f"#{int(t)}")

    # ---- at-a-glance report (shared core; same data the `fmq scout` CLI prints) ----
    rep = db.scout_report(int(opp), season, phase, method)
    cov = rep["coverage"]
    if cov["partial"]:
        st.warning(f"⚠️ Partial squad data — only {cov['in_frame']} of their players are rated "
                   f"({cov['n_with_attr']}/{cov['n_players']} have attributes). Treat the reads "
                   "below as directional; lean on the head-to-head + your in-game scout.")
    ov = rep["overall"]
    if pd.notna(ov["us"]) and pd.notna(ov["them"]):
        c = st.columns(2)
        c[0].metric("Our team index", f"{ov['us']:.0f}",
                    delta=f"{ov['us'] - ov['them']:+.0f} vs them",
                    help="Best XI, position-normalised. 100 = league-average player per position.")
        c[1].metric(f"{tname.get(opp, 'Their')} index", f"{ov['them']:.0f}")
    with st.expander("🧠 Auto-read", expanded=True):
        for fl in rep["flags"]:
            st.markdown(f"- {fl}")

    strength = rep["strength"]
    if not strength.empty:
        st.markdown("**Team & unit strength** — best XI, cross-position normalised")
        sdf = strength.rename(columns={"unit": "Unit", "us": "Us", "them": "Them",
                                       "edge": "Edge", "us_pctile": "Us %ile",
                                       "them_pctile": "Them %ile"})
        st.dataframe(sdf[["Unit", "Us", "Them", "Edge", "Us %ile", "Them %ile"]],
                     hide_index=True, width="stretch", column_config={
                         "Edge": st.column_config.NumberColumn(help="Us − them index (+ = ours)"),
                         "Us %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0,
                                                                    max_value=100),
                         "Them %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0,
                                                                      max_value=100)})
        st.caption("Index/%ile are rated under OUR tactic's role weights — how well each line "
                   "would fit our system. Fair for judging our own squad; an opponent doesn't "
                   "run our tactic, so use the face-off table below for them.")

    matchups = rep.get("matchups")
    if matchups is not None and not matchups.empty:
        st.markdown("**Face-off matchups** — who actually plays whom, by Level %ile "
                    "(tactic-agnostic quality, not Fit under our tactic)")
        mdf = matchups.rename(columns={"matchup": "Matchup", "us_quality": "Us",
                                       "them_quality": "Them", "edge": "Edge"})
        st.dataframe(mdf[["Matchup", "Us", "Them", "Edge"]], hide_index=True, width="stretch",
                     column_config={"Us": st.column_config.ProgressColumn(format="%.0f",
                                                                          min_value=0, max_value=100),
                                    "Them": st.column_config.ProgressColumn(format="%.0f",
                                                                            min_value=0, max_value=100),
                                    "Edge": st.column_config.NumberColumn(
                                        help="Us − them Level %ile (+ = our side of the "
                                             "matchup is the stronger unit)")})
        st.caption("A back line never plays a back line — this pairs our attack against "
                   "their defense, their attack against our defense, and midfield against "
                   "midfield.")

    st.markdown("**Their key players** — by position index, with each player's top attributes")
    kp = rep["key_players"]
    if kp.empty:
        st.caption("No rated players in our data for this club.")
    else:
        show = kp.head(12).rename(columns={"position": "Pos", "pos_index": "Index",
                                           "pctile_league": "Fit %ile",
                                           "level_league": "Level %ile",
                                           "top_attrs": "Top attributes"})
        show["Index"] = show["Index"].round(0)
        cols = ["Pos", "Index", "Fit %ile"]
        if "Level %ile" in show.columns:
            cols.append("Level %ile")
        cols.append("Top attributes")
        st.dataframe(show[cols], hide_index=True,
                     width="stretch", column_config={
                         "Fit %ile": st.column_config.ProgressColumn(
                             format="%.0f", min_value=0, max_value=100),
                         "Level %ile": st.column_config.ProgressColumn(
                             format="%.0f", min_value=0, max_value=100),
                         "Top attributes": st.column_config.TextColumn(width="large")})
        st.caption("Names aren't in the save — players shown by position; ranked so a top-%ile "
                   "full-back isn't buried under mid-tier midfielders, with their standout "
                   "attributes on the same row.")
    st.divider()
    st.caption("**Probe a specific matchup below** — e.g. our Attack vs their Defence.")

    with st.container(border=True):
        (ou, op), ol = subset_filter("Our players", "sc_us")
    with st.container(border=True):
        (tu, tp), tl = subset_filter("Their players", "sc_them")
    our_f = apply_subset(base[base["club_tid"] == US], ou, op)
    their_f = apply_subset(base[base["club_tid"] == opp], tu, tp)
    ug, ua, un = side_means(our_f)
    tg, ta, tn = side_means(their_f)
    us_col, them_col = f"Us · {ol} ({un})", f"{tname.get(opp,'Them')} · {tl} ({tn})"

    if ug is None or tg is None:
        st.info("One side has no players in the chosen subset — widen the filter.")
    else:
        st.caption(f"Comparing **your {ol}** ({un} players) vs **their {tl}** ({tn} players). "
                   "Pick different subsets per side to probe a matchup.")
        metric_cols = GROUPS + ["Overall"]
        comp = pd.DataFrame({"Metric": metric_cols,
                             us_col: [ug[m] for m in metric_cols],
                             them_col: [tg[m] for m in metric_cols]})
        comp["Edge"] = (comp[us_col] - comp[them_col]).round(1)
        st.dataframe(comp, width="stretch", hide_index=True, column_config={
            "Edge": st.column_config.NumberColumn(help="Us minus them (+ = our advantage)")})

        st.markdown("**Per-attribute** — us vs them (1–20).")
        grp_pick = st.selectbox("Attribute group ", GROUPS + ["Goalkeeping"], key="scout_grp")
        members = db.ATTR_GROUPS[grp_pick]
        d = pd.DataFrame({"attribute": members,
                          us_col: [ua[a] for a in members],
                          them_col: [ta[a] for a in members]})
        melt = d.melt("attribute", var_name="Side", value_name="Value")
        fig = px.bar(melt, x="attribute", y="Value", color="Side", barmode="group", height=360,
                     color_discrete_sequence=[PALETTE["us"], PALETTE["them"]])
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis_range=[0, 20],
                          xaxis_title="", legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, width="stretch")

    # ---- head-to-head: our match history vs this club (all seasons) ----
    st.divider()
    st.subheader(f"Our record vs {tname.get(opp, 'them')}")
    hist = db.our_match_history()
    h = (hist[hist["opp_tid"] == opp].sort_values(["season", "date"])
         if not hist.empty else hist)
    if h.empty:
        st.caption("No played matches on record against this club (only managed-club matches "
                   "are parsed).")
    else:
        w, dr, ls = [(h["result"] == r).sum() for r in "WDL"]
        k = st.columns(5)
        k[0].metric("Played", len(h))
        k[1].metric("W–D–L", f"{w}–{dr}–{ls}")
        k[2].metric("Goals for", int(h["gf"].sum()))
        k[3].metric("Goals against", int(h["ga"].sum()))
        k[4].metric("PPG", f"{h['pts'].mean():.2f}")
        pass_pct = lambda c, p: (100 * h[c] / h[p].where(h[p] > 0)).round(0)
        drill = pd.DataFrame({
            "Season": h["season"].values, "Date": h["date"].values, "V": h["venue"].values,
            "GF": h["gf"].astype(int).values, "GA": h["ga"].astype(int).values,
            "Res": h["result"].values, "Comp": h["competition"].values,
            "Shots": h["our_shots"].values, "Shots opp": h["opp_shots"].values,
            "Pass%": pass_pct("our_passes_completed", "our_passes").values,
            "Pass% opp": pass_pct("opp_passes_completed", "opp_passes").values,
            "TklW": h["our_tackles_won"].values, "TklW opp": h["opp_tackles_won"].values,
        })
        st.dataframe(drill, width="stretch", hide_index=True)
        st.caption("Every previous meeting with shot / passing / tackling splits — spot what "
                   "worked and what to shore up for next time.")
