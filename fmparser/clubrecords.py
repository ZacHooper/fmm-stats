#!/usr/bin/env python3
"""
Club history records -- the "Club History" screens, per club.

WHAT THIS REGION ACTUALLY IS, and why it matters. `fmparser/lightresults.py` has been
reading this same region as a list of simulated match RESULTS since 2026-07. It is not one.
It is the **club records** tables -- Team Records (biggest win, biggest defeat, highest
scoring match, ...) and Player Records (most goals in a season, youngest player, highest
transfer fee, ...). Identified 2026-09-17 against in-game screenshots of Southampton's Club
History, and the identification is exact:

    decoded  vs Newcastle United  3-6  day=135  -> "Highest scoring match, 16/5/2026"
    decoded  vs Sheffield United  4-0  day=227  -> "Biggest win, 16/8/2025"
    decoded  vs Manchester City   0-5  day=234  -> "Biggest defeat, 23/8/2025"
    decoded  float 6182 / 13212           -> "Youngest 16 yrs 338 days" / "Oldest 36 yrs 63 days"
                                             (= years*365.25 + days, exact)

Everything that made `lightresults` look like a broken results parser follows from this:

  * a club has ~12 rows because there are ~12 record CATEGORIES, not because a ring buffer
    ate its fixtures;
  * "each fixture is stored in >=2 copies" is the two-slot pattern -- "Highest scoring match"
    and "Highest scoring LEAGUE match" are the same game in adjacent slots. A game that is a
    record in both the Overall and the per-season table appears 4x;
  * the rows are not in date order because they are in CATEGORY order;
  * standings computed from these rows read 5-13 games played, because they were computed
    from record-holding matches.

So: this module does NOT give you a fixture list, and nothing here should be used to build
one. What it does give, for every club in the save, is the club's record book.

RECORD LAYOUTS
--------------
Team record, 21 bytes. **The club tid is at the END of the record, not the start** -- this
cost two wrong readings before the measurement settled it, so it is worth stating plainly:

    +0   value f32           the metric the record is sorted on, and it VARIES BY CATEGORY:
                             total goals for "highest scoring" (3-6 -> 9.0), goal difference
                             for biggest win/defeat (4-0 -> +4.0, 0-5 -> -5.0). Do not assume
                             one meaning.

                             CRUCIALLY, some categories are STREAKS, not matches -- "most
                             games without a win", "most consecutive defeats" and friends.
                             For those the value is the streak length and the opponent/score
                             fields are leftover bytes with no meaning. Southampton's rows
                             carry 11.0, 8.0, 7.0 and 4.0, which are exactly its screenshot
                             streaks (11 without a win, 8 without defeat, 7 consecutive
                             defeats, 4 consecutive wins). So: NEVER read opponent+score
                             without knowing the category, and we cannot yet name categories
                             -- `unk10` is the likeliest carrier and is unnamed on purpose.
    +4   comp_cid u16
    +6   season u16          the season the record was set, in the OVERALL table. In the
                             per-season table the season is implied, and this reads a
                             constant 0x07E4 sentinel. See `SEASON_SENTINEL`.
    +8   day u16             day-of-year, 0-based
    +10  UNKNOWN u16         observed 1, 4, 5 -- probably the table/category, not decoded
    +12  UNKNOWN u16         observed ff ff, a terminator
    +14  UNKNOWN u8          observed 1, 2
    +15  club_tid u16        the club whose record book this is
    +17  opponent_tid u16
    +19  score_for u8        from `club_tid`'s perspective
    +20  score_against u8

How that was settled, since "the values look right" would have passed either way. A record
held in two slots is stored TWICE in adjacent 21-byte rows. Anchoring on the tid pair and
reading the value/cid/day FORWARD is correct on the first copy and silently reads the NEXT
record's fields on the second -- so half the rows come out plausible and wrong. Reading
BACKWARD from the tid pair is correct on both copies, 12 sites out of 12, checked against
five record matches whose dates are known from screenshots. This is the same column-offset
trap CLAUDE.md records from the career-history table.

Player record, 22 bytes:

    +0   UNKNOWN u32         plausibly the player, but unverified -- see below
    +4   value f32           the record value. Counts (17 goals), ratings (7.37), ages in
                             DAYS (6182 = 16y338d) and money (44,958,444 -> "£45M") all share
                             this field, which is why its magnitude histogram has a hole
                             between 100 and 1,000.
    +8   UNKNOWN u32
    +12  UNKNOWN u32
    +16  UNKNOWN u32         usually ff ff ff ff, but NOT a terminator -- slots 1-2 carry
                             a real value here, so gating on it silently drops the two
                             categories the game lists first
    +20  season u16

The player-record row carries NO club id: it is attributed to a club by POSITION, because it
sits inside that club's block. That is weaker than a key and is recorded as such -- see
`docs/light-results-record.md`. The same goes for `+0`: it is carried verbatim rather than
named `player_id`, because guessing a name is how `-140` became a Style candidate.
"""
import struct

