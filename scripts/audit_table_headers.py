#!/usr/bin/env python3
"""
Does every table we walk declare its own size, the way the competition table does?

The competition table turned out to announce itself: a run of 0xFF filler, then a u16
holding the table's OWN record count, then record 0. That one fact replaced a
candidate-scan-plus-plausibility-gate cascade with pure arithmetic (`reference._walk_comp_table`),
and the history slab has the same shape one door down -- `u32 @ start-12` is its exact row
count (`history.locate`). Two tables, two self-declared counts, found years apart and by
accident both times.

So this script asks the question deliberately, for every table the parser locates: take the
FIRST record, look back HEADER_BACK bytes, and see whether any u16/u32 in there equals the
number of records we ended up with. It reports:

  * the byte immediately preceding the table (filler? and how much of it)
  * every u16/u32 in the look-back window that matches n / max_id+1 / max_id, and where
  * a hex dump of the look-back window, so a near-miss is visible rather than just absent

It deliberately does NOT try to re-walk anything from a header it finds. A match here is a
LEAD -- "this offset holds a number equal to our record count on this save" -- and a single
save cannot tell a real count field from a coincidence. Confirm a lead across saves and
careers (`--all`) before anything in fmparser/ starts trusting it.

Usage:
  uv run python scripts/audit_table_headers.py [save.fms]      # one save, with hex dumps
  uv run python scripts/audit_table_headers.py --all           # every archived save, terse
"""
import collections
import glob
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fmparser.tables import player_attributes as A                 # noqa: E402
import numpy as np                                   # noqa: E402
from fmparser import history as H                    # noqa: E402
from fmparser import lookups as LK                   # noqa: E402
from fmparser.tables import cities, stadiums         # noqa: E402
from fmparser import reference as R                  # noqa: E402
from fmparser.tables import staff as ST              # noqa: E402
from fmparser.tables.person_info import (
    DOB_YEAR_HI as _DOB_YEAR_HI,
    DOB_YEAR_LO as _DOB_YEAR_LO,
    NO_NICKNAME as _NO_NICKNAME,
    scrape_person_info as _scrape_players,
)                                                    # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes as _scrape_attributes  # noqa: E402

HEADER_BACK = 128          # how far behind record 0 to look for a count
MIN_UNDECLARED = 200       # count floor for t_undeclared; below it the exact-division
                           # test is satisfied by chance too often to mean anything
FILLER = (0x00, 0xFF)


class Table:
    """One table's measurement: where it starts, what ids it holds, how many records.

    `start` must be the first byte of the FIRST record in file order -- not the first record
    the scraper happened to find, and not a record's payload. Every locator below states
    which it is, because getting this wrong makes the look-back window land inside the
    previous record and the whole question unanswerable.
    """

    def __init__(self, name, start, ids=None, n=None, note=""):
        self.name = name
        self.start = start
        self.ids = sorted(ids) if ids is not None else None
        self.n = n if n is not None else (len(self.ids) if self.ids else None)
        self.note = note

    @property
    def targets(self):
        """The numbers a count field could plausibly be holding, as {value: label}.

        n and max_id+1 differ exactly when the table is NOT dense from 0, and which one a
        header matches is itself informative -- the competition table's count is the SLOT
        count (1372), which is max_cid+1 and larger than the 1272 records that carry a name.
        """
        t = {}
        if self.n:
            t.setdefault(self.n, "n_records")
        if self.ids:
            t.setdefault(self.ids[-1] + 1, "max_id+1")
            t.setdefault(self.ids[-1], "max_id")
        return t


def _u(mm, o, w):
    return int.from_bytes(mm[o:o + w], "little")


def filler_run(mm, start, min_run=4):
    """(byte, run_start, run_end) of the last constant 0x00/0xFF filler run ending at or
    before `start`, or None.

    The filler is what makes a header READABLE, and its position is the whole point: the
    competition table is `[...filler...][count u16][record 0]`, so the count sits BETWEEN the
    filler and the first record, not before the filler. A first pass here tested only
    `mm[start-1]` for filler and therefore reported "none (packed)" for the very tables that
    have the clearest header -- the count byte is not filler, which is exactly why it is
    legible. So find the filler, then treat everything from its end to the record as the
    candidate header.
    """
    end = start
    while end > 0:
        b = mm[end - 1]
        if b in FILLER:
            k = end
            while k > 0 and mm[k - 1] == b:
                k -= 1
            if end - k >= min_run:
                return b, k, end
            end = k                       # too short to be filler; keep looking back
        else:
            end -= 1
        if start - end > HEADER_BACK:
            return None
    return None


