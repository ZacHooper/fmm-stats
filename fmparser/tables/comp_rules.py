#!/usr/bin/env python3
"""`comp_rules` — each competition's stage and round structure, from `comp_<uid>.dat`.

Located inside the save's zstd tail archive (Shape D), one member per loaded competition,
named by the competition's `uid` -- the same uid the competition table in the main save
holds, so `staging.competitions.uid` names the member directly.

A member is a fixed 54-byte header (`HEADER`, declared below) followed by a TAGGED block in
the data-dictionary wire format (`fmparser/datadict.py`, read strictly by
`datadict.read_tree`). The header declares the block's top-level field count at +50, and
the block is exactly that many fields: they end at the file trailer (`XSvC`, `EdBr`,
`EdDt`, `SubF` = the source path); binary runtime state follows and is not read. A member
declaring 0 fields is a stub (the competition is loaded but not configured).

What is read is `stgs`, the stage list. Each stage element carries

    id    FourCC stage code ('leag', 'cham', 'rele', 'prom', 'bppr', 'chpr', 'grou', 'cup ', …)
    indx  stage index — the SAME number `fix_man.dat` carries at +76 (`stage_index`)
    type  0 knockout, 1 league, 2 groups, 6 play-off feeder
    ntms  teams in the stage
    stnm  the stage's name id (e.g. 2000016479 'League Path', 236 'Preliminary Phase')
    ngps  number of groups (group stages)
    rnds  the round list — element k is the round `fix_man.dat` carries at +77 (`round_index`)
          stnm  round name id (151 'Third Qualifying Round', 17 'Quarter Final', …)
          ntms  teams in the round
          nmlg  legs per tie (1 or 2)

A name id is either the scalar value of `stnm` or the `stgn` child of an `stnm` container;
both forms occur, and a scalar may be stored as a PAIR of equal u32s. Name ids resolve
through the round-name catalog in the main save (`tables/rounds.py`). Verified against the
in-game fixture screens: League Path / Third Qualifying Round / Playoff / Group D / First
Knockout Round (EURO Cup and Champions Cup), Preliminary Phase / Championship Group (3F
Superliga) and Third Round (Sydbank Pokalen).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .. import archive as A
from .. import datadict as DD
from ..core import Field, PAD, Record, TableDef, U16, U32, UNKNOWN

__all__ = [
    "COMP_RULES_TABLE",
    "HEADER",
    "MEMBER_PATTERN",
    "RulesError",
    "competition_rounds",
    "locate_comp_rules",
    "scrape",
    "stage_rows",
]

MEMBER_PATTERN = re.compile(r"^comp_(\d+)\.dat$")

# Profiled over every member of frem-2021-07-01, frem-2027-08-08 and bucaspor-2023-05-20.
HEADER = Record("comp_rules_header", 54, [
    Field(0,  6,  UNKNOWN, PAD, note="member header [03][01]['tad.'] (fixtures.MEMBER_HEADER)"),
    Field(6,  2,  UNKNOWN, PAD, note="constant 0x01d9 on every member"),
    Field(8,  12, UNKNOWN, PAD),
    Field(20, 2,  "season_year", U16, note="start year of the current season; 0 on a stub"),
    Field(22, 4,  UNKNOWN, PAD),
    Field(26, 4,  UNKNOWN, PAD, note="f32; 1.0 on most competitions"),
    Field(30, 18, UNKNOWN, PAD),
    Field(48, 2,  "base_year", U16, note="2000 on every member"),
    Field(50, 4,  "n_fields", U32, note="declared count of top-level tagged fields"),
])


class RulesError(Exception):
    """A member's tagged block did not read to its declared field count."""


class _TaggedField:
    """TableDef segment: one top-level field of the tagged block, read strictly."""

    def read(self, blob: Any, pos: int, limit: int) -> Optional[Tuple[Dict[str, Any], int]]:
        try:
            field, nxt = DD.read_tree(blob, pos, limit)
        except DD.TreeError as e:
            raise RulesError(str(e)) from e
        return {"field": field}, nxt


def locate_comp_rules(blob: Any) -> Optional[Tuple[int, int]]:
    """(base, declared field count) for the TableDef locator protocol, or None for a member
    too short to hold the header."""
    if len(blob) < HEADER.span:
        return None
    return (HEADER.span, HEADER.read(blob, 0)["n_fields"])


COMP_RULES_TABLE = TableDef(
    name="comp_rules",
    segments=(_TaggedField(),),
    locator=locate_comp_rules,
)


def scrape(blob: Any) -> List[Tuple[Optional[str], int, Any]]:
    """The member's top-level tagged fields -- exactly as many as its header declares."""
    rows = COMP_RULES_TABLE.scrape(blob)
    loc = locate_comp_rules(blob)
    if loc and len(rows) != loc[1]:
        raise RulesError(f"read {len(rows)} of {loc[1]} declared fields")
    return [r["field"] for r in rows]


def _child(fields: List, tag: str):
    return next((f for f in fields if f[0] == tag), None)


def _scalar(fields: List, tag: str) -> Optional[int]:
    f = _child(fields, tag)
    if f is None or isinstance(f[2], list):
        return None
    return f[2][0] if isinstance(f[2], tuple) else f[2]


def _name_id(fields: List) -> Optional[int]:
    f = _child(fields, "stnm")
    if f is None:
        return None
    if isinstance(f[2], list):
        return _scalar(f[2], "stgn")
    return f[2][0] if isinstance(f[2], tuple) else f[2]


def _fourcc(v: Optional[int]) -> Optional[str]:
    if v is None or isinstance(v, str):     # a type-0x02 id already decodes to its tag
        return v
    s = v.to_bytes(4, "little")[::-1]
    return s.decode("latin-1").strip() if all(32 <= c < 127 for c in s) else None


def stage_rows(uid: int, fields: List) -> List[Dict[str, Any]]:
    """One row per (stage, round); a stage with no round list gives one row with
    round_index None."""
    stgs = _child(fields, "stgs")
    rows: List[Dict[str, Any]] = []
    if stgs is None:
        return rows
    for element in stgs[2]:
        st = element[2]
        stage = {
            "uid": uid,
            "stage_index": _scalar(st, "indx"),
            "stage_code": _fourcc(_scalar(st, "id")),
            "stage_type": _scalar(st, "type"),
            "stage_teams": _scalar(st, "ntms"),
            "stage_name_id": _name_id(st),
            "n_groups": _scalar(st, "ngps"),
        }
        rnds = _child(st, "rnds")
        rounds = rnds[2] if rnds is not None else []
        if not rounds:
            rows.append({**stage, "round_index": None, "round_name_id": None,
                         "round_teams": None, "legs": None})
        for k, r in enumerate(rounds):
            rf = r[2]
            rows.append({**stage, "round_index": k, "round_name_id": _name_id(rf),
                         "round_teams": _scalar(rf, "ntms"), "legs": _scalar(rf, "nmlg")})
    return rows


def competition_rounds(mm: Any) -> List[Dict[str, Any]]:
    """Every loaded competition's stage/round structure, ordered by (uid, stage, round)."""
    ents = A.members(mm)
    rows: List[Dict[str, Any]] = []
    members = sorted((int(m.group(1)), name) for name in ents
                     if (m := MEMBER_PATTERN.match(name)))
    for uid, name in members:
        rows.extend(stage_rows(uid, scrape(A.read_member(mm, ents[name]))))
    return rows
