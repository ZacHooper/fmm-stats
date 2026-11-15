#!/usr/bin/env python3
"""`rule_files` — the data dictionary's library of competition rule files.

The save's tagged data dictionary (~16.7-20.0 MB, drifting per save) is the game's library
of rule files: 667 of them, each naming its source in a `file` string and its folder in
`SubF` (`.\\europe\\dan\\`). Within a career the rule files are byte-identical in every save (27 of the 667 differ
between the Frem and Bucaspor careers); what changes between saves is the bytes BETWEEN them
(below). A rule file is a tagged block in the tagged format of
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
227 of the 666 differ between frem-2026-03-28 and frem-2030-06-22, while no rule file changes
at all.

Five schemas cover every rule file (`core.TaggedRecord`), picked per row by `schema_for`:
a competition's file carries a stage list and reads with `comp_rules.FILE` -- the same
declaration the archive members read with; a nation's three kinds of file read with
`NATION_COMPS`, `NATION_RESERVE_COMPS` and `NATION_RULES`; and the two Welsh files that
configure a competition with no stage list read with `STAGELESS_COMP`.
`scripts/audit/audit_records.py --map` prints them.

A nation's `_comps` file carries `retm`, a list of team-count rules (`TEAM_RULE`), each
naming a competition by uid and, on 18% of them, its number of teams. `team_counts()` reads
them: 190 competitions, among them 3F Superliga (uid 6) and 3. Division, both 12.

FMM27 (782 rule files on Truro) has no `SubF` anywhere: a nation's files carry `PLgn`, an
unnamed 0/1, in its place. It adds the continents' rule files, men's and women's (`afr`,
`wmn_afr`, ... `wmn_sam`), stored bare like a merged `<nat>_rules`, and a few tags per
schema. `rule_files_table(mm)` picks the declaration; `schema_for_fmm27` the schema.
"""
from typing import Any, Dict, List, Tuple

from ..core import (
    FOURCC, INT, REF_U32, STRING, AnyOf, ListOf, Nested, Tag, TaggedBlock, TaggedRecord,
    TaggedTableDef, scan_tagged_blocks)
from ..save import cache_key
from .save_header import FMM27, save_format
from . import comp_rules as CR

__all__ = [
    "COMP_REF",
    "NATION_COMPS",
    "NATION_RESERVE_COMPS",
    "NATION_RULES",
    "RULE_FILES_TABLE",
    "STAGELESS_COMP",
    "PERMIT_RULE",
    "TEAM_RULE",
    "WORK_PERMITS",
    "RegionNotFound",
    "all_blocks",
    "find_region",
    "framing_problems",
    "is_rule_file",
    "locate_rule_files",
    "schema_for",
    "team_counts",
    "tiling",
    "work_permits",
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
        note="0 or 1, unnamed: 1 on 51 rules; Chile's 5250792 carries 0 (17 teams) and 1 (16)"),
], unread=('umox', 'igmt', 'mntm', 'mxtm', 'type', 'pare', 'team', 'Bktm', 'nati', 'Cexi',
           'STpr', 'spst'))

# A nation's work-permit rules (`wkpm`; `wkFT` on the four UK nations and the English
# women's file, the same shape). Not named by the game: the reading below is from which
# nations carry which `type` (docs/parser/rule_files.md, "Work permits"). `type` 21 is the
# four UK nations' scheme only; `type` 1 carries a cash amount (Denmark, Austria, Ireland);
# `type` 3/4 a small number (Norway 50, Australia 70).
PERMIT_CASH = TaggedRecord("rule_file_permit_cash", [
    Tag("id",   "ref_code", FOURCC,  required=True, note="'info' or 'wpca'"),
    Tag("cash", "cash",     INT,     required=True, note="an amount; its currency is `curr`"),
    Tag("curr", "curr",     REF_U32, note="unnamed: 6 Denmark, 7 Austria and Ireland, 21 "
                                          "Sweden; not a currencies uid (DKK is 23). FMM27 only"),
])

