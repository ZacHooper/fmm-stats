#!/usr/bin/env python3
"""
Record-coverage audit: prove we read the WHOLE record, and the WHOLE table.

Every parser bug this repo has hit in the last few rounds is one of three shapes, and none
of them is caught by "the values look right" -- a truncated record decodes its first fields
perfectly:

  1. TRUNCATED RECORD -- we know where a record starts and guess where it ends. The player
     attribute record ran to P+35 and we stopped at P+22, losing height, weight, shirt
     number and two reputations for four years.
  2. MIS-STRIDDEN WALK  -- a `+= stride` sweep across a multi-segment table desynchronises at
     the first segment break and silently drops most of the rows (2 of 7 managers found).
  3. TRUNCATED TABLE    -- the walk is bounded by a tuned constant (a miss counter, a
     plausibility test) rather than by the table's own structure, so the row count is a
     function of the constant. The city walk emitted 3 rows that were not cities and dropped
     31 that were.

This script asserts against all three, from the bytes, on a real save:

  STRIDE     the gap between consecutive record offsets has a single dominant value, and that
             value is the stride we claim. This is the measurement that settled the staff
             record at 39 bytes; it is the cheapest proof that a record ends where we say.
  COVERAGE   every byte in [0, stride) is either decoded into a named field or declared
             UNKNOWN in the layout. A byte that is neither is a byte we are stepping over
             without having decided to -- which is how the record tail went missing.
  EXTENT     a keyed table is contiguous in its own id space. Gaps and overshoot both mean
             the walk's boundary is wrong.

Run:  uv run python scripts/audit_records.py [path/to/save.fms]
      uv run python scripts/audit_records.py --map     # print the per-byte schema

Exits non-zero on a failure, so it can gate a merge. Declaring a byte UNKNOWN is a normal,
honest outcome -- the point is that it is written down rather than skipped by accident.
"""
import mmap
import os
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import attributes as A          # noqa: E402
from fmparser import staff as ST              # noqa: E402
from fmparser import places as PL             # noqa: E402
from fmparser import staging as S             # noqa: E402


# ---------------------------------------------------------------------------
# Layouts. Offsets are relative to the RECORD START, not to whatever internal
# landmark the parser happens to anchor on -- that difference is the bug in (1).
# Every entry is (offset, width, name). `UNKNOWN` names a byte we have decided we
# cannot yet name; it counts as covered, but it is visible in the report.
# ---------------------------------------------------------------------------
UNKNOWN = "UNKNOWN"


def _player_attr_layout():
    """The global player attribute record, anchored on the SID at P-42.

    Built from the parser's own tables rather than retyped, so the audit cannot drift from
    the code it is auditing: ATTR_OFFSETS and record_tail are the source of truth.
    """
    f = [(0, 4, "sid")]
    for rel, name in A.ATTR_OFFSETS.items():        # P-29 .. P-5, the named attributes
        f.append((42 + rel, 1, name))
    for rel, name in A.HIDDEN_OFFSETS.items():      # the 9 unnamed 1-20 attribute bytes
        f.append((42 + rel, 1, name))
    f += [(42, 15, "positions"), (57, 1, "foot_left"), (58, 1, "foot_right"),
          (59, 2, "ca"), (61, 2, "pa"), (63, 2, "home_reputation"),
          (65, 2, "current_reputation"), (67, 2, "world_reputation"),
          (69, 1, "international_retired"),
          (70, 2, UNKNOWN),                          # P+28..29, "always 0" in FMM26
          (72, 1, "squad_number"), (73, 1, "preferred_squad_number"),
          (74, 2, "height_cm"), (76, 2, "weight_kg")]
    # The ENTANGLED source bytes: 0-255, decoded to a displayed 1-20 value by the frozen model
    # rather than read straight. Not unknown -- `attributes.SRC_OFFSETS` names each one and the
    # store now carries them raw -- so `_src` marks that the byte is the SOURCE of the
    # attribute and not the attribute.
    #
    # Worth noting while here: the frozen model needs a PARTNER byte for exactly two
    # attributes, Aerial (P-29 + P-28) and Shooting (P-31 + P-30). Those are precisely the two
    # that fmm-editor's order says are composites -- Heading + Jumping, Finishing + LongShots.
    # A least-squares fit found that years before anyone read Player.cs.
    for rel, name in A.SRC_OFFSETS.items():
        f.append((42 + rel, 1, name))
    # rel 4..7 is the P-38 history link (docs/agent-context/history-chain-pointers.md).
    f += [(4, 4, "history_link_P38")]
    named = set()
    for off, width, _ in f:
        named.update(range(off, off + width))
    f += [(o, 1, UNKNOWN) for o in range(0, 42) if o not in named]
    return f


