#!/usr/bin/env python3
"""
Materialize and decode the save's tagged data dictionary (~17.0-20.8 MB).

Sits on top of `fmparser/tagged.py` (wire-format primitives) and turns the whole region
into a **local, self-contained JSON store** so the raw `.fms` never needs to be parsed
again, plus tooling to *understand* it (schema report, cross-reference decoder, human
labels). See docs/DATADICT.md.

WIRE FORMAT (fully decoded here; richer than tagged.py's original subset):
  A field is `[tag: 4 bytes REVERSED][0x01 marker][type][value]`, or tagless
  `[0x01][type][value]` (tag "~"). Value size depends on type:

    type            size            meaning
    0x01 0x0b 0x13   4              u32   (0x0b semantics unconfirmed -> kept raw)
    0x02             4              entity-type reference (a reversed 4-char tag)
    0x03 0x11        1              u8
    0x12             2              u16
    0x14             8              u64
    0x0a             4 + children   CONTAINER: value = child count; children follow.
                                    Three forms: id-headed record (`<tag> 0a <n>` then
                                    `id 02 <tag>` then n children), headerless container
                                    (`<tag> 0a <n>` then n children), anonymous
                                    (`~ 0a <n>` then n children).
    0x1a             4 + len        STRING: value = byte length, then that many bytes.

RECORD = an id-headed 0x0a container; its tag names the entity (comp, stdt, fxds, ...).
Records NEST. The region also holds loose fields, anonymous containers, and non-tagged
binary fragments (a fixed-format preamble ~17.0-17.5 MB). Anything not parseable and not
zero-padding is captured verbatim as a raw hex blob, so the store is byte-complete.
"""
import re

from . import tagged

LO, HI = tagged.TAGGED_LO, tagged.TAGGED_HI

CONTAINER = 0x0a
STRING = 0x1a
FIXED = {0x01: 4, 0x02: 4, 0x0b: 4, 0x13: 4, 0x03: 1, 0x11: 1, 0x12: 2, 0x14: 8}
KNOWN_TYPES = set(FIXED) | {CONTAINER, STRING}

# On-disk types whose meaning isn't fully confirmed -> keep raw bytes inline as a 3rd
# element of the field pair, so the value can be reinterpreted later without the save.
AMBIGUOUS_TYPES = {0x0b}

_MAX_STRLEN = 1_000_000       # sanity bound so a mis-read length can't run off the region


def _printable4(b):
    return len(b) == 4 and all(0x20 <= x < 127 for x in b)


def _header(mm, q, hi):
    """Peek a tagged field header at q: (tag, type, value_pos) or None."""
    if q + 6 > hi:
        return None
    t = mm[q:q + 4]
    if _printable4(t) and mm[q + 4] == 0x01:
        return t[::-1].decode("latin-1").strip(), mm[q + 5], q + 6
    return None


def _value(mm, typ, vpos, hi):
    """(json_value, next_p, raw_bytes) for a scalar/string value at vpos, or None."""
    if typ == STRING:
        if vpos + 4 > hi:
            return None
        n = int.from_bytes(mm[vpos:vpos + 4], "little")
        if n > _MAX_STRLEN or vpos + 4 + n > hi:
            return None
        return mm[vpos + 4:vpos + 4 + n].decode("latin-1", "replace"), vpos + 4 + n, None
    sz = FIXED[typ]
    if vpos + sz > hi:
        return None
    raw = mm[vpos:vpos + sz]
    if typ == 0x02:
        return raw[::-1].decode("latin-1", "replace").strip(), vpos + sz, raw
    return int.from_bytes(raw, "little"), vpos + sz, raw


