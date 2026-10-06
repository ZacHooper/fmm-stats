"""Per-player production from the match record (mart.fact_player_match / int.player_match_ratings).

fact_player_match already holds one row per player per match with detail,
and int.player_match_ratings carries rating_adj. Names come directly from
dim_person.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class Output:
    players: pd.DataFrame      # player, person_id, pos, apps, starts, mins, g, a, kp, sh, sot,
                               # ga90, kp90, rating, rating_adj, still_here
    n_matches: int
    unresolved: int            # appearances by players the store could not name


def player_output(st, club_tid, vs_tid=None, season=None, since=None):
    """Competitive production for one club's players. Reserve-side games belong to a different
    club tid (and carry no key-pass or shot data), so they never mix in. `still_here` is the
    club's genuine squad at the store's latest snapshot via mart.squad_membership."""
    where = ["f.team_tid = ?", "c.type != 'friendly'", "f.appeared"]
    params = [club_tid]
    if vs_tid is not None:
        where.append("f.opponent_tid = ?")
        params.append(vs_tid)
    if season is not None:
        where.append(
            "(year(m.match_date) + case when strftime(m.match_date, '%m-%d') >= "
            "(SELECT value FROM raw.app_config WHERE key='career_rollover') then 1 else 0 end) = ?"
        )
        params.append(season)
    if since is not None:
        where.append("m.match_date >= CAST(? AS DATE)")
        params.append(since)
    here_sql = "SELECT person_id FROM mart.squad_membership WHERE (club_tid = ? OR team_tid = ?) AND is_current"
    here_params = [club_tid, club_tid]
    cond = " AND ".join(where)
    n_matches, unresolved = st.con.execute(f"""
        SELECT COUNT(DISTINCT m.match_date), COUNT(*) FILTER (WHERE f.person_id IS NULL)
        FROM mart.fact_player_match f
        JOIN mart.dim_match m USING (match_id)
        JOIN mart.dim_competition c ON c.cid = m.cid
        WHERE {cond}""", params).fetchone()
    df = st.con.execute(f"""
        WITH base AS (
            SELECT f.person_id, f.player_tid, f.position, f.started, f.minutes,
                   f.goals, f.assists, f.key_passes, f.shots, f.shots_on_target,
                   f.rating, r.rating_adj
            FROM mart.fact_player_match f
            JOIN mart.dim_match m USING (match_id)
            JOIN mart.dim_competition c ON c.cid = m.cid
            LEFT JOIN int.player_match_ratings r USING (match_id, player_tid)
            WHERE {cond}
        ),
        tot AS (
            SELECT person_id, COUNT(*) AS apps, SUM(started::INT) AS starts,
                   SUM(minutes) AS mins, SUM(goals) AS g, SUM(assists) AS a,
                   SUM(key_passes) AS kp, SUM(shots) AS sh, SUM(shots_on_target) AS sot,
                   ROUND(AVG(rating), 2) AS rating,
                   ROUND(AVG(rating_adj), 2) AS rating_adj
            FROM base
            WHERE person_id IS NOT NULL GROUP BY person_id),
        pos AS (
            SELECT person_id, first(position ORDER BY n DESC, position) AS pos
            FROM (SELECT person_id, position, COUNT(*) AS n FROM base
                  WHERE person_id IS NOT NULL AND position IS NOT NULL
                  GROUP BY person_id, position)
            GROUP BY person_id)
        SELECT p.name AS player,
               tot.person_id, pos.pos, apps, starts, mins, g, a, kp, sh, sot,
               ROUND(90.0 * (g + a) / NULLIF(mins, 0), 2) AS ga90,
               ROUND(90.0 * kp / NULLIF(mins, 0), 2) AS kp90,
               rating, rating_adj,
               tot.person_id IN ({here_sql}) AS still_here
        FROM tot
        LEFT JOIN pos USING (person_id)
        LEFT JOIN mart.dim_person p USING (person_id)""", params + here_params).df()
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


def player_by_role(st, club_tid, season=None, since=None, min_starts=1):
    """Each player's competitive STARTS split by rating role (DM, Central mid, Attacking mid,
    ...), raw and position-adjusted. The question it answers is "where does this player
    perform best": compare roles on `rating_adj`, never on raw `rating`, which the game biases
    by position (a DM rates ~0.47 below a central midfielder for the same performance). Only
    starts carry a position, and only for OUR matches, so an opponent club returns nothing."""
    where = ["f.team_tid = ?", "c.type != 'friendly'", "f.started", "r.role IS NOT NULL"]
    params = [club_tid]
    if season is not None:
        where.append(
            "(year(m.match_date) + case when strftime(m.match_date, '%m-%d') >= "
            "(SELECT value FROM raw.app_config WHERE key='career_rollover') then 1 else 0 end) = ?"
        )
        params.append(season)
    if since is not None:
        where.append("m.match_date >= CAST(? AS DATE)")
        params.append(since)
    cond = " AND ".join(where)
    df = st.con.execute(f"""
        WITH base AS (
            SELECT f.person_id, f.player_tid, f.team_tid, r.role,
                   f.rating, r.rating_adj, f.goals, f.assists, f.key_passes,
                   f.passes_completed, f.tackles_won, f.interceptions, f.mistakes
            FROM mart.fact_player_match f
            JOIN mart.dim_match m USING (match_id)
            JOIN mart.dim_competition c ON c.cid = m.cid
            JOIN int.player_match_ratings r USING (match_id, player_tid)
            WHERE {cond}
        ),
        tot AS (
            SELECT person_id, role, any_value(ro.role_order) AS role_order, COUNT(*) AS starts,
                   ROUND(AVG(rating), 2) AS rating, ROUND(AVG(rating_adj), 2) AS rating_adj,
                   SUM(goals) AS g, SUM(assists) AS a, SUM(key_passes) AS kp,
                   ROUND(AVG(passes_completed), 1) AS passc_pg, ROUND(AVG(tackles_won), 1) AS tackw_pg,
                   ROUND(AVG(interceptions), 1) AS int_pg, ROUND(AVG(mistakes), 2) AS mis_pg
            FROM base
            LEFT JOIN (SELECT DISTINCT role, role_order FROM mart.rating_roles) ro USING (role)
            GROUP BY person_id, role)
        SELECT p.name AS player,
               tot.person_id, role, role_order, starts, rating, rating_adj,
               g, a, kp, passc_pg, tackw_pg, int_pg, mis_pg
        FROM tot
        LEFT JOIN mart.dim_person p USING (person_id)
        WHERE starts >= ?""", params + [min_starts]).df()
    return df
