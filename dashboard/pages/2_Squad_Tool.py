"""Squad tool — rating calculator + squad comparison on one page.

Calculator: type a player's attributes (tab-friendly number inputs) and a familiarity,
pick a position, and see where they'd slot among your squad at that position.
Compare: grouped radar (Technical/Mental/Physical/GK) with role-weighted attributes
colour-coded by importance, plus a rating/rank table.
"""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import stat_table

st.set_page_config(page_title="Squad tool", page_icon="🧮", layout="wide")
st.title("🧮 Squad tool")

PALETTE = ["#1f77b4", "#e45756", "#2ca02c", "#9467bd"]

season, phase = db.select_label()
method = db.select_method()
posmap = db.pos_role_map()
positions = sorted(posmap)
position = st.sidebar.selectbox("Position", positions,
                                index=positions.index("ST") if "ST" in positions else 0)
role = posmap[position]
wmap = db.role_weight_map(method, role)          # {attr_lower: weight}


def importance_caption():
    """Coloured legend of which attributes matter for this role."""
    buckets = {4: [], 3: [], 2: []}
    for a in db.ATTR_ORDER:
        w = wmap.get(a.lower(), 1)
        if w in buckets:
            buckets[w].append(a)
    parts = []
    for w in (4, 3, 2):
        if buckets[w]:
            c = db.WEIGHT_COLOR[w]
            parts.append(f"<span style='color:{c}'><b>{db.WEIGHT_NAME[w]}</b>: "
                         f"{', '.join(buckets[w])}</span>")
    return " &nbsp;·&nbsp; ".join(parts) or "no weighted attributes"


eff = db.effective_table(season, phase, method)
sq = db.squad(season, phase)
status = dict(zip(sq["tid"], sq["status"]))
squad = eff[eff["tid"].isin(set(sq["tid"]))].copy()
squad["Player"] = squad.apply(lambda r: db.player_label(r.tid, r["name"]), axis=1)
here = squad[squad["position"] == position].copy()

st.caption(f"Evaluating **{position}** (role: {role}, tactic: {method}).")
st.markdown(importance_caption(), unsafe_allow_html=True)

tab_calc, tab_cmp = st.tabs(["🧮 Calculator", "🕸️ Compare squad"])

# --------------------------------------------------------------------- calculator
def _saved_custom_players():
    path = _os.path.join(db.REPO, "seeds", "custom_players.json")
    if _os.path.exists(path):
        try:
            data = json.load(open(path))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def _clear_calc_inputs():
    for k in [k for k in st.session_state if k.startswith("attrin_")]:
        del st.session_state[k]


with tab_calc:
    with st.expander("💾 Save / load a custom player"):
        saved = _saved_custom_players()
        names = [p.get("name", "(unnamed)") for p in saved]
        pick = st.selectbox("Load a saved player", ["—"] + names) if saved else "—"
        up = st.file_uploader("…or upload player JSON", type="json", key="calc_up")
        paste = st.text_area("…or paste player JSON", key="calc_paste", height=110)
        if st.button("Load player"):
            try:
                if paste.strip():
                    blob = json.loads(paste)
                elif up is not None:
                    blob = json.loads(up.getvalue().decode("utf-8"))
                elif pick != "—":
                    blob = next(p for p in saved if p.get("name") == pick)
                else:
                    raise ValueError("nothing to load")
                st.session_state["calc_loaded"] = blob
                _clear_calc_inputs()
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't load: {e}")
        if st.session_state.get("calc_loaded"):
            lp = st.session_state["calc_loaded"]
            st.caption(f"Loaded **{lp.get('name', '(unnamed)')}** "
                       f"(saved at {lp.get('position', '?')}). Rating recomputes for the "
                       f"position selected in the sidebar.")
            if st.button("Clear loaded player"):
                del st.session_state["calc_loaded"]
                _clear_calc_inputs()
                st.rerun()

    loaded = st.session_state.get("calc_loaded")
    allsq = db.squad(season, phase)
    prefill = st.selectbox("Pre-fill from squad player (optional)",
                           ["— blank —"] + allsq["label"].tolist(),
                           disabled=bool(loaded),
                           help="Disabled while a saved player is loaded — clear it first.")
    base_vals = {a: 10 for a in db.ATTR_ORDER}
    fam_default = 20
    if loaded:
        base_vals = {a: int(loaded.get("attributes", {}).get(a, 10)) for a in db.ATTR_ORDER}
        fam_default = int(loaded.get("familiarity", 20))
    elif prefill != "— blank —":
        tid = int(allsq.loc[allsq["label"] == prefill, "tid"].iloc[0])
        base_vals = db.attributes_row(season, phase, tid) or base_vals
        r = here[here["tid"] == tid]
        if not r.empty:
            fam_default = int(r.iloc[0]["familiarity"])

    fam = st.number_input("Familiarity at this position (1–20)", 1, 20, fam_default)
    values = {}
    for group, members in db.ATTR_GROUPS.items():
        if group == "Goalkeeping" and position != "GK":
            continue
        st.markdown(f"**{group}**")
        cols = st.columns(len(members))
        for i, a in enumerate(members):
            values[a] = cols[i].number_input(a, 1, 20, int(base_vals.get(a, 10)),
                                             key=f"attrin_{position}_{prefill}_{a}")
    for a in db.ATTR_ORDER:
        values.setdefault(a, int(base_vals.get(a, 10)))

    base_rating = db.rating_from_attrs(values, method, role)
    mult = db.familiarity_multiplier(fam)
    eff_rating = base_rating * mult

    m1, m2, m3 = st.columns(3)
    m1.metric("Base rating", int(round(base_rating)))
    m2.metric("Familiarity ×", f"{mult:.2f}")
    m3.metric("Effective rating", int(round(eff_rating)))

    with st.expander("💾 Save this player"):
        pname = st.text_input("Name", value=(loaded.get("name", "") if loaded else ""),
                              key="calc_savename")
        blob = {"version": 1, "name": pname or "Custom player", "position": position,
                "method": method, "familiarity": int(fam),
                "attributes": {a: int(values[a]) for a in db.ATTR_ORDER}}
        js = json.dumps(blob, indent=2)
        st.download_button("Download player JSON", js,
                           f"{(pname or 'player').replace(' ', '_')}.json", "application/json")
        st.code(js, language="json")
        st.caption("Append this object to `seeds/custom_players.json` (a JSON list) to keep it "
                   "available in the build.")

    st.subheader(f"Where they'd slot at {position}")
    board = pd.concat([here[["Player", "eff"]],
                       pd.DataFrame([{"Player": "▶ entered player", "eff": eff_rating}])],
                      ignore_index=True)
    board["Rating"] = board["eff"].round().astype(int)
    board = board.sort_values("eff", ascending=False).reset_index(drop=True)
    board["Rank"] = board.index + 1
    st.dataframe(board[["Rank", "Player", "Rating"]], width="stretch", hide_index=True)
    slot = int(board.loc[board["Player"] == "▶ entered player", "Rank"].iloc[0])
    st.success(f"This player would be your **#{slot} of {len(board)}** at {position}.")

