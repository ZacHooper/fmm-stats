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
  2. `extract.py <save>`, which names the output after the save;
  3. check the save's header date, and the campaign the career's rollover places it in,
     against the manifest row's phase and season, and fail loudly on a mismatch;
  4. `load_duckdb.py output/<label> --db fm-<career>.duckdb --career <career>`.

The save names its own snapshot, so the manifest's season/phase are a CHECK, not an input: a
mismatch means the manifest or the save is wrong, and loading it anyway would add a slice
under a key the recipe does not expect. `--trust-manifest` loads the manifest's values
regardless.

Compression note: gzip is byte-exact, so a decompressed save is identical to the original and
every structural scan behaves the same. That only holds because we decompress FIRST — mmap a
`.gz` and every binary offset is garbage. extract.py must never see anything
but raw bytes.

Budget ~1 min per snapshot (~12 min for Frem's 12).
"""
import argparse
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import careers                                                       # noqa: E402

MANIFEST = os.path.join(REPO, "seeds", "manifest.csv")
SAVES_DIR = os.path.expanduser(os.environ.get("FM_SAVES_DIR", "~/fm-saves"))
R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")


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


# The newest field every CURRENT extract carries and no old one does. `--skip-existing`
# reuses an output dir without looking inside it, so an extract written before a field
# landed loads CLEANLY and silently produces a store whose column is entirely NULL -- no
# error, no warning (a Bucaspor hold-out lost 7 snapshots of `passing_src` that way). Move
# this to the newest field whenever the extract gains one.
_EXTRACT_MARKER = "history_head"


def _extract_is_current(out_dir):
    """Does this extract carry the fields the loader now expects? Reads one attribute
    record."""
    f = os.path.join(out_dir, "attribute_records.json")
    if not os.path.exists(f):
        return False
    try:
        with open(f) as fh:
            head = fh.read(200_000)
    except OSError:
        return False
    return f'"{_EXTRACT_MARKER}"' in head


def check_against_manifest(out_dir, row, career):
    """None when the extract's header date, and the campaign the career places it in, match
    the manifest row's phase and season, else a message."""
    try:
        with open(os.path.join(out_dir, "summary.json")) as f:
            date = json.load(f).get("save_date")
        with open(os.path.join(out_dir, "matches.json")) as f:
            played = any(m["date"] for m in json.load(f))
    except (OSError, ValueError) as e:
        return f"no readable summary.json/matches.json ({e})"
    if date is None:
        return "the save's header carries no date"
    got = (str(career.campaign(date, played)), date)
    want = (row["season"], row["phase"])
    if got != want:
        return (f"the save says season {got[0]} phase {got[1]}, the manifest says season "
                f"{want[0]} phase {want[1]}")
    return None


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
    ap.add_argument("--db", help="write to this store instead of the career's own "
                                 "fm-<key>.duckdb — use it to rebuild into a scratch file and "
                                 "diff against the live one before trusting a change")
    ap.add_argument("--trust-manifest", action="store_true",
                    help="load each snapshot under the manifest's season/phase even when the "
                         "save's own header date disagrees")
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
        db_path = a.db or car.db
        print(f"\n=== {car.name} ({career}) -> {db_path} — {len(crows)} snapshots ===")
        for i, r in enumerate(crows, 1):
            label, season, phase = r["label"], r["season"], r["phase"]
            print(f"  [{i}/{len(crows)}] {label}  season={season} phase={phase}")
            if not r["save_file"]:
                print("    ! no save recorded in the manifest — cannot rebuild")
                failed.append(label)
                continue
            out_dir = os.path.join(REPO, "output", label)
            if a.skip_existing and os.path.isdir(out_dir) and _extract_is_current(out_dir):
                print(f"    reusing existing {os.path.relpath(out_dir, REPO)}")
            else:
                if a.skip_existing and os.path.isdir(out_dir):
                    print("    existing extract predates the current player record "
                          "— re-extracting")
                save = fetch_save(career, r["save_file"], a.dry_run)
                if save is None:
                    failed.append(label)
                    continue
                if os.path.splitext(os.path.basename(save))[0] != label:
                    print(f"    ! the manifest's label {label!r} is not the save's name "
                          f"{os.path.basename(save)!r}")
                    failed.append(label)
                    continue
                if not run([sys.executable, "extract.py", save], a.dry_run):
                    print("    ! extract failed")
                    failed.append(label)
                    continue
            load = [sys.executable, "load_duckdb.py", os.path.join("output", label),
                    "--db", db_path, "--career", career]
            if not a.dry_run:
                problem = check_against_manifest(out_dir, r, car)
                if problem and not a.trust_manifest:
                    print(f"    ! {problem} -- fix the manifest, or pass --trust-manifest")
                    failed.append(label)
                    continue
                if problem:
                    print(f"    ~ {problem}; loading the manifest's values (--trust-manifest)")
                    load += ["--season", str(season), "--phase", phase]
            if not run(load, a.dry_run):
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
