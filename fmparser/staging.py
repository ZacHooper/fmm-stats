#!/usr/bin/env python3
"""
Staging scrapers: sweep each region of the save ONCE into a flat, keyed table.

Design (see docs/BUGS.md and the README): the player INFO section is the identity
spine — one record per player carrying every foreign key (SID -> attributes,
club_tid -> club, name IDs -> names). We scrape each region independently, capturing
its join keys, and defer all joins to the caller.

Sweeping record-by-record (rather than searching for a value) is both faster at scale
(~31k players) and collision-free: we read each record's embedded key instead of
hunting for bytes that might appear as stray data.
"""
from . import primitives as P
from . import records as RD
from . import reference as R
from . import schema as SC
from .schema import DATE, Field, HEX4, PAD, Record, U8, U16, U32, UNKNOWN
from .regions import (ATTR_LO, ATTR_HI, CONTRACTREC_LO, CONTRACTREC_HI,
                      WAGE_GBP_PER_UNIT)

# free agents / unattached carry this sentinel club id
NO_CLUB = P.NO_ID16

# The info record's NICKNAME field at +16. FFFFFFFF is the "no nickname" sentinel; a
# player who HAS one carries a real nickname id there instead. See `scrape_players`.
NO_NICKNAME = b"\xff\xff\xff\xff"

# DOB year plausibility window for an info record.
#
# The ceiling was 2012, which sounds generous until you notice the youngest cohort in a 2026
# save is already 2009/2010 — roughly three seasons before newgens start being born past the
# ceiling and vanishing from the spine entirely, silently, exactly like every other bug in
# this family. Raised to 2030.
#
# Measured cost of raising it, across 6 saves: bucaspor picks up TWO placeholder records
# (dob 2021-01-01, i.e. a one-year-old in a 2022 save — 'Sabri Davids', 'Edgar Carrera').
# They carry no SID so they gain no attributes, and 2 in 33,943 is the same order as the
# junk sweep 1 has always carried. Judged worth it against a scheduled, silent data loss.
# The day-of-year check added to sweep 1 below removes strictly more junk than this admits
# (one bogus record per save, on all 6).
#
# The FLOOR is fine and stays: the oldest people taper off smoothly (1956: 2, 1957: 4,
# 1958: 9), which is a real cohort edge, not a clipped one.
DOB_YEAR_LO, DOB_YEAR_HI = 1955, 2030

# first/last/nickname ids index the whole-DB name tables (~46k entries — see
# reference.build_name_resolver). The largest REAL id seen across the 30,798 records of
# a full save is 32,147; exactly two junk records carry 82M and 0xFFFF0000. 65536 sits
# comfortably above the real range and below the junk.
NAME_ID_MAX = 65536

# squad-availability status byte in the contract record. 65 = out on loan / unavailable
# (validated against the managed club's squad vs an in-game screenshot); 112 = normal
# squad member. Other values are further squad statuses (undecoded).
LOAN_STATUS = 65


# The 8 personality bytes at info+52..59, in order. Verified byte-exact against all 7
# ground-truth managers' Manager Profile screenshots (BUGS #14) and matching the order
# fmm-editor's `People.cs` declares. Slot 3 reads DETERMINATION on the FMM22 screens and
# `Controversy` in People.cs -- ours is the ground-truth reading for our game. `sportsmanship`
# is the one slot with no UI to check against, taken on the order's authority alone.
PERSONALITY = ("adaptability", "ambition", "determination", "loyalty", "pressure",
               "professionalism", "sportsmanship", "temperament")
# 0 means "not populated", not a real rating: all 622 staff who read 0 are exactly the staff
# with no attribute record at all -- placeholder people the save never filled in. Every staff
# member who HAS a record reads 1-20 on all eight.

