#!/usr/bin/env python3
"""`comp_rules` — each competition's stage and round structure, from `comp_<uid>.dat`.

Located inside the save's zstd tail archive (Shape D), one member per loaded competition,
named by the competition's `uid` -- the same uid the competition table in the main save
holds, so `staging.competitions.uid` names the member directly.

A member is a fixed 54-byte header (`HEADER`, declared below) followed by a block in the
tagged format. The header declares the block's top-level field count at +50, so the
table is a `TaggedTableDef` with one row per member: `locate_comp_rules` returns (54, n)
and the engine reads exactly n fields. They end at the file trailer (`XSvC`, `EdBr`, `EdDt`, `SubF` = the source path);
binary runtime state follows and is not read. A member declaring 0 fields is a stub (the
competition is loaded but not configured).

The tagged block is declared per TAG below -- FILE -> stgs -> STAGE -> rnds -> ROUND, with
NAME_REF for a name held in a container -- and read through those declarations
(`core.TaggedRecord`). A STAGE's `indx` is the number `fix_man.dat` carries at
+76 (`stage_index`); element k of its `rnds` is the round `fix_man.dat` carries at +77
(`round_index`). `scripts/audit/audit_records.py --map` prints the schemas.

A name id is either the scalar value of `stnm` or the `stgn` child of an `stnm` container;
both forms occur, and a scalar may be stored as a PAIR of equal u32s. Name ids resolve
through the round-name catalog in the main save (`tables/rounds.py`). Verified against the
in-game fixture screens: League Path / Third Qualifying Round / Playoff / Group D / First
Knockout Round (EURO Cup and Champions Cup), Preliminary Phase / Championship Group (3F
Superliga) and Third Round (Sydbank Pokalen).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from ..core import archive as A
from ..core import (
    FOURCC, INT, PAD, U16, U32, UNKNOWN, AnyOf, Field, ListOf, Nested, Record, Tag,
    TaggedRecord, TaggedSchemaError, TaggedTableDef, TaggedTableError)

__all__ = [
    "COMP_RULES_TABLE",
    "FILE",
    "HEADER",
    "NAME_REF",
    "ROUND",
    "STAGE",
    "MEMBER_PATTERN",
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


# ---- the tagged block: FILE -> stgs -> STAGE -> rnds -> ROUND ----------------------------
# Declared per TAG (core.TaggedRecord): each Tag is read, and every other tag
# the member carries is listed as `unread` -- seen and deliberately not read, the
# counterpart of a declared-UNKNOWN byte. The unread lists are every tag observed across
# all 30 Frem saves and bucaspor-2023-05-20 (2,263 configured members, 4,829 stages, 6,299
# rounds), in order of frequency, then the further tags the data dictionary's 453
# competition rule files carry (tables/rule_files.py), which read with these same schemas;
# tests/test_comp_rules.py and tests/test_rule_files.py fail on a tag that is neither.

# A name reference: the stage/round name id, sometimes held in a container instead of
# stored directly on `stnm`.
NAME_REF = TaggedRecord("comp_rules_name_ref", [
    Tag("id",   "ref_code", FOURCC, required=True, note="'stnm'"),
    Tag("stgn", "name_id",  INT,    required=True,
        note="round-name catalog id (tables/rounds.py); may be a repeated pair (28, 28)"),
], unread=("DBID",))

NAME_ID = AnyOf(INT, Nested(NAME_REF, pick="name_id"))

ROUND = TaggedRecord("comp_rules_round", [
    Tag("stnm", "round_name_id", NAME_ID,
        note="151 'Third Qualifying Round', 17 'Quarter Final', 20 'Final' ..."),
    Tag("ntms", "round_teams",   INT,
        note="teams in the round; absent where the draw sets it (fra_ligue_cup's early rounds)"),
    Tag("nmlg", "legs",          INT, note="legs per tie, 1 or 2"),
], unread=(
    'nmmt', 'date', 'drdt', 'ctmp', 'tvds', 'vlgr', 'ofsd', 'nmxt', 'drrl', 'prio', 'wrnk',
    'lrnk', 'nmrp', 'dat2', 'subr', 'wnpz', 'strl', 'iqum', 'apmn', 'tvty', 'mstc', 'lspz',
    'rank', 'nrdw', 'nrdl', 'crlm', 'SgSd', 'mnsc', 'nmrg', 'nchd', 'MnxO', 'MnxT', 'Sran',
    'spst', 'lgwz', 'ldpz',
    # ...and the data dictionary's rule files (tables/rule_files.py) add:
    'dpas', 'atpm', 'fxri', 'gtmp', 'tvmp', 't2pa', 'lpnd', 'ppmt', 'stfl', 'rusn', 'numb'),
    note="element k of a stage's rnds = fix_man +77 round_index k")

STAGE = TaggedRecord("comp_rules_stage", [
    Tag("id",   "stage_code",    AnyOf(FOURCC, INT), required=True,
        note="'leag' 'cham' 'prom' 'rele' 'bppr' 'chpr' 'play' 'grou' 'cup' ...; "
             "svk_first_4_qualifiers' stage 4 stores the number 4"),
    Tag("indx", "stage_index",   INT,    required=True, note="= fix_man +76 stage_index"),
    Tag("type", "stage_type",    INT,    required=True,
        note="0 knockout, 1 league, 2 groups, 6 play-off feeder"),
    Tag("ntms", "stage_teams",   INT,    note="teams in the stage"),
    Tag("stnm", "stage_name_id", NAME_ID,
        note="2000016479 'League Path', 236 'Preliminary Phase', 73 'Group Stage' ..."),
    Tag("ngps", "n_groups",      INT,    note="groups in a group stage"),
    Tag("rnds", "rounds",        ListOf(ROUND), note="the knockout rounds, in order"),
], unread=(
    'strq', 'tems', 'ftac', 'advs', 'sort', 'subr', 'prio', 'sche', 'rank', 'nrds', 'srnd',
    'ctll', 'ttac', 'qurl', 'relr', 'grrl', 'gnty', 'gpdt', 'strs', 'vlgr', 'sblt', 'exfp',
    'prmr', 'edtv', 'lgrl', 'fxor', 'RLtm', 'stfl', 'ngrt', 'clyc', 'tppr', 'mxtm', 'mntm',
    'pfpr', 'przm', 'sths', 'exlg', 'pspl', 'rkli', 'rvtm', 'TrSt', 'shsn', 'ByTm', 'shnt',
    'rfpr', 'OPpr', 'pwin', 'pdrw', 'comp', 'rndt', 'AlOO', 'sch?', 'tfpr', 'mtrl', 'pdad',
    'ptsd', 'btpr', 'acod', 'shrd', 'shpo', 'lwpz', 'drpz', 'hspp', 'TlCh', 'gcfp', 'dasn',
    'desc', 'hdst', 'pris', 'stsp', 'sthU', 'clyb', 'tvDd', 'FtEx', 'swtm', 'FtDt', 'jcom',
    'StSi', 'srbh', 'tmPL', 'plfd', 'MnGt', 'MxGt', 'seed', 'mstc', 'mxlg', 'ppnw', 'ppnd',
    'srst', 'fsff', 'tmor', 'cTmS', 'tvty', 'stsi', 'sequ', 'shi1', 'vdbf', 'midp', 'pref',
    'ExHG', 'NrTm',
    # ...and the data dictionary's rule files (tables/rule_files.py) add:
    'SCsn', 'pdef', 'adef', 'psr1', 'psr2', 'rran', 'ahrn', 'gptm', 'NpTm', 'AsCH', 'apmn',
    'lsfd', 'CrsD', 'alfp', 'SCos', 'stan', 'cftp', 'sbsn', 'lsff', 'dSaC', 'USYh', 'UEYh',
    'fpln', 'FtPr', 'endt', 'bfpr', 'ulsv', 'text', 'ssdi', 'dfpz', 'SFSL', 'shi2', 'FrTm',
    'dtPP', 'cldp', 'Cnrd', 'mr2l', 'gtmp', 'tvmp', 'ppmt'),
    note="one element of the member's stgs list")

FILE = TaggedRecord("comp_rules_file", [
    Tag("stgs", "stages", ListOf(STAGE), required=True, note="the stage list, in order"),
], unread=(
    'ftye', 'vers', 'type', 'year', 'ygap', 'dtrn', 'bsyr', 'inac', 'levl', 'ilgf', 'Bran',
    'file', 'XSvC', 'EdBr', 'EdDt', 'SubF', 'fnrg', 'itvm', 'crgt', 'fxds', 'Cdpc', 'ACfl',
    'tems', 'comp', 'vsdp', 'lgto', 'natl', 'MtTv', 'FxSt', 'ptsd', 'rkli', 'desc', 'aldt',
    'ldos', 'hlps', 'fxri', 'dcin', 'typz', 'ind1', 'ftac', 'lgfx', 'sudt', 'mstc', 'styr',
    'VRrl', 'mnsc', 'FAif', 'mgqm', 'yhos', 'sfal', 'vlys', 'tfxt', 'CcQR', 'UdFR', 'updy',
    'btfo', 'CcEx', 'dsrl', 'crlm', 'mcld', 'AfxD', 'fxrl', 'CdSr', 'cmps', 'mxss', 'Uddr',
    'aqtp', 'fnlc', 'NoMd', 'StPl', 'fsqt', 'cita', 'fycl', 'yctf', 'ycfm', 'MtAc', 'nptp',
    'snsd', 'rquh', 'midp', 'IChf', 'rqgp', 'prcm', 'Ucdr', 'sfst', 'LtfP', 'dahr', 'enyr',
    'GtRc', 'DOmf', 'dbmu', 'wkpm', 'sblt', 'chdc', 'btld', 'mdct', 'qurl', 'dbss', 'DbLm',
    'FxPr', 'DNSC', 'SlPy', 'poff', 'StLv', 'Bltp', 'edhm', 'iqtb', 'srdl', 'mxps', 'rnst',
    'strl', 'hstn', 'agdt', 'CRps', 'MxBT', 'MxMD', 'mntm', 'mxtm', 'tmPL', 'TlMS', 'imdf',
    'spid', 'OdDt', 'nelt', 'ntms', 'fpyc', 'fprc', 'fppz', 'apmn', '%itv', 'ICsl', 'DlCm',
    'YbHC', 'InTS', 'HsPo', 'styo', 'srar', 'usqn', 'othe', 'lsvy', 'RGps', 'SpDs', 'FxCD',
    'mBsc', 'IToc', 'MxBA', 'sdfd', 'edfd', 'cdtd', 'MGin', 'fnUA', 'visd', 'dbps', 'OdDb',
    'extc', 'MtGr', 'PrSt', 'rcfm', 'ctuf', 'RnsP', 'dtty', 'duni', 'prty',
    # ...and the data dictionary's rule files (tables/rule_files.py) add:
    'vwon', 'avpt', 'Sscu', 'Tp3t', 'ssif', 'rklp', 'derb', 'pris', 'MnNm', 'cLqT', 'sYro',
    'sYoO', 'RTiC', 'ftcl', 'InLP', 'MrTs', 'LsSh', 'RssR', 'rctf', 'frcl', 'cVpC', 'dsft',
    'psrl', 'ctfo', 'enyo', 'bt2d', 'A*tr', 'rdov', '#03d43e90', 'VlFd', 'CoyH', 'dcoy',
    'bpld', 'fVhR', 'kRtI', 'plpo', 'rsid', 'FtDt', 'Lwtp', 'SPyi', 'qFcL', 'HiHn', 'pmXy',
    'aPaW', 'eDpM', 'mtfl', '#20aac028', 'ycov', 'LRSR', 'CrCb', 'oqtc', 'rUqT', 'mssf'),
    note="the member's top-level fields; the trailer is XSvC EdBr EdDt SubF")


def locate_comp_rules(blob: Any) -> List[Tuple[int, int]]:
    """[(first field, declared field count)] -- a member's one tagged block, after its
    header; [] for a member too short to hold the header."""
    if len(blob) < HEADER.span:
        return []
    return [(HEADER.span, HEADER.read(blob, 0)["n_fields"])]


COMP_RULES_TABLE = TaggedTableDef(
    name="comp_rules",
    member="comp_<uid>.dat",
    locator=locate_comp_rules,
    schema=FILE,
)


def scrape(blob: Any) -> List[Tuple[Optional[str], int, Any]]:
    """The member's top-level tagged fields -- exactly as many as its header declares;
    raises TaggedTableError otherwise."""
    blocks = COMP_RULES_TABLE.blocks(blob)
    return blocks[0].fields if blocks else []


def stage_rows(uid: int, fields: List) -> List[Dict[str, Any]]:
    """One row per (stage, round), read through the declared FILE/STAGE/ROUND schemas; a
    stage with no round list gives one row with round_index None."""
    rows: List[Dict[str, Any]] = []
    if not fields:                  # a stub member: loaded, not configured, declares nothing
        return rows
    try:
        stages = FILE.read(fields)["stages"]
    except TaggedSchemaError as e:
        raise TaggedTableError(f"comp_rules: competition {uid}: {e}") from e
    for st in stages:
        stage = {"uid": uid, **{k: st[k] for k in (
            "stage_index", "stage_code", "stage_type", "stage_teams", "stage_name_id",
            "n_groups")}}
        rounds = st["rounds"] or []
        if not rounds:
            rows.append({**stage, "round_index": None, "round_name_id": None,
                         "round_teams": None, "legs": None})
        for k, r in enumerate(rounds):
            rows.append({**stage, "round_index": k, "round_name_id": r["round_name_id"],
                         "round_teams": r["round_teams"], "legs": r["legs"]})
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