# --------------------------------------------------------------------- compare
with tab_cmp:
    picks = st.multiselect("Players (2–4)",
                           sorted(squad["Player"].unique().tolist(), key=db.surname_key),
                           default=here.sort_values("eff", ascending=False)["Player"]
                           .head(2).tolist(), max_selections=4)
    if not picks:
        st.info("Pick 2–4 players to compare.")
        st.stop()

    colours = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(picks)}
    pick_tid = {p: int(squad.loc[squad["Player"] == p, "tid"].iloc[0]) for p in picks}
    st.markdown("&nbsp;&nbsp;".join(
        f"<span style='color:{colours[p]}'>●</span> {p}" for p in picks),
        unsafe_allow_html=True)

    # match rows for the whole squad (baseline for output-radar scaling) + filters
    mrows = db.enrich_match_rows(db.match_stats_rows(db.OUR_CLUBS))
    mrows = mrows[mrows["appeared"]] if not mrows.empty else mrows
    fc1, fc2, fc3 = st.columns(3)
    if mrows.empty:
        f_all = mrows
    else:
        m_seasons = fc1.multiselect("Seasons", sorted(mrows["season"].unique()),
                                    default=sorted(mrows["season"].unique()),
                                    key="cmp_seasons")
        m_comps = fc2.multiselect("Competitions",
                                  sorted(mrows["competition"].dropna().unique()),
                                  key="cmp_comps")
        m_opps = fc3.multiselect("Opponents", sorted(mrows["opponent"].unique()),
                                 key="cmp_opps")
        f_all = mrows[mrows["season"].isin(m_seasons or mrows["season"].unique())]
        if m_comps:
            f_all = f_all[f_all["competition"].isin(m_comps)]
        if m_opps:
            f_all = f_all[f_all["opponent"].isin(m_opps)]

    agg_all = db.aggregate_match_stats(f_all) if not f_all.empty else pd.DataFrame()
    pick_agg = (agg_all[agg_all["tid"].isin(pick_tid.values())].copy()
                if not agg_all.empty else pd.DataFrame())
    attrs_by_tid = db.attributes_rows(season, phase, list(pick_tid.values()))
    attrs_by = {p: attrs_by_tid.get(pick_tid[p], {}) for p in picks}
    prim = db.primary_position_map(list(pick_tid.values()))
    keepers = [p for p in picks if prim.get(pick_tid[p]) == "GK"]

    # ---- radars: Attributes (0–20) or Match output (0–100, scaled vs squad) ----
    view = st.segmented_control("Radar view", ["Attributes", "Match output"],
                                default="Attributes", key="cmp_radar_view")

    def radar(title, theta, series, rng, hover):
        """series: {player: (r_vals, raw_vals)}; closes the polygon; plain layout."""
        fig = go.Figure()
        for p, (rv, raw) in series.items():
            fig.add_trace(go.Scatterpolar(
                r=list(rv) + [rv[0]], theta=list(theta) + [theta[0]], fill="toself",
                name=p, line_color=colours[p],
                customdata=list(raw) + [raw[0]], hovertemplate=hover))
        fig.update_layout(title=title, height=340, showlegend=False,
                          polar=dict(radialaxis=dict(range=rng)),
                          margin=dict(l=40, r=40, t=40, b=30))
        return fig

    if view == "Attributes":
        st.caption("Axis labels colour-coded by role importance: "
                   f"<span style='color:{db.WEIGHT_COLOR[4]}'>key</span>, "
                   f"<span style='color:{db.WEIGHT_COLOR[3]}'>important</span>, "
                   f"<span style='color:{db.WEIGHT_COLOR[2]}'>useful</span>. "
                   "Values are the raw 1–20 attributes.", unsafe_allow_html=True)
        groups = ["Technical", "Mental", "Physical"] + (["Goalkeeping"] if keepers else [])
        gcols = st.columns(len(groups))
        for gi, group in enumerate(groups):
            members = db.ATTR_GROUPS[group]
            theta = [db.color_label(a, wmap) for a in members]
            series = {p: ([attrs_by[p].get(a, 0) for a in members],
                          [attrs_by[p].get(a, 0) for a in members]) for p in picks}
            gcols[gi].plotly_chart(
                radar(group, theta, series, [0, 20],
                      "%{theta}: %{customdata}<extra>%{fullData.name}</extra>"),
                width="stretch")
    else:
        if agg_all.empty:
            st.info("No match appearances for this filter (only managed-club matches "
                    "are richly parsed).")
        else:
            st.caption("Each axis scaled 0–100 against the squad's best under the current "
                       "filter, so the shape shows relative output — hover for the real "
                       "value. Match stats exist only for your club's matches.")
            radars = {} if set(picks) == set(keepers) else dict(db.OUTPUT_RADARS)
            if keepers:
                radars["Goalkeeper"] = db.GK_OUTPUT_RADAR
            gcols = st.columns(len(radars))
            by_tid = {int(r["tid"]): r for _, r in pick_agg.iterrows()}
            for gi, (title, axes) in enumerate(radars.items()):
                maxes = {}
                for name in axes:
                    col = db.MATCH_STAT_DEFS[name]
                    m = agg_all[col].max(skipna=True)
                    maxes[name] = m if (pd.notna(m) and m > 0) else 1.0
                series = {}
                for p in picks:
                    row = by_tid.get(pick_tid[p])
                    raw = [0 if row is None or pd.isna(row[db.MATCH_STAT_DEFS[n]])
                           else round(float(row[db.MATCH_STAT_DEFS[n]]), 2) for n in axes]
                    rv = [round(100 * v / maxes[n], 1) for v, n in zip(raw, axes)]
                    series[p] = (rv, raw)
                gcols[gi].plotly_chart(
                    radar(title, axes, series, [0, 100],
                          "%{theta}: %{customdata} (%{r:.0f}%)"
                          "<extra>%{fullData.name}</extra>"),
                    width="stretch")

    # ---- rating & standing at the sidebar position (attribute-rating based) ----
    st.subheader(f"Rating & standing at {position}")
    sel = squad[squad["Player"].isin(picks) & (squad["position"] == position)].copy()
    if sel.empty:
        st.info(f"None of the selected players list {position} among their positions.")
    else:
        sel["Rating"] = sel["eff"].round().astype(int)
        sel["Squad rank"] = sel["eff"].rank(ascending=False, method="min").astype(int)
        out = sel[["Player", "familiarity", "Rating", "Squad rank",
                   "pctile_league", "pctile_nation"]].rename(columns={
            "familiarity": "Fam", "pctile_league": "League %ile",
            "pctile_nation": "Nation %ile"}).sort_values("Rating", ascending=False)
        st.dataframe(out, width="stretch", hide_index=True, column_config={
            "League %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Nation %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100)})

    # ---- configurable match-stat + attribute table (shared component) ----
    st.subheader("Match stats")
    stats, attrs = stat_table.stat_selector("cmp", default_preset="Custom")

    if pick_agg.empty:
        st.caption("No match appearances for these players under this filter — showing "
                   "attributes only.")
        base = pd.DataFrame({"tid": [pick_tid[p] for p in picks], "Player": picks})
        base["Pos"] = base["tid"].map(prim)
    else:
        pa = pick_agg.sort_values("Rating", ascending=False)
        base = pa.rename(columns={"player": "Player", "pos": "Pos"})[
            ["tid", "Player", "Pos", "Apps", "Starts", "Sub", "Min", "Rating"]].copy()
    tbl = stat_table.attach_columns(base, stats, attrs, pick_agg, attrs_by_tid, after="Pos")
    st.dataframe(tbl, width="stretch", hide_index=True)
    st.caption("Apps exclude unused subs. Per 90 = ×90 ÷ minutes; per game = ÷ appearances. "
               "Conversion % = goals ÷ shots; DefActions = tackles won + interceptions + "
               "headers won. Filters above scope every figure and the output radars.")
