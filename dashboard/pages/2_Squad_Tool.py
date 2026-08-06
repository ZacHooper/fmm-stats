"""Squad tool — rating calculator, scouting shortlist, and player comparison.

Calculator: type a player's attributes + familiarity, pick a position, see where they'd
slot among your squad. Shortlist: save prospects (look them up from the DB or enter
manually), see where each would slot in the squad at the selected position, and compare
the shortlist for that position — all with the role's key attributes alongside the rating.
Compare: grouped radar (Technical/Mental/Physical/GK) role-weighted + colour-coded, for
squad players AND shortlisted prospects (prospects have no match stats).
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


def prospect_rating(attrs, fam):
    """Effective rating for a set of attributes at the current role + a familiarity."""
    base = db.rating_from_attrs(attrs, method, role)
    return base * db.familiarity_multiplier(fam)


eff = db.effective_table(season, phase, method)
sq = db.squad(season, phase)
status = dict(zip(sq["tid"], sq["status"]))
squad = eff[eff["tid"].isin(set(sq["tid"]))].copy()
squad["Player"] = squad.apply(lambda r: db.player_label(r.tid, r["name"]), axis=1)
here = squad[squad["position"] == position].copy()

st.caption(f"Evaluating **{position}** (role: {role}, tactic: {method}).")
st.markdown(importance_caption(), unsafe_allow_html=True)

tab_calc, tab_short, tab_cmp = st.tabs(
    ["🧮 Calculator", "⭐ Shortlist", "🕸️ Compare"])

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

    ca1, ca2 = st.columns(2)
    with ca1.expander("💾 Save this player (JSON)"):
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
    with ca2:
        add_name = st.text_input("Name", key="calc_sl_name",
                                 value=(loaded.get("name", "") if loaded else ""),
                                 placeholder="name to save to shortlist")
        if st.button("⭐ Add to shortlist", key="calc_sl_add"):
            if not add_name.strip():
                st.warning("Give the player a name first.")
            else:
                db.shortlist_add(add_name.strip(), {position: int(fam)},
                                 {a: int(values[a]) for a in db.ATTR_ORDER}, source="manual")
                st.success(f"Added **{add_name.strip()}** to the shortlist.")

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

# --------------------------------------------------------------------- shortlist
with tab_short:
    st.caption("Save prospects and see where they'd slot at the sidebar **position**. "
               "Look a player up to pull their attributes automatically, or add manually.")

    # ---- add by look-up -----------------------------------------------------
    ac1, ac2 = st.columns([3, 2])
    query = ac1.text_input("Look up a player by name", key="sl_query",
                           placeholder="start typing a surname…")
    if query and len(query) >= 2:
        matches = db.player_search(query, season, phase, limit=50)
        if matches.empty:
            ac1.caption("No players match.")
        else:
            opts = {f"{r.name} — {r.club}  (tid {r.tid})": int(r.tid)
                    for r in matches.itertuples()}
            choice = ac1.selectbox("Match", list(opts), key="sl_match",
                                   label_visibility="collapsed")
            if ac2.button("⭐ Add to shortlist", key="sl_add_lookup"):
                tid = opts[choice]
                nm = choice.split(" — ")[0]
                attrs = db.attributes_row(season, phase, tid) or {}
                pos = db.player_positions_map(season, phase, tid)
                db.shortlist_add(nm, pos, attrs, tid=tid, source="lookup")
                st.success(f"Added **{nm}**.")
                st.rerun()

    with st.expander("✍️ Add manually"):
        mname = st.text_input("Name", key="sl_m_name")
        mpos = st.multiselect("Positions they can play", positions,
                              default=[position], key="sl_m_pos")
        mfam = st.number_input("Familiarity at those positions (1–20)", 1, 20, 20,
                               key="sl_m_fam")
        mvals = {}
        for group, members in db.ATTR_GROUPS.items():
            st.markdown(f"**{group}**")
            cols = st.columns(len(members))
            for i, a in enumerate(members):
                mvals[a] = cols[i].number_input(a, 1, 20, 10, key=f"sl_m_{a}")
        if st.button("Add manual player", key="sl_add_manual"):
            if not mname.strip():
                st.warning("Give the player a name.")
            else:
                db.shortlist_add(mname.strip(), {p: int(mfam) for p in mpos},
                                 {a: int(mvals[a]) for a in db.ATTR_ORDER}, source="manual")
                st.success(f"Added **{mname.strip()}**.")
                st.rerun()

    sl = db.shortlist_get()
    st.divider()
    if sl.empty:
        st.info("Shortlist is empty — add players above.")
    else:
        # ---- manage (remove) ------------------------------------------------
        rc1, rc2 = st.columns([3, 1])
        rc1.markdown(f"**{len(sl)} shortlisted** — "
                     + ", ".join(f"{r['name']} "
                                 f"({'/'.join(r['positions'].keys()) or '—'})"
                                 for _, r in sl.iterrows()))
        rm = rc2.selectbox("Remove", ["—"] + sl["name"].tolist(),
                           key="sl_rm", label_visibility="collapsed")
        if rc2.button("🗑 Remove", key="sl_rm_btn") and rm != "—":
            sid = int(sl.loc[sl["name"] == rm, "id"].iloc[0])
            db.shortlist_remove(sid)
            st.rerun()

        # players who can play the sidebar position
        at_pos = sl[sl["positions"].map(lambda p: position in p)]

        # shared inputs for both tables: bio lookups + match aggregates + attribute maps.
        # `key` uniquely identifies each display row (real tid for DB players; a synthetic
        # 's<id>' for manual prospects with no tid) so compose can map attrs/stats per row.
        all_tids = (here["tid"].astype(int).tolist()
                    + [int(r["tid"]) for _, r in at_pos.iterrows() if pd.notna(r["tid"])])
        bio = db.player_bio(season, phase, all_tids)
        elig = db.eligibility_frame(season, phase)
        origin_by = dict(zip(elig["tid"], elig["origin_club"])) if not elig.empty else {}
        prim = db.primary_position_map([t for t in all_tids])
        sq_attrs = db.attributes_rows(season, phase, here["tid"].tolist())
        mrows = db.enrich_match_rows(db.match_stats_rows(db.OUR_CLUBS))
        mrows = mrows[mrows["appeared"]] if not mrows.empty else mrows
        agg = db.aggregate_match_stats(mrows) if not mrows.empty else pd.DataFrame()
        if not agg.empty:
            agg = agg.assign(key=agg["tid"])

        def prospect_row(r):
            """(key, name, fam, rating, attrs, tid_or_None, primary_pos) for a shortlist row."""
            fam = int(r["positions"][position]); at = r["attributes"]
            tid = int(r["tid"]) if pd.notna(r["tid"]) else None
            key = tid if tid is not None else f"s{int(r['id'])}"
            pp = (prim.get(tid) if tid is not None
                  else (max(r["positions"], key=r["positions"].get) if r["positions"] else None))
            return key, r["name"], fam, prospect_rating(at, fam), at, tid, pp

        # ---- picker: full control over identity/bio + attributes + match stats ----
        st.subheader(f"Where they'd slot at {position}")
        ID_A = ["Rank", "Type", "Player", "Pos", "Fam", "Rating", "Age", "Value", "Origin"]
        stats, attrs, ids = stat_table.stat_selector(
            "sl_slot", default_preset=None, extra_options=ID_A,
            default_extra=["Rank", "Type", "Player", "Fam", "Rating"],
            label="Columns (slot-in table)")
        if here.empty and at_pos.empty:
            st.info(f"No squad players or shortlisted prospects list {position}.")
        else:
            rows, attrs_by = [], {}
            for _, r in here.iterrows():
                tid = int(r["tid"]); at = sq_attrs.get(tid, {})
                attrs_by[tid] = at
                rows.append({"key": tid, "Type": "Squad", "Player": r["Player"],
                             "Pos": prim.get(tid), "Fam": int(r["familiarity"]),
                             "eff": r["eff"], "Age": bio.get(tid, {}).get("Age"),
                             "Value": bio.get(tid, {}).get("Value"),
                             "Origin": origin_by.get(tid)})
            for _, r in at_pos.iterrows():
                key, nm, fam, eff_r, at, tid, pp = prospect_row(r)
                attrs_by[key] = at
                rows.append({"key": key, "Type": "⭐ Shortlist", "Player": nm, "Pos": pp,
                             "Fam": fam, "eff": eff_r,
                             "Age": bio.get(tid, {}).get("Age") if tid else None,
                             "Value": bio.get(tid, {}).get("Value") if tid else None,
                             "Origin": origin_by.get(tid) if tid else None})
            base = pd.DataFrame(rows).sort_values("eff", ascending=False).reset_index(drop=True)
            base["Rank"] = base.index + 1
            base["Rating"] = base["eff"].round().astype(int)
            st.dataframe(stat_table.compose(base, ids, stats, attrs, agg, attrs_by),
                         width="stretch", hide_index=True)
            st.caption("Prospects (⭐) ranked in among the current squad at this position. "
                       "Add any attribute or match stat above — match stats are blank for "
                       "prospects (only managed-club matches are parsed). Wage isn't in the save.")

        st.subheader(f"Shortlist at {position}")
        ID_B = ["Player", "Source", "Pos", "Fam", "Rating", "Age", "Value", "Origin"]
        stats2, attrs2, ids2 = stat_table.stat_selector(
            "sl_only", default_preset=None, extra_options=ID_B,
            default_extra=["Player", "Source", "Fam", "Rating"],
            label="Columns (shortlist table)")
        if at_pos.empty:
            st.info(f"No shortlisted players list {position}. "
                    "Pick another position in the sidebar.")
        else:
            rows, attrs_by = [], {}
            for _, r in at_pos.iterrows():
                key, nm, fam, eff_r, at, tid, pp = prospect_row(r)
                attrs_by[key] = at
                rows.append({"key": key, "Player": nm, "Source": r["source"], "Pos": pp,
                             "Fam": fam, "eff": eff_r,
                             "Age": bio.get(tid, {}).get("Age") if tid else None,
                             "Value": bio.get(tid, {}).get("Value") if tid else None,
                             "Origin": origin_by.get(tid) if tid else None})
            base = pd.DataFrame(rows).sort_values("eff", ascending=False).reset_index(drop=True)
            base["Rating"] = base["eff"].round().astype(int)
            st.dataframe(stat_table.compose(base, ids2, stats2, attrs2, agg, attrs_by),
                         width="stretch", hide_index=True)

# --------------------------------------------------------------------- compare
with tab_cmp:
    # candidate pool = squad players + shortlisted prospects (prefixed ⭐)
    sl = db.shortlist_get()
    pool, pool_attrs, pool_pos = {}, {}, {}
    for _, r in squad.drop_duplicates("tid").iterrows():
        pool[r["Player"]] = {"tid": int(r["tid"]), "is_sl": False}
    sq_attr_all = db.attributes_rows(season, phase,
                                     [v["tid"] for v in pool.values()])
    for name, v in list(pool.items()):
        pool_attrs[name] = sq_attr_all.get(v["tid"], {})
    for _, r in sl.iterrows():
        nm = f"⭐ {r['name']}"
        pool[nm] = {"tid": (int(r["tid"]) if pd.notna(r["tid"]) else None), "is_sl": True}
        pool_attrs[nm] = r["attributes"]
        pool_pos[nm] = r["positions"]

    default = here.sort_values("eff", ascending=False)["Player"].head(2).tolist()
    picks = st.multiselect("Players (2–4) — includes ⭐ shortlisted prospects",
                           sorted(pool, key=db.surname_key),
                           default=[p for p in default if p in pool], max_selections=4)
    if not picks:
        st.info("Pick 2–4 players to compare (squad or ⭐ shortlist).")
        st.stop()

    colours = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(picks)}
    st.markdown("&nbsp;&nbsp;".join(
        f"<span style='color:{colours[p]}'>●</span> {p}" for p in picks),
        unsafe_allow_html=True)

    attrs_by = {p: pool_attrs.get(p, {}) for p in picks}
    # primary position per pick: squad from DB, prospects from their listed positions
    sl_tids = [pool[p]["tid"] for p in picks if not pool[p]["is_sl"] and pool[p]["tid"]]
    prim_db = db.primary_position_map(sl_tids)
    prim = {}
    for p in picks:
        if pool[p]["is_sl"]:
            pp = pool_pos.get(p, {})
            prim[p] = max(pp, key=pp.get) if pp else None
        else:
            prim[p] = prim_db.get(pool[p]["tid"])
    keepers = [p for p in picks if prim.get(p) == "GK"]
    squad_picks = [p for p in picks if not pool[p]["is_sl"]]
    if any(pool[p]["is_sl"] for p in picks):
        st.caption("⭐ Shortlisted prospects have attributes only — no match stats.")

    # ---- radars: Attributes (0–20) or Match output (squad only) ----
    view = st.segmented_control("Radar view", ["Attributes", "Match output"],
                                default="Attributes", key="cmp_radar_view")

    def radar(title, theta, series, rng, hover):
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
        match_ready = False
    else:
        match_ready = True

    # match rows for squad picks only (prospects have none)
    pick_tid = {p: pool[p]["tid"] for p in squad_picks}
    mrows = db.enrich_match_rows(db.match_stats_rows(db.OUR_CLUBS))
    mrows = mrows[mrows["appeared"]] if not mrows.empty else mrows
    if match_ready:
        fc1, fc2, fc3 = st.columns(3)
        if mrows.empty or not squad_picks:
            f_all = mrows.iloc[0:0] if not mrows.empty else mrows
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
    else:
        f_all = mrows.iloc[0:0] if not mrows.empty else mrows

    agg_all = db.aggregate_match_stats(f_all) if not f_all.empty else pd.DataFrame()
    pick_agg = (agg_all[agg_all["tid"].isin(pick_tid.values())].copy()
                if not agg_all.empty else pd.DataFrame())

    if match_ready:
        if not squad_picks:
            st.info("Match output is only available for squad players; none selected.")
        elif agg_all.empty:
            st.info("No match appearances for this filter (only managed-club matches "
                    "are richly parsed).")
        else:
            st.caption("Each axis scaled 0–100 against the squad's best under the current "
                       "filter — hover for the real value. Squad players only.")
            radars = {} if set(squad_picks) == set(keepers) else dict(db.OUTPUT_RADARS)
            if any(prim.get(p) == "GK" for p in squad_picks):
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
                for p in squad_picks:
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

    # ---- rating & standing at the sidebar position ----
    st.subheader(f"Rating & standing at {position}")
    rows = []
    for p in picks:
        if pool[p]["is_sl"]:
            pp = pool_pos.get(p, {})
            if position not in pp:
                continue
            fam = int(pp[position])
            rows.append({"Player": p, "Fam": fam,
                         "Rating": int(round(prospect_rating(attrs_by[p], fam))),
                         "Fit %ile": None, "Level %ile": None, "Nation %ile": None})
        else:
            r = squad[(squad["Player"] == p) & (squad["position"] == position)]
            if r.empty:
                continue
            r = r.iloc[0]
            rows.append({"Player": p, "Fam": int(r["familiarity"]),
                         "Rating": int(round(r["eff"])),
                         "Fit %ile": r.get("pctile_league"),
                         "Level %ile": r.get("level_league"),
                         "Nation %ile": r.get("pctile_nation")})
    if not rows:
        st.info(f"None of the selected players list {position}.")
    else:
        out = pd.DataFrame(rows).sort_values("Rating", ascending=False)
        st.dataframe(out, width="stretch", hide_index=True, column_config={
            "Fit %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Level %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Nation %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100)})

    # ---- configurable match-stat + attribute table (squad picks) ----
    st.subheader("Match stats & attributes")
    stats, attrs = stat_table.stat_selector("cmp", default_preset="Custom")
    attrs_by_tid = {pool[p]["tid"]: attrs_by[p] for p in squad_picks}
    if pick_agg.empty:
        st.caption("No match appearances for the selected squad players under this filter — "
                   "showing attributes only. (Prospects never have match stats.)")
        base = pd.DataFrame({"tid": [pool[p]["tid"] for p in squad_picks],
                             "Player": squad_picks})
        base["Pos"] = base["tid"].map(prim_db)
    else:
        pa = pick_agg.sort_values("Rating", ascending=False)
        base = pa.rename(columns={"player": "Player", "pos": "Pos"})[
            ["tid", "Player", "Pos", "Apps", "Starts", "Sub", "Min", "Rating"]].copy()
    if base.empty:
        st.caption("Select at least one squad player to see the match-stat table.")
    else:
        tbl = stat_table.attach_columns(base, stats, attrs, pick_agg, attrs_by_tid, after="Pos")
        st.dataframe(tbl, width="stretch", hide_index=True)
    st.caption("Apps exclude unused subs. Per 90 = ×90 ÷ minutes; per game = ÷ appearances. "
               "Conversion % = goals ÷ shots; DefActions = tackles won + interceptions + "
               "headers won. Filters above scope every figure and the output radars.")
