# Match position encoding — SOLVED (2026-08-29)

**Every starter's on-pitch position (GK/DR/DL/DC/DMC/DML/DMR/MR/ML/MC/AMR/AML/AMC/FC) is in the
save, immediately after the formation string.** It is NOT in the per-player stat block — that was
checked exhaustively first and is a dead end (see "What is NOT there").

## The encoding

Directly after the `FORMATION_MARKER` (`76 b9 f4 07`) + the ASCII formation string (e.g.
`"4-1-4-1"`), skip the zero padding, then read **11 pairs of 2 bytes — one per starting slot, in
XI order** (same order as `posOrder` 1..11).

```
pair = [band_byte][column_byte]

band_byte & 0x7f :  0x01 GK   0x04 D   0x08 DM   0x10 M   0x20 AM   0x40 ST
band_byte & 0x80 :  wide-LEFT flag
column_byte      :  0x08 wide-right | 0x04 right-of-centre | 0x02 centre
                    0x01 left-of-centre | 0x00 wide-left (paired with the 0x80 flag)
```

Position = band + laterality:

| band | col `0x08` | `0x80` flag set | otherwise |
|---|---|---|---|
| `D`  | `DR`  | `DL`  | `DC`  |
| `DM` | `DMR` | `DML` | `DMC` |
| `M`  | `MR`  | `ML`  | `MC`  |
| `AM` | `AMR` | `AML` | `AMC` |
| `GK` | — | — | `GK` |
| `ST` | — | — | `FC` |

```python
BAND = {0x01:'GK', 0x04:'D', 0x08:'DM', 0x10:'M', 0x20:'AM', 0x40:'ST'}

def fm_position(band_byte, col_byte):
    left = bool(band_byte & 0x80)
    band = BAND.get(band_byte & ~0x80)
    if band in ('GK', 'ST'):
        return 'GK' if band == 'GK' else 'FC'
    wide_r = (col_byte == 0x08)
    prefix = {'D':'D', 'DM':'DM', 'M':'M', 'AM':'AM'}[band]
    return prefix + ('R' if wide_r else ('L' if left else 'C'))
```

## Validation — two independent careers

- **Bucaspor 2022-04-30** (Karacabey 3-3 Bucaspor, `data/ground_truth_match1.json`, 4-1-2-2-1):
  **11/11 PERFECT** — `GK DR DL DC DC DMC MC MC AMR AML FC`.
- **Frem 2024-09-15** (FCM 0-5 Frem, in-game screenshot, 4-1-4-1): **10/11** — only the most
  advanced slot differs (decoded `FC`, screen showed `AMC`), which is the mid-match-change caveat
  below, not a decode error.
- **Shape self-check: 34/34.** Collapsing the 11 decoded bands back into a formation string
  reproduces the save's own stored formation string for every match in `frem-2024-11-10.fms`,
  across ten distinct shapes (4-4-2, 4-1-2-2-1, 3-2-2-1-2, 5-1-2-1-1, 4-2-2-2, 3-3-2-2, …). This
  is a free, self-contained regression test — no screenshots needed.

## The trap: the save stores ONE moment, the stats screen shows another

**If the manager changes formation mid-match, the stored formation + slot array will NOT match the
post-match stats screen.** The save keeps a single formation per match; the stats screen labels
players by a different snapshot. This cost real debugging time — decoded slots were validated
against screenshots, appeared contradictory ("two 4-1-4-1 games differing by one byte"), and only
made sense once the manager confirmed he'd changed shape during the game.

**Always validate the decode against the save's own formation string (34/34, self-checking), not
against a post-match screenshot.** See [[ground-truth-beats-my-parse]] — that note still holds, but
the ground truth here has to be a moment-matched one.

Related: the formation string itself is the *named* formation. FMM lets you drag players off the
named shape, so `3-2-2-1-2` in the save can present as `3-1-4-2` on the pitch. The slot array is
the truth about where players actually lined up at the stored moment.

## Reserve fixtures have no positions at all

