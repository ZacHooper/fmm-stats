"""Records — the fun superlatives from our parsed matches: biggest wins, single-game team &
player highs, and career/aggregate leaders. Season-filterable. Only managed-club matches are
richly parsed, so these are our team's records (not the whole league)."""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Records", page_icon="🏆", layout="wide")
st.title("🏆 Records")

hist = db.our_match_history()
pm = db.enrich_match_rows(db.match_stats_rows(db.OUR_CLUBS))
if hist.empty and (pm is None or pm.empty):
    st.info("No matches loaded.")
    st.stop()

seasons = sorted(set(hist["season"]) |
                 (set(pm["season"]) if pm is not None and not pm.empty else set()))
comp_opts = sorted(set(hist["competition"].dropna()) |
                   (set(pm["competition"].dropna()) if pm is not None and not pm.empty else set()))
sel = st.sidebar.multiselect("Seasons", seasons, default=seasons)
comps = st.sidebar.multiselect("Competitions", comp_opts,
                               help="Leave empty for all competitions.")
team_view = st.sidebar.radio("Squad (player records)", ["First team", "Reserve", "Both"],
                             index=0)
if not sel:
    st.stop()

m = hist[hist["season"].isin(sel)].copy()
p = (pm[pm["appeared"] & pm["season"].isin(sel)].copy()
     if pm is not None and not pm.empty else pd.DataFrame())
if comps:
    m = m[m["competition"].isin(comps)]
    if not p.empty:
        p = p[p["competition"].isin(comps)]
if not p.empty and team_view != "Both":
    p = p[p["squad"] == team_view]


def best(df, col, asc=False, mask=None):
    """Row with the max (or min) of col, honoring an optional boolean mask; None if empty."""
    d = df if mask is None else df[mask]
    d = d[pd.notna(d[col])]
    return None if d.empty else d.loc[d[col].idxmin() if asc else d[col].idxmax()]


def show(rows):
    rows = [r for r in rows if r is not None]
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("No data for this filter.")


def longest_run(flags):
    """Longest run of truthy values in `flags`; returns (length, start_idx, end_idx)."""
    best_len, bs, be = 0, -1, -1
    cur, cur_s = 0, 0
    for i, f in enumerate(flags):
        if f:
            cur_s = i if cur == 0 else cur_s
            cur += 1
            if cur > best_len:
                best_len, bs, be = cur, cur_s, i
        else:
            cur = 0
    return best_len, bs, be


def fdate(d):
    try:
        return pd.Timestamp(d).strftime("%d %b %Y")
    except Exception:
        return str(d)


tab_team, tab_player, tab_overall, tab_streaks = st.tabs(
    ["🏟️ Team — single game", "👤 Player — single game", "📊 Overall / career",
     "🔥 Streaks & runs"])

# ---------------------------------------------------------------- team single-game
with tab_team:
    st.caption("Biggest / highest single-match team performances across the selected seasons.")
    if m.empty:
        st.caption("No managed-club matches in this filter.")
    else:
        t = m.assign(margin=m["gf"] - m["ga"], total=m["gf"] + m["ga"],
                     passpct=(100 * m["our_passes_completed"]
                              / m["our_passes"].where(m["our_passes"] > 0)).round(0))

        def md(r):
            return (f"{int(r.gf)}–{int(r.ga)} vs {r.opponent} · {r.date} "
                    f"({r.venue}, {r.competition})")

        def tr(label, row, value_fn):
            return None if row is None else {"Record": label, "Value": str(value_fn(row)),
                                             "Match": md(row)}

        team_rows = [
            tr("Biggest win", best(t, "margin", mask=(t["result"] == "W")),
               lambda r: f"+{int(r.margin)}"),
            tr("Heaviest defeat", best(t, "margin", asc=True, mask=(t["result"] == "L")),
               lambda r: f"{int(r.margin)}"),
            tr("Most goals scored", best(t, "gf"), lambda r: int(r.gf)),
            tr("Most goals conceded", best(t, "ga"), lambda r: int(r.ga)),
            tr("Highest-scoring game", best(t, "total"), lambda r: f"{int(r.total)} goals"),
            tr("Most shots", best(t, "our_shots"), lambda r: int(r.our_shots)),
            tr("Highest pass %", best(t, "passpct"), lambda r: f"{r.passpct:.0f}%"),
            tr("Most tackles won", best(t, "our_tackles_won"), lambda r: int(r.our_tackles_won)),
            tr("Most interceptions", best(t, "our_interceptions"),
               lambda r: int(r.our_interceptions)),
            tr("Most crosses", best(t, "our_crosses"), lambda r: int(r.our_crosses)),
        ]
        show(team_rows)

