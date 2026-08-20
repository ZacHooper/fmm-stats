#!/usr/bin/env python3
"""Move a `.fms` save into the archive, gzip it, and verify the round-trip is byte-identical.

    uv run python scripts/archive_save.py ~/Downloads/denmark-24-start-2.fms --career frem
    uv run python scripts/archive_save.py --career frem --all-from-manifest   # bulk migration

Saves are the ONLY irreplaceable artefact in this project. The DuckDB store is derived and the
extract JSON is regenerable, but a lost `.fms` means a snapshot that can never be rebuilt. So
they live in two places: raw under $FM_SAVES_DIR/<career>/ for parsing, and gzipped in R2 for
keeping. They compress ~5x (64 MB -> 12 MB) because the format is mostly 00/ff filler.

Why the hash check matters: every structural read in this parser is offset-based
(fmparser/regions.py windows, tid/uid signature scans, the history slab's pointer chains). gzip
is byte-exact so decompression cannot move an offset — but that guarantee is worth verifying
once per file rather than assuming, because a silently truncated archive would look fine until
the day you needed to rebuild from it. So: hash the raw file, compress, decompress, hash again,
and refuse to keep the `.gz` unless the digests match.
"""
import argparse
import csv
import gzip
import hashlib
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fmparser import careers                                          # noqa: E402

SAVES_DIR = os.path.expanduser(os.environ.get("FM_SAVES_DIR", "~/fm-saves"))
R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")
MANIFEST = os.path.join(REPO, "seeds", "manifest.csv")
CHUNK = 8 << 20


def sha256(path, opener=open):
    h = hashlib.sha256()
    with opener(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    return f"{n / 1e6:.0f} MB"


def archive_one(src, career, upload=False, keep_source=False):
    """-> (ok, message). Moves src into the archive, writes a verified .gz beside it."""
    name = os.path.basename(src)
    dest_dir = os.path.join(SAVES_DIR, career)
    dest = os.path.join(dest_dir, name)
    gz = dest + ".gz"
    os.makedirs(dest_dir, exist_ok=True)

    if not os.path.exists(src) and os.path.exists(dest):
        print(f"  {name}: already in the archive")
    elif not os.path.exists(src):
        return False, f"{name}: not found at {src}"
    elif os.path.abspath(src) != os.path.abspath(dest):
        if os.path.exists(dest):
            if sha256(src) == sha256(dest):
                print(f"  {name}: identical copy already archived")
                if not keep_source:
                    os.remove(src)
            else:
                return False, (f"{name}: a DIFFERENT file of that name is already archived — "
                               f"resolve by hand, refusing to overwrite")
        else:
            (shutil.copy2 if keep_source else shutil.move)(src, dest)

    raw_digest = sha256(dest)
    raw_size = os.path.getsize(dest)

    if os.path.exists(gz) and sha256(gz, gzip.open) == raw_digest:
        print(f"  {name}: .gz already present and verified")
    else:
        with open(dest, "rb") as f_in, gzip.open(gz + ".part", "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out, length=CHUNK)
        os.replace(gz + ".part", gz)
        # the point of the exercise: prove decompression reproduces the file exactly, so no
        # offset in the parser can have shifted.
        if sha256(gz, gzip.open) != raw_digest:
            os.remove(gz)
            return False, f"{name}: gzip round-trip did NOT match — .gz discarded"

    ratio = raw_size / max(os.path.getsize(gz), 1)
    msg = f"{name}: {human(raw_size)} -> {human(os.path.getsize(gz))} ({ratio:.1f}x), verified"

    if upload:
        remote = f"{R2_REMOTE}/saves/{career}/"
        if shutil.which("rclone") is None:
            msg += "  [rclone not installed — not uploaded]"
        else:
            r = subprocess.run(["rclone", "copy", gz, remote], capture_output=True, text=True)
            msg += "  uploaded" if r.returncode == 0 else \
                   f"  UPLOAD FAILED: {(r.stderr or '').strip()[:120]}"
    return True, msg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("saves", nargs="*", help="paths to .fms files")
    ap.add_argument("--career", help="career key; required unless --all-from-manifest")
    ap.add_argument("--all-from-manifest", action="store_true",
                    help="archive every save named in seeds/manifest.csv, looking for each in "
                         "--source-dir (bulk one-time migration)")
    ap.add_argument("--source-dir", default=os.path.expanduser("~/Downloads"),
                    help="where to look for saves with --all-from-manifest")
    ap.add_argument("--upload", action="store_true", help="rclone copy each .gz to R2")
    ap.add_argument("--keep-source", action="store_true",
                    help="copy instead of move (leaves the original in place)")
    a = ap.parse_args()

    jobs = []
    if a.all_from_manifest:
        if not os.path.exists(MANIFEST):
            raise SystemExit(f"no manifest at {MANIFEST}")
        with open(MANIFEST) as f:
            for row in csv.DictReader(f):
                if a.career and row["career"] != a.career:
                    continue
                if row["save_file"]:
                    jobs.append((os.path.join(a.source_dir, row["save_file"]), row["career"]))
        seen, deduped = set(), []
        for src, car in jobs:                     # one save can back several labels
            if (src, car) not in seen:
                seen.add((src, car))
                deduped.append((src, car))
        jobs = deduped
    else:
        if not a.saves or not a.career:
            raise SystemExit("give one or more .fms paths plus --career, "
                             "or use --all-from-manifest")
        jobs = [(os.path.expanduser(s), a.career) for s in a.saves]

    print(f"archiving {len(jobs)} save(s) into {SAVES_DIR}")
    ok, bad = 0, []
    for src, career in jobs:
        careers.resolve_career(career)                       # fail fast on a bad key
        good, msg = archive_one(src, career, a.upload, a.keep_source)
        print(("  " if good else "  ! ") + msg)
        ok += good
        if not good:
            bad.append(msg)

    print(f"\n{ok}/{len(jobs)} archived and verified")
    if bad:
        print("problems:")
        for m in bad:
            print(f"  ! {m}")
        return 1
    if not a.upload:
        print(f"upload with:  rclone sync {SAVES_DIR} {R2_REMOTE}/saves --include '*.gz'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
