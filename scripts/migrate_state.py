#!/usr/bin/env python3
"""One-time migration: shortlist rows and the scouts JSONL -> state/ objects.

    uv run python scripts/migrate_state.py            # dry run, shows what it would move
    uv run python scripts/migrate_state.py --apply

Reads the OLD homes:
  - `staging.shortlist` in each career store (destroyed by any rebuild, invisible to a second
    machine, and needed CREATE TABLE on first read — which crashed pages against a read-only
    store);
  - `scouts/scouts.jsonl` (a shared append-only log: fine on one machine, a lost-write race
    as soon as two devices save different scouts).

Writes the NEW home: one JSON object per entry under state/, which dashboard/state.py mirrors
to R2. Idempotent — an entry already present is left alone, so running it twice is safe.

The old data is NOT deleted. Verify the dashboard reads everything first; the store copy
disappears on its own at the next rebuild, and scouts/scouts.jsonl can be removed by hand.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "dashboard"))

from _dbopen import open_readonly                                     # noqa: E402
from fmparser import careers                                          # noqa: E402
import state                                                          # noqa: E402

LEGACY_SCOUTS = os.path.join(REPO, "scouts", "scouts.jsonl")


def migrate_shortlist(apply):
    existing = {rec.get("name") for _k, rec in state.entries("shortlist", sync=False)}
    moved = 0
    for car in careers.CAREERS.values():
        store = os.path.join(REPO, car.db)
        if not os.path.exists(store):
            continue
        con, opened = open_readonly(store, tag="migrate")
        try:
            tbl = con.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='staging' "
                "AND table_name='shortlist'").fetchone()
            if not tbl:
                print(f"  {car.key}: no staging.shortlist table")
                continue
            rows = con.execute("SELECT id, tid, name, positions, attributes, source "
                               "FROM staging.shortlist ORDER BY id").fetchall()
        finally:
            con.close()
        if opened != store:
            print(f"  {car.key}: (store locked — read a copy)")
        print(f"  {car.key}: {len(rows)} shortlist rows in the store")
        for _id, tid, name, positions, attributes, source in rows:
            if name in existing:
                print(f"    = {name} (already in state/)")
                continue
            payload = {"tid": int(tid) if tid is not None else None,
                       "name": name,
                       "positions": json.loads(positions) if positions else {},
                       "attributes": json.loads(attributes) if attributes else {},
                       "source": source or "manual",
                       "migrated_from": f"{car.key}:staging.shortlist"}
            if apply:
                key = state.new_key()
                payload["id"] = key
                state.put("shortlist", key, payload)
            print(f"    {'+' if apply else '~'} {name} "
                  f"({', '.join(payload['positions']) or 'no positions'})")
            existing.add(name)
            moved += 1
    return moved


def migrate_scouts(apply):
    if not os.path.exists(LEGACY_SCOUTS):
        print("  no scouts/scouts.jsonl — nothing to migrate")
        return 0
    have = {k for k, _ in state.entries("scouts", sync=False)}
    moved = 0
    with open(LEGACY_SCOUTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print("    ! skipped an unparseable line")
                continue
            tid = rec.get("opponent_tid")
            label = rec.get("snapshot_label") or rec.get("snapshot")
            if tid is None or not label:
                print(f"    ! skipped a record with no opponent/snapshot key: "
                      f"{rec.get('opponent')}")
                continue
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(label))
            key = f"{int(tid)}-{safe}"
            if key in have:
                print(f"    = {rec.get('opponent')} @ {label} (already in state/)")
                continue
            if apply:
                state.put("scouts", key, rec)
            print(f"    {'+' if apply else '~'} {rec.get('opponent')} @ {label}")
            have.add(key)
            moved += 1
    return moved


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    a = ap.parse_args()

    print(f"{'MIGRATING' if a.apply else 'DRY RUN'} -> {state.STATE_DIR}")
    print(f"remote: {state.R2_REMOTE if state.remote_configured() else 'not configured '
                     '(local only; entries upload on the next write once rclone is set up)'}")
    print("\nshortlist")
    n_sl = migrate_shortlist(a.apply)
    print("\nscouts")
    n_sc = migrate_scouts(a.apply)
    verb = "migrated" if a.apply else "would migrate"
    print(f"\n{verb} {n_sl} shortlist entries and {n_sc} scout reports")
    if not a.apply:
        print("re-run with --apply to write them")
    else:
        print("old copies left in place on purpose — check the dashboard reads everything, "
              "then delete scouts/scouts.jsonl at your leisure (the store copy disappears at "
              "the next rebuild)")


if __name__ == "__main__":
    main()
