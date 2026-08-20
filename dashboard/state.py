"""Live shared state (scouting shortlist, saved scout reports) — one JSON object per entry,
mirrored between `state/` on disk and R2.

Why this exists. These are the only things in the project a human authors that aren't code: the
DuckDB store is derived (rebuildable from saves + seeds) and `output/` is regenerable, but a
shortlist entry typed on a phone exists nowhere else. It used to live in `staging.shortlist`
inside the store, which meant it was destroyed by any rebuild and invisible to a second machine.

Why one object per entry rather than one JSONL file. R2 has no append: writing to a shared file
means read-modify-write, so two devices adding a player at the same time silently loses one.
With `state/shortlist/<id>.json` per entry, adds can never collide, a delete is an object
delete, and syncing is a plain union — `rclone copy` in each direction, no merge logic and no
conflict resolution to get wrong. It's also what lets a Cloudflare Pages Function accept a
shortlist add from the phone: it PUTs one object and is done.

Degradation is deliberate: with no rclone binary or no configured remote, everything here works
against `state/` alone. A laptop in aeroplane mode shows the last-synced shortlist rather than
an error, and never blocks on the network.
"""
import json
import os
import shutil
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.environ.get("FM_STATE_DIR") or os.path.join(REPO, "state")
R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fm-parser")
PULL_TTL = int(os.environ.get("FM_STATE_TTL", "300"))       # seconds between remote pulls
KINDS = ("shortlist", "scouts")

_remote_ok = None                                            # probed once per process


def _kind_dir(kind, create=False):
    d = os.path.join(STATE_DIR, kind)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def remote_configured():
    """True if rclone exists and knows our remote. Probed once — `rclone listremotes` is a
    ~100ms subprocess and this gets asked on every page render."""
    global _remote_ok
    if _remote_ok is None:
        _remote_ok = False
        if os.environ.get("FM_STATE_OFFLINE") != "1" and shutil.which("rclone"):
            name = R2_REMOTE.split(":", 1)[0] + ":"
            try:
                r = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True,
                                   timeout=10)
                _remote_ok = r.returncode == 0 and name in r.stdout
            except (OSError, subprocess.SubprocessError):
                _remote_ok = False
    return _remote_ok


def _rclone(args, timeout=60):
    try:
        r = subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def _marker(kind):
    return os.path.join(_kind_dir(kind, create=True), ".last_pull")


def pull(kind, force=False):
    """Fetch remote entries we don't have. Throttled to once per PULL_TTL so a page render
    doesn't pay for a subprocess every time. `copy` (not `sync`) so it never deletes local
    entries — union merge is the whole point of one-object-per-entry."""
    if not remote_configured():
        return False
    m = _marker(kind)
    if not force and os.path.exists(m) and (time.time() - os.path.getmtime(m)) < PULL_TTL:
        return False
    ok, _err = _rclone(["copy", f"{R2_REMOTE}/state/{kind}", _kind_dir(kind, create=True)])
    open(m, "w").close()          # stamp even on failure, so we don't retry on every render
    return ok


def push(kind, key=None):
    """Upload one entry (or the whole kind). Called on write, since writes are rare and you
    want them to land immediately rather than at the next pull."""
    if not remote_configured():
        return False
    d = _kind_dir(kind, create=True)
    if key is not None:
        src = os.path.join(d, f"{key}.json")
        if not os.path.exists(src):
            return False
        ok, _ = _rclone(["copy", src, f"{R2_REMOTE}/state/{kind}/"])
        return ok
    ok, _ = _rclone(["copy", d, f"{R2_REMOTE}/state/{kind}", "--include", "*.json"])
    return ok


def entries(kind, sync=True):
    """[(key, payload)] for every entry, sorted by key. Unreadable files are skipped rather
    than raised: a half-synced object must not take the whole page down."""
    if sync:
        pull(kind)
    d = _kind_dir(kind)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                out.append((fn[:-5], json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def put(kind, key, payload):
    """Write one entry and push it. Atomic locally (write + replace) so a reader never sees
    a partial object."""
    d = _kind_dir(kind, create=True)
    path = os.path.join(d, f"{key}.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False, indent=1)
    os.replace(tmp, path)
    push(kind, key)
    return key


def delete(kind, key):
    """Remove an entry locally and remotely. The remote delete is the one operation a union
    merge can't express, so it has to be explicit — otherwise the next pull resurrects it."""
    path = os.path.join(_kind_dir(kind), f"{key}.json")
    if os.path.exists(path):
        os.remove(path)
    if remote_configured():
        _rclone(["deletefile", f"{R2_REMOTE}/state/{kind}/{key}.json"])
    return True


def new_key():
    """Microsecond timestamp as the entry id. Int-coercible (the Squad Tool casts it) and
    collision-free in practice — two devices would have to write in the same microsecond, and
    the worst case is one entry overwriting the other rather than any corruption."""
    return str(time.time_ns() // 1000)


def status():
    """{kind: count} plus remote reachability — for a diagnostics line in the UI."""
    return {"remote": R2_REMOTE if remote_configured() else None,
            "dir": STATE_DIR,
            **{k: len(entries(k, sync=False)) for k in KINDS}}
