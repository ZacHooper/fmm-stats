#!/usr/bin/env python3
"""
Small reference tables: languages, currencies, nations.

All three sit in the 12.8-14.1 MB reference block alongside stadiums and cities
(fmparser/places.py). Layouts from nyongrand/fmm-editor's FMM26 `Language`, `Currency` and
`Nation`; every one is located STRUCTURALLY, never by a constant offset.

What each is good for:
  * languages resolve the ids on every person record -- staff and players alike carry a
    counted language list (see fmparser/staging.py's `_decode_info` and BUGS #14 Round 4);
  * currencies give an exchange rate per GBP, which is what makes a foreign wage or fee
    comparable;
  * nations give the code, continent, capital CITY and national STADIUM, and replace the
    static NATIONS dict in reference.py with something the save actually asserts. They also
    carry the NATIONAL TEAM block: world ranking, ranking points, a GROWING ranking history,
    the rival nation, and the UEFA coefficients a European campaign is seeded from.

Cross-checks that make these more than plausible:
  * language 7 = English, 10 = German, 31 = Danish -- exactly the ids inferred independently
    from the managers' language lists;
  * Danish Krone = 8.699 and Czech Koruna = 29.81 per GBP -- real rates;
  * Denmark (id 138) -> capital city 58 (Copenhagen) and national stadium 177 (Parken), both
    of which resolve correctly through fmparser/places.py.
"""
import re
import struct

from . import primitives as P
from .schema import F32, Field, Record, U8, U16, U32

_MIN_CHAIN = 20        # consecutive valid records before we believe we found a table


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


def _string(mm, o, n, maxlen=64, allow_empty=False):
    """(text, next_offset) for a [len u32][utf-8] string, or (None, None).

    `allow_empty` admits `ln == 0`. It is off by default because a zero length is a weak
    signature -- four zero bytes are everywhere -- and these parsers double as LOCATORS. It
    is on for exactly one field: a language's `OtherName`, which is genuinely empty for 47 of
    the 124 languages. See `_language_at`.
    """
    if o + 4 > n:
        return None, None
    ln = _u32(mm, o)
    lo = 0 if allow_empty else 1
    if not (lo <= ln <= maxlen) or o + 4 + ln > n:
        return None, None
    try:
        return mm[o + 4:o + 4 + ln].decode("utf-8"), o + 4 + ln
    except UnicodeDecodeError:
        return None, None


class TableCountError(Exception):
    """A count-framed table read fewer records than it declares about itself."""


def _declared_count(mm, start, width=2, min_ff=8):
    """The count this table declares, from the `[>= 8 x 0xFF][count]` frame in front of it.

    Shape A in `docs/parser-architecture.md`, read BACKWARDS: `records.find_framed_count`
    searches forward from a known-good offset, but here the table start is what we already
    have. Returns None if the frame is not there, so a caller can still walk unbounded.

    `>= 8` and never `== 8`: the record before the sentinel can itself end in 0xFF. Measured
    on both careers -- the language frame runs 8 FF and the currency frame 10.
    """
    if start < width + min_ff:
        return None
    i = start - width - 1
    ff = 0
    while i >= 0 and mm[i] == 0xFF:
        ff += 1
        i -= 1
    if ff < min_ff:
        return None
    return _u16(mm, start - 2) if width == 2 else _u32(mm, start - 4)