def header(mm, tab):
    """The candidate header: the bytes between the preceding filler run and record 0.

    Returns (gap_len, {width: value}) reading the gap's LAST 2 and 4 bytes -- i.e. a count
    sitting flush against record 0, which is where the competition table puts it. Reported
    unconditionally, match or not: "the table declares 124 and we read 77" is a finding, and a
    probe that only prints hits would have shown that table as silent.
    """
    run = filler_run(mm, tab.start)
    if not run:
        return None, {}
    gap = tab.start - run[2]
    vals = {w: _u(mm, tab.start - w, w) for w in (2, 4) if gap >= w}
    return gap, vals


def probe(mm, tab):
    """Every u16/u32 in the look-back window whose value is one of `tab.targets`."""
    lo = max(0, tab.start - HEADER_BACK)
    hits = []
    for o in range(lo, tab.start):
        for w in (2, 4):
            if o + w <= tab.start:
                label = tab.targets.get(_u(mm, o, w))
                if label:
                    hits.append((o - tab.start, w, _u(mm, o, w), label))
    return hits


def hexdump(mm, tab):
    lo = max(0, tab.start - HEADER_BACK)
    out = []
    for row in range(lo, tab.start, 16):
        chunk = mm[row:min(row + 16, tab.start)]
        out.append(f"    {row - tab.start:+5d}  " + " ".join(f"{b:02x}" for b in chunk))
    return out


# --------------------------------------------------------------------------- locators
# Each returns a Table or None. Keep the `start` honest: see Table.__doc__.

def t_competitions(mm):
    """CONTROL CASE. The known-good answer -- if this table stops reporting a header hit at
    -2, the probe itself is broken, not the save."""
    anchor = R._comp_table_anchor(mm)
    if not anchor:
        return None
    start, count = anchor
    comps, n_blank = R._walk_comp_table(mm)
    return Table("competitions", start, ids=comps.keys(), n=count,
                 note=f"declared {count} = {len(comps)} named + {n_blank} blank")


def t_history(mm):
    """CONTROL CASE #2: the slab's row count is a u32 at start-12, already parsed."""
    cands = H.locate(mm)
    if not cands:
        return None
    rows, start, _hits = cands[0]
    return Table("history_slab", start, n=rows, note=f"{rows} rows x {H.STRIDE}B")


def t_cities(mm):
    """`offset` IS the record start, and the table is dense from id 0."""
    cities_map = cities.scrape_cities(mm)
    if not cities_map:
        return None
    return Table("cities", min(v["offset"] for v in cities_map.values()), ids=cities_map.keys())


def t_stadiums(mm):
    stadiums_map = stadiums.scrape_stadiums(mm)
    if not stadiums_map:
        return None
    return Table("stadiums", min(v["offset"] for v in stadiums_map.values()), ids=stadiums_map.keys())


def t_nations(mm):
    """`offset` is c-6, the uid field, which IS the record head ([uid u32][id u16][names])."""
    nations = LK.scrape_nations(mm)
    if not nations:
        return None
    return Table("nations", min(v["offset"] for v in nations.values()), ids=nations.keys())


def t_languages(mm):
    langs = LK.scrape_languages(mm)
    if not langs:
        return None
    return Table("languages", min(v["offset"] for v in langs.values()), ids=langs.keys())


def t_currencies(mm):
    """Keyed by uid, which is NOT an ordinal, so only `n_records` is a usable target."""
    cur = LK.scrape_currencies(mm)
    if not cur:
        return None
    return Table("currencies", min(v["offset"] for v in cur.values()), n=len(cur),
                 note="keyed by uid, not an ordinal")


def t_browse_names(mm):
    """The flat [len][utf-8] name table at the file's front -- no ids at all, so `n` is the
    only target. It is also the only table here whose start the parser already pins exactly."""
    start, end, names = R._walk_browse_bounds(mm)
    if not names:
        return None
    return Table("browse_names", start, n=len(names), note=f"{end - start} bytes of strings")