PERMIT_RULE = TaggedRecord("rule_file_permit_rule", [
    Tag("id",   "ref_code",   FOURCC, required=True, note="the rule's own code, repeated"),
    Tag("type", "scheme",     INT,    required=True,
        note="the kind of test: 21 the UK nations', 1 a cash amount, 3/4 a small number ..."),
    Tag("info", "info",       AnyOf(INT, Nested(PERMIT_CASH)),
        note="the scheme's parameter: an int, or a PERMIT_CASH"),
    Tag("decd", "decd",       INT, note="unnamed, 0-4; days to a decision?"),
    Tag("wpca", "fee",        Nested(PERMIT_CASH, pick="cash"),
        note="a cash amount: England's wopm 20,000 and appe 5,000"),
    Tag("wpcc", "wpcc",       INT, note="unnamed, 1 where present (UK nations)"),
    Tag("wpdw", "wpdw",       INT, note="unnamed, 120 where present (UK nations)"),
    Tag("wpaf", "wpaf",       REF_U32, note="unnamed, 1 on England's appe"),
])

WORK_PERMITS = TaggedRecord("rule_file_work_permits", [
    Tag("id",   "ref_code", FOURCC, required=True, note="'wkpm' or 'wkFT'"),
    Tag("wopm", "wopm", Nested(PERMIT_RULE), note="probably a new work permit"),
    Tag("wtpm", "wtpm", Nested(PERMIT_RULE)),
    Tag("ctrn", "ctrn", Nested(PERMIT_RULE), note="probably a contract renewal"),
    Tag("stWP", "stwp", Nested(PERMIT_RULE)),
    Tag("appe", "appe", Nested(PERMIT_RULE), note="probably an appeal: a fee on England's"),
], note="a nation's work-permit rules; empty (`id` alone) on most nations")

PERMIT_RULE_CODES = ("wopm", "wtpm", "ctrn", "stWP", "appe")

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

_PERMIT_TAGS = [
    Tag("wkpm", "work_permits",      Nested(WORK_PERMITS), note="work_permits()"),
    Tag("wkFT", "work_permits_wkft", Nested(WORK_PERMITS),
        note="a second set, on the UK nations and wmn_eng; what selects it is unknown"),
]

NATION_RULES = TaggedRecord("rule_file_nation_rules", _head("<nat>_rules") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE), note="the merged copy of _comps' retm"),
] + _PERMIT_TAGS, unread=_TRAILER + (
    'updy', 'fxrl', 'dsrl', 'trwi', 'year', 'sswn', 'lnrl', 'trrl', 'stdr', 'wdft', 'mdft',
    'tfxt', 'TrCm', 'mdsw', 'prsw', 'CnRl', 'dvlv', 'cmps', 'fles', 'rsvl',
    'dfdl', 'rsno', 'rsvt', 'pspd', 'trsd', 'pmdf', 'Draf', 'ifdr', 'hlps', 'desc', 'snft',
    'BclT', 'ReTT', 'Lpsd', 'NtSr', 'ifdy', 'ind1', 'ftac', 'u23t', 'u18t', 'PtSm',
    'ifsd', 'RgFr', 'u19t', 'u21t'),
    note="a nation's rules: fixtures (fxrl), discipline (dsrl), transfer windows (trwi), "
         "work permits (wkpm) ...; "
         "the merged bare copy also carries its _comps and _reserve_comps tags")

STAGELESS_COMP = TaggedRecord("rule_file_stageless_comp", _head("wal_cymru"),
                              unread=_TRAILER + (
    'comp', 'ilgf', 'type', 'inac', 'levl', 'year', 'ygap', 'bsyr', 'dtrn', 'sblt', 'chdc',
    'LtfP', 'dcin', 'fxri', 'desc', 'crlm', 'mnsc', 'mstc', 'fxds', 'hlps', 'enyr', 'styr'),
    note="a competition configured without a stage list (wal_cymru, wal_cymru_main)")


