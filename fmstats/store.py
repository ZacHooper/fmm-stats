"""Which copy of a career store a query reads, and how fresh it is.

The default is the PUBLISHED full store — `site-data/fm-<career>.duckdb` on R2, written by
`scripts/publish_duckdb.py --upload` — cached at `$FM_CACHE_DIR` (default
`~/.cache/fmm-stats/`). A fresh clone has no local store and building one takes ~1 min per
snapshot, while the published copy downloads in seconds and carries everything a query needs:
`mart`, `staging` and the method-dependent rating layer.

The cache is re-checked against R2 at most once per `FM_STORE_TTL` seconds (default 600), and
only re-downloaded when the remote object's size or modification time differs. The download
lands on a `.part` file and is renamed into place, so an interrupted transfer never leaves a
truncated store where a reader would open it.

Resolution order:
  1. an explicit path (`--db` / `$FM_DUCKDB`) — e.g. a store you just rebuilt locally;
  2. the R2 cache, refreshed if stale (skipped with `offline=True` / `$FM_STATE_OFFLINE=1`);
  3. the cache as it stands, if R2 cannot be reached;
  4. a repo-local `fm-<career>.duckdb`, if one exists.

A career is a key naming a store file, `fm-<key>.duckdb`; everything else about it — the club
we manage, its reserve side, the tactic we are rated on — is read from the store it opens
(`Career.from_store`). fmstats never imports the parser.

The published copy is only as fresh as the last publish, which is a manual step after an
import, so `describe()` names the snapshot date alongside the source on every run.

The `mart` schema is a layer of VIEW definitions over `staging`, so the published copy carries
whatever definitions the publishing machine had. The cache is ours, so after each download —
and whenever `fmstats/mart.py` changes — `open_store` re-creates the mart on it from this
checkout's definitions. The data is untouched; only the views are. An explicit `--db` store is
never modified: when it predates the current definitions, open_store says which command
refreshes it.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass

import duckdb

from fmstats.mart import MACROS, ORDER, create_mart
from fmstats import state
from fmstats.dbopen import open_readonly

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("FM_CACHE_DIR") or os.path.join(
    os.path.expanduser("~"), ".cache", "fmm-stats")
STORE_TTL = int(os.environ.get("FM_STORE_TTL", "600"))
DEFAULT_CAREER = "frem"
MART_VERSION = hashlib.sha256(
    "\x00".join([*MACROS, *(sql for _, sql in ORDER)]).encode()).hexdigest()[:16]
# staging tables the loader seeds that the current mart reads; a store published before one
# existed cannot have its mart refreshed until it is re-seeded
_MART_INPUTS = ("event_types",)
# a view every current consumer needs; its absence means the store's mart is out of date
_PROBE_VIEW = "player_vs_club"


@dataclass
class Career:
    """The career a store holds, read from the store itself."""
    key: str                        # as the loader recorded it, else the key it was opened by
    name: str
    managed_tid: int
    reserve_tid: int | None
    rating_method: str | None       # the tactic we play; None -> app_config default_method

    @property
    def db(self):
        return store_file(self.key)

    @classmethod
    def from_store(cls, con, key):
        """Our club and reserve side from the mart's data-derived views; the key and the
        tactic from the `career_*` keys the loader writes to staging.app_config."""
        managed = con.execute("SELECT club_tid FROM mart.managed_club").fetchone()
        if managed is None:
            raise SystemExit("the store has no managed club (mart.managed_club is empty)")
        managed = managed[0]
        reserve = con.execute("SELECT min(club_tid) FROM mart.reserve_clubs").fetchone()[0]
        name = con.execute("SELECT name FROM mart.clubs WHERE club_tid = ? "
                           "ORDER BY season DESC, phase DESC LIMIT 1", [managed]).fetchone()
        cfg = dict(con.execute("SELECT key, value FROM staging.app_config "
                               "WHERE key IN ('career_key', 'career_rating_method')").fetchall())
        stored = cfg.get("career_key")
        if stored is None:
            print("store: note — the loader has not recorded this store's career "
                  "(staging.app_config career_*), so the tactic falls back to "
                  "app_config.default_method; `load_duckdb.py --refresh-only` records it",
                  file=sys.stderr)
        elif stored != key:
            print(f"store: note — this store records career '{stored}', not '{key}'",
                  file=sys.stderr)
        return cls(stored or key, name[0] if name else f"club {managed}", managed, reserve,
                   cfg.get("career_rating_method"))


def store_file(key):
    return f"fm-{key}.duckdb"


@dataclass
class Store:
    con: object
    path: str
    source: str             # "explicit" | "r2" | "r2-cache-stale" | "repo"
    career: Career
    season: int
    phase: str
    phase_date: object
    label: str

    def describe(self):
        where = {"explicit": "local file",
                 "r2": "R2 published copy",
                 "r2-cache-stale": "R2 published copy (cached; could not re-check R2)",
                 "repo": "repo-local store"}[self.source]
        return (f"store: {where} · snapshot {self.phase_date} ({self.label}) · "
                f"{self.career.name} · {self.path}")


def _remote_meta(name):
    """(size, modtime-iso) of site-data/<name> on R2, or None if it cannot be read."""
    try:
        r = subprocess.run(["rclone", "lsjson", f"{state.R2_REMOTE}/site-data/{name}"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        rows = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return (rows[0]["Size"], rows[0]["ModTime"]) if rows else None


def _stamp(path):
    return path + ".meta.json"


def _refresh_cache(name, force=False):
    """Bring CACHE_DIR/<name> in line with R2. Returns True if the cache now matches R2,
    False if R2 could not be checked (the cache, if any, is left as it was)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    local = os.path.join(CACHE_DIR, name)
    stamp = _stamp(local)
    try:
        with open(stamp, encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, json.JSONDecodeError):
        seen = {}
    fresh = (os.path.exists(local) and not force
             and time.time() - seen.get("checked_at", 0) < STORE_TTL)
    if fresh:
        return True
    meta = _remote_meta(name)
    if meta is None:
        return False
    size, modtime = meta
    # compared against what R2 reported at download time, not the file on disk: refreshing the
    # mart views writes to the cached file and changes its size
    if not (os.path.exists(local) and seen.get("size") == size
            and seen.get("modtime") == modtime):
        part = local + ".part"
        print(f"store: downloading {name} from R2 ({size / 2**20:.0f} MB)…", file=sys.stderr)
        r = subprocess.run(["rclone", "copyto", f"{state.R2_REMOTE}/site-data/{name}", part],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not os.path.exists(part) or os.path.getsize(part) != size:
            print(f"store: download failed — {(r.stderr or '').strip()[:300]}", file=sys.stderr)
            if os.path.exists(part):
                os.remove(part)
            return False
        os.replace(part, local)
        seen.pop("mart_version", None)
    seen.update({"size": size, "modtime": modtime, "checked_at": time.time()})
    with open(stamp, "w", encoding="utf-8") as f:
        json.dump(seen, f)
    return True


def _sync_mart(path):
    """Re-create the mart views on a cached store when they were built from different
    definitions than this checkout's. Returns False (and leaves the store as it was) when the
    file cannot be opened for writing, e.g. another process has it open."""
    stamp = _stamp(path)
    try:
        with open(stamp, encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, json.JSONDecodeError):
        seen = {}
    if seen.get("mart_version") == MART_VERSION:
        return True
    try:
        con = duckdb.connect(path)
    except duckdb.Error as e:
        print(f"store: could not refresh the mart definitions on {path} ({e}); reading it as "
              f"published.", file=sys.stderr)
        return False
    try:
        missing = [t for t in _MART_INPUTS if not con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'staging' "
            "AND table_name = ?", [t]).fetchone()]
        if missing:
            print(f"store: {path} predates staging.{', staging.'.join(missing)}, which the "
                  f"current mart reads; reading it as published. Fix it with `uv run python "
                  f"load_duckdb.py --refresh-only --db {path}`, or republish the store.",
                  file=sys.stderr)
            return False
        # one transaction, so a definition that fails to bind leaves the published mart whole
        con.execute("BEGIN")
        try:
            create_mart(con)
            con.execute("COMMIT")
        except duckdb.Error:
            con.execute("ROLLBACK")
            raise
        con.execute("CHECKPOINT")
    finally:
        con.close()
    seen["mart_version"] = MART_VERSION
    with open(stamp, "w", encoding="utf-8") as f:
        json.dump(seen, f)
    return True


