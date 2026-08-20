#!/usr/bin/env python3
"""Rebuild a career's DuckDB store from the save archive. The whole bootstrap, one command.

    uv run python scripts/rebuild.py --career frem

The store is DERIVED, never synced: it had grown to 96 MiB, rewrites wholesale on every import,
and sat within 4 MiB of GitHub's hard per-file limit. What IS durable is the recipe —
seeds/manifest.csv in git plus the `.fms.gz` archive in R2 — and this script executes it. That
also means each machine builds its own store, so there is no multi-writer problem to solve.

For each active manifest row:
  1. ensure the raw save exists at $FM_SAVES_DIR/<career>/<save_file>, fetching and gunzipping
     it from R2 if it doesn't;
  2. `extract.py <save> --career <career> --label <label>`;
  3. `load_duckdb.py output/<label> --db fm-<career>.duckdb --season S --phase P`.

Season and phase are passed EXPLICITLY from the manifest rather than re-derived. A save whose
in-game date differs from its last match date would otherwise land on a different phase, adding
a duplicate slice instead of replacing the intended one.

Compression note: gzip is byte-exact, so a decompressed save is identical to the original and
every structural scan behaves the same. That only holds because we decompress FIRST — mmap a
`.gz` and every offset in fmparser/regions.py is garbage. extract.py must never see anything
but raw bytes.

Budget ~1 min per snapshot (~12 min for Frem's 12).
"""
import argparse
import csv
import gzip
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fmparser import careers                                          # noqa: E402

MANIFEST = os.path.join(REPO, "seeds", "manifest.csv")
SAVES_DIR = os.path.expanduser(os.environ.get("FM_SAVES_DIR", "~/fm-saves"))
R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fm-parser")


def read_manifest():
    if not os.path.exists(MANIFEST):
        raise SystemExit(f"no manifest at {MANIFEST} — generate it with "
                         f"`uv run python scripts/export_manifest.py`")
    with open(MANIFEST) as f:
        return list(csv.DictReader(f))


def have_rclone():
    return shutil.which("rclone") is not None


def fetch_save(career, save_file, dry_run=False):
    """Return the path to a RAW save, fetching `<save_file>.gz` from R2 if needed.
    Returns None (with an explanation printed) when it can't be produced."""
    local_dir = os.path.join(SAVES_DIR, career)
    raw = os.path.join(local_dir, save_file)
    if os.path.exists(raw):
        return raw
    gz_local = raw + ".gz"
    remote = f"{R2_REMOTE}/saves/{career}/{save_file}.gz"
    if not os.path.exists(gz_local):
        if dry_run:
            print(f"    would fetch {remote}")
            return raw
        if not have_rclone():
            print(f"    ! missing {raw} and rclone isn't installed. Either drop the save "
                  f"there by hand or install rclone and configure the '{R2_REMOTE}' remote.")
            return None
        os.makedirs(local_dir, exist_ok=True)
        print(f"    fetching {remote}")
        r = subprocess.run(["rclone", "copy", remote, local_dir], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(gz_local):
            print(f"    ! fetch failed: {(r.stderr or '').strip() or 'no such object'}")
            print(f"      fix by hand:  rclone copy {remote} {local_dir}/")
            return None
    if dry_run:
        print(f"    would gunzip {os.path.basename(gz_local)}")
        return raw
    print(f"    gunzip {os.path.basename(gz_local)}")
    with gzip.open(gz_local, "rb") as src, open(raw + ".part", "wb") as dst:
        shutil.copyfileobj(src, dst, length=8 << 20)
    os.replace(raw + ".part", raw)        # atomic: a half-written save must never look complete
    return raw


def run(cmd, dry_run=False):
    print(f"    $ {' '.join(cmd)}")
    if dry_run:
        return True
    r = subprocess.run(cmd, cwd=REPO)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career", action="append",
                    help="career key (repeatable). Default: every active career.")
    ap.add_argument("--only", action="append", help="rebuild just these labels (repeatable)")
    ap.add_argument("--include-inactive", action="store_true",
                    help="also rebuild archived careers (Bucaspor: kept as a cross-career "
                         "parser regression test, not played)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip a label whose output/<label> dir already exists (re-loads it "
                         "without re-extracting — much faster when only the ETL changed)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    a = ap.parse_args()

    rows = read_manifest()
    if a.career:
        rows = [r for r in rows if r["career"] in set(a.career)]
    if a.only:
        rows = [r for r in rows if r["label"] in set(a.only)]
    if not a.include_inactive and not a.only:
        rows = [r for r in rows if r["active"] == "1"]
    if not rows:
        raise SystemExit("nothing to rebuild — check --career/--only against seeds/manifest.csv")

    by_career = {}
    for r in rows:
        by_career.setdefault(r["career"], []).append(r)

    print(f"rebuilding {len(rows)} snapshot(s) across {len(by_career)} career(s)")
    print(f"  saves dir : {SAVES_DIR}   (override with FM_SAVES_DIR)")
    print(f"  r2 remote : {R2_REMOTE}   (override with FM_R2_REMOTE)"
          f"{'' if have_rclone() else '   [rclone NOT installed]'}")
    t0 = time.time()
    done, failed, skipped = 0, [], []

    for career, crows in by_career.items():
        car = careers.resolve_career(career)
        print(f"\n=== {car.name} ({career}) -> {car.db} — {len(crows)} snapshots ===")
        for i, r in enumerate(crows, 1):
            label, season, phase = r["label"], r["season"], r["phase"]
            print(f"  [{i}/{len(crows)}] {label}  season={season} phase={phase}")
            if not r["save_file"]:
                print("    ! no save recorded in the manifest — cannot rebuild")
                failed.append(label)
                continue
            out_dir = os.path.join(REPO, "output", label)
            if a.skip_existing and os.path.isdir(out_dir):
                print(f"    reusing existing {os.path.relpath(out_dir, REPO)}")
            else:
                save = fetch_save(career, r["save_file"], a.dry_run)
                if save is None:
                    failed.append(label)
                    continue
                if not run([sys.executable, "extract.py", save, "--career", career,
                            "--label", label], a.dry_run):
                    print("    ! extract failed")
                    failed.append(label)
                    continue
            if not run([sys.executable, "load_duckdb.py", os.path.join("output", label),
                        "--db", car.db, "--season", str(season), "--phase", phase], a.dry_run):
                print("    ! load failed")
                failed.append(label)
                continue
            done += 1

    mins = (time.time() - t0) / 60
    print(f"\n{'would rebuild' if a.dry_run else 'rebuilt'} {done}/{len(rows)} snapshots "
          f"in {mins:.1f} min")
    if skipped:
        print(f"skipped: {', '.join(skipped)}")
    if failed:
        print(f"FAILED ({len(failed)}): {', '.join(failed)}")
        return 1
    if not a.dry_run:
        print("\nverify before trusting it — the cheap ground-truth checks are in "
              "docs/agent-context/etl-duckdb-dashboard.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
