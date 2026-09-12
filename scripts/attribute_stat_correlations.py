#!/usr/bin/env python3
"""How do a player's ATTRIBUTES drive his on-pitch STATS?

Correlates each attribute against each per-90 match stat, **within positional unit**, over
player-SEASONS of our own club's competitive matches.

Why player-seasons and not players: a player's attributes change every year, and career totals
smear a 17-year-old's numbers into his 22-year-old ones. Each row here is one (person_id, season)
with the stats he actually produced that season and the attributes he actually had, read from that
season's latest snapshot.

Why within-unit: raw correlations are dominated by position. Centre-backs have high Tackling AND
high interceptions because they are centre-backs, so a naive whole-squad correlation "discovers"
that Tackling causes interceptions and that Movement prevents them. Every number here is computed
inside a unit, and the POOLED column is unit-demeaned rather than raw.

    uv run python scripts/attribute_stat_correlations.py                    # every stat
    uv run python scripts/attribute_stat_correlations.py --stat intercept_90
    uv run python scripts/attribute_stat_correlations.py --min-minutes 600 --top 10
    uv run python scripts/attribute_stat_correlations.py --csv out.csv

Read the output as description, not physics: these are OUR players under OUR team instructions.
A team instruction (closing down, Work Into Box) moves a whole column at once and will not show
up here as anything but noise.
"""
import argparse, os, sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Collapse the 14 positions to three outfield groups — no squad has the sample for finer.
POS_GROUP = {"GK": "GK",
             "DL": "Defence", "DC": "Defence", "DR": "Defence",
             "DML": "Midfield", "DMC": "Midfield", "DMR": "Midfield",
             "ML": "Midfield", "MC": "Midfield", "MR": "Midfield",
             "AML": "Attack", "AMC": "Attack", "AMR": "Attack", "ST": "Attack", "FC": "Attack"}

# The 18 outfield attributes (ATTR_ORDER minus the five keeper-only ones). Crossing belongs
# here: it is weighted KEY on our wing-backs, so leaving it out left a hole in exactly the
# role whose whole job is delivery.
ATTRS = ["Tackling", "Positioning", "Decisions", "Aggression", "Teamwork", "Strength", "Aerial",
         "Stamina", "Pace", "Agility", "Movement", "Technique", "Dribbling", "Creativity",
         "Passing", "Shooting", "Crossing", "Leadership"]

# counting stats -> per 90; the ratios are computed from their own numerator/denominator
COUNTS = ["intercept", "tackW", "tackA", "keyPass", "assists", "goals", "shotA", "shotO",
          "passA", "passC", "headA", "headW", "crossA", "crossC", "dribbles", "mistakes"]
RATIOS = {"pass_pct": ("passC", "passA"), "sot_pct": ("shotO", "shotA"),
          "head_pct": ("headW", "headA"), "tack_pct": ("tackW", "tackA"),
          "cross_pct": ("crossC", "crossA")}


def build(db, min_minutes, competition=None, who="us"):
    """One row per (person_id, season): minutes + stat totals + that season's attributes.

    `competition` is a SQL ILIKE pattern (e.g. "%Superliga%"). Our club has played in four
    different divisions, so an unfiltered run pools 3. Division minutes with top-flight ones.

    `who="opponents"` runs the same analysis on the players we have played AGAINST. That is the
    out-of-sample check: our own players all play under OUR instructions, opponents play under 57
    different clubs'. An effect that survives there is a property of the game, not of our tactic.
    Two things differ, and both matter when reading the result:
      * we only see an opponent in the 2-4 games he plays against us, so each observation is a
        handful of matches of noise and every correlation is ATTENUATED toward zero — compare
        signs and rank order with the `us` run, never magnitudes;
      * `match_player_facts.unit`/`position` are NULL for opponents (the mart only positions our
        own squad), so positions come from `mart.player_position_levels`, which covers every club.
    """
    # mart.match_player_facts is already deduped to one phase per season — never aggregate
    # staging.match_player_stats here, it is a ring buffer and stores a match up to 5 times.
    agg = ", ".join(f"SUM({c}) {c}" for c in COUNTS)
    side = ("team_tid IN (SELECT club_tid FROM mart.managed_club)" if who == "us"
            else "team_tid NOT IN (SELECT club_tid FROM mart.our_clubs)")
    comp = ("AND competition ILIKE '" + competition.replace("'", "''") + "'") if competition else ""
    f = db.q(f"""SELECT person_id, season, SUM(minutes) mins, {agg}, AVG(rating) rating
                 FROM mart.match_player_facts
                 WHERE {side} AND is_competitive AND minutes > 0 {comp}
                 GROUP BY person_id, season""")

    # Positions from player_position_levels, which names every club — match_player_facts.position
    # is NULL for opponents. Primary position = highest familiarity in that season.
    pos = db.q("""SELECT person_id, season, "position",
                         ROW_NUMBER() OVER (PARTITION BY person_id, season
                                            ORDER BY familiarity DESC, snap_ix DESC) rn
                  FROM mart.player_position_levels""")   # "position" is a DuckDB reserved word
    f = f.merge(pos[pos.rn == 1][["person_id", "season", "position"]], on=["person_id", "season"])

    snap = db.q("SELECT * FROM mart.player_snapshots")
    snap["_k"] = snap.phase.map(db.phase_key)            # phase is a DATE; never sort it as text
    snap = snap.sort_values("_k").groupby(["person_id", "season"], as_index=False).last()

    attrs = [a for a in ATTRS if a in snap.columns]
    m = f.merge(snap[["person_id", "season"] + attrs], on=["person_id", "season"], how="inner")
    m = m[(m.mins >= min_minutes) & m.position.notna()].copy()
    m["grp"] = m.position.map(POS_GROUP)
    m = m[m.grp != "GK"]                                 # keepers need their own stat set

    for c in COUNTS:
        m[c + "_90"] = 90 * m[c] / m.mins
    for name, (num, den) in RATIOS.items():
        m[name] = 100 * m[num] / m[den].replace(0, pd.NA)
    return m, attrs


