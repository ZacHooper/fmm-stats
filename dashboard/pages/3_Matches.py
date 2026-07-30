"""Match records across ALL seasons — head-to-head, per-competition overalls, team-stat
differentials, and formations. Cumulative snapshots are deduped (latest phase per
season). Opponent formation isn't parsed, so formation analysis is our-shape-only."""
import pandas as pd
import plotly.express as px
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Matches", page_icon="📋", layout="wide")
st.title("📋 Match records")
US = db.MANAGED_CLUB_TID
TS = db.MATCH_TEAM_STATS

all_hist = db.our_match_history()
if all_hist.empty:
    st.info("No matches loaded.")
    st.stop()

seasons = sorted(all_hist["season"].unique())
sel = st.sidebar.multiselect("Seasons", seasons, default=seasons)
if not sel:
    st.stop()
m = all_hist[all_hist["season"].isin(sel)].reset_index(drop=True)
if m.empty:
    st.info("No managed-club matches in the selected seasons.")
    st.stop()

w, d, l = [(m["result"] == r).sum() for r in "WDL"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Seasons", len(sel))
c2.metric("Played", len(m))
c3.metric("W-D-L", f"{w}-{d}-{l}")
c4.metric("PPG", f"{m.pts.mean():.2f}")

t1, t2, t3, t4, t5 = st.tabs(
    ["Head-to-head", "By competition", "Team stats", "Formations", "All results"])


def record_block(df, key):
    g = df.groupby(key).agg(
        P=("result", "size"),
        W=("result", lambda s: (s == "W").sum()),
        D=("result", lambda s: (s == "D").sum()),
        L=("result", lambda s: (s == "L").sum()),
        GF=("gf", "sum"), GA=("ga", "sum"), Pts=("pts", "sum")).reset_index()
    g["PPG"] = (g["Pts"] / g["P"]).round(2)
    g["Record"] = g["W"].astype(str) + "-" + g["D"].astype(str) + "-" + g["L"].astype(str)
    return g


with t1:
    st.caption("Record vs each opponent across the selected seasons — worst PPG first.")
    h2h = record_block(m, "opponent")
    h2h["Seasons"] = m.groupby("opponent")["season"].nunique().values
    st.dataframe(h2h[["opponent", "P", "Record", "GF", "GA", "PPG", "Seasons"]]
                 .sort_values(["PPG", "P"]), width="stretch", hide_index=True)

with t2:
    st.caption("Overall record per competition.")
    comp = record_block(m, "competition")
    st.dataframe(comp[["competition", "P", "Record", "GF", "GA", "Pts", "PPG"]]
                 .sort_values("P", ascending=False), width="stretch", hide_index=True)

with t3:
    st.caption("Our vs opponent team-stat averages per match — pick metrics.")
    labels = {"shots": "Shots", "shots_on_target": "Shots on target", "passes": "Passes",
              "passes_completed": "Passes completed", "tackles": "Tackles",
              "tackles_won": "Tackles won", "crosses": "Crosses",
              "interceptions": "Interceptions"}
    picks = st.multiselect("Metrics", list(labels.values()),
                           default=["Shots", "Shots on target", "Passes", "Tackles won"])
    inv = {v: k for k, v in labels.items()}
    rows = []
    for p in picks:
        k = inv[p]
        rows.append({"Metric": p, "Ours (avg)": round(m[f"our_{k}"].mean(), 1),
                     "Opp (avg)": round(m[f"opp_{k}"].mean(), 1)})
    if rows:
        agg = pd.DataFrame(rows)
        st.dataframe(agg, width="stretch", hide_index=True)
        melt = agg.melt("Metric", var_name="Side", value_name="Avg")
        fig = px.bar(melt, x="Metric", y="Avg", color="Side", barmode="group", height=340,
                     color_discrete_sequence=["#1f77b4", "#e45756"])
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

with t4:
    st.caption("How each of OUR formations performed (opponent shape not available).")
    fm = m.dropna(subset=["formation"])
    if fm.empty:
        st.info("No formation data.")
    else:
        agg = record_block(fm, "formation").sort_values("PPG", ascending=False)
        st.dataframe(agg[["formation", "P", "Record", "GF", "GA", "PPG"]],
                     width="stretch", hide_index=True)

with t5:
    st.dataframe(m[["season", "date", "venue", "opponent", "gf", "ga", "result",
                    "competition", "formation"]].rename(columns={"gf": "GF", "ga": "GA"}),
                 width="stretch", hide_index=True)
