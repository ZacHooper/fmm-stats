"""Open a career store read-only even when a live dashboard holds the write lock.

DuckDB is single-writer: a running Streamlit owns the file, and a read_only connect still
fails against it. Every read-only tool therefore needs the same fallback — copy the store to
a temp path and read that. (`fmq.py cmd_scout` carries this inline; it predates this module.)
"""
import os
import shutil
import tempfile

import duckdb


def open_readonly(path, tag="tool"):
    """(connection, path_actually_opened). Copies to a temp file if the store is locked, so
    the caller can report whether it read the live file or a snapshot of it."""
    src = os.path.abspath(path)
    try:
        return duckdb.connect(src, read_only=True), src
    except duckdb.Error:
        tmp = os.path.join(tempfile.gettempdir(), f"fm_{tag}_{os.path.basename(src)}")
        shutil.copy2(src, tmp)
        return duckdb.connect(tmp, read_only=True), tmp