def _parse(mm, p, hi, records=None, types=None, parent="~root"):
    """Parse one field (recursively) at p. Returns (pair, next_p) or None.
    `pair` is a JSON field: [tag, value] (value = int | str | list-of-pairs), with a 3rd
    raw-hex element for ambiguous types. Tagless fields use tag "~".
    Optional sinks (for the schema/decoders; the JSON dump doesn't use them):
      records -> every id-headed record at ANY depth as {"entity", "offset", "fields"}.
      types   -> every field as (parent_tag, tag, on_disk_type, value, is_container)."""
    hdr = _header(mm, p, hi)
    if hdr:
        tag, typ, vpos = hdr
    elif mm[p] == 0x01 and mm[p + 1] in KNOWN_TYPES:
        tag, typ, vpos = "~", mm[p + 1], p + 2
    else:
        return None

    if typ == CONTAINER:
        if vpos + 4 > hi:
            return None
        n = int.from_bytes(mm[vpos:vpos + 4], "little")
        q = vpos + 4
        record = False
        idf = _header(mm, q, hi)                      # id-headed record?
        if idf and idf[0] == "id" and idf[1] == 0x02:
            ref = mm[idf[2]:idf[2] + 4][::-1].decode("latin-1", "replace").strip()
            if ref == tag:
                q = idf[2] + 4                        # skip the id field
                record = True
        if types is not None:
            types.append((parent, tag, typ, None, True))
        kids = []
        for _ in range(n):
            c = _parse(mm, q, hi, records, types, tag)
            if not c:
                break
            kids.append(c[0])
            q = c[1]
        if record and records is not None:
            records.append({"entity": tag, "offset": p, "fields": kids})
        return [tag, kids], q

    if typ not in KNOWN_TYPES:
        return None
    v = _value(mm, typ, vpos, hi)
    if not v:
        return None
    val, nxt, raw = v
    if types is not None:
        types.append((parent, tag, typ, val, False))
    if typ in AMBIGUOUS_TYPES:
        return [tag, val, raw.hex()], nxt
    return [tag, val], nxt


def is_record(mm, p, hi=HI):
    """True if p starts an id-headed record (`<tag> 01 0a <n>` + `id 02 <tag>`)."""
    if not (p + 6 <= hi and mm[p + 4] == 0x01 and mm[p + 5] == CONTAINER
            and _printable4(mm[p:p + 4])):
        return False
    tag = mm[p:p + 4][::-1].decode("latin-1").strip()
    idf = _header(mm, p + 10, hi)
    if not (idf and idf[0] == "id" and idf[1] == 0x02):
        return False
    ref = mm[idf[2]:idf[2] + 4][::-1].decode("latin-1", "replace").strip()
    return ref == tag


# --------------------------------------------------------------------------- stream
def walk_stream(mm, lo=LO, hi=HI):
    """Single forward pass over the region, yielding every top-level item in order:
        ("rec",   entity, offset, pair)    id-headed record (pair = [entity, [fields]])
        ("field", tag,    offset, pair)    loose field / anonymous or headerless container
        ("raw",   None,   offset, hexstr)  non-padding bytes we couldn't parse (verbatim)
        ("pad",   None,   offset, length)  a run of 0x00 padding
    This is byte-complete: every byte in [lo, hi) falls into exactly one item."""
    p = lo
    while p < hi:
        if mm[p] == 0x00:                              # padding run
            q = p
            while q < hi and mm[q] == 0x00:
                q += 1
            yield "pad", None, p, q - p
            p = q
            continue
        res = _parse(mm, p, hi)
        if res and res[1] > p:
            pair, nxt = res
            if is_record(mm, p, hi):
                yield "rec", pair[0], p, pair
            else:
                yield "field", pair[0], p, pair
            p = nxt
            continue
        # raw blob: consume until the next padding byte or a parseable position
        q = p + 1
        while q < hi and mm[q] != 0x00:
            r = _parse(mm, q, hi)
            if (r and r[1] > q) or is_record(mm, q, hi):
                break
            q += 1
        yield "raw", None, p, mm[p:q].hex()
        p = q


