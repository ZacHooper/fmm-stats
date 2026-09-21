#!/usr/bin/env python3
"""Record schemas for staff attribute records."""
from ..schema import Field, Record, U8, U16, U32, UNKNOWN

STAFF_STRIDE = 39
STAFF_GRID_STRIDE = 78

# Offsets relative to the record start (= the ID2 u32).
STAFF_ATTRS = {
    14: "attacking_intent",
    15: "financial_control",
    16: "outfield_coaching",
    17: "goalkeeping_coaching",
    19: "discipline",
    21: "judging_ability",
    22: "judging_potential",
    23: "people_management",
    25: "motivating",
    29: "tactical_knowledge",
    30: "youth_coaching",
}

STAFF_HIDDEN_OFFSETS = {
    18: "hidden_s18",
    20: "hidden_s20",
    24: "hidden_s24",
    26: "hidden_s26",
    27: "hidden_s27",
    28: "hidden_s28",
}

STAFF_FORMATION_SLOTS = {
    31: "formation_preferred",
    32: "formation_attacking",
    33: "formation_defensive",
}

FORMATION_SLOTS = STAFF_FORMATION_SLOTS
HIDDEN_OFFSETS = STAFF_HIDDEN_OFFSETS

STAFF = Record("staff_attribute", STAFF_STRIDE, [
    Field(0,  4, "id2", U32, note="the info record's +64 link"),
    Field(4,  2, "ca", U16, note="never surfaced -- immersion rule"),
    Field(6,  2, "pa", U16, note="never surfaced -- immersion rule"),
    Field(8,  2, "home_reputation", U16),
    Field(10, 2, "current_reputation", U16),
    Field(12, 2, "world_reputation", U16),
    *[Field(o, 1, n, U8, group="attrs") for o, n in STAFF_ATTRS.items()],
    *[Field(o, 1, n, U8, group="hidden") for o, n in STAFF_HIDDEN_OFFSETS.items()],
    *[Field(o, 1, n, U8, group="formation") for o, n in STAFF_FORMATION_SLOTS.items()],
    *[Field(o, 1, UNKNOWN, U8)
      for o in range(14, 31) if o not in {**STAFF_ATTRS, **STAFF_HIDDEN_OFFSETS}],
    *[Field(o, 1, UNKNOWN, U8) for o in range(34, 39)],   # five catalog indices, undecoded
])

_TIER_BANDS = ((3000, "Regional"), (5800, "National"), (10**9, "Continental"))
_STYLE_BANDS = ((7, "Defensive"), (13, "Normal"), (20, "Attacking"))


def style(attacking_intent):
    """Displayed manager Style from `attacking_intent`, or None. DERIVED, not stored."""
    if attacking_intent is None:
        return None
    for ceiling, label in _STYLE_BANDS:
        if attacking_intent <= ceiling:
            return label
    return None


def reputation_tier(world_rep):
    """Displayed manager reputation tier from `world_reputation`, or None."""
    if world_rep is None:
        return None
    for ceiling, label in _TIER_BANDS:
        if world_rep < ceiling:
            return label
    return None

