"""Opposition scouting over a career store, plus the R2-mirrored scout log.

`scout_report()` is the one-stop pull a scout does by hand: head-to-head, both squads rated in
one coherent frame, unit strength and the face-off matchups, the opponent's key players and the
players who have actually produced against us, the opposing manager's formation/Style record,
and a rule-based auto-read. `save_scout()`/`grade_scout()` keep the pre-match read and its
post-match grading as two separate halves of one record, which is what makes the log usable as
calibration.

Two ratings run through a report and they answer different questions:
  * `index`/`pctile` (pos_index / pctile_league) are OUR tactic's role-weighted Fit — how well an
    attribute set suits the method we rate with. Only a fair question for OUR squad.
  * `quality` (level_league, mean Level %ile) is tactic-agnostic and immersion-safe — the number
    for sizing up a stranger. Matchups and the opponent's key players use it.
Neither is a record of output. `h2h_players` is: per-player production in matches against us.

Every function takes an open `fmstats.store.Store` (or its connection) — nothing here holds a
module-level connection.
"""
import datetime
import sys
import unicodedata

import pandas as pd

from fmparser.model import ATTR_ORDER
from fmstats import state

ATTR_GROUPS = {
    "Technical": ["Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
                  "Technique", "Aerial"],
    "Mental": ["Aggression", "Creativity", "Decisions", "Leadership", "Movement",
               "Positioning", "Teamwork"],
    "Physical": ["Pace", "Stamina", "Strength"],
    "Goalkeeping": ["Agility", "Handling", "Kicking", "Reflexes", "Throwing",
                    "Communication"],
}
POSITION_UNIT = {
    "GK": "GK",
    "DC": "Defense", "DL": "Defense", "DR": "Defense", "DML": "Defense", "DMR": "Defense",
    "DMC": "Midfield", "MC": "Midfield", "ML": "Midfield", "MR": "Midfield",
    "AMC": "Attack", "AML": "Attack", "AMR": "Attack", "ST": "Attack",
}
OUTFIELD_GROUPS = ["Technical", "Mental", "Physical"]
OUTFIELD_ATTRS = [a for g in OUTFIELD_GROUPS for a in ATTR_GROUPS[g]]
# pure-GK attributes — excluded when listing an outfield player's top attributes
_GK_ONLY = ("Handling", "Kicking", "Reflexes", "Throwing", "Communication")
# distinctive-but-not-a-threat mentals — a high value here doesn't describe how a player
# hurts you, so they never qualify as a standout
_LOW_SIGNAL = ("Leadership", "Teamwork", "Aggression")
# their-defence soft-spots: (attribute, below-this-is-weak, phrase)
_DEF_SOFT = [("Aerial", 9, "weak in the air"), ("Strength", 8, "physically light"),
             ("Positioning", 9, "poor positioning"), ("Pace", 9, "lacks pace")]
# best XI per unit for a team/unit rating (canonical 4-3-3): GK + 4 def + 3 mid + 3 att
UNIT_XI = {"GK": 1, "Defense": 4, "Midfield": 3, "Attack": 3}
# a player still at the opponent with at least this many goals+assists against us is flagged
PRODUCER_MIN_GA = 2

# A back line never plays a back line — it plays the opposition's front line. `strength` pairs
# each unit with itself ("how strong is each line in isolation"); these are the pairings that
# actually meet on the pitch.
FACE_OFFS = [
    ("Our attack vs their defense", "Attack", "Defense"),
    ("Their attack vs our defense", "Defense", "Attack"),
    ("Midfield (contested)", "Midfield", "Midfield"),
]


def _q(con, sql, params=None):
    return con.execute(sql, params or []).df()


# letters Unicode does not decompose into base + accent, so NFKD alone leaves them in place
_TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ł": "l",
                           "þ": "th", "ð": "d"})


def _fold(s):
    """Casefold + strip diacritics + transliterate, so an ASCII query ('kirklareli',
    'brondby') matches the stored name ('Kırklarelispor', 'Brøndbyernes')."""
    s = str(s).replace("ı", "i").replace("İ", "i").replace("I", "i").casefold()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.translate(_TRANSLIT)


def _initials(name):
    return "".join(w[0] for w in _fold(name).replace("-", " ").split() if w)


