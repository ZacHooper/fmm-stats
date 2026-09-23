"""Standalone database and positions review helpers for site data export.

Decoupled from the retired Streamlit dashboard so scripts/export_data.py has zero dependencies
on dashboard/ or streamlit. Reads solely from DuckDB (via fmstats.dbopen).
"""
import datetime
import duckdb
import numpy as np
import pandas as pd

DEFAULT_SLOTS = {"GK": 1, "LB": 1, "CB": 2, "RB": 1, "DM": 1, "CM": 2,
                 "AML": 1, "AMC": 1, "AMR": 1, "ST": 1}
ROLE_ORDER = ["GK", "LB", "CB", "RB", "DM", "CM", "AML", "AMC", "AMR", "ST"]
MIN_HOST_SQUAD = 3
DEFAULT_MIN_FAM = 15


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


def read_player(row, slots, primary, starts_at, lower):
    depth, age = int(row["depth"]), row["age"]
    pct = row["div_pct"]
    plays_lower = any(starts_at.get((int(row["tid"]), row["position"], c), 0) > 0
                      for c, _ in lower)
    home = primary.get(int(row["tid"]))
    if home and home != row["role"]:
        return (f"Keep — starter here, primary {home}" if depth <= slots
                else f"Cover only — primary {home}")
    if depth <= slots:
        if pd.notna(age) and age <= 19:
            return "Keep — starter (young; ranks low on CURRENT ability)"
        if pd.notna(pct) and pct < 40:
            return "Keep — starter, but upgrade target"
        return "Keep — starter"
    if depth == slots + 1:
        return "Keep — cover"
    if pd.notna(age) and age < 24 and plays_lower:
        return "Loan out"
    if pd.notna(age) and age <= 18:
        return "Keep — reserves (too young to judge)"
    if pd.notna(age) and age >= 23 and pd.notna(pct) and pct < 33:
        return "Sell / release"
    if not plays_lower and pd.notna(age) and age >= 20:
        return "Sell / release — starts nowhere below us"
    return "Surplus — loan or sell"