def table(m, attrs, stat, top):
    """Per-unit and unit-demeaned-pooled correlations of every attribute against one stat."""
    cols = {}
    for g in ["Defence", "Midfield", "Attack"]:
        s = m[(m.grp == g)].dropna(subset=[stat])
        cols[f"{g} (n={len(s)})"] = {a: (s[stat].corr(s[a]) if len(s) > 2 and s[a].std() else None)
                                     for a in attrs}
    z = m.dropna(subset=[stat]).copy()
    for c in [stat] + attrs:                             # demean inside unit, then pool
        z[c] = z.groupby("grp")[c].transform(lambda v: v - v.mean())
    cols[f"POOLED (n={len(z)})"] = {a: z[stat].corr(z[a]) for a in attrs}

    d = pd.DataFrame(cols).round(2)
    return d.reindex(d.iloc[:, -1].abs().sort_values(ascending=False).index).head(top)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--career", default=os.environ.get("FM_CAREER", "frem"))
    p.add_argument("--db", help="path to the store (default: db.py's resolved path)")
    p.add_argument("--stat", action="append", help="repeatable; default = all")
    p.add_argument("--who", choices=["us", "opponents"], default="us",
                   help="'opponents' runs the same analysis on players we have faced — the "
                        "out-of-sample check, since they play under 57 other managers' "
                        "instructions. Their per-observation samples are small, so correlations "
                        "attenuate: compare signs, not magnitudes.")
    p.add_argument("--competition", help="SQL ILIKE pattern, e.g. '%Superliga%' — our club has "
                   "played four different divisions, so pooling them mixes standards")
    p.add_argument("--min-minutes", type=int, default=450,
                   help="drop player-seasons below this (default 450 — ~5 full games)")
    p.add_argument("--top", type=int, default=7, help="attributes to show per stat")
    p.add_argument("--csv", help="write the full long-form matrix here")
    a = p.parse_args()

    os.environ["FM_CAREER"] = a.career
    if a.db:
        os.environ["FM_DUCKDB"] = a.db
    os.environ.setdefault("FM_DUCKDB_READONLY", "1")
    from dashboard import db

    m, attrs = build(db, a.min_minutes, a.competition, a.who)
    print(f"{len(m)} {'OPPONENT ' if a.who == 'opponents' else ''}player-seasons "
          f"at >= {a.min_minutes} minutes"
          + (f" in {a.competition}" if a.competition else " (ALL competitions/divisions pooled)") + "  |  "
          + ", ".join(f"{k} {v}" for k, v in m.grp.value_counts().items()))

    if a.who == "opponents" and a.min_minutes > 270:
        print("  ⚠️  we only see an opponent in the 2-4 games he plays us; >270 minutes leaves "
              "almost nobody.\n      Use --min-minutes 180 and read signs, not magnitudes.")
    if not a.competition:
        comps = db.q("""SELECT DISTINCT competition FROM mart.match_player_facts
                        WHERE team_tid IN (SELECT club_tid FROM mart.managed_club)
                          AND is_competitive AND competition NOT ILIKE '%Pokal%'""").competition.tolist()
        if len(comps) > 1:
            print(f"  ⚠️  pooling {len(comps)} different divisions ({', '.join(sorted(comps))}).\n"
                  f"      Standard changes what an attribute buys — Aggression on interceptions runs\n"
                  f"      +0.34 in the lower divisions and -0.32 in the Superliga. Pass\n"
                  f"      --competition '%<division>%' unless you specifically want the pooled read.\n"
                  f"      And cross-check with --who opponents before believing any single cut.")
    stats = a.stat or [c + "_90" for c in COUNTS] + list(RATIOS) + ["rating"]
    rows = []
    for s in stats:
        if s not in m.columns:
            print(f"  (skipping unknown stat {s})")
            continue
        d = table(m, attrs, s, a.top)
        print(f"\n### {s}\n{d.to_string()}")
        long = d.reset_index(names="attribute").melt(id_vars="attribute", var_name="group", value_name="r")
        long.insert(0, "stat", s)
        rows.append(long)

    if a.csv and rows:
        pd.concat(rows).to_csv(a.csv, index=False)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