def rating_method(st, method=None):
    """The weight-set to rate with: explicit > the career's `rating_method` > app_config."""
    if method:
        return method
    if st.career.rating_method:
        return st.career.rating_method
    row = st.con.execute("SELECT value FROM mart.app_config WHERE key='default_method'").fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------- club lookup
def resolve_club(st, name_or_tid):
    """Clubs matching a name, abbreviation or tid at the store's latest snapshot, best first.

    Tiers: exact name, then initials ("OB" -> Odense Boldklub, "FCK" -> Football Club
    København), then a name starting with the query, then a later word starting with it, then
    any substring. Within a tier, clubs in our own nation come first, then larger squads — so
    a first team outranks its reserves.
    A plain substring search is not enough: "ob" is inside "Hobro". Columns: tid, name,
    league, n_players, domestic, tier. Empty if nothing matches."""
    s = str(name_or_tid).strip()
    clubs = _q(st.con, """
        SELECT c.club_tid AS tid, c.name, c.league_name AS league, c.squad_size AS n_players,
               c.nation = (SELECT nation FROM mart.clubs m
                           WHERE (m.season, m.phase, m.club_tid) = (?, ?, ?)) AS domestic
        FROM mart.clubs c
        WHERE c.season = ? AND c.phase = ? AND c.name IS NOT NULL""",
               [st.season, st.phase, st.career.managed_tid, st.season, st.phase])
    clubs["domestic"] = clubs["domestic"].fillna(False).astype(bool)
    if s.isdigit():
        hit = clubs[clubs["tid"] == int(s)].copy()
        hit["tier"] = 0
        return hit.reset_index(drop=True)
    key = _fold(s)
    folded = clubs["name"].map(_fold)

    def tier(i):
        n = folded.iat[i]
        if n == key:
            return 0
        if len(key) >= 2 and _initials(clubs["name"].iat[i]) == key:
            return 1
        if n.startswith(key):
            return 2
        if any(w.startswith(key) for w in n.split()):
            return 2.5
        if key in n:
            return 3
        return None

    clubs["tier"] = [tier(i) for i in range(len(clubs))]
    hit = clubs[clubs["tier"].notna() & (clubs["n_players"] > 0)].copy()
    hit = hit.sort_values(["tier", "domestic", "n_players"], ascending=[True, False, False])
    return hit.reset_index(drop=True)


# --------------------------------------------------------------------------- squad frame
def effective_table(st, method, season=None, phase=None):
    """Every player x position at a snapshot: base role rating, familiarity-adjusted `eff`,
    Fit percentiles (method-dependent, mart.player_position_fit) and Level percentiles
    (method-independent, mart.player_position_levels). The ability number is not reachable
    from either view, so nothing here can leak it."""
    return _q(st.con, """
        SELECT f.tid, f.position, f.role, f.familiarity, f.base_rating, f.eff,
               f.name, f.club, f.club_tid, f.league_cid, f.nation,
               f.pctile_global, f.pctile_nation, f.pctile_league,
               l.level_global, l.level_nation, l.level_league
        FROM mart.player_position_fit f
        JOIN mart.player_position_levels l USING (season, phase, tid, position)
        WHERE f.season = ? AND f.phase = ? AND f.method = ?""",
              [season or st.season, phase or st.phase, method])


def _primary_position(eff):
    """One row per player: the position he's most familiar at, best-rated among equals. `eff`
    is not comparable across positions (each role weights a different number of attributes),
    so ranking a player's own positions by eff alone just picks his most heavily weighted role."""
    order = eff.sort_values(["familiarity", "eff"], ascending=[False, False])
    return order.groupby("tid", sort=False).head(1).copy()


def _add_position_index(eff):
    """`pos_index`: the role rating standardised within each position against the global pool,
    100 = an average player for that position, 15 = one std. Makes ratings comparable across
    positions (raw eff runs GK~324 vs ST~404 purely from weight scale)."""
    eff = eff.copy()
    if eff.empty:
        eff["pos_index"] = pd.Series(dtype=float)
        return eff
    grp = eff.groupby("position")["eff"]
    mean, std = grp.transform("mean"), grp.transform("std")
    eff["pos_index"] = (100 + 15 * (eff["eff"] - mean) / std.where(std > 0)).fillna(100.0).round(1)
    return eff


