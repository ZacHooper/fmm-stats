#!/usr/bin/env python3
"""The user's own files, kept in step with their copy in the object store.

    uv run python scripts/config_sync.py check   # does the local fmm.toml match the bucket's?
    uv run python scripts/config_sync.py pull    # bucket -> local (the canonical copy wins)
    uv run python scripts/config_sync.py push    # local -> bucket (after editing fmm.toml here)

`fmm.toml`, `CAREER.md`, `career-notes/` and `fmstats/known_answers/` are gitignored, so each
machine and each cloud session holds its own copy. The canonical copy is the one in
`<[storage] r2_remote>/config/`. A machine whose copy has gone stale builds a store that
silently disagrees with the career (an empty signing list publishes every player as outside
the rule), so everything that PUBLISHES checks two things first:

- `require_config_in_sync()`: the local `fmm.toml` is byte-identical to the bucket's. A
  difference stops the publish and says which way to sync: `pull` when the bucket is newer,
  `push` when the local edit is the one to keep.
- `require_store_matches_config()`: the store was seeded from that `fmm.toml`. The loader
  copies the career's settings into the store on every load and `--refresh-only`
  (`raw.app_config` career keys, `raw.eligible_origin_clubs`); a store built before the last
  edit still carries the old ones, and `load_duckdb.py --refresh-only` reseeds it.

With no remote configured or no rclone (a local-only player), the first check has nothing to
compare against and passes with a note; the second always runs.
"""
from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import fmconfig

# (local path relative to the repo, path under <remote>/config/, is a directory)
FILES = [("fmm.toml", "fmm.toml", False),
         ("CAREER.md", "CAREER.md", False),
         ("career-notes", "career-notes", True),
         (os.path.join("fmstats", "known_answers"), "known_answers", True)]


def _remote() -> str | None:
    r = fmconfig.r2_remote()
    if not r or shutil.which("rclone") is None:
        return None
    return r


def _rclone(*args, capture=True):
    return subprocess.run(["rclone", *args], capture_output=capture, text=True, check=False)


def remote_fmm_toml(remote: str) -> str | None:
    """The bucket's fmm.toml, or None when the bucket holds none. Exits when the bucket can't
    be read at all: a publish that can't see the canonical config must not guess."""
    r = _rclone("cat", f"{remote}/config/fmm.toml")
    if r.returncode == 0:
        return r.stdout
    if "not found" in (r.stderr or "").lower() or "doesn't exist" in (r.stderr or "").lower():
        return None
    raise SystemExit(f"could not read {remote}/config/fmm.toml to check the config is current:"
                     f" {(r.stderr or '').strip()[:300]}\n"
                     f"Fix rclone, or pass --skip-config-check if you are sure.")


def config_drift() -> tuple[str, str | None]:
    """('in-sync' | 'no-remote' | 'no-remote-copy' | 'no-local' | 'differs', diff text)."""
    remote = _remote()
    if remote is None:
        return "no-remote", None
    theirs = remote_fmm_toml(remote)
    if theirs is None:
        return "no-remote-copy", None
    path = fmconfig.config_path()
    if not os.path.exists(path):
        return "no-local", None
    with open(path, encoding="utf-8") as f:
        ours = f.read()
    if ours == theirs:
        return "in-sync", None
    diff = "".join(difflib.unified_diff(
        theirs.splitlines(keepends=True), ours.splitlines(keepends=True),
        fromfile=f"{remote}/config/fmm.toml", tofile="fmm.toml (local)"))
    return "differs", diff


