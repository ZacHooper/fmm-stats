#!/usr/bin/env python3
"""Reading a declared record. The half of the parser that is now generic.

`schema.py` says what a record is; this turns a `Record` plus an offset into values. It does
**no locating**: `walk` is handed its bounds and its predicate, because finding a table is the
part that is genuinely different per table -- six distinct shapes, catalogued in
`docs/parser-architecture.md` -- and a reader that also located things would have to guess.

THE CONSTRAINT THAT SHAPES THIS API
-----------------------------------
`extract.py`'s `dump()` calls `json.dump` with no `sort_keys`, so **the order fields are
inserted is part of the output bytes** and `scripts/assert_identical.py` compares those bytes.
A `read()` that returns the right values in a different order fails the gate -- correctly,
because `load_duckdb.py` reads some of these files positionally.

That is why there is more than one entry point. A record whose emitted dict starts with keys
the caller computed (a tid it already knows, a name it resolved) uses `read_into` on an
existing dict; a record that emits several blocks in a fixed order uses `read_group` per
block. Migrating a parser to this module is an order-preservation exercise, and the API exists
to make preserving order the easy path rather than a thing you remember to check afterwards.
"""
import struct

from . import primitives as P
from .schema import DATE, F32, HEX4, I16, I32, PAD, RAW, U8, U16, U32

# One dispatch table, so adding a kind is one line in `schema.KIND_WIDTH` and one here.
_READERS = {
    U8: P.u8, U16: P.u16, U32: P.u32, I16: P.i16, I32: P.i32,
    F32: P.f32, DATE: P.ymd, HEX4: P.hex4,
}


def read_field(mm, field, base):
    """One field's value. `RAW` yields `bytes`; `PAD` yields None and is never emitted."""
    if field.kind == RAW:
        return bytes(mm[base + field.offset:base + field.offset + field.width])
    if field.kind == PAD or field.kind is None:
        return None
    return _READERS[field.kind](mm, base + field.offset)


def read(mm, rec, base):
    """The whole declared record at `base`, in DECLARATION ORDER.

    Declaration order, not sorted-by-offset: a layout is free to declare a field where it
    belongs conceptually, and the emitted order is the one the author chose. Change the order
    of lines in a layout and you change the output file -- which the acceptance gate will tell
    you about.
    """
    return {f.name: read_field(mm, f, base) for f in rec.fields if f.emits}


def read_at_anchor(mm, rec, anchor_off):
    """The record whose LOCATOR landmark sits at `anchor_off`.

    The player attribute record is found by its SID marker, always described in the project's
    notes as `P` with fields at `P-38` and `P+28`, while the record itself starts 42 bytes
    earlier. Declaring `anchor=42` and calling this keeps the layout in record coordinates and
    does the subtraction exactly once, instead of at every call site -- the "offsets relative
    to what?" ambiguity that `scripts/audit_records.py` already calls out as the bug in its
    first layout.
    """
    return read(mm, rec, anchor_off - rec.anchor)


def read_into(dst, mm, rec, base, names=None):
    """Read into an EXISTING dict, so caller-computed keys keep their place at the front.

    Returns `dst`. This is the shape most migrations need: a parser that builds
    `{"tid": ..., "name": ...}` and then fills in the record's own fields produces a different
    key order than one that reads the record first and updates.
    """
    for f in rec.fields:
        if not f.emits or (names is not None and f.name not in names):
            continue
        dst[f.name] = read_field(mm, f, base)
    return dst


def read_fields(mm, rec, base, names):
    """A named subset, in the order **`names`** gives -- not in declaration order.

    For a parser whose current output order differs from the order the layout reads best in.
    Preserving the existing order is not a concession: changing it changes the output file for
    no gain, and a field order that is explicit at the call site is still a declaration.
    """
    by_name = {f.name: f for f in rec.fields if f.emits}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise KeyError(f"{rec.name} does not emit: {', '.join(map(str, missing))}")
    return {n: read_field(mm, by_name[n], base) for n in names}