def club_attributes(st, club_tids, season=None, phase=None):
    """The 23 attributes for players GENUINELY at the given clubs, via mart.snapshot_squad.

    A raw `club_tid` filter is not safe: a loan that lapsed without being renewed can leave a
    departed player's `club_tid` pointing at his old club indefinitely (Ernest Nuamah read
    `club_tid=346` sixteen months after his loan to us ended)."""
    if not club_tids:
        return pd.DataFrame()
    cols = ", ".join(f'ps."{a}"' for a in ATTR_ORDER)
    ph = ",".join("?" * len(club_tids))
    return _q(st.con, f"""
        SELECT ps.tid, ps.club_tid, {cols}
        FROM mart.player_snapshots ps
        JOIN mart.snapshot_squad ss
             ON (ss.season, ss.phase, ss.tid, ss.club_tid)
              = (ps.season, ps.phase, ps.tid, ps.club_tid)
        WHERE ps.season = ? AND ps.phase = ? AND ps.club_tid IN ({ph})""",
              [season or st.season, phase or st.phase, *club_tids])


def squad_frame(st, method, club_tids, season=None, phase=None):
    """One row per player (primary position) for the given clubs: eff, pos_index,
    pctile_league, level_league, unit, and the 23 attributes."""
    eff = _add_position_index(effective_table(st, method, season, phase))
    if eff.empty:
        return pd.DataFrame()
    prim = _primary_position(eff)
    prim = prim[prim["club_tid"].isin(list(club_tids))]
    if prim.empty:
        return prim
    prim["unit"] = prim["position"].map(POSITION_UNIT)
    ca = club_attributes(st, list(club_tids), season, phase)
    keep = ["tid", "name", "club_tid", "position", "unit", "eff", "pos_index",
            "pctile_league", "level_league"]
    return prim[keep].merge(ca.drop(columns=["club_tid"]), on="tid", how="inner")


def _best_xi(frame_club):
    """Best-N players per unit by position index — a canonical 4-3-3 (GK+4+3+3)."""
    parts = [frame_club[frame_club["unit"] == u].sort_values("pos_index", ascending=False).head(k)
             for u, k in UNIT_XI.items()]
    return pd.concat(parts) if parts else frame_club.iloc[0:0]


def team_strength(frame, club_tid):
    """(per-unit DataFrame, team dict) over a club's best XI: `index` (mean pos_index) and
    `pctile` (mean Fit %ile) under the rating method; `quality` (mean Level %ile), tactic-agnostic."""
    xi = _best_xi(frame[frame["club_tid"] == club_tid]) if not frame.empty else frame
    rows = []
    for unit in ["Defense", "Midfield", "Attack", "GK"]:
        u = xi[xi["unit"] == unit] if not xi.empty else xi
        rows.append({"unit": unit, "n": len(u),
                     "index": round(u["pos_index"].mean(), 1) if len(u) else None,
                     "pctile": round(u["pctile_league"].mean(), 0) if len(u) else None,
                     "quality": round(u["level_league"].mean(), 0) if len(u) else None})
    team = {"index": round(xi["pos_index"].mean(), 1) if not xi.empty else None,
            "pctile": round(xi["pctile_league"].mean(), 0) if not xi.empty else None,
            "quality": round(xi["level_league"].mean(), 0) if not xi.empty else None,
            "n": len(xi) if not xi.empty else 0}
    return pd.DataFrame(rows), team


def _role_relevance(st, method):
    """{position: {attr_lower: weight}} for weights >= 2 — which attributes a slot is judged on."""
    w = _q(st.con, """
        SELECT pr.position, w.attribute, w.weight
        FROM mart.position_roles pr
        JOIN mart.role_weights w ON w.role = pr.role
        WHERE w.method = ? AND w.weight >= 2""", [method])
    rel = {}
    for r in w.itertuples(index=False):
        rel.setdefault(r.position, {})[r.attribute] = r.weight
    return rel


def _player_top_attrs(row, rel, n=3, floor=9):
    """A player's most threat-defining attributes: value >= floor, boosted by role relevance so
    role-relevant strengths lead but an elite off-role attribute still shows."""
    pos = row.get("position")
    rw = rel.get(pos, {})
    scored = []
    for a in ATTR_ORDER:
        if (pos != "GK" and a in _GK_ONLY) or a in _LOW_SIGNAL:
            continue
        v = row.get(a)
        if v is None or pd.isna(v) or int(v) < floor:
            continue
        scored.append((a, int(v), int(v) + 0.6 * rw.get(a.lower(), 0)))
    scored.sort(key=lambda x: (-x[2], -x[1]))
    return ", ".join(f"{a} {v}" for a, v, _ in scored[:n])