# ---- FMM27 ----------------------------------------------------------------------------------
# FMM22's schemas with `PLgn` where `SubF` was, and the tags FMM27 adds, observed across
# both Truro saves, unread like the rest.

def _head_fmm27(kind: str) -> List[Tag]:
    return [
        Tag("file", "file", STRING, required=True, note=f"source name, '{kind}'"),
        Tag("PLgn", "plgn", INT, note="unnamed: 0 on 246 files, 1 on 57; absent on one"),
        Tag("ftye", "file_type", INT, required=True),
    ]


TEAM_RULE_FMM27 = TaggedRecord("rule_file_team_rule_fmm27", TEAM_RULE.tags,
                               unread=TEAM_RULE.unread + ('FBkt', 'ReTT', 'DbSt', 'DbEd', 'ifmh'))

NATION_COMPS_FMM27 = TaggedRecord("rule_file_nation_comps_fmm27", _head_fmm27("<nat>_comps") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE_FMM27), note="team-count rules; team_counts()"),
], unread=NATION_COMPS.unread)

NATION_RESERVE_COMPS_FMM27 = TaggedRecord(
    "rule_file_nation_reserve_comps_fmm27", _head_fmm27("<nat>_reserve_comps"),
    unread=NATION_RESERVE_COMPS.unread)

NATION_RULES_FMM27 = TaggedRecord("rule_file_nation_rules_fmm27", _head_fmm27("<nat>_rules") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE_FMM27), note="the merged copy of _comps' retm"),
] + _PERMIT_TAGS, unread=NATION_RULES.unread + ('fxry', 'ngid', 'ngiv'))

CONTINENT_RULES_FMM27 = TaggedRecord("rule_file_continent_rules_fmm27", _head_fmm27("afr") + [
    Tag("retm", "team_rules", ListOf(TEAM_RULE_FMM27)),
], unread=_TRAILER + (
    'cmps', 'cnti', 'natl', 'gpnl', 'tems', 'type', 'updy', 'year', 'dsrl', 'fxrl', 'fxry',
    'hlps', 'sswn', 'COwl', 'DRiH', 'InyL', 'SaEC', 'USfy', 'UsCf', 'qPcC', 'yNqC', 'fles',
    'TCPB', 'dvlv', 'dfdl'),
    note="a continent's rules, men's and women's (afr, wmn_afr, ...), new in FMM27")

STAGELESS_COMP_FMM27 = TaggedRecord(
    "rule_file_stageless_comp_fmm27", [Tag("file", "file", STRING, required=True),
                                       Tag("ftye", "file_type", INT, required=True)],
    unread=STAGELESS_COMP.unread + (
        'PLgn', 'tems', 'Cdpc', 'ACfl', 'ind1', 'ftac', 'ldos', 'vlys', 'btfo', 'typz', 'PrSt',
        'MxBT', 'btld', 'mxNH', 'fnrg', 'rkli', 'sfst', 'mcld', 'apmn', 'lgfx', 'cmps', 'cuni',
        'vwon', 'rqgp', 'nelt', 'ssif', 'NoMd', 'nscc', 'extc', 'RTiC', 'MtGr', 'mgqm', 'RDCA',
        'ktsr', 'Dotc'),
    note="a competition configured without a stage list, and no source folder")


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

_NATION_FMM27 = (("_reserve_comps", NATION_RESERVE_COMPS_FMM27), ("_comps", NATION_COMPS_FMM27),
                 ("_rules", NATION_RULES_FMM27))


def schema_for_fmm27(block: TaggedBlock) -> TaggedRecord:
    """The declared schema an FMM27 rule file reads with."""
    if "stgs" in block.top_tags:
        return CR.FILE
    name = block.get("file") or ""
    for suffix, rec in _NATION_FMM27:
        if name.endswith(suffix):
            return rec
    return CONTINENT_RULES_FMM27 if "PLgn" in block.top_tags else STAGELESS_COMP_FMM27


