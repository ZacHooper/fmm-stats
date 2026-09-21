#!/usr/bin/env python3
"""Byte-level schema for Name ID index tables.

The 16-byte records connect entity name IDs to string catalog offsets (browse ordinals).
Three chained count-framed tables:
1. Surnames (~32,148 records)
2. First names (~19,128 records)
3. Nicknames / common names (~9,480 records)
"""
from ..schema import Field, RAW, Record, U32, UNKNOWN

NAME_ID_STRIDE = 16

NAME_ID_ENTRY = Record("name_id_entry", NAME_ID_STRIDE, [
    Field(0, 4, "ordinal", U32, note="index into the browse string table"),
    Field(4, 4, "id", U32, note="id referenced by person record"),
    Field(8, 8, UNKNOWN, RAW),
])