def squad_key_players(st, frame, club_tid, method, rank_by="pos_index"):
    """A club's players ranked by `rank_by`, each with `top_attrs`. Use "pos_index" for our own
    squad (we run the rating method) and "level_league" for an opponent (quality, not fit to a
    system they don't play)."""
    of = frame[frame["club_tid"] == club_tid] if not frame.empty else frame
    if of.empty:
        return pd.DataFrame()
    rel = _role_relevance(st, method)
    ofs = of.sort_values(rank_by, ascending=False)
    kp = ofs[["tid", "name", "position", "eff", "pos_index", "pctile_league",
              "level_league"]].copy()
    kp["top_attrs"] = [_player_top_attrs(r, rel) for _, r in ofs.iterrows()]
    return kp.reset_index(drop=True)


def _unit_tables(frame, us, opp):
    """(group-level, attribute-level) us-vs-them tables for Defense/Midfield/Attack.
    edge = us - them (+ = our advantage); None where a side is empty."""
    grp_rows, attr_rows = [], []
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    for unit in ["Defense", "Midfield", "Attack"]:
        fu = frame[frame["unit"] == unit]
        us_f, them_f = fu[fu["club_tid"] == us], fu[fu["club_tid"] == opp]
        for metric in OUTFIELD_GROUPS:
            u = round(us_f[ATTR_GROUPS[metric]].mean(axis=1).mean(), 1) if not us_f.empty else None
            t = (round(them_f[ATTR_GROUPS[metric]].mean(axis=1).mean(), 1)
                 if not them_f.empty else None)
            grp_rows.append({"unit": unit, "metric": metric, "us": u, "them": t,
                             "edge": round(u - t, 1) if u is not None and t is not None else None,
                             "us_n": len(us_f), "them_n": len(them_f)})
        for a in OUTFIELD_ATTRS:
            u = round(us_f[a].mean(), 1) if not us_f.empty else None
            t = round(them_f[a].mean(), 1) if not them_f.empty else None
            attr_rows.append({"unit": unit, "attribute": a, "us": u, "them": t,
                              "edge": round(u - t, 1) if u is not None and t is not None else None})
    return pd.DataFrame(grp_rows), pd.DataFrame(attr_rows)


def matchup_table(us_units, op_units):
    """Face-off unit comparison (see FACE_OFFS). Headline is `quality` (Level %ile);
    `us_fit`/`them_fit` (pos_index) ride along."""
    us_by = {r["unit"]: r for _, r in us_units.iterrows()} if not us_units.empty else {}
    op_by = {r["unit"]: r for _, r in op_units.iterrows()} if not op_units.empty else {}
    rows = []
    for label, us_unit, them_unit in FACE_OFFS:
        u, t = us_by.get(us_unit), op_by.get(them_unit)
        uq = u["quality"] if u is not None else None
        tq = t["quality"] if t is not None else None
        rows.append({"matchup": label, "us_unit": us_unit, "them_unit": them_unit,
                     "us_quality": uq, "them_quality": tq,
                     "edge": round(uq - tq, 1) if pd.notna(uq) and pd.notna(tq) else None,
                     "us_fit": u["index"] if u is not None else None,
                     "them_fit": t["index"] if t is not None else None})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- history
def match_history(st, club_tid=None):
    """Competitive matches for a club (default: ours), oriented from its side — one row per
    match, already deduplicated across snapshots by mart.club_matches."""
    return _q(st.con, """SELECT * FROM mart.club_matches
                         WHERE club_tid = ? AND is_competitive ORDER BY date""",
              [club_tid or st.career.managed_tid])