def _walk(mm, parse, seeds, min_chain=_MIN_CHAIN, declared=None, label=""):
    """Find the longest chain `parse` can walk, then collect the whole table from its start.

    Chaining is the validator: a real record's length fields land exactly on the next record,
    so `min_chain` consecutive successful parses is not something noise produces.
    """
    n = len(mm)
    start = None
    for o in seeds:
        k, p = 0, o
        while k < min_chain:
            rec, nxt = parse(mm, p, n)
            if rec is None:
                break
            p, k = nxt, k + 1
        if k >= min_chain:
            start = o
            break
    if start is None:
        return []
    # Rewind to the true first record. The seed is only the first place the signature
    # matched, which for languages is wherever Name first equals OtherName -- seeding at,
    # say, id 7 would silently drop ids 0-6. Records are variable-length, so step back by
    # finding the record that ends exactly where this one starts.
    while True:
        prev = None
        for cand in range(start - 1, max(-1, start - 200), -1):
            rec, nxt = parse(mm, cand, n)
            if rec is not None and nxt == start:
                prev = cand
                break
        if prev is None:
            break
        start = prev
    # THE WALK IS BOUNDED BY THE TABLE'S OWN DECLARED COUNT, not by "until a parse fails".
    # Those differ in exactly the way that hid two bugs for the life of this parser: a single
    # record the parser wrongly rejects truncates EVERYTHING after it, silently, and the
    # result still looks like a clean table. Languages stopped at 77 of 124 on one empty
    # string; currencies at 94 of 173 on one plausibility gate.
    #
    # Reaching a DIFFERENT declared number is fine -- a new game version may simply ship more
    # languages, and we read what it declares. Falling SHORT of it is a parser bug and raises.
    if declared is None:
        declared = _declared_count(mm, start)
    out, o = [], start
    while declared is None or len(out) < declared:
        rec, nxt = parse(mm, o, n)
        if rec is None:
            break
        out.append(rec)
        o = nxt
    if declared is not None and len(out) != declared:
        raise TableCountError(
            f"{label or parse.__name__}: read {len(out)} records but the table declares "
            f"{declared} (stopped at offset {o}). A record the parser rejects truncates the "
            f"whole table from that point -- fix the reject, do not lower the count.")
    return out


# Nation-less "regional" languages are numbered from a synthetic base rather than given a
# real uid: 1,000,000 for Latin American, then 1,000,001, 1,000,002 ... Bounded above by the
# declared count, so this admits a band, not "any large number".
_REGIONAL_UID_BASE = 1_000_000


# ------------------------------------------------------------------ languages
# [Id u16][Uid u32][len][Name][len][OtherName][NationId u16][Difficulty u8]
# DECLARATIONS ONLY, for the three seeded-chain tables (shape E in
# docs/parser-architecture.md). Each record is `[fixed head][length-prefixed strings][fixed
# tail]`, so neither half is a stride and both are `is_head=True` -- the span is the block,
# not the record. The parsers keep reading these themselves, because their reads are
# interleaved with the plausibility tests that decide whether a candidate IS a record, and
# those tests are LOCATING. What the declarations buy is that the blocks are visible to
# `scripts/audit_records.py` at all: none of these three tables was in it.
LANGUAGE_HEAD = Record("language_head", 6, (
    Field(0, 2, "id", U16, note="what the person record's language list references"),
    Field(2, 4, "uid", U32),
), is_head=True)
LANGUAGE_TAIL = Record("language_tail", 3, (
    Field(0, 2, "nation_id", U16),
    Field(2, 1, "difficulty", U8),
), is_head=True)

CURRENCY_HEAD = Record("currency_head", 2, (
    Field(0, 2, "uid", U16),
), is_head=True)
CURRENCY_TAIL = Record("currency_tail", 4, (
    Field(0, 4, "exchange_rate", F32, note="per GBP"),
), is_head=True)

# The nation head sits BEFORE the first string, so the walk reaches it by stepping backwards
# from the 3-letter code -- `uid` at head+0 and `id` at head+4, which is why the parser reads
# them as `c - 6` and `c - 2`.
NATION_HEAD = Record("nation_head", 6, (
    Field(0, 4, "uid", U32),
    Field(4, 2, "id", U16),
), is_head=True)
NATION_TAIL = Record("nation_tail", 6, (
    Field(0, 2, "continent_id", U16),
    Field(2, 2, "capital_city_id", U16),
    Field(4, 2, "national_stadium_id", U16),
), is_head=True)


