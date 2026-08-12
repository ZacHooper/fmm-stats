"""Awards — the season roll of honour. For every season in the store we crown a winner of each
player award (serious + silly) and each team award, always showing the stat that decided it.
Only managed-club matches are richly parsed, so these are OUR club's awards. Player awards use
appearances (not just starts); the min-apps bar scales with games played that season."""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Awards", page_icon="🏅", layout="wide")
st.title("🏅 Awards")
st.caption("Season-by-season roll of honour — each award's winner and the stat that won it.")

# ─────────────────────────────────────────────────────────── data
hist = db.our_match_history()
pm = db.enrich_match_rows(db.match_stats_rows(db.OUR_CLUBS))
if (hist is None or hist.empty) and (pm is None or pm.empty):
    st.info("No matches loaded yet — awards populate once a season has games played.")
    st.stop()
if pm is None:
    pm = pd.DataFrame()

# Awards count COMPETITIVE games only — drop friendlies everywhere (name contains "friendly").
def _competitive(df):
    if df is None or df.empty or "competition" not in df.columns:
        return df
    return df[~df["competition"].astype(str).str.lower().str.contains("friendly", na=False)]

hist, pm = _competitive(hist), _competitive(pm)
if (hist is None or hist.empty) and pm.empty:
    st.info("No competitive matches loaded yet — awards exclude friendlies.")
    st.stop()

# age lookup (season - birth year); dob is a timestamp on staging.players
_dob = db.q("SELECT tid, ANY_VALUE(dob) AS dob FROM staging.players WHERE NOT is_staff GROUP BY tid")
_dob["byear"] = pd.to_datetime(_dob["dob"], errors="coerce").dt.year
BYEAR = dict(zip(_dob["tid"], _dob["byear"]))

# competition type (league/cup/friendly) + attendance-by-date, for team awards
try:
    _ct = db.q("SELECT name, ANY_VALUE(type) AS type FROM staging.competitions GROUP BY name")
    COMP_TYPE = dict(zip(_ct["name"], _ct["type"]))
except Exception:
    COMP_TYPE = {}
try:
    _att = db.q(f"SELECT date, MAX(attendance) AS att FROM staging.matches "
                f"WHERE (home_tid={db.MANAGED_CLUB_TID} OR away_tid={db.MANAGED_CLUB_TID}) "
                f"AND attendance IS NOT NULL AND attendance > 0 GROUP BY date")
    ATT = dict(zip(_att["date"], _att["att"]))
except Exception:
    ATT = {}

# attribute columns for the "Most Improved" growth award (wide staging.player_attributes)
GROWTH_ATTRS = ["Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling", "Technique",
                "Aggression", "Creativity", "Decisions", "Leadership", "Movement", "Positioning",
                "Teamwork", "Pace", "Stamina", "Strength", "Agility", "Handling", "Kicking",
                "Reflexes", "Communication", "Throwing"]

# ─────────────────────────────────────────────────────────── sidebar
squad_opts = sorted(set(pm["squad"].dropna())) if not pm.empty else []
squad_view = st.sidebar.radio("Squad", ["First team", "Reserve", "Both"], index=0) \
    if len(squad_opts) > 1 else "First team"
show_silly = st.sidebar.toggle("Include silly awards", value=True)

seasons = sorted(set(hist["season"]) | (set(pm["season"]) if not pm.empty else set()))

# ─────────────────────────────────────────────────────────── helpers
def _win(df, col, fmt, mask=None, asc=False):
    """(player, stat_str) for the row maximising (or minimising) col under an optional mask."""
    if df is None or df.empty:
        return None
    d = df if mask is None else df[mask]
    d = d[pd.notna(d[col])]
    d = d[d[col] > 0] if not asc else d[d[col] > 0]      # a 0-goal 'winner' isn't a winner
    if d.empty:
        return None
    r = d.loc[d[col].idxmin() if asc else d[col].idxmax()]
    return r["player"], fmt(r[col])


def _fdate(d):
    try:
        return pd.Timestamp(d).strftime("%d %b %Y")
    except Exception:
        return str(d)


def _longest_run(flags):
    best_len, cur = 0, 0
    for f in flags:
        cur = cur + 1 if f else 0
        best_len = max(best_len, cur)
    return best_len


