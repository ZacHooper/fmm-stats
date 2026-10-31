#!/usr/bin/env python3
"""
Print a competition's rules as an indented tagged tree, with round-name ids resolved.

A competition's rules exist twice in a save: as a rule file in the data dictionary
(`fmparser/tables/rule_files.py`, named by its `file` string, e.g. `eur_champions_cup_2021`)
and, for a loaded competition, as the archive member `comp_<uid>.dat`
(`fmparser/tables/comp_rules.py`): a 54-byte header, the same tagged block byte-for-byte,
then binary runtime state that is not decoded. See `docs/competition-formats.md`.

    uv run python scripts/audit/dump_comp_rules.py <save.fms> --uid 1301394      # archive member
    uv run python scripts/audit/dump_comp_rules.py <save.fms> --file usa_mls_2022 # dictionary
    uv run python scripts/audit/dump_comp_rules.py <save.fms> --file eur_champions_cup_2021 --tags stgs
    uv run python scripts/audit/dump_comp_rules.py <save.fms> --find exlg          # who uses a tag
    uv run python scripts/audit/dump_comp_rules.py <save.fms> --file inter_concacaf_nations_league_qual --grid

`--grid` reads a stage's `cftp` fixture grid (one list per matchday, `tNNN` = slot NNN's
opponent; a value v >= 128 is an away match at slot 256 - v) and checks it is a valid
schedule: every pairing mirrored, and each slot's home count and distinct opponents.
"""
import argparse
import mmap
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fmparser.core import archive as A                    # noqa: E402
from fmparser.core.types import read_tree                 # noqa: E402
from fmparser.tables import comp_rules as CR              # noqa: E402
from fmparser.tables import rounds as R                   # noqa: E402
from fmparser.tables import rule_files as RF              # noqa: E402

NAME_TAGS = {"stnm", "stgn", "nmsn", "nssn", "mnsn", "sbsn", "pvrn"}
AWAY = 128


def member_fields(mm, uid):
    blob = A.extract(mm, f"comp_{uid}.dat")
    n = CR.HEADER.read(blob, 0)["n_fields"]
    p, fields = CR.HEADER.span, []
    for _ in range(n):
        node, p = read_tree(blob, p, len(blob))
        fields.append(node)
    print(f"# comp_{uid}.dat: {len(blob)} B = {CR.HEADER.span} header + {p - CR.HEADER.span} "
          f"rules + {len(blob) - p} runtime state")
    return fields


def dictionary_fields(mm, name):
    for b in RF.RULE_FILES_TABLE.blocks(mm):
        if b.get("file") == name:
            print(f"# rule file {name!r} @ {b.start}, {b.end - b.start} B")
            return b.fields
    sys.exit(f"no rule file named {name!r}")


def show(node, names, depth=0):
    tag, typ, val = node
    pad = "  " * depth
    if isinstance(val, list):
        print(f"{pad}{tag} ({len(val)})")
        for kid in val:
            show(kid, names, depth + 1)
        return
    label = ""
    if tag in NAME_TAGS:
        key = val[0] if isinstance(val, tuple) else val
        if isinstance(key, int) and key in names:
            label = f"  <{names[key]}>"
    print(f"{pad}{tag} = {val!r}{label}")


def grids(fields):
    """[(stage indx, [{slot: value} per matchday])] for every stage carrying `cftp`."""
    out = []
    for tag, _, stages in fields:
        if tag != "stgs":
            continue
        for _, _, st in stages:
            d = {t: v for t, _, v in st}
            if d.get("cftp"):
                days = [{int(t[1:]): v for t, _, v in day if re.fullmatch(r"t\d{3}", t or "")}
                        for _, _, day in d["cftp"]]
                out.append((d.get("indx"), days))
    return out


def check_grid(days):
    slots = sorted(days[0])
    home = {s: 0 for s in slots}
    opps = {s: set() for s in slots}
    bad = 0
    for day in days:
        for s, v in day.items():
            opp, mirror = (v, AWAY * 2 - s) if v < AWAY else (AWAY * 2 - v, s)
            if day.get(opp) != mirror:
                bad += 1
            home[s] += v < AWAY
            opps[s].add(opp)
    print(f"  {len(days)} matchdays x {len(slots)} slots; unmirrored pairings: {bad}; "
          f"home games per slot: {sorted(set(home.values()))}; "
          f"distinct opponents per slot: {sorted({len(o) for o in opps.values()})}")


def find(mm, tag):
    def walk(node, path):
        t, _, v = node
        if t == tag and v not in ([], None):
            yield "/".join(path + [t]), v
        if isinstance(v, list):
            for kid in v:
                yield from walk(kid, path + ([t] if t else []))
    for b in RF.RULE_FILES_TABLE.blocks(mm):
        for fld in b.fields:
            for path, v in walk(fld, []):
                text = repr(v)
                print(f"{b.get('file')}: {path} = {text[:160]}{'...' if len(text) > 160 else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("save")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--uid", type=int, help="archive member comp_<uid>.dat")
    src.add_argument("--file", help="data dictionary rule file, by its `file` name")
    src.add_argument("--find", metavar="TAG", help="every rule file carrying a non-empty TAG")
    ap.add_argument("--tags", help="comma-separated top-level tags to print (default all)")
    ap.add_argument("--grid", action="store_true", help="check each stage's cftp fixture grid")
    a = ap.parse_args()

    with open(a.save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if a.find:
            find(mm, a.find)
            return
        names = R.round_names_map(mm) if R.locate_rounds(mm) is not None else {}
        fields = member_fields(mm, a.uid) if a.uid is not None else dictionary_fields(mm, a.file)
        if a.grid:
            for indx, days in grids(fields):
                print(f"stage {indx}: cftp")
                check_grid(days)
            return
        want = set(a.tags.split(",")) if a.tags else None
        for fld in fields:
            if want is None or fld[0] in want:
                show(fld, names)


if __name__ == "__main__":
    main()
