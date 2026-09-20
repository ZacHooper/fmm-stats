#!/usr/bin/env python3
"""What a record IS, as data.

A locator shape tells you how to FIND a record; a layout tells you how to READ it. This module
is the second half. It holds no offsets of its own -- it is the vocabulary the record modules
declare in, and the thing `scripts/audit_records.py` and `tests/test_layouts.py` check.

The rule it enforces is already the project's rule (CLAUDE.md: *"One declarative layout per
record is the schema"*); what was missing is one dialect. There were three:

    staging.INFO_LAYOUT          (offset, width, name, kind)   executable, read by the parser
    matchslots.LAYOUT            (offset, width, name, kind)   executable, read by the parser
    scripts/audit_records.LAYOUTS (offset, width, name)        audit only, kind dropped

and dropping `kind` is not cosmetic: it is why the audit could not catch a field whose
DECLARED WIDTH disagrees with its KIND. `staging._read` structurally cannot catch it either --
it ignores `width` entirely for `DATE` and `HEX4` -- so `(20, 2, "dob", DATE)` would declare
two bytes, read four, and pass every check in the repo. `validate()` catches it here.

WHAT IS DELIBERATELY NOT DECLARABLE
-----------------------------------
Meaning. Sentinel collapsing (`uid == 0` blanks the person block), banding (a hidden byte ->
Attacking/Normal/Defensive), composites (an attribute modelled from CA), and the four money
conventions are all record-specific judgements with evidence behind them. They live in the
record's own module, after the read. A schema that could express them would be a programming
language, and the argument for each would stop being visible.

Counted and nested structures. The competition record is
`[names][trailer 14][count 4][entry 8 x n][tail 21]`; the person record has counted language
and relationship lists past its 68-byte head. Only the FIXED-WIDTH parts are declared, and
`Record.span` is the extent of the declared part, not of the record. `is_head=True` says so.
"""


class _Unknown:
    """A byte we have decided we cannot name yet -- which is a different thing from a byte we
    are stepping over by accident. Declaring it UNKNOWN makes it covered AND visible.

    A singleton object rather than the string `"UNKNOWN"`, which is what it was in four
    separate declarations. As a string it was compared by identity (`name is not UNKNOWN`) in
    `staging._decode_info` and by equality (`owner[b] == UNKNOWN`) in `audit_records._coverage`,
    and those two agree only because CPython interns short literals -- a fact about the
    interpreter, not about the code. As an object both spellings are correct and a name that
    merely happens to read "UNKNOWN" cannot impersonate it.
    """
    __slots__ = ()

    def __repr__(self):
        return "UNKNOWN"

    def __bool__(self):
        return False


UNKNOWN = _Unknown()


# Field kinds, with the width each one actually reads. `validate()` checks a declared width
# against this table, which is the check no existing layout could make.
U8, U16, U32, I16, I32, F32 = "u8", "u16", "u32", "i16", "i32", "f32"
DATE, HEX4, HEX2 = "date", "hex4", "hex2"
RAW = "raw"      # a byte range carried verbatim (positions, a blob) -- any width
PAD = "pad"      # structural filler / declared-unknown span -- any width, never emitted

KIND_WIDTH = {U8: 1, U16: 2, U32: 4, I16: 2, I32: 4, F32: 4,
              DATE: 4, HEX4: 4, HEX2: 2}
VARIABLE_KINDS = frozenset({RAW, PAD})


class Field:
    """One declared span of a record.

    offset  bytes from the RECORD START -- never from whatever internal landmark the parser
            happens to anchor on. That distinction is a real bug this project has already had;
            `Record.anchor` is how an anchored record reconciles the two, in one place.
    width   how many bytes the field occupies. Checked against `kind`.
    name    the key this field emits, or `UNKNOWN`.
    kind    how to read it. `None` is accepted only for UNKNOWN/PAD spans.
    group   an optional tag for `records.read_group`, which is how a record emits an ORDERED
            SUBSET -- the attribute record emits four groups in a fixed order and its JSON key
            order is part of the acceptance test.
    alias   this field re-reads bytes another field already covers, under a second name.
            `attributes.PLAIN_OFFSETS` and `ATTR_OFFSETS` name the identical nine bytes, and
            the audit silently OMITS `PLAIN_OFFSETS` today because including it would trip the
            overlap check -- a table the parser reads that its audit cannot see. An alias is
            exempt from coverage and overlap, and must overlap a non-alias field.
    note    why, for the generated per-byte documentation.
    """
    __slots__ = ("offset", "width", "name", "kind", "group", "alias", "note")

    def __init__(self, offset, width, name, kind=None, group=None, alias=False, note=""):
        self.offset, self.width, self.name, self.kind = offset, width, name, kind
        self.group, self.alias, self.note = group, alias, note

    @property
    def emits(self):
        """True if this field contributes a key to the decoded dict."""
        return self.name is not UNKNOWN and self.kind is not PAD

    def __repr__(self):
        return f"Field({self.offset}, {self.width}, {self.name!r}, {self.kind!r})"