def h2h_players(st, opp_tid, us_tid=None):
    """The opponent's per-player production in competitive matches against us, one row per
    person, aggregated BEFORE the name is attached (mart.at_club_spells has one row per spell,
    so joining it first multiplies every total). `still_there` = at the opponent at the store's
    latest snapshot. Level %ile rankings are a poor guide to who actually hurts us — in the OB
    fixture the two lowest-rated regulars were the top scorer and top creator — so this is the
    output record to read alongside `key_players`."""
    return _q(st.con, """
        WITH f AS (
            SELECT * FROM mart.match_player_facts
            WHERE team_tid = ? AND opponent_tid = ? AND is_competitive AND appeared),
        tot AS (
            SELECT person_id, COUNT(*) AS apps, SUM(started::INT) AS starts,
                   SUM(minutes) AS minutes, SUM(goals) AS goals, SUM(assists) AS assists,
                   SUM(keyPass) AS key_passes, SUM(shotA) AS shots, SUM(shotO) AS on_target,
                   SUM(crossC) AS crosses_completed, SUM(dribbles) AS dribbles,
                   ROUND(AVG(rating), 2) AS avg_rating, MAX(date) AS last_played
            FROM f WHERE person_id IS NOT NULL GROUP BY person_id)
        SELECT (SELECT any_value(s.name) FROM mart.at_club_spells s
                WHERE s.person_id = tot.person_id) AS name,
               tot.*,
               tot.person_id IN (SELECT person_id FROM mart.snapshot_squad
                                 WHERE club_tid = ? AND season = ? AND phase = ?) AS still_there
        FROM tot
        ORDER BY goals + assists DESC, key_passes DESC, shots DESC""",
              [opp_tid, us_tid or st.career.managed_tid, opp_tid, st.season, st.phase])


def opponent_manager(st, club_tid, season=None, phase=None):
    """The club's manager at a snapshot from mart.club_managers — his preferred / attacking /
    defensive formation and derived Style. A tendency, not today's XI. None for a club we
    manage (every one of our staff is listed, so no AI manager exists)."""
    df = _q(st.con, """SELECT name, style, attacking_intent, reputation_tier,
                              formation_preferred_name, formation_attacking_name,
                              formation_defensive_name, tactical_knowledge, discipline, motivating
                       FROM mart.club_managers
                       WHERE club_tid = ? AND season = ? AND phase = ?""",
            [club_tid, season or st.season, phase or st.phase])
    if df.empty:
        return None
    r = df.iloc[0]
    return {"name": r["name"], "style": r["style"],
            "attacking_intent": (int(r["attacking_intent"])
                                 if pd.notna(r["attacking_intent"]) else None),
            "reputation_tier": r["reputation_tier"],
            "formation_preferred": r["formation_preferred_name"],
            "formation_attacking": r["formation_attacking_name"],
            "formation_defensive": r["formation_defensive_name"],
            "tactical_knowledge": r["tactical_knowledge"], "discipline": r["discipline"],
            "motivating": r["motivating"]}


# --------------------------------------------------------------------------- report
def _fmt_edge(x):
    return f"+{x:.1f}" if x >= 0 else f"{x:.1f}"