def _language_at(mm, o, n):
    if o + 8 > n:
        return None, None
    lid, uid = _u16(mm, o), _u32(mm, o + 2)
    # REGIONAL languages -- "Latin American", "Brazilian" and three more -- belong to no
    # nation, and the save says so twice: a synthetic `uid` from 1,000,000 up and a
    # `nation_id` of 0xFFFF. The old gates (`uid > 100_000`, `0 <= nat <= 4096`) rejected
    # both, which ended the walk at id 119 and cost the last five languages.
    if lid > 4096 or (uid > 100_000 and not
                      _REGIONAL_UID_BASE <= uid < _REGIONAL_UID_BASE + 4096):
        return None, None
    name, p = _string(mm, o + 6, n)
    if not name or not name[0].isupper():
        return None, None
    # OtherName is EMPTY on 47 of the 124 languages -- Malayalam (id 77) is the first, and
    # rejecting it used to end the walk there, costing every language after it.
    other, p2 = _string(mm, p, n, allow_empty=True)
    if other is None or p2 + 3 > n:
        return None, None
    nat, diff = _u16(mm, p2), mm[p2 + 2]
    if not (0 <= nat <= 4096 or nat == P.NO_ID16) or diff > 20:
        return None, None
    return ({"id": lid, "uid": uid, "name": name, "other_name": other,
             "nation_id": nat, "difficulty": diff, "offset": o}, p2 + 3)


def scrape_languages(mm):
    """{language_id: record}. Keyed by the id the person records reference.

    Seeded on a signature unique to this table: Name and OtherName are usually the SAME
    string, so `[len][X][len][X]` back to back is a strong marker. Seeding on "any
    capitalised word" instead does not work -- the save opens with tens of thousands of
    first/last names, so a capped scan never reaches the reference block at all.
    """
    seeds = []
    for ln in range(3, 25):
        pre = re.escape(struct.pack("<I", ln))
        for m in re.finditer(pre + rb"([A-Za-z\x80-\xff]{%d})" % ln + pre + rb"\1", mm[:]):
            if m.start() >= 6:
                seeds.append(m.start() - 6)       # back over [Id u16][Uid u32]
    seeds.sort()
    recs = _walk(mm, _language_at, seeds, label="languages")
    return {r["id"]: r for r in recs}


# ------------------------------------------------------------------ currencies
# [Uid u16][len][Name][ExchangeRate f32]  -- rate is units per GBP
def _currency_at(mm, o, n):
    if o + 6 > n:
        return None, None
    # NO `uid > 4096` GATE. It used to be here as a plausibility test, on the assumption
    # that a currency uid is a small ordinal. It is not: real uids run to 65,045, and Macao
    # Pataca (uid 51,535) is the 95th record -- so the gate did not filter noise, it ended
    # the walk 79 records early. The name and exchange-rate tests below are what validate a
    # record, and they terminate the table on their own at exactly the declared 173.
    uid = _u16(mm, o)
    name, p = _string(mm, o + 2, n)
    if not name or not name[0].isupper() or p + 4 > n:
        return None, None
    rate = struct.unpack("<f", mm[p:p + 4])[0]
    if not (0.0 < rate < 1e7):
        return None, None
    return ({"uid": uid, "name": name, "exchange_rate": round(rate, 6), "offset": o}, p + 4)


def scrape_currencies(mm):
    """{currency_uid: record} with the exchange rate per GBP."""
    seeds = _seed_offsets(mm, rb"[A-Z][A-Za-z ]{3,28} (?:Krone|Peso|Dollar|Pound|Franc|Euro)")
    return {r["uid"]: r
            for r in _walk(mm, _currency_at, (s - 6 for s in seeds if s >= 6), min_chain=10,
                           label="currencies")}


