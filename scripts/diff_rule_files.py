#!/usr/bin/env python3
"""Structural diff of one rule file between two saves (any game: FMM22 against FMM27 works).

    uv run python scripts/diff_rule_files.py <save A> <file A> <save B> [<file B>] [--all]

Reads each file from the save's data dictionary (`fmparser.tables.rule_files`) and walks
both tag trees side by side. A container's children are matched by tag; a list's elements by
their own `id` (a stage's `leag`, `grou`, ...), else their round name (`stnm`; `mnsn` in a
ranking list), else their position. Prints:

  - A only / B only   a tag (with the size of its subtree) on one side only
  - changed           a scalar whose value differs
  - type              a tag whose type code differs (u8 -> u16 is a widening, not a change)

Empty containers and lists are skipped unless `--all`: FMM22 writes many empty lists FMM27
omits. A four-character code stored as a u32 prints as its characters.
"""
import argparse
import mmap
import os
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import rule_files as RF  # noqa: E402

Field = Tuple[Any, int, Any]
NUMERIC = {0x01, 0x03, 0x11, 0x12, 0x13, 0x14, 0x15, 0x18}


def load(path: str, name: str) -> List[Field]:
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for b in RF.all_blocks(mm):
        if RF.is_rule_file(b) and b.get("file") == name:
            return b.fields
    raise SystemExit(f"{name!r} not in {os.path.basename(path)}")


def show(v: Any) -> str:
    if isinstance(v, int) and v >= 1 << 24:
        b = v.to_bytes(4, "big")
        if all(32 <= c < 127 for c in b):
            return f"'{b.decode()}'"
    if isinstance(v, str):
        return repr(v)
    return str(v)


def size(v: Any) -> str:
    if not isinstance(v, list):
        return f"= {show(v)}"
    n = sum(1 for _ in walk(v))
    return f"[{len(v)} children, {n} nodes]"


def walk(fields: List[Field]):
    for t, typ, v in fields:
        yield t
        if isinstance(v, list):
            yield from walk(v)


def name_id(v: Any) -> Any:
    """A round-name reference as stored: a scalar, a pair (n, n), or `{stgn <id>, ...}`."""
    if isinstance(v, list):
        v = next((cv for ct, _, cv in v if ct == "stgn"), None)
    if isinstance(v, tuple):
        v = v[0]
    return v


def label(field: Field, i: int) -> str:
    """How a list element is matched: its `id` code, else its round name (`stnm`, or
    `mnsn` in a ranking list), else its position."""
    t, typ, v = field
    if isinstance(v, list):
        kids = {ct: cv for ct, _, cv in v}
        if "id" in kids:
            return show(kids["id"])
        for tag in ("stnm", "mnsn"):
            n = name_id(kids.get(tag))
            if isinstance(n, int):
                return f"{tag}={n}"
    return f"#{i}"


def keyed(fields: List[Field], is_list: bool) -> Dict[str, Field]:
    out: Dict[str, Field] = {}
    for i, f in enumerate(fields):
        k = label(f, i) if is_list else str(f[0])
        n, base = 2, k
        while k in out:                     # repeated tag or id: number the repeats
            k, n = f"{base}~{n}", n + 1
        out[k] = f
    return out


def empty(v: Any) -> bool:
    return isinstance(v, list) and not v


def diff(a: List[Field], b: List[Field], path: str, is_list: bool, everything: bool,
         out: List[str]) -> None:
    ka, kb = keyed(a, is_list), keyed(b, is_list)
    for k in list(ka) + [k for k in kb if k not in ka]:
        p = f"{path}[{k}]" if is_list else f"{path}/{k}"
        fa, fb = ka.get(k), kb.get(k)
        if fb is None or fa is None:
            t, typ, v = fa or fb
            if everything or not empty(v):
                out.append(f"{'A only' if fb is None else 'B only':8} {p} {size(v)}")
            continue
        (_, ta, va), (_, tb, vb) = fa, fb
        la, lb = isinstance(va, list), isinstance(vb, list)
        if la and lb:
            diff(va, vb, p, ta == 0x0b, everything, out)
        elif la or lb:
            out.append(f"{'type':8} {p} {size(va)} -> {size(vb)}")
        elif va != vb:
            out.append(f"{'changed':8} {p} {show(va)} -> {show(vb)}")
        elif ta != tb and not (ta in NUMERIC and tb in NUMERIC):
            out.append(f"{'type':8} {p} type {ta:#x} -> {tb:#x}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("save_a")
    ap.add_argument("file_a")
    ap.add_argument("save_b")
    ap.add_argument("file_b", nargs="?")
    ap.add_argument("--all", action="store_true", help="include empty containers and lists")
    args = ap.parse_args()
    a = load(args.save_a, args.file_a)
    b = load(args.save_b, args.file_b or args.file_a)
    out: List[str] = []
    diff(a, b, "", False, args.all, out)
    print(f"A = {args.file_a} ({os.path.basename(args.save_a)})")
    print(f"B = {args.file_b or args.file_a} ({os.path.basename(args.save_b)})")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
