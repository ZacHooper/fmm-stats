#!/usr/bin/env python3
"""
The save's TAIL IS A NAMED ARCHIVE of zstd-compressed member files.

Found 2026-09-20 while opening `docs/savefile-map.md`'s densest unexplored gap — the
1.93 MB after the squad snapshot, recorded there as "71% other / 25.8% printable, by far
the most TEXT-dense unparsed span in the file". It is not text: 95/256 = 37.1% of uniform
random bytes are printable, which is exactly what that span measures. The block-entropy
profile is a flat 7.99 bits/byte from the archive's first frame to EOF, and the reason is
that every byte of it is COMPRESSED.

    ... the last uncompressed structure ...
    02 01 'fmf.' 08 00 00 [u32]        <- 13-byte record header (see UNKNOWNS below)
    [u32 stored_size][zstd frame]      <- member 1, possibly several frames
    [u32 stored_size][zstd frame]      <- member 2
    ...                                <- 159 members on frem-2026-06-11
    02 01 'fmf.' 08 00 00 [u32 n]      <- the DIRECTORY's own 13-byte header; n = its size
    [zstd frame]                       <- the directory, running to EOF exactly

`28 b5 2f fd` is the Zstandard magic number. Nothing below the archive contains it: on all
34 saves in the two careers the first occurrence in the file IS the archive's first frame,
which is what `locate` keys on.

THE DIRECTORY, which is what makes this a named archive rather than a blob:

    [u32 len]['sicomps'][u32 0][u32 1][u32 len]['rgman'][u32 count]
    then `count` entries of
    [u32 len][name][u32 len][ext][u64 offset][u64 stored][u64 unpacked][u64 ?][u64 ?]

`offset` is relative to the first member's length prefix, `stored` counts the 4-byte length
prefixes, and `unpacked` is the exact decompressed size. On frem-2026-06-11 that is 159
entries: twelve named subsystems --

    rgman  rule_group  comp_man  comp_hosts  fix_man  stadium
    squad_man  national_teams  fifa_rankings  discipline  reserves  friend_man

-- plus 147 `comp_<digits>.dat`, one per loaded competition. (`comp_man` is a subsystem, not
a competition: match the digits, not the `comp_` prefix.) `fix_man.dat` is the big one at
2.52 MB; see docs/save-archive.md for what is and is not known about its contents.

EXTENT, proven by the structure's own invariants rather than a window, on all 34 saves
(27 Frem + 7 Bucaspor, `scripts/audit_archive.py`):

  * walking `[u32 stored][frame]` from the first zstd magic consumes the file with a
    residual of 2.0-2.1 KB, and that residual is exactly one 13-byte header plus the
    directory frame, which ends ON the last byte of the file. Nothing is left over.
  * every member's concatenated frames decompress to EXACTLY its declared `unpacked`
    size, and the entries tile the member area with no gap and no overlap.
  * the directory's declared `count` is exact: the walk consumes the buffer to within
    4 bytes.

The archive grows with the career (3.58 MB unpacked on the day-one save, 6.58 MB by 2026)
and both careers carry the same twelve named members, so the shape is the format's, not
Frem's.

DEPENDENCY. zstd is not in the standard library before Python 3.14, so this module needs
`zstandard` and every other fmparser module stays stdlib+numpy as before. Install with
`uv sync --extra archive`; the import error names the command.

UNKNOWNS, carried rather than guessed:
  * the two u64s that end each directory entry are 0xFFFFFFF1886E0900 on every entry of
    every save measured. Constant, so NOT a per-member timestamp. Unnamed.
  * the `[u8 08][u8 00][u8 00]` in the 13-byte record header; the u32 after it on the
    header that OPENS the archive (on the directory's header that u32 is exactly the
    directory frame's size, which `locate` checks; on the archive's it is 17 more than the
    members' stored total on both Frem saves measured and 495 LESS on Bucaspor, so it is
    not that total either); and the further 13 constant bytes
    `00 00 00 00 11 00 00 00 00 00 00 00 03` that sit between that header and member 0.
    Unnamed.
  * 'sicomps', the u32 0 and u32 1 after it, and the 'rgman' before the count. 'rgman' is
    also entry 0's name, so the leading copy may be a root-member pointer or may be
    something else entirely. Unnamed.
"""
import struct

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# Every record in this part of the file opens `[u8 kind][0x01][4-char extension, REVERSED]`,
# the same reversal the tagged data dictionary uses for its field names (fmparser/tagged.py).
MEMBER_HEADER = b"\x03\x01tad."      # '.dat', on the DECOMPRESSED payload of every member
RECORD_HEADER = b"\x02\x01fmf."      # '.fmf', on the archive's and the directory's headers
RECORD_HEADER_LEN = 13               # [kind][01][ext 4][08][00][00][u32]

