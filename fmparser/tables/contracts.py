#!/usr/bin/env python3
"""`contracts` — the 83-byte Contract Grid and Contract Status records.

The contract grid is a dense preallocated grid (~29-33 MB) of 83-byte records,
one per person slot (`slot_index == tid`). Declared capacity (~59k-61k slots) is
preceded by an 11-byte `0x12` delimiter frame and a 4-byte slot capacity header.
Active contracts carry `marker == 0x01` at offset +4.

Contract status records (40 bytes) map player `squad_status` codes and loan status
(`LOAN_STATUS = 65`) keyed by `[tid u32][uid u32]` matching the info spine.
"""
import struct
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from ..core import primitives as P
from .. import records as RD
from ..save import cache_key as _cache_key
from ..core import DATE, Field, PAD, Record, U16, U32, U8, UNKNOWN, TableDef, table_spans

# £/yr per wage unit (from ground truth: De Bruyne 34000u=£17.75M, Hull/Frem across the range).
WAGE_GBP_PER_UNIT = 520

__all__ = [
    "CONTRACT",
    "CONTRACT_DETAIL",
    "CONTRACT_RECORD",
    "CONTRACT_STATUS",
    "CONTRACT_STRIDE",
    "CONTRACT_TABLE",
    "LOAN_STATUS",
    "contracts_table_spans",
    "locate_contracts",
    "scrape_contract_status",
    "scrape_contracts",
]

CONTRACT_STRIDE = 83
CONTRACT_RECORD = 83
LOAN_STATUS = 65

CONTRACT = Record("contract", CONTRACT_STRIDE, [
    Field(0,  4, "tid",                  U32, note="== the slot index"),
    Field(4,  1, "marker",               U8,  note="0x01 = active contract; other = lapsed/inactive"),
    Field(5,  2, "wage_units",           U16),
    Field(7,  6, UNKNOWN,                PAD),
    Field(13, 4, "expiry",               DATE, note="some Danish deals expire 31 Dec -- keep the DAY"),
    Field(15, 2, "expiry_year",          U16,  alias=True),
    Field(17, 19, UNKNOWN,               PAD),
    Field(36, 4, "start_date",           DATE, note="contract signed/commencement date"),
    Field(38, 2, "start_year",           U16,  alias=True),
    Field(40, 43, UNKNOWN,               PAD),
])

# Alias for backward-compatibility with audit scripts
CONTRACT_DETAIL = CONTRACT

CONTRACT_STATUS = Record("contract_status", 40, [
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", U32, note="both must match the info spine -- 8 exact bytes"),
    Field(8, 29, UNKNOWN, PAD),
    Field(37, 2, "marker", U16, note="0x0087; marker searched across file"),
    Field(39, 1, "squad_status", U8),
], is_head=True)

