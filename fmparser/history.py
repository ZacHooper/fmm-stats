"""Career (season-by-season) player history — the top-of-the-History-screen club list.

THE TABLE IS A FOREST OF LINKED LISTS. One fixed-size stride-16 slab (265,423 rows in every
frem save, world creation to 2023 — only the byte offset drifts). Each row:

    +0  u16  club tid (0xffff = free/none)
    +2  u16  fee for the move INTO that club: ffff=none, fffe=loan, fffd/0=free, else £000s
    +4  u32  NEXT ROW POINTER — the 0-based index of the next row in THIS player's chain.
             0xFFFFFFFF = end of chain.
    +8  u8   season code — ABSOLUTE; end_year = 1971 + code (50 = the 2020/21 campaign)
    +9  u8   appearances       +10 u8  goals — CONCEDED for goalkeepers
    +11 u8   assists           +14 u16 average rating x100 (0 on pre-career rows)

`+4` IS A POINTER, NOT A COUNTER. This is the whole thing, and getting it wrong is what broke
every previous version. On a FRESH save each record is laid out contiguously, so row k holds
k+1 and the field is indistinguishable from a monotonic counter — and the chain-terminating
0xFFFFFFFF is indistinguishable from a record trailer. Both misreadings work perfectly on
denmark-start and nowhere else: seasons played DURING a career are appended into RECYCLED
slots elsewhere in the slab, so the chain jumps and the "+1 sequence" breaks *inside* a
record. Splitting records on a sequence break shatters each player into 3-4 fake players.

    66162 -> 66163 -> ... -> 66172 -> 66173 -+   contiguous run (pre-career), ptr = k+1
                                             +-> 10541 -> 2471 -> END   appended, recycled

RECORD STARTS = ROWS WITH IN-DEGREE 0 — rows nothing points at. Exact; no delimiter
heuristics, no season-plausibility guessing, no alignment DP. Audit any candidate slab with
`Table.sanity()`: `max_indeg == 1` and `heads == terminators`. True on all 10 frem saves.

THE ONE READING RULE. Walking a chain gives rows [h, r1, r2, ...]. For each row k after the
head, **the season and stats come from row k-1, and the club and fee come from row k.**
So the head supplies only a club: the youth/origin club (the Athletic-Bilbao eligibility
key). Equivalently: the club column leads the stats by one row, in both the contiguous and
the appended parts of a chain. Verified against five in-game Player-History screens
(`denmark-24-start.fms`, 30 Jun 2023) — every season line matches, and all five career
Pld/Gls/Ast TOTALS match exactly: Dirksen 198/10/0, Andersson 286/16/2, Thrane 195/26/4,
Fugl 46/8/12, Erenbjerg 82/19/3 (including his two loan spells and their loan fee markers).
The rule fixes transfer years too: reading the club off the same row put Dirksen at Frem from
2018/19, one season late — the club column is what tells you he signed for 2017/18.

The last row of the contiguous run is a DEBUT/summary row (0 apps, `+8` = debut season, often
the season the player turned 15/16). Under the rule above it is consumed as a club row, so it
never becomes a spurious season — which is exactly what makes the totals come out right.

LINKING IS SOLVED AND IS NOT POSITIONAL. There is no tid/sid/uid anywhere in this table; the
pointer runs the other way. The player's ATTRIBUTE record holds the chain head:

    P-42  u32  SID                    (already used to key the attribute record)
    P-38  u32  HISTORY CHAIN HEAD     <- the link

where P is the record pointer `staging.scrape_attributes` computes. 25,627/25,627 in-range
values on denmark-24-start are valid chain heads, all distinct; out-of-range = no history yet
(newgens). Do NOT re-derive P by hand: being off by one 78-byte grid step silently returns a
NEIGHBOURING player's career, which looks entirely plausible inside a youth-intake cohort.

KNOWN GAP: blank youth seasons can be one short (the game renders a row for the debut season
itself; we start at the first stored row). Apps are 0 there, so totals are unaffected.

See docs/agent-context/player-history-table.md for the full reverse-engineering story and
docs/IDS.md section PLAYER -> CAREER HISTORY for the link.
"""
import struct

import numpy as np