def role_read(g, n_slots):
    best = g.iloc[0]
    pct = best["div_pct"]
    young = pd.notna(best["age"]) and best["age"] <= 19
    if pd.notna(pct) and pct < 40 and young:
        return "Prospect starting — cover him"
    if pd.notna(pct) and pct < 40:
        return "Needs a starter"
    if len(g) <= n_slots:
        return "Thin — no cover"
    if len(g) > n_slots + 2:
        return "Stocked — surplus to move on"
    return "Settled"


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

    def player_label(self, tid, name):
        if isinstance(name, str) and name:
            return name
        return f"#{int(tid)}"

    def by_surname(self, df, name_col="label"):
        def surname_key(label):
            if not isinstance(label, str) or not label or label.startswith("#"):
                return ("~~~", label or "")
            parts = label.split()
            return (parts[-1].lower(), " ".join(parts[:-1]).lower())
        return df.assign(_sk=df[name_col].map(surname_key)).sort_values("_sk").drop(columns="_sk")

    def squad(self, season, phase):
        ph = ",".join("?" * len(self.OUR_CLUBS))
        df = self.q(f"""
            WITH loaned_out AS (
                SELECT DISTINCT s.tid, s.name
                FROM mart.loan_out_spells s
                JOIN (SELECT phase_date FROM mart.snapshots WHERE season=? AND phase=?) sn
                  ON sn.phase_date BETWEEN s.valid_from AND s.valid_to
            ),
            present AS (
                SELECT tid, any_value(name) AS name, max(club_tid) AS club_tid
                FROM mart.snapshot_squad
                WHERE season=? AND phase=? AND club_tid IN ({ph})
                GROUP BY tid
            )
            SELECT tid, name, ? AS club_tid, 'Loan' AS status FROM loaned_out
            UNION ALL
            SELECT tid, name, club_tid,
                   CASE WHEN club_tid = ? THEN 'Reserve' ELSE 'First team' END AS status
            FROM present WHERE tid NOT IN (SELECT tid FROM loaned_out)
            """, [season, phase, season, phase, *self.OUR_CLUBS, self.RESERVE_CLUB_TID, self.RESERVE_CLUB_TID])
        df["label"] = df.apply(lambda r: self.player_label(r.tid, r["name"]), axis=1)
        return self.by_surname(df, "label").reset_index(drop=True)

    def player_bio(self, season, phase, tids):
        tids = [int(t) for t in tids if t is not None]
        if not tids:
            return {}
        ph = ",".join("?" * len(tids))
        df = self.q(f"""SELECT tid, age, player_value, club FROM mart.player_snapshots
                        WHERE season=? AND phase=? AND tid IN ({ph})""", [season, phase, *tids])
        return {int(r.tid): {"Age": int(r.age) if pd.notna(r.age) else None,
                             "Value": int(r.player_value) if pd.notna(r.player_value) else None,
                             "Club": r.club}
                for r in df.itertuples()}

    def contract_info(self, season, phase, tids):
        tids = [int(t) for t in tids if t is not None]
        if not tids:
            return {}
        ph = ",".join("?" * len(tids))
        df = self.q(f"""SELECT tid, wage_gbp, contract_expiry FROM mart.player_snapshots
                        WHERE season=? AND phase=? AND tid IN ({ph})""", [season, phase, *tids])
        return {int(r.tid): {"Wage": r.wage_gbp, "Expiry": r.contract_expiry}
                for r in df.itertuples()}

    def match_stats_rows(self, club_tids):
        if not club_tids:
            return pd.DataFrame()
        ph = ",".join("?" * len(club_tids))
        return self.q(f"""
            SELECT season, tid, team_tid, opponent_tid, date, competition,
                   rating, goals, assists, passA, passC, keyPass,
                   tackA, tackW, intercept, headA, headW, crossA, crossC,
                   dribbles, shotA, shotO, mistakes, yellow,
                   started, appeared, minutes
            FROM mart.match_player_facts
            WHERE team_tid IN ({ph})""", [*club_tids])

    def comparison_leagues(self, season, phase, limit=4):
        df = self.q("""SELECT cid, name FROM mart.comparison_ladder
                       WHERE season=? AND phase=? ORDER BY ladder_rank LIMIT ?""",
                    [season, phase, limit])
        if df.empty:
            return []
        return [(int(r.cid), r.name) for r in df.itertuples(index=False)]

    def effective_table(self, season, phase, method):
        sql = """
        SELECT f.tid, f.position, f.role, f.familiarity, f.base_rating, f.eff,
               f.name, f.club, f.club_tid, f.league_cid, f.nation,
               f.pctile_global, f.pctile_nation, f.pctile_league,
               l.level_global, l.level_nation, l.level_league,
               f.rank_global, f.rank_nation, f.rank_league,
               l.n_global, l.n_nation, l.n_league
        FROM mart.player_position_fit f
        JOIN mart.player_position_levels l USING (season, phase, tid, position)
        WHERE f.season = ? AND f.phase = ? AND f.method = ?
        """
        return self.q(sql, [season, phase, method])

    def ability_rank_leagues(self, season, phase, tid_positions, league_cids, min_fam=0):
        if not tid_positions or not league_cids:
            return pd.DataFrame(columns=["tid", "position", "league_cid", "rank", "n"])
        vals = ", ".join(f"({int(t)}, '{str(pos)}')" for t, pos in tid_positions)
        cids = ", ".join(str(int(c)) for c in league_cids)
        sql = f"""
        WITH cl AS (SELECT club_tid, league_cid FROM mart.club_leagues WHERE season = ? AND phase = ?),
             pool AS (
                 SELECT p.tid, pp.position, p.ca, p.club_tid, cl.league_cid
                 FROM staging.players p
                 JOIN staging.player_positions pp ON (pp.season, pp.phase, pp.tid) = (p.season, p.phase, p.tid)
                 LEFT JOIN cl ON cl.club_tid = p.club_tid
                 WHERE p.season = ? AND p.phase = ? AND NOT p.is_staff AND p.ca IS NOT NULL
                   AND pp.familiarity >= ?
             ),
             tgt AS (SELECT po.tid, po.position, po.ca FROM pool po
                     JOIN (VALUES {vals}) v(tid, position)
                       ON v.tid = po.tid AND v.position = po.position)
        SELECT t.tid, t.position, l.league_cid,
               1 + COUNT(CASE WHEN o.ca > t.ca THEN 1 END) AS rank,
               1 + COUNT(o.tid) AS n
        FROM tgt t
        CROSS JOIN (SELECT DISTINCT league_cid FROM pool WHERE league_cid IN ({cids})) l
        LEFT JOIN pool o
          ON o.position = t.position AND o.league_cid = l.league_cid AND o.tid <> t.tid
        GROUP BY 1, 2, 3"""
        params = [season, phase, season, phase, int(min_fam)]
        return self.q(sql, params)

    def ability_rank_clubs(self, season, phase, tid_positions, league_cid, min_fam=0):
        if not tid_positions or league_cid is None:
            return pd.DataFrame(columns=["tid", "position", "club_tid", "club", "rank", "n"])
        vals = ", ".join(f"({int(t)}, '{str(pos)}')" for t, pos in tid_positions)
        sql = f"""
        WITH cl AS (SELECT club_tid, league_cid FROM mart.club_leagues WHERE season = ? AND phase = ?),
             pool AS (
                 SELECT p.tid, pp.position, p.ca, p.club_tid, cl.league_cid
                 FROM staging.players p
                 JOIN staging.player_positions pp ON (pp.season, pp.phase, pp.tid) = (p.season, p.phase, p.tid)
                 LEFT JOIN cl ON cl.club_tid = p.club_tid
                 WHERE p.season = ? AND p.phase = ? AND NOT p.is_staff AND p.ca IS NOT NULL
                   AND pp.familiarity >= ?
             ),
             tgt AS (SELECT po.tid, po.position, po.ca FROM pool po
                     JOIN (VALUES {vals}) v(tid, position)
                       ON v.tid = po.tid AND v.position = po.position),
             hosts AS (SELECT DISTINCT club_tid FROM pool WHERE league_cid = {int(league_cid)})
        SELECT t.tid, t.position, h.club_tid,
               COALESCE(any_value(c.name), '#' || h.club_tid) AS club,
               1 + COUNT(CASE WHEN o.ca > t.ca THEN 1 END) AS rank,
               1 + COUNT(o.tid) AS n
        FROM tgt t
        CROSS JOIN hosts h
        LEFT JOIN pool o
          ON o.position = t.position AND o.club_tid = h.club_tid AND o.tid <> t.tid
        LEFT JOIN staging.clubs c ON c.tid = h.club_tid AND c.season = ? AND c.phase = ?
        GROUP BY 1, 2, 3"""
        params = [season, phase, season, phase, int(min_fam), season, phase]
        return self.q(sql, params)

    def last_season_stats(self, season):
        rows = self.match_stats_rows(self.OUR_CLUBS)
        if rows is None or rows.empty:
            return pd.DataFrame()
        rows = rows[(rows["season"] == season - 1) & rows["appeared"]]
        if rows.empty:
            return pd.DataFrame()
        return rows.groupby("tid").agg(starts=("started", "sum"), apps=("rating", "size"),
                                       mins=("minutes", "sum"), rat=("rating", "mean"))

    def build_positions(self, season, phase, method, min_fam=DEFAULT_MIN_FAM, excl_loanees=True, slots=None):
        slots = dict(DEFAULT_SLOTS if slots is None else slots)

        ladder = self.comparison_leagues(season, phase, limit=4)
        if not ladder or ladder[0][0] is None:
            return {"error": "No club→league membership for this snapshot, so there's nothing to "
                             "rank against. Ability ranks need each club's division."}
        our_cid, our_lg = ladder[0]
        lower = [(c, n) for c, n in ladder[1:] if c is not None]

        eff = self.effective_table(season, phase, method)
        if eff.empty:
            return {"error": "No rated players in this snapshot."}

        squad_tids = set(self.q("SELECT DISTINCT tid FROM mart.squad_on(?)", [phase])["tid"].astype(int))
        loan_in_tids = (set(self.q("SELECT DISTINCT tid FROM mart.loan_in_spells "
                                   "WHERE CAST(? AS DATE) BETWEEN valid_from AND valid_to",
                                   [phase])["tid"].astype(int))
                        if squad_tids else set())

        ours = eff[eff["club_tid"].isin(self.OUR_CLUBS)
                  & eff["tid"].astype(int).isin(squad_tids)].copy()
        if excl_loanees and loan_in_tids:
            ours = ours[~ours["tid"].astype(int).isin(loan_in_tids)]
        if ours.empty:
            return {"error": "No owned players in this snapshot."}
        if min_fam:
            ours = ours[ours["familiarity"] >= min_fam]
            if ours.empty:
                return {"error": f"No owned player has a position at familiarity {min_fam} or above."}

        ours = ours.sort_values(["tid", "role", "position"], kind="mergesort")
        per_role = ours.loc[ours.groupby(["tid", "role"])["eff"].idxmax()].copy()
        per_role["depth"] = (per_role.groupby("role")["eff"]
                             .rank(ascending=False, method="min").astype(int))
        primary = per_role.loc[per_role.groupby("tid")["eff"].idxmax()].set_index("tid")["role"].to_dict()

        div_pool = eff[(eff["league_cid"] == our_cid) & (eff["familiarity"] >= min_fam)]

        def fit_pctile(tid, position, value):
            p = div_pool[(div_pool["position"] == position) & (div_pool["tid"] != tid)]["eff"]
            return round(100 * (p < value).mean(), 1) if len(p) >= 8 else float("nan")

        per_role["fit_div"] = [fit_pctile(t, p, e) for t, p, e
                               in zip(per_role["tid"], per_role["position"], per_role["eff"])]

        tid_pos = tuple(sorted({(int(t), str(p))
                                for t, p in zip(per_role["tid"], per_role["position"])}))
        ranks = self.ability_rank_leagues(season, phase, tid_pos, tuple(c for c, _ in ladder), min_fam)
        rk = {(int(r.tid), r.position, int(r.league_cid)): (int(r.rank), int(r.n))
              for r in ranks.itertuples()}

        def rank_pct(tid, position, cid):
            v = rk.get((int(tid), position, int(cid)))
            if not v or v[1] < 2:
                return float("nan")
            return round(100 * (v[1] - v[0]) / (v[1] - 1), 1)

        per_role["div_pct"] = [rank_pct(t, p, our_cid)
                               for t, p in zip(per_role["tid"], per_role["position"])]

        starts_at, best_hosts = {}, {}
        for cid, _lname in lower:
            hosts = self.ability_rank_clubs(season, phase, tid_pos, cid, min_fam)
            if hosts.empty:
                continue
            for (t, p), g in hosts.groupby(["tid", "position"]):
                firsts = g[(g["rank"] == 1) & (g["n"] >= MIN_HOST_SQUAD)]
                starts_at[(int(t), p, cid)] = len(firsts)
                best_hosts[(int(t), p, cid)] = g.sort_values(
                    ["rank", "n", "club"], ascending=[True, False, True])

        tids = [int(t) for t in per_role["tid"].unique()]
        bio = self.player_bio(season, phase, tids)
        per_role["age"] = per_role["tid"].map(lambda t: bio.get(int(t), {}).get("Age"))
        per_role["name_label"] = [self.player_label(t, n)
                                  for t, n in zip(per_role["tid"], per_role["name"])]

        roles_present = [r for r in ROLE_ORDER if r in set(per_role["role"])]
        roles_present += [r for r in sorted(set(per_role["role"])) if r not in ROLE_ORDER]

        per_role["read"] = [read_player(r, slots.get(r["role"], 1), primary, starts_at, lower)
                            for _, r in per_role.iterrows()]
        by_tid = per_role.groupby("tid")["role"].apply(set).to_dict()
        per_role["also"] = [", ".join(sorted(by_tid.get(int(t), set()) - {r})) or "—"
                            for t, r in zip(per_role["tid"], per_role["role"])]

        rows = []
        for role in roles_present:
            g = per_role[per_role["role"] == role].sort_values(
                ["eff", "tid"], ascending=[False, True], kind="mergesort")
            n_slots = slots.get(role, 1)
            best, top = g.iloc[0], g.head(max(1, n_slots))
            rows.append({"role": role, "owned": len(g), "slots": n_slots,
                         "best": best["name_label"], "best_tid": int(best["tid"]),
                         "position": best["position"], "fam": int(best["familiarity"]),
                         "rank_ours": rk.get((int(best["tid"]), best["position"], int(our_cid))),
                         "div_pct": best["div_pct"], "fit_div": best["fit_div"],
                         "avg_age": (round(top["age"].mean(), 1)
                                     if top["age"].notna().any() else None),
                         "read": role_read(g, n_slots)})
        summary = pd.DataFrame(rows).sort_values(["div_pct", "role"], na_position="last",
                                                 kind="mergesort")

        sq = self.squad(season, phase)
        return {"season": season, "phase": phase, "method": method, "min_fam": min_fam,
                "excl_loanees": excl_loanees, "slots": slots,
                "ladder": ladder, "our_cid": our_cid, "our_lg": our_lg, "lower": lower,
                "per_role": per_role, "roles_present": roles_present, "summary": summary,
                "primary": primary, "ranks": rk, "starts_at": starts_at, "best_hosts": best_hosts,
                "contract": self.contract_info(season, phase, tids),
                "status": dict(zip(sq["tid"].astype(int), sq["status"])),
                "prev": self.last_season_stats(season)}