def _staff_layout():
    f = [(0, 4, "id2"), (4, 2, "ca"), (6, 2, "pa"), (8, 2, "home_reputation"),
         (10, 2, "current_reputation"), (12, 2, "world_reputation")]
    f += [(o, 1, n) for o, n in ST._ATTRS.items()]
    f += [(o, 1, n) for o, n in ST.HIDDEN_OFFSETS.items()]
    f += [(o, 1, n) for o, n in ST.FORMATION_SLOTS.items()]
    # +14..+30 is seventeen attribute bytes and every one is now carried, so nothing in the
    # block should be left over. If this ever adds an entry again, a byte went unparsed.
    named = {o for o, _, _ in f}
    f += [(o, 1, UNKNOWN) for o in range(14, 31) if o not in named]
    f += [(o, 1, UNKNOWN) for o in range(34, 39)]    # five catalog indices, undecoded
    return f


def _info_head_layout():
    """The INFO (person) record's fixed head -- taken straight from staging.INFO_LAYOUT.

    Not retyped: that table is what `_decode_info` reads from, so the audit is checking the
    parser's own declaration rather than a copy that can rot. The record as a whole is
    variable-length (counted language and relationship lists follow), so there is no stride to
    measure and only the head is covered.
    """
    f = [(off, width, name) for off, width, name, _ in S.INFO_LAYOUT]
    named = set()
    for off, width, _ in f:
        named.update(range(off, off + width))
    f += [(o, 1, UNKNOWN) for o in range(0, S.INFO_HEAD) if o not in named]
    return f


def _comp_trailer_layout():
    """The competition record's fixed 14-byte trailer, starting right after its 3
    length-prefixed names (long/short/code) -- offsets straight from
    `reference._read_comp_slot`, not retyped.

    Like `info_head`, this is NOT a stride: the names in front are variable-length. It is
    also not the whole record -- `comp_history_head` below covers what follows it.

    `nation` is declared here as a u16 and that is the correct width: byte +4 is 0x00 for
    all 1,212 nation-bound competitions on frem-2026-06-11 and 0xFF for exactly the 60 that
    carry the 0xFFFF sentinel. `_read_comp_slot` read it as a single byte against 255 until
    2026-09-18 -- right answer, wrong width, and only because all 227 nation ids in the save
    fit in a byte (1-249). The parser now reads the declared width. This is what COVERAGE is
    for: the layout and the parser disagreeing is a defect even when the output matches.
    """
    return [(0, 1, "type"), (1, 2, "continent"), (3, 2, "nation"),
            (5, 2, "fg_colour"), (7, 2, "bg_colour"),
            (9, 2, "reputation"), (11, 1, "level"), (12, 2, "parent_cid")]


def _comp_ref_count_layout():
    """The count of 8-byte reference entries that follows the competition trailer.

    **A u8 plus three UNKNOWN bytes, because the width is undecidable from this data.**
    Bytes +1..+3 are zero on all 46,641 slots across every archived save and the largest
    count anywhere is 134, so a `u8` followed by three zero bytes and a little-endian `u32`
    cannot be told apart. `reference._read_comp_slot` reads a u32, which is safe either way;
    the LAYOUT must not assert what was not measured. A save with 256+ entries in one
    competition would settle it.
    """
    return [(0, 1, "n_refs"), (1, 3, UNKNOWN)]