All 13 reserve (tid 7296) matches in `frem-2024-11-10.fms` carry a **byte-identical** slot array
(a default 4-4-2). In game, reserve match stats show no position labels — just numbers 1-16, GK at
1, bench from 12. Reason: the array only carries meaning when a manager assigns a tactic; the AI
reserve side never does. So:

- **Do not trust reserve-match positions** — they are a default, not a lineup.
- A byte-identical array across matches is the tell that the club was AI-managed.

## What is NOT there (checked exhaustively — do not re-hunt)

The 54-byte per-player match stat block does **not** encode position. Verified against 44
known (label, match) pairs spanning 12 distinct position labels, plus 68 GK samples and 46 CB
samples:

- No single byte is constant-per-label and distinct-across-labels — every "constant" hit was
  already-known filler (`0x00` padding or `0xFF` sentinel).
- No byte correlates with pitch depth or left/right side (only `posOrder` @+41 correlates with
  depth, and that is already parsed).
- No 2-byte window matches squad size / slot counts.
- The 8-byte inter-block delimiter is always `ff`×8; the 16 bytes before a block are the previous
  block's tail.
- `b24` (range 1-20) is NOT a substitution counter (`20 − subs` hit 4/68, noise).

Also ruled out: the coordinate-looking tuples after the formation string's zero padding are a
**formation-picker menu preset** (static shape templates for the UI), not per-match data.

## Adjacent findings from the same investigation

**The XI walker truncates at 11 blocks (BUG).** `looks_like_block`/`is_block_start` require
`1 <= condition(b[3]) <= 100`, but **unused substitutes carry `condition = 0xFF`**, so the walk
aborts at the first unused sub. In `frem-2024-11-10.fms`: 16 of 34 matches truncated, 184 player
blocks never parsed, and **26 of those actually played** (`subOn != 255`) — real lost appearances.
The tell in the region map: the "gap" between the two XIs is `247` bytes normally but `681` when
truncated, and `681 − 247 = 434 = 7 × 62` (exactly 7 unparsed block strides). Fix by stopping on
`posOrder` rather than requiring a plausible `condition`.

**The 988-byte post-header region is a structured goal/event list.** Fixed size in every match,
laid out as 17-byte records; the populated ones decode to that match's scorers in chronological
order (verified: Frem 3-1 Vejle → Mucolli 9', Chukwuani 38', Ementa 77', Ementa 86'). We currently
recover events by scanning *backwards* from the header for byte patterns (`parse_events`,
`back=380`) — this table is the structured source and should replace that heuristic.

## Match section region map

Per match, ~5,170 bytes (`frem-2024-11-10.fms`, 35 anchors, 270 KB region). Before this
investigation ~45% was parsed:

| Region | Size | Status |
|---|---|---|
| `DELIM_UNIT` cluster | 80 B | parsed (anchor detection) |
| pre-header gap | ~256 B | events, via fragile backward scan |
| HEADER `[home u16][away u16][day u16][year u16][att u16]` | 10 B | parsed |
| post-header block | **988 B (fixed)** | **goal list, 17-byte records** |
| HOME XI | 18 × 62 B | parsed (54-byte block + 8-byte delim) |
| gap between XIs | 247 B (681 when truncated) | **unparsed bench blocks — see bug above** |
| AWAY XI | 18 × 62 B | parsed |
| trailer → formation | 203 B | still unknown |
| `FORMATION_MARKER` + string | 13 B | parsed (string only) |
| **slot array** | **22 B** | **position encoding (this note)** |
| tail → next anchor | ~1,140 B | partly unknown (menu presets + team sliders?) |

Only one formation string exists per match region — we are not picking the wrong one.

## Next steps

1. Fix the bench-truncation bug (restores 26 appearances in the current save alone).
2. Emit `position` per player-match from the slot array through `staging` → `mart`, so unit
   analysis can separate DM from CM and DC from DR/DL instead of bucketing raw `pos_order`
   (`dashboard`/`mart` currently hardcode `pos_order IN (2,3) → Fullbacks`, which is wrong for any
   back-3 shape).
3. Consider replacing `parse_events` with the 988-byte record table.

Both 1 and 2 touch `fmparser/matches.py` and need one reload of all snapshots — do them together.
