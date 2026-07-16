#!/usr/bin/env python3
"""
Decode FMM22 per-match player-stat blocks.

CONFIRMED layout (validated against ground_truth_match1.json — Karacabey 3-3 Bucaspor):
  - Each player block = 54 bytes.
  - Blocks separated by an 8-byte 0xFF delimiter -> stride = 62 bytes.
  - Block starts `00 00 00 <condition>`.
  - Field offsets within the 54-byte block (from the old mojo map, all re-verified):
"""
from fmtool import Save

BLOCK = 54
DELIM = 8
STRIDE = BLOCK + DELIM

# offset -> field name (single byte unless noted)
FIELDS = {
    0: "assists", 3: "condition", 4: "crossA", 5: "crossC", 8: "dribbles",
    10: "goals", 11: "headA", 12: "headW", 16: "intercept", 19: "subOn",
    21: "subOff", 22: "mistakes", 23: "mistGoal", 25: "passA", 26: "passC",
    27: "keyPass", 32: "rating", 35: "shotA", 36: "shotO", 41: "posOrder",
    48: "tackA", 49: "tackW", 53: "yellow",
}
# offset 53 = yellow-card flag (1 = booked). Confirmed vs ground_truth_match1:
# Karacabey HOME pos2 & pos3 booked -> b53=1; Bucaspor AWAY pos6 (Yüksel) booked -> b53=1;
# everyone else 0. Plain yellows are NOT in the header event stream, only here.


def decode_block(b: bytes) -> dict:
    d = {name: b[off] for off, name in FIELDS.items()}
    d["sid"] = b[28:30].hex()
    d["tid"] = b[42:46].hex()
    d["tid_int"] = int.from_bytes(b[42:46], "little")
    d["_raw"] = b.hex()
    return d


def is_block_start(mm, i):
    """A valid 54-byte stat block, identified by stable invariants (NOT by
    byte[0], which is `assists` and can be nonzero):
      - condition byte [3] in 1..100
      - the 5-byte 0xFF run at [13:18] (present in every real block)
      - posOrder [41] in 1..30
      - player TID [42:46] nonzero and plausibly small
    """
    if i + BLOCK > len(mm):
        return False
    return (1 <= mm[i + 3] <= 100
            and mm[i + 17] == 0xff and mm[i + 18] == 0xff and mm[i + 20] == 0xff
            and 1 <= mm[i + 41] <= 30
            and 0 < int.from_bytes(mm[i + 42:i + 46], "little") < 200000)


def walk(mm, start, max_blocks=40):
    """Walk consecutive stat blocks from `start`, stopping when the FF-delimiter
    structure breaks."""
    out = []
    i = start
    for _ in range(max_blocks):
        if not is_block_start(mm, i):
            break
        blk = mm[i:i + BLOCK]
        d = decode_block(blk)
        d["_offset"] = i
        out.append(d)
        # expect 8x FF delimiter next
        delim = mm[i + BLOCK:i + BLOCK + DELIM]
        i += STRIDE
        if delim != b"\xff" * DELIM:
            # structure may vary; note it and stop
            d["_delim_after"] = delim.hex()
            break
    return out


def find_match_start(mm, known_offset):
    """Walk backwards from a known block to the first block of the match."""
    i = known_offset
    while is_block_start(mm, i - STRIDE) and mm[i - STRIDE + BLOCK:i - STRIDE + BLOCK + DELIM] == b"\xff" * DELIM:
        i -= STRIDE
    # also allow walking back one more if the preceding delim precedes i
    while is_block_start(mm, i - STRIDE):
        prev = i - STRIDE
        if mm[prev + BLOCK:prev + BLOCK + DELIM] == b"\xff" * DELIM:
            i = prev
        else:
            break
    return i


if __name__ == "__main__":
    import sys
    s = Save()
    start = int(sys.argv[1], 0) if len(sys.argv) > 1 else 56549031
    blocks = walk(s.mm, start)
    hdr = ["posOrder", "condition", "rating", "passA", "passC", "keyPass",
           "assists", "tackA", "tackW", "intercept", "headA", "headW",
           "crossA", "crossC", "dribbles", "mistakes", "goals", "shotA", "shotO",
           "subOn", "subOff", "tid", "sid"]
    print(f"{'off':>9} " + " ".join(f"{h:>8}" for h in hdr))
    for d in blocks:
        row = " ".join(f"{str(d[h]):>8}" for h in hdr)
        print(f"{d['_offset']:>9} {row}")
    print(f"\n{len(blocks)} blocks decoded from {start} (0x{start:x})")
