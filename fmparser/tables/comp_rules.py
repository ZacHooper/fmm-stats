#!/usr/bin/env python3
"""`comp_rules` — each competition's stage and round structure, from `comp_<uid>.dat`.

The save's tail archive carries one member per loaded competition, named by the competition's
`uid` (the same `uid` the competition table in the main save holds, so `staging.competitions`
joins straight to it). Each member is a TAGGED TREE, the same wire format as the tagged data
dictionary (field names are FourCC tags stored byte-reversed):

    [6-byte member header][44-byte binary preamble][u32 n @ +50][n fields @ +54]
    field     = [tag x4][0x01][type][value]          tagged
              | [0x01][type][value]                  tagless (list elements)
    type 0x0a = container: [u32 m] then m fields
    type 0x0b = list:      [u32 n] then n fields (each a tagless 0x0a container)
    type 0x1a = string:    [u32 len][bytes]
    type 0x0f = a pair of u32
    other types are fixed width (FIELD_SIZE)

The n top-level fields end at the file trailer (`EdBr`, `EdDt`, `SubF` = the source path);
binary runtime state follows and is not read. A member whose declared count is 0 is a stub
(the competition is loaded but not configured) and yields no rows.

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
both forms occur. Name ids resolve through the round-name catalog in the main save
(`tables/rounds.py`, `round_names_map`). Verified against in-game fixture screens: League
Path / Third Qualifying Round / Playoff / Group D / First Knockout Round (EURO Cup and
Champions Cup), Preliminary Phase / Championship Group (3F Superliga) and Third Round
(Sydbank Pokalen).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .. import archive as A

__all__ = [
    "BLOCK_AT",
    "COUNT_AT",
    "FIELD_SIZE",
    "RulesError",
    "comp_members",
    "competition_rounds",
    "parse_block",
    "read_field",
    "stage_rows",
]

COUNT_AT = 50          # u32 declared top-level field count
BLOCK_AT = 54          # first top-level field
MAX_ITEMS = 5000       # a container or list count above this is a misread, not data

# Fixed-width value types. 0x00 carries no value.
FIELD_SIZE = {0x00: 0, 0x01: 4, 0x02: 4, 0x03: 1, 0x0f: 8, 0x11: 1, 0x12: 2,
              0x13: 4, 0x14: 8, 0x18: 8, 0x19: 4, 0x20: 4}
CONTAINER, LIST, STRING = 0x0a, 0x0b, 0x1a
PAIR = 0x0f            # two u32; a name id stored this way repeats itself: (28, 28)

_MEMBER = re.compile(r"^comp_(\d+)\.dat$")


class RulesError(Exception):
    """A member's tagged block did not parse to its declared field count."""


def _printable(b: bytes) -> bool:
    return all(32 <= c < 127 for c in b)


def read_field(blob: Any, p: int) -> Tuple[Tuple[Optional[str], int, Any], int]:
    """((tag, type, value), next_p) for the field at p. Containers and lists decode to a
    list of child fields; a tagless field has tag None."""
    if p + 2 > len(blob):
        raise RulesError(f"field at {p} runs past the member")
    head = bytes(blob[p:p + 6])
    if head[0] == 0x01 and (head[1] in (CONTAINER, LIST, STRING)
                            or (head[1] in FIELD_SIZE and not _printable(head[:4]))):
        tag, typ, q = None, head[1], p + 2
    elif len(head) == 6 and _printable(head[:4]) and head[4] == 0x01:
        tag, typ, q = head[:4][::-1].decode("latin-1").strip(), head[5], p + 6
    else:
        raise RulesError(f"no field at {p}")
    if typ in (CONTAINER, LIST):
        n = int.from_bytes(blob[q:q + 4], "little")
        if n > MAX_ITEMS:
            raise RulesError(f"implausible item count {n} at {p}")
        q += 4
        kids = []
        for _ in range(n):
            kid, q = read_field(blob, q)
            kids.append(kid)
        return (tag, typ, kids), q
    if typ == STRING:
        n = int.from_bytes(blob[q:q + 4], "little")
        return (tag, typ, bytes(blob[q + 4:q + 4 + n]).decode("latin-1")), q + 4 + n
    if typ not in FIELD_SIZE:
        raise RulesError(f"unknown field type 0x{typ:02x} at {p}")
    size = FIELD_SIZE[typ]
    if typ == PAIR:
        return (tag, typ, (int.from_bytes(blob[q:q + 4], "little"),
                           int.from_bytes(blob[q + 4:q + 8], "little"))), q + 8
    return (tag, typ, int.from_bytes(blob[q:q + size], "little")), q + size


def parse_block(blob: Any) -> List[Tuple[Optional[str], int, Any]]:
    """The member's top-level fields, exactly as many as it declares."""
    n = int.from_bytes(blob[COUNT_AT:COUNT_AT + 4], "little")
    out, p = [], BLOCK_AT
    for _ in range(n):
        f, p = read_field(blob, p)
        out.append(f)
    return out


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
    if v is None:
        return None
    s = v.to_bytes(4, "little")[::-1]
    return s.decode("latin-1").strip() if _printable(s) else None


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


def comp_members(mm: Any) -> Dict[int, str]:
    """{uid: member filename} for every competition member in the archive."""
    out = {}
    for name in A.members(mm):
        m = _MEMBER.match(name)
        if m:
            out[int(m.group(1))] = name
    return out


def competition_rounds(mm: Any) -> List[Dict[str, Any]]:
    """Every loaded competition's stage/round structure, ordered by (uid, stage, round)."""
    ents = A.members(mm)
    rows: List[Dict[str, Any]] = []
    for uid, name in sorted(comp_members(mm).items()):
        blob = A.read_member(mm, ents[name])
        if len(blob) < BLOCK_AT:
            continue
        rows.extend(stage_rows(uid, parse_block(blob)))
    return rows
