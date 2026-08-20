"""Open a career store read-only even when a live dashboard holds the write lock.

DuckDB is single-writer: a running Streamlit owns the file, and a read_only connect still
fails against it. Every read-only tool therefore needs the same fallback — copy the store to
a temp path and read that. (`fmq.py cmd_scout` carries this inline; it predates this module.)
"""
import os
import shutil
import tempfile
import time

import duckdb

# A store written more recently than this is treated as having a live writer. Long enough to
# span the gap between two loads in a rebuild; short enough that an idle dashboard clears it.
QUIET_SECONDS = 90


def open_readonly(path, tag="tool", allow_dirty_copy=False):
    """(connection, path_actually_opened). Copies to a temp file if the store is locked, so
    the caller can report whether it read the live file or a snapshot of it.

    REFUSES the copy when a `<store>.wal` sits beside it. A byte copy of a DuckDB file that is
    mid-transaction is NOT transactionally consistent: it captures whatever happened to be
    durable, so a store being written by a rebuild reads back with an arbitrary subset of
    snapshots present. That cost real debugging time — a rebuild in progress looked like a
    finished rebuild with two failed snapshots. A dashboard idling on the file is fine (no
    .wal, nothing in flight); a writer mid-run is not. Pass allow_dirty_copy=True only if you
    genuinely want a best-effort read of a moving target."""
    src = os.path.abspath(path)
    try:
        return duckdb.connect(src, read_only=True), src
    except duckdb.Error:
        age = time.time() - os.path.getmtime(src)
        wal = os.path.exists(src + ".wal")
        if (wal or age < QUIET_SECONDS) and not allow_dirty_copy:
            why = f"{os.path.basename(src)}.wal exists" if wal else \
                  f"last written {age:.0f}s ago"
            raise RuntimeError(
                f"{os.path.basename(src)} looks like it is being WRITTEN right now ({why}) — "
                f"a byte copy would not be transactionally consistent, and would read back "
                f"with an arbitrary subset of snapshots. Wait for the writer to finish, or "
                f"pass allow_dirty_copy=True if you accept a partial view.\n"
                f"An idle dashboard holds the lock but does not touch mtime, so it clears this "
                f"check after {QUIET_SECONDS}s.")
        tmp = os.path.join(tempfile.gettempdir(), f"fm_{tag}_{os.path.basename(src)}")
        shutil.copy2(src, tmp)
        return duckdb.connect(tmp, read_only=True), tmp