def _scout_flags(overall, attrs_df, key_players, h2h, coverage, matchups, producers):
    """Rule-based auto-read. On a partial frame (<11 rated players) every squad-derived read is
    WITHHELD rather than hedged: scouting Hajduk Split off two rated players produced "their
    defence: weak in the air (Aerial 5)" from ONE full-back, and a plan built on it lost 1-3.
    H2H and the producers list come from match history, so coverage does not affect them."""
    F = []
    partial = coverage["partial"]
    if partial:
        F.append(f"⚠️ PARTIAL DATA — only {coverage['in_frame']} rated players "
                 f"({coverage['n_with_attr']}/{coverage['n_players']} with attributes). "
                 "Team strength, matchups, danger men and defensive soft spots are WITHHELD.")
    u, t, up, tp = (overall.get(k) for k in ("us", "them", "us_pctile", "them_pctile"))
    if not partial and u is not None and t is not None:
        d = u - t
        ctx = f" ({up:.0f} vs {tp:.0f} %ile league)" if pd.notna(up) and pd.notna(tp) else ""
        if abs(d) < 3:
            F.append(f"Evenly matched — team index {u:.0f} vs {t:.0f}{ctx}.")
        elif d > 0:
            F.append(f"We're stronger — team index {u:.0f} vs {t:.0f}{ctx}.")
        else:
            F.append(f"They're stronger — team index {t:.0f} vs {u:.0f} to us{ctx}.")
    if h2h.get("played"):
        rec = f"P{h2h['played']} W{h2h['w']} D{h2h['d']} L{h2h['l']}"
        if h2h["w"] == 0 and h2h["played"] >= 3:
            F.append(f"🚩 BOGEY SIDE — never beaten them ({rec}).")
        elif h2h["l"] == 0 and h2h["played"] >= 3:
            F.append(f"✅ We own them ({rec}, {h2h['ppg']:.2f} ppg).")
        else:
            F.append(f"H2H: {rec} ({h2h['ppg']:.2f} ppg).")
        for venue, lbl in (("H", "home"), ("A", "away")):
            v = h2h.get(venue)
            if v and v["played"] >= 3 and (v["w"] == 0 or v["l"] == 0):
                word = "never won" if v["w"] == 0 else "unbeaten"
                F.append(f"H2H {lbl}: {word} "
                         f"(P{v['played']} W{v['w']} D{v['d']} L{v['l']}).")
    if producers is not None and not producers.empty:
        hot = producers[producers["still_there"]
                        & ((producers["goals"] + producers["assists"]) >= PRODUCER_MIN_GA)]
        if not hot.empty:
            men = [f"{r['name']} {int(r['goals'])}G {int(r['assists'])}A"
                   for _, r in hot.head(4).iterrows()]
            F.append(f"Still there and has hurt us before: {', '.join(men)}.")
    if not partial and matchups is not None and not matchups.empty:
        for _, r in matchups.iterrows():
            if pd.isna(r["edge"]):
                continue
            side = "favours us" if r["edge"] >= 0 else "favours them"
            F.append(f"{r['matchup']}: {side} ({_fmt_edge(r['edge'])} quality %ile).")
    if not partial and key_players is not None and not key_players.empty:
        men = [f"{r['name']} {r['position']}"
               + (f" ({r['level_league']:.0f}%ile)" if pd.notna(r["level_league"]) else "")
               for _, r in key_players.head(3).iterrows()]
        F.append(f"Highest-rated (Level %ile, tactic-agnostic): {', '.join(men)}.")
    if not partial and not attrs_df.empty:
        td = attrs_df[attrs_df["unit"] == "Defense"].set_index("attribute")["them"]
        soft = [f"{lbl} ({a} {td[a]:.0f})" for a, thr, lbl in _DEF_SOFT
                if a in td.index and pd.notna(td[a]) and td[a] < thr]
        if soft:
            F.append(f"Their defence: {', '.join(soft)} — target it.")
    return F


def _record(h):
    w, d, l = (int((h["result"] == r).sum()) for r in "WDL")
    return {"played": len(h), "w": w, "d": d, "l": l,
            "gf": int(h["gf"].sum()), "ga": int(h["ga"].sum()),
            "ppg": round(float(h["pts"].mean()), 2) if len(h) else 0.0}


