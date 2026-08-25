"""Depth-chart computation: every position in starting order, with a keep / loan / sell read.

Extracted from the Positions page so the Streamlit page and the static site build render the
SAME numbers and the same verdicts. It was worth pulling out the moment there were two
consumers: the two yardsticks below disagree constantly, and a site that computed them even
slightly differently from the dashboard would quietly become a second opinion instead of a
second screen.

The two independent yardsticks, and why both:
  - **Fit** — tactic fit under the selected weight-set, already multiplied down by position
    familiarity. Flatters a player whose attribute spread suits the role even when his level
    is poor, which is why `fam` travels beside it as the sanity check.
  - **Ability rank** — level. His position-matched rank among every player in a division,
    the only fair way to compare across divisions (a fit percentile is scoped to whatever
    league its owner sits in, so a reserve-team player would be ranked against the reserve
    league). Computed inside db.py, so only "6 of 75" ever comes back — never the number
    behind it.

Nothing here touches Streamlit: callers pass the knobs in and get plain frames + dicts back,
which is what lets the same call run under `streamlit run` and under a build script.
"""
import pandas as pd

import db

# Slots a role fills in the XI — drives the starter / cover / surplus split.
DEFAULT_SLOTS = {"GK": 1, "LB": 1, "CB": 2, "RB": 1, "DM": 1, "CM": 2,
                 "AML": 1, "AMC": 1, "AMR": 1, "ST": 1}
ROLE_ORDER = ["GK", "LB", "CB", "RB", "DM", "CM", "AML", "AMC", "AMR", "ST"]
# A host club needs at least this many players at the position (him included) before "he'd be
# their first choice" means anything — some lower-division clubs field 1 player in a position,
# or none at all, so every player we own would nominally "start" there.
MIN_HOST_SQUAD = 3
# Default familiarity floor. staging.player_positions lists every position a player has ANY
# familiarity in, so at 0 a depth chart of left backs is padded with centre-halves who could
# shuffle across — and the comparison pools are padded the same way.
DEFAULT_MIN_FAM = 15


def read_player(row, slots, primary, starts_at, lower):
    """Suggestion, not a verdict — it only knows depth, level, age and whether a lower
    division would start him. The rules are spelled out for the reader in both UIs so they
    can be overruled."""
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
    """One-line read for a whole position, from its best available player."""
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


def last_season_stats(season):
    """Starts / apps / minutes / avg rating in the PREVIOUS campaign, deduped to the latest
    phase per season (the light-results buffer repeats rows across snapshots)."""
    rows = db.match_stats_rows(db.OUR_CLUBS)
    if rows is None or rows.empty:
        return pd.DataFrame()
    rows = rows[(rows["season"] == season - 1) & rows["appeared"]]
    if rows.empty:
        return pd.DataFrame()
    return rows.groupby("tid").agg(starts=("started", "sum"), apps=("rating", "size"),
                                   mins=("minutes", "sum"), rat=("rating", "mean"))