def require_config_in_sync() -> None:
    """Stop a publish whose local fmm.toml is not the bucket's."""
    if os.environ.get("FM_CONFIG"):
        print(f"  config check: FM_CONFIG={os.environ['FM_CONFIG']} is set; not compared "
              f"with the bucket")
        return
    state, diff = config_drift()
    if state == "in-sync":
        print("  config check: fmm.toml matches the bucket's ✓")
    elif state == "no-remote":
        print("  config check: no R2 remote or rclone; fmm.toml not compared")
    elif state == "no-remote-copy":
        print("  config check: the bucket holds no config/fmm.toml; "
              "`scripts/config_sync.py push` puts this one there")
    else:
        msg = ("there is no local fmm.toml" if state == "no-local"
               else "the local fmm.toml differs from the bucket's:\n\n" + diff)
        raise SystemExit(
            f"REFUSING TO PUBLISH: {msg}\n"
            "The bucket's copy is canonical. Either\n"
            "  uv run python scripts/config_sync.py pull     # take the bucket's (usual case)\n"
            "  uv run python scripts/config_sync.py push     # keep the local edit\n"
            "then reseed the store: uv run python load_duckdb.py --refresh-only "
            "--db <store> --career <key>, and publish again.")


def store_config_drift(con, car) -> list[str]:
    """How the store's seeded career settings differ from `car` (fmm.toml), one line each."""
    import load_duckdb as L
    want = dict(L.career_app_config(car))
    have = dict(con.execute("SELECT key, value FROM raw.app_config "
                            "WHERE key IN (" + ", ".join("?" * len(want)) + ")",
                            list(want)).fetchall())
    out = [f"{k}: store {have.get(k)!r}, fmm.toml {v!r}"
           for k, v in want.items() if have.get(k) != v]
    stored = set(con.execute("SELECT club_tid, region FROM raw.eligible_origin_clubs")
                 .fetchall())
    wanted = set(car.eligible_origin_clubs)
    if stored != wanted:
        out.append(f"eligible_origin_clubs: store has {len(stored)} clubs, fmm.toml "
                   f"{len(wanted)} (missing {sorted(t for t, _ in wanted - stored)}, "
                   f"extra {sorted(t for t, _ in stored - wanted)})")
    return out


def require_store_matches_config(con, car, store: str) -> None:
    """Stop a publish from a store seeded with other career settings than fmm.toml's."""
    drift = store_config_drift(con, car)
    if not drift:
        print("  config check: the store was seeded from this fmm.toml ✓")
        return
    raise SystemExit(
        "REFUSING: the store's career settings are not fmm.toml's:\n  "
        + "\n  ".join(drift)
        + f"\nReseed it: uv run python load_duckdb.py --refresh-only --db {store} "
          f"--career {car.key}")


# --------------------------------------------------------------------------- CLI
def _sync(direction: str) -> int:
    remote = fmconfig.r2_remote()
    if not remote:
        raise SystemExit("no R2 remote configured ([storage] r2_remote or FM_R2_REMOTE)")
    if shutil.which("rclone") is None:
        raise SystemExit("rclone not installed")
    for local, name, is_dir in FILES:
        lp, rp = os.path.join(REPO, local), f"{remote}/config/{name}"
        src, dst = (rp, lp) if direction == "pull" else (lp, rp)
        if direction == "push" and not os.path.exists(lp):
            continue
        if direction == "pull" and not is_dir and os.path.exists(lp):
            # keep the copy being replaced, in case it held an edit nobody pushed
            r = _rclone("cat", rp)
            if r.returncode == 0:
                with open(lp, encoding="utf-8") as f:
                    if f.read() != r.stdout:
                        shutil.copy2(lp, lp + ".replaced")
                        print(f"  {local}: local copy differed; kept as {local}.replaced")
        r = _rclone("copy" if is_dir else "copyto", src, dst, capture=False)
        if r.returncode != 0:
            print(f"  ! {local}: rclone failed ({r.returncode})")
            return 1
        print(f"  {direction}ed {local}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["check", "pull", "push"])
    a = ap.parse_args()
    if a.action == "check":
        state, diff = config_drift()
        print({"in-sync": "fmm.toml matches the bucket's",
               "no-remote": "no R2 remote or rclone: nothing to compare",
               "no-remote-copy": "the bucket holds no config/fmm.toml",
               "no-local": "no local fmm.toml (pull to fetch it)",
               "differs": "fmm.toml differs from the bucket's:\n\n" + (diff or "")}[state])
        return 0 if state in ("in-sync", "no-remote", "no-remote-copy") else 1
    return _sync(a.action)


if __name__ == "__main__":
    sys.exit(main())
