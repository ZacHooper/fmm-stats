"""Match stats — whole-squad grid with configurable columns, plus per-player drill-down.

Shows both volume (attempts) and success rate so like-for-like comparisons are fair
(a high tackle % on few attempts != a busy reliable defender). Filter by season /
competition / opponent / position, pick which stats to show."""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import stat_table

st.set_page_config(page_title="Match stats", page_icon="📊", layout="wide")
st.title("📊 Match stats")

rows = db.match_stats_rows(db.OUR_CLUBS)
if rows.empty:
    st.info("No player match stats loaded (only managed-club matches are richly parsed).")
    st.stop()

# enrich: player name, opponent name, primary position/unit/squad
rows = db.enrich_match_rows(rows)

# --- filters ---
team_view = st.radio("Squad", ["First team", "Reserve", "Both"], horizontal=True,
                     help="Reserve fixtures (Reserves Group 4) are kept separate from "
                          "first-team matches.")
f = rows.copy()
if team_view != "Both":
    f = f[f["squad"] == team_view]
c1, c2, c3 = st.columns(3)
seasons = c1.multiselect("Seasons", sorted(rows["season"].unique()),
                         default=sorted(rows["season"].unique()))
comps = c2.multiselect("Competitions", sorted(rows["competition"].dropna().unique()))
opps = c3.multiselect("Opponents", sorted(rows["opponent"].unique()))
c4, c5 = st.columns(2)
units = c4.multiselect("Units", db.UNIT_ORDER,
                       help="Broad pitch area (GK / Defense / Midfield / Attack).")
positions = c5.multiselect("Positions", sorted(rows["pos"].dropna().unique()),
                           help="Specific position codes — e.g. pick just DC to compare "
                                "centre-backs without the full-backs (DL/DR).")
f = f[f["season"].isin(seasons)]
if comps:
    f = f[f["competition"].isin(comps)]
if units:
    f = f[f["unit"].isin(units)]
if positions:
    f = f[f["pos"].isin(positions)]
if opps:
    f = f[f["opponent"].isin(opps)]
f = f[f["appeared"]]                      # drop unused subs — they didn't play
if f.empty:
    st.info("No appearances for that filter.")
    st.stop()

# --- aggregate per player (shared with the Squad tool) ---
agg = db.aggregate_match_stats(f)

stats, attrs = stat_table.stat_selector("ps", default_preset="Custom")
detail = st.checkbox("Show start/sub/minutes detail", value=True)

# attribute columns are snapshotted from the latest label (match stats are career)
snap = db.labels_df().iloc[-1]
attrs_by = db.attributes_rows(int(snap["season"]), snap["phase"], agg["tid"].tolist()) if attrs else {}

base = agg.rename(columns={"player": "Player", "pos": "Pos"})[["tid", "Player", "Pos"]].copy()
for c in (["Apps", "Starts", "Sub", "Min"] if detail else ["Apps"]):
    base[c] = agg[c].values
base["Rating"] = agg["Rating"].values
out = stat_table.attach_columns(base, stats, attrs, agg, attrs_by, after="Pos")
st.dataframe(out.sort_values("Rating", ascending=False), width="stretch", hide_index=True)
st.caption("Appearances exclude unused subs. Starts = named in the XI; Sub = off the "
           "bench; Min = minutes (subOff−subOn, 90 if unsubbed). Per 90 = ×90 ÷ minutes "
           "(fairer for subs); per game = ÷ appearances. Conversion % = goals ÷ shots; "
           "DefActions = tackles won + interceptions + headers won. Attribute columns are "
           f"from the latest snapshot ({int(snap['season'])} {snap['phase']}).")

# --- per-player drill-down ---
st.divider()
st.subheader("Player drill-down")
who = st.selectbox("Player", sorted(f["player"].unique(), key=db.surname_key))
p = f[f["player"] == who].copy()
p["role"] = p["started"].map({True: "Start", False: "Sub"})
d = p[["season", "date", "opponent", "competition", "role", "minutes", "rating",
       "goals", "assists", "passA", "passC", "tackA", "tackW", "shotA", "shotO",
       "yellow"]].rename(columns={"minutes": "Min"}).sort_values(["season", "date"])
st.dataframe(d, width="stretch", hide_index=True)
