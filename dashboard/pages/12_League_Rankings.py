"""League Rankings — every playable league ranked by REPUTATION (a u16 parsed straight from
the competition record; see fmparser/reference.find_comp_record). Our nation's pyramid is
highlighted, and our own division's standing is tracked across snapshots so you can watch it
climb as the club rises.

Immersion note: alongside reputation we show an optional SKILL INDEX — average player ability
per league, normalised 0–100. It's a CA-derived aggregate (like the Level %ile), never a raw
CA number, and the underlying average is dropped before anything is displayed."""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="League Rankings", page_icon="🌍", layout="wide")
st.title("🌍 League Rankings")
st.caption("Every loaded league ranked by reputation, with our nation's pyramid tracked over time.")

season, phase = db.select_label()

# ─────────────────────────────────────────────────────────── data: leagues @ snapshot
lg = db.q(
    "SELECT cid, name, nation, nation_id, reputation, member_count "
    "FROM staging.leagues WHERE season=? AND phase=? "
    "AND reputation IS NOT NULL AND name IS NOT NULL "
    "ORDER BY reputation DESC, name",
    [season, phase])
if lg.empty:
    st.info("No league reputation for this snapshot. Re-extract + reload it "
            "(the reputation field is parsed by the current extractor).")
    st.stop()
lg = lg.drop_duplicates("cid").reset_index(drop=True)
lg["rank"] = lg.index + 1

# skill index (immersion-safe): avg player ability per league, normalised 0–100. The raw
# average is computed here and DROPPED — only the index leaves this function.
skill = db.q(
    "SELECT league_cid AS cid, AVG(ca) AS aca, COUNT(*) AS rated "
    "FROM staging.players WHERE season=? AND phase=? AND NOT is_staff "
    "AND has_attributes AND ca > 0 AND league_cid IS NOT NULL "
    "GROUP BY league_cid HAVING COUNT(*) >= 30",
    [season, phase])
if not skill.empty:
    lo, hi = skill["aca"].min(), skill["aca"].max()
    rng = (hi - lo) or 1
    skill["skill_idx"] = ((skill["aca"] - lo) / rng * 100).round(1)
    lg = lg.merge(skill[["cid", "skill_idx", "rated"]], on="cid", how="left")
else:
    lg["skill_idx"] = pd.NA
    lg["rated"] = pd.NA

# our nation: the nation of the league our managed club sits in this snapshot
our_nat = db.q(
    "SELECT l.nation_id FROM staging.players p "
    "JOIN staging.leagues l ON (l.season, l.phase, l.cid) = (p.season, p.phase, p.league_cid) "
    "WHERE p.season=? AND p.phase=? AND p.club_tid=? AND l.nation_id IS NOT NULL LIMIT 1",
    [season, phase, db.MANAGED_CLUB_TID])
OUR_NATION = int(our_nat["nation_id"].iloc[0]) if not our_nat.empty else None
our_name = (lg.loc[lg["nation_id"] == OUR_NATION, "nation"].dropna().head(1).tolist() or [None])[0]

tab_world, tab_ours = st.tabs(["🌍 World", "🇩🇰 Our pyramid"])

