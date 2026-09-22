#!/usr/bin/env python3
"""DEPRECATED: Forwarding shim for fmparser.core.schema and types.

This module is maintained for backward compatibility with unmigrated parsers.
It will be removed once all domain parsers are migrated to `fmparser.core`.
New code should import directly from `fmparser.core`.
"""
from .core.schema import (
    REGISTRY,
    Field,
    Record,
    _runs,
    per_byte_map,
    validate,
)
from .core.types import (
    DATE,
    F32,
    HEX2,
    HEX4,
    I16,
    I32,
    KIND_WIDTH,
    PAD,
    RAW,
    U8,
    U16,
    U32,
    UNKNOWN,
    PString,
)

__all__ = [
    "DATE",
    "F32",
    "Field",
    "HEX2",
    "HEX4",
    "I16",
    "I32",
    "KIND_WIDTH",
    "PAD",
    "PString",
    "RAW",
    "REGISTRY",
    "Record",
    "U8",
    "U16",
    "U32",
    "UNKNOWN",
    "_runs",
    "per_byte_map",
    "validate",
]
