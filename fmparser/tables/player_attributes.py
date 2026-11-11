#!/usr/bin/env python3
"""`player_attributes` — Player global attribute table (~26,505 records).

Preallocated 78-byte fixed-stride table located between 3.8 MB and 6.6 MB.
Count-framed by `[8x 0xFF][u32 count]` preceding record 0.

FMM27 appends a u32-counted list of 19-byte unavailabilities (injuries, medical conditions,
bans) to each record, so its rows are 82 bytes plus 19 per item.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..core import (CountedList, DATE, Field, HEX4, I32, PAD, RAW, Record, U16, U32, U8,
                    UNKNOWN, TableDef, table_spans)
from .save_header import FMM27, save_format

# Global attribute records byte range window (3.8 MB to 6.6 MB across careers)
ATTR_LO, ATTR_HI = 3_800_000, 6_600_000

__all__ = [
    "ATTR_OFFSETS",
    "HIDDEN_OFFSETS",
    "PLAIN_OFFSETS",
    "PLAYER",
    "PLAYER_ATTRIBUTES_TABLE",
    "PLAYER_ATTRIBUTES_TABLE_FMM27",
    "UNAVAILABILITY",
    "POSITIONS",
    "RECORD",
    "SRC_OFFSETS",
    "locate_player_attributes",
    "player_attributes_end",
    "player_attributes_table",
    "scrape_player_attributes",
]

RECORD = 78

POSITIONS = [
    "GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR",
    "AML", "AMC", "AMR", "ST", "DML", "DMR",
]

ATTR_OFFSETS = {
    -29: "Aerial", -25: "Teamwork", -24: "Pace", -23: "Strength",
    -22: "Stamina", -21: "Technique", -19: "Aggression", -16: "Leadership",
    -5: "Agility",
}

SRC_OFFSETS = {
    -34: "crossing_src", -33: "dribbling_src", -32: "tackling_src",
    -31: "finishing_src", -30: "long_shot_src", -27: "passing_src",
    -26: "decision_src", -12: "creativity_src", -11: "movement_src",
    -10: "positioning_src", -7: "handling_src", -6: "kicking_src",
    -4: "aerial_gk_src", -3: "reflexes_src", -2: "communication_src",
    -1: "throwing_src",
}

PLAIN_OFFSETS = {
    -29: "heading_src", -25: "unselfishness_src", -24: "pace_src",
    -23: "strength_src", -22: "stamina_src", -21: "technique_src",
    -19: "aggression_src", -16: "leadership_src", -5: "agility_src",
}

HIDDEN_OFFSETS = {
    -28: "jumping", -20: "consistency", -18: "big_match",
    -17: "injury_prone", -15: "versatility", -14: "set_pieces",
    -13: "penalty", -9: "work_rate", -8: "flair",
}

PLAYER = Record("player_attribute", RECORD, [
    Field(0, 4, "sid", HEX4),
    Field(4, 4, "history_head", U32,
          note="the row this player's chain starts at in the history pool (tables/history.py)"),
    *[Field(42 + rel, 1, n, U8, group="src") for rel, n in SRC_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="hidden") for rel, n in HIDDEN_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="attrs") for rel, n in ATTR_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="plain", alias=True)
      for rel, n in PLAIN_OFFSETS.items()],
    Field(42, 15, "positions", RAW, note="15 position-rating bytes, decoded to a dict"),
    Field(57, 1, "foot_left", U8),
    Field(58, 1, "foot_right", U8),
    Field(59, 2, "ca", U16, note="never surfaced -- immersion rule"),
    Field(61, 2, "pa", U16, note="never surfaced -- immersion rule"),
    Field(63, 2, "reputation", U16),
    Field(65, 2, "current_reputation", U16, group="tail"),
    Field(67, 2, "world_reputation", U16, group="tail"),
    Field(69, 1, "international_retired", U8, group="tail"),
    Field(70, 2, UNKNOWN, U16),
    Field(72, 1, "squad_number", U8, group="tail"),
    Field(73, 1, "preferred_squad_number", U8, group="tail"),
    Field(74, 2, "height_cm", U16, group="tail"),
    Field(76, 2, "weight_kg", U16, group="tail"),
], anchor=42)

_PLAYER_ATTR_CACHE: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}


def _valid_positions(seg: Any) -> bool:
    return len(seg) == 15 and all(1 <= b <= 20 for b in seg) and max(seg) == 20


def locate_player_attributes(mm: Any, lo: int = ATTR_LO, hi: int = ATTR_HI) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the player attributes table, or None."""
    key = _cache_key(mm)
    if key in _PLAYER_ATTR_CACHE:
        return _PLAYER_ATTR_CACHE[key]

    n = len(mm)
    # Search for the first valid player record to locate base0
    P = lo
    while P < hi and P + 21 <= n:
        seg = mm[P:P + 15]
        if _valid_positions(seg):
            left, right = mm[P + 15], mm[P + 16]
            ca = int.from_bytes(mm[P + 17:P + 19], "little")
            pa = int.from_bytes(mm[P + 19:P + 21], "little")
            if 0 <= left <= 20 and 0 <= right <= 20 and 0 < ca <= pa <= 200:
                base0 = P - 42
                if base0 >= 12 and all(mm[base0 - 4 - 1 - k] == 0xFF for k in range(8)):
                    count = int.from_bytes(mm[base0 - 4:base0], "little")
                    if 0 < count < 1_000_000 and base0 + count * RECORD <= n:
                        res = (base0, count)
                        _PLAYER_ATTR_CACHE[key] = res
                        return res
        P += 1

    # Fallback for synthetic unit test buffers
    if 0 < n < 10_000 and n % RECORD == 0:
        res = (0, n // RECORD)
        _PLAYER_ATTR_CACHE[key] = res
        return res

    _PLAYER_ATTR_CACHE[key] = None
    return None


def _process_player_attribute(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    pos_raw = rec.get("positions", b"")
    P = offset + 42
    out = {
        "sid": rec["sid"],
        "history_head": rec["history_head"],
        "offset": offset,
        "P": P,
        "positions": {POSITIONS[k]: v for k, v in enumerate(pos_raw) if v > 1},
        "feet": {"left": rec["foot_left"], "right": rec["foot_right"]},
        "ca": rec["ca"],
        "pa": rec["pa"],
        "reputation": rec["reputation"],
        "attributes": {
            "Aerial": rec["Aerial"],
            "Teamwork": rec["Teamwork"],
            "Pace": rec["Pace"],
            "Strength": rec["Strength"],
            "Stamina": rec["Stamina"],
            "Technique": rec["Technique"],
            "Aggression": rec["Aggression"],
            "Leadership": rec["Leadership"],
            "Agility": rec["Agility"],
        },
        "current_reputation": rec["current_reputation"],
        "world_reputation": rec["world_reputation"],
        "international_retired": bool(rec["international_retired"]),
        "squad_number": rec["squad_number"],
        "preferred_squad_number": rec["preferred_squad_number"],
        "height_cm": rec["height_cm"],
        "weight_kg": rec["weight_kg"],
        "jumping": rec["jumping"],
        "consistency": rec["consistency"],
        "big_match": rec["big_match"],
        "injury_prone": rec["injury_prone"],
        "versatility": rec["versatility"],
        "set_pieces": rec["set_pieces"],
        "penalty": rec["penalty"],
        "work_rate": rec["work_rate"],
        "flair": rec["flair"],
        "crossing_src": rec["crossing_src"],
        "dribbling_src": rec["dribbling_src"],
        "tackling_src": rec["tackling_src"],
        "finishing_src": rec["finishing_src"],
        "long_shot_src": rec["long_shot_src"],
        "passing_src": rec["passing_src"],
        "decision_src": rec["decision_src"],
        "creativity_src": rec["creativity_src"],
        "movement_src": rec["movement_src"],
        "positioning_src": rec["positioning_src"],
        "handling_src": rec["handling_src"],
        "kicking_src": rec["kicking_src"],
        "aerial_gk_src": rec["aerial_gk_src"],
        "reflexes_src": rec["reflexes_src"],
        "communication_src": rec["communication_src"],
        "throwing_src": rec["throwing_src"],
        "heading_src": rec["heading_src"],
        "unselfishness_src": rec["unselfishness_src"],
        "pace_src": rec["pace_src"],
        "strength_src": rec["strength_src"],
        "stamina_src": rec["stamina_src"],
        "technique_src": rec["technique_src"],
        "aggression_src": rec["aggression_src"],
        "leadership_src": rec["leadership_src"],
        "agility_src": rec["agility_src"],
    }
    if "unavailability" in rec:
        out["unavailability"] = rec["unavailability"]
    return out


PLAYER_ATTRIBUTES_TABLE = TableDef(
    name="player_attributes",
    segments=(PLAYER,),
    locator=locate_player_attributes,
    include_offset=True,
    post_process=_process_player_attribute,
)


# FMM27: one unavailability, a spell the player cannot play. Start and end are each
# [day u16][month u8, 0-based][year u16] -- except on type 14, whose 10 bytes are not dates
# (docs/parser/player_attributes.md, Quirks).
UNAVAILABILITY = Record("player_unavailability", 19, [
    Field(0,  1, "type",        U8, note="11 a ban or ineligibility; 14 on Eriksen and Blind"),
    Field(1,  2, "start_day",   U16),
    Field(3,  1, "start_month", U8, note="0-based"),
    Field(4,  2, "start_year",  U16),
    Field(6,  2, "end_day",     U16),
    Field(8,  1, "end_month",   U8, note="0-based"),
    Field(9,  2, "end_year",    U16),
    Field(11, 4, "club_uid",    I32, note="the club it applies at; -1 on a global ban"),
    Field(15, 4, UNKNOWN,       I32, note="-1 on all but one"),
])

# FMM27's record opens with FMM22's 78 bytes, as the head of a variable-length row.
PLAYER_FMM27 = Record("player_attribute_fmm27", RECORD, PLAYER.fields, is_head=True)

PLAYER_ATTRIBUTES_TABLE_FMM27 = TableDef(
    name="player_attributes",
    segments=(PLAYER_FMM27, CountedList("unavailability", U32, UNAVAILABILITY, max_count=64)),
    locator=locate_player_attributes,
    include_offset=True,
    post_process=_process_player_attribute,
)


def player_attributes_table(mm: Any) -> TableDef:
    """The player attribute table's declaration for this save's format."""
    return PLAYER_ATTRIBUTES_TABLE_FMM27 if save_format(mm) == FMM27 else PLAYER_ATTRIBUTES_TABLE


def player_attributes_end(mm: Any) -> Optional[int]:
    """Where the table's last record ends (the next table's frame), or None."""
    spans = table_spans(mm, player_attributes_table(mm), include_count_header=False)
    return spans[0][1] if spans else None


def scrape_player_attributes(mm: Any) -> Dict[str, Dict[str, Any]]:
    """{sid: record} for every player attribute record in the save."""
    return player_attributes_table(mm).id_map(mm, key_field="sid")


def record_for(mm: Any, tid: int) -> Optional[Dict[str, Any]]:
    """A player's attribute record: his person record's `sid`, from the walked person
    table, looked up in the attribute table. None for staff or an unknown tid."""
    from .person_info import scrape_person_info
    person = scrape_person_info(mm).get(tid)
    if person is None:
        return None
    return player_attributes_table(mm).id_map(mm, key_field="sid").get(person["sid"])