# ------------------------------------------------------------------ nations
# [Uid u32][Id u16][len][Name][00][len][Nationality][00][len][Code]
#   [ContinentId u16][CapitalCityId u16][NationalStadiumId u16] ... (variable tail)
#
# The tail carries a counted language list and up to two national teams, and is NOT walked:
# the head is what we want and mis-stepping the tail would desynchronise the whole table. So
# nations are located individually, by the three-string signature ending in a 3-letter code.
# TWO or three letters. Six nations carry a 2-letter code -- United Kingdom (UK) and the five
# ethnicity pseudo-nations SEA Chinese, Singh Indian, Borneo Malay, West Malay, Tamil Indian --
# and searching only the 3-letter length prefix missed every one of them.
_CODE = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")
_CODE_LENS = (3, 2)
# Continents are a tiny enumeration (Europe is 2). Anything larger is a club or competition
# record whose colour/type bytes happen to sit where the continent id would be -- EXCEPT the
# no-continent sentinel, see `_plausible_continent`.
_MAX_CONTINENT = 6


def _plausible_continent(v):
    """A continent id, or the sentinel that says this nation has no continent.

    17 nations carry `continent_id == 0xFFFF`, and they are not junk: they are the DEFUNCT
    and non-FIFA states -- U.S.S.R., Czechoslovakia, East and West Germany, Yugoslavia, Zaire,
    Upper Volta, Great Britain, Netherlands Antilles, Ireland (Pre-1922). The game keeps them
    so a player can have been born in one. Rejecting the sentinel dropped all 17.
    """
    return v <= _MAX_CONTINENT or v == P.NO_ID16


# The national-team block, immediately after the national stadium id. Offsets relative to it:
#   +1   4 x Color u16 (RGB555)
#   +11  RivalNationId u16        +18  IsRanked u8
#   +19  WorldRanking u16         +21  RankingPoints u16
#   +23  history count u16 (0 for an unranked nation; otherwise it GROWS with career
#        length -- 10 in a 2022 save, 24 by 2026 -- so read the count, never assume it),
#        then that many u16
#   +2 past the history: coefficient count u8, then that many f32
#
# Evidence this is right, none of it needing an external table:
#   * the ranking is very nearly a PERMUTATION -- 186 distinct values over 1..210 across 209
#     ranked nations, which a mis-read field cannot produce;
#   * every rival resolves to a real footballing rivalry: Belgium<->Holland, Brazil<->Argentina,
#     England<->Scotland, Denmark<->Sweden, Portugal<->Spain, Croatia<->Serbia;
#   * coefficients are UEFA-only -- Brazil, Mexico, Peru and Argentina come back empty, while
#     Italy 21.29, Germany 20.0, England 19.71 are real country coefficients;
#   * Russia is rank 0 but keeps 1,463 points (suspended), and non-FIFA territories
#     (Bonaire, Crimea, Reunion, Mayotte, Wallis & Futuna) are 0/0.
# The final coefficient is always 0.0 -- the season in progress.
#
# COEFFICIENT ORDERING — settled against three in-game screenshots, two careers.
#
# The array is the country coefficient history, CHRONOLOGICAL, seq 0 oldest, the newest
# completed season last, and a trailing 0.0 for the season in progress. One entry is appended
# per completed European season.
#
#   * SUM(coefficients) is exactly the in-game "Coef" column. 11/11 nations on a Frem 2026
#     screen (England 197.498, Spain 195.096, Italy 172.009 ...) and 11/11 again on a
#     Bucaspor 2022 screen (Spain 203.568, England 176.853, Turkey 66.225 ...). Two careers,
#     four game-years apart. This is the number European seeding turns on — use it.
#   * A day-1 save (16 Jul 2021) and one from 26 May 2022 are IDENTICAL: no European season
#     completed between them. frem-2025-07-01 and frem-2025-11-30 likewise.
#   * The array is SEEDED WITH REAL HISTORY. In a fresh save England reads
#     [15.25, 16.428, 16.785, 13.571, 14.25, 14.928, 20.071, 22.642, 18.571, 24.357] —
#     England's actual 2011/12-2020/21 coefficients, summing to the 176.853 the game shows.
#     So seq 9 is unambiguously 2020/21 there, and the series rolls forward from it.
#
# DO NOT map a seq to the season the GAME prints beside it. FMM's per-season columns read
# slots 2 and 3 while labelling them with the two most recent seasons — a constant 6-slot
# offset, reproduced in all three screenshots (a 2021 day-one save, a 2022 Turkish save and a
# 2026 Danish one). In the fresh save it prints seq 2 (16.785, really 2013/14) under the
# header "19/20", whose true value 18.571 sits at seq 8. The totals still agree, so this is a
# display quirk in the game, not a decode error here — but it means the only safe reads are
# the total and the trend.