# ---------------------------------------------------------------- player single-game
with tab_player:
    st.caption("Best individual single-match performances (appearances only).")
    if p.empty:
        st.caption("No player appearances in this filter.")
    else:
        pp = p.assign(passpct=(100 * p["passC"] / p["passA"].where(p["passA"] >= 20)).round(0))

        def pr(label, row, value_fn):
            return None if row is None else {
                "Record": label, "Player": row.player, "Value": str(value_fn(row)),
                "Match": f"vs {row.opponent} · {row.date} ({row.competition})"}

        player_rows = [
            pr("Most goals", best(p, "goals"), lambda r: int(r.goals)),
            pr("Most assists", best(p, "assists"), lambda r: int(r.assists)),
            pr("Most shots", best(p, "shotA"), lambda r: int(r.shotA)),
            pr("Most shots on target", best(p, "shotO"), lambda r: int(r.shotO)),
            pr("Most passes", best(p, "passA"), lambda r: int(r.passA)),
            pr("Highest pass % (≥20 passes)", best(pp, "passpct"), lambda r: f"{r.passpct:.0f}%"),
            pr("Most key passes", best(p, "keyPass"), lambda r: int(r.keyPass)),
            pr("Most tackles won", best(p, "tackW"), lambda r: int(r.tackW)),
            pr("Most interceptions", best(p, "intercept"), lambda r: int(r.intercept)),
            pr("Most dribbles", best(p, "dribbles"), lambda r: int(r.dribbles)),
            pr("Highest match rating", best(p, "rating"), lambda r: f"{r.rating:.2f}"),
        ]
        show(player_rows)

# ---------------------------------------------------------------- overall / career
with tab_overall:
    st.caption("Career leaders across the selected seasons (appearances only).")
    if p.empty:
        st.caption("No player appearances in this filter.")
    else:
        agg = p.groupby("player").agg(
            Apps=("rating", "size"), Goals=("goals", "sum"), Assists=("assists", "sum"),
            Shots=("shotA", "sum"), KeyP=("keyPass", "sum"), TackW=("tackW", "sum"),
            Yellows=("yellow", "sum"), Minutes=("minutes", "sum"),
            Rating=("rating", "mean")).reset_index()
        agg["G+A"] = agg["Goals"] + agg["Assists"]
        agg["Rating"] = agg["Rating"].round(2)
        agg["Conv"] = (100 * agg["Goals"] / agg["Shots"].where(agg["Shots"] >= 10)).round(0)

        def ov(label, col, fmt=lambda v: int(v), mask=None, asc=False):
            d = agg if mask is None else agg[mask]
            d = d[pd.notna(d[col])]
            if d.empty:
                return None
            r = d.loc[d[col].idxmin() if asc else d[col].idxmax()]
            return {"Record": label, "Player": r.player, "Value": str(fmt(r[col]))}

        overall_rows = [
            ov("Top scorer", "Goals"),
            ov("Most assists", "Assists"),
            ov("Most goal involvements (G+A)", "G+A"),
            ov("Most appearances", "Apps"),
            ov("Most minutes", "Minutes"),
            ov("Best avg rating (≥5 apps)", "Rating", lambda v: f"{v:.2f}", mask=agg["Apps"] >= 5),
            ov("Best conversion % (≥10 shots)", "Conv", lambda v: f"{v:.0f}%"),
            ov("Most shots", "Shots"),
            ov("Most key passes", "KeyP"),
            ov("Most tackles won", "TackW"),
            ov("Most yellow cards", "Yellows"),
        ]
        show(overall_rows)

        st.markdown("**Top scorers**")
        st.dataframe(agg.sort_values("Goals", ascending=False)
                     .head(10)[["player", "Apps", "Goals", "Assists", "G+A", "Rating"]]
                     .rename(columns={"player": "Player"}), width="stretch", hide_index=True)