from .core import primitives as P
from . import records as RD
from .core import F32, Field, Record, U8, U16, U32
from collections import defaultdict

SEASON_LO, SEASON_HI = 0x07E4, 0x07EC        # 2020..2028, the seasons a save can hold
SEASON_SENTINEL = 0x07E4                     # what the season field reads in a per-season table
TEAM_STRIDE = 21
PLAYER_STRIDE = 22
BLOCK = 12                                   # categories per table, both tables
MAX_SCORE = 30                               # a scoreline; not a tuned window, a rule of football
NO_OPPONENT = 0xFFFF                         # categories 1-2 carry no match
NO_SCORE = 0xFF

# The record CATEGORIES, in the order the game stores them -- which is the order the Club
# History screen lists them, verified slot-for-slot against screenshots of Southampton on
# frem-2026-06-11. The slot index IS the category; there is no category id in the record.
#
# `kind` says which fields of the row mean anything, and this matters more than it looks:
#   match  -- opponent/score/day/cid are real, `value` is the sort metric (TOTAL goals for
#             the "highest scoring" pair, GOAL DIFFERENCE for the win/defeat pairs)
#   table  -- a league position; opponent is 0xFFFF and the score bytes are 0xFF
#   streak -- `value` is a run length and the opponent/score/day bytes are LEFTOVER. Reading
#             them as a fixture is how "Leicester 4-2" ended up carrying the values 5 and 3,
#             which are really "5 games without a win" and "3 consecutive defeats".
TEAM_CATEGORIES = [
    ("highest_league_position", "table"),
    ("lowest_league_position", "table"),
    ("highest_scoring_match", "match"),
    ("highest_scoring_league_match", "match"),
    ("biggest_win", "match"),
    ("biggest_league_win", "match"),
    ("biggest_defeat", "match"),
    ("biggest_league_defeat", "match"),
    ("most_consecutive_wins", "streak"),
    ("most_games_without_defeat", "streak"),
    ("most_games_without_win", "streak"),
    ("most_consecutive_defeats", "streak"),
]

# Player records. `unit` is what `value` is counted in -- confirmed against the game:
# "16 yrs, 338 days" is stored as 6182 = years*365.25 + days, and "GBP 31M" as 31,156,734
# (money is DISPLAYED rounded, per CLAUDE.md).
PLAYER_CATEGORIES = [
    ("most_goals_in_a_season", "count"),
    ("most_league_goals_in_a_season", "count"),
    ("most_assists_in_a_season", "count"),
    ("highest_average_rating_in_a_season", "rating"),
    ("most_player_of_match_in_a_season", "count"),
    ("most_bookings_in_a_season", "count"),
    ("most_red_cards_in_a_season", "count"),
    ("most_appearances_in_a_season", "count"),
    ("youngest_player", "days"),
    ("oldest_player", "days"),
    ("highest_transfer_fee_paid", "money_gbp"),
    ("highest_transfer_fee_received", "money_gbp"),
]


# THE TWO ROWS, declared.
#
# Field order here is OUTPUT order, not offset order -- `season` sits at +20 in the player row
# and is emitted before the three unknowns, which is how `player_records.json` has always been
# written and it is written without `sort_keys`. Declaration order is free; offsets are not.
#
# The team row's `club_tid` is in its own group because it CANNOT be read per row: slots 1-2
# are the league-position categories and carry 0xFFFF there, so the club is the value the
# other ten slots agree on. Requiring row 1 to name the club finds nothing at all, which is
# how that was caught. The block reads it through `TEAM_ROW.field("club_tid").offset` and
# decides the club itself.
TEAM_ROW = Record("club_team_record", TEAM_STRIDE, [
    Field(0,  4, "value",         F32, group="row"),
    Field(4,  2, "comp_cid",      U16, group="row"),
    Field(6,  2, "season",        U16, group="row"),
    Field(8,  2, "day",           U16, group="row"),
    Field(10, 2, "unk10",         U16, group="row"),
    Field(12, 2, "unk12",         U16, group="row"),
    Field(14, 1, "unk14",         U8,  group="row"),
    Field(15, 2, "club_tid",      U16, group="club",
          note="0xffff on slots 1-2; the block decides the club, not the row"),
    Field(17, 2, "opponent_tid",  U16, group="match"),
    Field(19, 1, "score_for",     U8,  group="match"),
    Field(20, 1, "score_against", U8,  group="match"),
])

