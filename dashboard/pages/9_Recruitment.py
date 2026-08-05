"""Recruitment — the Athletic-Bilbao origin strategy.

Browse players whose YOUTH/ORIGIN club is on the eligible list (Danish Capital Region by
default, see seeds/eligible_origin_clubs.csv), ranked by their role rating for our tactic.
Only players whose career history is reliably aligned (high/medium confidence) are shown —
the high-sid tail (confidence 'low') is excluded because its origin can't be trusted.
"""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Recruitment", page_icon="🎯", layout="wide")
st.title("🎯 Recruitment — eligible origins")

season, phase = db.select_label()
method = db.select_method()

st.caption("Players whose **origin (youth) club** is on the eligibility list — the "
           "Athletic-Bilbao strategy. Edit `seeds/eligible_origin_clubs.csv` to change the "
           "policy. Origin comes from parsed career history; only reliably-aligned players "
           "(high/medium confidence) appear.")

elig = db.eligibility_frame(season, phase)
eligible = elig[elig["eligible"] & elig["confidence"].isin(["high", "medium"])]
if eligible.empty:
    st.info("No eligible players in this snapshot yet. Check the eligibility list "
            "(`seeds/eligible_origin_clubs.csv`) and that history loaded for this label.")
    st.stop()

# one row per player = their strongest position (max effective rating)
eff = db.effective_table(season, phase, method)
best = eff.sort_values("eff").drop_duplicates("tid", keep="last")
df = best.merge(eligible[["tid", "origin_club", "confidence"]], on="tid", how="inner")

# --- filters -------------------------------------------------------------------
tier = st.sidebar.segmented_control(
    "Confidence", ["High only", "High + medium"], default="High + medium")
if tier == "High only":
    df = df[df["confidence"] == "high"]
hide_ours = st.sidebar.checkbox("Hide players already at our clubs", value=True)
if hide_ours:
    df = df[~df["club_tid"].isin(db.OUR_CLUBS)]
hide_free = st.sidebar.checkbox("Hide free agents", value=False)
if hide_free:
    df = df[df["club"].str.lower() != "free agent"]
allpos = sorted(df["position"].dropna().unique())
picks = st.sidebar.multiselect("Positions", allpos, default=[])
if picks:
    df = df[df["position"].isin(picks)]
min_level = st.sidebar.slider("Min level %ile (global)", 0, 100, 0, 5)
df = df[df["level_global"].fillna(0) >= min_level]

# --- table ---------------------------------------------------------------------
df = df.sort_values("eff", ascending=False)
out = pd.DataFrame({
    "Player": df["name"],
    "Pos": df["position"],
    "Origin": df["origin_club"],
    "Current club": df["club"],
    "Rating": df["eff"].round(1),
    "Fit %ile": df["pctile_global"],
    "Level %ile": df["level_global"],
    "Conf": df["confidence"],
})
st.caption(f"**{len(out)}** eligible players "
           f"({(df['confidence'] == 'high').sum()} high, "
           f"{(df['confidence'] == 'medium').sum()} medium).")
st.dataframe(
    out, width="stretch", hide_index=True,
    column_config={
        "Fit %ile": st.column_config.ProgressColumn(
            "Fit %ile", help="Tactic-fit rating percentile at this position (global)",
            min_value=0, max_value=100, format="%d"),
        "Level %ile": st.column_config.ProgressColumn(
            "Level %ile", help="Tactic-agnostic quality percentile at this position (global)",
            min_value=0, max_value=100, format="%d"),
    },
)