# ------------------------------------------------------------------------- coverage
def coverage(mm, lo=LO, hi=HI):
    """Byte-accounting proof of losslessness. Every byte is tagged / raw / padding;
    unaccounted is 0 by construction. Reports the raw runs (candidates for decoding)."""
    tagged_b = raw_b = pad_b = 0
    recs = fields = 0
    raw_runs = []
    items = list(walk_stream(mm, lo, hi))
    for i, (kind, _, off, data) in enumerate(items):
        span = (items[i + 1][2] if i + 1 < len(items) else hi) - off
        if kind == "pad":
            pad_b += span
        elif kind == "raw":
            raw_b += span
            raw_runs.append((off, span))
        else:
            tagged_b += span
            recs += (kind == "rec")
            fields += (kind == "field")
    raw_runs.sort(key=lambda r: -r[1])
    total = tagged_b + raw_b + pad_b
    return {
        "region": [lo, hi],
        "region_bytes": hi - lo,
        "accounted_bytes": total,
        "unaccounted_bytes": (hi - lo) - total,
        "tagged_bytes": tagged_b,
        "raw_bytes": raw_b,
        "padding_bytes": pad_b,
        "tagged_pct": round(100 * tagged_b / (hi - lo), 2),
        "raw_pct": round(100 * raw_b / (hi - lo), 2),
        "records": recs,
        "loose_fields": fields,
        "raw_runs": len(raw_runs),
        "largest_raw_runs": [{"offset": o, "len": n} for o, n in raw_runs[:20]],
    }


# --------------------------------------------------------------------------- collect
def all_records(mm, lo=LO, hi=HI):
    """Every id-headed record at ANY nesting depth, in document order, as
    {"entity", "offset", "fields"}. Nested records also live inside their parent's
    fields, so a nested `comp` appears both here (its own entry) and inside its parent."""
    sink = []
    for kind, _, off, _ in walk_stream(mm, lo, hi):
        if kind in ("rec", "field"):
            _parse(mm, off, hi, records=sink)
    return sink


def collect(mm, lo=LO, hi=HI):
    """{entity: [record, ...]} of every id-headed record (any depth) -> per-entity files."""
    out = {}
    for r in all_records(mm, lo, hi):
        out.setdefault(r["entity"], []).append(
            {"offset": r["offset"], "fields": r["fields"]})
    return out


def _safe_name(entity):
    s = re.sub(r"[^0-9A-Za-z_-]", "_", entity.strip())
    return s or "_"


# --------------------------------------------------------------------------- schema
TYPE_MEANING = {
    "0x1": "u32", "0x2": "entity-ref", "0x3": "u8", "0xa": "container",
    "0xb": "u32?", "0x11": "u8", "0x12": "u16", "0x13": "u32", "0x14": "u64",
    "0x1a": "string",
}


def schema_report(mm, lo=LO, hi=HI):
    """Auto-derived data dictionary: per-tag stats (types, cardinality, min/max, samples,
    parents), per-entity field schemas, and the container nesting graph. Covers every one
    of the ~1000+ field tags mechanically — the instrument the semantic decode works from.
    """
    from collections import Counter, defaultdict

    types = []
    for kind, _, off, _ in walk_stream(mm, lo, hi):
        if kind in ("rec", "field"):
            _parse(mm, off, hi, types=types)

    tag_count = Counter()
    tag_types = defaultdict(Counter)
    tag_container = Counter()
    tag_values = defaultdict(Counter)
    tag_parents = defaultdict(Counter)
    nesting = defaultdict(Counter)
    type_dist = Counter()
    for parent, tag, typ, val, cont in types:
        h = hex(typ)
        tag_count[tag] += 1
        tag_types[tag][h] += 1
        type_dist[h] += 1
        tag_parents[tag][parent] += 1
        nesting[parent][tag] += 1
        if cont:
            tag_container[tag] += 1
        elif isinstance(val, int):
            tag_values[tag][val] += 1

    tags = {}
    for tag, c in tag_count.most_common():
        vals = tag_values[tag]
        entry = {
            "count": c,
            "types": {t: n for t, n in tag_types[tag].most_common()},
            "as_container": tag_container[tag],
            "distinct_values": len(vals),
            "samples": [[v, n] for v, n in vals.most_common(10)],
            "parents": {p: n for p, n in tag_parents[tag].most_common(8)},
        }
        if vals:
            entry["min"], entry["max"] = min(vals), max(vals)
        tags[tag] = entry

    per = collect(mm, lo, hi)
    entities = {}
    for entity, recs in sorted(per.items(), key=lambda kv: -len(kv[1])):
        fc = Counter()
        ex = {}
        for r in recs:
            for f in r["fields"]:
                t = f[0]
                fc[t] += 1
                if t not in ex:
                    ex[t] = "{...}" if isinstance(f[1], list) else f[1]
        n = len(recs)
        entities[entity] = {
            "count": n,
            "fields": [{"tag": t, "present": k, "pct": round(100 * k / n),
                        "example": ex[t]} for t, k in fc.most_common()],
        }

    return {
        "type_distribution": [{"type": t, "meaning": TYPE_MEANING.get(t, "?"),
                               "count": n} for t, n in type_dist.most_common()],
        "tag_count": len(tags),
        "entity_count": len(entities),
        "entities": entities,
        "nesting": {p: {t: n for t, n in c.most_common(15)}
                    for p, c in nesting.items()},
        "tags": tags,
    }