_MAX_HISTORY = 128      # grows with career length; 10 in 2022, 24 by 2026
_MAX_COEFFS = 32


def _national_team(mm, t, n):
    out = {"rival_nation_id": None, "is_ranked": None, "world_ranking": None,
           "ranking_points": None, "ranking_history": [], "coefficients": [],
           "kit_colours": []}
    if t + 25 > n:
        return out
    out["kit_colours"] = [_u16(mm, t + 1 + 2 * i) for i in range(4)]
    rival = _u16(mm, t + 11)
    out["rival_nation_id"] = rival if 0 < rival <= 4096 else None
    out["is_ranked"] = bool(mm[t + 18])
    out["world_ranking"] = _u16(mm, t + 19)
    out["ranking_points"] = _u16(mm, t + 21)
    hn = _u16(mm, t + 23)
    # The history is a GROWING list, not a fixed 24. It held 10 entries in a 2022 Turkish
    # save and 24 in a 2026 Danish one, so pinning it to 24 silently returned nothing for
    # every earlier career — which is exactly what the cross-career check caught.
    if not (0 < hn <= _MAX_HISTORY) or t + 25 + 2 * hn > n:
        return out                      # unranked nations carry 0 here
    out["ranking_history"] = [_u16(mm, t + 25 + 2 * i) for i in range(hn)]
    q = t + 25 + 2 * hn
    cn = mm[q + 2] if q + 2 < n else 0
    if 0 < cn <= _MAX_COEFFS and q + 3 + 4 * cn <= n:
        out["coefficients"] = [round(struct.unpack("<f", mm[q + 3 + 4 * i:q + 7 + 4 * i])[0], 4)
                               for i in range(cn)]
    return out


def scrape_nations(mm):
    """{nation_id: record} — code, continent, capital city and national stadium.

    CLUB and COMPETITION records share this exact shape (long name, short name, 3-letter
    code), so the signature alone finds 1,860 candidates for 227 nations. Two filters are
    applied together, and neither works on its own — see the comment below.
    """
    # Two filters, and BOTH are needed. Position alone picks the competition table, which has
    # the same three-strings-plus-3-letter-code shape and is packed just as densely ("World
    # Cup Oceania Qualifying Section", code WCQ). A continent-id range alone leaves 35 club
    # and competition records scattered across 7-12 MB, one of which squats Belgium's id.
    cands = [c for c in _nation_candidates(mm) if _plausible_continent(c["continent_id"])]
    if not cands:
        return {}
    # densest cluster: nations sit together; a club match is isolated
    offs = sorted(c["offset"] for c in cands)
    best, run_start, run = (0, 0, 0), offs[0], 1
    for a, b in zip(offs, offs[1:]):
        if b - a <= 4096:
            run += 1
            if run > best[0]:
                best = (run, run_start, b)
        else:
            run, run_start = 1, b
    if best[0] < 20:
        return {}
    lo, hi = best[1], best[2]
    out = {}
    for c in cands:
        if lo <= c["offset"] <= hi:
            out.setdefault(c["id"], c)
    _check_nation_extent(mm, out)
    return out


