#!/usr/bin/env python3
"""
Ground-truth guard for the tagged data-dictionary parser (fmparser/datadict.py).

Asserts the region still parses byte-lossless, the known record counts hold, records
round-trip (a dumped record re-reads identically from the save), and decoded anchors are
present. A refactor or an offset-shifting save fails loudly instead of silently.

Requires a 21-22 save (gitignored):
    python3 tests/test_datadict.py [path/to/21-22-save.fms]
Skips cleanly if none is found.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save                        # noqa: E402
from fmparser import datadict as D                    # noqa: E402

CANDIDATES = ["21-22-end.fms", "21-22-mid.fms", "fm_save1.fms"]

# --- ground truth (21-22-end.fms) ---
MIN_RECORDS = 25_000            # deep record count (25,818 on 21-22-end)
MIN_ENTITIES = 150             # distinct entity types (159 on 21-22-end)
KNOWN_COUNTS = {               # per-entity record counts that must hold exactly
    "comp": 7042, "stnm": 1373, "Ttea": 1158, "stdt": 1002, "fxds": 996,
    "endt": 954, "sdfd": 928, "nmsn": 823, "nati": 442,
}


def _check(cond, msg, fails):
    if not cond:
        fails.append(msg)


def _find_save(argv):
    if len(argv) > 1 and os.path.exists(argv[1]):
        return argv[1]
    for c in CANDIDATES:
        p = os.path.join(ROOT, c)
        if os.path.exists(p):
            return p
    return None


def run(save_path=None):
    save_path = save_path or _find_save(sys.argv)
    if not save_path:
        print("SKIP: no 21-22 save found")
        return 0

    fails = []
    s = Save(save_path)
    mm = s.mm

    # 1. lossless byte accounting
    cov = D.coverage(mm)
    _check(cov["unaccounted_bytes"] == 0,
           f"unaccounted bytes {cov['unaccounted_bytes']} != 0 (not lossless)", fails)
    _check(cov["accounted_bytes"] == cov["region_bytes"],
           "accounted != region_bytes", fails)

    # 2. record / entity counts
    per = D.collect(mm)
    total = sum(len(v) for v in per.values())
    _check(total >= MIN_RECORDS, f"only {total} records (< {MIN_RECORDS})", fails)
    _check(len(per) >= MIN_ENTITIES, f"only {len(per)} entities (< {MIN_ENTITIES})", fails)
    for entity, want in KNOWN_COUNTS.items():
        got = len(per.get(entity, []))
        _check(got == want, f"{entity}: {got} records, expected {want}", fails)

    # 3. round-trip fidelity: every dumped record re-parses identically from its offset
    mism = 0
    for entity, recs in per.items():
        for r in recs:
            res = D._parse(mm, r["offset"], D.HI)
            if not res or res[0][1] != r["fields"] or res[0][0] != entity:
                mism += 1
    _check(mism == 0, f"{mism} records failed round-trip re-parse", fails)

    # 4. decoded anchors present: our Turkish 2. League White Group comp uid 463485
    #    appears somewhere as a comp value.
    comp_uids = {v for r in per.get("comp", [])
                 for (t, v, *_) in r["fields"] if t == "comp" and isinstance(v, int)}
    _check(463485 in comp_uids, "comp uid 463485 (cid 228) not found in comp records", fails)

    # 5. schema report covers the tag space
    schema = D.schema_report(mm)
    _check(schema["tag_count"] >= 900, f"only {schema['tag_count']} tags (< 900)", fails)
    for tag in ("comp", "levl", "ntms", "year"):
        _check(tag in schema["tags"], f"schema missing tag {tag}", fails)

    # 6. cross-ref reverse index links comp uid 463485 back to the `comp` tag
    xr = D.crossref(mm, schema)
    key = "comp_uid:463485 (cid 228 Turkish 2.League White)"
    _check(key in xr["reverse_index"] and "comp" in xr["reverse_index"][key],
           "crossref reverse index missing comp uid -> comp", fails)

    if fails:
        print("FAIL:")
        for f in fails:
            print("  -", f)
        s.close()
        return 1
    print(f"PASS: datadict {total} records / {len(per)} entities, "
          f"lossless ({cov['tagged_pct']}% tagged, {cov['raw_pct']}% raw), round-trip OK")
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
