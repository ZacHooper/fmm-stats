"""Database helpers for the site export, including the loan outlook (`build_loans`).

Reads solely from DuckDB (via fmstats.dbopen); no dependency on the retired Streamlit dashboard.
"""
import bisect

import pandas as pd

# A position counts as one a player can be picked at from this familiarity up (the house floor).
DEFAULT_MIN_FAM = 15
# Our division plus the three below it: every division a loan destination is drawn from.
LOAN_TIERS = 4

# Starting slots per position for each formation an AI manager can prefer (the names in
# mart.club_managers.formation_preferred_name). "Would he start there" is answered against the
# host club's own shape, so a second striker starts at a 4-4-2 club and not at a 4-2-3-1 one.
# In a back-four 4-2-3-1 the two deep midfielders decode as MC (see mart.rating_roles), and a
# back five's wide men are DML/DMR.
FORMATION_SLOTS = {
    "4-4-2":         {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "ML": 1, "MC": 2, "MR": 1, "ST": 2},
    "4-4-2 Diamond": {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "DMC": 1, "MC": 2, "AMC": 1, "ST": 2},
    "4-1-2-2-1":     {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "DMC": 1, "MC": 2, "AML": 1, "AMR": 1,
                      "ST": 1},
    "4-1-4-1":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "DMC": 1, "ML": 1, "MC": 2, "MR": 1,
                      "ST": 1},
    "4-2-3-1":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "MC": 2, "AML": 1, "AMC": 1, "AMR": 1,
                      "ST": 1},
    "4-2-2-2":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "MC": 2, "AML": 1, "AMR": 1, "ST": 2},
    "4-3-1-2":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "MC": 3, "AMC": 1, "ST": 2},
    "4-3-3":         {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "MC": 3, "AML": 1, "AMR": 1, "ST": 1},
    "4-4-1-1":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "ML": 1, "MC": 2, "MR": 1, "AMC": 1,
                      "ST": 1},
    "4-3-2-1":       {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "MC": 3, "AMC": 2, "ST": 1},
    "4-5-1":         {"GK": 1, "DL": 1, "DC": 2, "DR": 1, "ML": 1, "MC": 3, "MR": 1, "ST": 1},
    "5-1-2-2":       {"GK": 1, "DML": 1, "DC": 3, "DMR": 1, "DMC": 1, "MC": 2, "ST": 2},
    "5-2-1-2":       {"GK": 1, "DML": 1, "DC": 3, "DMR": 1, "MC": 2, "AMC": 1, "ST": 2},
    "5-2-2-1":       {"GK": 1, "DML": 1, "DC": 3, "DMR": 1, "MC": 2, "AML": 1, "AMR": 1, "ST": 1},
    "5-3-2":         {"GK": 1, "DML": 1, "DC": 3, "DMR": 1, "MC": 3, "ST": 2},
}
# A club whose manager record did not parse is read as the most common shape in the ladder.
FALLBACK_FORMATION = "4-2-3-1"


def _json_clean(o):
    """Recursively make a value JSON-safe: numpy scalars -> python, NaN -> None."""
    if isinstance(o, dict):
        return {k: _json_clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_clean(v) for v in o]
    if hasattr(o, "item"):          # numpy scalar
        o = o.item()
    if isinstance(o, float) and o != o:   # NaN
        return None
    return o


