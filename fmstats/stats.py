"""Per-player production from the match record (mart.match_player_facts).

mart.match_player_facts already holds one row per player per match — the ring-buffer
re-scrapes across snapshots are resolved there — so a sum over it is a true total. Names are
attached AFTER aggregating: mart.at_club_spells has one row per spell, so joining it first
multiplies every stat by that player's spell count.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class Output:
    players: pd.DataFrame      # player, person_id, pos, apps, starts, mins, g, a, kp, sh, sot,
                               # ga90, kp90, rating, still_here
    n_matches: int
    unresolved: int            # appearances by players the store could not name


def player_output(st, club_tid, vs_tid=None, season=None, since=None):
    """Competitive production for one club's players. Reserve-side games belong to a different
    club tid (and carry no key-pass or shot data), so they never mix in. `still_here` is the
    club's genuine squad at the store's latest snapshot: mart.squad_current for ours, which
    reads the squad array, and mart.snapshot_squad for anyone else (mart.club_squad_latest)."""
    where, params = ["team_tid = ?", "is_competitive", "appeared"], [club_tid]
    if vs_tid is not None:
        where.append("opponent_tid = ?")
        params.append(vs_tid)
    if season is not None:
        where.append("season = ?")
        params.append(season)
    if since is not None:
        where.append("date >= CAST(? AS DATE)")
        params.append(since)
    here_sql = "SELECT person_id FROM mart.club_squad_latest WHERE club_tid = ?"
    here_params = [club_tid]
    if club_tid == st.career.managed_tid and st.career.reserve_tid:
        here_sql += " OR club_tid = ?"
        here_params.append(st.career.reserve_tid)
    cond = " AND ".join(where)
    n_matches, unresolved = st.con.execute(f"""
        SELECT COUNT(DISTINCT date), COUNT(*) FILTER (WHERE person_id IS NULL)
        FROM mart.match_player_facts WHERE {cond}""", params).fetchone()
    df = st.con.execute(f"""
        WITH tot AS (
            SELECT person_id, COUNT(*) AS apps, SUM(started::INT) AS starts,
                   SUM(minutes) AS mins, SUM(goals) AS g, SUM(assists) AS a,
                   SUM(keyPass) AS kp, SUM(shotA) AS sh, SUM(shotO) AS sot,
                   ROUND(AVG(rating), 2) AS rating
            FROM mart.match_player_facts
            WHERE {cond} AND person_id IS NOT NULL GROUP BY person_id),
        pos AS (
            SELECT person_id, first(position ORDER BY n DESC, position) AS pos
            FROM (SELECT person_id, position, COUNT(*) AS n FROM mart.match_player_facts
                  WHERE {cond} AND person_id IS NOT NULL AND position IS NOT NULL
                  GROUP BY person_id, position)
            GROUP BY person_id)
        SELECT (SELECT any_value(s.name) FROM mart.at_club_spells s
                WHERE s.person_id = tot.person_id) AS player,
               person_id, pos, apps, starts, mins, g, a, kp, sh, sot,
               ROUND(90.0 * (g + a) / NULLIF(mins, 0), 2) AS ga90,
               ROUND(90.0 * kp / NULLIF(mins, 0), 2) AS kp90,
               rating,
               person_id IN ({here_sql}) AS still_here
        FROM tot LEFT JOIN pos USING (person_id)""", params + params + here_params).df()
    if not df.empty and df["pos"].isna().any():
        # an opponent's match rows carry no position; use his primary position now
        prim = st.con.execute("""
            SELECT person_id, any_value(position) AS pos FROM mart.player_primary_position
            WHERE season = ? AND phase = ? GROUP BY person_id""",
                              [st.season, st.phase]).df().set_index("person_id")["pos"]
        df["pos"] = df["pos"].fillna(df["person_id"].map(prim))
    for c in ("starts", "mins", "g", "a", "kp", "sh", "sot"):
        df[c] = df[c].astype("Int64")
    return Output(df, int(n_matches or 0), int(unresolved or 0))
