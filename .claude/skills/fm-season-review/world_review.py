"""National + global half of the end-of-season review: transfers, continental cups, nations.

    uv run python .claude/skills/fm-season-review/world_review.py --season 2027
    uv run python .claude/skills/fm-season-review/world_review.py --season 2027 --db fm-frem.duckdb

`--season` is the END-YEAR (26/27 -> 2027). Reads the career's local store read-only
(`fm-<career>.duckdb`, `--db` to name another). The season must be complete in the store: its
window is 1 Jul (season-1) .. 30 Jun (season), and the coefficient move needs a snapshot at each
end.

Everything here is derived from the dbt models (`mart.*`, `site.*`, and `int.matches` for the
fixture list's stage keys). Two pieces are reconstructions the models do not hold, so each says
how it can go wrong:

* TRANSFERS come from mart.fact_transfer, which reads each move's fee from the career history.
  `season` there is the campaign a player moves FOR, so June signings belong to the NEXT
  season's market. Only clubs the save tracks in detail are covered, so totals are a floor.
* CONTINENTAL CUPS. The world fixture list has stage keys, not competition ids, for other
  clubs' continental matches, and the keys move every season. Competitions are rebuilt from the
  finals backwards: a late-season single-match cross-nation stage is a final, the two-legged
  stages its finalists played are its knockout rounds, and a group belongs to whichever
  competition's knockout rounds hold at least two of its clubs (the top two stay in the
  competition; a third-placed club drops a tier, which is why "any club" would be wrong). Tiers
  are ranked by the average club reputation of the group stage and named from EURO_TIERS.
* CLUB NATION is mart.dim_club's nation. Clubs from nations the save does not load have none;
  they are shown as '?<club>' and can be named by hand.
"""
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import careers as C  # noqa: E402


# The European club competitions by tier, from the save's own competition records:
# cid 256 'European Champions Cup' (reputation 200), 258 'EURO Cup' (150), 505 'EURO Cup II'
# (130). cid 257 'European Cup Winners Cup' is also in the table but dormant (never in the
# fixture list). The comp_man roll of honour (comp_cid 505: Sevilla beat Gladbach in 25/26)
# confirms the third tier is EC2 and matches this reconstruction.
EURO_TIERS = ("European Champions Cup", "EURO Cup", "EURO Cup II")


def connect(path):
    """Read-only connection to the store. dbt bakes the store's file name into every view as
    its catalog, so a locked store is copied to a temp DIRECTORY under the same file name."""
    path = os.path.abspath(path)
    try:
        return duckdb.connect(path, read_only=True)
    except duckdb.Error:
        if os.path.exists(path + ".wal"):
            sys.exit(f"{os.path.basename(path)} is being written (a .wal exists); try again "
                     "when the writer has finished")
        tmp = os.path.join(tempfile.mkdtemp(prefix="world_review_"), os.path.basename(path))
        shutil.copy2(path, tmp)
        return duckdb.connect(tmp, read_only=True)


def show(con, sql, title=None):
    if title:
        print(f"\n--- {title} ---")
    df = con.execute(sql).df()
    print(df.to_string(index=False) if len(df) else "(none)")
    return df


def phases(con, season):
    first, last = con.execute(
        "SELECT min(snapshot_date), max(snapshot_date) FROM site.snapshots WHERE season = ?",
        [season]).fetchone()
    if first is None:
        sys.exit(f"no snapshots for season {season}")
    return first, last


def home_nation(con):
    return con.execute(
        """SELECT n.name FROM site.our_teams t JOIN mart.dim_club c USING (club_tid)
           JOIN mart.dim_nation n USING (nation_id) WHERE t.is_managed""").fetchone()[0]