# ---------------------------------------------------------------- streaks & runs
with tab_streaks:
    st.caption("Longest runs across the selected seasons, in chronological order.")
    run_rows = []

    if not m.empty:
        ms = m.sort_values("date").reset_index(drop=True)

        def run_row(label, flags):
            L, s, e = longest_run(list(flags))
            if L == 0:
                return None
            return {"Record": label, "Value": f"{L} in a row",
                    "When": f"{fdate(ms.loc[s, 'date'])} → {fdate(ms.loc[e, 'date'])}"}

        run_rows += [
            run_row("Longest win streak", ms["result"] == "W"),
            run_row("Longest unbeaten run", ms["result"].isin(["W", "D"])),
            run_row("Longest winless run", ms["result"].isin(["D", "L"])),
            run_row("Longest clean-sheet streak", ms["ga"] == 0),
        ]
        cs = int((ms["ga"] == 0).sum())
        run_rows.append({"Record": "Most clean sheets", "Value": f"{cs} of {len(ms)} games",
                         "When": "—"})

    pens = db.our_penalties(sel)
    if not pens.empty:
        pens = pens.reset_index(drop=True)
        made = list(pens["made"].astype(bool))

        def pen_row(label, flags):
            L, s, e = longest_run(flags)
            if L == 0:
                return None
            who = ", ".join(pd.unique(pens.loc[s:e, "player"].dropna())) or "—"
            return {"Record": label, "Value": f"{L} in a row",
                    "When": f"{fdate(pens.loc[s, 'date'])} → {fdate(pens.loc[e, 'date'])} ({who})"}

        run_rows.append(pen_row("Most penalties scored in a row", made))
        run_rows.append(pen_row("Most penalties missed in a row", [not x for x in made]))

    if not p.empty:
        top_streak = None
        for player, grp in p.sort_values("date").groupby("player"):
            L, s, e = longest_run(list(grp["goals"] >= 1))
            if top_streak is None or L > top_streak[0]:
                top_streak = (L, player, grp.reset_index(drop=True), s, e)
        if top_streak and top_streak[0] >= 1:
            L, player, grp, s, e = top_streak
            run_rows.append({
                "Record": "Longest player goal streak", "Value": f"{L} game(s)",
                "When": f"{player} · {fdate(grp.loc[s, 'date'])} → {fdate(grp.loc[e, 'date'])}"})

    # comebacks / blown leads — reconstruct running score from minute-stamped goal events
    ge = db.our_goal_events(sel)
    if not ge.empty and comps:
        ge = ge[ge["competition"].isin(comps)]
    if not ge.empty:
        cbrows = []
        for anchor, g in ge.groupby("anchor"):
            us = them = mdef = mlead = 0
            for _, e in g.sort_values(["minute", "seq"]).iterrows():
                us, them = (us + 1, them) if e.our_goal else (us, them + 1)
                mdef, mlead = max(mdef, them - us), max(mlead, us - them)
            r = g.iloc[0]
            rec = dict(result=r.result, mdef=mdef, mlead=mlead, gf=int(r.gf), ga=int(r.ga),
                       opponent=r.opponent, date=r.date, venue=r.venue,
                       competition=r.competition)
            cbrows.append(rec)
        cb = pd.DataFrame(cbrows)

        def cb_row(label, sub, col, vfmt):
            sub = sub[sub[col] >= 1]
            if sub.empty:
                return None
            r = sub.loc[sub[col].idxmax()]
            return {"Record": label, "Value": vfmt(int(r[col])),
                    "When": f"{r.gf}–{r.ga} vs {r.opponent} · {fdate(r.date)} "
                            f"({r.venue}, {r.competition})"}

        run_rows.append(cb_row("Biggest comeback win", cb[cb["result"] == "W"], "mdef",
                               lambda n: f"from {n} down"))
        run_rows.append(cb_row("Biggest comeback to draw", cb[cb["result"] == "D"], "mdef",
                               lambda n: f"from {n} down"))
        run_rows.append(cb_row("Biggest lead surrendered", cb[cb["result"] != "W"], "mlead",
                               lambda n: f"led by {n}"))

    show(run_rows)
    st.caption("Comebacks reconstruct the running score from minute-stamped goal events "
               "(≈99% reconcile the scoreline). Penalty streaks combine all our takers "
               "chronologically. Goal streak = consecutive appearances with ≥1 goal.")
