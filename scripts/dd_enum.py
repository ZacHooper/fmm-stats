#!/usr/bin/env python3
"""
Enumerate the tagged data-dictionary of an .fms save -> docs/dd_inventory.json.

    python3 scripts/dd_enum.py <save.fms>

Pure-stdlib. Locates the datadict by the `comp` tag cluster (it drifts per save, like
every region — see denmark-region-drift), raw-walks every tagged field, segments records
by the `<Tag> 0x0a` + `id 0x02 -><Tag>` opener, and records per-field stats + per-entity
child fields. Feed the JSON to scripts/dd_doc.py to (re)build docs/DATADICT.md tables.
"""
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fmparser.save import Save                       # noqa: E402
from fmparser import tagged as T                     # noqa: E402


def locate(mm):
    """Datadict region = the densest cluster of the `comp` (reversed 'pmoc') tag."""
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


def enumerate_dd(mm, lo, hi):
    field = defaultdict(lambda: {"count": 0, "types": Counter(), "samples": [],
                                 "imin": None, "imax": None, "ent_refs": Counter()})
    records = Counter()
    ent_fields = defaultdict(Counter)
    cur_ent = None
    p = lo
    while p < hi - 6:
        if mm[p] == 0:
            p += 1
            continue
        f = T.read_field(mm, p)
        if not f:
            p += 1
            continue
        tg, typ, val, nxt = f
        ref = None
        if typ == 0x02:
            ref = mm[p + 6:p + 10][::-1].decode("latin-1", "replace").strip()
        if typ == 0x0a:
            nf = T.read_field(mm, nxt)
            if nf and nf[0] == "id" and nf[1] == 0x02:
                rref = mm[nxt + 6:nxt + 10][::-1].decode("latin-1", "replace").strip()
                if rref == tg:
                    cur_ent = tg
                    records[tg] += 1
        d = field[tg]
        d["count"] += 1
        d["types"][f"0x{typ:02x}"] += 1
        if ref is not None:
            d["ent_refs"][ref] += 1
        elif isinstance(val, int):
            d["imin"] = val if d["imin"] is None else min(d["imin"], val)
            d["imax"] = val if d["imax"] is None else max(d["imax"], val)
        sv = ("->" + ref) if ref is not None else val
        if len(d["samples"]) < 8 and sv not in d["samples"]:
            d["samples"].append(sv)
        if cur_ent and tg != cur_ent:
            ent_fields[cur_ent][tg] += 1
        p = nxt
    return field, records, ent_fields


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 scripts/dd_enum.py <save.fms>")
    s = Save(sys.argv[1])
    mm = s.mm
    lo, hi = locate(mm)
    field, records, ent_fields = enumerate_dd(mm, lo, hi)
    out = {
        "save": os.path.basename(sys.argv[1]),
        "region": [lo, hi],
        "fields": {t: {"count": d["count"], "types": dict(d["types"]),
                       "int_range": [d["imin"], d["imax"]],
                       "ent_refs": dict(d["ent_refs"].most_common(6)),
                       "samples": d["samples"][:8]} for t, d in field.items()},
        "records": dict(records.most_common()),
        "ent_fields": {e: dict(c.most_common(20)) for e, c in ent_fields.items()},
    }
    dest = os.path.join(ROOT, "docs", "dd_inventory.json")
    json.dump(out, open(dest, "w"), indent=1, default=str)
    print(f"{sys.argv[1]}: region {lo/1e6:.3f}-{hi/1e6:.3f}M  "
          f"{len(field)} field tags, {len(records)} entity types -> {dest}")
    s.close()


if __name__ == "__main__":
    main()
