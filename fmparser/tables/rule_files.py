#!/usr/bin/env python3
"""`rule_files` — the data dictionary's library of competition rule files.

The save's tagged data dictionary (~16.7-20.0 MB, drifting per save) is the game's library
of rule files: 667 of them, each naming its source in a `file` string and its folder in
`SubF` (`.\\europe\\dan\\`). Within a career the rule files are value-for-value
identical in every save (Bucaspor's total 60 bytes fewer than Frem's); what changes between
saves is the bytes BETWEEN them (below). A rule file is a tagged block in the tagged format of
the archive's `comp_<uid>.dat` members (`tables/comp_rules.py`) minus their 54-byte header:

    [u32 n][n tagged fields]

`find_region` gives the window to search: the densest cluster of the `comp` tag, padded
60 KB before and 300 KB after. The pad is slack, not content -- the first rule file opens
~66 bytes before the cluster's first `comp` and the last closes ~170 bytes after its last
-- and the dictionary's real extent is the span from the first rule file to the last.

`RULE_FILES_TABLE` is a `TaggedTableDef`, one row per rule file. Its locator runs
`core.scan_tagged_blocks` over the window (Shape A, count-framed: a block must read to
exactly its declared field count) and keeps the blocks whose top level carries both `ftye`
and `file`. Every count-framed block in the span is a rule file, so a block that is not one
is a rule file that failed to read, broken into fragments -- `tiling()` counts them and the
test requires zero.

How the files sit in the region, in order, for each of the 53 nations:

    [dated record][u32 n][n fields]                  the nation's merged `<nat>_rules`
    [separator][u32 k] k x ([01 0a][u32 n][n fields])
                                                     a GROUP of k tagless containers:
                                                     `<nat>_comps`, `<nat>_reserve_comps`,
                                                     `<nat>_rules`, then the nation's
                                                     competition files

The group count k equals the number of container files that follow, on every group. The
merged `<nat>_rules` (a BARE block, no container head) carries every tag of the three files
in its nation's group and some of its own. Neither the separator (empty after a bare file,
else runs of `ffffffff`-led u16 entries ending `01`) nor the dated record (41 bytes on
most, u16 day-of-year + u16 year pairs such as `9d04 eb07`) is decoded; together they are
the 0.8% of the span `tiling()` reports as unread, and they are the part that is STATE:
26 of the 666 differ between frem-2027-07-02 and frem-2027-08-08, 216 between
frem-2021-07-01 and frem-2027-08-08, while no rule file changes at all.

Five schemas cover every rule file (`core.TaggedRecord`), picked per row by `schema_for`:
a competition's file carries a stage list and reads with `comp_rules.FILE` -- the same
declaration the archive members read with; a nation's three kinds of file read with
`NATION_COMPS`, `NATION_RESERVE_COMPS` and `NATION_RULES`; and the two Welsh files that
configure a competition with no stage list read with `STAGELESS_COMP`.
`scripts/audit/audit_records.py --map` prints them.

A nation's `_comps` file carries `retm`, a list of team-count rules (`TEAM_RULE`), each
naming a competition by uid and, on 18% of them, its number of teams. `team_counts()` reads
them: 190 competitions, among them 3F Superliga (uid 6) and 3. Division, both 12.
"""
from typing import Any, Dict, List, Tuple

from ..core import (
    FOURCC, INT, STRING, AnyOf, ListOf, Nested, Tag, TaggedBlock, TaggedRecord,
    TaggedTableDef, scan_tagged_blocks)
from ..save import cache_key
from . import comp_rules as CR

__all__ = [
    "COMP_REF",
    "NATION_COMPS",
    "NATION_RESERVE_COMPS",
    "NATION_RULES",
    "RULE_FILES_TABLE",
    "STAGELESS_COMP",
    "TEAM_RULE",
    "RegionNotFound",
    "all_blocks",
    "find_region",
    "framing_problems",
    "is_rule_file",
    "locate_rule_files",
    "schema_for",
    "team_counts",
    "tiling",
]

# ---- the schemas ---------------------------------------------------------------------------
# Every rule file opens `ftye vers` and closes with the trailer `XSvC EdBr EdDt SubF` the
# archive members also end with; `Bran` and `file` sit just before it. The unread lists are
# every tag observed across all 30 Frem saves and bucaspor-2023-05-20, in order of
# frequency; tests/test_rule_files.py fails on a tag that is neither read nor listed.

def _head(kind: str) -> List[Tag]:
    return [
        Tag("file", "file", STRING, required=True, note=f"source name, '{kind}'"),
        Tag("SubF", "source_path", STRING, required=True, note="source folder, '.\\europe\\dan\\'"),
        Tag("ftye", "file_type", INT, required=True),
    ]