# ---------------------------------------------------------------------------------------
# The INFO (person) record's FIXED HEAD -- the single declaration of what this record is.
#
# `_decode_info` reads FROM this table and `scripts/audit_records.py` checks AGAINST it, so
# the parser and its audit cannot drift; `audit_records.py --map` prints it as the schema.
# UNKNOWN rows are first-class: a byte we have decided we cannot name is covered, and visible.
#
# Offsets come from fmm-editor's `People.cs` constructor, which gives read ORDER, shifted for
# one FMM22 divergence: NationalCaps and NationalGoals are u8 here and i16 there, so
# everything from +40 on sits 2 bytes earlier than FMM26. That shift is what makes the rest
# land on offsets we had already verified independently -- club at +42, personality at +52,
# PlayerId at +60, the staff link at +64 -- which is the check that the alignment is right.
#
# The record as a whole is VARIABLE-LENGTH: past this head come counted language and
# relationship lists (BUGS #14 Round 4). Only the head is fixed, and only the head is declared.
INFO_LAYOUT = Record("info_head", 68, (
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", U32),
    Field(8, 4, "first_name_id", U32),
    Field(12, 4, "last_name_id", U32),
    # People.cs calls this CommonNameId: the name the game DISPLAYS, 0xFFFFFFFF when unset.
    # It indexes the THIRD id-table (`reference.resolve_common_name`), not either name table.
    #
    # This comment used to say "only 0.1% of records set it ... so it is NOT the link
    # `_scrape_nicknamed` follows". That was wrong twice over. The real rate is 7.4% (2,424
    # of 32,760 on frem-2023-07-02, every one of which resolves), which is exactly the ~8%
    # that carry a nickname -- and it IS the same +16 field `_scrape_nicknamed` keys on, as
    # `scrape_players`' own docstring says when it calls +16 "the nickname field".
    Field(16, 4, "common_name_id", U32),
    Field(20, 4, "dob", DATE),
    Field(24, 2, "nationality_id", U16),
    # 78% ffff, and the other 22% sit in the same id space as the primary nationality.
    Field(26, 2, "second_nationality_id", U16),
    # People.cs: Ethnicity. 13 distinct small values -- which also retires BUGS #6's guess that
    # this byte was a "declared national team", a field that would hold nation ids in the 100s.
    Field(28, 1, "ethnicity", U8),
    Field(29, 4, UNKNOWN, PAD),                 # People.cs Unknown1; not a date (0% plausible)
    # People.cs: Type. NOT a clean player/staff flag -- three values (1, 0, and 16, which is
    # rough-guide's "role flag 10 = manager" in hex) and it agrees with our SID rule on only
    # 82.4% of records. BUGS #14's "agrees ~99%" was wrong. Carried; the SID rule still decides.
    Field(33, 1, "type_flag", U8),
    Field(34, 4, "unknown_date", DATE),                 # decodes 100% as a date, but 82% read 1900 = null
    Field(38, 1, "international_caps", U8),
    Field(39, 1, "international_goals", U8),
    Field(40, 1, "u21_caps", U8),
    Field(41, 1, "u21_goals", U8),
    # People.cs declares ClubId as i32 and it is: +44..45 is 0 for every real club and ffff
    # paired with the no-club sentinel. Read whole, then normalised back to the u16 NO_CLUB
    # the rest of the codebase compares against.
    Field(42, 4, "club_tid", U32),
    # Date joined the current club. 100% of records decode as a plausible [day][year], none
    # later than the save's own season, and 4 of 5,998 earlier than age 14.
    Field(46, 4, "joined_date", DATE),
    Field(50, 2, UNKNOWN, PAD),                 # People.cs Unknown3
    *(Field(52 + i, 1, n, U8) for i, n in enumerate(PERSONALITY)),
    Field(60, 4, "sid", HEX4),                 # People.cs PlayerId; ffffffff for staff
    Field(64, 4, "id2", U32),                 # People.cs Unknown6b -> the STAFF attribute record
), is_head=True)


INFO_HEAD = INFO_LAYOUT.span

# Everything the INFO record contributes that is true of a PERSON rather than of a player or
# a staff member -- named once so extract.py, the loader and the mart cannot drift apart.
PERSON_FIELDS = PERSONALITY + ("international_caps", "international_goals",
                               "u21_caps", "u21_goals", "joined_date",
                               "second_nationality_id", "ethnicity")


