---
name: get-started
description: Set up fmm-stats from scratch for a new player and show them their own Football Manager Mobile 2022 career — install what's needed, find their club in their save, build the store and open the stats site. Use when someone has just cloned the repo, says "get started", "set this up", "here's my save", or has no fmm.toml yet. The player does not need to know how to code; you run everything.
---

# Get started: from a save file to your stats site

The player hands you a `.fms` save; you do the rest. Talk to them in plain language, not
commands. Run every step yourself and only ask them for what only they can do: copy the save off
their phone, and confirm their club.

## 0. Already set up?
If `fmm.toml` exists and names a career, this isn't a first run: use `import-fm-saves` to add
a new save instead.

## 1. Get the save
Ask where their save is. If they don't have it on the computer yet, walk them through it
(iPhone and Mac):

1. Plug the iPhone into the Mac with a cable, and unlock it (tap **Trust** if asked).
2. Open **Finder** and click the iPhone in the sidebar.
3. Open the **Files** tab and expand **FMM22**.
4. Drag the save file (`.fms`) onto the Mac, e.g. into **Downloads**.

Saves from one career, taken at different points in the game, each become a snapshot, so more
saves means growth and history. Any of them works to start with; the newest is best.

## 2. Install the tools
The project runs under [uv](https://docs.astral.sh/uv/), which also fetches the right Python.

```bash
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh   # then open a new shell
uv sync                                                            # a minute or two, once
```

## 3. Find their club
```bash
uv run python scripts/discover_career.py "<path to the save>" --write
```
It reads the club from the save and writes it into `fmm.toml`. Tell the player the club name it
found and check it's theirs. The career **key** it prints (`[careers.<key>]`) is used below.

If it finds no club, show them the list it printed and ask which is theirs; then write the
`[careers.<key>]` table into `fmm.toml` by hand, following `fmm.example.toml`.

The season rollover defaults to 30 June. If their league isn't European, ask roughly when their
in-game season starts and set `rollover` to match.

## 4. Build their database
```bash
uv run python scripts/archive_save.py "<path to the save>" --career <key>   # files it by its in-game date
uv run python extract.py ~/fm-saves/<key>/<key>-<date>.fms                  # the file archive_save made
uv run python load_duckdb.py output/<key>-<date>
```
The load builds the store and runs every check, about a minute. It must end with
`done: 1 loaded, 0 failed`. If it fails, show the error to the player as "something went wrong
reading your save", and report the failing step and message: a first load passing is part of
the project's contract (see `AGENTS.md`).

## 5. Show them
```bash
uv run python scripts/export_data.py
uv run python -m http.server -d site 8000
```
Open <http://localhost:8000> for them. Then tell them what they can ask you next, for example:
- "Scout my next opponent" (`scout-opponent`)
- "Who should start?" (`preseason-squad-review`)
- "Review my season" (`fm-season-review`)
- any question about their squad, matches or the world (`query-fm-data`)

## Adding more saves later
Use `import-fm-saves`. Putting the site online so it works on their phone is optional and
needs a Cloudflare account: `docs/DEPLOY.md`.