FF = 0xFFFFFFFF
NO_CLUB = 0xFFFF
STRIDE = 16
SEASON_BASE = 1971                             # end_year = SEASON_BASE + code
HEAD_AT = -38                                  # chain head, relative to the attribute-record P
SID_AT = -42                                   # sid, relative to the same P


def season_end_year(code, base=SEASON_BASE):
    """History season byte -> campaign end-year (50 -> 2021, i.e. the 2020/21 season)."""
    return base + code


def decode_fee(v):
    """+2 transfer-fee field -> a friendly value. Little-endian u16: `ff ff` = no fee recorded,
    `fe ff` = loan, `fd ff` = a second free-transfer marker, 0 = free, else the fee in £000s.

    Display note: the game shows `ff ff` as blank when the club is unchanged but as **"Bos"**
    (Bosman) on a row where the player moved — same stored value, two labels. Both `fd ff` and
    0 render as "Free" (confirmed on Thrane's 2021/22 Naestved move, which stores `fd ff`).
    """
    return {0xffff: "stay", 0xfffe: "loan", 0xfffd: "free", 0: "free"}.get(v, v)


def _u32(buf, off):
    return (buf[off].astype(np.uint32) | buf[off + 1].astype(np.uint32) << 8 |
            buf[off + 2].astype(np.uint32) << 16 | buf[off + 3].astype(np.uint32) << 24)


def _as_array(mm):
    return mm if isinstance(mm, np.ndarray) else np.frombuffer(mm, dtype=np.uint8)


def locate(mm, vmin=5000, vmax=4_000_000, samples=48, min_seq=0.45):
    """Find the slab. -> [(rows, start, hits)], best first; one survivor on every save tested.

    `u32 @ (start - 12)` is the exact row count. It sits at offset %4 == 1 (NOT 4-byte
    aligned), which is why no aligned scan ever found it, and there is no pointer to the table
    anywhere else in the file. Signals, none of which hardcode an offset or a season range:
      1. the header is a plausible row count and start + 16*rows fits in the file;
      2. `next == k+1` for a supermajority of sampled rows — untouched rows still point at
         their physical successor. (Never read a "first counter" from row 0: on a played-in
         save row 0 is usually a recycled row holding an unrelated pointer. That mistake is
         what made the old locator settle on a FALSE header partway into the slab.)
      3. every non-terminal pointer is in-slab (`< rows`).
    Ranked by signal 2, then size. Verify the winner with Table.sanity().
    """
    buf = _as_array(mm)
    n = len(buf)
    p = np.flatnonzero(buf[3:n - 3] == 0)                   # the header's high byte
    V = _u32(buf, p)
    keep = (V >= vmin) & (V <= vmax)
    p, V = p[keep], V[keep]
    S = p + 12
    fits = (S.astype(np.int64) + STRIDE * (V.astype(np.int64) + 2)) <= n - STRIDE
    V, S = V[fits].astype(np.int64), S[fits].astype(np.int64)
    if not len(S):
        return []
    hits = np.zeros(len(S), np.int32)
    inrange = np.ones(len(S), bool)
    for f in np.linspace(0, 1, samples):
        k = ((V - 1) * f).astype(np.int64)
        c = _u32(buf, S + STRIDE * k + 4).astype(np.int64)
        hits += (c == k + 1)
        inrange &= ((c == FF) | (c < V))
    good = inrange & (hits >= int(samples * min_seq))
    out = [(int(v), int(s), int(h)) for v, s, h in zip(V[good], S[good], hits[good])]
    out.sort(key=lambda r: (-r[2], -r[0]))
    return out


