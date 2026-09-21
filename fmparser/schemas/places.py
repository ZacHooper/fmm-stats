#!/usr/bin/env python3
"""Record schemas for stadiums and cities."""
from ..schema import F32, Field, Record, U8, U16, U32, UNKNOWN

# Stadium: [Id u32][Uid u32][CityId u16][Capacity u32][Expansion u32][len u32][name][00]
STADIUM_HEADER = 18

STADIUM_HEAD = Record("stadium_head", STADIUM_HEADER, (
    Field(0,  4, "id", U32),
    Field(4,  4, "uid", U32),
    Field(8,  2, "city_id", U16),
    Field(10, 4, "capacity", U32),
    Field(14, 4, "expansion_capacity", U32),
), is_head=True)

# City is fixed-width (20 bytes). Layout from fmm-editor's FMM26 `City`.
CITY_RECORD = 20

CITY = Record("city", CITY_RECORD, [
    Field(0,  2, "id",         U16, note="== the slot index; that is what bounds the walk"),
    Field(2,  4, "uid",        U32),
    Field(6,  2, "nation_id",  U16, note="0 on 31 real cities with good coordinates"),
    Field(8,  4, "latitude",   F32),
    Field(12, 4, "longitude",  F32),
    Field(16, 1, "attraction", U8),
    Field(17, 2, "region_id",  U16),
    Field(19, 1, UNKNOWN,      U8),
])
