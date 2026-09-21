#!/usr/bin/env python3
"""The in-database attribute model must agree with an independent evaluation of its own
coefficients -- and, when the store still carries the frozen seed, with fmparser/model.py.

Two implementations of one formula exist now: `model.predict` in Python, and the SQL that
`load_duckdb._player_attributes_view` generates from `staging.attribute_model`. That is the
hazard CLAUDE.md already calls out for `v_player_ratings` vs `site/js/data.js`.

The invariant is NOT "SQL matches model.py" -- that breaks by design the moment anyone refits,
which is the whole point of moving the model into the database. It is:

  1. the SQL evaluates THE COEFFICIENTS THE STORE HOLDS correctly (always), and
  2. a store still carrying the frozen seed reproduces fmparser/model.py exactly (only then).

Needs no save file and no extract -- the raw bytes are in the store.

    uv run python tests/test_attribute_model.py [--db fm-frem.duckdb]
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import skip  # noqa: E402

from fmparser import model as MOD                                   # noqa: E402
from fmparser import player_attributes as A                                # noqa: E402
from fmparser.player_attributes import (ATTR_ORDER, SRC_OFFSETS, PLAIN_OFFSETS,  # noqa: E402
                                  HIDDEN_OFFSETS, EXACT_SINGLE)

COLS = {**SRC_OFFSETS, **PLAIN_OFFSETS, **HIDDEN_OFFSETS}
MEAN9 = ["heading_src", "unselfishness_src", "pace_src", "strength_src", "stamina_src",
         "technique_src", "aggression_src", "leadership_src", "agility_src"]
POS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
       "ST", "DML", "DMR"]
SAMPLE = 3000


def main(argv):
    db = argv[argv.index("--db") + 1] if "--db" in argv else "fm-frem.duckdb"
    if not os.path.exists(db):
        return skip(f"{db} not found (build it with scripts/rebuild.py)")
    import duckdb
    con = duckdb.connect(db, read_only=True)

    spec, tags = {}, set()
    for attr, feat, coef, own, partner, fitted in con.execute(
            "SELECT attribute, feature, coef, own_offset, partner_offset, fitted "
            "FROM staging.attribute_model").fetchall():
        d = spec.setdefault(attr, {"own": own, "partner": partner, "coef": {}})
        d["coef"][feat] = coef
        tags.add(fitted)
    if not spec:
        return skip("staging.attribute_model is empty")
    print(f"  coefficients in store: {', '.join(sorted(tags))}")

    byte_cols = sorted(set(COLS.values()))
    rows = con.execute(f"""
        SELECT p.tid, p.ca, p.pa,
               {', '.join('p."' + c + '"' for c in byte_cols)},
               {', '.join(f'''COALESCE((SELECT t.familiarity FROM staging.player_positions t
                    WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid)
                      AND t.position = '{q}'), 0)''' for q in POS)},
               {', '.join('a."' + a + '"' for a in ATTR_ORDER)},
               {', '.join('a."' + a + '_est"' for a in ATTR_ORDER)}
        FROM staging.players p JOIN staging.player_attributes a USING (season, phase, tid)
        WHERE p.ca IS NOT NULL AND p.passing_src IS NOT NULL
        USING SAMPLE {SAMPLE} ROWS
    """).fetchall()
    if not rows:
        return skip("no attributed players in the store")

    bi = {c: 3 + i for i, c in enumerate(byte_cols)}
    pi = 3 + len(byte_cols)
    ai = pi + len(POS)
    ei = ai + len(ATTR_ORDER)

    bad_sql, bad_frozen, n_sql, n_frozen = {}, {}, 0, 0
    frozen_seed = all(t.startswith("frozen") for t in tags)
    for r in rows:
        ca, pa = r[1], r[2]
        m9 = sum(r[bi[c]] for c in MEAN9) / 9.0
        fam = r[pi:pi + len(POS)]
        top = POS[max(range(len(POS)), key=lambda i: (fam[i], -i))] if max(fam) else ""
        fwd = 1.0 if top in ("ST", "AML", "AMR", "AMC") else (
              0.5 if top in ("ML", "MR", "MC", "DMC", "DML", "DMR") else 0.0)
        for attr, d in spec.items():
            j = ATTR_ORDER.index(attr)
            if not r[ei + j]:
                continue            # exact value; the model did not produce it
            want = r[ai + j]
            own = MOD.uw(r[bi[COLS[d["own"]]]])
            vals = {"own": own, "CA": ca, "PA": pa, "mean9": m9, "fwd": fwd,
                    "own*CA": own * ca / 100.0, "intercept": 1.0,
                    "partner": MOD.uw(r[bi[COLS[d["partner"]]]]) if d["partner"] else 0.0}
            vals.update({p: fam[k] for k, p in enumerate(POS)})
            # the NAT_ flags: a refit may pick 'nat' (Movement does), and a feature the
            # evaluator cannot read is a feature this test silently stops checking.
            vals.update({f"NAT_{p}": (1.0 if fam[k] >= 20 else 0.0)
                         for k, p in enumerate(POS)})
            vals["GK"] = fam[POS.index("GK")]
            acc = sum(c * vals[f] for f, c in d["coef"].items())
            got = max(1, min(20, int(_round_half_up(acc))))
            n_sql += 1
            if got != want:
                bad_sql.setdefault(attr, []).append((r[0], want, got))
            if frozen_seed and attr in MOD.FROZEN:
                n_frozen += 1
                fz = MOD.predict(attr, _buf(r, bi), 60, ca, pa, m9, fwd)
                if fz != want:
                    bad_frozen.setdefault(attr, []).append((r[0], want, fz))

    ok = True
    if bad_sql:
        ok = False
        print(f"FAIL: SQL disagrees with its OWN coefficients on "
              f"{sum(map(len, bad_sql.values()))} of {n_sql:,} values")
        for a, d in sorted(bad_sql.items(), key=lambda kv: -len(kv[1]))[:5]:
            print(f"  {a}: {len(d)} (tid, sql, expected) e.g. {d[:3]}")
    else:
        print(f"  OK  {n_sql:,} modelled values match an independent evaluation of the "
              f"store's own coefficients")

    if frozen_seed:
        if bad_frozen:
            ok = False
            print(f"FAIL: the frozen seed does not reproduce fmparser/model.py on "
                  f"{sum(map(len, bad_frozen.values()))} of {n_frozen:,}")
            for a, d in sorted(bad_frozen.items(), key=lambda kv: -len(kv[1]))[:5]:
                print(f"  {a}: {len(d)} e.g. {d[:3]}")
        else:
            print(f"  OK  {n_frozen:,} values also reproduce fmparser/model.py exactly")
    else:
        print("  --  store carries a refit, so the model.py cross-check does not apply")

    # The two PLAIN-BYTE COMPOSITES. These are not fits, so the coefficient check above never
    # touches them -- but their SQL is GENERATED from attributes.TEAMWORK_W / AERIAL_W, and a
    # generated expression that silently stops matching its own constants is exactly the drift
    # this file exists to catch. Also pins the `_est` asymmetry: Teamwork's formula is exact
    # (FALSE), Aerial's is ~71% (TRUE), and swapping them would quietly reclassify every
    # non-squad player across the mart.
    JOINS = ("FROM staging.players p "
             "JOIN staging.player_attributes a USING (season, phase, tid) "
             "JOIN staging.player_attributes_exact e USING (season, phase, tid) ")
    for attr, fn, b1, b2, est in (
            ("Teamwork", A.teamwork, "unselfishness_src", "work_rate", False),
            ("Aerial", A.aerial, "heading_src", "jumping", True)):
        where = f'WHERE e."{attr}" IS NULL AND p.{b1} IS NOT NULL '
        bad = con.execute(f'SELECT count(*) {JOINS}{where}'
                          f'AND a."{attr}_est" != {est}').fetchone()[0]
        if bad:
            ok = False
            print(f"FAIL: {attr}_est should be {est} on every modelled row -- {bad:,} wrong")
        rows = con.execute(f'SELECT p.{b1}, p.{b2}, a."{attr}" {JOINS}{where}'
                           f'USING SAMPLE {SAMPLE} ROWS').fetchall()
        off = [(x, y, got) for x, y, got in rows if fn(x, y) != got]
        if off:
            ok = False
            print(f"FAIL: generated {attr} SQL disagrees with attributes.{fn.__name__}() on "
                  f"{len(off)} of {len(rows):,} e.g. {off[:3]}")
        elif rows:
            print(f"  OK  {len(rows):,} {attr} values match the closed form, _est = {est}")

    stray = [a for a in EXACT_SINGLE
             if con.execute(f'SELECT count(*) FROM staging.player_attributes '
                            f'WHERE "{a}_est"').fetchone()[0]]
    if stray:
        ok = False
        print(f"FAIL: read directly off the record, must never be modelled: {stray}")
    else:
        print(f"  OK  the {len(EXACT_SINGLE)} directly-read attributes are never modelled")

    print("\nPASS: the database attribute model is self-consistent" if ok else "\nFAIL")
    return 0 if ok else 1


def _round_half_up(x):
    """DuckDB's round() goes half AWAY FROM ZERO; Python's round() goes half to EVEN."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _buf(r, bi):
    b = bytearray(120)
    for off, name in COLS.items():
        b[60 + off] = r[bi[name]]
    return b


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