def _comp_ref_entry_layout():
    """One 8-byte entry in the competition's reference list. Fields decoded; what the LIST
    MEANS is deliberately NOT named -- see below, it is not one thing.

    `ref` resolves as a club **UID** for club competitions, and that identification is solid:
    Major League Soccer's entries come back as its 28 member clubs (D.C. United, LA Galaxy,
    Atlanta United, Charlotte FC, Chicago Fire, CF Montréal), and Copa Libertadores' as
    Bolivian and Ecuadorian clubs (Club The Strongest, Club Bolívar, Royal Pari) in the right
    competition. `0xFFFFFFFF` is the empty-slot sentinel. **Resolve by UID, never by tid:**
    1,095 of these values also match some club's tid and that reading is wrong every time --
    uid 1913 is D.C. United (right for MLS), tid 1913 is York United.

    NATIONAL-TEAM competitions carry a reference in a different, unresolved id space: 1,143
    entries read as a small negative int32, 132 distinct values in -1658..-5, and they cluster
    densely (-1658..-1649 is ten consecutive values, and Copa América -- which is where they
    appear -- has exactly ten CONMEBOL member nations). Nations are not in the club table, so
    this is very likely a national-team id space. Unresolved, and not guessed at.

    `ordinal` is declared as a u8 for the same reason as the count: the byte above it is 0 on
    5,220 of 5,237 entries and 1 on the other 17, so u8-plus-a-rare-flag and u16 are not
    separable here. Values are small (1, 2, 3 ...) and read as a placing where the list is a
    qualification list.

    WHY THE LIST ITSELF IS UNNAMED. It was briefly called the `Qualifiers` table (fmm-editor
    has one, `n × 8 bytes`, which this may well be) and Zac was right to push back: only 24 of
    1,272 competitions populate it at all, and the populated ones do not share one meaning.
      * Copa Libertadores: 47 entries per season for two seasons, each with a domestic
        qualifying position. A qualifier list, exactly.
      * Major League Soccer: its 28 member clubs, with Charlotte FC stamped season 2022 --
        its real expansion year. A membership list, not a qualification.
      * Canadian Championship: 3 entries -- Forge FC, Toronto FC, CF Montréal, i.e. the
        Canadian clubs that play in FOREIGN leagues but enter the Canadian cup. Reads as
        "entrants the league structure cannot imply".
      * Copa América: 10 national-team refs, no clubs.
      * Scottish Cup: 13 entries, ALL `0xFFFFFFFF`. Reserved and empty.
      * Italian Cup: 4 entries (3 Serie C clubs + a sentinel) against a ~78-team real field.
    And the asymmetry that makes a single label untenable: European Champions Cup has ZERO
    while Copa Libertadores / Asian / African Champions Leagues have 94 / 47 / 54, and 3F
    Superliga has zero while MLS has 28. A plausible story is "an explicit entrant list,
    stored only where the field cannot be derived from the league structure the game
    simulates" -- promotion/relegation pyramids and UEFA coefficients being derivable, a
    closed franchise league and CONMEBOL's entrants not. That is a story, not a decode, so
    the layout names the FIELDS and leaves the list structural.
    """
    return [(0, 4, "ref"), (4, 2, "season"), (6, 1, "ordinal"), (7, 1, UNKNOWN)]