class Record:
    """A fixed-width record's declared layout.

    span    the extent this declaration covers, from the record start.
    stride  the distance to the NEXT record, when the record lives in a grid. Usually equal to
            `span`; different when the record is a head inside something longer. `None` for a
            record that is located individually rather than walked.
    anchor  the offset, within the record, of the landmark the LOCATOR finds. The player
            attribute record is found by its SID and the project has always described its
            fields relative to `P`, the marker -- `P-38`, `P+28` -- while the record starts at
            `P-42`. Declaring `anchor=42` lets both spellings coexist: declarations stay in
            record coordinates, and `records.read_at_anchor(mm, rec, p)` does the subtraction
            once instead of at every call site.
    is_head True when the record continues past `span` with counted or variable-length parts.
            Suppresses the "span must equal stride" expectation.
    """
    __slots__ = ("name", "span", "fields", "stride", "anchor", "is_head", "note")

    def __init__(self, name, span, fields, stride=None, anchor=0, is_head=False, note="",
                 register=True):
        self.name, self.span = name, span
        self.fields = tuple(fields)
        self.stride = stride if stride is not None else (None if is_head else span)
        self.anchor, self.is_head, self.note = anchor, is_head, note
        if register:
            REGISTRY[name] = self

    def field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.name} has no field {name!r}")

    def groups(self):
        """Group tags in first-declared order -- the order `read_group` will emit them in."""
        seen = []
        for f in self.fields:
            if f.group is not None and f.group not in seen:
                seen.append(f.group)
        return seen

    def __repr__(self):
        return f"Record({self.name!r}, span={self.span}, {len(self.fields)} fields)"


# Every Record declared anywhere registers itself here on construction, so
# `tests/test_layouts.py` validates the whole set by iterating it. Auto-registration rather
# than an explicit list: a record that someone forgets to add to a list is exactly the record
# that has not been checked.
REGISTRY = {}


def validate(rec):
    """Return a list of problems with a declared layout. Empty means it is sound.

    Five checks. The first two are what `audit_records._coverage` already did; the last three
    are new, and each one corresponds to a mistake that is currently possible.
    """
    problems = []
    solid = [f for f in rec.fields if not f.alias]

    # 1. width agrees with kind. NEW -- and the one no existing layout could catch, because
    #    `staging._read` ignores `width` for DATE and HEX4 and reads 4 regardless.
    for f in rec.fields:
        if f.kind in KIND_WIDTH and f.width != KIND_WIDTH[f.kind]:
            problems.append(
                f"{f.name}: declared width {f.width} but kind {f.kind} reads "
                f"{KIND_WIDTH[f.kind]}")
        if f.kind is None and f.emits:
            problems.append(f"{f.name}: emits a value but declares no kind")
        if f.width <= 0:
            problems.append(f"{f.name}: width {f.width}")

    # 2. coverage + overlap: every byte in [0, span) owned exactly once.
    owner = [None] * rec.span
    for f in solid:
        if f.offset < 0 or f.offset + f.width > rec.span:
            problems.append(
                f"{f.name}: [{f.offset},{f.offset + f.width}) outside [0,{rec.span})")
            continue
        for b in range(f.offset, f.offset + f.width):
            if owner[b] is not None:
                problems.append(f"byte {b}: {owner[b]} overlaps {f.name}")
            owner[b] = f.name
    gaps = [b for b in range(rec.span) if owner[b] is None]
    if gaps:
        problems.append(
            f"{len(gaps)} unaccounted byte(s) {_runs(gaps)} -- name them, or declare them "
            f"PAD. A byte that is neither is a byte we are stepping over by accident.")

    # 3. an alias must actually alias something. NEW -- otherwise `alias=True` becomes a way
    #    to smuggle a field past the coverage check.
    for f in rec.fields:
        if not f.alias:
            continue
        covered = all(0 <= b < rec.span and owner[b] is not None
                      for b in range(f.offset, f.offset + f.width))
        if not covered:
            problems.append(
                f"{f.name}: alias=True but [{f.offset},{f.offset + f.width}) is not covered "
                f"by a declared field -- an alias re-reads bytes, it does not add them")

    # 4. no two fields emit the same key. NEW -- a duplicate silently wins by declaration
    #    order and the loser vanishes from the output.
    emitted = [f.name for f in rec.fields if f.emits]
    dupes = sorted({n for n in emitted if emitted.count(n) > 1})
    if dupes:
        problems.append(f"duplicate emitted name(s): {', '.join(map(str, dupes))}")

    # 5. a walked record's stride must be at least its span. NEW -- a stride shorter than the
    #    declaration means consecutive records overlap, which is a decode that cannot be right.
    if rec.stride is not None and rec.stride < rec.span:
        problems.append(f"stride {rec.stride} < span {rec.span}: records would overlap")
    if rec.anchor < 0 or rec.anchor >= max(rec.span, 1):
        problems.append(f"anchor {rec.anchor} outside [0,{rec.span})")

    return problems


def _runs(nums):
    """[1,2,3,7,8] -> '1-3,7-8' -- a byte list is unreadable past about six entries."""
    out, start, prev = [], None, None
    for n in list(nums) + [None]:
        if start is None:
            start = prev = n
            continue
        if n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    return ",".join(out)


def per_byte_map(rec):
    """The record's documentation, generated rather than retyped: one line per declared span.

    `scripts/audit_records.py --map` exists because a hand-written byte map goes stale and a
    generated one cannot. This is that, for a `Record`.
    """
    lines = [f"{rec.name}: span {rec.span}"
             + (f", stride {rec.stride}" if rec.stride != rec.span else "")
             + (f", anchor +{rec.anchor}" if rec.anchor else "")
             + ("  [HEAD of a variable-length record]" if rec.is_head else "")]
    for f in sorted(rec.fields, key=lambda f: (f.offset, f.alias)):
        hi = f.offset + f.width
        span = f"{f.offset:>4}" if f.width == 1 else f"{f.offset:>4}..{hi - 1}"
        flag = " (alias)" if f.alias else ""
        lines.append(f"  {span:<11} {str(f.kind or '-'):<5} {str(f.name):<28}{flag}"
                     + (f"  # {f.note}" if f.note else ""))
    return "\n".join(lines)
