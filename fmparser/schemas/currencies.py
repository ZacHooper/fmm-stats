#!/usr/bin/env python3
"""Byte-level schemas for Currencies (173 records).

Count-framed table at ~13.98 MB declared with u16 count = 173.
Layout: [Uid u16][len u32][Name (UTF-8)][ExchangeRate f32 per GBP].
"""
from ..schema import F32, Field, Record, U16, U32

CURRENCY_COUNT = 173

CURRENCY_HEAD = Record("currency_head", 6, (
    Field(0, 2, "uid", U16, note="currency unique identifier"),
    Field(2, 4, "len", U32, note="length of UTF-8 name in bytes"),
), is_head=True)

CURRENCY_TAIL = Record("currency_tail", 4, (
    Field(0, 4, "exchange_rate", F32, note="exchange rate units per GBP"),
), is_head=True)