def _decode_info(mm, base):
    """Decode one info record at `base` into the spine's identity dict, from INFO_LAYOUT."""
    rec = RD.read(mm, INFO_LAYOUT, base)
    # Sentinels, handled here rather than in the layout because they are about MEANING, not
    # about where the bytes are.
    #
    # AN EMPTY SLOT HAS NO UID. 77 of 32,849 person records are unpopulated, and `uid == 0`
    # identifies them EXACTLY -- it is the record's own invariant, not a tuned window. They are
    # the source of every implausible value this record produces: all 77 read 255 in both
    # international fields (the only records that do), and all 66 of the nonsense joined_dates
    # -- 1290, 1545, 2570 -- are theirs. Blanking the person block at the record level is why
    # no per-field plausibility test is needed anywhere downstream. The identity fields are
    # left alone so the spine still resolves them.
    if rec["uid"] == 0:
        for k in PERSON_FIELDS:
            rec[k] = None
    # 0 and ffff both mean "no second nationality".
    if rec["second_nationality_id"] in (0, 0xFFFF):
        rec["second_nationality_id"] = None
    # A full-width no-club sentinel collapses to the u16 NO_CLUB the rest of the code compares
    # against; anything else above u16 range is a mis-anchored record, and reads as no club too.
    if rec["club_tid"] > 0xFFFF:
        rec["club_tid"] = NO_CLUB
    return rec


def _scrape_nicknamed(mm, found):
    """The info records `scrape_players`' FFFFFFFF sweep structurally cannot see.

    Anchoring on FFFFFFFF finds the nickname field only when it is EMPTY, so every player
    who HAS a nickname was invisible to the whole player decode — no name, no attributes,
    no squad membership, no ratings. On a real save that is ~2,100 records, heavily
    concentrated in the nickname-using nations: Brøndby's Carlos Polo ("Peque Polo") and
    Waldo Rubio ("Waldo") both started against us and neither existed in our data.

    There is no anchor byte to search for here and the records are variable length
    (91-107 bytes, no alignment), so we sweep the 58 possible DOB-year u16 values instead
    — each an `mm.find` at C speed — and validate hard. `found` is the FFFFFFFF sweep's
    result, which supplies the strongest validator we have: the set of club ids already
    known to be real. A false positive would need a plausible tid, a plausible day-of-year,
    a real club id AND a pair of name ids that resolve to actual names.
    """
    clubs = {p["club_tid"] for p in found.values()} - {NO_CLUB}
    # Every one of the 30,798 records the FFFFFFFF sweep finds resolves to a name, so
    # "resolves" is a sound invariant to filter on. Degrade gracefully if the name tables
    # aren't discoverable rather than dropping every candidate.
    try:
        resolves = R.build_name_resolver(mm)
    except Exception:
        resolves = False

    out = {}
    end = len(mm)
    for year in range(DOB_YEAR_LO, DOB_YEAR_HI + 1):
        pat = year.to_bytes(2, "little")
        p = 0
        while True:
            k = mm.find(pat, p)
            if k == -1:
                break
            p = k + 1
            base = k - 22                   # the year u16 sits at +22
            if base < 0 or base + 64 > end:
                continue
            if mm[base + 16:base + 20] == NO_NICKNAME:
                continue                    # the FFFFFFFF sweep already had its chance
            tid = int.from_bytes(mm[base:base + 4], "little")
            if not (100 < tid < 70000) or tid in found or tid in out:
                continue
            if int.from_bytes(mm[base + 20:base + 22], "little") > 366:
                continue                    # day-of-year
            club = int.from_bytes(mm[base + 42:base + 44], "little")
            if club != NO_CLUB and club not in clubs:
                continue
            rec = _decode_info(mm, base)
            nick = int.from_bytes(mm[base + 16:base + 20], "little")
            if max(rec["first_name_id"], rec["last_name_id"], nick) >= NAME_ID_MAX:
                continue
            if resolves and R.resolve_name(
                    mm, rec["first_name_id"], rec["last_name_id"]) is None:
                continue
            out[tid] = rec
    return out


def scrape_players(mm):
    """The identity spine: {tid: info dict}, in two sweeps.

    1. Records with NO nickname, found by searching for the FFFFFFFF sentinel that sits in
       the nickname field at +16 (then a plausible DOB year and tid). Fast, and it covers
       ~94% of the database.
    2. Records WITH a nickname, which sweep 1 cannot see by construction — see
       `_scrape_nicknamed`. Sweep 1's results are passed in and always win a tid clash, so
       this only ever ADDS to the spine.
    """
    players = {}
    for base in _nickname_sentinel_candidates(mm):
        tid = P.u32(mm, base)
        if tid in players:
            continue
        players[tid] = _decode_info(mm, base)

    players.update(_scrape_nicknamed(mm, players))
    return players


