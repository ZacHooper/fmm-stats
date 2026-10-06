import subprocess
import sys


def test_rebuild_dry_run_flags():
    res = subprocess.run([sys.executable, "scripts/rebuild.py", "--career", "frem", "--dry-run"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "would rebuild" in res.stdout
    assert "load_duckdb.py" in res.stdout
    assert "--skip-views" in res.stdout


def test_load_duckdb_skip_views_flag():
    res = subprocess.run([sys.executable, "load_duckdb.py", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "--skip-views" in res.stdout
    assert "--refresh-only" in res.stdout