def scout_report(st, opp_tid, method=None, season=None, phase=None):
    """Structured opposition report (dicts + DataFrames, no rendering). Keys: opp, season,
    phase, method, coverage, overall, strength, matchups, units, unit_attrs, key_players,
    h2h (+ per-venue H/A records and the `matches` frame), h2h_players, flags, manager."""
    method = rating_method(st, method)
    season, phase = season or st.season, phase or st.phase
    us = st.career.managed_tid
    nm = st.con.execute("SELECT name FROM mart.clubs WHERE season=? AND phase=? AND club_tid=?",
                        [season, phase, opp_tid]).fetchone()
    opp_name = nm[0] if nm and nm[0] else f"#{opp_tid}"

    cov = st.con.execute("""
        SELECT COUNT(*), COALESCE(SUM(CASE WHEN ps.has_attributes THEN 1 ELSE 0 END), 0)
        FROM mart.snapshot_squad ss
        LEFT JOIN mart.player_snapshots ps USING (season, phase, tid)
        WHERE ss.season = ? AND ss.phase = ? AND ss.club_tid = ?""",
                         [season, phase, opp_tid]).fetchone()
    frame = squad_frame(st, method, [opp_tid, us], season, phase)
    in_frame = int((frame["club_tid"] == opp_tid).sum()) if not frame.empty else 0
    coverage = {"n_players": int(cov[0] or 0), "n_with_attr": int(cov[1] or 0),
                "in_frame": in_frame, "partial": in_frame < 11}

    us_units, us_team = team_strength(frame, us)
    op_units, op_team = team_strength(frame, opp_tid)
    matchups = matchup_table(us_units, op_units)
    strength = us_units.merge(op_units, on="unit", suffixes=("_us", "_them")).rename(columns={
        "index_us": "us", "index_them": "them", "pctile_us": "us_pctile",
        "pctile_them": "them_pctile", "quality_us": "us_quality",
        "quality_them": "them_quality"})
    strength["edge"] = (strength["us"] - strength["them"]).round(1)
    strength["quality_edge"] = (strength["us_quality"] - strength["them_quality"]).round(1)
    ti, oi, tq, oq = us_team["index"], op_team["index"], us_team["quality"], op_team["quality"]
    strength = pd.concat([strength, pd.DataFrame([{
        "unit": "TEAM", "us": ti, "them": oi, "us_pctile": us_team["pctile"],
        "them_pctile": op_team["pctile"], "us_quality": tq, "them_quality": oq,
        "n_us": us_team["n"], "n_them": op_team["n"],
        "edge": round(ti - oi, 1) if ti is not None and oi is not None else None,
        "quality_edge": round(tq - oq, 1) if pd.notna(tq) and pd.notna(oq) else None}])],
        ignore_index=True)
    overall = {"us": ti, "them": oi, "us_pctile": us_team["pctile"],
               "them_pctile": op_team["pctile"], "us_quality": tq, "them_quality": oq}

    groups_df, attrs_df = _unit_tables(frame, us, opp_tid)
    key_players = squad_key_players(st, frame, opp_tid, method, rank_by="level_league")

    hist = match_history(st, us)
    h = hist[hist["opp_tid"] == opp_tid].sort_values("date")
    if not h.empty:
        h2h = {**_record(h),
               "H": _record(h[h["venue"] == "H"]), "A": _record(h[h["venue"] == "A"]),
               "matches": h}
    else:
        h2h = {"played": 0, "matches": h}
    producers = h2h_players(st, opp_tid, us)

    flags = _scout_flags(overall, attrs_df, key_players, h2h, coverage, matchups, producers)
    return {"opp": {"tid": opp_tid, "name": opp_name}, "season": season, "phase": phase,
            "method": method, "coverage": coverage, "overall": overall, "strength": strength,
            "matchups": matchups, "units": groups_df, "unit_attrs": attrs_df,
            "key_players": key_players, "h2h": h2h, "h2h_players": producers, "flags": flags,
            "manager": opponent_manager(st, opp_tid, season, phase)}


# --------------------------------------------------------------------------- scout log
# Saved scouts live in state/scouts/<opponent_tid>-<snapshot_label>[-<fixture>].json, mirrored
# to R2 by fmstats.state — one object per scout, so two devices saving different scouts can
# never clobber each other.

def _slug(x, sep="-"):
    """Lowercase, filesystem- and R2-safe token. Runs of anything else collapse to one `sep`."""
    out = "".join(c if c.isalnum() or c in "-_." else sep for c in str(x).strip().lower())
    return sep.join(t for t in out.split(sep) if t)