def _season_player_agg(S):
    if pm.empty:
        return pd.DataFrame()
    d = pm[(pm["season"] == S) & pm["appeared"]]
    if squad_view != "Both":
        d = d[d["squad"] == squad_view]
    if d.empty:
        return pd.DataFrame()
    agg = d.groupby(["tid", "player"]).agg(
        apps=("rating", "size"), rating=("rating", "mean"), minutes=("minutes", "sum"),
        goals=("goals", "sum"), assists=("assists", "sum"), key_passes=("keyPass", "sum"),
        headers=("headW", "sum"), dribbles=("dribbles", "sum"), passes=("passC", "sum"),
        tackW=("tackW", "sum"), intercept=("intercept", "sum"),
        mistakes=("mistakes", "sum"), yellows=("yellow", "sum"), shots=("shotA", "sum"),
        crosses=("crossC", "sum"),
    ).reset_index()
    agg["def_actions"] = agg["tackW"] + agg["intercept"]
    agg["rating"] = agg["rating"].round(2)
    agg["conv"] = (100 * agg["goals"] / agg["shots"].where(agg["shots"] >= 10)).round(0)
    agg["age"] = agg["tid"].map(lambda t: (S - BYEAR[t]) if BYEAR.get(t) == BYEAR.get(t) else None)
    # bench impact: goals+assists in games the player did NOT start
    b = d[~d["started"]].groupby("tid").agg(sub_g=("goals", "sum"),
                                            sub_a=("assists", "sum")).reset_index()
    agg = agg.merge(b, on="tid", how="left")
    agg["sub_ga"] = agg["sub_g"].fillna(0) + agg["sub_a"].fillna(0)
    return agg


def _golden_glove(S):
    """First-team keeper who started the most clean-sheet games (goals-against joined from hist)."""
    if pm.empty or hist is None or hist.empty:
        return None
    d = pm[(pm["season"] == S) & pm["started"] & (pm["pos"] == "GK")]
    if squad_view != "Both":
        d = d[d["squad"] == squad_view]
    ga_by_date = dict(zip(hist.loc[hist["season"] == S, "date"],
                          hist.loc[hist["season"] == S, "ga"]))
    d = d.assign(ga=d["date"].map(ga_by_date))
    d = d[d["ga"].notna()]
    if d.empty:
        return None
    cs = d[d["ga"] == 0].groupby("player").size()
    if cs.empty:
        return None
    return cs.idxmax(), f"{int(cs.max())} clean sheets"


def _most_improved(S):
    """Biggest total-attribute growth between the season's earliest and latest snapshot."""
    pa = db.q(
        f"SELECT season, phase, tid, {', '.join(GROWTH_ATTRS)} "
        f"FROM staging.player_attributes WHERE season = {S} AND tid IN "
        f"(SELECT tid FROM staging.players WHERE season={S} AND club_tid IN "
        f"({', '.join(str(t) for t in db.OUR_CLUBS)}) AND NOT is_staff)")
    if pa is None or pa.empty:
        return None
    phases = sorted(pa["phase"].unique(), key=db.phase_key)
    if len(phases) < 2:
        return None
    pa["total"] = pa[GROWTH_ATTRS].fillna(0).sum(axis=1)
    early = pa[pa["phase"] == phases[0]].set_index("tid")["total"]
    late = pa[pa["phase"] == phases[-1]].set_index("tid")["total"]
    g = (late - early).dropna()
    g = g[g > 0]
    if g.empty:
        return None
    tid = int(g.idxmax())
    name = db.q(f"SELECT ANY_VALUE(name) n FROM staging.players WHERE tid={tid}")["n"].iloc[0]
    return name, f"+{int(g.max())} attr pts"


def _hattrick(S):
    """Best single-game goal haul (a hat-trick when one happens)."""
    if pm.empty:
        return None
    d = pm[(pm["season"] == S) & pm["appeared"] & (pm["goals"] >= 1)]
    if squad_view != "Both":
        d = d[d["squad"] == squad_view]
    if d.empty:
        return None
    r = d.loc[d["goals"].idxmax()]
    return r["player"], f"{int(r['goals'])} in a game (vs {r['opponent']}, {_fdate(r['date'])})"


def _stormtrooper(S):
    """Most shots in a single game without scoring (appearances only)."""
    if pm.empty:
        return None
    d = pm[(pm["season"] == S) & pm["appeared"] & (pm["goals"] == 0)]
    if squad_view != "Both":
        d = d[d["squad"] == squad_view]
    d = d[d["shotA"] > 0]
    if d.empty:
        return None
    r = d.loc[d["shotA"].idxmax()]
    return r["player"], f"{int(r['shotA'])} shots, 0 goals (vs {r['opponent']})"