def _check_nation_extent(mm, out):
    """The nation table is DENSE from id 0 to its declared count. Assert that, don't hope it.

    Unlike languages and currencies this table is not walked by chaining, so a rejected record
    does not truncate the rest -- it punches a hole. That is worse, not better: the result
    still looks like a well-formed table with 227 nations in it, and the only way to notice is
    to ask what the save says the count should be. Every one of the 23 that used to be absent
    was a REAL record (U.S.S.R., Yugoslavia, United Kingdom, Zaire ...), not a blank slot.

    So the check is both halves: the right NUMBER of records, and no gap in the id range.
    `0 <= id < declared` with no holes is the table's own invariant; the densest-cluster
    bound above is a heuristic, and this is what keeps the heuristic honest.
    """
    if not out:
        return
    start = min(r["offset"] for r in out.values())
    declared = _declared_count(mm, start)
    if declared is None:
        return
    missing = [i for i in range(declared) if i not in out]
    if missing or len(out) != declared:
        raise TableCountError(
            f"nations: read {len(out)} records but the table declares {declared}; "
            f"{len(missing)} id(s) absent from 0..{declared - 1}"
            + (f" (first few: {missing[:8]})" if missing else "")
            + ". A missing nation is a candidate the locator rejected, not a blank slot.")


def _nation_candidates(mm):
    n = len(mm)
    out = []
    # Both code lengths, longest first: a 3-letter code's prefix is the more specific match.
    pats = [(ln, struct.pack("<I", ln)) for ln in _CODE_LENS]
    heads = []
    for ln, pat in pats:
        q = 0
        while True:
            j = mm.find(pat, q)
            if j == -1:
                break
            q = j + 1
            heads.append((j, ln))
    heads.sort()
    for j, code_len in heads:
        try:
            code = mm[j + 4:j + 4 + code_len].decode("ascii")
        except UnicodeDecodeError:
            continue
        if not _CODE.match(code):
            continue
        # walk BACK over [len][Nationality][00] and [len][Name][00] to the header
        for nat_len in range(2, 40):
            a = j - 1 - nat_len - 4              # start of the nationality length field
            if a < 6 or _u32(mm, a) != nat_len or mm[a + 4 + nat_len] != 0:
                continue
            nationality, _ = _string(mm, a, n)
            if not nationality:
                continue
            for name_len in range(2, 48):
                c = a - 1 - name_len - 4
                if c < 6 or _u32(mm, c) != name_len or mm[c + 4 + name_len] != 0:
                    continue
                name, _ = _string(mm, c, n)
                if not name or not name[0].isupper():
                    continue
                nid = _u16(mm, c - 2)
                uid = _u32(mm, c - 6)
                # `0 <=`, not `1 <=`. Nation id 0 is ALGERIA, a real record at the very start
                # of the table, and excluding it did not just lose one nation: the table start
                # is derived from the surviving candidates, so rejecting record 0 moved the
                # whole table's start 188 bytes later than it really is.
                if not (0 <= nid <= 4096):
                    continue
                t = j + 4 + code_len      # just past [len][code]; 7 for a 3-letter code
                rec = {
                    "id": nid, "uid": uid, "name": name, "nationality": nationality,
                    "code": code, "continent_id": _u16(mm, t),
                    "capital_city_id": _u16(mm, t + 2),
                    "national_stadium_id": _u16(mm, t + 4), "offset": c - 6,
                }
                rec.update(_national_team(mm, t + 6, n))
                out.append(rec)
                break
            break
    return out


# ------------------------------------------------------------------ shared
def _seed_offsets(mm, pattern, limit=4000):
    """Offsets of strings matching `pattern`, as candidate table seeds."""
    return [m.start() for m in re.finditer(pattern, mm[:])][:limit]