def setup(con, season, last):
    """cn: each club first team's nation and reputation at the season's last snapshot;
    cnc: each club's nation (transfers are club to club); wf: every world fixture of the
    season between two first teams, once per side."""
    lo, hi = f"{season - 1}-07-01", f"{season}-06-30"
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE cn AS
    SELECT t.team_tid AS club_tid, n.name AS nation, ts.reputation AS rep
    FROM mart.dim_team t
    JOIN mart.dim_club c USING (club_tid)
    LEFT JOIN mart.dim_nation n ON n.nation_id = c.nation_id
    LEFT JOIN mart.fact_team_snapshot ts
           ON ts.team_tid = t.team_tid AND ts.snapshot_date = DATE '{last}'
    WHERE t.team_type = 'first'""")
    con.execute("""
    CREATE OR REPLACE TEMP TABLE cnc AS
    SELECT c.club_tid, c.name AS club, n.name AS nation
    FROM mart.dim_club c LEFT JOIN mart.dim_nation n USING (nation_id)""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE wf AS
    SELECT tm.team_tid AS club_tid, tm.opponent_tid AS opp_tid, a.name AS club,
           b.name AS opponent, m.match_date AS date, tm.venue, tm.goals_for AS gf,
           tm.goals_against AS ga, tm.pens_for, tm.pens_against, m.stage_key, m.stage_index
    FROM mart.fact_team_match tm
    JOIN int.matches m USING (match_id)
    JOIN mart.dim_team a ON a.team_tid = tm.team_tid AND a.team_type = 'first'
    JOIN mart.dim_team b ON b.team_tid = tm.opponent_tid AND b.team_type = 'first'
    WHERE m.match_date BETWEEN DATE '{lo}' AND DATE '{hi}' AND tm.goals_for IS NOT NULL""")
    return lo, hi


def transfers(con, season, nation):
    # mart.fact_transfer: one row per permanent move or graduation, `season` = the campaign
    # the player moves FOR (a June signing counts toward next season). Fees in £. A
    # graduation (academy to senior side) is not a market move and is left out.
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE mv AS
    SELECT t.*, p.name,
           extract(year FROM age(coalesce(t.move_date, t.moved_by, DATE '{season}-06-30'),
                                 p.dob)) AS age,
           round(t.fee_gbp / 1e6, 2) AS fee_m,
           fc.club AS from_club, tc.club AS to_club,
           fc.nation AS from_nation, tc.nation AS to_nation,
           CASE WHEN coalesce(t.move_date, t.moved_by) IS NULL THEN 'undated'
                WHEN month(coalesce(t.move_date, t.moved_by)) BETWEEN 6 AND 9 THEN 'summer'
                ELSE 'winter' END AS transfer_window
    FROM mart.fact_transfer t
    JOIN mart.dim_person p USING (person_id)
    LEFT JOIN cnc fc ON fc.club_tid = t.from_club_tid
    LEFT JOIN cnc tc ON tc.club_tid = t.to_club_tid
    WHERE t.season = {season} AND t.transfer_type IN ('permanent', 'free')""")
    show(con, """SELECT count(*) AS transfers,
                        count(*) FILTER (WHERE transfer_type = 'permanent') AS paid,
                        count(*) FILTER (WHERE transfer_type = 'free') AS free,
                        round(sum(fee_gbp) / 1e6, 1) AS total_m,
                        count(*) FILTER (WHERE fee_gbp >= 10e6) AS over_10m FROM mv""",
         "WORLD TRANSFERS (£M)")
    show(con, """SELECT transfer_window, count(*) FILTER (WHERE transfer_type = 'permanent') AS paid,
                        round(sum(fee_gbp) / 1e6, 1) AS total_m FROM mv GROUP BY 1 ORDER BY 1""",
         "BY WINDOW (move date, else the first snapshot showing it)")
    show(con, """SELECT name, age, from_club, to_club, move_date, fee_m FROM mv
                 WHERE transfer_type = 'permanent' ORDER BY fee_gbp DESC LIMIT 10""",
         "TOP 10 DEALS")
    show(con, """SELECT to_club, round(sum(fee_gbp) / 1e6, 1) AS spent_m,
                        count(*) FILTER (WHERE transfer_type = 'permanent') AS n
                 FROM mv GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 6""", "BIGGEST SPENDERS")
    show(con, """SELECT from_club, round(sum(fee_gbp) / 1e6, 1) AS received_m
                 FROM mv GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 6""", "BIGGEST SELLERS")
    show(con, """WITH s AS (SELECT to_nation AS nation, sum(fee_gbp) AS spent FROM mv GROUP BY 1),
                      r AS (SELECT from_nation AS nation, sum(fee_gbp) AS received FROM mv GROUP BY 1)
                 SELECT nation, round(spent / 1e6, 1) AS spent_m, round(received / 1e6, 1) AS received_m,
                        round((coalesce(received, 0) - coalesce(spent, 0)) / 1e6, 1) AS net_m
                 FROM s FULL JOIN r USING (nation) WHERE nation IS NOT NULL
                 ORDER BY greatest(coalesce(spent, 0), coalesce(received, 0)) DESC LIMIT 8""",
         "BY LEAGUE NATION")
    show(con, f"""SELECT name, age, from_club, to_club, move_date, fee_m FROM mv
                  WHERE (to_nation = '{nation}' OR from_nation = '{nation}')
                    AND transfer_type = 'permanent'
                  ORDER BY fee_gbp DESC LIMIT 10""", f"{nation.upper()}: BIGGEST DEALS")
    show(con, f"""SELECT round(sum(fee_gbp) FILTER (WHERE to_nation = '{nation}') / 1e6, 2) AS spent_m,
                         round(sum(fee_gbp) FILTER (WHERE from_nation = '{nation}') / 1e6, 2) AS received_m,
                         round(sum(fee_gbp) FILTER (WHERE from_nation = '{nation}'
                               AND to_nation IS DISTINCT FROM '{nation}') / 1e6, 2) AS exports_m
                  FROM mv""", f"{nation.upper()}: MARKET TOTALS")
    show(con, """SELECT name, age, from_club, to_club, move_date, transfer_type, fee_kind, fee_m
                 FROM mv
                 WHERE from_club_tid IN (SELECT club_tid FROM site.our_teams)
                    OR to_club_tid IN (SELECT club_tid FROM site.our_teams)
                 ORDER BY move_date NULLS LAST""", "OUR LEDGER")


