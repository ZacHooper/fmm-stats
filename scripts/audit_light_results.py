#!/usr/bin/env python3
"""
Light-results audit: prove what we read, and measure exactly what we do not.

`scripts/audit_records.py` does this for the player/staff/city records and its value is
structural: the parser reads FROM a declarative layout and the audit checks AGAINST it, so
the two cannot drift. Light results has no such layout, and three faults hid behind that --
each one the same shape, a TUNED CONSTANT bounding a walk:

  1. `lightresults.YEARS` is (2020, 2021, 2022), a Bucaspor-era literal. Every record whose
     +12 year field holds a later season is dropped, which on a 2026 Frem save is ~35% of
     them.
  2. `find_light_regions` LOCATES regions by searching for those same three year markers,
     then gates the result on `min_hits`, `margin` and `merge_gap` -- four constants. It
     returns fewer regions the further a career runs past 2022.
  3. One record layout is assumed, `[home u16][away u16][sH][sA]`, though the module's own
     docstring warns light fixtures are MULTI-VARIANT. Some verified fixtures have their two
     club tids nowhere near each other in the file.

None of that is visible from "the values look right" -- every fixture we DO decode decodes
correctly. It is only visible by measuring coverage against ground truth we did not generate.

    uv run python scripts/audit_light_results.py [save.fms]
    uv run python scripts/audit_light_results.py --map        # the per-byte schema
    uv run python scripts/audit_light_results.py --truth-only # just the ground-truth scorecard

GROUND TRUTH is `tests/fixtures/light_results_truth.json` -- results read off in-game
screenshots. It is the only independent check available: our own club's matches live in the
rich match region (`regions.MATCH_LO`), a different structure, so grading against them would
be the parser marking its own homework.
"""
import argparse
import datetime
import json
import os
import struct
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Light results was retired (it scanned club records thinking they were simulated results).
from fmparser.tables.person_info import NO_CLUB, scrape_person_info  # noqa: E402
from fmparser.save import Save                  # noqa: E402

TRUTH_PATH = os.path.join(ROOT, "tests", "fixtures", "light_results_truth.json")
UNKNOWN = "UNKNOWN"

# The 21-byte light record as we currently read it. Offsets that the parser never touches are
# declared UNKNOWN rather than omitted -- an omitted byte is a byte we step over by accident,
# which is the whole lesson of the player record's missing tail.
LIGHT_LAYOUT = [
    (0, 2, "home_tid"),
    (2, 2, "away_tid"),
    (4, 1, "score_home"),
    (5, 1, "score_away"),
    (6, 2, UNKNOWN),          # never read
    (8, 2, "flags"),          # 0x40xx / 0xc0xx family; a record marker, NOT the competition
    (10, 2, "comp_cid"),
    (12, 2, "year"),          # base-offset, not a literal year (see docs)
    (14, 2, "day"),           # day-of-year, but mis-paired across a variant boundary
    (16, 2, UNKNOWN),
    (18, 2, UNKNOWN),         # observed 'ff ff' terminator
    (20, 1, UNKNOWN),         # observed copy index
]
LIGHT_STRIDE = 21


# ---------------------------------------------------------------------------
# ground truth
# ---------------------------------------------------------------------------
def load_truth():
    with open(TRUTH_PATH) as fh:
        return json.load(fh)


def iter_truth(truth):
    for rnd in truth["rounds"]:
        for fx in rnd["fixtures"]:
            yield rnd, fx


# ---------------------------------------------------------------------------
# 1a. region discovery -- structural, no year markers
# ---------------------------------------------------------------------------
def club_pair_positions(mm, valid):
    """Every offset where u16@+0 and u16@+2 are both real, different club tids.

    This is the light record's own signature and it needs no year, no cid and no score
    plausibility -- which is the point. `find_light_regions` uses the year markers instead,
    so it goes blind as a career moves past 2022.
    """
    u16 = lambda o: struct.unpack_from("<H", mm, o)[0]      # noqa: E731
    out = []
    for o in range(0, len(mm) - 4):
        h = u16(o)
        if h not in valid:
            continue
        a = u16(o + 2)
        if a in valid and a != h:
            out.append(o)
    return out