def _injury_summary(S):
    """Per-player injury aggregate for the season: name, spells, weeks_out, windows."""
    inj = db.player_injuries(S)
    if inj.empty:
        return pd.DataFrame()
    rows = []
    for name, g in inj.groupby("name"):
        g = g.sort_values("spell_start")
        wins = "; ".join(f"{pd.Timestamp(a).strftime('%d %b')}–{pd.Timestamp(b).strftime('%d %b')}"
                         for a, b in zip(g["spell_start"], g["spell_end"]))
        rows.append({"Player": name, "Spells": len(g),
                     "Weeks out": int(g["weeks_out"].sum()), "Windows": wins})
    return pd.DataFrame(rows).sort_values("Weeks out", ascending=False)


def _injury_award(S):
    """Most weeks out (the Sick Note) — winner + stat, or None."""
    summ = _injury_summary(S)
    if summ.empty:
        return None
    r = summ.iloc[0]
    sp = int(r["Spells"])
    return r["Player"], f"{int(r['Weeks out'])} weeks out ({sp} spell{'s' if sp != 1 else ''})"


# ── award definitions (edit these lists to change the roll of honour) ──────────
# Each player award: (emoji, name, builder(agg, S) -> (winner, stat) | None, silly?)
def PLAYER_AWARDS(agg, S, min_apps, young_apps):
    A = [
        ("🏆", "Player of the Season",
         _win(agg, "rating", lambda v: f"{v:.2f} avg", mask=agg["apps"] >= min_apps), False),
        ("🌟", "Young Gun (U21)",
         _win(agg, "rating", lambda v: f"{v:.2f} avg",
              mask=(agg["age"] <= 21) & (agg["apps"] >= young_apps)), False),
        ("👟", "Golden Boot", _win(agg, "goals", lambda v: f"{int(v)} goals"), False),
        ("🎩", "Hat-trick Hero", _hattrick(S), False),
        ("🅰️", "Playmaker", _win(agg, "assists", lambda v: f"{int(v)} assists"), False),
        ("🎯", "The Maestro", _win(agg, "key_passes", lambda v: f"{int(v)} key passes"), False),
        ("🎪", "The Crosser", _win(agg, "crosses", lambda v: f"{int(v)} crosses completed"), False),
        ("🗼", "Aerial Dominator", _win(agg, "headers", lambda v: f"{int(v)} headers won"), False),
        ("⚡", "Quick Feet", _win(agg, "dribbles", lambda v: f"{int(v)} dribbles"), False),
        ("🎛️", "The Metronome", _win(agg, "passes", lambda v: f"{int(v)} passes"), False),
        ("🧱", "The Brick Wall",
         _win(agg, "def_actions", lambda v: f"{int(v)} tackles+interceptions"), False),
        ("🧤", "Golden Glove", _golden_glove(S), False),
        ("🎯", "Deadeye (conversion)",
         _win(agg, "conv", lambda v: f"{v:.0f}% shots→goals", mask=agg["shots"] >= 10), False),
        ("⚙️", "Iron Man", _win(agg, "minutes", lambda v: f"{int(v)} minutes"), False),
        ("🚀", "Supersub", _win(agg, "sub_ga", lambda v: f"{int(v)} G+A off the bench"), False),
        ("📈", "Most Improved", _most_improved(S), False),
        ("🤕", "Sick Note (weeks out)", _injury_award(S), False),
        ("🤡", "The Liability", _win(agg, "mistakes", lambda v: f"{int(v)} mistakes"), True),
        ("🔪", "The Enforcer", _win(agg, "yellows", lambda v: f"{int(v)} yellows"), True),
        ("🌩️", "The Stormtrooper", _stormtrooper(S), True),
    ]
    return A