_TRAILER = ("vers", "nati", "Bran", "XSvC", "EdBr", "EdDt")

# A competition reference held in a container: `{id 'comp', comp <uid>}`.
COMP_REF = TaggedRecord("rule_file_comp_ref", [
    Tag("id",   "ref_code", FOURCC, required=True, note="'comp'"),
    Tag("comp", "comp_uid", INT,    required=True, note="= staging.competitions.uid"),
], unread=("DBID",))

# One element of a nation's `retm` list: a team-count rule for one competition (or, where
# `comp` is absent, for a team or a nation).
TEAM_RULE = TaggedRecord("rule_file_team_rule", [
    Tag("comp", "comp_uid", AnyOf(INT, Nested(COMP_REF, pick="comp_uid")),
        note="the competition; a u32 uid or a COMP_REF. Absent on the team/nation rules"),
    Tag("ntms", "teams",    INT, note="teams in the competition, on 18% of rules"),
    Tag("nxss", "nxss",     INT, required=True,
        note="0 on every rule but one: Chile's 5250792 carries 0 (17 teams) and 1 (16)"),
], unread=('umox', 'igmt', 'mntm', 'mxtm', 'type', 'pare', 'team', 'Bktm', 'nati', 'Cexi',
           'STpr', 'spst'))

NATION_COMPS = TaggedRecord("rule_file_nation_comps", _head("<nat>_comps") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE), note="team-count rules; team_counts()"),
], unread=_TRAILER + ('dvlv', 'cmps', 'dfdl', 'desc', 'ind1', 'ftac', 'year', 'updy'),
    note="a nation's competition list: division levels (dvlv), competitions (cmps), "
         "team-count rules (retm)")

NATION_RESERVE_COMPS = TaggedRecord(
    "rule_file_nation_reserve_comps", _head("<nat>_reserve_comps"), unread=_TRAILER + (
        'rsvl', 'rsno', 'rsvt', 'BclT', 'ReTT', 'desc', 'ind1', 'ftac', 'u23t', 'u18t', 'u19t',
        'u21t'),
    note="a nation's reserve and youth competitions")

NATION_RULES = TaggedRecord("rule_file_nation_rules", _head("<nat>_rules") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE), note="the merged copy of _comps' retm"),
], unread=_TRAILER + (
    'updy', 'fxrl', 'dsrl', 'trwi', 'year', 'sswn', 'lnrl', 'trrl', 'stdr', 'wdft', 'mdft',
    'wkpm', 'tfxt', 'TrCm', 'mdsw', 'prsw', 'CnRl', 'dvlv', 'cmps', 'fles', 'rsvl',
    'dfdl', 'rsno', 'rsvt', 'pspd', 'trsd', 'pmdf', 'Draf', 'ifdr', 'hlps', 'desc', 'snft',
    'BclT', 'ReTT', 'Lpsd', 'wkFT', 'NtSr', 'ifdy', 'ind1', 'ftac', 'u23t', 'u18t', 'PtSm',
    'ifsd', 'RgFr', 'u19t', 'u21t'),
    note="a nation's rules: fixtures (fxrl), discipline (dsrl), transfer windows (trwi) ...; "
         "the merged bare copy also carries its _comps and _reserve_comps tags")

STAGELESS_COMP = TaggedRecord("rule_file_stageless_comp", _head("wal_cymru"),
                              unread=_TRAILER + (
    'comp', 'ilgf', 'type', 'inac', 'levl', 'year', 'ygap', 'bsyr', 'dtrn', 'sblt', 'chdc',
    'LtfP', 'dcin', 'fxri', 'desc', 'crlm', 'mnsc', 'mstc', 'fxds', 'hlps', 'enyr', 'styr'),
    note="a competition configured without a stage list (wal_cymru, wal_cymru_main)")


# ---- locating ------------------------------------------------------------------------------
_TAG_COMP = b"pmoc"         # `comp` as stored (reversed)
_CLUSTER_GAP = 500_000      # two `comp` tags this far apart start a new cluster
_PAD_LO, _PAD_HI = 60_000, 300_000
_CONTAINER_HEAD = b"\x01\x0a"

# Keyed by save.cache_key -- (id(mm), len(mm)) -- never id(mm) alone: CPython reuses a freed
# object's id, so a loop over saves would be served the previous save's answer.
_REGION_CACHE: Dict[Any, Tuple[int, int]] = {}
_BLOCK_CACHE: Dict[Any, List[TaggedBlock]] = {}


class RegionNotFound(Exception):
    """The save carries no `comp` tag, so there is no dictionary to walk."""