# ─────────────────────────────────────────────────────────── World
with tab_world:
    total = len(lg)
    c1, c2 = st.columns([3, 1])
    only_ours = c2.toggle("Only our nation", value=False)
    qtext = c1.text_input("Filter by league / nation name", "").strip().lower()
    view = lg
    if only_ours and OUR_NATION is not None:
        view = view[view["nation_id"] == OUR_NATION]
    if qtext:
        view = view[view["name"].str.lower().str.contains(qtext, na=False)
                    | view["nation"].astype(str).str.lower().str.contains(qtext, na=False)]
    show = view[["rank", "name", "nation", "reputation", "skill_idx", "member_count"]].copy()
    show.columns = ["#", "League", "Nation", "Reputation", "Skill idx", "Clubs"]

    # boolean mask (aligned to show's index) for our-nation rows; NA nation -> False
    ours_mask = (view["nation_id"].eq(OUR_NATION).fillna(False).astype(bool)
                 if OUR_NATION is not None else pd.Series(False, index=view.index))

    def _hi(row):
        tint = "background-color: rgba(80,160,255,0.16)" if bool(ours_mask.loc[row.name]) else ""
        return [tint for _ in row]

    st.caption(f"{total} leagues ranked by reputation"
               + (f" · {our_name} highlighted" if our_name else ""))
    st.dataframe(
        show.style.apply(_hi, axis=1).format(
            {"Reputation": "{:,.0f}", "Skill idx": "{:.1f}", "Clubs": "{:.0f}"}, na_rep="—"),
        use_container_width=True, hide_index=True,
        column_config={"Skill idx": st.column_config.NumberColumn(
            help="Avg player ability, normalised 0–100 across ranked leagues (CA-derived index, "
                 "not a raw rating). Blank for leagues with <30 rated players.")})

# ─────────────────────────────────────────────────────────── Our pyramid + tracking
with tab_ours:
    if OUR_NATION is None:
        st.info("Couldn't resolve our nation for this snapshot.")
        st.stop()
    ours = lg[lg["nation_id"] == OUR_NATION][
        ["rank", "name", "reputation", "skill_idx", "member_count"]].copy()
    ours.columns = ["World #", "League", "Reputation", "Skill idx", "Clubs"]
    st.subheader(f"{our_name or 'Our'} pyramid — this snapshot")
    st.dataframe(ours.style.format(
        {"Reputation": "{:,.0f}", "Skill idx": "{:.1f}", "Clubs": "{:.0f}"}, na_rep="—"),
        use_container_width=True, hide_index=True)

    # our division's reputation across every snapshot — jumps when we're promoted
    div = db.q(
        "WITH us AS (SELECT p.season, p.phase, p.league_cid FROM staging.players p "
        "  WHERE p.club_tid=? AND NOT p.is_staff GROUP BY p.season, p.phase, p.league_cid) "
        "SELECT us.season, us.phase, l.name AS league, l.reputation "
        "FROM us JOIN staging.leagues l "
        "  ON (l.season, l.phase, l.cid) = (us.season, us.phase, us.league_cid) "
        "WHERE l.reputation IS NOT NULL",
        [db.MANAGED_CLUB_TID])
    if not div.empty:
        div = div.drop_duplicates(["season", "phase"])
        div["ord"] = div["phase"].map(db.phase_key)
        div = div.sort_values(["season", "ord"])
        div["snapshot"] = div["season"].astype(str) + " · " + div["phase"].astype(str)
        st.subheader("Our division's reputation over time")
        st.caption("Follows the league our club is registered in each snapshot — it steps up "
                   "when we're promoted.")
        st.line_chart(div.set_index("snapshot")["reputation"])
        st.dataframe(div[["snapshot", "league", "reputation"]].rename(
            columns={"snapshot": "Snapshot", "league": "Division", "reputation": "Reputation"}
        ).style.format({"Reputation": "{:,.0f}"}), use_container_width=True, hide_index=True)

    # whole-nation reputation history (all tiers), for completeness
    hist = db.q(
        "SELECT season, phase, name AS league, reputation FROM staging.leagues "
        "WHERE nation_id=? AND reputation IS NOT NULL AND name IS NOT NULL",
        [OUR_NATION])
    if not hist.empty and hist["phase"].nunique() > 1:
        hist["ord"] = hist["phase"].map(db.phase_key)
        hist = hist.sort_values(["season", "ord"])
        hist["snapshot"] = hist["season"].astype(str) + " · " + hist["phase"].astype(str)
        pivot = hist.pivot_table(index="snapshot", columns="league",
                                 values="reputation", aggfunc="last")
        with st.expander("All our tiers' reputation over time"):
            st.line_chart(pivot)