def _comp_history_tail_layout():
    """The 21 fixed bytes that END a competition record, AFTER the reference list.

    THE ORDER HERE WAS ESTABLISHED BY MEASUREMENT, NOT ASSUMED, and two earlier readings of
    it were wrong. The fixed part is NOT a contiguous 25-byte head with the qualifiers after
    it (which is how it was first declared, and which looks right because 1,348 of 1,372
    records have zero entries, so the two readings coincide); nor is it
    `[count][3 stat u32][entries][3 season u16][tail]`, which is what docs/TODO.md
    claimed. All the candidate orderings give the same record length, so arithmetic cannot
    separate them -- only content can. On the 914 records that DO carry entries, the
    three-u16 season triple reads as a plausible year (1990-2060) at `record_end - 9` on 686
    of them and at `count + 16` on ZERO. So: count, then the qualifiers, then this.

    The three u32s and the three u16s are parallel arrays, three seasons wide, which is
    exactly the shape of fmm-editor's FMM26 `Competition` Rank[3]/Year[3] history -- and
    unlike the reference entries, these u32s do NOT resolve as clubs by either uid or tid
    (3F Superliga's read 505/526/507), so they are carried UNNAMED. Both arrays go
    0xFF-sentinel on records that carry a full reference list instead, which is itself a
    hint about what the two represent.
    """
    return [(0, 4, UNKNOWN), (4, 4, UNKNOWN), (8, 4, UNKNOWN),
            (12, 2, "season_0"), (14, 2, "season_1"), (16, 2, "season_2"),
            (18, 2, UNKNOWN), (20, 1, UNKNOWN)]


LAYOUTS = {
    "player_attribute": (78, _player_attr_layout()),
    # NOT a stride -- the info record is variable-length; this is the fixed head we decode.
    "info_head": (S.INFO_HEAD, _info_head_layout()),
    "staff_attribute": (39, _staff_layout()),
    "city": (PL.CITY_RECORD, [
        (0, 2, "id"), (2, 4, "uid"), (6, 2, "nation_id"),
        (8, 4, "latitude"), (12, 4, "longitude"),
        (16, 1, "attraction"), (17, 2, "region_id"), (19, 1, UNKNOWN)]),
    # NOT strides -- variable-length names precede the trailer and a variable-length entries
    # array sits inside the part after it. Together these four cover the competition record
    # in full, in file order:
    #   [cid u16][uid u32]
    #   [len u32][long name][1 terminator][len u32][short name][1 terminator][len u32][code]
    #   comp_trailer            14
    #   comp_ref_count           4   -> n_refs
    #   comp_ref_entry           8   x n_refs
    #   comp_history_tail       21
    # = 25 + 8 * n_refs after the code name, which is exactly what
    # reference._walk_comp_table steps by -- and scripts/audit_coverage.py claims the whole
    # table MEASURED per record on the strength of it.
    "comp_trailer": (14, _comp_trailer_layout()),
    "comp_ref_count": (4, _comp_ref_count_layout()),
    "comp_ref_entry": (8, _comp_ref_entry_layout()),
    "comp_history_tail": (21, _comp_history_tail_layout()),
}


def _coverage(name, stride, fields):
    """Every byte in [0, stride) accounted for?"""
    owner = [None] * stride
    clash = []
    for off, width, fname in fields:
        for b in range(off, off + width):
            if not (0 <= b < stride):
                clash.append(f"{fname} byte {b} outside [0,{stride})")
                continue
            if owner[b] is not None and owner[b] != fname:
                clash.append(f"byte {b}: {owner[b]} vs {fname}")
            owner[b] = fname
    gaps = [b for b in range(stride) if owner[b] is None]
    unknown = sorted({owner[b] for b in range(stride) if owner[b] == UNKNOWN})
    n_unknown = sum(1 for b in range(stride) if owner[b] == UNKNOWN)
    ok = not gaps and not clash
    print(f"  COVERAGE {name}: stride {stride}, "
          f"{stride - len(gaps) - n_unknown} named + {n_unknown} declared-unknown "
          f"+ {len(gaps)} UNACCOUNTED")
    for c in clash:
        print(f"    OVERLAP {c}")
    if gaps:
        print(f"    UNACCOUNTED BYTES {gaps}")
        print("    -> name them, or declare them UNKNOWN in LAYOUTS. A byte that is neither "
              "is a byte we are stepping over by accident.")
    return ok