def find_region(mm: Any) -> Tuple[int, int]:
    """(lo, hi): the window to search -- the densest cluster of the `comp` tag, padded.
    Raises rather than falling back to a fixed window."""
    key = cache_key(mm)
    if key in _REGION_CACHE:
        return _REGION_CACHE[key]
    hits, i = [], mm.find(_TAG_COMP)
    while i != -1:
        hits.append(i)
        i = mm.find(_TAG_COMP, i + 1)
    if not hits:
        raise RegionNotFound("no `comp` tag in this save: there is no data dictionary")
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] <= _CLUSTER_GAP:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    best = max(clusters, key=len)
    region = (max(0, best[0] - _PAD_LO), min(len(mm), best[-1] + _PAD_HI))
    _REGION_CACHE[key] = region
    return region


def all_blocks(mm: Any) -> List[TaggedBlock]:
    """Every count-framed block in the window (`core.scan_tagged_blocks`), rule file or
    not; cached per save."""
    key = cache_key(mm)
    if key not in _BLOCK_CACHE:
        _BLOCK_CACHE[key] = scan_tagged_blocks(mm, *find_region(mm))
    return _BLOCK_CACHE[key]


def is_rule_file(block: TaggedBlock) -> bool:
    """A block is a rule file iff its top level carries both `ftye` and `file`."""
    return {"ftye", "file"} <= block.top_tags


def locate_rule_files(mm: Any) -> List[Tuple[int, int]]:
    """[(first field, field count)] of every rule file, in region order."""
    return [(b.start, len(b.fields)) for b in all_blocks(mm) if is_rule_file(b)]


def schema_for(block: TaggedBlock) -> TaggedRecord:
    """The declared schema a rule file reads with."""
    if "stgs" in block.top_tags:
        return CR.FILE
    name = block.get("file") or ""
    for suffix, rec in (("_reserve_comps", NATION_RESERVE_COMPS), ("_comps", NATION_COMPS),
                        ("_rules", NATION_RULES)):
        if name.endswith(suffix):
            return rec
    return STAGELESS_COMP


RULE_FILES_TABLE = TaggedTableDef(
    name="rule_files",
    locator=locate_rule_files,
    schema=schema_for,
)


# ---- what the rule files give ----------------------------------------------------------------
def team_counts(mm: Any) -> Dict[int, int]:
    """{competition uid: teams} from every nation's `_comps` team-count rules -- the rules
    that name a competition and carry `ntms`, with `nxss` 0."""
    out: Dict[int, int] = {}
    for b in RULE_FILES_TABLE.blocks(mm):
        if schema_for(b) is not NATION_COMPS:
            continue
        for rule in RULE_FILES_TABLE.read(b)["team_rules"] or []:
            if rule["comp_uid"] is not None and rule["teams"] is not None and not rule["nxss"]:
                out[rule["comp_uid"]] = rule["teams"]
    return out


# ---- checks: the framing and the share of the span that is read ------------------------------
def is_bare(mm: Any, block: TaggedBlock) -> bool:
    """True for a block with no tagless-container head (the merged `<nat>_rules`)."""
    return mm[block.start - 6:block.start - 4] != _CONTAINER_HEAD


def framing_problems(mm: Any) -> List[str]:
    """Where the region breaks the layout in the docstring: a group whose count k is not the
    number of container files that follow, or a bare block that is not a `<nat>_rules`."""
    files = RULE_FILES_TABLE.blocks(mm)
    problems: List[str] = []
    i = 0
    while i < len(files):
        b = files[i]
        if is_bare(mm, b):
            if not (b.get("file") or "").endswith("_rules"):
                problems.append(f"bare block {b.get('file')!r} @ {b.start} is not a nation's rules")
            i += 1
            continue
        k = int.from_bytes(mm[b.start - 10:b.start - 6], "little")
        j = i + 1
        while (j < len(files) and not is_bare(mm, files[j])
               and files[j].start == files[j - 1].end + len(_CONTAINER_HEAD) + 4):
            j += 1
        if k != j - i:
            problems.append(f"group @ {b.start - 10} declares {k} files, {j - i} follow")
        i = j
    return problems


def tiling(mm: Any) -> Dict[str, int]:
    """Bytes of the span from the first block to the last, by what reads them: rule files
    (with their field counts), any other count-framed block (a rule file that failed to
    read), and the rest -- separators, group counts and dated records, not read."""
    bl = all_blocks(mm)
    if not bl:
        return {"span": 0, "rule_files": 0, "n_rule_files": 0, "other_blocks": 0, "unread": 0}
    span = bl[-1].end - (bl[0].start - 4)
    rf = [b for b in bl if is_rule_file(b)]
    covered = sum(b.end - b.start + 4 for b in rf)
    other = sum(b.end - b.start + 4 for b in bl if not is_rule_file(b))
    return {"span": span, "rule_files": covered, "n_rule_files": len(rf),
            "other_blocks": other, "unread": span - covered - other}