def _nickname_sentinel_candidates(mm):
    """Record starts for sweep 1, in ascending file order.

    NO WINDOW, and no gap threshold either. The records do form one dense run -- 30,797 of
    them between 0.584 MB and 3.989 MB on frem-2026-06-11, largest internal gap 6 KB, and
    the same shape on frem-2021 and bucaspor-2023 -- but "dense run" is not an invariant this
    table asserts about itself, and bounding the walk by a tuned gap would make the record
    count a function of that number. That is the mistake the city table's miss counter made.

    So the SCAN stays whole-file and the predicate is unchanged; what changes is that it is
    evaluated with numpy instead of in a 21-million-iteration Python loop. Measured on
    frem-2026-06-11: the sentinel occurs 21,213,200 times and 30,797 survive, which is a
    ratio of 689:1 -- the loop existed almost entirely to reject.

    Overlapping matches are kept, exactly as `mm.find(..., j + 1)` produced them: a run of
    five 0xFF bytes yields a candidate at both of its first two positions.
    """
    import numpy as np
    a = np.frombuffer(mm, dtype=np.uint8)
    ff = a == 0xFF
    # every offset where four consecutive bytes are 0xFF (overlaps included)
    j = np.flatnonzero(ff[:-3] & ff[1:-2] & ff[2:-1] & ff[3:])
    base = j - 16                          # the sentinel is the nickname field at +16
    base = base[base >= 0]
    base = base[base + INFO_HEAD <= len(a)]

    def u16(off):
        return a[base + off].astype(np.uint32) | a[base + off + 1].astype(np.uint32) << 8

    def u32(off):
        return (u16(off) | a[base + off + 2].astype(np.uint32) << 16
                | a[base + off + 3].astype(np.uint32) << 24)

    year = u16(22)
    tid = u32(0)
    # Day-of-year sanity, which `_scrape_nicknamed` has always applied and this sweep did
    # not until the DOB ceiling was raised: a junk record carrying a plausible year and a
    # day-of-year of ~61,000 rolls forward into a DOB of 2199 and was admitted to the spine
    # ('Rajagobal Rajagobal', 2-5 per save). The two sweeps validate it the same way now.
    day = u16(20)
    keep = ((year >= DOB_YEAR_LO) & (year <= DOB_YEAR_HI)
            & (tid > 100) & (tid < 70000) & (day <= 366))
    return [int(b) for b in base[keep]]


# THE TWO CONTRACT RECORDS. Both are shape F in docs/parser-architecture.md -- found by
# searching for a key, not by walking a table -- so neither has a stride and both are declared
# `is_head=True`: the span is what we READ, not what the record is.
#
# The status record is the interesting declaration. We read 8 bytes at the front and 3 at
# +37, and the 29 bytes between them were simply never mentioned anywhere. Naming them PAD
# says out loud that the record continues and we cannot read it, which is a different claim
# from the record being 11 bytes long.
CONTRACT_STATUS = Record("contract_status", 40, (
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", U32, note="both must match the info spine -- 8 exact bytes"),
    Field(8, 29, UNKNOWN, PAD),
    Field(37, 2, "marker", U16, note="0x0087; this is what the scan searches for"),
    Field(39, 1, "squad_status", U8),
), is_head=True)

# `[tid u32][0x01][wage u16][6 x 00][expiry day u16][expiry year u16]`.
#
# `expiry` is a DATE in the same [day-of-year][year] encoding as DOB, so it is ONE four-byte
# field, not two -- and `expiry_year` is an alias over its second half, because the year alone
# is both the plausibility gate the scan uses and a column downstream.
#
# The money conversion is NOT here. Wage units x WAGE_GBP_PER_UNIT (~520) is one of four money
# conventions in this save, and which applies is a property of this record; a shared helper
# would let a call site be wrong by that factor and still return a plausible number.
CONTRACT_DETAIL = Record("contract_detail", 17, (
    Field(0, 4, "tid", U32),
    Field(4, 1, "marker", U8, note="0x01 -- distinguishes this from the 0x87 status record"),
    Field(5, 2, "wage_units", U16),
    Field(7, 6, UNKNOWN, PAD),
    Field(13, 4, "expiry", DATE, note="some Danish deals expire 31 Dec -- keep the DAY"),
    Field(15, 2, "expiry_year", U16, alias=True),
), is_head=True)


