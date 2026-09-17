"""Score Frem-fitted coefficients on ANOTHER CAREER, without refitting.

This is the only evidence we have that the model generalises. Everything in the refit was
fitted AND validated on Frem; the frozen model scored ~63% on its own Bucaspor data and 54.8%
on ours, which is exactly the failure a single-career check cannot see.

Reads the coefficients out of one store and evaluates them against another store's bytes and
truth. Nothing is written and nothing is refitted -- if the numbers hold up, they hold up.

    uv run python scripts/holdout_score.py --fit fm-frem.duckdb --on fm-buca.duckdb
"""
import argparse, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
from fmparser.attributes import (ATTR_ORDER, SRC_OFFSETS, PLAIN_OFFSETS,      # noqa: E402
                                 HIDDEN_OFFSETS, EXACT_SINGLE, teamwork, aerial)
from fmparser import model as MOD                                             # noqa: E402

COLS = {**SRC_OFFSETS, **PLAIN_OFFSETS, **HIDDEN_OFFSETS}
MEAN9 = ["heading_src", "unselfishness_src", "pace_src", "strength_src", "stamina_src",
         "technique_src", "aggression_src", "leadership_src", "agility_src"]
POS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
       "ST", "DML", "DMR"]
_rhu = lambda x: math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)
GK_ATTRS = ("Handling", "Kicking", "Reflexes", "Communication", "Throwing")


def spec_from(db):
    import duckdb
    con = duckdb.connect(db, read_only=True)
    out, tags = {}, set()
    for a, f, c, o, p, fit in con.execute(
            "SELECT attribute,feature,coef,own_offset,partner_offset,fitted "
            "FROM staging.attribute_model").fetchall():
        out.setdefault(a, {"own": o, "partner": p, "coef": {}})["coef"][f] = c
        tags.add(fit)
    con.close()
    return out, tags


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", default="fm-frem.duckdb", help="store holding the coefficients")
    ap.add_argument("--on", required=True, help="store to score them against")
    a = ap.parse_args()
    import duckdb
    for f in (a.fit, a.on):
        if not os.path.exists(f):
            print(f"SKIP: {f} not found")
            return 0
    spec, tags = spec_from(a.fit)
    print(f"coefficients: {', '.join(sorted(tags))}  (from {a.fit})")
    print(f"scored on:    {a.on}, WITHOUT refitting\n")
    con = duckdb.connect(a.on, read_only=True)
    bc = sorted(set(COLS.values()))
    rows = con.execute(f"""
        SELECT p.ca, p.pa, {', '.join('p."' + c + '"' for c in bc)},
               {', '.join('e."' + x + '"' for x in ATTR_ORDER)},
               {', '.join(f'''COALESCE((SELECT t.familiarity FROM staging.player_positions t
                    WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid)
                      AND t.position = '{q}'), 0)''' for q in POS)}
        FROM staging.players p JOIN staging.player_attributes_exact e USING (season, phase, tid)
        WHERE p.ca IS NOT NULL AND p.passing_src IS NOT NULL AND e."Passing" IS NOT NULL
    """).fetchall()
    if not rows:
        print("no exact rows in the target store — nothing to score")
        return 0
    bi = {c: 2 + i for i, c in enumerate(bc)}
    ai = 2 + len(bc)
    pi = ai + len(ATTR_ORDER)
    is_gk = np.array([r[pi + POS.index("GK")] == 20 for r in rows])
    print(f"{len(rows)} exact rows ({int(is_gk.sum())} goalkeeper)\n")
    print(f"{'attribute':<15}{'frozen ex':>10}{'refit ex':>10}{'refit ±1':>10}{'n':>7}")
    tot = np.zeros(3)
    n_attr = 0
    for attr in ATTR_ORDER:
        y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
        keep = ~np.isnan(y)
        if not keep.any():
            continue
        if attr in EXACT_SINGLE or attr in ("Teamwork", "Aerial"):
            continue                                  # read or closed-form, not fitted
        if attr not in spec:
            continue
        d = spec[attr]
        got, fz = [], []
        for r in rows:
            fam = r[pi:pi + len(POS)]
            own = MOD.uw(r[bi[COLS[d["own"]]]])
            m9 = sum(r[bi[c]] for c in MEAN9) / 9.0
            v = {"own": own, "CA": r[0], "PA": r[1], "mean9": m9, "intercept": 1.0,
                 "own*CA": own * r[0] / 100.0, "GK": fam[POS.index("GK")],
                 "partner": MOD.uw(r[bi[COLS[d["partner"]]]]) if d["partner"] else 0.0}
            v.update({p: fam[k] for k, p in enumerate(POS)})
            v.update({f"NAT_{p}": (1.0 if fam[k] >= 20 else 0.0) for k, p in enumerate(POS)})
            top = POS[max(range(len(POS)), key=lambda i: (fam[i], -i))] if max(fam) else ""
            fwd = 1.0 if top in ("ST", "AML", "AMR", "AMC") else (
                  0.5 if top in ("ML", "MR", "MC", "DMC", "DML", "DMR") else 0.0)
            got.append(max(1, min(20, int(_rhu(sum(c * v[f] for f, c in d["coef"].items()))))))
            b = bytearray(120)
            for off, name in COLS.items():
                b[60 + off] = r[bi[name]]
            fz.append(MOD.predict(attr, b, 60, r[0], r[1], m9, fwd)
                      if attr in MOD.FROZEN else np.nan)
        got = np.array(got, float); fz = np.array(fz, float)
        # Score on the population that HAS the attribute. A goalkeeping attribute is pinned at
        # the display floor for an outfielder, so a pooled score measures how often we predict
        # 1 -- Communication reads 92% pooled and 3% on actual keepers.
        pop = keep & (is_gk if attr in GK_ATTRS else ~is_gk)
        if not pop.any():
            continue
        e = (got[pop] == y[pop]).mean()
        w = (np.abs(got[pop] - y[pop]) <= 1).mean()
        fe = (fz[pop] == y[pop]).mean()
        print(f"{attr:<15}{fe:>9.1%}{e:>10.1%}{w:>10.1%}{int(pop.sum()):>7}")
        tot += (fe, e, w); n_attr += 1
    print(f"\n{'MEAN':<15}{tot[0]/n_attr:>9.1%}{tot[1]/n_attr:>10.1%}{tot[2]/n_attr:>10.1%}")
    # the closed forms, which carry over unchanged
    for attr, fn, b1, b2 in (("Teamwork", teamwork, "unselfishness_src", "work_rate"),
                             ("Aerial", aerial, "heading_src", "jumping")):
        y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
        k = ~np.isnan(y)
        if not k.any():
            continue
        g = np.array([fn(r[bi[b1]], r[bi[b2]]) for r in rows], float)
        print(f"  {attr:<13}{'':>9}{(g[k] == y[k]).mean():>10.1%}"
              f"{(np.abs(g[k] - y[k]) <= 1).mean():>10.1%}  (closed form)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
