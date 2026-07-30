"""Player development — attribute and weighted-rating trajectory across phases/seasons.
Defaults to the player's primary position; attributes grouped Technical/Mental/Physical
with the role-weighted ones highlighted. No CA/PA reveal."""
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

pick = st.selectbox("Player", allsq["label"].tolist())
tid = int(allsq.loc[allsq["label"] == pick, "tid"].iloc[0])

# primary position (max familiarity across labels) → default role + highlight weights
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
