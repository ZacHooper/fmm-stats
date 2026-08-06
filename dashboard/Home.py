"""FM analytics dashboard — entry page.

Run:  uv run streamlit run dashboard/Home.py
"""
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import stat_table

st.set_page_config(page_title="FM Analytics", page_icon="⚽", layout="wide")

st.title("⚽ FM Analytics")
st.caption("Weighted role ratings, player development, and match records — "
           "immersion-safe (no CA/PA anywhere).")

season, phase = db.select_label()
method = db.select_method()

eff = db.effective_table(season, phase, method)
sq = db.squad(season, phase)
status = dict(zip(sq["tid"], sq["status"]))
squad = eff[eff["tid"].isin(set(sq["tid"]))].copy()
if squad.empty:
    st.info("No rated squad players for this label.")
    st.stop()

positions = sorted(squad["position"].unique())
pos = st.selectbox("Position", ["Primary position"] + positions,
                   help="Default shows each player at their strongest position. "
                        "Pick a position to see everyone who can play it there.")

if pos == "Primary position":
    rows = squad.loc[squad.groupby("tid")["familiarity"].idxmax()].copy()
    subtitle = "each player at their primary position"
else:
    rows = squad[squad["position"] == pos].copy()
    subtitle = f"squad players who can play {pos}"

rows["Player"] = rows.apply(lambda r: db.player_label(r.tid, r["name"]), axis=1)
rows["Status"] = rows["tid"].map(status)
rows["Rating"] = rows["eff"].round().astype(int)
rows["League"] = rows.apply(lambda r: f"{int(r.rank_league)} / {int(r.n_league)}", axis=1)
rows["Nation"] = rows.apply(lambda r: f"{int(r.rank_nation)} / {int(r.n_nation)}", axis=1)
rows = rows.sort_values("Rating", ascending=False)

st.subheader(f"Squad · {season} {phase} · {method}")
st.caption(subtitle)

c1, c2, c3 = st.columns(3)
c1.metric("Players shown", len(rows))
c2.metric("Top rating", int(rows["Rating"].max()))
c3.metric("Median league %ile", f"{rows['pctile_league'].median():.0f}")

show = rows[["tid", "Player", "Status", "position", "familiarity", "Rating",
             "pctile_league", "level_league", "League", "pctile_nation", "Nation"]].rename(columns={
    "position": "Pos", "familiarity": "Fam", "pctile_league": "Fit %ile",
    "level_league": "Level %ile", "pctile_nation": "Nation %ile"})
show = db.attach_bio(show, season, phase)         # Age / Value / Origin (toggleable)
show["key"] = show["tid"]

stat_table.player_table(
    "home", show,
    id_options=["Player", "Status", "Pos", "Fam", "Rating", "Fit %ile", "Level %ile",
                "League", "Nation %ile", "Nation", "Age", "Value", "Origin"],
    default_cols=["Player", "Status", "Pos", "Fam", "Rating", "Fit %ile", "Level %ile",
                  "League", "Nation"],
    agg_provider=lambda keys: db.player_match_agg([int(k) for k in keys]),
    attrs_provider=lambda keys: db.attributes_rows(season, phase, [int(k) for k in keys]),
    picker_label="Columns — add/remove any field, match stat or attribute")

st.caption("Rating = tactic-weighted attribute sum × position-familiarity multiplier "
           "(configurable on the Config page). League/Nation columns rank the player among "
           "everyone who plays that position in their division / country. Add any attribute "
           "or match stat, or Age / Value / Origin, via the column picker.")
