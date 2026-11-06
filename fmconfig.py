#!/usr/bin/env python3
"""The user's config: `fmm.toml` at the repo root (or the path in `$FM_CONFIG`).

Everything that belongs to ONE player rather than to the project lives there: the careers
they manage, where their saves and published data go, and how they like to play (the
immersion switches). The file is gitignored; `fmm.example.toml` is the committed template.
Copy it to start:

    cp fmm.example.toml fmm.toml

Precedence, per setting: environment variable > fmm.toml > built-in default. So an
environment that already sets `FM_SAVES_DIR` / `FM_R2_REMOTE` / `FM_SITE_URL` keeps working
unchanged.

The parser (`fmparser/`, `extract.py`) never reads this: a save reads the same whoever owns it.
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache

REPO = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(REPO, "fmm.example.toml")


def config_path() -> str:
    return os.environ.get("FM_CONFIG") or os.path.join(REPO, "fmm.toml")


@lru_cache(maxsize=None)
def load() -> dict:
    """The parsed config, or {} when there is no file (a fresh clone)."""
    path = config_path()
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _get(section: str, key: str, env: str | None, default):
    if env and os.environ.get(env):
        return os.environ[env]
    return load().get(section, {}).get(key, default)


# --------------------------------------------------------------------------- storage / deploy
def saves_dir() -> str:
    """Where raw saves live, one folder per career (`<saves_dir>/<career>/`)."""
    return os.path.expanduser(_get("storage", "saves_dir", "FM_SAVES_DIR", "~/fm-saves"))


def r2_remote() -> str | None:
    """The rclone `remote:bucket` holding the save archive and the published data, or None
    when no remote is configured (everything that uploads then says so and skips)."""
    return _get("storage", "r2_remote", "FM_R2_REMOTE", None)


def require_r2_remote() -> str:
    """The remote, or a clear exit when an upload was asked for and none is configured."""
    r = r2_remote()
    if not r:
        raise SystemExit("no R2 remote configured: set [storage] r2_remote in fmm.toml "
                         "(or FM_R2_REMOTE), or drop --upload and keep it local.")
    return r


def site_url() -> str:
    """The deployed web app's base URL, written into index.json so an agent can follow links.
    Empty when not deployed: the export then writes relative links."""
    return (_get("site", "url", "FM_SITE_URL", "") or "").rstrip("/")


# --------------------------------------------------------------------------- play style
def hide_ability() -> bool:
    """Immersion: never surface the raw current/potential ability number.

    True (the default) makes the export refuse any raw-ability key in what it publishes, and
    tells agents to reason in percentiles, role fit and attributes instead. False is for a
    player who is happy to see the number: it lifts the export's guard and tells agents they
    may quote it (`FM_HIDE_ABILITY=0` does the same for one run). The site marts still ship
    percentiles only either way; the raw number stays in `mart.fact_player_snapshot`."""
    v = _get("immersion", "hide_ability", "FM_HIDE_ABILITY", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off")
    return bool(v)


def default_career() -> str | None:
    return _get("careers", "default", "FM_CAREER", None)


def career_tables() -> dict[str, dict]:
    """`[careers.<key>]` tables, each a dict of that career's settings."""
    return {k: v for k, v in load().get("careers", {}).items() if isinstance(v, dict)}