def resolve_path(career=None, db=None, refresh=False, offline=False):
    """(career key, path, source) without opening anything."""
    key = career or os.environ.get("FM_CAREER") or DEFAULT_CAREER
    name = store_file(key)
    explicit = db or os.environ.get("FM_DUCKDB")
    if explicit:
        path = os.path.abspath(explicit)
        if not os.path.exists(path):
            raise SystemExit(f"no store at {path}")
        return key, path, "explicit"
    cached = os.path.join(CACHE_DIR, name)
    offline = offline or os.environ.get("FM_STATE_OFFLINE") == "1"
    if not offline and state.remote_configured():
        if _refresh_cache(name, force=refresh):
            return key, cached, "r2"
    if os.path.exists(cached):
        return key, cached, "r2-cache-stale"
    repo_store = os.path.join(REPO, name)
    if os.path.exists(repo_store):
        return key, repo_store, "repo"
    raise SystemExit(
        f"no store for career '{key}'. Either configure rclone with the R2 remote "
        f"'{state.R2_REMOTE.split(':')[0]}:' (the session-start hook does this on Claude Code "
        f"web) so {name} can be fetched from site-data/, or build one locally with "
        f"`uv run python scripts/rebuild.py --career {key}` and pass --db.")


def open_store(career=None, db=None, refresh=False, offline=False, announce=True):
    """Open the career's store read-only and return a Store. `announce` prints describe() to
    stderr so every answer says which data it came from."""
    key, path, source = resolve_path(career, db, refresh, offline)
    if source.startswith("r2"):
        _sync_mart(path)
    con, used = open_readonly(path, tag="fmq")
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = 'mart' "
                       "AND table_name = ?", [_PROBE_VIEW]).fetchone():
        print(f"store: {path} predates the current mart definitions (no mart.{_PROBE_VIEW}); "
              f"refresh it with `uv run python load_duckdb.py --refresh-only --db {path}`.",
              file=sys.stderr)
    row = con.execute("SELECT season, phase, phase_date, label FROM mart.snapshots "
                      "ORDER BY snap_ix DESC LIMIT 1").fetchone()
    if row is None:
        raise SystemExit(f"{path} has no snapshots loaded")
    car = Career.from_store(con, key)
    st = Store(con, used, source, car, int(row[0]), row[1], row[2], row[3])
    if announce:
        print(st.describe(), file=sys.stderr)
        repo_store = os.path.join(REPO, car.db)
        if source.startswith("r2") and os.path.exists(repo_store) \
                and os.path.getmtime(repo_store) > os.path.getmtime(path):
            when = datetime.datetime.fromtimestamp(os.path.getmtime(repo_store))
            print(f"store: note — {car.db} in the repo was modified {when:%Y-%m-%d %H:%M}, "
                  f"after this cached copy; pass --db {car.db} to read it instead.",
                  file=sys.stderr)
    return st