def TEAM_AWARDS(ms, S):
    """Team season honours from our match rows (+ goal events for comebacks)."""
    if ms is None or ms.empty:
        return []
    ms = ms.sort_values("date").reset_index(drop=True)
    W = int((ms["result"] == "W").sum()); D = int((ms["result"] == "D").sum())
    L = int((ms["result"] == "L").sum())
    gf, ga = int(ms["gf"].sum()), int(ms["ga"].sum())
    ppg = (3 * W + D) / len(ms)
    t = ms.assign(margin=ms["gf"] - ms["ga"], total=ms["gf"] + ms["ga"],
                  passpct=(100 * ms["our_passes_completed"]
                           / ms["our_passes"].where(ms["our_passes"] >= 100)).round(0))

    def mrow(col, fmt, mask=None, asc=False):
        d = t if mask is None else t[mask]
        d = d[pd.notna(d[col])]
        if d.empty:
            return None
        r = d.loc[d[col].idxmin() if asc else d[col].idxmax()]
        return fmt(r), f"vs {r['opponent']} · {_fdate(r['date'])} ({r['venue']})"

    # comeback / blown-lead from minute-stamped goal events (reconstruct running score)
    comeback = bottle = None
    ge = _competitive(db.our_goal_events([S]))
    if ge is not None and not ge.empty:
        rows = []
        for anchor, g in ge.groupby("anchor"):
            us = them = mdef = mlead = 0
            for _, e in g.sort_values(["minute", "seq"]).iterrows():
                us, them = (us + 1, them) if e["our_goal"] else (us, them + 1)
                mdef, mlead = max(mdef, them - us), max(mlead, us - them)
            r0 = g.iloc[0]
            rows.append(dict(result=r0["result"], mdef=mdef, mlead=mlead,
                             gf=int(r0["gf"]), ga=int(r0["ga"]),
                             opponent=r0["opponent"], date=r0["date"], venue=r0["venue"]))
        cb = pd.DataFrame(rows)
        won = cb[(cb["result"] == "W") & (cb["mdef"] >= 1)]
        if not won.empty:
            r = won.loc[won["mdef"].idxmax()]
            comeback = (f"from {int(r['mdef'])} down → {int(r['gf'])}–{int(r['ga'])}",
                        f"vs {r['opponent']} · {_fdate(r['date'])} ({r['venue']})")
        blown = cb[(cb["result"] != "W") & (cb["mlead"] >= 1)]
        if not blown.empty:
            r = blown.loc[blown["mlead"].idxmax()]
            bottle = (f"led by {int(r['mlead'])} → {int(r['gf'])}–{int(r['ga'])}",
                      f"vs {r['opponent']} · {_fdate(r['date'])} ({r['venue']})")

    def _rec(x):
        if x.empty:
            return None
        w = int((x["result"] == "W").sum()); dd = int((x["result"] == "D").sum())
        ll = int((x["result"] == "L").sum())
        return f"{w}W {dd}D {ll}L", f"{(3 * w + dd) / len(x):.2f} PPG ({len(x)} games)"

    # best calendar month (≥2 games), biggest crowd, deepest cup run
    best_month = None
    mm = ms.assign(ym=pd.to_datetime(ms["date"]).dt.to_period("M"))
    cand = []
    for ym, x in mm.groupby("ym"):
        if len(x) < 2:
            continue
        w = int((x["result"] == "W").sum()); dd = int((x["result"] == "D").sum())
        ll = int((x["result"] == "L").sum())
        cand.append(((3 * w + dd) / len(x), len(x), ym, w, dd, ll))
    if cand:
        bppg, bn, bym, bw, bd, bl = max(cand)
        best_month = (f"{bppg:.2f} PPG", f"{bym.strftime('%b %Y')} ({bw}W {bd}D {bl}L, {bn} games)")

    crowd = None
    att = ms["date"].map(ATT)
    if att.notna().any():
        r = ms.loc[att.idxmax()]
        crowd = (f"{int(att.max()):,}", f"vs {r['opponent']} · {_fdate(r['date'])} ({r['venue']})")

    cup_run = None
    cup_names = [n for n, tp in COMP_TYPE.items() if tp == "cup"]
    cups = ms[ms["competition"].isin(cup_names)] if cup_names else ms.iloc[0:0]
    if not cups.empty:
        top_cup = cups["competition"].value_counts().idxmax()
        c = cups[cups["competition"] == top_cup].sort_values("date")
        last = c.iloc[-1]
        status = ("won it" if last["result"] == "W"
                  else f"out {int(last['gf'])}–{int(last['ga'])} vs {last['opponent']}")
        cup_run = (f"{len(c)} matches", f"{top_cup} · last: {status}")

    out = [
        ("📋", "Season Record", (f"{W}W {D}D {L}L", f"{gf} for / {ga} against · {ppg:.2f} PPG")),
        ("💥", "Biggest Win",
         mrow("margin", lambda r: f"{int(r['gf'])}–{int(r['ga'])} (+{int(r['margin'])})",
              mask=t["result"] == "W")),
        ("⚽", "Highest-scoring Game",
         mrow("total", lambda r: f"{int(r['gf'])}–{int(r['ga'])} ({int(r['total'])} goals)")),
        ("🎯", "Best Passing Display",
         mrow("passpct", lambda r: f"{r['passpct']:.0f}% pass completion")),
        ("🗡️", "Most Shots in a Game", mrow("our_shots", lambda r: f"{int(r['our_shots'])} shots")),
        ("🛡️", "Clean Sheets", (f"{int((ms['ga'] == 0).sum())} of {len(ms)}", "shut-outs this season")),
        ("🧱", "Longest Clean-sheet Streak",
         (f"{_longest_run(ms['ga'] == 0)} in a row", "consecutive shut-outs")),
        ("🔥", "Longest Win Streak",
         (f"{_longest_run(ms['result'] == 'W')} in a row", "consecutive wins")),
        ("📈", "Longest Unbeaten Run",
         (f"{_longest_run(ms['result'].isin(['W', 'D']))} games", "without defeat")),
        ("🏰", "Home Fortress", _rec(ms[ms["venue"] == "H"])),
        ("✈️", "Road Warriors", _rec(ms[ms["venue"] == "A"])),
    ]
    if best_month:
        out.append(("📅", "Best Month", best_month))
    if crowd:
        out.append(("🏟️", "Biggest Crowd", crowd))
    if cup_run:
        out.append(("🏆", "Cup Run", cup_run))
    if comeback:
        out.append(("🔄", "Biggest Comeback", comeback))
    if bottle:
        out.append(("💔", "Bottle Job (lead surrendered)", bottle))
    return out


