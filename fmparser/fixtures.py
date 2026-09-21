#!/usr/bin/env python3
"""`fix_man.dat` — the world fixture list, from the save's zstd archive.

26,954 matches across 1,751 clubs on `frem-2026-06-11`, against the 275 our 25-byte
`matchslots` table resolves and the ~60 of our own that `matches.py` parses. It is the
largest single thing in the archive and the answer to four of TODO #4's dead ends. The
container is `fmparser/archive.py` (shape D in `docs/parser-architecture.md`); this is the
member's own record.

WHAT THIS CAN AND CANNOT BE USED FOR
------------------------------------
**It is a two-calendar-year rolling window, and it is NOT a history.** Both segments are
always the current and the previous calendar year, so a 2026 save knows nothing about 2021
and no amount of reading it will produce the early career. It ENRICHES the snapshot it came
from. See `docs/archive-coverage.md` — that fact is what turned almost every "can the archive
replace our parser?" answer from *replace* into *augment*.

**It is mostly, but not only, matches already played.** `archive-coverage.md` originally said
"already played, not a forward fixture list" and that is an over-claim from too few saves.
Measured 2026-09-20 against each save's own date: 0 future rows on frem-2021-07-01 and
frem-2023-07-02, exactly 1 on frem-2025-06-10 and frem-2026-06-11 (the singleton below), but
**619 of 29,471 (2.1%) on bucaspor-2023-05-20**, running up to a month ahead. So a forward
schedule IS present mid-season; it is simply small next to the played rows, and it was absent
from the end-of-June saves that the original claim was checked on.

The corollary is the opportunity: we keep 27 snapshots, each carrying ~18 months of world
results, and consecutive snapshots are far closer together than that, so a union across the
archive would cover the whole career with overlap rather than holes. That union is not built
here.

TWO FIELDS ARE DELIBERATELY NOT EMITTED
---------------------------------------
**Scores.** `+6` and `+11` read the goals correctly on 282 of 285 ground-truth rows, and that
is not good enough, because the failure is structural rather than statistical: the ten bytes
after the opener are a VARIABLE-SHAPE block and the one Frem mismatch shows it directly.

    plain (works):    01 14 ff ff ff ff  02 ff ff ff ff  01 ff ff ff ff   -> 2-1
    frem 2023-02-22:  01 14 ff ff ff ff  00 00 ff 00 ff  00 01 ff 01 ff   -> reads 0-0, store says 0-1

So `+6/+11` is a reading that happens to be right whenever the block takes its plain shape --
most likely the other shape carries extra time, penalties or an aggregate. A field that is
right 99% of the time and wrong for a reason we cannot state is worse than no field, because
nothing downstream can tell which 1% it has. The bytes are declared UNKNOWN and carried
nowhere.

**Competition.** No competition field is identified in this record. Every fixture's
competition is unknown from the record alone -- the same gap the 25-byte table has.

**Competition, still.** No competition field is identified in this record, and that is the
one gap that actually costs something -- see `round` below for how far you can get without it.

THE ROUND COUNTER AT +78 -- DECODED 2026-09-21, CORRECTING THIS MODULE
----------------------------------------------------------------------
This section used to say the counter was not decodable: "read as a u32 it takes 135 distinct
values up to 67,240,195, and read as a u8 it takes 47 with 255 the single most common -- but
bytes +79..81 are non-zero on 5,551 of 26,954 records, so it is not a u8 followed by padding
either. Neither reading is clean."

Every measurement there is correct and the conclusion is wrong. The error was assuming the
four adjacent bytes are one field, so the only choices on offer were "u8 plus padding" or
"u32". They are FOUR INDEPENDENT FIELDS: `+78` is the round, and `+79`/`+80`/`+81` are three
separate small-valued columns (8, 4 and 2 distinct values respectively, mostly zero, still
unidentified). Non-zero neighbours never argued against a u8 -- they only argued against
PADDING, which is a different claim.

`+78` is a matchday counter WITHIN a competition, 0-45 plus 255, verified against our own
matches where the competition IS labelled: our 3F Superliga rows run 0..21 and then restart
for the post-split phase, our Friendlies are all 255, and a Sydbank Pokalen tie carries 2 --
its own competition's round 2, not the league's. So the counter does not identify the
competition; it counts within whichever one the match belongs to.

That is still enough to reconstruct a league table with no competition field in the data --
see docs/TODO.md. The round separates matchdays, a >30-day gap inside one round number
separates the regular phase from the post-split phase, and a league round is a PERFECT
MATCHING over the division's clubs (every club exactly once), which a cup tie can never join
because it duplicates a club. Measured on the Danish top flight: exactly 192 matches and 32
per club in all five seasons the archive reaches, cross-checked 12/12 against the save's own
final positions.

WHAT IS PROVEN
--------------
STRIDE 92, from a gap histogram of the `[u8][0x14][4 x FF]` opener: 26,951 of 26,953 gaps are
exactly 92 on `frem-2026-06-11`.

SEGMENTS THAT TILE EXACTLY. The openers fall into MORE THAN ONE residue class mod 92, so the
member is a series of grids rather than one. Splitting on the residue change, every segment
satisfies `record_count * 92 == segment_span` exactly, on six saves across both careers. That
is the extent test, and it is the table's own invariant rather than a tuned constant.

GROUND TRUTH: every `mart.club_matches` row for the managed club, both careers, five saves --
**282 of 285 in-window rows match exactly on date, home tid, away tid and both scores; the 3
that disagree do so only on the score; 0 disagree on clubs or date.** Rows outside the
two-year window are simply absent: 51/51 of our 2025-26 matches present, 0/143 of 2021-24.

**That "0 disagree on date" was only true once the day-of-year base was right, and it was NOT
right when this module first shipped.** The field is one-indexed; `ymd_from` is zero-indexed;
every emitted date was a day late. It went unnoticed because the original check matched rows
BY date, so a uniform shift could not show up as a mismatch -- it just silently matched fewer
rows. Re-measured 2026-09-21 by joining on (opponent, score) instead and letting the date
float: 51 of 51 rows on frem-2026-06-29 and 60 of 60 on bucaspor-2023-03-25 needed exactly
-1 day, with no other offset represented. See `DAY_BASE`.

**HOME-FIRST.** `matchslots.py`'s 25-byte table is away-first and mis-orients one row of every
repeated club pair; this one got venue right on all 282.
"""
from . import archive as A
from . import primitives as P
from . import records as RD
from .schemas.fixtures import (
    DAY_BASE,
    DAY_MASK,
    FIXTURE,
    OPENER,
    STRIDE,
)

