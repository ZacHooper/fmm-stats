"""National + global half of the end-of-season review: transfers, continental cups, nations.

    uv run python .claude/skills/fm-season-review/world_review.py --season 2027
    uv run python .claude/skills/fm-season-review/world_review.py --season 2027 --db fm-frem.duckdb

`--season` is the END-YEAR (26/27 -> 2027). Reads the store through fmstats.store, so with no
--db it uses the R2 published copy. The season must be complete in the store: its window is
1 Jul (season-1) .. 30 Jun (season), and the transfer diff needs a snapshot at each end.

Everything here is derived from the mart. Two pieces are reconstructions the mart does not
model, so each says how it can go wrong:

* TRANSFERS come from mart.transfers (fmstats/mart.py), which reads each move's fee from
  the career history. `season` there is the campaign a player moves FOR, so June signings
  belong to the NEXT season's market. Only clubs the save tracks in detail are covered, so
  totals are a floor.
* CONTINENTAL CUPS. The fixture list has stage keys, not competition ids, and the keys move
  every season. Competitions are rebuilt from the finals backwards: a late-season
  single-match cross-nation stage is a final, the two-legged stages its finalists played
  are its knockout rounds, and a group belongs to whichever competition's knockout rounds
  hold at least two of its clubs (the top two stay in the competition; a third-placed club
  drops a tier, which is why "any club" would be wrong). Tiers are ranked by the average club
  reputation of the group stage and named from EURO_TIERS.
* CLUB NATION comes from mart.clubs at the last snapshot. Clubs from nations the save does
  not load have no nation; they are shown as '?<club>' and can be named by hand.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fmstats.store import open_store  # noqa: E402


# The European club competitions by tier, from the save's own competition records (read with
# fmparser.clubs_comps.comp_detail): cid 256 'European Champions Cup' (reputation 200),
# 258 'EURO Cup' (150), 505 'EURO Cup II' (130). cid 257 'European Cup Winners Cup' is also
# in the table but dormant (level 100, never in the fixture list). The store's
# staging.competitions only carries competitions with a match in OUR data, so 505 is absent
# from it and cannot be looked up there. The comp_man roll of honour (comp_cid 505: Sevilla
# beat Gladbach in 25/26) confirms the third tier is EC2 and matches this reconstruction.
EURO_TIERS = ("European Champions Cup", "EURO Cup", "EURO Cup II")


def show(con, sql, title=None):
    if title:
        print(f"\n--- {title} ---")
    df = con.execute(sql).df()
    print(df.to_string(index=False) if len(df) else "(none)")
    return df


def phases(con, season):
    first, last = con.execute(
        "SELECT min(phase), max(phase) FROM mart.snapshots WHERE season = ?", [season]
    ).fetchone()
    if first is None:
        sys.exit(f"no snapshots for season {season}")
    return first, last


def home_nation(con):
    return con.execute(
        """SELECT c.nation FROM mart.clubs c JOIN mart.managed_club m USING (club_tid)
           ORDER BY c.phase DESC LIMIT 1"""
    ).fetchone()[0]


def transfers(con, season, nation):
    # mart.transfers: one row per club move, `season` = the campaign the player moves FOR
    # (a June signing counts toward next season). Fees in £; see the view's comment in
    # fmstats/mart.py for how they are read and what fee_type means.
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE mv AS
    SELECT t.*, round(t.fee_gbp / 1e6, 2) AS fee_m,
           fc.nation AS from_nation, tc.nation AS to_nation
    FROM mart.transfers t
    LEFT JOIN cn fc ON fc.club_tid = t.from_club_tid
    LEFT JOIN cn tc ON tc.club_tid = t.to_club_tid
    WHERE t.season = {season} AND t.move_type <> 'internal'
    """)
    show(con, """SELECT count(*) FILTER (WHERE move_type = 'transfer') AS transfers,
                        count(*) FILTER (WHERE fee_type = 'fee') AS paid,
                        count(*) FILTER (WHERE fee_type = 'free') AS free,
                        round(sum(fee_gbp) / 1e6, 1) AS total_m,
                        count(*) FILTER (WHERE fee_gbp >= 10e6) AS over_10m FROM mv""",
         "WORLD TRANSFERS (£M)")
    show(con, """SELECT transfer_window, count(*) FILTER (WHERE fee_type = 'fee') AS paid,
                        round(sum(fee_gbp) / 1e6, 1) AS total_m FROM mv GROUP BY 1 ORDER BY 1""",
         "BY WINDOW")
    show(con, """SELECT name, age, from_club, to_club, move_date, fee_m FROM mv
                 WHERE fee_type = 'fee' ORDER BY fee_gbp DESC LIMIT 10""", "TOP 10 DEALS")
    show(con, """SELECT to_club, round(sum(fee_gbp) / 1e6, 1) AS spent_m,
                        count(*) FILTER (WHERE fee_type = 'fee') AS n
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
                  WHERE (to_nation = '{nation}' OR from_nation = '{nation}') AND fee_type = 'fee'
                  ORDER BY fee_gbp DESC LIMIT 10""", f"{nation.upper()}: BIGGEST DEALS")
    show(con, f"""SELECT round(sum(fee_gbp) FILTER (WHERE to_nation = '{nation}') / 1e6, 2) AS spent_m,
                         round(sum(fee_gbp) FILTER (WHERE from_nation = '{nation}') / 1e6, 2) AS received_m,
                         round(sum(fee_gbp) FILTER (WHERE from_nation = '{nation}'
                               AND to_nation IS DISTINCT FROM '{nation}') / 1e6, 2) AS exports_m
                  FROM mv""", f"{nation.upper()}: MARKET TOTALS")
    show(con, """SELECT name, age, from_club, to_club, move_date, move_type, fee_type, fee_m FROM mv
                 WHERE from_club_tid IN (SELECT club_tid FROM mart.our_clubs)
                    OR to_club_tid IN (SELECT club_tid FROM mart.our_clubs)
                 ORDER BY move_date NULLS LAST""", "OUR LEDGER")


