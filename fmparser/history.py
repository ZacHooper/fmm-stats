"""Career (season-by-season) player history — the top-of-the-History-screen club list.

The save stores one big contiguous **stride-16 table** (denmark-start.fms: 39.56M–41.46M,
118,659 rows, 11,238 player records). Each 16-byte row:

    +0  u16  club tid (a REAL club tid; 0xffff = free/none)
    +2  u16  transfer fee for that move: 0xffff=stayed, 0xfeff=loan, 0=free, else £000s
    +4  u32  global monotonic row counter (1..N). The value 0xFFFFFFFF marks a record
             TRAILER (end of one player's history) and still consumes a counter slot.
    +8  u8   season code — ABSOLUTE: 50 = the 2020/21 campaign, end_year = 1971 + code.
             On a TRAILER row this byte is instead the player's DEBUT season.
    +9  u8   appearances that season
    +10 u8   goals that season
    +11..15  assists / cards / avg-rating (trailing; not decoded here)

On a trailer row `+0` = the player's club as of the last COMPLETED season (2020/21) — i.e.
the authoritative CURRENT club. (There is a known ~1-row lag between the club column and the
stat columns for the final season when a player moved mid-season: the last data row shows the
club he moved FROM with the new club's stats, and the trailer shows the club he moved TO. So
trust the trailer for the current club, and the FIRST data row for the origin club.)

LINKING records to players (validated 2026-08 on the Frem squad, 4/4 in-game confirmations):
records are **SID-ORDERED**, covering the ~10,500 LOWEST-sid players (the ones that existed at
world creation and therefore have a real career). Newgens / youth-intake players have no record
yet — they map past the end of the table (the reserved empty tail that fills in future seasons).
The sid-less staff/legend entities (info sid == 0xFFFFFFFF, e.g. record 0 = a 27-season veteran)
ALSO have records and are interleaved by sid, so the record<->player offset DRIFTS smoothly
(0 → ~740 across the range). We recover the exact map with a banded DP that walks the sid-sorted
player list and decides, per record, whether it belongs to the next player or is an interleaved
staff record (a "gap"), scoring on the trailer-club == player-club signal. The result is a
monotonic offset backbone pinned by ~3,700 self-consistent "stayer" anchors. Transfers (whose
trailer club is their OLD club, not their current one) are carried by the local offset.

See docs/agent-context/player-history-table.md for the full reverse-engineering story.
"""

FF = 0xFFFFFFFF
NO_CLUB = 0xFFFF


def season_end_year(code):
    """History season byte -> campaign end-year (50 -> 2021, i.e. the 2020/21 season)."""
    return 1971 + code


def decode_fee(v):
    """+2 transfer-fee field -> a friendly value. Bytes are little-endian u16:
    `ff ff` = 0xffff -> 'stay', `fe ff` = 0xfffe -> 'loan', 0 -> 'free', else fee in £000s (int)."""
    if v == 0xffff:
        return "stay"
    if v == 0xfffe:
        return "loan"
    if v == 0:
        return "free"
    return v                                   # thousands of pounds (15000 = £15M)


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


def _season_plausible(mm, start, sample=400, lo=20, hi=55):
    """Fraction of the first `sample` data rows whose +8 season byte is a real campaign
    code (20..55). The history table reads ~1.0; other stride-16 counter tables (which also
    increment +4 but store season 0) read ~0.0 — this is what tells them apart."""
    ok = tot = 0
    o = start
    while tot < sample and o < len(mm):
        c4 = _u32(mm, o + 4)
        if c4 != FF:
            tot += 1
            if lo <= mm[o + 8] <= hi:
                ok += 1
        o += 16
    return ok / tot if tot else 0.0


def find_table_start(mm, min_run=48, min_season_frac=0.7):
    """Locate the history table's first row = where the +4 counter resets to 1 and then
    increments 1 per row (delimiter rows show 0xFFFFFFFF but still consume their slot).
    Derived per-save (offsets differ between saves) — never hard-coded. Validated by
    season-plausibility so we don't lock onto a look-alike counter table (e.g. an
    established-career save whose history is laid out differently reads season 0 and is
    rejected -> the caller skips history rather than emit garbage)."""
    target = (1).to_bytes(4, "little")
    pos = mm.find(target)
    while pos != -1:
        c = pos - 4                            # counter sits at row+4
        if c >= 0 and _u32(mm, c + 12) == 0:   # data rows have zero trailing u32
            ok = True
            for k in range(min_run):
                v = _u32(mm, c + 4 + 16 * k)
                if v == FF:                    # trailer consumes a counter slot
                    continue
                if v != k + 1:
                    ok = False
                    break
            if ok and _season_plausible(mm, c) >= min_season_frac:
                return c
        pos = mm.find(target, pos + 1)
    raise ValueError("no season-plausible history table found "
                     "(counter==1 run with real season codes)")