MEMBER = "fix_man.dat"
MEMBER_HEADER = 6             # every member's decompressed payload opens [03][01]['tad.']
NO_ROUND = 0xFF           # +78 when the match belongs to no matchday (friendlies)


def segments(blob):
    """[(start, count)] for each grid in the member, from the member's own structure.

    The openers occupy more than one residue class mod 92, and a change of residue is a change
    of grid. Each segment TILES EXACTLY -- `count * STRIDE == span` -- which is the table's own
    invariant and the reason no tuned gap threshold appears here.

    **That invariant is VACUOUS at n = 1**, and this save has such a case.
    `save-archive.md` reports frem-2026-06-11 as two segments of 7,721 and 19,232; the walk
    finds a THIRD, of one record, at offset 710,558, alone in the 38 KB between them that the
    write-up lists as unidentified. The two readings are reconcilable: the same write-up's gap
    histogram counts 26,951 of 26,953 gaps at exactly 92, and 26,953 gaps means 26,954
    records, which is 7,721 + 19,232 + 1. The singleton is the pair of non-92 gaps. The
    segment table is one record short, not the histogram.

    It is KEPT rather than filtered, because filtering on segment SIZE would be a guess, and
    the caller's `valid_clubs` gate is a real discriminator that drops it anyway -- neither tid
    277 nor 867 resolves to a club we can name.

    What the singleton IS remains unknown. The obvious guess is wrong: on frem-2026-06-11 it
    is dated day 162, the save's own date, which invites "the match being played today" -- but
    frem-2025-06-10 has a singleton too and it is dated **2026-03-26**, nine months out. Three
    of five saves measured carry exactly one row dated after the save date and in each case it
    is the singleton, so whatever these are, they are not ordinary fixtures and they do not
    belong to either grid.
    """
    hits = []
    i = MEMBER_HEADER
    n = len(blob)
    while i + STRIDE <= n:
        if blob[i + 1] == OPENER and blob[i + 2:i + 6] == b"\xff\xff\xff\xff":
            hits.append(i)
            i += STRIDE
        else:
            i += 1
    if not hits:
        return []
    out, start, prev = [], hits[0], hits[0]
    for h in hits[1:]:
        if h - prev != STRIDE:
            out.append((start, (prev - start) // STRIDE + 1))
            start = h
        prev = h
    out.append((start, (prev - start) // STRIDE + 1))
    return out


def fixtures(mm, valid_clubs=None):
    """[{home_tid, away_tid, date, year, round, ...}] for every world match in the save's archive.

    `valid_clubs` should be the set of tids we can NAME -- `extract.py` passes the keys of its
    club index, ~4,705 clubs on frem-2026-06-11. Do NOT pass the info spine's
    `{p["club_tid"]}` set: that is "clubs with at least one player in the spine", and it drops
    a third of the real fixtures (19,688 of 26,954). Without a set, every row is kept.

    Raises `archive.ArchiveError` if the save carries no archive or if the
    `archive` extra is not installed -- both of which the caller should treat
    as "no fixtures", not as a parse failure.
    """
    blob = A.extract(mm, MEMBER)
    out = []
    wanted_fields = (
        "home_tid", "away_tid", "day_raw", "year", "round",
        "home_goals", "away_goals", "home_pens", "away_pens",
        "stage_key", "seq_id", "season_year",
        "stage_attr_76", "stage_attr_77", "stage_attr_83",
    )
    for start, count in segments(blob):
        for k in range(count):
            base = start + k * STRIDE
            r = RD.read_fields(blob, FIXTURE, base, wanted_fields)
            if valid_clubs is not None and (r["home_tid"] not in valid_clubs
                                            or r["away_tid"] not in valid_clubs):
                continue
            hg = None if r["home_goals"] == 0xFF else r["home_goals"]
            ag = None if r["away_goals"] == 0xFF else r["away_goals"]
            hp = None if r["home_pens"] == 0xFF else r["home_pens"]
            ap = None if r["away_pens"] == 0xFF else r["away_pens"]
            rnd = None if r["round"] == NO_ROUND else r["round"]
            rnd_idx = None if r["stage_attr_77"] == 0xFF else r["stage_attr_77"]
            d_day = (r["day_raw"] & DAY_MASK) - DAY_BASE
            out.append({
                "home_tid": r["home_tid"],
                "away_tid": r["away_tid"],
                "date": P.ymd_from(r["year"], d_day),
                "year": r["year"],
                "round": rnd,
                "home_goals": hg,
                "away_goals": ag,
                "home_pens": hp,
                "away_pens": ap,
                "stage_key": r["stage_key"],
                "seq_id": r["seq_id"],
                "season_year": None if r["season_year"] == 0 else r["season_year"],
                "stage_index": r["stage_attr_76"],
                "round_index": rnd_idx,
                "subr": r["stage_attr_83"],
            })
    return out


def summary(mm):
    """Counts for a quick sanity read, without building the whole list."""
    blob = A.extract(mm, MEMBER)
    segs = segments(blob)
    years = {}
    for start, count in segs:
        y = P.u16(blob, start + FIXTURE.field("year").offset)
        years[y] = years.get(y, 0) + count
    return {"segments": len(segs), "records": sum(c for _, c in segs), "by_year": years}
