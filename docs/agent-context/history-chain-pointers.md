---
name: history-chain-pointers
description: "SOLVED: career-history +4 is a NEXT-ROW POINTER (linked lists), and the player link is u32 @ P-38 in the attribute record"
metadata:
  type: reference
---

**The career-history table is a forest of LINKED LISTS, not an array.** `+4` holds the
0-based index of the **next row in that player's chain**; `FFFFFFFF` = end of chain. On a
fresh save every record is contiguous so row `k` holds `k+1` — indistinguishable from a
counter, which is why v1 read it that way and why `FFFFFFFF` looked like a record trailer.
Seasons played DURING the career are appended into **recycled slots**, so the chain jumps
and the `+1` sequence breaks *inside* a record. Every "sequence break = new record" rule
over-split established saves ~2.5×.

**Record starts = rows with in-degree 0.** Exact, no heuristics. Audit any candidate table
with `max in-degree == 1` and `#(in-degree-0) == #(FFFFFFFF)` — true on all 10 frem saves.
The slab is **fixed-size: 265,423 rows in every frem save**; only the byte offset drifts,
and `u32 @ (start-12)` is that count. v1's locator was picking a FALSE header mid-table.

**THE PLAYER LINK RUNS THE OTHER WAY — `u32 @ P-38`.** The history table contains no
tid/sid/uid at all; the player's **attribute record** points at it. Anchored on the `P` that
`staging.scrape_attributes` computes: `[SID u32 @ P-42][history chain head u32 @ P-38]`.
25,627/25,627 in-range values are valid chain heads, all distinct. Positional sid-order DP
is obsolete. Don't re-derive `P` by hand — being off by one 78-byte grid step returns a
*neighbouring* player's career, which looks totally plausible in a youth-intake cohort.

**THE READING RULE (one rule, everywhere):** walking a chain gives `[h, r1, r2, …]`; for each
row `k` after the head, **season+stats come from row `k-1`, club+fee from row `k`.** The head
supplies only the youth/origin club, and the trailing debut row is consumed as a club row so it
never becomes a phantom season. Verified twice over: 4 of the matched stat lines are globally
unique in 265k rows and every one sits at `pointer-1`, AND all five career TOTALS match exactly.
It fixes transfer years too — same-row reading put Dirksen at Frem from 2018/19 when he signed
for 2017/18. (An earlier "stats are staggered, but only in the appended region" framing was the
same fact mis-read; ignore it.)

**SHIPPED 2026-08-19**: `fmparser/history.py` rewritten on this model (numpy; `build(mm, info,
attrs)` now takes `attrs` for the P-38 link), wired into `extract.py`, loader carries the new
assists/rating/debut columns. All 10 frem saves parse, 21.4k-23.6k players each — **8 of them
previously returned zero rows**. `scripts/history_v2.py` is a thin debugging CLI that prints
the TOTAL line for diffing against a screenshot. Base year 1971 confirmed. Full story:
`docs/agent-context/player-history-table.md`, link write-up in `docs/IDS.md`.

**Method that cracked it:** dump every byte between two known anchors to a text file and
read it (the user's call), then search the whole slab for the ground-truth stat line and
look at where it landed vs the prediction. Related: [[player-history-table]],
[[name-resolution]], [[tid-recycling]].
