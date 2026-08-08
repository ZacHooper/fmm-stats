#!/usr/bin/env python3
"""
Discover the section layout of an .fms save from its own structure, so region
bounds are DERIVED per-save instead of hard-coded (see regions.py, which holds
Bucaspor-tuned constants that drift as saves grow / differ between careers).

The save is delimited by long runs of `00` bytes: big zero-gaps separate the
major sections. Within record sections, `ff ff ff ff` runs pad/delimit records,
and some regions are fixed-stride "pages". This module:

  1. `sections(mm, min_gap)` — split the file on zero-gaps >= min_gap.
  2. detectors — each looks at one section and, if it recognises the shape,
     returns a (kind, detail) label. Add detectors here as regions get decoded;
     the first that matches wins, else `characterize()` gives a generic texture.
  3. `discover(mm)` — the labelled Region list for a whole save.

Deliberately signature-anchored: each Region carries the first bytes of the
section, so the same region can be recognised across saves even when it moves.

Everything here is pure-stdlib (mmap only), like the other extractors.
"""
from dataclasses import dataclass, asdict
import mmap


# --------------------------------------------------------------------------- skeleton
def zero_gaps(mm, min_gap=8192):
    """Offsets+lengths of every run of >= min_gap zero bytes (the section delimiters).
    Uses a probe search so it's fast on a 60MB file."""
    n = len(mm)
    probe = b"\x00" * min_gap
    out = []
    i = mm.find(probe)
    while i != -1:
        s = i
        while s > 0 and mm[s - 1] == 0:
            s -= 1
        e = i
        while e < n and mm[e] == 0:
            e += 1
        out.append((s, e - s))
        i = mm.find(probe, e)
    return out


def sections(mm, min_gap=8192):
    """List of (start, end) content spans between the big zero-gaps."""
    spans = []
    prev = 0
    for s, ln in zero_gaps(mm, min_gap):
        if s > prev:
            spans.append((prev, s))
        prev = s + ln
    if prev < len(mm):
        spans.append((prev, len(mm)))
    return spans


# --------------------------------------------------------------------------- helpers
def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def _sample(mm, a, b, cap=60000):
    return mm[a:min(b, a + cap)]


def _printable_frac(seg):
    return sum(1 for c in seg if 32 <= c < 127) / max(1, len(seg))


def _ff_frac(seg):
    return seg.count(0xff) / max(1, len(seg))


def _walk_strtable(mm, start, end, maxlen=40, limit=200000):
    """Walk a [len u32][utf-8] concatenated string table from `start`; return the
    list of strings (stops at first non-string). Used by the name-table detector."""
    o = start
    out = []
    while o + 4 < end and len(out) < limit:
        ln = _u32(mm, o)
        if not (1 <= ln <= maxlen):
            break
        raw = mm[o + 4:o + 4 + ln]
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            break
        if not s or any(ord(c) < 0x20 for c in s):
            break
        out.append(s)
        o = o + 4 + ln
    return out, o


# --------------------------------------------------------------------------- detectors
# Each detector: (mm, start, end) -> (kind, detail) or None. Registered in order.

def _detect_name_table(mm, start, end):
    """Flat [len u32][utf-8] name table (the FM master name DB). Skip a small header
    to find the first valid entry, then require a long run of name-shaped strings."""
    probe_end = min(start + 512, end)
    for o in range(start, probe_end):
        ln = _u32(mm, o)
        if 2 <= ln <= 40:
            raw = mm[o + 4:o + 4 + ln]
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if s and s[0].isalpha() and all(ord(c) >= 0x20 for c in s):
                names, endo = _walk_strtable(mm, o, end)
                if len(names) >= 1000:
                    return ("name_table", f"{len(names)} names, entry0@{o}={names[0]!r}")
    return None