PLAYER_ROW = Record("club_player_record", PLAYER_STRIDE, [
    Field(0,  4, "player_tid", U32, note="verified 8/8 against Southampton's Club History"),
    Field(4,  4, "value",      F32),
    Field(20, 2, "season",     U16),
    Field(8,  4, "unk8",       U32),
    Field(12, 4, "unk12",      U32),
    # NOT a terminator, though it reads ff ff ff ff in most rows: slots 1-2 of Southampton's
    # block carry 1a 02 00 00, so gating on it drops the two categories the game lists FIRST.
    Field(16, 4, "unk16",      U32),
])


def scrape_team_records(mm, valid_clubs, lo=0, hi=None):
    """Every team record in the save, as whole 12-slot BLOCKS.

    Blocks, not loose rows, because the slot index IS the category: there is no category id
    in the record, so a row is only interpretable as part of a run of 12. A club has one
    block per table (Overall, plus one per season it has played).

    Located structurally -- a run of 12 records on the 21-byte stride sharing one club tid --
    with no region window. The old `regions.LIGHT_LO/HI` was Bucaspor-tuned and the
    year-marker region finder went blind as a career ran past 2022; a whole-file sweep costs
    a few seconds and cannot drift.
    """
    hi = (len(mm) - TEAM_STRIDE * BLOCK) if hi is None else hi
    out = []
    r = lo
    while r < hi:
        # A block is 12 structurally-valid rows that agree on one club. Slots 1-2 are the
        # league-position categories and carry NO club: both the club and opponent fields
        # read 0xFFFF. So the club is the one every OTHER slot agrees on -- requiring row 1
        # to name the club finds nothing at all, which is how this was caught.
        if not all(_team_row_ok(mm, r + n * TEAM_STRIDE, valid_clubs) for n in range(BLOCK)):
            r += 1
            continue
        _club_off = TEAM_ROW.field("club_tid").offset
        tids = [P.u16(mm, r + n * TEAM_STRIDE + _club_off) for n in range(BLOCK)]
        named = [x for x in tids if x != NO_OPPONENT]
        if len(named) < BLOCK - 2 or len(set(named)) != 1:
            r += 1
            continue
        club = named[0]
        if club not in valid_clubs:
            r += 1
            continue
        for k in range(BLOCK):
            o = r + k * TEAM_STRIDE
            cat, kind = TEAM_CATEGORIES[k]
            row = {"offset": o, "club_tid": club, "slot": k, "category": cat, "kind": kind}
            row.update(RD.read_group(mm, TEAM_ROW, o, "row"))
            fixture = RD.read_group(mm, TEAM_ROW, o, "match")
            # Only a `match` category has a real fixture attached. For `table` the opponent
            # is 0xFFFF and the scores 0xFF; for `streak` they are leftover bytes that WILL
            # look like a plausible fixture if you let them.
            if (kind == "match" and fixture["opponent_tid"] != NO_OPPONENT
                    and fixture["score_for"] != NO_SCORE
                    and fixture["score_against"] != NO_SCORE):
                row.update(fixture)
            else:
                row.update(opponent_tid=None, score_for=None, score_against=None)
            out.append(row)
        r += BLOCK * TEAM_STRIDE
    return out


def _team_row_ok(mm, r, valid_clubs):
    """Structural test for one team-record row: a real club, a plausible season and day."""
    if r < 0 or r + TEAM_STRIDE > len(mm):
        return False
    if not (SEASON_LO <= P.u16(mm, r + 6) <= SEASON_HI):
        return False
    if P.u16(mm, r + 8) > 366:
        return False
    cid = P.u16(mm, r + 4)
    return 0 <= cid < 20000


def scrape_player_records(mm, valid_players=None, lo=0, hi=None):
    """Every player record, as whole 12-slot blocks. Same reasoning as the team records.

    `+0` is the PLAYER TID -- verified 8/8 against the game: Southampton's block resolves to
    Samuel Dias Lino (most goals AND most league goals, which is why slots 1 and 2 carry the
    same tid), Joe Aribo, Dujon Sterling, James Ward-Prowse, Jan Bednarek, Fraser Forster,
    Tino Livramento and Benjamin Nygren.
    """
    hi = (len(mm) - PLAYER_STRIDE * BLOCK) if hi is None else hi
    out = []
    r = lo
    while r < hi:
        if not _player_row_ok(mm, r, valid_players):
            r += 1
            continue
        if not all(_player_row_ok(mm, r + n * PLAYER_STRIDE, valid_players)
                   for n in range(BLOCK)):
            r += 1
            continue
        for k in range(BLOCK):
            o = r + k * PLAYER_STRIDE
            cat, unit = PLAYER_CATEGORIES[k]
            out.append(RD.read_into(
                {"offset": o, "slot": k, "category": cat, "unit": unit},
                mm, PLAYER_ROW, o))
        r += BLOCK * PLAYER_STRIDE
    return out


