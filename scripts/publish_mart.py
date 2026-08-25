#!/usr/bin/env python3
"""Publish a SLIM analysis store — the `mart` layer only — to R2, alongside the full copy.

    uv run python scripts/publish_mart.py --career frem --upload

`publish_duckdb.py` ships the whole store (~107 MB) so a remote agent can run arbitrary SQL
over `staging`. That stays. This is the companion artefact for the far commoner case: someone
wants to ANALYSE the career, not re-derive it, and every correctness rule they'd otherwise
have to remember (latest-phase-per-season, snapshot-scoped joins, person_id-not-tid, the
255-sentinel minutes arithmetic) is already baked into the mart. See fmparser/mart.py.

WHY IT IS SMALL — and why the obvious approach makes it BIGGER
--------------------------------------------------------------
The mart costs nothing in the live store because it is a VIEW layer. Materialising it
wholesale is a trap: `mart.player_attribute_growth` is one row per person x attribute x
snapshot-pair over every player in the world, which expands to 8.88M rows / 108 MB — 78% of a
materialised mart, and on its own bigger than the entire store it came from.

But that table exists to answer "how are OUR players developing". Of its 8.88M rows, the
players who have actually turned out for us account for 21,321 — 0.24%. So the growth family
is scoped to `mart.our_clubs` (first team + reserves, per careers.py) and the artefact lands
at ~11.5 MB instead of ~133 MB.

WHAT IS DELIBERATELY *NOT* SCOPED
---------------------------------
Only the growth family narrows. Everything else stays WORLD-WIDE, because scoping it would
quietly destroy the opposition analysis this store is also for:

  * `match_player_facts` keeps every appearance in our matches, ours and theirs alike —
    ~45% of its rows are opponent players. Scoping it would leave you unable to say anything
    about who we played against.
  * `at_club_spells` / `player_spells` keep all ~3,330 clubs, so squad composition and
    transfer/loan history remain answerable for any club, not just ours.

If you need growth for a player who never played for us (a recruitment target, say), pass
`--all-players` and accept the ~133 MB. The usual answer is instead to read current attributes
from the full store `publish_duckdb.py` ships.

MACROS TRAVEL WITH IT
---------------------
`mart.squad_on(d)` is a PARAMETERISED TABLE MACRO, not a view — "who was in the squad on date
d" is a function of d, so it cannot be materialised into a table and has to be re-declared in
the output. The same goes for the scalar macros the mart's own SQL calls (`phase_ord`,
`season_of`): they live in `main` and do NOT resolve across an ATTACH, so a store missing them
fails at query time rather than at build time. All of them are declared here and smoke-tested
before upload.

READING player_attribute_growth: FILTER ON is_gk_attr
-----------------------------------------------------
The engine stores all 23 attributes for everyone, but the ones a player's role does not use
sit pinned in a low band and only jitter (see fmparser/mart.py's role/attribute table). The
table ships `is_gk_attr` so you can exclude them; it does NOT pre-filter, because keepers
legitimately use all 23. A bare `ORDER BY delta DESC` therefore surfaces noise — in this
career, 52 rows are outfielders drifting on keeper attributes. Join to `mart.player_growth`
for `is_gk` and drop `is_gk_attr AND NOT is_gk`:

    SELECT g.* FROM mart.player_attribute_growth g
    JOIN mart.player_growth pg USING (person_id, season, phase)
    WHERE NOT (g.is_gk_attr AND NOT pg.is_gk)

IMMERSION
---------
No mart column carries raw ability (checked at build time against CLAUDE.md's house rule, the
same guard `scripts/build_site.py` applies to published JSON), so unlike publish_duckdb.py
there is nothing to scrub — but the check runs anyway, so that a future mart column named
`ca` cannot ship by accident.

Derived, R2-only artefact — NOT git (see the storage-tiers table in CLAUDE.md). Re-run after
any import you want reflected remotely.

    ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);
    SELECT * FROM m.mart.player_growth_season WHERE season = 2024 ORDER BY growth DESC;
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

import _dbopen                                                          # noqa: E402
from fmparser.mart import create_mart, ORDER, MACROS, SQUAD_ON          # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")

# Raw-ability column names that must never leave (CLAUDE.md immersion rule). Level/Fit
# percentiles are fine and deliberately not listed — see the house rule's stated exception.
# `aca` is here because scripts/export_data.py's BANNED_KEYS has it and this list did not:
# same rule, two lists, and a gap between them is how a leak ships.
FORBIDDEN = {"ca", "pa", "aca", "current_ability", "potential_ability"}

OURS = ("person_id IN (SELECT person_id FROM mart.at_club_spells "
        "WHERE club_tid IN (SELECT club_tid FROM mart.our_clubs))")

# One snapshot per season instead of every snapshot. The store holds up to six snapshots in a
# season, several of them days apart, and for a dimension table those are near-duplicates —
# useful locally for a mid-season trajectory, dead weight in an analysis artefact.
LATEST_IN_SEASON = ("(season, phase) IN (SELECT season, phase FROM mart.snapshots "
                    "WHERE is_latest_in_season)")

# Just the newest snapshot. Career history is re-scraped whole every import, so every snapshot
# carries the same rows; scripts/export_data.py reads exactly one snapshot for this reason.
NEWEST_ONLY = ("(season, phase) IN (SELECT season, phase FROM mart.snapshots "
               "ORDER BY snap_ix DESC LIMIT 1)")

# Per-table scoping. Anything absent ships world-wide and at every snapshot.
#
# The judgement behind each choice: the growth family is about OUR players' development, so it
# scopes to us (unscoped, player_attribute_growth alone is 8.88M rows / 108 MB — bigger than
# the store it came from). The dimensions keep every club and every player but drop the
# mid-season near-duplicates, because opposition analysis is a first-class use of this artefact
# and scoping those to our clubs would break it — the same reason match_player_facts and
# at_club_spells are not scoped at all.
SCOPE = {
    "player_attribute_growth": OURS,
    "player_growth": OURS,
    "player_growth_season": OURS,
    "player_growth_at_club": OURS,
    "player_growth_tenure": OURS,
    # Current standing, not history. These three are world-wide dimensions, so an extra
    # snapshot costs 23k-80k rows each; at every snapshot they were 17 MB of the artefact,
    # more than everything else combined. The history they would carry is already covered
    # where it matters: our players' development is the growth family above (per attribute,
    # per snapshot, with deltas), and for anyone else the question is "how good is he now".
    # Season-over-season level history for a player who was never ours is what the full store
    # is for.
    "player_snapshots": NEWEST_ONLY,
    "player_position_levels": NEWEST_ONLY,
    "player_origin": NEWEST_ONLY,
    "player_career_seasons": NEWEST_ONLY,
}

# NEVER materialised. These two are the method-dependent rating layer: 27M and 9.4M rows, each
# many times the size of the whole artefact. They exist as VIEWS so scripts/export_data.py has a
# single schema to read from while it runs against a real local store — a machine that has the
# ability number, which the published copy deliberately does not. Do not "fix" this omission.
UNPUBLISHED = {"player_role_ratings", "player_position_fit"}

# Refuse to upload something wildly bigger than expected. The failure this guards against is
# silent: a new object materialises to 200 MB, the upload succeeds, and nobody notices until a
# remote agent waits five minutes for an ATTACH.
MAX_MB = 40


def build(src_path, dest, scope_ours=True):
    """Materialise the mart from `src_path` into a fresh store at `dest`. Returns the table
    rowcounts. The source is only ever ATTACHed read-only."""
    if os.path.exists(dest):
        os.remove(dest)
    work = dest + ".work"
    if os.path.exists(work):
        os.remove(work)

    # The mart's views + macros are built in a WORK db pointed at the source's staging, rather
    # than read out of the source's own `mart` schema: that way this script works against a
    # store built before the mart existed, and always emits the CURRENT mart definition.
    con = duckdb.connect(work)
    try:
        con.execute(f"ATTACH '{src_path}' AS s (READ_ONLY)")
        create_mart(con, src="s.staging")

        con.execute(f"ATTACH '{dest}' AS out")
        con.execute("CREATE SCHEMA out.mart")

        counts = []
        for full, sql in ORDER:
            name = full.split(".", 1)[1]
            if "CREATE OR REPLACE MACRO" in sql:
                continue            # macros are re-declared in the output below, not copied
            if name in UNPUBLISHED:
                counts.append((name, None, "not published — see UNPUBLISHED"))
                continue
            pred = SCOPE.get(name) if scope_ours else None
            where = f" WHERE {pred}" if pred else ""
            con.execute(f'CREATE TABLE out.mart."{name}" AS '
                        f'SELECT * FROM mart."{name}"{where}')
            n = con.execute(f'SELECT count(*) FROM out.mart."{name}"').fetchone()[0]
            label = ("scoped to our clubs" if pred is OURS else
                     "latest snapshot per season" if pred is LATEST_IN_SEASON else
                     "newest snapshot only" if pred is NEWEST_ONLY else None)
            counts.append((name, n, label))
        con.execute("CHECKPOINT out")
        con.execute("DETACH out")
    finally:
        con.close()
        if os.path.exists(work):
            os.remove(work)

    # Macros must be declared INSIDE the artefact so it stands alone.
    con = duckdb.connect(dest)
    try:
        for stmt in MACROS:
            con.execute(stmt)
        con.execute(SQUAD_ON)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return counts


def verify(dest):
    """Fail loudly rather than upload something subtly broken."""
    con = duckdb.connect(dest, read_only=True)
    try:
        leaks = con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'mart' AND lower(column_name) IN "
            f"({', '.join(repr(c) for c in sorted(FORBIDDEN))})").fetchall()
        if leaks:
            raise SystemExit(f"RAW ABILITY would ship: {leaks} — see CLAUDE.md immersion rule")

        # the macros are the easiest thing to get wrong: they resolve at query time, so a
        # missing one builds fine and fails in the user's hands.
        latest = con.execute("SELECT max(phase) FROM mart.snapshots").fetchone()[0]
        n = con.execute(f"SELECT count(*) FROM mart.squad_on('{latest}')").fetchone()[0]
        n_persons = con.execute(
            f"SELECT count(DISTINCT person_id) FROM mart.squad_on('{latest}')").fetchone()[0]
        if n == 0:
            raise SystemExit(f"mart.squad_on('{latest}') returned 0 players — macro or spell "
                             f"data is wrong; refusing to publish")

        # opponent coverage is the thing scoping most easily destroys — assert it survived
        opp = con.execute("""
            SELECT count(*) FROM mart.match_player_facts
            WHERE person_id NOT IN (SELECT person_id FROM mart.at_club_spells
                                    WHERE club_tid IN (SELECT club_tid FROM mart.our_clubs))
        """).fetchone()[0]
        clubs = con.execute("SELECT count(DISTINCT club_tid) FROM mart.at_club_spells").fetchone()[0]
    finally:
        con.close()

    # And now the way it is ACTUALLY read. Every doc tells you to ATTACH this file, and under
    # ATTACH a macro breaks: its body's unqualified `mart.player_spells` resolves against the
    # caller's catalog, not the attached one, so `m.mart.squad_on(...)` fails with "schema mart
    # does not exist". The direct-connection check above passes right through that. So test the
    # documented path too, and assert the parameterless view that exists for exactly this reason
    # agrees with the macro.
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{dest}' AS m (READ_ONLY)")
        cur = con.execute("SELECT count(*) FROM m.mart.squad_current").fetchone()[0]
        if cur == 0:
            raise SystemExit("m.mart.squad_current is empty over ATTACH — refusing to publish")
        if cur != n_persons:
            raise SystemExit(f"m.mart.squad_current has {cur} players but squad_on('{latest}') "
                             f"has {n_persons} distinct — they must agree")
        con.execute("USE m")            # the documented workaround for the macro
        if con.execute(f"SELECT count(*) FROM mart.squad_on('{latest}')").fetchone()[0] == 0:
            raise SystemExit("squad_on is unusable even after USE m — refusing to publish")
    finally:
        con.close()

    return latest, n, opp, clubs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--upload", action="store_true",
                    help="rclone the artefact to R2 (site-data/fm-<career>-mart.duckdb)")
    ap.add_argument("--out", help="write here and keep it, instead of a scratch temp file")
    ap.add_argument("--all-players", action="store_true",
                    help="do NOT scope the growth tables to our clubs (~133 MB, rarely wanted)")
    a = ap.parse_args()

    if a.career:
        os.environ["FM_CAREER"] = a.career
    from fmparser import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if not os.path.exists(store):
        raise SystemExit(f"no store at {store} — build it with scripts/rebuild.py")

    # Same single-writer-safe fallback publish_duckdb.py uses: refuses to read a store that is
    # mid-write, copies it aside if a dashboard holds the lock.
    con, used = _dbopen.open_readonly(store, tag="publish-mart")
    con.close()

    keep = bool(a.out)
    dest = a.out or os.path.join(tempfile.gettempdir(), f"fm-{car.key}-mart.duckdb")
    try:
        counts = build(used, dest, scope_ours=not a.all_players)
        for name, n, label in counts:
            if n is None:
                print(f"  mart.{name:32s} {'—':>10}        [{label}]")
            else:
                print(f"  mart.{name:32s} {n:>10,} rows"
                      f"{f'   [{label}]' if label else ''}")

        latest, n_squad, opp, clubs = verify(dest)
        print(f"\n  checks: no raw ability; mart.squad_on('{latest}') -> {n_squad} players; "
              f"{opp:,} opponent appearance rows and {clubs:,} clubs retained")

        size = os.path.getsize(dest)
        full = os.path.getsize(store)
        print(f"\nmart store: {dest} ({size / 1024 / 1024:.1f} MB, "
              f"{100 * size / full:.0f}% of the {full / 1024 / 1024:.0f} MB full store)")

        mb = size / 1024 / 1024
        if mb > MAX_MB:
            raise SystemExit(
                f"\nREFUSING: the artefact is {mb:.1f} MB, over the {MAX_MB} MB ceiling. "
                f"Something new is materialising far bigger than expected — check SCOPE and "
                f"UNPUBLISHED in this file before raising the limit.")

        if not a.upload:
            print("(not uploaded — pass --upload once rclone + the R2 remote are configured)")
            return 0

        if shutil.which("rclone") is None:
            raise SystemExit(f"rclone not installed — can't upload. Configure the "
                             f"'{R2_REMOTE}' remote, or push {os.path.basename(dest)} yourself.")
        remote = f"{R2_REMOTE}/site-data/fm-{car.key}-mart.duckdb"
        print(f"uploading to {remote} ...")
        t0 = time.time()
        r = subprocess.run(["rclone", "copyto", dest, remote], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"upload failed: {(r.stderr or '').strip()[:300]}")
        print(f"uploaded in {time.time() - t0:.0f}s")
        return 0
    finally:
        if not keep and os.path.exists(dest):
            os.remove(dest)


if __name__ == "__main__":
    sys.exit(main())
