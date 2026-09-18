#!/usr/bin/env python3
"""
Reader for the save's self-describing TAGGED data dictionary (~16.6-21 MB; the exact
region DRIFTS per save and per career and is derived by find_tagged_region).

This region is a hierarchical, relational database of everything competition-related:
competitions, standings, fixtures, teams-in-comps, nations, prize money, etc. It's the
proper source for club->league membership and league tables (see docs/DATADICT.md).

FORMAT (fully decoded):
  field  = [tag: 4 bytes, stored REVERSED][0x01 marker][type: 1 byte][value: size(type)]
  record = an `id`(type 0x02) header naming the entity type, then its fields; records
           NEST (a standings table `sdfd` contains child rows each with their own `id`).
  records are separated by `00 00` padding.

TYPE -> value size:
  0x01, 0x0a, 0x0b, 0x13 = u32 (4)   0x02 = 4-byte entity-type reference (a reversed tag)
  0x03, 0x11             = u8  (1)   0x12 = u16 (2)   0x14 = u64 (8)

Entity types (id -> X), most common: comp (competitions), stnm/stag (stages), Ttea/team
(teams in comps), stdt/endt (start/end dates), fxds (fixtures), sdfd (STANDINGS:
comp+team+posn+rank), nmsn/nssn/sbsn (season), nati (nations), przm/wnpz/cash (prize
money). Full catalogue in docs/DATADICT.md.
"""
from .save import cache_key as _cache_key

# FALLBACK ONLY — see find_tagged_region. These bounds were measured on Bucaspor, whose
# region starts at 17.50 MB. Frem's starts at 16.64-16.79 MB, so TAGGED_LO opened AFTER the
# section did and silently cut 13-23% of the dictionary off the FRONT (1,623 `comp` records
# on frem-2021-07-01), which cost 11-15 of the 93 competitions in every Frem snapshot ever
# built. Identical failure to the one regions.py documents for REFDATA_LO. The region is
# DERIVED per save now; these are kept only for the no-hits fallback path.
TAGGED_LO, TAGGED_HI = 17_000_000, 20_800_000

TYPE_SIZE = {0x01: 4, 0x0a: 4, 0x0b: 4, 0x13: 4, 0x02: 4,
             0x03: 1, 0x11: 1, 0x12: 2, 0x14: 8}

# on-disk tag bytes are the field name reversed; a couple used below
_TAG_ID = b"  di"     # "id  "
_TAG_COMP = b"pmoc"   # "comp"
_TAG_NTMS = b"smtn"   # "ntms" (number of teams)

# find_tagged_region tuning. The cluster gap and the margins are all RELATIVE, so they
# travel between saves and careers — which is the entire point.
_CLUSTER_GAP = 500_000      # two `comp` tags this far apart start a new cluster
_MARGIN_LO, _MARGIN_HI = 60_000, 300_000

# Keyed via save.cache_key -- (id(mm), len(mm)), NOT id(mm) alone. CPython reuses the id of
# a freed object, so a loop that opens one save after another serves the previous save's
# region for the next one; caught exactly that way here (Bucaspor came back with Frem's
# bounds and lost 829 records). See `save.cache_key` for the full story and the second time
# it bit, in reference.py.
_REGION_CACHE = {}          # save.cache_key -> (lo, hi)


def find_tagged_region(mm):
    """(lo, hi) for the tagged data dictionary, DERIVED from this save's own content.

    The region is the densest cluster of the `comp` tag. This is the locator
    `scripts/dd_enum.py` and `scripts/dd_anatomy.py` have used all along — their docstring
    says the region "drifts per save, like every region" — promoted here so the parser gets
    it too instead of trusting a hand-tuned constant. Measured on two careers, the cluster
    start lands within ~4 KB of the first real record (frem-2026: 16.751M vs 16.755M;
    frem-2021: 16.636M vs 16.639M).

    Deliberately NOT `mapregions.sections()`: at the default min_gap that returns one
    35.7 MB span (16.7M-52.4M), ~9.4x this window, and `datadict.walk_stream` calls two
    functions per byte over any unstructured run. The `comp` cluster gives the right
    POSITION at roughly the current SIZE.

    Falls back to the static TAGGED_LO/TAGGED_HI if the tag is absent, matching
    `matches.find_match_region` and `attributes.snapshot_bounds`.
    """
    key = _cache_key(mm)
    cached = _REGION_CACHE.get(key)
    if cached is not None:
        return cached

    hits, i = [], mm.find(_TAG_COMP)
    while i != -1:
        hits.append(i)
        i = mm.find(_TAG_COMP, i + 1)
    if not hits:                                  # no tag at all -> trust the old window
        _REGION_CACHE[key] = (TAGGED_LO, TAGGED_HI)
        return _REGION_CACHE[key]

    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] <= _CLUSTER_GAP:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    best = max(clusters, key=len)
    region = (max(0, best[0] - _MARGIN_LO), min(len(mm), best[-1] + _MARGIN_HI))
    _REGION_CACHE[key] = region
    return region


