#!/usr/bin/env python3
"""The in-database attribute model must agree with fmparser/model.py, exactly.

The estimation moved out of the parser and into the database on 2026-09-17, so there are now
TWO implementations of the same fit: `model.predict` in Python and the SQL that
`load_duckdb._player_attributes_view` generates from `staging.attribute_model`. This is the
same hazard CLAUDE.md already calls out for `v_player_ratings` vs `site/js/data.js` -- two
implementations of one formula drift unless something checks them.

It reads the RAW BYTES back out of the store and re-runs the Python model over them, so it
needs no save file and no extract: the store alone is enough.

    uv run python tests/test_attribute_model.py [--db fm-frem.duckdb]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import model as MOD                                   # noqa: E402
from fmparser.attributes import (ATTR_ORDER, SRC_OFFSETS,           # noqa: E402
                                 PLAIN_OFFSETS, HIDDEN_OFFSETS, EXACT_SINGLE)

COLS = {**SRC_OFFSETS, **PLAIN_OFFSETS, **HIDDEN_OFFSETS}
MEAN9_COLS = ["heading_src", "unselfishness_src", "pace_src", "strength_src", "stamina_src",
              "technique_src", "aggression_src", "leadership_src", "agility_src"]
FWD_ORDER = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
             "ST", "DML", "DMR"]


def main(argv):
    db = "fm-frem.duckdb"
    if "--db" in argv:
        db = argv[argv.index("--db") + 1]
    if not os.path.exists(db):
        print(f"SKIP: {db} not found (build it with scripts/rebuild.py)")
        return 0
    import duckdb
    con = duckdb.connect(db, read_only=True)

    byte_cols = sorted(set(COLS.values()))
    rows = con.execute(f"""
        SELECT p.season, p.phase, p.tid, p.ca, p.pa,
               {', '.join('p."' + c + '"' for c in byte_cols)},
               (SELECT t.position FROM staging.player_positions t
                 WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid)
                 ORDER BY t.familiarity DESC,
                          list_position({FWD_ORDER!r}, t.position) LIMIT 1) AS toppos,
               {', '.join('a."' + a + '"' for a in ATTR_ORDER)},
               {', '.join('a."' + a + '_est"' for a in ATTR_ORDER)}
        FROM staging.players p JOIN staging.player_attributes a USING (season, phase, tid)
        WHERE p.ca IS NOT NULL AND p.passing_src IS NOT NULL
        USING SAMPLE 4000 ROWS
    """).fetchall()
    if not rows:
        print("SKIP: no attributed players in the store")
        return 0

    bi = {c: 5 + i for i, c in enumerate(byte_cols)}
    top_i = 5 + len(byte_cols)
    attr_i = top_i + 1
    est_i = attr_i + len(ATTR_ORDER)
    bad = {}
    for r in rows:
        ca, pa = r[3], r[4]
        mean9 = sum(r[bi[c]] for c in MEAN9_COLS) / 9.0
        top = r[top_i] or ""
        fwd = 1.0 if top in ("ST", "AML", "AMR", "AMC") else (
              0.5 if top in ("ML", "MR", "MC", "DMC", "DML", "DMR") else 0.0)
        # a flat buffer the Python model can index exactly as it indexes an mmap
        buf = bytearray(120)
        for rel, name in COLS.items():
            buf[60 + rel] = r[bi[name]]
        for attr, spec in MOD.FROZEN.items():
            # Only rows the model actually produced. Our own squad carries EXACT values from
            # the managed-club snapshot, and those are supposed to differ from the fit --
            # comparing them would be testing that the model is wrong.
            if not r[est_i + ATTR_ORDER.index(attr)]:
                continue
            want = r[attr_i + ATTR_ORDER.index(attr)]
            got = MOD.predict(attr, buf, 60, ca, pa, mean9, fwd)
            if want != got:
                bad.setdefault(attr, []).append((r[2], want, got))

    n = sum(1 for r in rows for a in MOD.FROZEN if r[est_i + ATTR_ORDER.index(a)])
    if bad:
        print(f"FAIL: SQL and fmparser/model.py disagree on {sum(map(len, bad.values()))}"
              f" of {n:,} values")
        for a, d in sorted(bad.items(), key=lambda kv: -len(kv[1])):
            print(f"  {a}: {len(d)} (tid, sql, python) e.g. {d[:3]}")
        return 1
    print(f"  OK  {n:,} modelled values across {len(rows):,} players agree exactly")
    # The exactly-known ones must never be modelled: they come straight off the record.
    exact_bad = [a for a in EXACT_SINGLE
                 if con.execute(f'SELECT count(*) FROM staging.player_attributes '
                                f'WHERE "{a}_est"').fetchone()[0]]
    if exact_bad:
        print(f"FAIL: these are read directly and must never be flagged estimated: {exact_bad}")
        return 1
    print(f"  OK  the {len(EXACT_SINGLE)} directly-read attributes are never flagged estimated")
    print("\nPASS: the database model and fmparser/model.py agree exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
