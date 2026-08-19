#!/usr/bin/env python3
"""Dump EVERY stride-16 row of a save region between two byte offsets, fully decoded.

This is the tool that cracked the career-history format (2026-08-19). The question was why
131 rows "broke the counter sequence" between two players only 53 sid-ranks apart; rather
than keep guessing delimiter rules, we printed all 765 rows with every field decoded and read
them. The answer -- two interleaved series, because `+4` is a next-row POINTER and not a
counter at all -- was obvious within a minute of looking at the dump.

Keep it for the next byte-level hunt: when a structural theory keeps almost working, dump a
span between two known-good anchors and read it. The `*` column flags rows whose `+4` does not
continue the +1 sequence -- i.e. where a chain jumps.

    uv run python scripts/dump_history_span.py <save.fms> <lo> <hi> [--db fm-frem.duckdb]
"""
import sys, struct

FF = 0xFFFFFFFF


def club_names(db):
    try:
        import duckdb
    except ImportError:
        return {}
    try:
        con = duckdb.connect(db, read_only=True)
        rows = con.execute(
            "SELECT tid, arg_max(name, phase) FROM staging.clubs WHERE name IS NOT NULL GROUP BY tid"
        ).fetchall()
        con.close()
        return dict(rows)
    except Exception as e:                     # locked DB / missing store -- names are optional
        print(f"# (no club names: {e})", file=sys.stderr)
        return {}


def main():
    path, lo, hi = sys.argv[1], int(sys.argv[2].replace(",", "")), int(sys.argv[3].replace(",", ""))
    db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "fm-frem.duckdb"
    names = club_names(db)

    with open(path, "rb") as f:
        f.seek(lo)
        buf = f.read(hi - lo + 16)

    prev_cnt = None
    print(f"# {path}  rows {lo:,}..{hi:,}  ({(hi - lo) // 16 + 1} rows of 16 bytes)")
    print("#   idx  offset      | club        fee   | counter      d | seas  ap  gl  as | "
          "+12 +13 +14 +15 | raw")
    for i in range(0, len(buf) - 15, 16):
        r = buf[i:i + 16]
        off = lo + i
        club, fee, cnt = struct.unpack_from("<HHI", r)
        seas, ap, gl, ast = r[8], r[9], r[10], r[11]
        d = "" if prev_cnt is None else ("FF" if cnt == FF else f"{cnt - prev_cnt:+d}")
        mark = " " if (cnt == FF or d in ("+1", "")) else "*"      # * = sequence break
        cname = names.get(club, "")
        cs = f"{club:5d} {cname[:14]:<14s}" if club != 0xFFFF else f"{'-':>5s} {'(none)':<14s}"
        cnts = "FFFFFFFF" if cnt == FF else f"{cnt:8d}"
        print(f"{mark}{i // 16:5d}  {off:,} | {cs} {fee:5d} | {cnts} {d:>6s} | "
              f"{seas:4d} {ap:3d} {gl:3d} {ast:3d} | {r[12]:3d} {r[13]:3d} {r[14]:3d} {r[15]:3d} | "
              f"{r.hex(' ')}")
        prev_cnt = cnt


main()