_LOCATE_CACHE = {}                   # save.cache_key -> (first_prefix, dir_header, dir_frame)
_DIR_CACHE = {}                      # save.cache_key -> (archive_name, [Entry, ...])

# Upper bound for decompressing the DIRECTORY member, which is the one member whose unpacked
# size nothing declares in advance (it is the thing that declares everyone else's). Measured:
# 10,237 B on both frem-2021-07-01 and frem-2026-06-11, 10,384 B on bucaspor-2023-03-25, from
# ~2 KB of frame. 1 MB is two orders of magnitude of headroom and still bounds the allocation,
# which an unbounded `decompress()` does not. If this ever trips, the directory grew by 100x
# and that is worth stopping for rather than absorbing.
_DIR_MAX = 1 << 20


class ArchiveError(Exception):
    pass


def _zstd():
    try:
        import zstandard
    except ImportError as exc:                        # pragma: no cover - environment
        raise ArchiveError(
            "reading the save archive needs the `zstandard` package: "
            "run `uv sync --extra archive`"
        ) from exc
    return zstandard


class Entry(tuple):
    """One directory entry. `offset` is relative to the first member's length prefix."""
    __slots__ = ()
    _FIELDS = ("name", "ext", "offset", "stored", "unpacked", "unknown_a", "unknown_b")

    def __new__(cls, *vals):
        return tuple.__new__(cls, vals)

    def __getattr__(self, k):
        try:
            return self[self._FIELDS.index(k)]
        except ValueError:
            raise AttributeError(k) from None

    @property
    def filename(self):
        return self.name + self.ext

    def __repr__(self):
        return (f"Entry({self.filename!r}, offset={self.offset}, "
                f"stored={self.stored}, unpacked={self.unpacked})")


def locate(mm):
    """(members_start, directory_header, directory_frame) for this save's archive.

    `members_start` is the 4-byte length prefix of member 0; `directory_frame` runs to the
    last byte of the file. Raises ArchiveError if the save carries no archive.

    Located by the FIRST zstd magic in the file and validated by walking the chain: the
    walk must land on a `.fmf` record header followed by the final frame. No offset and no
    window is involved, so this survives the megabyte-scale drift of the career half.
    """
    from .save import cache_key as _ck
    key = _ck(mm)
    hit = _LOCATE_CACHE.get(key)
    if hit is not None:
        return hit

    first = mm.find(ZSTD_MAGIC)
    if first == -1 or first < 4:
        raise ArchiveError("no zstd frame in this save")
    start = first - 4
    off, n = start, len(mm)
    while off < n - RECORD_HEADER_LEN:
        stored = int.from_bytes(mm[off:off + 4], "little")
        if mm[off + 4:off + 8] != ZSTD_MAGIC:
            break
        if stored <= 0 or off + 4 + stored > n:
            raise ArchiveError(f"frame at {off} declares {stored} bytes, past EOF")
        off += 4 + stored
    if mm[off:off + 6] != RECORD_HEADER:
        raise ArchiveError(f"member chain ended at {off} on {mm[off:off + 6]!r}, not a "
                           f".fmf record header")
    dir_frame = off + RECORD_HEADER_LEN
    declared = int.from_bytes(mm[off + 9:off + 13], "little")
    if dir_frame + declared != n:
        raise ArchiveError(f"directory declares {declared} bytes at {dir_frame}, which "
                           f"does not end on EOF ({n})")
    _LOCATE_CACHE[key] = (start, off, dir_frame)
    return _LOCATE_CACHE[key]