def scrape_contract_status(mm, info, lo=None, hi=None):
    """{tid: squad_status_code} from the contract records. Each record is keyed by
    [TID:u32][UID:u32]; a 0x0087 marker sits at TID+37 and the status byte at TID+39.

    SCANS THE WHOLE FILE by default. It used to scan a 54-58 MB window (regions.py),
    which was measured on Bucaspor and is simply the wrong place on Frem — the section runs
    ~50-60 MB there, so the window opened ~4 MB after it started and threw away everything
    before that. Measured cost of the constant: frem-2021-07-01 and frem-2023-07-01 found
    ZERO of ~25,500 records (squad_status entirely NULL for those snapshots), the later Frem
    saves 39-57%, and Bucaspor — the career it was tuned on — a flawless 100%.

    No window is needed because the validation is already far stronger than a byte range:
    every hit must match BOTH the tid and the uid from the info spine, 8 exact bytes. Across
    the whole file that yields 25,687 records on frem-2026 with no tid disagreeing on status.
    `lo`/`hi` are kept for callers that want to restrict the scan.
    """
    lo = 0 if lo is None else lo
    hi = len(mm) if hi is None else hi
    uid_of = {tid: p["uid"] for tid, p in info.items()}
    out = {}
    p = lo
    while True:
        m = mm.find(b"\x87\x00", p, hi)
        if m == -1:
            break
        p = m + 1
        if m - 37 < 0:
            continue
        base = m - CONTRACT_STATUS.field("marker").offset
        rec = RD.read_fields(mm, CONTRACT_STATUS, base, ("tid", "uid", "squad_status"))
        if uid_of.get(rec["tid"]) == rec["uid"]:
            out[rec["tid"]] = rec["squad_status"]
    return out


def scrape_contracts(mm, info, lo=CONTRACTREC_LO, hi=CONTRACTREC_HI):
    """{tid: {wage_units, wage_gbp, expiry, expiry_year}} from the contract DETAIL records.

    Record layout (anchored on the player TID): `[tid u32][0x01 marker][wage u16][6×00]
    [expiry day-of-year u16][expiry year u16]`. Wage £/yr = units × WAGE_GBP_PER_UNIT
    (validated £15.5K–£17.75M, ±2%). Expiry is a full date in the same day-of-year+year
    encoding as DOB. We scan the section and keep every hit whose TID is in the info spine
    (collision-safe), first record per tid wins."""
    out = {}
    # -17, not 0: the record body reads as far as p+16 (expiry year at +15..+17), so a bare
    # `p < len(mm)` walks off the end and raises IndexError. Harmless while hi defaulted to
    # 40M, but scrape_contract_status now scans to EOF and this is the same family of scan.
    end = min(hi, len(mm) - 17)
    p = lo
    while p < end:
        if mm[p + 4] == 0x01:
            yr = P.u16(mm, p + CONTRACT_DETAIL.field("expiry_year").offset)
            if 2018 <= yr <= 2035:
                tid = P.u32(mm, p)
                if tid in info and tid not in out:
                    r = RD.read_fields(mm, CONTRACT_DETAIL, p, ("wage_units", "expiry"))
                    out[tid] = {
                        "wage_units": r["wage_units"],
                        "wage_gbp": r["wage_units"] * WAGE_GBP_PER_UNIT,
                        "expiry": r["expiry"],
                        "expiry_year": yr,
                    }
        p += 1
    return out


def scrape_attributes(mm, lo=ATTR_LO, hi=ATTR_HI):
    """Every global attribute record in [lo, hi), keyed by its embedded SID."""
    from .tables.player_attributes import scrape_player_attributes
    return scrape_player_attributes(mm)