def _stride(name, offsets, claimed):
    """Does the gap between consecutive records actually equal the claimed stride?"""
    offs = sorted(offsets)
    if len(offs) < 50:
        print(f"  STRIDE   {name}: only {len(offs)} records, not measuring")
        return True
    gaps = collections.Counter(b - a for a, b in zip(offs, offs[1:]))
    modal, hits = gaps.most_common(1)[0]
    frac = hits / (len(offs) - 1)
    # the rest should be small MULTIPLES of the stride (a skipped record), not noise
    multiples = sum(c for g, c in gaps.items() if g and g % claimed == 0)
    ok = modal == claimed and frac > 0.5
    print(f"  STRIDE   {name}: modal gap {modal} ({frac:.1%} of {len(offs)-1} gaps), "
          f"{multiples/(len(offs)-1):.1%} are multiples of {claimed} "
          f"-- claimed {claimed} {'OK' if ok else 'MISMATCH'}")
    return ok


def _extent(name, ids):
    """A keyed table should be contiguous in its own id space."""
    ids = sorted(ids)
    lo, hi = ids[0], ids[-1]
    missing = sorted(set(range(lo, hi + 1)) - set(ids))
    ok = not missing and lo == 0
    print(f"  EXTENT   {name}: {len(ids)} rows, ids {lo}..{hi}, "
          f"{len(missing)} gaps {'OK' if ok else 'CHECK'}")
    if missing:
        print(f"    gaps: {missing[:20]}{' ...' if len(missing) > 20 else ''}")
        print("    -> a gap is either a real hole in the save or a row the walk dropped. "
              "Decide which; do not leave it to a tolerance constant.")
    return ok


def _print_map(name, stride, fields):
    """The per-byte schema, UNKNOWN rows included. This is the record documentation:
    generated from the layouts the parser actually uses, so it cannot go stale."""
    print(f"\n{name}  ({stride} bytes)")
    print(f"  {'offset':>10}  {'width':>5}  field")
    for off, width, fname in sorted(fields):
        span = f"+{off}" if width == 1 else f"+{off}..{off + width - 1}"
        flag = "   <-- undecoded" if fname == UNKNOWN else ""
        print(f"  {span:>10}  {width:>5}  {fname}{flag}")
    n_unk = sum(w for _, w, n in fields if n == UNKNOWN)
    print(f"  -- {stride - n_unk} of {stride} bytes decoded, {n_unk} undecoded")


def main():
    if "--map" in sys.argv:
        for name, (stride, fields) in LAYOUTS.items():
            _print_map(name, stride, fields)
        return 0
    save = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/fm-saves/frem/frem-2024-11-10.fms")
    if not os.path.exists(save):
        print(f"SKIP: {save} not found (fetch with rclone or scripts/rebuild.py)")
        return 0
    print(f"auditing {os.path.basename(save)}\n")
    ok = True

    print("static layout checks (no save needed):")
    for name, (stride, fields) in LAYOUTS.items():
        ok &= _coverage(name, stride, fields)
    print()

    with open(save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        print("measured against the save:")
        attrs = S.scrape_attributes(mm)
        ok &= _stride("player_attribute", [r["P"] for r in attrs.values()], 78)

        info = S.scrape_players(mm)
        sa = ST.scrape_staff_attributes(
            mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
        ok &= _stride("staff_attribute", [r["offset"] for r in sa.values()], 39)

        cities = PL.scrape_cities(mm)
        ok &= _stride("city", [v["offset"] for v in cities.values()], PL.CITY_RECORD)
        ok &= _extent("city", cities.keys())

        stadiums = PL.scrape_stadiums(mm)
        ok &= _extent("stadium", stadiums.keys())

    print("\n" + ("PASS: every record fully accounted for" if ok
                  else "FAIL: see UNACCOUNTED / MISMATCH / CHECK above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