def grid_regions(mm, positions, min_run=5):
    """Group positions into regions by the 21-byte grid they sit on.

    A light region is a CHAIN of records on a common stride, so the honest boundary test is
    "o and o+21 are both records", followed as far as it goes. Note the chain has to be
    followed through a SET -- the position list is dense (neighbouring offsets often both
    hold two valid tids), so "consecutive entries 21 apart" finds nothing.

    `min_run` is 5 because the chains are SHORT BY CONSTRUCTION and that is a finding, not a
    nuisance: measured on frem-2026-06-11 the longest is 17 and there is a clear mode at
    10-17, which is one club's home fixtures for a season. The region is a sequence of
    per-club blocks (standings-record.md), not one continuous table, so any `min_run` above
    ~17 finds nothing at all. Returns [(lo, hi, n_records)].
    """
    if not positions:
        return []
    pos = set(positions)
    seen = set()
    runs = []
    for o in positions:
        if o in seen or (o - LIGHT_STRIDE) in pos:
            continue                      # not a chain head
        chain = [o]
        seen.add(o)
        nxt = o + LIGHT_STRIDE
        while nxt in pos:
            chain.append(nxt)
            seen.add(nxt)
            nxt += LIGHT_STRIDE
        if len(chain) >= min_run:
            runs.append(chain)
    runs.sort(key=lambda c: c[0])
    # merge runs that are close enough to be one table with gaps (headers, padding, blocks)
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] < 250_000:
            merged[-1] = (merged[-1][0], run[-1], merged[-1][2] + len(run))
        else:
            merged.append((run[0], run[-1], len(run)))
    return merged


# ---------------------------------------------------------------------------
# 1b. coverage
# ---------------------------------------------------------------------------
def coverage(mm, lo, hi, record_offsets):
    """What fraction of the region do we actually read, and what is the rest?

    Padding is counted separately from content. The headline number is NON-PADDING UNREAD:
    bytes that carry something and that no parser looks at.
    """
    seg = mm[lo:hi]
    total = hi - lo
    c = Counter(seg)
    pad = c[0x00] + c[0xFF]
    read = bytearray(total)
    for o in record_offsets:
        if lo <= o < hi:
            for b in range(o - lo, min(o - lo + LIGHT_STRIDE, total)):
                read[b] = 1
    n_read = sum(read)
    # non-padding bytes that are not inside a record we decode
    unread_content = sum(1 for i in range(total)
                         if not read[i] and seg[i] not in (0x00, 0xFF))
    return {"total": total, "read": n_read, "pad": pad,
            "unread_content": unread_content}


# ---------------------------------------------------------------------------
# 1c. variant inventory -- probe with ground truth, every separation
# ---------------------------------------------------------------------------
def find_all_sites(mm, h, a, hg, ag, span=64):
    """Every place both club tids sit within `span` bytes, in either order.

    Deliberately does NOT require adjacency: the assumption that the two tids are 2 bytes
    apart is fault #3, so the audit must not bake it in. Returns
    [(offset_of_first_tid, separation, score_offset_or_None)].
    """
    def positions(t):
        pat = struct.pack("<H", t)
        out, i = [], mm.find(pat, 0)
        while i != -1:
            out.append(i)
            i = mm.find(pat, i + 1)
        return out

    ph, pa = positions(h), set(positions(a))
    sites = []
    for o in ph:
        for sep in range(-span, span + 1):
            if sep == 0 or (o + sep) not in pa:
                continue
            base = min(o, o + sep)
            soff = None
            for k in range(0, 40):
                if base + k + 1 < len(mm):
                    if mm[base + k] == hg and mm[base + k + 1] == ag:
                        soff = k
                        break
                    if mm[base + k] == ag and mm[base + k + 1] == hg:
                        soff = k
                        break
            sites.append((o, sep, soff))
    return sites


# ---------------------------------------------------------------------------
# 1d. per-gate rejection cost
# ---------------------------------------------------------------------------
def gate_costs(mm, valid, lo, hi):
    """How many candidates does each of sweep()'s conditions reject, in isolation?

    Measured one gate at a time against the same candidate set, so the answer is "what does
    THIS constant cost", not "what does the conjunction cost".
    """
    u16 = lambda o: struct.unpack_from("<H", mm, o)[0]      # noqa: E731
    cand = 0
    rej = Counter()
    for o in range(lo, min(hi, len(mm) - 16)):
        h = u16(o)
        if h not in valid:
            continue
        a = u16(o + 2)
        if a not in valid or a == h:
            continue
        cand += 1
        if not (mm[o + 4] <= 30 and mm[o + 5] <= 30):
            rej["score <= 30"] += 1
        cid = u16(o + 10)
        if not (0 < cid < 20000):
            rej["0 < cid < 20000"] += 1
        if u16(o + 12) not in L.YEARS:
            rej["year in YEARS (2020-22)"] += 1
        if u16(o + 12) not in set(range(0x07E4, 0x07F6)):
            rej["year in 2020..2037"] += 1
    return cand, rej


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def print_map():
    named = sum(w for _, w, n in LIGHT_LAYOUT if n != UNKNOWN)
    print(f"\nlight_result  ({LIGHT_STRIDE} bytes)")
    print(f"  {'offset':>10}  {'width':>5}  field")
    for off, width, name in sorted(LIGHT_LAYOUT):
        span = f"+{off}" if width == 1 else f"+{off}..{off + width - 1}"
        flag = "   <-- undecoded" if name == UNKNOWN else ""
        print(f"  {span:>10}  {width:>5}  {name}{flag}")
    print(f"  -- {named} of {LIGHT_STRIDE} bytes decoded, {LIGHT_STRIDE - named} undecoded")
    owner = [None] * LIGHT_STRIDE
    for off, width, name in LIGHT_LAYOUT:
        for b in range(off, off + width):
            owner[b] = name
    gaps = [b for b in range(LIGHT_STRIDE) if owner[b] is None]
    if gaps:
        print(f"  UNACCOUNTED BYTES {gaps} -- name them or declare them UNKNOWN")
    return not gaps