class Table:
    """The slab, decoded column-wise, plus its pointer forest."""

    def __init__(self, mm, start=None, rows=None):
        buf = _as_array(mm)
        if start is None:
            cand = locate(buf)
            if not cand:
                raise ValueError("career-history table not found")
            rows, start, _ = cand[0]
        self.start, self.rows = start, rows
        o = start + STRIDE * np.arange(rows)
        self.next = _u32(buf, o + 4).astype(np.int64)
        self.club = buf[o].astype(np.int64) | buf[o + 1].astype(np.int64) << 8
        self.fee = buf[o + 2].astype(np.int64) | buf[o + 3].astype(np.int64) << 8
        self.season = buf[o + 8].astype(np.int64)
        self.apps = buf[o + 9].astype(np.int64)
        self.goals = buf[o + 10].astype(np.int64)
        self.assists = buf[o + 11].astype(np.int64)
        self.rating = buf[o + 14].astype(np.int64) | buf[o + 15].astype(np.int64) << 8
        live = self.next != FF
        self.indeg = np.bincount(self.next[live], minlength=rows)

    def sanity(self):
        """A well-formed slab is a forest: in-degree <= 1 everywhere, one terminator per head."""
        k = np.arange(self.rows)
        return {"rows": self.rows, "start": self.start,
                "heads": int((self.indeg == 0).sum()),
                "terminators": int((self.next == FF).sum()),
                "max_indeg": int(self.indeg.max()),
                "untouched": round(float((self.next == k + 1).mean()), 4)}

    def is_forest(self):
        s = self.sanity()
        return s["max_indeg"] <= 1 and s["heads"] == s["terminators"]

    def debut_row(self, head):
        """The DEBUT/summary row: the last row of the chain's contiguous run, i.e. the row
        whose pointer is the first to jump out of it (or the final row if it never jumps)."""
        rows = self.chain(head)
        for k in rows[:-1]:
            if self.next[k] != k + 1:
                return k
        return rows[-1]

    def chain(self, head, limit=400):
        """Row indices of one player's record, head first. `limit` guards a corrupt slab."""
        out, k = [], int(head)
        while 0 <= k < self.rows and len(out) < limit:
            out.append(k)
            if self.next[k] == FF:
                break
            k = int(self.next[k])
        return out

    def seasons(self, head, base=SEASON_BASE):
        """[{season, end_year, club_tid, fee, apps, goals, assists, rating}] for one player.

        THE READING RULE: season+stats from row k-1, club+fee from row k. See the module
        docstring — the head therefore contributes no season, only the origin club, and the
        trailing debut row is consumed as a club row rather than emitted as a phantom season.
        """
        out = []
        for k in self.chain(head)[1:]:
            j = k - 1
            out.append({"season": int(self.season[j]),
                        "end_year": season_end_year(int(self.season[j]), base),
                        "club_tid": int(self.club[k]),
                        "fee": decode_fee(int(self.fee[k])),
                        "apps": int(self.apps[j]), "goals": int(self.goals[j]),
                        "assists": int(self.assists[j]),
                        "rating": round(int(self.rating[j]) / 100, 2) or None})
        return out


def head_index(mm, info, attrs):
    """{tid: chain head row} via the attribute record's `u32 @ P-38`. Absent = no history."""
    out = {}
    for tid, p in info.items():
        rec = attrs.get(p["sid"])
        if rec is not None:
            out[tid] = struct.unpack_from("<I", mm, rec["P"] + HEAD_AT)[0]
    return out


def build(mm, info, attrs):
    """Top-level: {tid: history} for every player whose attribute record points at a chain.

    history = {origin_club_tid, last_season_club_tid, debut_season, debut_end_year,
               confidence, record_offset, seasons: [...]}.

    `confidence` is kept for the existing schema and is always 'exact' now — the link is a
    stored pointer, not an inferred alignment, so there is no low-confidence tail any more.
    `info` / `attrs` are the shared spines from staging.scrape_players / scrape_attributes.
    """
    table = Table(mm)
    if not table.is_forest():                  # a mislocated slab decodes into garbage chains
        raise ValueError(f"history slab failed the forest check: {table.sanity()}")

    out = {}
    for tid, head in head_index(mm, info, attrs).items():
        if not 0 <= head < table.rows or table.indeg[head] != 0:
            continue                           # no history yet (newgen), or a stale pointer
        seasons = table.seasons(head)
        if not seasons:
            continue
        debut = int(table.season[table.debut_row(head)])
        out[tid] = {
            # youth/origin club = the head row's club — the Athletic-Bilbao eligibility key.
            "origin_club_tid": int(table.club[head]),
            # club of the most recent STORED season — not necessarily his club today (a summer
            # signing's current club is on the player row itself).
            "last_season_club_tid": seasons[-1]["club_tid"],
            "debut_season": debut,
            "debut_end_year": season_end_year(debut) if debut is not None else None,
            "confidence": "exact",
            "record_offset": table.start + STRIDE * head,
            "seasons": seasons,
        }
    return out