def continental(con, season, last):
    lo, hi = f"{season - 1}-07-01", f"{season}-06-30"
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE cn AS
    SELECT club_tid, any_value(nation) AS nation, any_value(reputation) AS rep
    FROM mart.clubs WHERE phase = '{last}' GROUP BY 1""")
    # Continental = non-friendly stages (stage_index 255 is the friendly pool) that are mostly
    # cross-nation: a knockout draw can pair two clubs of one nation, so "all" would drop the round.
    # The majority is taken over matches where BOTH nations are known: a club from an
    # unloaded nation has none, and counting NULL as "different" drags domestic stages in,
    # while counting it as "same" drops any group that holds such a club.
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE xf AS
    SELECT f.*, coalesce(a.nation, '?' || f.club) AS nation, b.nation AS opp_nation, a.rep
    FROM mart.world_club_fixtures f
    LEFT JOIN cn a ON a.club_tid = f.club_tid
    LEFT JOIN cn b ON b.club_tid = f.opp_tid
    WHERE f.date BETWEEN DATE '{lo}' AND DATE '{hi}' AND f.stage_index <> 255
      AND f.stage_key IN (
          SELECT f2.stage_key FROM mart.world_club_fixtures f2
          LEFT JOIN cn a2 ON a2.club_tid = f2.club_tid
          LEFT JOIN cn b2 ON b2.club_tid = f2.opp_tid
          WHERE f2.date BETWEEN DATE '{lo}' AND DATE '{hi}' AND f2.stage_index <> 255
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
    return lo, hi


def home_nation_europe(con, nation, lo, hi):
    show(con, f"""SELECT f.club, f.date, f.venue AS v, f.opponent, f.gf, f.ga,
                         f.pens_for AS pf, f.pens_against AS pa, coalesce(e.comp, 'qualifier') AS comp,
                         coalesce(e.rnd, '') AS rnd
                  FROM xf f LEFT JOIN (SELECT DISTINCT stage_key, comp, rnd FROM ef) e USING (stage_key)
                  WHERE f.nation = '{nation}' ORDER BY f.club, f.date""",
         f"{nation.upper()} IN EUROPE (every cross-nation tie, qualifiers included)")


def coefficients(con, first, last):
    # seq 0..9 is a rolling ten-season history, oldest first; seq 9 at the season's last
    # snapshot is the season just finished. The 5-year ranking is the sum of seq 5..9.
    show(con, f"""
    WITH n AS (SELECT nation, sum(coefficient) FILTER (WHERE seq = 9) AS season,
                      max(coefficient) FILTER (WHERE seq BETWEEN 0 AND 8) AS best_prev,
                      sum(coefficient) FILTER (WHERE seq BETWEEN 5 AND 9) AS five
               FROM mart.nation_coefficients WHERE phase = '{last}' GROUP BY 1),
    o AS (SELECT nation, sum(coefficient) FILTER (WHERE seq BETWEEN 5 AND 9) AS five_before
          FROM mart.nation_coefficients WHERE phase = '{first}' GROUP BY 1)
    SELECT n.nation, round(season, 2) AS season_coef, rank() OVER (ORDER BY season DESC) AS season_rank,
           round(best_prev, 2) AS best_prev_9yrs, rank() OVER (ORDER BY five DESC) AS rank_5yr_now,
           rank() OVER (ORDER BY five_before DESC) AS rank_5yr_before
    FROM n JOIN o USING (nation) ORDER BY season DESC LIMIT 20""", "NATION COEFFICIENTS (season + 5-yr rank move)")


def domestic(con, season, last, nation, lo, hi):
    show(con, f"""
    SELECT f.stage_key, f.date, f.club, f.gf, f.ga, f.pens_for AS pf, f.pens_against AS pa, f.opponent
    FROM mart.world_club_fixtures f
    JOIN cn a ON a.club_tid = f.club_tid JOIN cn b ON b.club_tid = f.opp_tid
    WHERE a.nation = '{nation}' AND b.nation = '{nation}' AND f.venue = 'H'
      AND f.date BETWEEN DATE '{season}-03-01' AND DATE '{hi}'
      AND f.stage_key IN (SELECT stage_key FROM mart.world_club_fixtures
                          WHERE date BETWEEN DATE '{lo}' AND DATE '{hi}' GROUP BY 1 HAVING count(*) <= 8)
    ORDER BY f.date""",
         f"{nation.upper()} CUP CANDIDATES (the final is the lone match after a 2-club/2-leg semi stage)")
    show(con, f"""
    WITH top AS (SELECT DISTINCT club_tid, league_name FROM mart.clubs c
                 JOIN mart.leagues l ON l.cid = c.league_cid AND l.phase = c.phase
                 WHERE c.phase = '{last}' AND l.tier = 1
                   AND c.nation IN ('{nation}', 'England', 'Germany', 'Spain', 'Italy', 'France')),
    s AS (SELECT person_id, any_value(name) AS name, max(is_gk) AS gk, any_value(age) AS age
          FROM mart.player_snapshots WHERE phase = '{last}' GROUP BY 1),
    h AS (SELECT c.person_id, c.club, c.club_tid, c.apps, c.goals FROM mart.player_career_seasons c
          WHERE c.phase = '{last}' AND c.end_year = {season})
    SELECT league_name, name, age, club, apps, goals FROM h JOIN top USING (club_tid) JOIN s USING (person_id)
    WHERE s.gk = 0
    QUALIFY row_number() OVER (PARTITION BY league_name ORDER BY goals DESC) <= 3
    ORDER BY league_name, goals DESC""",
         "TOP SCORERS, top divisions (all comps; GKs excluded, their 'goals' are conceded)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True, help="END-YEAR: 26/27 -> 2027")
    ap.add_argument("--career")
    ap.add_argument("--db")
    ap.add_argument("--nation", help="home nation for the national section (default: our club's)")
    a = ap.parse_args()
    st = open_store(career=a.career, db=a.db)
    con = st.con
    first, last = phases(con, a.season)
    nation = a.nation or home_nation(con)
    print(f"=== {a.season - 1}/{str(a.season)[2:]} WORLD REVIEW · snapshots {first} -> {last} · home nation {nation} ===")
    r = continental(con, a.season, last)
    if r:
        home_nation_europe(con, nation, *r)
    coefficients(con, first, last)
    lo, hi = f"{a.season - 1}-07-01", f"{a.season}-06-30"
    domestic(con, a.season, last, nation, lo, hi)
    transfers(con, a.season, nation)


if __name__ == "__main__":
    main()