def _player_row_ok(mm, r, valid_players=None):
    """Structural test for one player-record row: a real player, a season, a live float.

    NOTE `+16` is NOT a terminator, though it reads `ff ff ff ff` in most rows. Slots 1-2 of
    Southampton's block carry `1a 02 00 00` there, so gating on it drops the two categories
    the game lists FIRST ("most goals", "most league goals"). It is carried as `unk16`.

    The exponent-byte test does the work instead: a float32 whose exponent is 0 is a denormal
    ~= 0, which is exactly what an unrelated small integer looks like read as a float.
    """
    if r < 0 or r + PLAYER_STRIDE > len(mm):
        return False
    if not (SEASON_LO <= P.u16(mm, r + 20) <= SEASON_HI):
        return False
    if mm[r + 7] == 0:
        return False
    if valid_players is not None and P.u32(mm, r) not in valid_players:
        return False
    return True


def attribute_player_records(team_rows, player_rows, max_gap=4096):
    """Attach each player-record block to the club whose team-record block it sits nearest.

    The player row has no club id, so this is POSITIONAL and weaker than a join. It is kept
    explicit (and capped by `max_gap`) so a caller can see it is an inference rather than a
    key -- see CLAUDE.md's rule about tables with no id in them.
    """
    if not team_rows:
        return []
    import bisect
    anchors = sorted((r["offset"], r["club_tid"]) for r in team_rows)
    offs = [a[0] for a in anchors]
    out = []
    for row in player_rows:
        j = bisect.bisect_left(offs, row["offset"])
        best, bestd = None, None
        for k in (j - 1, j):
            if 0 <= k < len(anchors):
                d = abs(anchors[k][0] - row["offset"])
                if bestd is None or d < bestd:
                    best, bestd = anchors[k][1], d
        if best is not None and bestd <= max_gap:
            out.append(dict(row, club_tid=best, club_distance=bestd))
    return out


ZERO_WALL = 4096         # a run this long is real filler, not a gap inside a record


def region(mm):
    """(lo, hi) for the club-records tables, bounded by the file's own structure.

    Both scrapes below used to sweep the whole file: 26 of the ~60 seconds an extraction
    takes, spent looking at 60 MB to read a ~1.3 MB table. Two structural facts fix the
    region without a tuned window:

      lo  the history slab's END. The club-records grid starts within ~200 bytes of it on
          every save tested -- 27 Frem, 2 Bucaspor. On a DAY-ONE save those bytes are already
          there as empty 21-byte rows (club tid 0xFFFF, the 0x07E4 year-2020 sentinel), which
          is why `scrape_team_records` returns nothing at all for that save: the grid is
          preallocated and not yet written, not missing.
      hi  the first run of >= ZERO_WALL zero bytes after `lo` (or capped at lo + 1.5MB,
          as all records finish within ~1.29MB across both careers).

    Verified byte-identical to the whole-file sweep on both careers, day-one and late-career
    saves alike. Raises if the slab can't be located; `build` falls back to the old
    whole-file sweep in that case.
    """
    from . import history as _H              # local: keeps numpy off this module's import path
    lo = _H.slab_bounds(mm)[1]
    hi = mm.find(b"\x00" * ZERO_WALL, lo)
    hi_bound = lo + 1_500_000
    if hi != -1:
        return lo, min(hi, hi_bound)
    return lo, min(len(mm), hi_bound)


def build(mm, valid_clubs, valid_players=None, lo=None, hi=None):
    """{team_records, player_records} for the whole save.

    Bounded by `region()` unless the caller pins `lo`/`hi`. If the slab won't locate we scan
    the whole file exactly as before -- slower, never wrong.
    """
    if lo is None and hi is None:
        try:
            lo, hi = region(mm)
        except Exception as e:                # locator failure -> the old behaviour
            print(f"  NOTE: club-records region not bounded ({e}); scanning the whole file")
            lo, hi = 0, None
    team = scrape_team_records(mm, valid_clubs, lo=lo or 0, hi=hi)
    player = attribute_player_records(
        team, scrape_player_records(mm, valid_players=valid_players, lo=lo or 0, hi=hi))
    return {"team_records": team, "player_records": player}


def summary(mm, valid_clubs):
    """Per-club counts, for a quick sanity read."""
    b = build(mm, valid_clubs)
    per = defaultdict(int)
    for r in b["team_records"]:
        per[r["club_tid"]] += 1
    return {"team_rows": len(b["team_records"]),
            "player_rows": len(b["player_records"]),
            "clubs": len(per)}