def enumerate_records(mm, start=None, end_gap=6, empty_run_limit=64):
    """Walk the table from `start`, splitting into per-player records. Returns a list of
    records, each: {rows, current_club, debut_season, offset, has_trailer}, where
    `rows` = [(club, fee_raw, season, apps, goals), ...] oldest -> newest.

    RECORD BOUNDARIES:
      * a TRAILER row `+4 == 0xFFFFFFFF` (the normal case) — carries current club (+0) and
        debut season (+8); OR
      * a SEASON DROP — a data row whose season is LOWER than the previous row's. Within a
        record seasons only ever increase (oldest -> newest), so a drop begins a new player.
        This catches the ~0.4% of records (on established saves) that lack an explicit trailer.

    TABLE END: two signals. (1) the +4 counter is a monotonic 1..N row-index used ONLY to bound
    the table — NOT to split records; we tolerate isolated holes (players added mid-career carry
    an out-of-sequence +4 ~271k) and stop after `end_gap` CONSECUTIVE counter misses (the next,
    independently-counted segment). (2) the real table is followed by a large PADDING region of
    EMPTY records (a data-less FF trailer each, ~25k of them) reserved for future newgens — so we
    also stop after `empty_run_limit` consecutive empty (0-row) records and drop that trailing run.
    Short empty runs (<=~30) are kept: they are genuine no-history players interleaved by sid."""
    if start is None:
        start = find_table_start(mm)
    records, cur = [], []
    rec_off = start

    def close(trailer_off=None):
        nonlocal cur, rec_off
        if not cur and trailer_off is None:
            return
        records.append({
            "rows": cur,
            "current_club": _u16(mm, trailer_off) if trailer_off is not None
                            else (cur[-1][0] if cur else NO_CLUB),
            "current_fee": _u16(mm, trailer_off + 2) if trailer_off is not None else 0xffff,
            "debut_season": mm[trailer_off + 8] if trailer_off is not None
                            else (cur[0][2] if cur else 0),
            "offset": rec_off,
            "has_trailer": trailer_off is not None,
        })
        cur = []

    zero = b"\x00" * 16
    o, expected, bad, zrun, empty_run, last_seas, n = \
        start, _u32(mm, start + 4), 0, 0, 0, None, len(mm)
    while o < n:
        if mm[o:o + 16] == zero:                # big empty region -> section end, stop
            zrun += 1
            if zrun >= 16:
                break
            o += 16
            continue
        zrun = 0
        c4 = _u32(mm, o + 4)
        if c4 == FF:                           # explicit trailer -> close record
            n_before = len(records)
            close(trailer_off=o)
            if len(records) > n_before and not records[-1]["rows"]:
                empty_run += 1                  # a data-less (padding-candidate) record
                if empty_run >= empty_run_limit:   # entered the reserved padding tail -> stop
                    del records[-empty_run:]    # drop the whole trailing empty run
                    return records
            else:
                empty_run = 0
            last_seas = None
            expected += 1
            bad = 0
            o += 16
            rec_off = o
            continue
        if c4 == expected:                     # counter in sequence
            bad = 0
        else:                                  # a hole (isolated) or the table end
            bad += 1
            if bad >= end_gap:                 # sustained break -> next segment: stop
                break
        expected += 1
        s = mm[o + 8]
        if last_seas is not None and s < last_seas:   # season drop -> implicit boundary
            close()
            rec_off = o
        cur.append((_u16(mm, o), _u16(mm, o + 2), s, mm[o + 9], mm[o + 10]))
        last_seas = s
        o += 16
    close()                                    # flush trailing record (no trailer)
    return records


