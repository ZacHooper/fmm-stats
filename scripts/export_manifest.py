#!/usr/bin/env python3
"""Write seeds/manifest.csv — the recipe for rebuilding every store from the save archive.

The manifest is the one artefact that makes a DuckDB store disposable. Git holds the code and
the seeds, R2 holds the `.fms` archive, and this file says which save produced which snapshot.
Together they reproduce a store exactly, so the store itself never has to be synced, committed,
or backed up (it had grown to 96 MiB and was rewriting wholesale on every import).

Regenerate after importing a save:  uv run python scripts/export_manifest.py

Columns: career, save_file, label, season, phase, active
  save_file  basename only. `staging.extracts.save_path` used to hold an absolute path
             (/Users/<you>/Downloads/...), which silently made the recipe machine-specific.
  phase      the snapshot's in-game DATE. Passed explicitly on rebuild — letting the loader
             re-derive it can land a save on a different phase and duplicate the slice instead
             of replacing it.
  active     from Career.active. 0 = saves archived, store not rebuilt.
"""
import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from _dbopen import open_readonly                                    # noqa: E402
from fmparser import careers                                         # noqa: E402

MANIFEST = os.path.join(REPO, "seeds", "manifest.csv")
FIELDS = ["career", "save_file", "label", "season", "phase", "active"]


def rows_for(car, existing):
    store = os.path.join(REPO, car.db)
    if not os.path.exists(store):
        kept = existing.get(car.key, [])
        # No store to read fresh rows from — keep whatever this career already had in the
        # manifest rather than dropping it. A machine that has only built ONE of two careers'
        # stores (the common case: bucaspor is archived and normally left unbuilt) must not
        # wipe the other career's rebuild recipe out of git just by running this script.
        print(f"  {car.key:10s} no store at {car.db} — kept {len(kept)} existing row(s) "
              f"({'archived' if not car.active else 'not built yet'})")
        return kept
    con, opened = open_readonly(store, tag="manifest")
    if opened != store:
        print(f"  {car.key:10s} (store locked by a running dashboard — read a copy)")
    try:
        rows = con.execute(
            "SELECT label, save_path, season, phase FROM staging.extracts "
            "ORDER BY season, phase").fetchall()
    finally:
        con.close()
    out = []
    for label, save_path, season, phase in rows:
        out.append({"career": car.key,
                    # tolerate both conventions: older stores hold an absolute path, newer
                    # ones already hold the basename.
                    "save_file": os.path.basename(save_path) if save_path else "",
                    "label": label, "season": season, "phase": phase,
                    "active": 1 if car.active else 0})
    missing = [r["label"] for r in out if not r["save_file"]]
    if missing:
        print(f"  ! {car.key}: no save_path recorded for {missing} — these cannot be rebuilt")
    print(f"  {car.key:10s} {len(out)} snapshots  (active={int(car.active)})")
    return out


def read_existing():
    if not os.path.exists(MANIFEST):
        return {}
    with open(MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        # CSV gives every field back as a string; fresh rows from rows_for() carry season/active
        # as the int types DuckDB returned, and main()'s sum()/dupe-key logic needs both branches
        # to agree.
        r["season"] = int(r["season"])
        r["active"] = int(r["active"])
        out.setdefault(r["career"], []).append(r)
    return out


def main():
    print("reading staging.extracts from each career store")
    existing = read_existing()
    rows = [r for car in careers.CAREERS.values() for r in rows_for(car, existing)]
    if not rows:
        raise SystemExit("no snapshots found in any store — nothing to write")
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    active = sum(r["active"] for r in rows)
    print(f"\nwrote {os.path.relpath(MANIFEST, REPO)}: {len(rows)} rows "
          f"({active} active, {len(rows) - active} archived)")
    dupes = {}
    for r in rows:
        dupes.setdefault((r["career"], r["season"], r["phase"]), []).append(r["label"])
    for k, labels in dupes.items():
        if len(labels) > 1:
            print(f"! WARNING {k} has {len(labels)} labels {labels} — a rebuild loads them in "
                  f"order and the last one wins")


if __name__ == "__main__":
    main()
