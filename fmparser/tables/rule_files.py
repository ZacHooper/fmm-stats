#!/usr/bin/env python3
"""`rule_files` — the data dictionary's library of competition rule files.

The save's tagged data dictionary (~16.7-20.0 MB, drifting per save) is the game's library
of rule files: 667 of them, each naming its source in a `file` string and its
folder in `SubF` (`.\\europe\\dan\\`). Within a career the rule files are value-for-value
identical in every save (Bucaspor's total 60 bytes fewer than Frem's); what changes between
saves is the bytes BETWEEN them (below). A rule file is a tagged block in the wire format of
the archive's `comp_<uid>.dat` members (`tables/comp_rules.py`) minus their 54-byte header:

    [u32 n][n tagged fields]            (tagged.read_tree reads each field strictly)

`find_region` gives the window to search: the densest cluster of the `comp` tag, padded
60 KB before and 300 KB after. The pad is slack, not content -- the first rule file opens
~66 bytes before the cluster's first `comp` and the last closes ~170 bytes after its last
-- and the dictionary's real extent is the span from the first rule file to the last.

Each file is located as a COUNT-FRAMED block (Shape A): a block declares its own field
count and must read to exactly that many fields, so its extent is proved rather than
guessed. The walk is one forward pass over the window: at every candidate `[u32 n][tag 01 type]` it reads n
fields strictly, and a block that reads is taken whole and the walk resumes after it, so a
block's inner containers are never re-read as blocks of their own. A block is a rule file
iff its top level carries both `ftye` and `file`. Every count-framed block in the span is a
rule file, so a block that is not one is a rule file that failed to read, broken into
fragments -- `tiling()` counts them and the test requires zero.

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

Five schemas cover every rule file (`fmparser/core/tagged_schema.py`), picked by
`schema_for`: a competition's file carries a stage list and reads with `comp_rules.FILE` --
the same declaration the archive members read with; a nation's three kinds of file read
with `NATION_COMPS`, `NATION_RESERVE_COMPS` and `NATION_RULES`; and the two Welsh files
that configure a competition with no stage list read with `STAGELESS_COMP`.
`scripts/audit/audit_records.py --map` prints them.

A nation's `_comps` file carries `retm`, a list of team-count rules (`TEAM_RULE`), each
naming a competition by uid and, on 18% of them, its number of teams. `team_counts()` reads
them: 190 competitions, among them 3F Superliga (uid 6) and 3. Division, both 12.
"""
import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from .. import tagged
from ..core.tagged_schema import (
    FOURCC, INT, STRING, AnyOf, ListOf, Nested, Tag, TaggedRecord, TaggedSchemaError)
from ..save import cache_key
from . import comp_rules as CR

__all__ = [
    "Block",
    "COMP_REF",
    "NATION_COMPS",
    "NATION_RESERVE_COMPS",
    "NATION_RULES",
    "STAGELESS_COMP",
    "TEAM_RULE",
    "RuleFileError",
    "RegionNotFound",
    "blocks",
    "find_region",
    "framing_problems",
    "read",
    "rule_files",
    "schema_for",
    "team_counts",
    "tiling",
]

# `[tag x4][0x01][type]`: the head of a tagged field, the only thing a block opens with.
_FIELD_HEAD = re.compile(rb"[\x20-\x7e]{4}\x01[\x00-\x20]")
_MAX_FIELDS = 5000
_CONTAINER_HEAD = b"\x01\x0a"

_TAG_COMP = b"pmoc"         # `comp` as stored (reversed)
_CLUSTER_GAP = 500_000      # two `comp` tags this far apart start a new cluster
_PAD_LO, _PAD_HI = 60_000, 300_000

# Keyed by save.cache_key -- (id(mm), len(mm)) -- never id(mm) alone: CPython reuses a freed
# object's id, so a loop over saves would be served the previous save's answer.
_REGION_CACHE: Dict[Any, Tuple[int, int]] = {}
_BLOCK_CACHE: Dict[Any, List["Block"]] = {}


class RegionNotFound(Exception):
    """The save carries no `comp` tag, so there is no dictionary to walk."""


def find_region(mm: Any) -> Tuple[int, int]:
    """(lo, hi): the window the walk searches -- the densest cluster of the `comp` tag,
    padded. Raises rather than falling back to a fixed window."""
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


class RuleFileError(Exception):
    """A rule file did not read through its declared schema."""