RULE_FILES_TABLE_FMM27 = TaggedTableDef(
    name="rule_files",
    locator=locate_rule_files,
    schema=schema_for_fmm27,
)


def rule_files_table(mm: Any) -> TaggedTableDef:
    """The rule files' declaration for this save's format."""
    return RULE_FILES_TABLE_FMM27 if save_format(mm) == FMM27 else RULE_FILES_TABLE


# ---- what the rule files give ----------------------------------------------------------------
def team_counts(mm: Any) -> Dict[int, int]:
    """{competition uid: teams} from every nation's `_comps` team-count rules -- the rules
    that name a competition and carry `ntms`, with `nxss` 0."""
    out: Dict[int, int] = {}
    table = rule_files_table(mm)
    for b in table.blocks(mm):
        if table.schema_for(b) not in (NATION_COMPS, NATION_COMPS_FMM27):
            continue
        for rule in table.read(b)["team_rules"] or []:
            if rule["comp_uid"] is not None and rule["teams"] is not None and not rule["nxss"]:
                out[rule["comp_uid"]] = rule["teams"]
    return out


def work_permits(mm: Any) -> List[Dict[str, Any]]:
    """One row per work-permit rule a rule file carries: {file, set ('wkpm' or 'wkFT'),
    rule (wopm, wtpm, ctrn, stWP, appe), scheme, info, cash, curr, fee, decd, wpcc, wpdw,
    wpaf}. `info` is the int parameter, or None where the parameter is cash (`cash`, `curr`).

    Read from every rule file that carries the tag: the nations' `_rules` and a few
    competition files (`swe_second_2018`; most competition files' sets are empty). A
    nation's `_rules` is stored twice, merged and in its group; the copies are identical
    and give one set of rows."""
    rows: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], Any] = {}
    for b in rule_files_table(mm).blocks(mm):
        name = b.get("file")
        for set_tag in ("wkpm", "wkFT"):
            value = b.get(set_tag)
            if value is None:
                continue
            if (name, set_tag) in seen:
                if seen[(name, set_tag)] != value:
                    raise ValueError(f"{name}: the two copies' {set_tag} differ")
                continue
            seen[(name, set_tag)] = value
            ws = WORK_PERMITS.read(value)
            for code in PERMIT_RULE_CODES:
                r = ws[code.lower()]
                if r is None:
                    continue
                info = r["info"]
                cash = info if isinstance(info, dict) else None
                rows.append({
                    "file": name, "set": set_tag, "rule": code, "scheme": r["scheme"],
                    "info": None if cash else info,
                    "cash": cash["cash"] if cash else None,
                    "curr": cash["curr"] if cash else None,
                    "fee": r["fee"], "decd": r["decd"], "wpcc": r["wpcc"],
                    "wpdw": r["wpdw"], "wpaf": r["wpaf"]})
    return rows


# ---- checks: the framing and the share of the span that is read ------------------------------
def is_bare(mm: Any, block: TaggedBlock) -> bool:
    """True for a block with no tagless-container head (the merged `<nat>_rules`)."""
    return mm[block.start - 6:block.start - 4] != _CONTAINER_HEAD


def framing_problems(mm: Any) -> List[str]:
    """Where the region breaks the layout in the docstring: a group whose count k is not the
    number of container files that follow, or a bare block that is not a `<nat>_rules`."""
    table = rule_files_table(mm)
    files = table.blocks(mm)
    problems: List[str] = []
    i = 0
    while i < len(files):
        b = files[i]
        if is_bare(mm, b):
            if (not (b.get("file") or "").endswith("_rules")
                    and table.schema_for(b) is not CONTINENT_RULES_FMM27):
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