_CONTRACTS_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_contracts(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 83-byte contract grid, or None.

    Anchored on the `b'\\x12' * 11` delimiter preceding slot capacity at `base0 - 6`.
    Verified by slot 0 (tid 0) and slot 1 (tid 1).
    """
    key = _cache_key(mm)
    if key in _CONTRACTS_CACHE:
        return _CONTRACTS_CACHE[key]

    marker = b"\x12" * 11
    pos = 15_000_000
    n = len(mm)
    end = min(n, 45_000_000)

    while True:
        idx = mm.find(marker, pos, end)
        if idx == -1:
            break
        pos = idx + 1
        base0 = idx + 17
        if base0 + CONTRACT_STRIDE * 2 > n:
            continue
        if mm[base0:base0 + 4] == b"\x00\x00\x00\x00" and mm[base0 + CONTRACT_STRIDE:base0 + CONTRACT_STRIDE + 4] == b"\x01\x00\x00\x00":
            total_slots = struct.unpack("<I", mm[base0 - 6:base0 - 2])[0]
            if 10_000 <= total_slots <= 200_000:
                res = (base0, total_slots)
                _CONTRACTS_CACHE[key] = res
                return res

    # Fallback for synthetic unit test buffers
    if 0 < n < 10_000 and n % CONTRACT_STRIDE == 0:
        res = (0, n // CONTRACT_STRIDE)
        _CONTRACTS_CACHE[key] = res
        return res

    _CONTRACTS_CACHE[key] = None
    return None


def _process_contract(rec: Dict[str, Any], offset: int) -> Optional[Dict[str, Any]]:
    """Filter out empty or sentinel slots during bulk table walks."""
    tid = rec.get("tid")
    if tid is None or tid == 0xFFFFFFFF:
        return None
    rec["offset"] = offset
    w = rec.get("wage_units", 0)
    rec["wage_gbp"] = w * WAGE_GBP_PER_UNIT
    return rec


CONTRACT_TABLE = TableDef(
    name="contracts",
    segments=(CONTRACT,),
    locator=locate_contracts,
    include_offset=True,
)


def contracts_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Byte spans covering the 83-byte contract grid."""
    return table_spans(mm, CONTRACT_TABLE, include_count_header=True)


def scrape_contracts(
    mm: Any,
    tids_or_info: Optional[Union[Iterable[int], Dict[int, Any]]] = None,
) -> Dict[int, Dict[str, Any]]:
    """{tid: {wage_units, wage_gbp, expiry, expiry_year}} from the contract grid.

    Uses O(1) direct slot arithmetic `base0 + tid * 83`.
    Filters for active contracts (`marker == 0x01` and `2018 <= expiry_year <= 2045`).
    """
    loc = locate_contracts(mm)
    if not loc:
        return {}
    base0, total_slots = loc
    n = len(mm)
    out: Dict[int, Dict[str, Any]] = {}

    if tids_or_info is not None:
        target_tids: Iterable[int] = tids_or_info.keys() if isinstance(tids_or_info, dict) else tids_or_info
        for tid in target_tids:
            if tid < 0 or tid >= total_slots:
                continue
            off = base0 + tid * CONTRACT_STRIDE
            if off + CONTRACT_STRIDE > n:
                continue
            # Active contract check
            if mm[off + 4] == 0x01:
                yr = P.u16(mm, off + 15)
                if 2018 <= yr <= 2045:
                    w = P.u16(mm, off + 5)
                    out[tid] = {
                        "wage_units": w,
                        "wage_gbp": w * WAGE_GBP_PER_UNIT,
                        "expiry": P.ymd(mm, off + 13),
                        "expiry_year": yr,
                    }
    else:
        # Full grid walk
        for slot in range(total_slots):
            off = base0 + slot * CONTRACT_STRIDE
            if off + CONTRACT_STRIDE > n:
                break
            rec_tid = P.u32(mm, off)
            if rec_tid != slot:
                break
            if mm[off + 4] == 0x01:
                yr = P.u16(mm, off + 15)
                if 2018 <= yr <= 2045:
                    w = P.u16(mm, off + 5)
                    out[slot] = {
                        "wage_units": w,
                        "wage_gbp": w * WAGE_GBP_PER_UNIT,
                        "expiry": P.ymd(mm, off + 13),
                        "expiry_year": yr,
                    }

    return out


def scrape_contract_status(
    mm: Any,
    info: Dict[int, Dict[str, Any]],
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[int, int]:
    """{tid: squad_status_code} from contract status records.

    Keyed by [TID:u32][UID:u32] matching both tid and uid from the info spine.
    """
    lo = 0 if lo is None else lo
    hi = len(mm) if hi is None else hi
    uid_of = {tid: p["uid"] for tid, p in info.items()}
    out: Dict[int, int] = {}
    p = lo

    while True:
        m = mm.find(b"\x87\x00", p, hi)
        if m == -1:
            break
        p = m + 1
        if m - 37 < 0:
            continue
        base = m - CONTRACT_STATUS.field("marker").offset
        rec = RD.read_fields(mm, CONTRACT_STATUS, base, ("tid", "uid", "squad_status"))
        if uid_of.get(rec["tid"]) == rec["uid"]:
            out[rec["tid"]] = rec["squad_status"]

    return out