def build(season, phase, method, min_fam=DEFAULT_MIN_FAM, excl_loanees=True, slots=None):
    """Everything both UIs need for the position review.

    Returns a dict, or {'error': msg} when the snapshot can't support the view (no
    club→league mapping, no rated players, nothing owned above the familiarity floor).
    Keys: ladder / our_cid / our_lg / lower, per_role (one row per player×role with depth,
    fit_div, div_pct, age, read), summary (one row per role), ranks / starts_at / best_hosts
    for the ability-rank cells, plus contract / status / prev lookups.
    """
    slots = dict(DEFAULT_SLOTS if slots is None else slots)

    ladder = db.comparison_leagues(season, phase, limit=4)
    if not ladder or ladder[0][0] is None:
        return {"error": "No club→league membership for this snapshot, so there's nothing to "
                         "rank against. Ability ranks need each club's division."}
    our_cid, our_lg = ladder[0]
    lower = [(c, n) for c, n in ladder[1:] if c is not None]

    eff = db.effective_table(season, phase, method)
    if eff.empty:
        return {"error": "No rated players in this snapshot."}

    # Squad membership comes from the dated spell model (mart.squad_on), not raw club_tid or
    # the staging.players.loaned_in flag — that flag is SET-ONLY (never cleared when a loan
    # lapses without renewal), so a naive club_tid filter here silently kept every past
    # loan-in forever, and excl_loanees's old flag-based check compounded it by ALSO dropping
    # the loan-ins who are genuinely still here this season. mart.squad_on(phase) already
    # gets both right: current squad = who's on it; currently-on-loan = a separate,
    # season-scoped lookup from mart.loan_in_spells.
    squad_tids = set(db.q("SELECT DISTINCT tid FROM mart.squad_on(?)", [phase])
                     ["tid"].astype(int))
    loan_in_tids = (set(db.q("SELECT DISTINCT tid FROM mart.loan_in_spells "
                             "WHERE CAST(? AS DATE) BETWEEN valid_from AND valid_to",
                             [phase])["tid"].astype(int))
                    if squad_tids else set())

    ours = eff[eff["club_tid"].isin(db.OUR_CLUBS)
              & eff["tid"].astype(int).isin(squad_tids)].copy()
    if excl_loanees and loan_in_tids:
        ours = ours[~ours["tid"].astype(int).isin(loan_in_tids)]
    if ours.empty:
        return {"error": "No owned players in this snapshot."}
    if min_fam:
        ours = ours[ours["familiarity"] >= min_fam]
        if ours.empty:
            return {"error": f"No owned player has a position at familiarity {min_fam} or above."}

    # Pin the row order before anything groups or ranks. effective_table is a plain SELECT
    # with no ORDER BY, so its order varies between runs; idxmax() and rank() then break ties
    # differently and the emitted positions.json churns even though nothing in the data moved.
    ours = ours.sort_values(["tid", "role", "position"], kind="mergesort")

    # one row per (player, role): his best position for that role, ranked by effective rating
    per_role = ours.loc[ours.groupby(["tid", "role"])["eff"].idxmax()].copy()
    per_role["depth"] = (per_role.groupby("role")["eff"]
                         .rank(ascending=False, method="min").astype(int))
    primary = per_role.loc[per_role.groupby("tid")["eff"].idxmax()].set_index("tid")["role"].to_dict()

    # Fit percentile recomputed against OUR OWN division at that position, so a reserve-team
    # player is measured on the same scale as a first-teamer (his club's own league_cid would
    # be the reserve league, which ranks him against other reserve sides).
    div_pool = eff[(eff["league_cid"] == our_cid) & (eff["familiarity"] >= min_fam)]

    def fit_pctile(tid, position, value):
        p = div_pool[(div_pool["position"] == position) & (div_pool["tid"] != tid)]["eff"]
        return round(100 * (p < value).mean(), 1) if len(p) >= 8 else float("nan")

    per_role["fit_div"] = [fit_pctile(t, p, e) for t, p, e
                           in zip(per_role["tid"], per_role["position"], per_role["eff"])]

    tid_pos = tuple(sorted({(int(t), str(p))
                            for t, p in zip(per_role["tid"], per_role["position"])}))
    ranks = db.ability_rank_leagues(season, phase, tid_pos, tuple(c for c, _ in ladder),
                                    min_fam, db._dbver())
    rk = {(int(r.tid), r.position, int(r.league_cid)): (int(r.rank), int(r.n))
          for r in ranks.itertuples()}

    def rank_pct(tid, position, cid):
        """0-100 quality percentile derived from rank/N (100 = best in that division)."""
        v = rk.get((int(tid), position, int(cid)))
        if not v or v[1] < 2:
            return float("nan")
        return round(100 * (v[1] - v[0]) / (v[1] - 1), 1)

    per_role["div_pct"] = [rank_pct(t, p, our_cid)
                           for t, p in zip(per_role["tid"], per_role["position"])]

    # would a club one or two divisions down actually PLAY him? rank 1 = their first choice
    starts_at, best_hosts = {}, {}
    for cid, _lname in lower:
        hosts = db.ability_rank_clubs(season, phase, tid_pos, cid, min_fam, db._dbver())
        if hosts.empty:
            continue
        for (t, p), g in hosts.groupby(["tid", "position"]):
            firsts = g[(g["rank"] == 1) & (g["n"] >= MIN_HOST_SQUAD)]
            starts_at[(int(t), p, cid)] = len(firsts)
            # club breaks the tie so the .head(5) cut downstream is deterministic. Without
            # it, clubs sharing a (rank, n) reorder between runs and the top-5 boundary
            # silently swaps members — which churns positions.json on every re-export.
            best_hosts[(int(t), p, cid)] = g.sort_values(
                ["rank", "n", "club"], ascending=[True, False, True])

    tids = [int(t) for t in per_role["tid"].unique()]
    bio = db.player_bio(season, phase, tids)
    per_role["age"] = per_role["tid"].map(lambda t: bio.get(int(t), {}).get("Age"))
    per_role["name_label"] = [db.player_label(t, n)
                              for t, n in zip(per_role["tid"], per_role["name"])]

    roles_present = [r for r in ROLE_ORDER if r in set(per_role["role"])]
    roles_present += [r for r in sorted(set(per_role["role"])) if r not in ROLE_ORDER]

    per_role["read"] = [read_player(r, slots.get(r["role"], 1), primary, starts_at, lower)
                        for _, r in per_role.iterrows()]
    # other roles the same player rates in — the "Also" column in both UIs
    by_tid = per_role.groupby("tid")["role"].apply(set).to_dict()
    per_role["also"] = [", ".join(sorted(by_tid.get(int(t), set()) - {r})) or "—"
                        for t, r in zip(per_role["tid"], per_role["role"])]

    rows = []
    for role in roles_present:
        # tid breaks eff ties so `best` (and everything derived from him) is stable
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
    # role breaks the tie: div_pct is NaN for any role with too small a comparison pool, and
    # pandas' default quicksort leaves both the ties and the NaN block in arbitrary order.
    summary = pd.DataFrame(rows).sort_values(["div_pct", "role"], na_position="last",
                                             kind="mergesort")

    sq = db.squad(season, phase)
    return {"season": season, "phase": phase, "method": method, "min_fam": min_fam,
            "excl_loanees": excl_loanees, "slots": slots,
            "ladder": ladder, "our_cid": our_cid, "our_lg": our_lg, "lower": lower,
            "per_role": per_role, "roles_present": roles_present, "summary": summary,
            "primary": primary, "ranks": rk, "starts_at": starts_at, "best_hosts": best_hosts,
            "contract": db.contract_info(season, phase, tids),
            "status": dict(zip(sq["tid"].astype(int), sq["status"])),
            "prev": last_season_stats(season)}


def rank_cell(ranks, tid, position, cid):
    v = ranks.get((int(tid), position, int(cid)))
    return f"{v[0]} / {v[1]}" if v else "—"


def prev_cell(prev, tid):
    """'starts/apps · minutes · avg rating' for last season, or an em dash."""
    if prev is None or prev.empty or int(tid) not in prev.index:
        return "—"
    r = prev.loc[int(tid)]
    return f"{int(r.starts)}/{int(r.apps)} · {int(r.mins)}m · {r.rat:.2f}"