def continental(con, season, lo, hi):
    # Continental = competitive stages (stage_index is NULL for the friendly pool) that are
    # mostly cross-nation: a knockout draw can pair two clubs of one nation, so "all" would
    # drop the round. The majority is taken over matches where BOTH nations are known: a club
    # with no nation, counted as "different", drags domestic stages in, and counted as "same"
    # drops any group that holds such a club.
    con.execute("""
    CREATE OR REPLACE TEMP TABLE xf AS
    SELECT f.*, coalesce(a.nation, '?' || f.club) AS nation, b.nation AS opp_nation, a.rep
    FROM wf f
    LEFT JOIN cn a ON a.club_tid = f.club_tid
    LEFT JOIN cn b ON b.club_tid = f.opp_tid
    WHERE f.stage_index IS NOT NULL
      AND f.stage_key IN (
          SELECT f2.stage_key FROM wf f2
          LEFT JOIN cn a2 ON a2.club_tid = f2.club_tid
          LEFT JOIN cn b2 ON b2.club_tid = f2.opp_tid
          WHERE f2.stage_index IS NOT NULL
          GROUP BY 1
          HAVING count(*) FILTER (WHERE a2.nation <> b2.nation) * 2
                 >= count(*) FILTER (WHERE a2.nation IS NOT NULL AND b2.nation IS NOT NULL)
             AND count(*) FILTER (WHERE a2.nation <> b2.nation) > 0)""")
    # Stage shapes. A group is 3-4 clubs playing each other over months; everything after
    # the group phase that is not a group is a knockout leg. A final is a one-match stage
    # from May on.
    con.execute("""
    CREATE OR REPLACE TEMP TABLE st AS
    SELECT stage_key, count(DISTINCT club_tid) AS clubs, count(*) AS rows, min(date) AS d0,
           max(date) AS d1, string_agg(DISTINCT club_tid::VARCHAR, ',' ORDER BY club_tid::VARCHAR) AS club_set
    FROM xf GROUP BY 1""")
    con.execute("""
    CREATE OR REPLACE TEMP TABLE st AS
    SELECT *, clubs BETWEEN 3 AND 4 AND rows >= 6 AND d1 - d0 > 30 AS is_group FROM st""")
    groups_end = con.execute("SELECT max(d1) FROM st WHERE is_group").fetchone()[0]
    if groups_end is None:
        print("\n(no continental group stage in the fixture list for this season)")
        return
    finals = [r[0] for r in con.execute(f"""
        SELECT stage_key FROM st WHERE clubs = 2 AND rows = 2 AND d0 >= DATE '{season}-05-01'
        ORDER BY d0""").fetchall()]
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE ko AS
    SELECT * FROM st WHERE NOT is_group AND d0 > DATE '{groups_end}'""")
    con.execute("CREATE OR REPLACE TEMP TABLE comp_stage (comp INT, stage_key INT, kind VARCHAR)")
    con.executemany("INSERT INTO comp_stage VALUES (?, ?, 'KO')", [(i, k) for i, k in enumerate(finals)])
    # Grow each competition backwards: an unassigned knockout stage joins the competition
    # whose (later) stages its clubs go on to play. Winners progress within a competition,
    # so this converges in as many passes as there are rounds.
    while True:
        n = con.execute("""
        INSERT INTO comp_stage
        SELECT comp, stage_key, 'KO' FROM (
            SELECT cs.comp, k.stage_key, count(DISTINCT x1.club_tid) AS n
            FROM ko k JOIN xf x1 USING (stage_key)
            JOIN xf x2 ON x2.club_tid = x1.club_tid AND x2.date > x1.date
            JOIN comp_stage cs ON cs.stage_key = x2.stage_key
            WHERE k.stage_key NOT IN (SELECT stage_key FROM comp_stage)
            GROUP BY 1, 2)
        QUALIFY row_number() OVER (PARTITION BY stage_key ORDER BY n DESC) = 1
        RETURNING 1""").fetchall()
        if not n:
            break
    # A group belongs to the competition that keeps >= 2 of its clubs: the top two stay,
    # a third-placed club drops a tier.
    con.execute("""
    INSERT INTO comp_stage
    WITH kc AS (SELECT DISTINCT cs.comp, x.club_tid FROM comp_stage cs JOIN xf x USING (stage_key)),
    votes AS (SELECT g.stage_key, kc.comp, count(DISTINCT x.club_tid) AS n
              FROM st g JOIN xf x USING (stage_key) JOIN kc USING (club_tid)
              WHERE g.is_group GROUP BY 1, 2)
    SELECT comp, stage_key, 'Group' FROM votes WHERE n >= 2
    QUALIFY row_number() OVER (PARTITION BY stage_key ORDER BY n DESC) = 1""")
    # Tier by group-stage club reputation, named from EURO_TIERS.
    tiers = con.execute("""
        SELECT cs.comp, avg(x.rep) AS r FROM comp_stage cs JOIN xf x USING (stage_key)
        WHERE cs.kind = 'Group' GROUP BY 1 ORDER BY r DESC""").fetchall()
    label = {comp: EURO_TIERS[t] if t < len(EURO_TIERS) else f"tier {t + 1} cup"
             for t, (comp, _) in enumerate(tiers)}
    con.execute("CREATE OR REPLACE TEMP TABLE comp_label (comp INT, label VARCHAR)")
    con.executemany("INSERT INTO comp_label VALUES (?, ?)", list(label.items()))

    # Name a knockout round by how many clubs it holds; both legs of a tie are separate
    # stage keys with the same club set. Two 16-club rounds = a play-off then the R16.
    con.execute("""
    CREATE OR REPLACE TEMP TABLE rounds AS
    WITH r AS (SELECT cs.comp, st.club_set, st.clubs, min(st.d0) AS d
               FROM comp_stage cs JOIN st USING (stage_key) WHERE cs.kind = 'KO' GROUP BY 1, 2, 3)
    SELECT *, row_number() OVER (PARTITION BY comp, clubs ORDER BY d DESC) AS nth FROM r""")
    con.execute("""
    CREATE OR REPLACE TEMP TABLE ef AS
    SELECT l.label AS comp, cs.kind, x.*,
           CASE WHEN cs.kind = 'Group' THEN 'Group'
                WHEN r.nth > 1 THEN 'KO play-off'
                WHEN st.clubs = 2 THEN 'Final' WHEN st.clubs = 4 THEN 'SF'
                WHEN st.clubs = 8 THEN 'QF' WHEN st.clubs = 16 THEN 'R16'
                ELSE 'R' || st.clubs END AS rnd,
           CASE WHEN cs.kind = 'Group' THEN 0 ELSE 100 - st.clubs - r.nth END AS depth
    FROM comp_stage cs JOIN comp_label l USING (comp) JOIN st USING (stage_key)
    JOIN xf x USING (stage_key)
    LEFT JOIN rounds r ON r.comp = cs.comp AND r.club_set = st.club_set""")

    show(con, """SELECT comp, date, club, gf, ga, pens_for AS pf, pens_against AS pa, opponent
                 FROM ef WHERE rnd = 'Final' AND venue = 'H' ORDER BY date DESC""", "CONTINENTAL FINALS")
    show(con, """SELECT comp, rnd, club, nation FROM (
                   SELECT comp, club, nation, max(depth) AS d, arg_max(rnd, depth) AS rnd FROM ef GROUP BY 1, 2, 3)
                 WHERE rnd IN ('Final', 'SF', 'QF') ORDER BY comp, d DESC, club""", "LAST EIGHT AND BEYOND")
    show(con, """SELECT comp, count(DISTINCT stage_key) FILTER (WHERE kind = 'Group') AS groups,
                        count(DISTINCT club_tid) AS clubs FROM ef GROUP BY 1""",
         "SANITY: groups/clubs per competition (expect ~8 groups, ~32-40 clubs)")
    show(con, """SELECT nation, count(DISTINCT club_tid) AS clubs, count(*) AS p,
                        count(*) FILTER (WHERE gf > ga) AS w, count(*) FILTER (WHERE gf = ga) AS d,
                        count(*) FILTER (WHERE gf < ga) AS l, sum(gf) AS gf, sum(ga) AS ga,
                        round((3 * count(*) FILTER (WHERE gf > ga) + count(*) FILTER (WHERE gf = ga))
                              / count(*), 2) AS ppg
                 FROM ef GROUP BY 1 ORDER BY w DESC LIMIT 15""", "NATION RECORDS (group stage on)")
    show(con, """WITH g AS (SELECT comp, club_tid, nation, max(depth) AS d FROM ef GROUP BY 1, 2, 3)
                 SELECT comp, nation, count(*) AS clubs_in, count(*) FILTER (WHERE d >= 1) AS past_groups
                 FROM g GROUP BY 1, 2 HAVING count(*) >= 2 ORDER BY 1, 3 DESC""", "CLUBS THROUGH THE GROUPS")
    show(con, """SELECT comp, rnd, date, club, gf, ga, opponent FROM ef WHERE venue = 'H'
                 ORDER BY abs(gf - ga) DESC, gf + ga DESC LIMIT 5""", "BIGGEST SCORELINES")
    return True


def home_nation_europe(con, nation, lo, hi):
    show(con, f"""SELECT f.club, f.date, f.venue AS v, f.opponent, f.gf, f.ga,
                         f.pens_for AS pf, f.pens_against AS pa, coalesce(e.comp, 'qualifier') AS comp,
                         coalesce(e.rnd, '') AS rnd
                  FROM xf f LEFT JOIN (SELECT DISTINCT stage_key, comp, rnd FROM ef) e USING (stage_key)
                  WHERE f.nation = '{nation}' ORDER BY f.club, f.date""",
         f"{nation.upper()} IN EUROPE (every cross-nation tie, qualifiers included)")


def coefficients(con, season):
    # site.nations: coefficient_history is oldest first, its last entry the season in progress;
    # coefficient_season is the newest COMPLETED one (the second to last entry) and
    # uefa_rank the 5-season ranking. "now" is the latest snapshot on which season S is the
    # newest completed season, "before" the latest on which S-1 was.
    show(con, f"""
    WITH now AS (
        SELECT name, coefficient_history[-2] AS season_coef,
               list_max(coefficient_history[1:-3]) AS best_prev, uefa_rank, coefficient_5
        FROM site.nations WHERE is_uefa AND coefficient_season = {season}
        QUALIFY snapshot_date = max(snapshot_date) OVER ()),
    before AS (
        SELECT name, uefa_rank FROM site.nations WHERE is_uefa AND coefficient_season = {season - 1}
        QUALIFY snapshot_date = max(snapshot_date) OVER ())
    SELECT now.name AS nation, round(season_coef, 2) AS season_coef,
           rank() OVER (ORDER BY season_coef DESC) AS season_rank,
           round(best_prev, 2) AS best_prev, now.uefa_rank AS rank_5yr_now,
           before.uefa_rank AS rank_5yr_before
    FROM now LEFT JOIN before USING (name) ORDER BY season_coef DESC LIMIT 20""",
         "UEFA NATION COEFFICIENTS (season + 5-yr rank move)")


def domestic(con, season, last, nation, lo, hi):
    show(con, f"""
    SELECT f.stage_key, f.date, f.club, f.gf, f.ga, f.pens_for AS pf, f.pens_against AS pa, f.opponent
    FROM wf f
    JOIN cn a ON a.club_tid = f.club_tid JOIN cn b ON b.club_tid = f.opp_tid
    WHERE a.nation = '{nation}' AND b.nation = '{nation}' AND f.venue = 'H'
      AND f.date >= DATE '{season}-03-01'
      AND f.stage_key IN (SELECT stage_key FROM wf GROUP BY 1 HAVING count(*) <= 8)
    ORDER BY f.date""",
         f"{nation.upper()} CUP CANDIDATES (the final is the lone match after a 2-club/2-leg semi stage)")
    show(con, f"""
    WITH top AS (SELECT ts.team_tid, l.name AS league_name
                 FROM mart.fact_team_snapshot ts
                 JOIN site.leagues l ON l.cid = ts.league_cid AND l.snapshot_date = ts.snapshot_date
                 WHERE ts.snapshot_date = DATE '{last}' AND l.tier = 1
                   AND l.nation IN ('{nation}', 'England', 'Germany', 'Spain', 'Italy', 'France')),
    gk AS (SELECT person_id FROM mart.fact_player_snapshot
           WHERE snapshot_date = DATE '{last}' AND is_goalkeeper)
    SELECT top.league_name, p.name, extract(year FROM age(DATE '{season}-06-30', p.dob)) AS age,
           t.name AS club, s.apps, s.goals
    FROM mart.fact_player_season s
    JOIN top USING (team_tid)
    JOIN mart.dim_person p USING (person_id)
    JOIN mart.dim_team t USING (team_tid)
    WHERE s.season = {season} AND s.person_id NOT IN (SELECT person_id FROM gk)
    QUALIFY row_number() OVER (PARTITION BY top.league_name ORDER BY s.goals DESC) <= 3
    ORDER BY top.league_name, s.goals DESC""",
         "TOP SCORERS, top divisions (all comps; GKs excluded, their 'goals' are conceded)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True, help="END-YEAR: 26/27 -> 2027")
    ap.add_argument("--career")
    ap.add_argument("--db", help="store path (default: the career's fm-<career>.duckdb)")
    ap.add_argument("--nation", help="home nation for the national section (default: our club's)")
    a = ap.parse_args()
    db = a.db or str(REPO / C.resolve_career(a.career or os.environ.get("FM_CAREER")).db)
    con = connect(db)
    first, last = phases(con, a.season)
    nation = a.nation or home_nation(con)
    print(f"=== {a.season - 1}/{str(a.season)[2:]} WORLD REVIEW · snapshots {first} -> {last} · home nation {nation} ===")
    lo, hi = setup(con, a.season, last)
    if continental(con, a.season, lo, hi):
        home_nation_europe(con, nation, lo, hi)
    coefficients(con, a.season)
    domestic(con, a.season, last, nation, lo, hi)
    transfers(con, a.season, nation)


if __name__ == "__main__":
    main()