def truth_scorecard(mm, valid, truth):
    """The only check that is not the parser grading itself."""
    print("\n" + "=" * 78)
    print("GROUND TRUTH  (in-game screenshots -- tests/fixtures/light_results_truth.json)")
    print("=" * 78)
    recs = L.sweep(mm, valid, lo=0, hi=len(mm), min_copies=1)
    got = set()
    for r in recs:
        got.add((r["home"], r["away"], r["scoreH"], r["scoreA"]))
    by_group = defaultdict(lambda: [0, 0])
    by_round = []
    for rnd in truth["rounds"]:
        hit = 0
        for fx in rnd["fixtures"]:
            h, a, hg, ag = fx["home"], fx["away"], fx["hg"], fx["ag"]
            ok = (h, a, hg, ag) in got or (a, h, ag, hg) in got
            hit += ok
            g = by_group[fx["ui_group"]]
            g[1] += 1
            g[0] += ok
        by_round.append((rnd, hit))
        print(f"  {rnd['competition'][:26]:<26} {rnd['date']}   "
              f"{hit}/{len(rnd['fixtures'])} recovered")
    tot = sum(len(r['fixtures']) for r in truth["rounds"])
    hits = sum(h for _, h in by_round)
    print(f"\n  TOTAL {hits}/{tot} = {hits/tot:.0%} of verified fixtures recovered by sweep()")
    print("\n  by UI group (the game renders one match-day as two sections; Zac spotted it,")
    print("  and it is the best hint that a single round is stored in more than one place):")
    for g, (h, t) in sorted(by_group.items()):
        print(f"     group {g}: {h}/{t} = {h/t:.0%}")
    return hits, tot