def align(records, player_clubs, max_staff=1500, staff_penalty=0.15):
    """Map sid-sorted players -> records via a banded DP (see module docstring).

    `player_clubs` = list of each sid-sorted player's current club_tid. Returns
    `rec2p` = {record_index: player_index or None} (None = an interleaved staff record).

    State `s` = number of staff records seen so far; record i, if a player record, belongs
    to player (i - s). We reward trailer-club == player-club (+1) and charge a small penalty
    per staff gap so the ~740 real staff records are placed but not over-inserted."""
    N = len(records)
    S = max_staff
    NEG = float("-inf")
    dp = [NEG] * (S + 1)
    dp[0] = 0.0
    choice = bytearray(N * (S + 1))
    for i in range(N):
        ndp = [NEG] * (S + 1)
        rc = records[i]["current_club"]
        smax = S if i >= S else i
        base_row = i * (S + 1)
        for s in range(smax + 1):
            base = dp[s]
            if base == NEG:
                continue
            pj = i - s                          # record i as a player -> player pj
            m = 1.0 if (pj < len(player_clubs) and player_clubs[pj] == rc) else 0.0
            if base + m > ndp[s]:
                ndp[s] = base + m
                choice[base_row + s] = 0        # 0 = player record
            if s + 1 <= S and base - staff_penalty > ndp[s + 1]:
                ndp[s + 1] = base - staff_penalty
                choice[base_row + s + 1] = 1    # 1 = staff record (gap)
        dp = ndp
    s = max(range(S + 1), key=lambda k: dp[k])
    rec2p = {}
    for i in range(N - 1, -1, -1):
        if choice[i * (S + 1) + s] == 0:
            rec2p[i] = i - s
        else:
            rec2p[i] = None
            s -= 1
    return rec2p


def build(mm, info):
    """Top-level: {tid: history} for every player that has a career record.

    history = {origin_club_tid, current_club_tid, confidence, record_offset, seasons:[{
        season (raw byte), end_year, club_tid, fee, apps, goals}]}. `confidence` is 'high'
    when the player is a self-consistent "stayer" (trailer club == their current club),
    else 'medium' (transfer/loan, carried by the local offset — origin/current still sound).
    `info` is the shared player-info spine from staging.scrape_players."""
    def sid_u16(r):
        s = r["sid"]
        if isinstance(s, str) and len(s) >= 8:
            v = int.from_bytes(bytes.fromhex(s)[:2], "little")
            return None if v == 0xffff else v
        return None

    players = sorted((r for r in info.values() if sid_u16(r) is not None),
                     key=lambda r: sid_u16(r))
    player_clubs = [r["club_tid"] for r in players]
    records = enumerate_records(mm)
    rec2p = align(records, player_clubs)

    out = {}
    for i, pj in rec2p.items():
        if pj is None or pj >= len(players):
            continue
        rec = records[i]
        rows = rec["rows"]
        p = players[pj]
        last_season = rec["current_club"]       # trailer = club as of last completed season
        last_fee = rec.get("current_fee", 0xffff)
        # WITHIN A RECORD THE CLUB COLUMN LEADS THE STATS BY ONE ROW (verified vs in-game history):
        # the apps/goals on row k were played at the club on row k+1 (last row -> the trailer's
        # club). The fee travels WITH that club (its own row: loan/sold-for/stay), NOT with the
        # stats. So a season entry = (season/apps/goals from row k) + (club & fee from row k+1).
        # Row 0's club is the youth/origin club (the "from" of the first move) -> origin_club_tid.
        seasons = []
        for k, (c, fv, se, a, g) in enumerate(rows):
            if k + 1 < len(rows):
                club, fee = rows[k + 1][0], decode_fee(rows[k + 1][1])
            else:                                # last data row -> played at the trailer's club
                club, fee = last_season, decode_fee(last_fee)
            seasons.append({"season": se, "end_year": season_end_year(se),
                            "club_tid": club, "fee": fee, "apps": a, "goals": g})
        origin = rows[0][0] if rows else last_season   # first row's club = youth/origin club
        out[p["tid"]] = {
            # origin (youth) club = first career row -> the Athletic-Bilbao eligibility key.
            "origin_club_tid": origin,
            # club as of the last completed season (trailer). Equals the player's actual
            # current club (info.club_tid) for "stayers"; differs for summer signings, whose
            # actual current club is on the player row itself.
            "last_season_club_tid": last_season,
            "confidence": "high" if last_season == p["club_tid"] else "medium",
            "record_offset": rec["offset"],
            "seasons": seasons,
        }
    return out