def schema_markdown(schema):
    """Render schema_report() output as a human-readable Markdown data dictionary."""
    L = ["# Tagged data dictionary — auto-derived schema", "",
         "Machine-generated by `fmparser/datadict.py::schema_report`. Do not hand-edit; "
         "curated meanings live in DATADICT.md.", "",
         f"- **{schema['entity_count']}** entity types, **{schema['tag_count']}** distinct "
         f"field tags.", "",
         "## On-disk value types", "", "| type | meaning | fields |", "|---|---|---|"]
    for t in schema["type_distribution"]:
        L.append(f"| `{t['type']}` | {t['meaning']} | {t['count']:,} |")

    L += ["", "## Entities (by record count)", ""]
    for entity, e in schema["entities"].items():
        fields = ", ".join(f"`{f['tag']}`" + ("*" if f["pct"] == 100 else "")
                           for f in e["fields"][:16])
        L.append(f"- **`{entity}`** ×{e['count']:,} — {fields}")

    L += ["", "## Field tags (by frequency)", "",
          "| tag | count | type(s) | distinct | min | max | samples |",
          "|---|---|---|---|---|---|---|"]
    for tag, t in sorted(schema["tags"].items(), key=lambda kv: -kv[1]["count"]):
        typs = ",".join(t["types"])
        mn = t.get("min", "")
        mx = t.get("max", "")
        smp = " ".join(str(v) for v, _ in t["samples"][:5])[:40]
        L.append(f"| `{tag}` | {t['count']:,} | {typs} | {t['distinct_values']} "
                 f"| {mn} | {mx} | {smp} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------ crossref
# Ground-truth anchors (docs/IDS.md): known IDs whose appearances reveal what a tag means.
KNOWN_CLUBS = {955: "Galatasaray", 954: "Fenerbahce", 951: "Besiktas",
               961: "Trabzonspor", 356: "Liverpool", 6567: "Bucaspor",
               6353: "Karacabey"}
KNOWN_COMP_UID = {463485: "cid 228 Turkish 2.League White"}
KNOWN_NATION = {173: "Turkey"}
DATE_DOMAINS = {"dyow": (0, 6), "dyom": (1, 31), "mont": (1, 12), "year": (1900, 2100)}


def _ascii_code(v):
    """If v is a u32 whose 4 little-endian bytes are printable, return that string."""
    if not isinstance(v, int) or not (0 <= v < 2**32):
        return None
    b = v.to_bytes(4, "little")
    if all(0x20 <= c < 127 for c in b):
        return b.decode("latin-1")
    return None


def crossref(mm, schema=None, lo=LO, hi=HI):
    """Automated label suggestions. Two parts:
      reverse_index — for each known anchor ID (club TID, comp uid, nation), the tags that
                      hold it and how often (answers 'which tag carries club 955?').
      tag_candidates — per-tag heuristic meaning (date part, enum, tier, packed 4-char
                      code, holds-club/comp/nation) from value domains + anchor hits."""
    from collections import Counter, defaultdict

    if schema is None:
        schema = schema_report(mm, lo, hi)

    anchors = {}
    anchors.update({k: ("club", v) for k, v in KNOWN_CLUBS.items()})
    anchors.update({k: ("comp_uid", v) for k, v in KNOWN_COMP_UID.items()})
    anchors.update({k: ("nation", v) for k, v in KNOWN_NATION.items()})

    tag_anchor = defaultdict(Counter)             # tag -> Counter(anchor_key)
    types = []
    for kind, _, off, _ in walk_stream(mm, lo, hi):
        if kind in ("rec", "field"):
            _parse(mm, off, hi, types=types)
    for _parent, tag, _typ, val, cont in types:
        if not cont and isinstance(val, int) and val in anchors:
            kind_, label = anchors[val]
            tag_anchor[tag][f"{kind_}:{val} ({label})"] += 1

    # reverse index: anchor -> tags
    reverse = defaultdict(dict)
    for tag, c in tag_anchor.items():
        for key, n in c.items():
            reverse[key][tag] = n

    # per-tag candidates
    cands = {}
    for tag, t in schema["tags"].items():
        c = []
        mn, mx, distinct = t.get("min"), t.get("max"), t["distinct_values"]
        samples = [v for v, _ in t["samples"]]
        if tag in tag_anchor:
            for key, n in tag_anchor[tag].most_common():
                c.append(f"holds {key} ×{n}")
        if tag in DATE_DOMAINS and mn is not None:
            lo_d, hi_d = DATE_DOMAINS[tag]
            if mn >= lo_d and mx <= hi_d:
                c.append(f"date part ({tag})")
        if mn is not None and 0 <= mn and mx <= 27 and distinct <= 30 and t["as_container"] == 0:
            c.append(f"small ordinal / tier (0..{mx})")
        codes = [s for v in samples if (s := _ascii_code(v))]
        if len(codes) >= 2 and mx and mx > 2**24:
            c.append(f"packed 4-char code, e.g. {codes[:3]}")
        if 1 < distinct <= 12 and t["as_container"] == 0 and mx is not None and mx <= 255:
            c.append(f"enum {{{', '.join(str(v) for v in samples[:8])}}}")
        if c:
            cands[tag] = c

    return {
        "reverse_index": {k: dict(sorted(v.items(), key=lambda kv: -kv[1]))
                          for k, v in sorted(reverse.items())},
        "tag_candidates": cands,
    }


# --------------------------------------------------------------------------- dump
def dump_json(mm, dest, lo=LO, hi=HI):
    """Write the whole region to `dest/` as JSON: one file per entity, a lossless ordered
    stream (`_stream.json`), a byte-accounting manifest (`_coverage.json`), and an index
    (`_index.json`). Returns the coverage manifest. Requires only stdlib json/os."""
    import json
    import os

    os.makedirs(dest, exist_ok=True)

    # lossless ordered master: every top-level item (records inline w/ their nesting,
    # loose fields, and raw blobs). Padding (zeros) is omitted; it carries no data.
    stream = []
    for kind, _, off, data in walk_stream(mm, lo, hi):
        if kind == "pad":
            continue
        stream.append({"o": off, "raw": data} if kind == "raw" else {"o": off, "f": data})

    # friendly per-entity view: every id-headed record at any depth
    per = collect(mm, lo, hi)
    names = {}                                   # entity -> filename stem (sanitized)
    used = set()
    for entity in per:
        stem = _safe_name(entity)
        base = stem
        k = 1
        while stem in used:                      # avoid filename collisions after sanitize
            k += 1
            stem = f"{base}~{k}"
        used.add(stem)
        names[entity] = stem

    def _dump(name, obj):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False)

    for entity, recs in per.items():
        _dump(names[entity] + ".json", recs)
    _dump("_stream.json", stream)

    schema = schema_report(mm, lo, hi)
    _dump("_schema.json", schema)
    with open(os.path.join(dest, "_schema.md"), "w") as f:
        f.write(schema_markdown(schema))
    _dump("_crossref.json", crossref(mm, schema, lo, hi))

    cov = coverage(mm, lo, hi)
    record_count = sum(len(v) for v in per.values())
    _dump("_coverage.json", cov)
    _dump("_index.json", {
        "region": [lo, hi],
        "entity_count": len(per),
        "record_count": record_count,
        "stream_items": len(stream),
        "entities": {e: {"file": names[e] + ".json", "records": len(per[e])}
                     for e in sorted(per, key=lambda e: -len(per[e]))},
    })
    cov["entity_count"] = len(per)
    cov["record_count"] = record_count
    return cov
