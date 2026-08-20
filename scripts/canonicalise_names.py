#!/usr/bin/env python3
"""Rename every save and label to `<career>-<in-game date>`, everywhere it appears.

    uv run python scripts/canonicalise_names.py            # dry run
    uv run python scripts/canonicalise_names.py --apply

The naming convention
---------------------
    <career>-<YYYY-MM-DD>[-<tag>].fms        e.g. frem-2023-07-02.fms

The date is the snapshot's **in-game date**, which is exactly `phase` — half of the store's
natural key `(season, phase)`. So the filename states the snapshot's identity instead of
nicknaming it: unique by construction, sorts chronologically, scoped by career. `season` is
omitted because it's derivable (a phase in July or later belongs to the next campaign).

An optional `-<tag>` may follow the date as a human note (`frem-2023-07-02-window-open.fms`).
It is deliberately OUTSIDE the identity: nothing parses it, so renaming a note can't break a
rebuild. Only `<career>-<date>` is meaningful.

Why it needed doing: the old names carried three typos (`denamrk`, `denarm`, `demark`), some had
no career (`21-22-mid.fms`), some no date (`fm_save3.fms`), and two consecutive days were
distinguished only by a `-2` suffix. Labels were a THIRD vocabulary again (`denmark-start`,
`frem-23-summer`, `2023-07-02`). One string now covers all of it.

What this touches — all five, or the rename is worse than useless
----------------------------------------------------------------
  1. `$FM_SAVES_DIR/<career>/<save>.fms` and its `.gz`
  2. the R2 object `saves/<career>/<save>.fms.gz`
  3. `output/<label>/` (the extract dir)
  4. `staging.extracts.save_path` AND `.label` in each career store
  5. saved scouts in `state/scouts/`, whose object key embeds `snapshot_label`

Step 4 is the one that bites: `seeds/manifest.csv` is GENERATED from the store, so renaming
files without updating `staging.extracts` means the next `export_manifest.py` run silently
reverts the manifest to the old names — and then a rebuild looks for saves that no longer exist.

Saves with no manifest row have no in-game date and so no canonical name; they move to
`<career>/unfiled/` rather than being guessed at.

Requires the stores to be writable — stop Streamlit first.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "dashboard"))

import duckdb                                                          # noqa: E402
from fmparser import careers                                           # noqa: E402
import state                                                           # noqa: E402

MANIFEST = os.path.join(REPO, "seeds", "manifest.csv")
SAVES_DIR = os.path.expanduser(os.environ.get("FM_SAVES_DIR", "~/fm-saves"))
R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")


def canonical_stem(career, phase, tag=None):
    return f"{career}-{phase}" + (f"-{tag}" if tag else "")


def rclone(args):
    if shutil.which("rclone") is None:
        return False, "rclone not installed"
    r = subprocess.run(["rclone", *args], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()


def plan_rows():
    with open(MANIFEST) as f:
        rows = list(csv.DictReader(f))
    plan = []
    for r in rows:
        stem = canonical_stem(r["career"], r["phase"])
        plan.append({**r, "new_stem": stem, "new_save": stem + ".fms",
                     "save_changed": r["save_file"] != stem + ".fms",
                     "label_changed": r["label"] != stem})
    return plan


def move_local(old, new, apply, what):
    if not os.path.exists(old):
        return f"      - {what}: missing ({os.path.basename(old)})"
    if os.path.exists(new) and os.path.abspath(old) != os.path.abspath(new):
        return f"      ! {what}: target exists, skipped ({os.path.basename(new)})"
    if apply:
        os.rename(old, new)
    return f"      {'>' if apply else '~'} {what}: {os.path.basename(old)} -> {os.path.basename(new)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually rename (default: dry run)")
    ap.add_argument("--career", action="append", help="limit to these careers")
    ap.add_argument("--skip-r2", action="store_true", help="don't touch R2 objects")
    a = ap.parse_args()
    apply = a.apply

    plan = plan_rows()
    if a.career:
        plan = [r for r in plan if r["career"] in set(a.career)]
    todo = [r for r in plan if r["save_changed"] or r["label_changed"]]
    print(f"{'APPLYING' if apply else 'DRY RUN'} — {len(todo)} of {len(plan)} rows need renaming\n")

    for r in todo:
        print(f"  {r['career']}/{r['phase']}  (season {r['season']})")
        if r["save_changed"]:
            print(f"      save : {r['save_file']}  ->  {r['new_save']}")
        if r["label_changed"]:
            print(f"      label: {r['label']}  ->  {r['new_stem']}")
        d = os.path.join(SAVES_DIR, r["career"])
        if r["save_changed"]:
            print(move_local(os.path.join(d, r["save_file"]),
                             os.path.join(d, r["new_save"]), apply, "raw"))
            print(move_local(os.path.join(d, r["save_file"] + ".gz"),
                             os.path.join(d, r["new_save"] + ".gz"), apply, "gz"))
            if not a.skip_r2:
                src = f"{R2_REMOTE}/saves/{r['career']}/{r['save_file']}.gz"
                dst = f"{R2_REMOTE}/saves/{r['career']}/{r['new_save']}.gz"
                if apply:
                    ok, err = rclone(["moveto", src, dst])
                    print(f"      {'>' if ok else '!'} r2 : {'moved' if ok else err[:70]}")
                else:
                    print(f"      ~ r2 : moveto {os.path.basename(src)} -> {os.path.basename(dst)}")
        if r["label_changed"]:
            print(move_local(os.path.join(REPO, "output", r["label"]),
                             os.path.join(REPO, "output", r["new_stem"]), apply, "output dir"))

    # ---- stores: save_path + label are what make the manifest regenerate correctly
    print("\nstores")
    for key, car in careers.CAREERS.items():
        if a.career and key not in set(a.career):
            continue
        store = os.path.join(REPO, car.db)
        if not os.path.exists(store):
            print(f"  {key}: no store — skipped")
            continue
        rows = [r for r in plan if r["career"] == key]
        if apply:
            con = duckdb.connect(store)
            try:
                for r in rows:
                    con.execute("UPDATE staging.extracts SET save_path=?, label=? "
                                "WHERE season=? AND phase=?",
                                [r["new_save"], r["new_stem"], int(r["season"]), r["phase"]])
                n = con.execute("SELECT COUNT(*) FROM staging.extracts WHERE label LIKE ?",
                                [f"{key}-%"]).fetchone()[0]
                print(f"  {key}: updated {len(rows)} rows ({n} now canonically labelled)")
            finally:
                con.close()
        else:
            print(f"  {key}: would update {len(rows)} rows (save_path + label)")

    # ---- saved scouts embed snapshot_label in their object key
    print("\nsaved scouts")
    label_map = {(r["career"], r["label"]): r["new_stem"] for r in plan}
    for skey, rec in state.entries("scouts", sync=False):
        old_label = rec.get("snapshot_label")
        new_label = next((v for (c, l), v in label_map.items() if l == old_label), None)
        if not new_label or new_label == old_label:
            print(f"  {skey}: label {old_label!r} unchanged")
            continue
        new_key = f"{int(rec['opponent_tid'])}-{new_label}"
        print(f"  {'>' if apply else '~'} {skey} -> {new_key}  "
              f"(snapshot_label {old_label!r} -> {new_label!r})")
        if apply:
            rec["snapshot_label"] = new_label
            state.put("scouts", new_key, rec)
            state.delete("scouts", skey)

    # ---- unfiled saves: no manifest row means no in-game date, so no canonical name
    print("\nunfiled saves (no manifest row -> no date -> left named as-is)")
    known = {r["save_file"] for r in plan} | {r["new_save"] for r in plan}
    for key in careers.CAREERS:
        if a.career and key not in set(a.career):
            continue
        d = os.path.join(SAVES_DIR, key)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".fms") or fn in known:
                continue
            sub = os.path.join(d, "unfiled")
            print(f"  {'>' if apply else '~'} {key}/{fn} -> {key}/unfiled/{fn}")
            if apply:
                os.makedirs(sub, exist_ok=True)
                for ext in ("", ".gz"):
                    src = os.path.join(d, fn + ext)
                    if os.path.exists(src):
                        os.rename(src, os.path.join(sub, fn + ext))
                if not a.skip_r2:
                    rclone(["moveto", f"{R2_REMOTE}/saves/{key}/{fn}.gz",
                            f"{R2_REMOTE}/saves/{key}/unfiled/{fn}.gz"])

    if apply:
        print("\nregenerating the manifest from the updated stores")
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "export_manifest.py")],
                       cwd=REPO)
    else:
        print("\nre-run with --apply to perform all of the above")


if __name__ == "__main__":
    main()