class Block(NamedTuple):
    start: int                  # offset of the u32 field count
    end: int                    # one past the last field
    fields: List[Tuple[Optional[str], int, Any]]

    @property
    def top_tags(self) -> frozenset:
        return frozenset(f[0] for f in self.fields)

    @property
    def is_rule_file(self) -> bool:
        return {"ftye", "file"} <= self.top_tags

    @property
    def file(self) -> Optional[str]:
        return next((v for t, _, v in self.fields if t == "file"), None)


def blocks(mm: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> List[Block]:
    """Every count-framed tagged block in the window, in order, none overlapping."""
    key = None
    if lo is None or hi is None:
        key = cache_key(mm)
        if key in _BLOCK_CACHE:
            return _BLOCK_CACHE[key]
        lo, hi = find_region(mm)
    out: List[Block] = []
    end = lo
    for m in _FIELD_HEAD.finditer(mm, lo + 4, hi):
        p = m.start()
        if p - 4 < end:
            continue
        n = int.from_bytes(mm[p - 4:p], "little")
        if not 0 < n <= _MAX_FIELDS:
            continue
        q, fields = p, []
        try:
            for _ in range(n):
                f, q = tagged.read_tree(mm, q, hi)
                fields.append(f)
        except tagged.TreeError:
            continue
        out.append(Block(p - 4, q, fields))
        end = q
    if key is not None:
        _BLOCK_CACHE[key] = out
    return out


def rule_files(mm: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> List[Block]:
    """The rule files, in region order."""
    return [b for b in blocks(mm, lo, hi) if b.is_rule_file]


def is_bare(mm: Any, block: Block) -> bool:
    """True for a block with no tagless-container head (the merged `<nat>_rules`)."""
    return mm[block.start - 2:block.start] != _CONTAINER_HEAD


def schema_for(block: Block) -> TaggedRecord:
    """The declared schema a rule file reads with."""
    if "stgs" in block.top_tags:
        return CR.FILE
    name = block.file or ""
    for suffix, rec in (("_reserve_comps", NATION_RESERVE_COMPS), ("_comps", NATION_COMPS),
                        ("_rules", NATION_RULES)):
        if name.endswith(suffix):
            return rec
    return STAGELESS_COMP


def read(block: Block) -> Dict[str, Any]:
    """A rule file read through its schema."""
    try:
        return schema_for(block).read(block.fields)
    except TaggedSchemaError as e:
        raise RuleFileError(f"{block.file} @ {block.start}: {e}") from e


def framing_problems(mm: Any, files: Optional[List[Block]] = None) -> List[str]:
    """Where the region breaks the layout in the docstring: a group whose count k is not the
    number of container files that follow, or a bare block that is not a `<nat>_rules`."""
    files = rule_files(mm) if files is None else files
    problems: List[str] = []
    i = 0
    while i < len(files):
        b = files[i]
        if is_bare(mm, b):
            if not (b.file or "").endswith("_rules"):
                problems.append(f"bare block {b.file!r} @ {b.start} is not a nation's rules")
            i += 1
            continue
        k = int.from_bytes(mm[b.start - 6:b.start - 2], "little")
        j = i + 1
        while (j < len(files) and not is_bare(mm, files[j])
               and files[j].start == files[j - 1].end + len(_CONTAINER_HEAD)):
            j += 1
        if k != j - i:
            problems.append(f"group @ {b.start - 6} declares {k} files, {j - i} follow")
        i = j
    return problems


def tiling(mm: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> Dict[str, int]:
    """Bytes of the span from the first block to the last, by what reads them: rule files,
    any other count-framed block (a rule file that failed to read), and the rest --
    separators and dated records, not read."""
    bl = blocks(mm, lo, hi)
    if not bl:
        return {"span": 0, "rule_files": 0, "n_rule_files": 0, "other_blocks": 0, "unread": 0}
    span = bl[-1].end - bl[0].start
    rf = [b for b in bl if b.is_rule_file]
    covered = sum(b.end - b.start for b in rf)
    other = sum(b.end - b.start for b in bl if not b.is_rule_file)
    return {"span": span, "rule_files": covered, "n_rule_files": len(rf),
            "other_blocks": other, "unread": span - covered - other}


def team_counts(mm: Any) -> Dict[int, int]:
    """{competition uid: teams} from every nation's `_comps` team-count rules -- the rules
    that name a competition and carry `ntms`, with `nxss` 0."""
    out: Dict[int, int] = {}
    for b in rule_files(mm):
        if schema_for(b) is not NATION_COMPS:
            continue
        for rule in read(b)["team_rules"] or []:
            if rule["comp_uid"] is not None and rule["teams"] is not None and not rule["nxss"]:
                out[rule["comp_uid"]] = rule["teams"]
    return out
