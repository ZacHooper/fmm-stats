#!/usr/bin/env python3
"""
Profile every field of every datadict entity to make meanings inferable ->
docs/dd_anatomy.txt.

    python3 scripts/dd_anatomy.py <save.fms> [entity1 entity2 ...]

For each entity type, segments its records (opener `<Tag> 0x0a` + `id 0x02 -><Tag>`) and,
per child field, reports: occurrence count, type(s), int range, a sample of distinct values,
and HEURISTIC hints (bool / day-of-week / month / year / HHMM time / club-tid-like /
uid-like / entity-ref / ascii). Feeds the manual decode that fills scripts/dd_doc.py KNOWN.
Pure-stdlib.
"""
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fmparser.save import Save                       # noqa: E402
from fmparser import tagged as T                     # noqa: E402


def locate(mm):
    hits, i = [], mm.find(b"pmoc")
    while i != -1:
        hits.append(i)
        i = mm.find(b"pmoc", i + 1)
    hits.sort()
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] <= 500_000:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    best = max(clusters, key=len)
    return best[0] - 60_000, best[-1] + 300_000


def segment(mm, lo, hi):
    """Yield (entity, [(tag, typ, val)]) records."""
    p, cur_ent, cur = lo, None, []
    while p < hi - 6:
        if mm[p] == 0:
            p += 1
            continue
        f = T.read_field(mm, p)
        if not f:
            p += 1
            continue
        tg, typ, val, nxt = f
        opener = False
        if typ == 0x0a:
            nf = T.read_field(mm, nxt)
            if nf and nf[0] == "id" and nf[1] == 0x02 and \
               mm[nxt + 6:nxt + 10][::-1].decode("latin-1", "replace").strip() == tg:
                opener = True
        if opener:
            if cur_ent is not None:
                yield cur_ent, cur
            cur_ent, cur = tg, []
        else:
            ref = mm[p + 6:p + 10][::-1].decode("latin-1", "replace").strip() if typ == 0x02 else None
            cur.append((tg, typ, ("->" + ref) if ref else val))
        p = nxt
    if cur_ent is not None:
        yield cur_ent, cur


def hint(vals):
    """Heuristic label for a field from its distinct int values."""
    ints = [v for v in vals if isinstance(v, int)]
    if not ints:
        refs = [v for v in vals if isinstance(v, str)]
        return "ref(" + ",".join(sorted(set(refs))[:4]) + ")" if refs else "?"
    lo, hi = min(ints), max(ints)
    st = set(ints)
    tags = []
    if st <= {0, 1}:
        tags.append("bool")
    if 1 <= lo and hi <= 7 and len(st) <= 7:
        tags.append("dow?")
    if 1 <= lo and hi <= 12 and len(st) <= 12:
        tags.append("month?")
    if all(2000 <= v <= 2035 for v in ints):
        tags.append("year")
    if all(0 <= v <= 2359 for v in ints) and any(v > 100 for v in ints) and all(v % 100 < 60 for v in ints):
        tags.append("HHMM?")
    if any(100 <= v < 70000 for v in ints) and hi < 70000:
        tags.append("clubtid-like")
    if any(v >= 1_000_000_000 for v in ints):
        tags.append("uid/2e9")
    if not tags:
        tags.append(f"int[{lo}..{hi}]")
    return ",".join(tags)


def profile(mm, lo, hi, only=None):
    byent = defaultdict(list)
    for ent, fields in segment(mm, lo, hi):
        byent[ent].append(fields)
    out = []
    ents = only or [e for e, r in sorted(byent.items(), key=lambda x: -len(x[1]))]
    for ent in ents:
        recs = byent.get(ent, [])
        if not recs:
            continue
        fcount = Counter()
        fvals = defaultdict(list)
        ftypes = defaultdict(Counter)
        for r in recs:
            for tg, typ, val in r:
                fcount[tg] += 1
                ftypes[tg][f"0x{typ:02x}"] += 1
                if len(fvals[tg]) < 400:
                    fvals[tg].append(val)
        out.append(f"\n===== {ent}  ({len(recs)} records) =====")
        for tg, c in fcount.most_common():
            distinct = list(dict.fromkeys(fvals[tg]))[:10]
            samp = ", ".join(str(x) for x in distinct)[:70]
            tstr = ",".join(ftypes[tg])
            h = hint(fvals[tg])
            out.append(f"  {tg:6} x{c:<5} {tstr:9} {h:22} e.g. {samp}")
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 scripts/dd_anatomy.py <save.fms> [entity ...]")
    s = Save(sys.argv[1])
    mm = s.mm
    lo, hi = locate(mm)
    only = sys.argv[2:] or None
    text = profile(mm, lo, hi, only=only)
    dest = os.path.join(ROOT, "docs", "dd_anatomy.txt")
    open(dest, "w").write(f"datadict anatomy — {os.path.basename(sys.argv[1])} "
                          f"region {lo/1e6:.3f}-{hi/1e6:.3f}M\n" + text + "\n")
    print(f"wrote {dest} ({text.count(chr(10))} lines)")
    s.close()


if __name__ == "__main__":
    main()
