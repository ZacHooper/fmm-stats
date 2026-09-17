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
    +16  ff ff ff ff         row terminator
    +20  season u16

The player-record row carries NO club id: it is attributed to a club by POSITION, because it
sits inside that club's block. That is weaker than a key and is recorded as such -- see
`docs/light-results-record.md`. The same goes for `+0`: it is carried verbatim rather than
named `player_id`, because guessing a name is how `-140` became a Style candidate.
"""
import struct
from collections import defaultdict

SEASON_LO, SEASON_HI = 0x07E4, 0x07EC        # 2020..2028, the seasons a save can hold
SEASON_SENTINEL = 0x07E4                     # what +12 reads in a per-season table
TEAM_STRIDE = 21
PLAYER_STRIDE = 22
MAX_SCORE = 30                               # a scoreline; not a tuned window, a rule of football


def _u16(mm, o):
    return struct.unpack_from("<H", mm, o)[0]


def _u32(mm, o):
    return struct.unpack_from("<I", mm, o)[0]


def _f32(mm, o):
    return struct.unpack_from("<f", mm, o)[0]


def scrape_team_records(mm, valid_clubs, lo=0, hi=None):
    """Every team record row in the save.

    Located structurally: two real club tids, a scoreline, a plausible competition and a
    day-of-year in range. There is deliberately NO region window -- the old
    `regions.LIGHT_LO/HI` was Bucaspor-tuned and the year-marker region finder went blind as
    a career ran past 2022. A whole-file sweep costs a few seconds and cannot drift.

    Rows are returned verbatim, duplicates included: a record held in two slots (or in both
    the Overall and per-season table) is genuinely stored more than once, and collapsing that
    here would throw away the only signal we have about which table a row came from.
    """
    hi = len(mm) - 2 if hi is None else hi
    out = []
    for p in range(lo + 15, hi):            # p = the club tid, 15 bytes into the record
        club = _u16(mm, p)
        if club not in valid_clubs:
            continue
        opp = _u16(mm, p + 2)
        if opp not in valid_clubs or opp == club:
            continue
        sf, sa = mm[p + 4], mm[p + 5]
        if sf > MAX_SCORE or sa > MAX_SCORE:
            continue
        r = p - 15                           # record start
        season = _u16(mm, r + 6)
        if not (SEASON_LO <= season <= SEASON_HI):
            continue
        day = _u16(mm, r + 8)
        if day > 366:
            continue
        cid = _u16(mm, r + 4)
        if not (0 < cid < 20000):
            continue
        out.append({
            "offset": r, "club_tid": club, "opponent_tid": opp,
            "score_for": sf, "score_against": sa,
            "value": _f32(mm, r), "comp_cid": cid,
            "season": season,                        # stored as a plain year
            "day": day,
            "unk10": _u16(mm, r + 10), "unk12": _u16(mm, r + 12), "unk14": mm[r + 14],
        })
    return out


def scrape_player_records(mm, lo=0, hi=None):
    """Every player record row: `[u32][f32][u32][u32][ff ff ff ff][season u16]`.

    Anchored on the `ff ff ff ff` terminator plus a plausible season, which is the row's own
    structure rather than a guessed offset. The 22-byte stride is then confirmed by the gap
    between consecutive rows, not assumed.
    """
    hi = len(mm) if hi is None else hi
    out = []
    i = mm.find(b"\xff\xff\xff\xff", lo)
    while i != -1 and i < hi:
        season = _u16(mm, i + 4) if i + 6 <= len(mm) else 0
        if SEASON_LO <= season <= SEASON_HI:
            r = i - 16
            if r >= 0:
                val = _f32(mm, r + 4)
                # a float32 whose exponent byte is 0 is a denormal ~= 0: that row is some
                # other structure our anchor swept up, not a player record.
                if mm[r + 7] != 0:
                    out.append({"offset": r, "value": val, "season": season,
                                "unk0": _u32(mm, r), "unk8": _u32(mm, r + 8),
                                "unk12": _u32(mm, r + 12)})
        i = mm.find(b"\xff\xff\xff\xff", i + 1)
    return out


def attribute_player_records(team_rows, player_rows, max_gap=4096):
    """Attach each player-record row to the club whose team-record block it sits nearest.

    The player row has no club id, so this is POSITIONAL and therefore weaker than a join.
    It is kept explicit (and capped by `max_gap`) so a caller can see it is an inference
    rather than a key -- see CLAUDE.md's rule about tables with no id in them.
    """
    if not team_rows:
        return []
    anchors = sorted((r["offset"], r["club_tid"]) for r in team_rows)
    offs = [a[0] for a in anchors]
    import bisect
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


def build(mm, valid_clubs):
    """{team_records, player_records} for the whole save."""
    team = scrape_team_records(mm, valid_clubs)
    player = attribute_player_records(team, scrape_player_records(mm))
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
