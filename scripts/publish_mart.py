#!/usr/bin/env python3
"""Publish a SLIM analysis store — the `mart` layer only — to R2, alongside the full copy.

    uv run python scripts/publish_mart.py --career frem --upload

Copies all materialized `mart.*` tables from the local DuckDB store into a lightweight,
standalone DuckDB file (~156 MB vs ~279 MB full store) with zero raw/staging/intermediate overhead.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import duckdb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import careers as C                                                      # noqa: E402
import dbopen as _dbopen                                                  # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")
MAX_MB = 200  # Guardrail against runaway materialization


def build(src_path, dest):
    """Extract all base tables from `mart` in `src_path` into `dest`."""
    if os.path.exists(dest):
        os.remove(dest)

    t0 = time.time()
    con = duckdb.connect(dest)
    con.execute(f"ATTACH '{src_path}' AS src (READ_ONLY)")
    con.execute("CREATE SCHEMA mart")

    TABLE_SORT_KEYS = {
        'fact_player_state_scd': 'person_id, valid_from',
        'fact_player_valuation': 'person_id, snapshot_date',
        'fact_stadium_snapshot': 'stadium_id, snapshot_date',
        'fact_team_snapshot': 'team_tid, snapshot_date',
        'fact_staff_snapshot': 'person_id, snapshot_date',
        'fact_team_match': 'match_id',
        'fact_club_snapshot': 'club_tid, snapshot_date',
        'fact_contract': 'person_id, first_seen_date',
        'fact_transfer': 'person_id, season',
        'fact_player_season': 'person_id, season',
        'fact_loan_spell': 'person_id, season',
    }

    # Copy all base tables
    tables = [t for (t,) in con.execute(
        "SELECT table_name FROM duckdb_tables() "
        "WHERE database_name = 'src' AND schema_name = 'mart' "
        "ORDER BY table_name").fetchall()]
    print(f"  copying {len(tables)} materialized mart tables...", flush=True)
    t0 = time.time()
    for i, t in enumerate(tables, 1):
        t_tab = time.time()
        order_clause = f" ORDER BY {TABLE_SORT_KEYS[t]}" if t in TABLE_SORT_KEYS else ""
        con.execute(f'CREATE TABLE mart."{t}" AS SELECT * FROM src.mart."{t}"{order_clause}')
        cnt = con.execute(f'SELECT count(*) FROM mart."{t}"').fetchone()[0]
        sort_note = f" (sorted by {TABLE_SORT_KEYS[t]})" if t in TABLE_SORT_KEYS else ""
        print(f"    [{i:2d}/{len(tables)}] mart.{t:<32s} {cnt:>9,} rows [{time.time() - t_tab:.2f}s]{sort_note}", flush=True)

    # Recreate fact_player_snapshot view over SCD2 and Valuation
    con.execute("""
        CREATE VIEW mart.fact_player_snapshot AS
        SELECT
            val.person_id,
            val.snapshot_date,
            scd.tid,
            scd.team_tid,
            scd.club_tid,
            date_diff('year', person.dob, val.snapshot_date) -
                case when (month(val.snapshot_date) < month(person.dob))
                     or (month(val.snapshot_date) = month(person.dob) and day(val.snapshot_date) < day(person.dob))
                     then 1 else 0 end as age,
            scd.nationality_id,
            scd.second_nationality_id,
            scd.is_goalkeeper,
            scd.has_attributes,
            scd.ca,
            scd.pa,
            val.reputation,
            val.current_reputation,
            val.world_reputation,
            scd.squad_number,
            scd.international_retired,
            scd.international_caps,
            scd.international_goals,
            scd.u21_caps,
            scd.u21_goals,
            scd.joined_date,
            val.value,
            val.value_is_estimated,
            val.value_in_trusted_band,
            scd.scrapbook_entry_date,
            scd.wage_gbp,
            scd.contract_start,
            scd.contract_expiry,
            scd.contract_status,
            scd.is_contracted,
            scd.squad_status,
            scd.training_intensity,
            scd.training_focus_role,
            scd.training_focus_attribute,
            scd.training_focus_position,
            scd."Aerial", scd."Crossing", scd."Dribbling", scd."Shooting", scd."Passing",
            scd."Tackling", scd."Technique", scd."Aggression", scd."Creativity", scd."Decisions",
            scd."Leadership", scd."Movement", scd."Positioning", scd."Teamwork", scd."Pace",
            scd."Stamina", scd."Strength", scd."Agility", scd."Handling", scd."Kicking",
            scd."Reflexes", scd."Communication", scd."Throwing",
            scd.attributes_are_estimated,
            scd.jumping, scd.consistency, scd.big_match, scd.injury_prone, scd.versatility,
            scd.set_pieces, scd.penalty, scd.work_rate, scd.flair,
            scd.adaptability, scd.ambition, scd.determination, scd.loyalty, scd.pressure,
            scd.professionalism, scd.sportsmanship, scd.temperament,
            scd.pos_gk, scd.pos_sw, scd.pos_dl, scd.pos_dc, scd.pos_dr, scd.pos_dmc,
            scd.pos_ml, scd.pos_mc, scd.pos_mr, scd.pos_aml, scd.pos_amc, scd.pos_amr,
            scd.pos_st, scd.pos_dml, scd.pos_dmr,
            val.snapshot_date = max(val.snapshot_date) over () as is_current
        FROM mart.fact_player_valuation val
        JOIN mart.fact_player_state_scd scd
          ON val.person_id = scd.person_id
         AND val.snapshot_date >= scd.valid_from
         AND val.snapshot_date <= scd.valid_to
        LEFT JOIN mart.dim_person person
          ON val.person_id = person.person_id
    """)
    print("    mart.fact_player_snapshot        (snapshot consumer view created)")




    con.execute("CHECKPOINT")
    con.close()
    print(f"  materialized in {time.time() - t0:.1f}s", flush=True)
    return len(tables)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career", default=C.DEFAULT_CAREER)
    ap.add_argument("--upload", action="store_true",
                    help="rclone copy to R2 (site-data/fm-<career>-mart.duckdb)")
    ap.add_argument("--out", help="write here instead of temp file")
    a = ap.parse_args()

    car = C.resolve_career(a.career)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if not os.path.exists(store):
        raise SystemExit(f"no store at {store} — build it first")

    con, used = _dbopen.open_readonly(store, tag="publish-mart")
    con.close()

    dest = a.out or os.path.join(tempfile.gettempdir(), f"fm-{car.key}-mart.duckdb")
    keep = bool(a.out)
    try:
        n_tabs = build(used, dest)
        size = os.path.getsize(dest)
        full = os.path.getsize(store)
        mb = size / 1024 / 1024
        print(f"\nmart store: {dest} ({mb:.1f} MB, {100 * size / full:.0f}% of {full / 1024 / 1024:.0f} MB full store)")

        if mb > MAX_MB:
            raise SystemExit(f"REFUSING: artefact is {mb:.1f} MB, exceeds {MAX_MB} MB ceiling.")

        if not a.upload:
            print("(not uploaded — pass --upload to push to R2)")
            return 0

        if shutil.which("rclone") is None:
            raise SystemExit("rclone not installed — cannot upload")

        remote = f"{R2_REMOTE}/site-data/fm-{car.key}-mart.duckdb"
        print(f"uploading {os.path.basename(dest)} ({mb:.1f} MB) to {remote} ...")
        t0 = time.time()
        r = subprocess.run(["rclone", "copyto", "--stats", "15s", "-v", dest, remote])
        if r.returncode != 0:
            raise SystemExit(f"upload failed with exit code {r.returncode}")
        elapsed = time.time() - t0
        speed = mb / max(elapsed, 0.1)
        print(f"uploaded in {elapsed:.1f}s ({speed:.1f} MB/s)")
    finally:
        if not keep and os.path.exists(dest):
            os.remove(dest)


if __name__ == "__main__":
    sys.exit(main())