def _bounds(mm, lo, hi):
    """Resolve caller-supplied bounds, deriving either end left as None."""
    if lo is None or hi is None:
        d_lo, d_hi = find_tagged_region(mm)
        lo = d_lo if lo is None else lo
        hi = d_hi if hi is None else hi
    return lo, hi


def _is_field(mm, p):
    t = mm[p:p + 4]
    return (all(0x20 <= b < 127 for b in t)
            and mm[p + 4] == 0x01 and mm[p + 5] in TYPE_SIZE)


def read_field(mm, p):
    """(tag, type, value, next_p) for the tagged field at p, or None. Type-0x02 values
    decode to the referenced entity-type tag (string); others to little-endian ints."""
    if not _is_field(mm, p):
        return None
    tag = mm[p:p + 4][::-1].decode("latin-1").strip()
    typ = mm[p + 5]
    sz = TYPE_SIZE[typ]
    raw = mm[p + 6:p + 6 + sz]
    val = raw[::-1].decode("latin-1", "replace").strip() if typ == 0x02 \
        else int.from_bytes(raw, "little")
    return tag, typ, val, p + 6 + sz


def parse_field(mm, p):
    """Parse one field (possibly a nested container) at p. Returns (name, value, next_p):
      - scalar field     -> value is an int (or entity-ref string for type 0x02)
      - tagless field     -> name is '~' (positional value)
      - CONTAINER         -> a `<tag> t0a <n>` opener followed by `id t02 <tag>`; value is
                             a list of n parsed child fields.
    Returns None if p isn't a parseable field."""
    f = read_field(mm, p)
    if not f:
        if mm[p] == 0x01 and mm[p + 1] in TYPE_SIZE:      # tagless positional field
            typ = mm[p + 1]
            sz = TYPE_SIZE[typ]
            return "~", int.from_bytes(mm[p + 2:p + 2 + sz], "little"), p + 2 + sz
        return None
    tag, typ, val, nxt = f
    if typ == 0x0a:                                        # maybe a container opener
        nf = read_field(mm, nxt)
        if nf and nf[0] == "id" and nf[1] == 0x02 and nf[2] == tag:
            q = nf[3]
            kids = []
            for _ in range(val):                          # `val` = child field count
                c = parse_field(mm, q)
                if not c:
                    break
                kids.append((c[0], c[1]))
                q = c[2]
            return tag, kids, q
    return tag, val, nxt


def iter_records(mm, entity, lo=None, hi=None):
    """Yield every top-level record of the given entity type (e.g. 'comp', 'sdfd') as a
    parsed field list. Finds each `<entity> t0a <n>` + `id t02 <entity>` opener.

    Bounds default to `find_tagged_region(mm)` — per-save, not a constant."""
    lo, hi = _bounds(mm, lo, hi)
    on_disk = entity.ljust(4)[:4][::-1].encode("latin-1")
    p = lo
    while p < hi:
        if (mm[p:p + 4] == on_disk and mm[p + 4] == 0x01 and mm[p + 5] == 0x0a):
            nf = read_field(mm, p + 10)
            if nf and nf[0] == "id" and nf[1] == 0x02 and nf[2] == entity:
                rec = parse_field(mm, p)
                if rec:
                    yield p, rec[1]
                    p = rec[2]
                    continue
        p += 1


def walk_fields(mm, lo=None, hi=None):
    """Yield (offset, tag, type, value) for every tagged field in [lo, hi).
    Skips padding and the occasional tagless `[01][type][value]` field.

    Bounds default to `find_tagged_region(mm)` — per-save, not a constant."""
    lo, hi = _bounds(mm, lo, hi)
    p = lo
    while p < hi:
        f = read_field(mm, p)
        if f:
            tag, typ, val, nxt = f
            yield p, tag, typ, val
            p = nxt
        elif mm[p] == 0x01 and mm[p + 1] in TYPE_SIZE:   # tagless field
            p += 2 + TYPE_SIZE[mm[p + 1]]
        else:
            p += 1


# --- legacy helper kept for the competitions reference (extract.build_competitions) ---
def league_team_counts(mm, lo=None, hi=None):
    """{comp_uid: num_teams} from `comp`+`ntms` field pairs. (Superseded by full
    entity parsing once that lands; retained so competitions.json keeps working.)

    Bounds default to `find_tagged_region(mm)` — per-save, not a constant."""
    lo, hi = _bounds(mm, lo, hi)
    out = {}
    p = lo
    while True:
        i = mm.find(_TAG_COMP, p, hi)
        if i == -1:
            break
        p = i + 1
        if mm[i + 4] == 0x01 and mm[i + 5] == 0x01:
            uid = int.from_bytes(mm[i + 6:i + 10], "little")
            j = i + 10
            if mm[j:j + 4] == _TAG_NTMS and mm[j + 4] == 0x01 and mm[j + 5] == 0x11:
                out[uid] = mm[j + 6]
    return out
