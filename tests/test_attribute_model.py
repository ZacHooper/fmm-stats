#!/usr/bin/env python3
"""The in-database attribute model must agree with an independent evaluation of its own
coefficients -- and, when the store still carries the frozen seed, with fmparser/model.py.

Two implementations of one formula exist: `model.predict` in Python, and the SQL that the dbt
model int.player_attribute_estimates (`fmstats/macros/attribute_decode.sql`) generates from
`stg.attribute_model`. That is the hazard CLAUDE.md already calls out for `v_player_ratings`
vs `site/js/data.js`.

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
from fmparser import model as A                                # noqa: E402
from fmparser.model import ATTR_ORDER, EXACT_SINGLE
from fmparser.tables.player_attributes import (  # noqa: E402
    HIDDEN_OFFSETS,
    PLAIN_OFFSETS,
    SRC_OFFSETS,
)

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
            "SELECT attribute, feature, coef, own_column, partner_column, fitted "
            "FROM stg.attribute_model").fetchall():
        d = spec.setdefault(attr, {"own": own, "partner": partner, "coef": {}})
        d["coef"][feat] = coef
        tags.add(fitted)
    if not spec:
        return skip("stg.attribute_model is empty")
    print(f"  coefficients in store: {', '.join(sorted(tags))}")

    # The decode reads the player's own attribute record (stg.player_attributes, keyed by
    # sid) and int.player_attribute_estimates holds its output for every player with one,
    # stated or not.
    byte_cols = sorted(set(COLS.values()))
    fitted = sorted(spec)
    rows = con.execute(f"""
        SELECT p.tid, r.ca, r.pa,
               {', '.join('r."' + c + '"' for c in byte_cols)},
               {', '.join(f'COALESCE(r.pos_{q.lower()}, 0)' for q in POS)},
               {', '.join('e."' + a + '"' for a in fitted)}
        FROM int.player_attribute_estimates e
        JOIN stg.persons p USING (snapshot_date, tid)
        JOIN stg.player_attributes r ON r.snapshot_date = p.snapshot_date AND r.sid = p.sid
        WHERE r.ca IS NOT NULL AND r.passing_src IS NOT NULL
        USING SAMPLE {SAMPLE} ROWS
    """).fetchall()
    if not rows:
        return skip("no attributed players in the store")

    bi = {c: 3 + i for i, c in enumerate(byte_cols)}
    pi = 3 + len(byte_cols)
    ei = pi + len(POS)

    bad_sql, bad_frozen, n_sql, n_frozen = {}, {}, 0, 0
    frozen_seed = all(t.startswith("frozen") for t in tags)
    for r in rows:
        ca, pa = r[1], r[2]
        m9 = sum(r[bi[c]] for c in MEAN9) / 9.0
        fam = r[pi:pi + len(POS)]
        top = POS[max(range(len(POS)), key=lambda i: (fam[i], -i))] if max(fam) else ""
        fwd = 1.0 if top in ("ST", "AML", "AMR", "AMC") else (
              0.5 if top in ("ML", "MR", "MC", "DMC", "DML", "DMR") else 0.0)
        for j, attr in enumerate(fitted):
            d = spec[attr]
            want = r[ei + j]
            own = MOD.uw(r[bi[d["own"]]])
            vals = {"own": own, "CA": ca, "PA": pa, "mean9": m9, "fwd": fwd,
                    "own*CA": own * ca / 100.0, "intercept": 1.0,
                    "partner": MOD.uw(r[bi[d["partner"]]]) if d["partner"] else 0.0}
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
    # touches them -- but their SQL is GENERATED from var('composites'), and a generated
    # expression that silently stops matching attributes.teamwork / aerial is exactly the
    # drift this file exists to catch. Also pins the estimate asymmetry: Teamwork's formula is
    # exact (estimate: false), Aerial's is ~71% (estimate: true), and swapping them would
    # quietly reclassify every non-squad player's is_estimated.
    import yaml
    with open(os.path.join(ROOT, "fmstats", "dbt_project.yml")) as f:
        composites = yaml.safe_load(f)["vars"]["composites"]
    JOINS = ("FROM int.player_attribute_estimates e "
             "JOIN stg.persons p USING (snapshot_date, tid) "
             "JOIN stg.player_attributes r "
             "ON r.snapshot_date = p.snapshot_date AND r.sid = p.sid ")
    for attr, fn, b1, b2, est in (
            ("Teamwork", A.teamwork, "unselfishness_src", "work_rate", False),
            ("Aerial", A.aerial, "heading_src", "jumping", True)):
        if composites[attr]["estimate"] is not est:
            ok = False
            print(f"FAIL: composites.{attr}.estimate should be {est}")
        rows = con.execute(f'SELECT r.{b1}, r.{b2}, e."{attr}" {JOINS}'
                           f'WHERE r.{b1} IS NOT NULL '
                           f'USING SAMPLE {SAMPLE} ROWS').fetchall()
        off = [(x, y, got) for x, y, got in rows if fn(x, y) != got]
        if off:
            ok = False
            print(f"FAIL: generated {attr} SQL disagrees with attributes.{fn.__name__}() on "
                  f"{len(off)} of {len(rows):,} e.g. {off[:3]}")
        elif rows:
            print(f"  OK  {len(rows):,} {attr} values match the closed form, estimate = {est}")

    # The seven attributes read directly off the record are never decoded, and
    # int.player_attributes takes every other one as stated where stated, decoded otherwise.
    decoded = {r[0] for r in con.execute("DESCRIBE int.player_attribute_estimates").fetchall()}
    stray = [a for a in EXACT_SINGLE if a in decoded]
    if stray:
        ok = False
        print(f"FAIL: read directly off the record, must never be modelled: {stray}")
    else:
        print(f"  OK  the {len(EXACT_SINGLE)} directly-read attributes are never modelled")
    chosen = " + ".join(
        f'count(*) FILTER (WHERE a."{c}" IS DISTINCT FROM '
        + (f'x."{c}")' if c in EXACT_SINGLE else f'COALESCE(x."{c}", e."{c}"))')
        for c in ATTR_ORDER)
    wrong = con.execute(f"""
        SELECT {chosen}
        FROM int.player_attributes a
        JOIN int.player_attributes_exact x USING (snapshot_date, tid)
        JOIN int.player_attribute_estimates e USING (snapshot_date, tid)""").fetchone()[0]
    if wrong:
        ok = False
        print(f"FAIL: int.player_attributes is not stated-else-decoded on {wrong:,} values")
    else:
        print("  OK  int.player_attributes is the stated value where stated, decoded otherwise")

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