def main():
    ap = argparse.ArgumentParser(description="Audit the light-results region.")
    ap.add_argument("save", nargs="?",
                    default=os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms"))
    ap.add_argument("--map", action="store_true", help="print the per-byte schema and exit")
    ap.add_argument("--truth-only", action="store_true", help="only the ground-truth scorecard")
    ap.add_argument("--variants", action="store_true", help="run the variant inventory (slow)")
    args = ap.parse_args()

    if args.map:
        return 0 if print_map() else 1

    if not os.path.exists(args.save):
        print(f"SKIP: {args.save} not found (fetch with rclone or scripts/rebuild.py)")
        return 0

    mm = Save(args.save).mm
    print(f"auditing {os.path.basename(args.save)}  ({len(mm)/1e6:.1f} MB)")
    info = scrape_person_info(mm)
    valid = {v["club_tid"] for v in info.values()
             if v.get("club_tid") and v["club_tid"] != NO_CLUB}
    truth = load_truth()

    hits, tot = truth_scorecard(mm, valid, truth)
    if args.truth_only:
        return 0

    print("\n" + "=" * 78)
    print("1a. REGIONS -- structural (21-byte runs of club-tid pairs), vs the year-marker finder")
    print("=" * 78)
    pos = club_pair_positions(mm, valid)
    regions = grid_regions(mm, pos)
    current = L.find_light_regions(mm, valid)
    print(f"  club-tid-pair positions in file : {len(pos):,}")
    print(f"  structural regions found        : {len(regions)}")
    print(f"  find_light_regions() returns    : {len(current)}")
    print(f"\n  {'MB range':<20} {'records':>9}   seen by find_light_regions()?")
    for lo, hi, n in regions:
        seen = any(a <= lo <= b or a <= hi <= b for a, b in current)
        print(f"  {lo/1e6:8.3f}-{hi/1e6:8.3f} {n:>9}   {'yes' if seen else 'NO  <-- never swept'}")

    print("\n" + "=" * 78)
    print("1b. COVERAGE -- every byte named, declared UNKNOWN, or padding")
    print("=" * 78)
    u16 = lambda o: struct.unpack_from("<H", mm, o)[0]      # noqa: E731
    print(f"  {'MB range':<20} {'read':>7} {'padding':>8} {'UNREAD CONTENT':>15}")
    for lo, hi, _ in regions:
        offs = [o for o in pos if lo <= o <= hi
                and mm[o+4] <= 30 and mm[o+5] <= 30
                and 0 < u16(o+10) < 20000 and u16(o+12) in L.YEARS]
        c = coverage(mm, lo, hi + LIGHT_STRIDE, offs)
        print(f"  {lo/1e6:8.3f}-{hi/1e6:8.3f} {c['read']/c['total']:>6.1%} "
              f"{c['pad']/c['total']:>8.1%} {c['unread_content']:>10,} "
              f"({c['unread_content']/c['total']:.1%})")

    print("\n" + "=" * 78)
    print("1d. GATE COST -- what each tuned constant rejects, measured one at a time")
    print("=" * 78)
    for lo, hi, _ in regions[:6]:
        cand, rej = gate_costs(mm, valid, lo, hi + LIGHT_STRIDE)
        print(f"\n  region {lo/1e6:.3f}-{hi/1e6:.3f} MB   candidates (two valid club tids): {cand:,}")
        for gate, n in sorted(rej.items(), key=lambda kv: -kv[1]):
            print(f"     rejected by {gate:<26} {n:>8,}  ({n/cand:5.1%})" if cand else "")

    if args.variants:
        print("\n" + "=" * 78)
        print("1c. VARIANT INVENTORY -- tid separations that reproduce a known scoreline")
        print("=" * 78)
        print("  Counted as DISTINCT FIXTURES EXPLAINED, not site-hits: scores are small")
        print("  numbers, so any single site is cheap coincidence. A real layout explains")
        print("  many different fixtures at the SAME (separation, score offset).\n")
        recs = L.sweep(mm, valid, lo=0, hi=len(mm), min_copies=1)
        got = {(r["home"], r["away"], r["scoreH"], r["scoreA"]) for r in recs}
        explains = defaultdict(set)          # (sep, soff) -> {fixture labels}
        missing_only = defaultdict(set)
        for rnd, fx in iter_truth(truth):
            h, a, hg, ag = fx["home"], fx["away"], fx["hg"], fx["ag"]
            known = (h, a, hg, ag) in got or (a, h, ag, hg) in got
            for _, sep, soff in find_all_sites(mm, h, a, hg, ag):
                if soff is None:
                    continue
                explains[(sep, soff)].add(fx["label"])
                if not known:
                    missing_only[(sep, soff)].add(fx["label"])
        n_tot = sum(len(r["fixtures"]) for r in truth["rounds"])
        print(f"  {'tid sep':>9} {'score@':>7} {'fixtures':>9} {'of which CURRENTLY MISSING':>28}")
        ranked = sorted(explains.items(), key=lambda kv: -len(kv[1]))
        for (sep, soff), fixtures in ranked[:14]:
            miss = len(missing_only.get((sep, soff), ()))
            tag = "  <-- the layout sweep() reads" if (sep, soff) in ((2, 4), (-2, 4)) else ""
            print(f"  {sep:>+9} {soff:>+7} {len(fixtures):>5}/{n_tot:<3} {miss:>21}{tag}")
        best = [(k, v) for k, v in ranked if k not in ((2, 4), (-2, 4))
                and len(missing_only.get(k, ())) >= 3]
        print()
        if best:
            print("  CANDIDATE SECOND LAYOUT(S) -- explain >=3 fixtures we currently miss:")
            for (sep, soff), fixtures in best[:5]:
                print(f"     tids {sep:+} apart, score at +{soff}: "
                      f"{sorted(missing_only[(sep, soff)])[:3]}")
        else:
            print("  No (separation, score-offset) explains 3+ of the missing fixtures.")
            print("  -> the misses are NOT a second tid-pair layout. Either the score is")
            print("     encoded (nibbles/single byte), or the opponent is not stored as a")
            print("     tid at all (slot index into the competition's team list).")

    print("\n" + "=" * 78)
    print(f"HEADLINE: {hits}/{tot} verified fixtures recovered. "
          f"{len(regions) - len(current)} region(s) the current finder never sweeps.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