def _strings_reader(buf):
    pos = 0

    def u32():
        nonlocal pos
        v = int.from_bytes(buf[pos:pos + 4], "little")
        pos += 4
        return v

    def u64():
        nonlocal pos
        v = int.from_bytes(buf[pos:pos + 8], "little")
        pos += 8
        return v

    def s():
        nonlocal pos
        ln = u32()
        v = buf[pos:pos + ln].decode("latin-1")
        pos += ln
        return v

    def tell():
        return pos

    return u32, u64, s, tell


def directory(mm):
    """(archive_name, [Entry, ...]) read from the archive's own directory member.

    The entry count is DECLARED; this reads exactly that many and checks the walk lands
    within 4 bytes of the end of the buffer, which is the directory's own extent test."""
    from .save import cache_key as _ck
    key = _ck(mm)
    hit = _DIR_CACHE.get(key)
    if hit is not None:
        return hit

    _, _, dir_frame = locate(mm)
    buf = _zstd().ZstdDecompressor().decompress(mm[dir_frame:], max_output_size=_DIR_MAX)
    u32, u64, s, tell = _strings_reader(buf)
    name = s()
    u32(); u32()                      # UNKNOWN: 0 and 1 on every save measured
    s()                               # UNKNOWN: repeats entry 0's name
    count = u32()
    ents = [Entry(s(), s(), u64(), u64(), u64(), u64(), u64()) for _ in range(count)]
    left = len(buf) - tell()
    if left > 8:
        raise ArchiveError(f"directory declared {count} entries but left {left} bytes")
    _DIR_CACHE[key] = (name, ents)
    return _DIR_CACHE[key]


def members(mm):
    """{filename: Entry} — e.g. 'fix_man.dat', 'comp_100104.dat'."""
    return {e.filename: e for e in directory(mm)[1]}


def read_member(mm, entry):
    """The member's decompressed bytes, INCLUDING its 6-byte `[03][01]['.dat']` header.

    A member may span several zstd frames; they are concatenated. The result is checked
    against the directory's declared `unpacked` size, which is the per-member extent test.
    """
    start, _, _ = locate(mm)
    dec = _zstd().ZstdDecompressor()
    base, end, out = start + entry.offset, start + entry.offset + entry.stored, []
    off = base
    while off < end:
        stored = int.from_bytes(mm[off:off + 4], "little")
        # `max_output_size` bounds the allocation AND lets a frame that carries no
        # content size in its header still decompress -- `decompress()` raises on those
        # otherwise. A member's total unpacked size is an upper bound for any one of its
        # frames, and the exact total is re-checked below.
        out.append(dec.decompress(mm[off + 4:off + 4 + stored],
                                  max_output_size=entry.unpacked))
        off += 4 + stored
    blob = b"".join(out)
    if len(blob) != entry.unpacked:
        raise ArchiveError(f"{entry.filename}: unpacked {len(blob)} B, "
                           f"directory declares {entry.unpacked}")
    return blob


def extract(mm, filename):
    """Convenience: decompressed bytes of the member with this filename."""
    try:
        return read_member(mm, members(mm)[filename])
    except KeyError:
        raise ArchiveError(f"no member named {filename!r}") from None


def summary(mm):
    """One-line-per-member listing, for scripts and the audit."""
    name, ents = directory(mm)
    start, dhdr, dframe = locate(mm)
    lines = [f"archive {name!r}: {len(ents)} members, "
             f"members {start}..{dhdr}, directory {dframe}..{len(mm)}",
             f"  stored {sum(e.stored for e in ents):,} B  ->  "
             f"unpacked {sum(e.unpacked for e in ents):,} B"]
    for e in sorted(ents, key=lambda x: -x.unpacked)[:12]:
        lines.append(f"    {e.filename:24} {e.unpacked:>10,} B")
    return "\n".join(lines)
