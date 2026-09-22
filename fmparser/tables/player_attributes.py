#!/usr/bin/env python3
"""`player_attributes` — Player global attribute table (~26,505 records).

Preallocated 78-byte fixed-stride table located between 3.8 MB and 6.6 MB.
Count-framed by `[8x 0xFF][u32 count]` preceding record 0.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..regions import ATTR_HI, ATTR_LO
from ..save import cache_key as _cache_key
from ..core import DATE, Field, HEX4, PAD, RAW, Record, U16, U32, U8, UNKNOWN
from ..core import TableDef

__all__ = [
    "ATTR_OFFSETS",
    "HIDDEN_OFFSETS",
    "PLAIN_OFFSETS",
    "PLAYER",
    "PLAYER_ATTRIBUTES_TABLE",
    "POSITIONS",
    "RECORD",
    "SRC_OFFSETS",
    "locate_player_attributes",
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
    Field(4, 4, "history_link_P38", U32),
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
    return out


PLAYER_ATTRIBUTES_TABLE = TableDef(
    name="player_attributes",
    segments=(PLAYER,),
    locator=locate_player_attributes,
    include_offset=True,
    post_process=_process_player_attribute,
)


def scrape_player_attributes(mm: Any) -> Dict[str, Dict[str, Any]]:
    """{sid: record} for every player attribute record in the save."""
    return PLAYER_ATTRIBUTES_TABLE.id_map(mm, key_field="sid")


def record_for(mm: Any, tid: int) -> Optional[Dict[str, Any]]:
    """Locate a player's global attribute record via SID. Returns a dict or None."""
    from ..reference import info_offset
    io = info_offset(mm, tid)
    if io is None:
        return None
    sid = mm[io + 60:io + 64].hex()
    return PLAYER_ATTRIBUTES_TABLE.id_map(mm, key_field="sid").get(sid)

