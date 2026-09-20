#!/usr/bin/env python3
"""
Ground-truth check for `fix_man.dat` against a club NEITHER career manages.

PR #63 validated the archive's fixture list against `mart.club_matches` for the MANAGED
club only (282/285 rows across both careers, 3 score-only mismatches attributed to a
variable-shape score block it explicitly declined to ship as a parser). That is the parser
marking its own homework on the one club it has independent data for -- Stoke City is
neither Frem nor Bucaspor's opponent in any special sense, so grading against it is the
first check that does not touch a single byte the two careers' own ETL already reads.

GROUND TRUTH is `tests/fixtures/fix_man_stoke_truth.json`, read off an in-game "Club
Fixtures" screenshot (2026-09-20): 11 rows, including both legs of a two-legged playoff
tie -- the shape most likely to break the "plain" score block save-archive.md warns about.

This intentionally re-derives the record layout inline rather than importing it from
`fmparser/archive.py` or a new `fmparser/fixtures.py`: docs/save-archive.md is explicit that
`fix_man.dat` is NOT shipped as a parser (no LAYOUTS entry, no `audit_records.py` coverage,
~70 of 92 bytes unnamed, no competition field). Promoting it to a real module is follow-up
work for once the score block's shape rule is understood -- see docs/TODO.md.

    uv sync --extra archive
    uv run python scripts/audit_fix_man.py [save.fms]
    uv run python scripts/audit_fix_man.py --resolve      # confirm truth-file tids by name
"""
import argparse
import datetime
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import archive as A                 # noqa: E402
from fmparser import reference as R                # noqa: E402
from fmparser.save import Save                     # noqa: E402

TRUTH_PATH = os.path.join(ROOT, "tests", "fixtures", "fix_man_stoke_truth.json")
SAVES = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))

# [u8 0x01][0x14][4 x 0xFF] opens every 92-byte record (docs/save-archive.md: STRIDE 92).
OPENER = bytes([0x01, 0x14, 0xFF, 0xFF, 0xFF, 0xFF])
STRIDE = 92

# Only the fields save-archive.md documents as verified. Everything else in the 92 bytes is
# UNNAMED there -- this script does not touch it, and does not claim to.
FIELDS = {"home_tid": (41, "<I"), "away_tid": (47, "<I"),
          "doy_raw": (53, "<H"), "year": (55, "<H"),
          "home_goals": (6, "<B"), "away_goals": (11, "<B")}


def read_records(blob):
    pos, out = 0, []
    while True:
        i = blob.find(OPENER, pos)
        if i == -1:
            break
        rec = blob[i:i + STRIDE]
        if len(rec) == STRIDE:
            vals = {name: struct.unpack_from(fmt, rec, off)[0]
                    for name, (off, fmt) in FIELDS.items()}
            vals["doy"] = vals.pop("doy_raw") & 0x1FF     # +53: day-of-year is a 9-bit field
            out.append(vals)
        pos = i + 1
    return out


def records_for_club(blob, tid):
    hits = [r for r in read_records(blob) if tid in (r["home_tid"], r["away_tid"])]
    for r in hits:
        try:
            r["date"] = (datetime.date(r["year"], 1, 1)
                         + datetime.timedelta(days=r["doy"] - 1)).isoformat()
        except ValueError:
            r["date"] = None
    return {r["date"]: r for r in hits if r["date"]}


def check(path, truth):
    with Save(path) as s:
        blob = A.extract(s.mm, "fix_man.dat")
        by_date = records_for_club(blob, truth["club_tid"])

    rows, ok = [], 0
    for f in truth["fixtures"]:
        rec = by_date.get(f["date"])
        if rec is None:
            rows.append((f, None, f"NO RECORD for {f['date']}"))
            continue
        got = (rec["home_tid"], rec["away_tid"], rec["home_goals"], rec["away_goals"])
        want = (f["home"], f["away"], f["hg"], f["ag"])
        if got == want:
            ok += 1
            rows.append((f, rec, "ok"))
        else:
            rows.append((f, rec, f"want {want} got {got}"))
    return rows, ok


def resolve(truth):
    """Print the name behind every tid in the truth file, as an independent name check."""
    path = os.path.join(SAVES, "frem", truth["save"])
    with Save(path) as s:
        clubs, _ = R._build_refdata_index(s.mm)
        tids = {truth["club_tid"]}
        for f in truth["fixtures"]:
            tids.add(f["home"])
            tids.add(f["away"])
        for tid in sorted(tids):
            rec = clubs.get(tid)
            print(f"  {tid:6} {rec['name'] if rec else '???'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("save", nargs="?", help="defaults to the truth file's own save")
    ap.add_argument("--resolve", action="store_true", help="print truth-file tids by name")
    args = ap.parse_args()

    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    if args.resolve:
        resolve(truth)
        return 0

    path = args.save or os.path.join(SAVES, "frem", truth["save"])
    if not os.path.exists(path):
        print(f"SKIP: {path} not present")
        return 0

    rows, ok = check(path, truth)
    for f, rec, status in rows:
        flag = "PASS" if status == "ok" else "FAIL"
        print(f"{flag} {f['date']}  {f['label']:42} {status}")

    print(f"\n{ok}/{len(rows)} fixtures match exactly on date, home/away tid and score "
          f"({truth['club_name']}, tid {truth['club_tid']}, not managed by either career)")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