def read_group(mm, rec, base, group):
    """One tagged block of the record, in declaration order within the block.

    The player attribute record emits its named attributes, its hidden attributes, its
    entangled source bytes and its identity fields as four blocks in a fixed order. Four
    `read_group` calls state that order in the code; one `read` over 60-odd fields would leave
    it implicit in the layout's line ordering, where a tidy-up would silently break the output.
    """
    return {f.name: read_field(mm, f, base)
            for f in rec.fields if f.emits and f.group == group}


def walk(mm, rec, lo, hi, keep=None, stride=None, limit=None):
    """Yield `(offset, values)` for each record in `[lo, hi)`.

    **Takes its bounds; never finds them.** `lo`/`hi` come from the table's own locator, and
    `keep(offset, values) -> bool` is the table's own invariant -- `id == slot index` for the
    city table, a marker byte, a valid tid. Both stay with the caller on purpose: a walk
    bounded by a constant inside a shared helper is how a row count becomes a function of a
    tuned number instead of the table's structure.
    """
    step = stride or rec.stride
    if not step:
        raise ValueError(f"{rec.name} has no stride; walk needs one")
    n = 0
    for base in range(lo, max(lo, hi - rec.span + 1), step):
        vals = read(mm, rec, base)
        if keep is not None and not keep(base, vals):
            continue
        yield base, vals
        n += 1
        if limit is not None and n >= limit:
            return


def columns(mm, rec, lo, count, names=None, stride=None):
    """Read a fixed-width grid COLUMN-WISE, as `{name: [value, ...]}`.

    For slabs where per-row dict building dominates: `history.py` scans 265k rows and does
    this with numpy today. numpy is used when it is importable and the fallback is a plain
    loop, because the extractors are otherwise stdlib-only.

    Values are converted to builtin ints at the edge. This is not tidiness: `np.uint32` is not
    JSON-serialisable and its `repr` differs from `int`'s, so leaking one changes
    `extract.py`'s output bytes -- the same trap `primitives.f32` documents.
    """
    step = stride or rec.stride
    if not step:
        raise ValueError(f"{rec.name} has no stride; columns needs one")
    fields = [f for f in rec.fields
              if f.emits and (names is None or f.name in names)]
    order = names if names is not None else [f.name for f in fields]
    by_name = {f.name: f for f in fields}

    try:
        import numpy as np
    except ImportError:
        np = None

    if np is None or any(by_name[n].kind not in (U8, U16, U32) for n in order):
        # Mixed or exotic kinds, or no numpy: read rows and transpose. Same values, same order.
        out = {n: [] for n in order}
        for i in range(count):
            base = lo + i * step
            for n in order:
                out[n].append(read_field(mm, by_name[n], base))
        return out

    buf = np.frombuffer(mm, dtype=np.uint8, count=count * step, offset=lo).reshape(count, step)
    out = {}
    for n in order:
        f = by_name[n]
        col = buf[:, f.offset].astype(np.uint32)
        for k in range(1, f.width):
            col = col | (buf[:, f.offset + k].astype(np.uint32) << (8 * k))
        out[n] = [int(v) for v in col]
    del buf          # release the view before the caller closes the mmap: an exported
    return out       # pointer makes mmap.close() raise BufferError


def find_framed_count(mm, start, hi, width=4, min_ff=8):
    """The count a count-framed table declares about itself: `[>= 8 x 0xFF][count]`.

    Shape A in `docs/parser-architecture.md`, and the only structure in the save that both
    declares its extent and asserts `id == slot index`. Returns `(count, first_record_offset)`
    or `(None, None)`.

    `>= 8` and never `== 8`: the record preceding the sentinel can itself end in 0xFF, so an
    exact-length test misses the frame. That is measured, not defensive.

    The sentinel alone occurs 566,078 times in one save, so this is a CANDIDATE generator and
    nothing more -- a caller that does not then validate `id == slot index` on the declared
    records is not using it correctly.
    """
    i = mm.find(b"\xff" * min_ff, start, hi)
    if i == -1:
        return None, None
    j = i
    while j < hi and mm[j] == 0xFF:
        j += 1
    if j + width > hi:
        return None, None
    count = struct.unpack_from("<I" if width == 4 else "<H", mm, j)[0]
    return count, j + width