def t_name_id_tables(mm):
    """The two id->ordinal tables, 16B stride, id == slot index. Already walked by their own
    invariant (`_discover_id_tables`), so a declared count would be confirmation, not news."""
    browse = R._walk_browse(mm)
    if not browse:
        return []
    out = []
    for i, (base, n) in enumerate(R._discover_id_tables(mm, len(browse))):
        out.append(Table(f"name_id_table_{i}", base, ids=range(n),
                         note=f"{n} entries x 16B"))
    return out


def t_player_attributes(mm):
    """78B grid. The scraper reports `P` (the positions block); the record STARTS at the sid,
    P-42 -- see `scripts/audit_records.py`'s player_attribute layout."""
    attrs = _scrape_attributes(mm)
    if not attrs:
        return None
    return Table("player_attributes", min(r["P"] for r in attrs.values()) - 42,
                 n=len(attrs), note="keyed by sid (a hex handle, not an ordinal)")


def t_staff_attributes(mm, info):
    """39B stride, and the table is a DENSE ARRAY INDEXED BY id2 -- confirmed 4642/4642 slots
    where `id2 == slot index` on frem-2023-07-02.

    The base is derived from the PLAYER attribute table rather than from our own walk, and
    that distinction is the finding: `scrape_staff_attributes` is driven by the id2 values the
    info spine hands it, so the first record it reaches is whichever staff member happens to
    be in the spine -- 9 slots into the table here. Reporting that offset as the table start
    would look header-less while the header sits 351 bytes (9 x 39) behind it.
    """
    pa = t_player_attributes(mm)
    if not pa:
        return None
    decl = _u(mm, pa.start - 4, 4)
    base = pa.start + 78 * decl + 8 + 4          # player table, its 8B FF filler, its count
    if _u(mm, base, 4) != 0:                     # slot 0 must be id2 0
        return None
    sa = ST.scrape_staff_attributes(
        mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
    return Table("staff_attributes", base, n=len(sa),
                 note=f"we read {len(sa)}, driven by the info spine's id2 set")


def t_info_spine(mm, info):
    """The person records. `scrape_players` does not report offsets, so re-derive the FIRST
    one here the same way sweep 1 does (the FFFFFFFF nickname sentinel at +16) -- that sweep
    sees ~94% of the database, which is more than enough to find where the table begins.
    """
    first = None
    i = 0
    while True:
        j = mm.find(_NO_NICKNAME, i)
        if j == -1:
            break
        i = j + 1
        base = j - 16
        if base < 0:
            continue
        year = _u(mm, base + 22, 2)
        if not (_DOB_YEAR_LO <= year <= _DOB_YEAR_HI):
            continue
        tid = _u(mm, base, 4)
        if not (100 < tid < 70000) or _u(mm, base + 20, 2) > 366:
            continue
        first = base
        break
    if first is None:
        return None
    return Table("info_spine", first, ids=info.keys(), n=len(info),
                 note="variable-length records; keyed by tid")


def t_clubs(mm):
    """CLUBS HAVE NO TABLE ANCHOR, and that is the finding -- there is no "first record" to
    look behind, so this returns None and prints why.

    Clubs come from the candidate scan, whose accepted records sprawl across ONE 6.4 MB run
    (6,340,470 .. 12,776,631 on frem-2023-07-02, 24,669 of them) whose first entry is junk
    (tid 1,701,276,737). A scan with no located table cannot be asked "what is behind your
    first record", because it does not have one. This is the same conclusion the club-side
    exclusions in `reference._nation_table_bounds` already argue for from the other
    direction, and it is the club-table item in docs/TODO.md.
    """
    return None


def t_undeclared(mm):
    """Tables the file DECLARES that no parser here reads, found by the framing convention
    rather than by looking for content: a run of >=8 0xFF, a u32 count, then `count * stride`
    bytes landing exactly on the next such run.

    The exact-division test is what makes this safe to report at all -- a count alone is a
    coincidence away from meaningless, but a count whose product with an integer stride lands
    precisely on the next filler run is describing a real fixed-width table. It only sees
    FIXED-WIDTH tables with no internal filler, so absence here is not evidence of absence
    (the two name id-tables are fixed-width and still invisible to it, because their free
    slots are themselves 0xFF).
    """
    buf = np.frombuffer(mm, dtype=np.uint8)
    d = np.diff(np.concatenate(([0], (buf == 0xFF).view(np.int8), [0])))
    runs = [(int(s), int(e)) for s, e in
            zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)) if e - s >= 8]
    out = []
    for i, (_s, e) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(mm)
        n = _u(mm, e, 4)
        if not (MIN_UNDECLARED <= n <= 5_000_000):
            continue
        span = nxt - (e + 4)
        if span > 0 and span % n == 0 and 4 <= span // n <= 4096:
            out.append((e + 4, n, span // n))
    return out


def tables(mm):
    out = []
    info = _scrape_players(mm)
    for fn in (t_competitions, t_history, t_cities, t_stadiums, t_nations, t_languages,
               t_currencies, t_browse_names, t_player_attributes):
        try:
            t = fn(mm)
        except Exception as exc:                       # a locator failing is a finding
            out.append((fn.__name__, exc))
            continue
        if t:
            out.append((fn.__name__, t))
    for fn in (t_staff_attributes, t_info_spine):
        try:
            t = fn(mm, info)
        except Exception as exc:
            out.append((fn.__name__, exc))
            continue
        if t:
            out.append((fn.__name__, t))
    try:
        for t in t_name_id_tables(mm):
            out.append(("t_name_id_tables", t))
    except Exception as exc:
        out.append(("t_name_id_tables", exc))
    return out


def verdict(tab, gap, vals):
    """How the declared header (if any) relates to what we actually read out of the table.

    Both widths are reported, because which one a table uses is not guessable: the
    competition, city, stadium, language and currency tables put a u16 flush against record 0,
    while the player/staff attribute grids and the two name id-tables use a u32 there. An
    earlier version of this function only fell back to u16 and therefore printed "nothing
    count-shaped" for every u32 table -- including the three that turned out to be the most
    interesting ones.

    DECLARED == n / max_id+1   -- the table's own count agrees with what we read. max_id+1 is
                                  the competition table's case: 1372 slots, 1272 named.
    SHORT                      -- we read FEWER than declared. What a walk that halts at the
                                  first unparseable or free slot looks like from outside.
    OVER                       -- we read MORE than declared, i.e. the scan is inventing
                                  records past the end of the table.
    """
    if not vals:
        return "no filler in front of the table -- nothing to read a header from"
    for w in (2, 4):
        val = vals.get(w)
        label = tab.targets.get(val) if val is not None else None
        if label:
            return f"DECLARED {val} at u{w * 8}@-{w} == {label}  [gap {gap}B]"
    parts = []
    for w in (2, 4):
        val = vals.get(w)
        if val is None or not tab.n:
            continue
        # A count field should be the same ORDER as the record count. Anything wilder is
        # another record's bytes, not a header -- say so rather than reporting a delta that
        # invites a reader to believe it.
        if not (tab.n / 8 <= val <= tab.n * 8):
            parts.append(f"u{w * 8}@-{w} = {val} (not count-shaped)")
        elif val > tab.n:
            parts.append(f"DECLARED? {val} at u{w * 8}@-{w} vs {tab.n} read"
                         f" -> {val - tab.n} SHORT")
        elif val < tab.n:
            parts.append(f"DECLARED? {val} at u{w * 8}@-{w} vs {tab.n} read"
                         f" -> {tab.n - val} OVER (records past the end?)")
    return ("; ".join(parts) or f"nothing count-shaped in the {gap}B gap") + f"  [gap {gap}B]"


def report(save, verbose=True):
    print(f"\n=== {os.path.basename(save)} ===")
    with open(save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        rows = []
        for fname, t in tables(mm):
            if isinstance(t, Exception):
                print(f"\n{fname}: LOCATOR FAILED: {type(t).__name__}: {t}")
                continue
            gap, vals = header(mm, t)
            hits = probe(mm, t)
            rows.append((t, gap, vals, hits))
            print(f"\n{t.name}  start={t.start:,}  n={t.n}"
                  + (f"  ids {t.ids[0]}..{t.ids[-1]}" if t.ids else "")
                  + (f"  [{t.note}]" if t.note else ""))
            print(f"  {verdict(t, gap, vals)}")
            for rel, w, val, label in hits:
                print(f"  hit  {rel:+5d}  u{w * 8:<2} = {val:<12} == {label}")
            if verbose:
                print("\n".join(hexdump(mm, t)))

        print("\nclubs: " + t_clubs.__doc__.split("\n\n")[0].strip())

        und = t_undeclared(mm)
        known = {t.start for _f, t in tables(mm) if not isinstance(t, Exception)}
        print(f"\ndeclared fixed-width tables found by the framing convention ({len(und)}):")
        for start, n, stride in und:
            tag = "" if start in known else "   <- NOTHING HERE PARSES THIS"
            print(f"  start={start:,}  count={n:,}  stride={stride}B  "
                  f"({n * stride:,} bytes){tag}")
        mm.close()
    return rows


# --------------------------------------------------------------------------- confirmation
# The per-table report above compares a declared count against WHAT OUR PARSER READ, which
# conflates two questions: is the count real, and is our walk complete? These checks answer
# the FIRST one only, by testing each declared count against the table's OWN invariant --
# every declared slot decodes, the last one is valid, the table ends where the count says.
# That is both cheaper (no full scrape) and stronger evidence, and it is what makes a
# cross-career sweep affordable.

def _person_table_base(mm, limit=1_200_000, filler=4096):
    """Offset of the person table's record 0, or None.

    The table's base is the first run of >= 8 0xFF in the first megabyte that is preceded by
    a long run of 0x00 -- the filler behind the browse name table. Requiring the filler is
    what stops an ordinary record ending in FF from being mistaken for a table base, and it
    needs no offset: `table-framing.md` warns to test for >= 8, never == 8.
    """
    run = 0
    for p in range(filler, min(limit, len(mm))):
        if mm[p] == 0xFF:
            run += 1
            continue
        if run >= 8:
            if all(mm[q] == 0 for q in range(p - run - filler, p - run)):
                return p + 4              # skip the u32 count, which is flush against rec 0
        run = 0
    return None


def confirm(mm):
    """[(table, declared, ok, detail)] -- each declared count checked against its own table."""
    out = []

    def add(name, declared, ok, detail):
        out.append((name, declared, ok, detail))

    # ---- player attribute grid: every declared slot must pass the position check
    attrs_start = None
    for start, n, stride in t_undeclared(mm):
        if stride == 78:
            attrs_start = start
            bad = sum(1 for k in range(n)
                      if not A._valid_positions(mm[start + 78 * k + 42:start + 78 * k + 57]))
            add("player_attributes", n, bad == 0, f"{bad} of {n} slots fail the position check")
        # ---- staff grid: id2 must equal the slot index
        elif stride == 39 and attrs_start is not None:
            ok = sum(1 for k in range(n) if _u(mm, start + 39 * k, 4) == k)
            add("staff_attributes", n, ok == n, f"id2 == slot index on {ok} of {n}")

    # ---- the PERSON table (info spine). Found 2026-09-20; this file used to say "no
    # header found", because it looked near the first record the SWEEP reaches instead of
    # at the table's base -- the same mistake the staff grid already taught once.
    #
    # The base is the first run of >= 8 0xFF below 1 MB, which sits just past the ~53 KB of
    # zero filler that follows the browse name table. The check is structural and cheap: the
    # run must be preceded by real filler (so it is a table base and not a record that
    # happens to end in FF), and the count must be person-shaped. Its real value is the
    # cross-save tally `--confirm` prints, which shows the count is CAREER-CONSTANT and
    # career-specific -- a per-database pool, like the history slab.
    base = _person_table_base(mm)
    if base is None:
        add("person_table", 0, False, "no >=8-FF run below 1 MB preceded by zero filler")
    else:
        declared = _u(mm, base - 4, 4)
        ok = 20_000 <= declared <= 60_000
        add("person_table", declared, ok,
            f"record 0 at {base}; count flush against it"
            f"{'' if ok else ' -- NOT person-shaped'}")

    # ---- the two name id-tables: the LAST declared slot must be a valid entry
    browse = R._walk_browse(mm)
    for i, (base, walked) in enumerate(R._discover_id_tables(mm, len(browse))):
        declared = _u(mm, base - 4, 4)
        if not (walked <= declared <= walked * 4):
            add(f"name_id_table_{i}", declared, False, f"not count-shaped vs walked {walked}")
            continue
        last = base + (declared - 1) * 16
        ok = (_u(mm, last + 4, 4) == declared - 1 and _u(mm, last, 4) < len(browse)
              and _u(mm, base + declared * 16 + 4, 4) != declared)
        add(f"name_id_table_{i}", declared,
            ok, f"last slot id={_u(mm, last + 4, 4)} ordinal={_u(mm, last, 4)}"
                f"/{len(browse)}, walk stopped at {walked}")

    # ---- languages and currencies: a tolerant walk must land EXACTLY on the declared count
    for name, start, step in (("languages", None, _lang_step), ("currencies", None, _cur_step)):
        tab = (t_languages if name == "languages" else t_currencies)(mm)
        if not tab:
            continue
        declared = _u(mm, tab.start - 2, 2)
        o, k = tab.start, 0
        while k < declared + 2:
            nxt = step(mm, o)
            if nxt is None:
                break
            o, k = nxt, k + 1
        add(name, declared, k == declared,
            f"tolerant walk reached {k}, then stopped; our parser reads {tab.n}")
    return out


def _lang_step(mm, o):
    """One language record, tolerating a ZERO-LENGTH OtherName -- which is the only reason
    `lookups._language_at` stops at slot 77 ('Malayalam'). Same failure as the competition
    table's empty code field on cid 172 'Welsh First Division'."""
    p = o + 6
    for _ in range(2):                        # Name, then OtherName
        ln = _u(mm, p, 4)
        if ln > 200:
            return None
        p += 4 + ln
    return p + 3


def _cur_step(mm, o):
    """One currency record, with NO uid range gate -- `lookups._currency_at` rejects
    `uid > 4096` and so stops at slot 94, 'Macao Pataca' (uid 51535). The fourth uid range
    gate in this codebase to cut a table short; see reference.py on the other three."""
    ln = _u(mm, o + 2, 4)
    if ln > 200:
        return None
    return o + 2 + 4 + ln + 4


# ---------------------------------------------------------------------------- discovery
# Can the header convention FIND tables we have not located? Partly -- and the measured
# funnel is the honest answer, because every stage below was tried on its own first and the
# early ones are nowhere near selective enough to use (frem-2023-07-02):
#
#   566,078   an 8-byte 0xFF sentinel somewhere in the file
#   245,929   + a plausible count flush against it
#        39   + count * stride landing exactly on the NEXT sentinel
#        24   + the same (count, stride) in all 27 saves of the career
#        12   + sharing a section's drift with at least one other table
#
# Two traps worth stating, both measured rather than reasoned:
#
# REQUIRING THE RUN TO BE EXACTLY 8 IS WRONG. The sentinel IS 8 bytes, but the record in
# front of it can end in 0xFF of its own, making the run 9 or 10. Tightening stage 0 to
# "exactly 8" drops the currency table and the first-name id-table -- 2 of the 9 tables we
# already know. Match the LAST 8 bytes of a run of >= 8, never the run length.
#
# STAGE 2 ONLY SEES FIXED-WIDTH TABLES with no internal sentinel. Competitions, stadiums,
# languages, currencies and both name id-tables all have a real header and are all invisible
# to it (variable-length records, or free slots that are themselves 0xFF). So a miss here is
# not evidence that a table has no header.
#
# And the funnel does NOT terminate in certainty: of the 12 survivors on Frem, 5 are the
# award records at ~13.71M, where `count * stride` is a numeric accident and the bytes are
# plainly length-prefixed strings ("Players' Team of the Year"). A record-shape check is
# still the last word; this only says WHERE to look.

def discover(mm, min_count=8, min_stride=3, max_stride=4096):
    """[(start, header_width, count, stride)] for every self-validating fixed-width table.

    Self-validating means: an 8-byte 0xFF sentinel, a count flush against it, and
    `count * stride` landing EXACTLY on the next sentinel. That last condition is what makes
    the result worth printing -- a count on its own is one coincidence away from noise.
    """
    buf = np.frombuffer(mm, dtype=np.uint8)
    d = np.diff(np.concatenate(([0], (buf == 0xFF).view(np.int8), [0])))
    runs = [(int(a), int(b)) for a, b in
            zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)) if b - a >= 8]
    out = []
    for i, (_a, b) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(mm)
        for w in (4, 2):
            n = int.from_bytes(mm[b:b + w], "little")
            if not (min_count <= n <= 5_000_000):
                continue
            span = nxt - (b + w)
            if span > 0 and span % n == 0 and min_stride <= span // n <= max_stride:
                out.append((b + w, w, n, span // n))
                break
    return out


def discover_report(saves):
    """Run `discover` over every save and keep only what survives BOTH cross-save filters.

    Keying on (count, stride) rather than on the offset is not a convenience -- a first
    attempt keyed on the offset and found ZERO stable candidates in either career, because
    every section drifts per save (23,584 bytes across Frem's 27 saves for the attribute
    section, 84,317 for the reference section). The shape travels; the address does not.

    The second filter is the sharper one: tables in the same section drift by the SAME
    amount, so a candidate whose drift value is shared by nothing else is in a different
    place in every save and is arithmetic, not a table.
    """
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for sv in saves:
        career = os.path.basename(os.path.dirname(sv))
        with open(sv, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for start, w, n, stride in discover(mm):
                per[career][(n, stride, w)].append(start)
            mm.close()
    n_by = collections.Counter(os.path.basename(os.path.dirname(s)) for s in saves)
    for career, d in per.items():
        total = n_by[career]
        stable = {k: v for k, v in d.items() if len(v) >= total}
        sections = collections.defaultdict(list)
        for (n, stride, w), starts in stable.items():
            sections[max(starts) - min(starts)].append((min(starts), n, stride, w))
        print(f"\n=== {career}: {len(d)} shapes seen, {len(stable)} in all {total} saves")
        for drift, items in sorted(sections.items(), key=lambda kv: -len(kv[1])):
            if len(items) < 2:
                continue
            print(f"  section drift {drift:,} -- {len(items)} tables move together:")
            for lo, n, stride, w in sorted(items):
                print(f"     @{lo:>12,}  {n:>7,} x {stride:>4}B = {n * stride:>10,} B  u{w * 8}")
        lone = sum(len(v) for v in sections.values() if len(v) < 2)
        print(f"  ({lone} discarded: drift value shared by nothing else)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--discover" in sys.argv:
        discover_report(args or sorted(glob.glob(os.path.expanduser("~/fm-saves/*/*.fms"))))
        return 0
    if "--confirm" in sys.argv:
        saves = args or sorted(glob.glob(os.path.expanduser("~/fm-saves/*/*.fms")))
        tally = {}
        for sv in saves:
            with open(sv, "rb") as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                for name, declared, ok, detail in confirm(mm):
                    print(f"  {'ok ' if ok else 'BAD'} {os.path.basename(sv):<26} "
                          f"{name:<20} declared {declared:<8} {detail}")
                    tally.setdefault(name, []).append((ok, declared))
                mm.close()
        print(f"\n=== {len(saves)} saves ===")
        for name, rs in sorted(tally.items()):
            good = sum(1 for ok, _d in rs if ok)
            print(f"  {good}/{len(rs)} confirmed  {name:<20} "
                  f"declared counts seen: {sorted({d for _o, d in rs})}")
        return 0 if all(ok for rs in tally.values() for ok, _d in rs) else 1
    if "--all" in sys.argv:
        saves = sorted(glob.glob(os.path.expanduser("~/fm-saves/*/*.fms")))
        tally = {}
        for sv in saves:
            for t, gap, vals, hits in report(sv, verbose=False):
                key = (t.name, verdict(t, gap, vals).split("[")[0].strip())
                tally[key] = tally.get(key, 0) + 1
        print(f"\n\n=== across {len(saves)} saves: which (table, hit-set) recurs ===")
        for (name, v), k in sorted(tally.items()):
            print(f"  {k:>3}/{len(saves)}  {name:<20} {v}")
        return 0
    save = args[0] if args else os.path.expanduser("~/fm-saves/frem/frem-2023-07-02.fms")
    if not os.path.exists(save):
        print(f"SKIP: {save} not found")
        return 0
    report(save)
    return 0


if __name__ == "__main__":
    sys.exit(main())