def _windows(start, end, n=16, win=65536):
    """Up to `n` evenly-spaced probe windows across a section, so detectors find
    signatures that sit deep inside a big section (history @40.6M, names @58M) at
    bounded cost regardless of section size."""
    span = end - start
    if span <= win:
        return [(start, end)]
    step = max(win, span // n)
    return [(o, min(o + win, end)) for o in range(start, end, step)]


def _detect_history(mm, start, end):
    """Career-history table: 16-byte rows, club-tid u16 at +0, u32 counter at +4 that
    increments +1 across consecutive rows, +12 u32 == 0. Scan probe windows for a run."""
    step = 16
    for wa, wb in _windows(start, end):
        o = wa
        while o + step * 8 < wb:
            run = 1
            while o + step * (run + 1) < end and run < 40:
                a = o + step * (run - 1)
                b = o + step * run
                if _u32(mm, b + 4) == _u32(mm, a + 4) + 1 and _u32(mm, a + 12) == 0 \
                   and 1 <= _u16(mm, a) <= 60000:
                    run += 1
                else:
                    break
            if run >= 8:
                return ("history_table", f"stride-16 rows @{o} ({o/1e6:.3f}M), first club={_u16(mm, o)}")
            o += step
    return None


def _detect_inline_names(mm, start, end):
    """Snapshot inline player records (~58M): a 'First Last' full name followed by
    length-prefixed echoes of the parts — …Rasmus Wedege[06]Rasmus[06]Wedege… . The
    first-name echo right after the full name is the distinctive signature that
    separates real player records from competition/other capitalised text."""
    import re
    pat = re.compile(rb"([A-Z\xc6\xd8\xc5][a-z\xe6\xf8\xe5]+) [A-Z\xc6\xd8\xc5][a-z\xe6\xf8\xe5]+")
    echoes = 0
    example = None
    where = None
    seg = mm[start:end]
    for m in pat.finditer(seg):
        first = m.group(1)
        e = m.end()
        if seg[e:e + 4] == len(first).to_bytes(4, "little") and seg[e + 4:e + 4 + len(first)] == first:
            echoes += 1
            if example is None:
                example = m.group(0).decode("latin-1")
                where = start + m.start()
    if echoes >= 5:
        return ("inline_names", f"{echoes} player records, first @{where/1e6:.3f}M e.g. {example!r}")
    return None


def _characterize(mm, start, end):
    """Generic fallback: texture + record-delimiter stats."""
    seg = _sample(mm, start, end)
    pf, ff = _printable_frac(seg), _ff_frac(seg)
    tags = []
    if pf > 0.65:
        tags.append(f"text({pf*100:.0f}%)")
    if ff > 0.15:
        tags.append(f"ff-records({ff*100:.0f}%)")
    if not tags:
        tags.append("binary")
    # fixed-stride page detection: spacing between ffffffff runs
    stride = _page_stride(seg)
    if stride:
        tags.append(f"pages~{stride}B")
    return ("data", " ".join(tags))


def _page_stride(seg):
    """If ff-runs recur at a near-constant spacing, return that stride, else None."""
    marks = []
    i = seg.find(b"\xff\xff\xff\xff")
    while i != -1 and len(marks) < 64:
        marks.append(i)
        i = seg.find(b"\xff\xff\xff\xff", i + 4)
    if len(marks) < 8:
        return None
    diffs = [b - a for a, b in zip(marks, marks[1:]) if 8 <= b - a <= 4096]
    if len(diffs) < 6:
        return None
    diffs.sort()
    med = diffs[len(diffs) // 2]
    near = sum(1 for d in diffs if abs(d - med) <= 2)
    return med if near >= len(diffs) * 0.6 else None


DETECTORS = [_detect_name_table, _detect_history, _detect_inline_names]


# --------------------------------------------------------------------------- discover
@dataclass
class Region:
    start: int
    end: int
    kind: str
    detail: str
    sig: str          # hex of first 16 bytes (anchor to recognise across saves)

    @property
    def size(self):
        return self.end - self.start


def discover(mm, min_gap=8192, min_section=2048):
    """Labelled Region list for the whole save. `min_section` drops tiny fragments
    (the 38–39M zone breaks into hundreds of sub-KB records; roll those up)."""
    out = []
    for a, b in sections(mm, min_gap):
        if b - a < min_section:
            continue
        label = None
        for det in DETECTORS:
            try:
                label = det(mm, a, b)
            except Exception:
                label = None
            if label:
                break
        if not label:
            label = _characterize(mm, a, b)
        out.append(Region(a, b, label[0], label[1], mm[a:a + 16].hex()))
    return out


def sub_regions(mm):
    """Content-located regions that sit INSIDE a bigger zero-gap section (so the
    skeleton splitter can't isolate them) but are self-locating by signature. This
    is the 'locate sub-regions inside the big sections' iteration of the map — add
    more as they get decoded. Currently: the per-match region (delimiter clusters
    with plausible date/opponent headers), which drifts per-career and used to be a
    hard-coded MATCH_LO. Returns a list of (start, end, kind, detail)."""
    out = []
    try:
        from . import matches as _M
        reg = _M.find_match_region(mm)
        if reg:
            anchors = _M.match_anchors(mm, lo=reg[0], hi=reg[1])
            out.append((reg[0], reg[1], "matches",
                        f"{len(anchors)} match blocks (delimiter-clustered), "
                        f"self-located @{reg[0]/1e6:.3f}M"))
    except Exception:
        pass
    return out


def discover_path(path, **kw):
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            return discover(mm, **kw)
        finally:
            mm.close()


def sub_regions_path(path):
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            return sub_regions(mm)
        finally:
            mm.close()


def as_dicts(regions):
    return [dict(asdict(r), size=r.size) for r in regions]