# ─────────────────────────────────────────────────────────── render
def _award_table(items):
    rows = [{"": e, "Award": n, "Winner": (v[0] if v else "—"), "Stat": (v[1] if v else "—")}
            for (e, n, v, *rest) in items]
    return pd.DataFrame(rows)


tab_player, tab_team, tab_honours = st.tabs(
    ["👤 Player awards", "🏟️ Team awards", "📜 Roll of honour (all years)"])

with tab_player:
    for S in reversed(seasons):
        agg = _season_player_agg(S)
        gms = len(hist[hist["season"] == S]) or 1
        min_apps, young_apps = max(5, round(0.35 * gms)), max(3, round(0.20 * gms))
        st.subheader(f"Season {S}")
        if agg.empty:
            st.caption("No player appearances this season.")
            continue
        items = [a for a in PLAYER_AWARDS(agg, S, min_apps, young_apps) if show_silly or not a[3]]
        st.dataframe(_award_table(items), width="stretch", hide_index=True)
        st.caption(f"Min apps: Player of the Season ≥{min_apps}, Young Gun ≥{young_apps} "
                   f"({gms} games played).")
        inj = _injury_summary(S)
        if not inj.empty:
            st.markdown("**🤕 Injuries** — from the weekly Player-Progress table "
                        "(includes training injuries, not just in-match).")
            st.dataframe(inj, width="stretch", hide_index=True)

with tab_team:
    for S in reversed(seasons):
        ms = hist[hist["season"] == S]
        st.subheader(f"Season {S}")
        items = TEAM_AWARDS(ms, S)
        if not items:
            st.caption("No managed-club matches this season.")
            continue
        st.dataframe(_award_table(items), width="stretch", hide_index=True)

with tab_honours:
    st.caption("Every award's winner across all seasons — the club's honours board.")
    for scope, builder in [("Player", "player"), ("Team", "team")]:
        st.markdown(f"### {scope} awards")
        matrix = {}
        for S in seasons:
            if builder == "player":
                agg = _season_player_agg(S)
                gms = len(hist[hist["season"] == S]) or 1
                if agg.empty:
                    continue
                items = [a for a in PLAYER_AWARDS(agg, S, max(5, round(0.35 * gms)),
                                                  max(3, round(0.20 * gms))) if show_silly or not a[3]]
            else:
                items = TEAM_AWARDS(hist[hist["season"] == S], S)
            for (e, n, v, *rest) in items:
                matrix.setdefault(f"{e} {n}", {})[S] = (f"{v[0]} — {v[1]}" if v and
                                                        isinstance(v, tuple) and v[0] else "—")
        if matrix:
            df = pd.DataFrame(matrix).T.reindex(columns=seasons)
            df.columns = [str(c) for c in df.columns]
            st.dataframe(df.fillna("—"), width="stretch")
