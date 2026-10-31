"""Replace one rule file in a save's data dictionary.

A competition's rules live in the dictionary (`fmparser/tables/rule_files.py`) and, while the
competition is loaded, in its archive member `comp_<uid>.dat`. The game rebuilds the member
from the dictionary on the competition's update day (`updy`; 11 June for the Champions Cup):
across the Frem saves the member's header season moves on, its runtime state resets, and a
competition with dated rule files swaps to the dictionary's other version
(`eng_fm_cup_even_years` -> `_odd_years` between 2029-06-15 and 2029-06-30). So a rules change
is made in the dictionary, in a save dated before the update day, and the archive is left
alone.

A rule file is `[u32 n][n tagged fields]`; nothing else in the save holds its offset or byte
length (no u32 anywhere matches the dictionary's or the archive's offsets, or the file size),
and the whole dictionary already moves by hundreds of bytes from save to save. The patch
therefore rewrites the block in place, with its count, and shifts the rest of the file.
"""
import mmap
from typing import Callable, List

from fmparser.tables import rule_files as RF

from . import tagged as T

__all__ = ["PatchError", "patch_rule_file"]


class PatchError(Exception):
    pass


def _rule_file(mm, name: str):
    hits = [b for b in RF.RULE_FILES_TABLE.blocks(mm) if b.get("file") == name]
    if len(hits) != 1:
        raise PatchError(f"{len(hits)} rule files named {name!r}; expected exactly one")
    return hits[0]


def patch_rule_file(src: str, dst: str, name: str,
                    edit: Callable[[List[T.Node]], None]) -> dict:
    """Write `src` to `dst` with rule file `name` rewritten by `edit` (which mutates the
    top-level Nodes in place). Returns what changed. Verifies the result re-reads: the same
    667 rule files, the edited one equal to the edit, every other one byte-identical, and the
    dictionary's group framing intact."""
    with open(src, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        blocks = RF.RULE_FILES_TABLE.blocks(mm)
        b = _rule_file(mm, name)
        idx = next(i for i, x in enumerate(blocks) if x.start == b.start)
        if int.from_bytes(mm[b.start - 4:b.start], "little") != len(b.fields):
            raise PatchError(f"{name}: the u32 before the block is not its field count")
        nodes, end = T.parse_block(mm, b.start, len(b.fields))
        old = bytes(mm[b.start:end])
        if T.encode_block(nodes) != old:
            raise PatchError(f"{name}: does not round-trip; refusing to write")
        edit(nodes)
        new = T.encode_block(nodes)
        others = [bytes(mm[x.start:x.end]) for i, x in enumerate(blocks) if i != idx]
        out = (bytes(mm[:b.start - 4]) + len(nodes).to_bytes(4, "little") + new
               + bytes(mm[end:]))
        mm.close()
    with open(dst, "wb") as f:
        f.write(out)

    with open(dst, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        blocks = RF.RULE_FILES_TABLE.blocks(mm)
        if len(blocks) != len(others) + 1 or blocks[idx].get("file") != name:
            raise PatchError("the dictionary no longer reads as the same list of rule files")
        if bytes(mm[blocks[idx].start:blocks[idx].end]) != new:
            raise PatchError("the patched rule file does not read back as written")
        if [bytes(mm[x.start:x.end]) for i, x in enumerate(blocks) if i != idx] != others:
            raise PatchError("a rule file other than the patched one changed")
        problems = RF.framing_problems(mm)
        if problems:
            raise PatchError(f"dictionary framing broken: {problems[:3]}")
        mm.close()
    return {"rule_file": name, "old_bytes": len(old), "new_bytes": len(new),
            "shift": len(new) - len(old), "size": len(out)}