class ExportDB:
    def __init__(self, con, car):
        self.con = con
        self.car = car
        self.MANAGED_CLUB_TID = car.managed_tid
        self.RESERVE_CLUB_TID = car.reserve_tid
        self.OUR_CLUBS = (car.managed_tid, car.reserve_tid)
        self._json_clean = _json_clean

    def q(self, sql, params=None):
        if params is not None:
            return self.con.execute(sql, params).df()
        return self.con.execute(sql).df()

    def latest_snapshot(self):
        row = self.con.execute("""
            SELECT season, phase FROM mart.snapshots
            ORDER BY snap_ix DESC LIMIT 1
        """).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def config(self):
        try:
            return dict(self.con.execute("SELECT key, value FROM mart.app_config").fetchall())
        except Exception:
            return {}

    def methods(self):
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT method FROM mart.role_weights ORDER BY method"
        ).fetchall()]

    def familiarity_params(self):
        cfg = self.config()
        curve = cfg.get("familiarity_curve", "linear_floor")
        try:
            floor = float(cfg.get("familiarity_floor", 0.50))
        except (TypeError, ValueError):
            floor = 0.50
        return curve, floor

    def labels_df(self):
        return self.con.execute("""
            SELECT season, phase, label FROM mart.snapshots ORDER BY snap_ix
        """).df()

    def comparison_leagues(self, season, phase, limit=4):
        df = self.q("""SELECT cid, name FROM mart.comparison_ladder
                       WHERE season=? AND phase=? ORDER BY ladder_rank LIMIT ?""",
                    [season, phase, limit])
        if df.empty:
            return []
        return [(int(r.cid), r.name) for r in df.itertuples(index=False)]

    def build_loans(self, season, phase, min_fam=DEFAULT_MIN_FAM):
        """Where each owned player would play on loan: for every position he is familiar at,
        his Level %ile in each division of the ladder, and at each club in it, how many of that
        club's own players at the position are ahead of him.

        AI managers pick their XI largely on ability, so ability is the ordering throughout —
        which is why this is computed here, from `ca`, and ships only percentiles and ranks.

        - `lvl` is his percentile against everyone in that division with the position, exactly
          as mart.player_position_levels computes `level_league`: the share of the pool below
          him, himself excluded. In his own division it equals the Level %ile the Squad table
          shows.
        - A club's `line` is the same percentile for the weakest player it would START at the
          position — the slot-th best of its own natural players there (familiarity >=
          min_fam), with slots from its manager's preferred formation. He starts there iff he
          is ahead of that player, i.e. `rank <= slots`. `line` is null when the club has fewer
          natural players than slots: a natural player of ours walks into the open slot.
        - Club membership is the spell model (mart.player_spells), with a loanee counted at the
          club he is on loan to — never a raw club_tid, which can keep a lapsed loanee on a
          club's books indefinitely.
        """
        ladder = self.comparison_leagues(season, phase, limit=LOAN_TIERS)
        if not ladder or ladder[0][0] is None:
            return {"error": "No club->league membership for this snapshot, so there is no "
                             "division ladder to place anyone in."}
        cids = [c for c, _ in ladder]
        cph = ",".join("?" * len(cids))
        ours_ph = ",".join("?" * len(self.OUR_CLUBS))

        # The Level %ile pool: every player with the position in a ladder division, partitioned
        # the way mart.player_position_levels partitions it (any familiarity, raw club_tid).
        pool = self.q(f"""
            SELECT l.tid, l.position, l.league_cid, p.ca
            FROM mart.player_position_levels l
            JOIN staging.players p USING (season, phase, tid)
            WHERE l.season = ? AND l.phase = ? AND l.league_cid IN ({cph})""",
                      [season, phase, *cids])
        scale, in_pool = {}, set()
        for (cid, pos), g in pool.groupby(["league_cid", "position"]):
            scale[(int(cid), pos)] = sorted(float(v) for v in g["ca"])
        for t, pos, cid in zip(pool["tid"], pool["position"], pool["league_cid"]):
            in_pool.add((int(t), pos, int(cid)))

        def pctile(cid, pos, ca, tid):
            arr = scale.get((cid, pos))
            if not arr:
                return None, 0
            n = len(arr) - (1 if (tid, pos, cid) in in_pool else 0)
            if n <= 0:
                return None, 0
            return round(100 * bisect.bisect_left(arr, ca) / n), n

        # Who is at each ladder club, and who of them can be picked at each position.
        roster = self.q(f"""
            WITH d AS (SELECT phase_date FROM mart.snapshots WHERE season = ? AND phase = ?),
            here AS (
                SELECT s.tid,
                       COALESCE(max(s.club_tid) FILTER (WHERE s.spell_type = 'loan_in'),
                                max(s.club_tid)) AS club_tid
                FROM mart.player_spells s, d
                WHERE s.spell_type IN ('at_club', 'loan_in')
                  AND d.phase_date >= s.valid_from
                  AND (s.valid_to IS NULL OR d.phase_date <= s.valid_to)
                GROUP BY s.tid
            )
            SELECT here.tid, here.club_tid, cl.league_cid, pp.position, p.ca
            FROM here
            JOIN mart.club_leagues cl
              ON (cl.season, cl.phase, cl.club_tid) = (?, ?, here.club_tid)
            JOIN staging.players p
              ON (p.season, p.phase, p.tid) = (?, ?, here.tid)
            JOIN staging.player_positions pp
              ON (pp.season, pp.phase, pp.tid) = (?, ?, here.tid)
            WHERE cl.league_cid IN ({cph}) AND NOT p.is_staff AND p.ca IS NOT NULL
              AND pp.familiarity >= ?""",
                        [season, phase, season, phase, season, phase, season, phase,
                         *cids, int(min_fam)])
        # Per (club, position): the club's natural players there, best first, as (-ca, tid).
        natural = {}
        for (club, pos), g in roster.groupby(["club_tid", "position"]):
            natural[(int(club), pos)] = sorted(zip((-float(v) for v in g["ca"]),
                                                   (int(t) for t in g["tid"])))

        clubs = self.q(f"""
            SELECT cl.club_tid, cl.league_cid, m.formation_preferred_name AS formation
            FROM mart.club_leagues cl
            LEFT JOIN mart.club_managers m
              ON (m.season, m.phase, m.club_tid) = (cl.season, cl.phase, cl.club_tid)
            WHERE cl.season = ? AND cl.phase = ? AND cl.league_cid IN ({cph})
              AND cl.club_tid NOT IN ({ours_ph})
            ORDER BY cl.league_cid, cl.club_tid""",
                       [season, phase, *cids, *self.OUR_CLUBS])
        # A formation missing from the manager record, or one FORMATION_SLOTS does not know,
        # ships as null and is read as FALLBACK_FORMATION.
        shape = {int(t): (f if isinstance(f, str) and f in FORMATION_SLOTS else None)
                 for t, f in zip(clubs["club_tid"], clubs["formation"])}
        by_league = {c: [] for c in cids}
        for t, cid in zip(clubs["club_tid"], clubs["league_cid"]):
            by_league[int(cid)].append(
                (int(t), FORMATION_SLOTS[shape[int(t)] or FALLBACK_FORMATION]))

        # Owned players: ours on the date, minus anyone here on loan, plus anyone out on loan.
        owned = self.q("""
            WITH d AS (SELECT phase_date FROM mart.snapshots WHERE season = ? AND phase = ?)
            SELECT DISTINCT s.tid, NULL::INTEGER AS loaned_to FROM mart.squad_on(?) s
            WHERE s.spell_type = 'at_club'
              AND s.tid NOT IN (SELECT tid FROM mart.squad_on(?) WHERE spell_type = 'loan_in')
              AND s.tid NOT IN (SELECT o.tid FROM mart.loan_out_spells o, d
                                WHERE d.phase_date BETWEEN o.valid_from AND o.valid_to)
            UNION ALL
            SELECT DISTINCT o.tid, o.club_tid FROM mart.loan_out_spells o, d
            WHERE d.phase_date BETWEEN o.valid_from AND o.valid_to""",
                        [season, phase, phase, phase])
        loaned_to = {int(t): (None if pd.isna(c) else int(c))
                     for t, c in zip(owned["tid"], owned["loaned_to"])}
        tids = sorted(loaned_to)
        if not tids:
            return {"error": "No owned players in this snapshot."}
        tph = ",".join("?" * len(tids))
        mine = self.q(f"""
            SELECT pp.tid, pp.position, pp.familiarity, p.ca
            FROM staging.player_positions pp
            JOIN staging.players p USING (season, phase, tid)
            WHERE pp.season = ? AND pp.phase = ? AND pp.tid IN ({tph})
              AND pp.familiarity >= ? AND p.ca IS NOT NULL
            ORDER BY pp.tid, pp.familiarity DESC, pp.position""",
                      [season, phase, *tids, int(min_fam)])

        players = {}
        for r in mine.itertuples():
            tid, pos, ca = int(r.tid), r.position, float(r.ca)
            rows = []
            for cid in cids:
                lvl, n = pctile(cid, pos, ca, tid)
                hosts = []
                for club, slots in by_league[cid]:
                    k = slots.get(pos, 0)
                    if not k:
                        continue        # his position is not in this club's shape
                    others = [x for x in natural.get((club, pos), []) if x[1] != tid]
                    rank = 1 + sum(1 for neg, _ in others if -neg >= ca)
                    line = None
                    if len(others) >= k:
                        neg, starter = others[k - 1]
                        line = pctile(cid, pos, -neg, starter)[0]
                    hosts.append([club, rank, k, line])
                rows.append([cid, lvl, n, hosts])
            entry = players.setdefault(str(tid), {"loaned_to": loaned_to.get(tid),
                                                  "positions": {}})
            entry["positions"][pos] = rows

        return {"ladder": ladder, "players": players,
                "formations": shape,
                "fallback_formation": FALLBACK_FORMATION}