def scout_key(opponent_tid, snapshot_label, fixture=None):
    """One key per SCOUT. `fixture` (the match date) separates the home and away meetings of
    the same opponent between two imports; without it the second would replace the first."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(snapshot_label))
    base = f"{int(opponent_tid)}-{safe}"
    fx = _slug(fixture) if fixture is not None else ""
    return f"{base}-{fx}" if fx else base


def _json_clean(o):
    """Recursively make a value JSON-safe: numpy scalars -> python, NaN -> None, dates -> iso."""
    if isinstance(o, dict):
        return {k: _json_clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_clean(v) for v in o]
    if hasattr(o, "item"):
        o = o.item()
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, (datetime.date, datetime.datetime, pd.Timestamp)):
        return o.isoformat()
    return o


def load_scouts():
    """All saved scouts as a DataFrame (empty if none), oldest first by save time."""
    rows = [rec for _key, rec in state.entries("scouts")]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values("saved_at").reset_index(drop=True) if "saved_at" in df.columns else df


def _snapshot_label(st, season, phase):
    row = st.con.execute("SELECT label FROM mart.snapshots WHERE season=? AND phase=?",
                         [season, phase]).fetchone()
    return row[0] if row and row[0] else f"{season}-{phase}"


def scout_record(st, report, venue=None, formation=None, style=None, note=None, saved_at=None,
                 fixture=None):
    """The JSON-safe record `save_scout` stores for a report — no I/O."""
    return _json_clean({
        "saved_at": saved_at or datetime.datetime.now().isoformat(timespec="seconds"),
        "opponent_tid": report["opp"]["tid"], "opponent": report["opp"]["name"],
        "snapshot": f"{report['season']}-{report['phase']}",
        "snapshot_label": _snapshot_label(st, report["season"], report["phase"]),
        "method": report["method"],
        "venue": venue, "formation": formation, "style": style, "note": note,
        "fixture": fixture,
        "overall": report["overall"], "coverage": report["coverage"],
        "strength": report["strength"].to_dict("records"),
        "matchups": report["matchups"].to_dict("records"),
        "flags": report["flags"],
        "key_players": (report["key_players"].head(8).to_dict("records")
                        if not report["key_players"].empty else []),
        "h2h_players": (report["h2h_players"].head(8).drop(columns=["person_id"])
                        .to_dict("records") if not report["h2h_players"].empty else []),
        "h2h": {k: report["h2h"].get(k)
                for k in ("played", "w", "d", "l", "gf", "ga", "ppg", "H", "A")},
    })


def save_scout(st, report, venue=None, formation=None, style=None, note=None, saved_at=None,
               fixture=None):
    """Store a report in the scout log and push it to R2. Returns the record plus transient
    `_key`, `_sync` (state.SYNCED / LOCAL_ONLY / SYNC_FAILED) and `_collision` — report the
    last two whenever they are not clean.

    A record holds two halves that must not overwrite each other: `note` is what we thought
    BEFORE the game, `result_note` how it graded afterwards. Re-saving carries the grading
    forward and files a superseded `note` into `revisions` rather than losing it."""
    rec = scout_record(st, report, venue, formation, style, note, saved_at, fixture)
    key = scout_key(rec["opponent_tid"], rec["snapshot_label"], fixture)
    prev = state.get("scouts", key) or {}
    collision = bool(prev and fixture is None and prev.get("venue") and venue
                     and prev.get("venue") != venue)
    if collision:
        print(f"scout: {key} already holds a {prev['venue']} scout of {rec['opponent']} and this "
              f"one is {venue} — REPLACING it. Pass fixture= (the match date) to keep both.",
              file=sys.stderr)
    for field in ("result_note", "result", "graded_at"):
        if prev.get(field) is not None:
            rec[field] = prev[field]
    rec["revisions"] = list(prev.get("revisions") or [])
    if prev.get("note") and prev["note"] != rec.get("note"):
        rec["revisions"].append({"saved_at": prev.get("saved_at"), "note": prev["note"]})
    res = state.put("scouts", key, rec)
    rec["_key"], rec["_sync"], rec["_collision"] = key, res.status, collision
    return rec


def grade_scout(opponent_tid, result_note, result=None, snapshot_label=None, graded_at=None,
                fixture=None):
    """Record how a saved scout graded, WITHOUT touching its pre-match `note`.

    Returns None when there is no scout to grade, and raises ValueError rather than guessing
    when several ungraded scouts exist for the opponent and nothing picks one — a wrong guess
    grades the wrong briefing and can overwrite a grading that was already right."""
    want = _slug(fixture) if fixture is not None else None
    cands = [(k, r) for k, r in state.entries("scouts")
             if r.get("opponent_tid") == opponent_tid
             and (snapshot_label is None or r.get("snapshot_label") == snapshot_label)
             and (want is None or (_slug(r["fixture"]) if r.get("fixture") else "") == want)]
    if not cands:
        return None
    if len(cands) > 1 and want is None:
        ungraded = [kr for kr in cands if not kr[1].get("result_note")]
        if len(ungraded) != 1:
            raise ValueError(
                f"{len(cands)} scouts saved for opponent {opponent_tid} "
                f"({', '.join(sorted(k for k, _ in cands))}) — pass fixture= (or "
                f"snapshot_label=) to say which one this result belongs to.")
        cands = ungraded
    key, rec = max(cands, key=lambda kr: kr[1].get("saved_at") or "")
    rec["result_note"] = result_note
    if result is not None:
        rec["result"] = result
    rec["graded_at"] = graded_at or datetime.datetime.now().isoformat(timespec="seconds")
    res = state.put("scouts", key, rec)
    rec["_key"], rec["_sync"] = key, res.status
    return rec
