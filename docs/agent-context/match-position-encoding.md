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

## The trap: the save stores ONE moment (the START), the stats screen can show another

**If the manager changes formation mid-match — including reshuffling roles around a
substitution — the stored formation + slot array will NOT match the post-match stats screen.**
Two confirmed cases:

- **Vejle, 2024-11-10**: stored `3-2-2-1-2`, in-game tactics screenshot showed `3-1-4-2`.
- **Frem 1-3 FCN, 2024-08-04**: stored `5-1-2-1-1` (verified against 3 independent checks —
  unique anchor for that date, header tids/score exact match to the screenshot, formation
  marker 1,187 B clear of the next match), full-time screenshot showed `4-1-2-2-1` (Ellegaard
  AMR / Tånnander AML, not the AMC + 5th CB the save stores). Manager confirmed he subbed Garly
  for Ellegaard and reshuffled others around it.

**Searched the whole match span for a second formation record and found none** — one
`FORMATION_MARKER` occurrence only, and the 22-byte slot array is immediately duplicated once
(same bytes, twice) rather than a second, later state. **The save appears to commit to a single
formation — most likely the starting XI's shape — and never revisits it.** That is the working
theory, not a proven fact: we have not found a change-event to positively confirm it, only the
absence of a second array in every match checked so far.

**Practical consequence: treat every decoded position as "who started where," full stop.** There
is currently no way to recover a mid-match reshuffle from the save, and no way to tell, from the
byte data alone, whether a given match had one. A full-time stats screenshot is therefore
**only valid ground truth if the manager is sure nothing changed that game** — a pre-kickoff
Tactics → Formation screenshot is safer, since it can't be contaminated by in-match changes.

**Always validate the decode against the save's own formation string (34/34, self-checking) as
the first check, since it needs no screenshot at all.** See [[ground-truth-beats-my-parse]] — that
note still holds, but the ground truth here has to be a moment-matched one.

## Known limitation: bands with 4+ members lose the inner left/right split

The column byte isn't binary (wide-right vs "everything else") — it's an **ordinal rank across
the whole band**, and different formations put different numbers of players in a band. Confirmed
values seen per band: D up to 5 (`0x00+L, 0x01, 0x02, 0x04, 0x08`), M up to 4, AM up to 2 seen so
far but the D/M evidence says more slots exist. The current decoder only distinguishes the two
edges (`0x08` = rightmost, `0x80` flag = leftmost) and folds every interior value to the centre
letter (`DC`/`MC`/`AMC`). That is right for a 3-member band (there's no code for
"left-of-two-CBs" in FM's own 15-code vocabulary either) but **silently wrong for wider bands**:

- **Confirmed via a within-player check**: in a flat 4-1-4-1, Frederik Ellegaard is `col=0x04`
  and Isak Tånnander is `col=0x01` in **every one of 10 separate matches**, both nominally "MC".
  The manager's own recollection was that Ellegaard is right-sided, Tånnander left — the
  consistent, stable column split matches that exactly. FM's on-screen label is genuinely `MC` for
  both (no finer code exists), but the underlying data preserves which side, and analysis that
  cares about that (see [[match-rating-position-bias]]) should use it.
- **Suspected, not yet confirmed**: the AM-band `AMC`/`AMC` case above (2024-08-25) is probably the
  same phenomenon and probably really `AMR`/`AMC` — needs ground truth.

**Do not trust `DC`/`MC`/`AMC` from this decoder as truly central without checking `col`
directly** when the band has more than 2-3 members that match. `slot_position()` needs a revision
that uses the full ordinal rank, not just the two edges, once there's enough ground truth to derive
the right mapping (rank 0 of N → leftmost, rank N-1 of N → rightmost, for whatever N that match's
band actually has).

## Positions are STARTING positions only — nothing past kick-off is recoverable

See "The trap" above for the full story. The load-bearing rule for any consumer of `position`:
**it describes who started where, and that is the only thing the save commits to.** A manager
reshuffling around a substitution (confirmed real example: subbing a DM off for an AM and moving
players to cover) changes nothing in the stored array. Do not read `position` as "what this player
did all match," and do not use a full-time stats screenshot as ground truth unless the manager
confirms nothing changed that game.

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

**The ~1,140-byte tail after the slot array is NOT confidently parsed.** An earlier pass called it
a "static UI preset menu" from a single side-by-side comparison; that was underpowered. A proper
multi-match diff (7 matches sharing formation `4-1-2-2-1`) instead found:

- **Two matches with byte-IDENTICAL slot arrays → byte-IDENTICAL tails**, 0 bytes differing across
  1,158 bytes each.
- **One match with a different fine-grained slot array (see below) → 192 bytes differing**, starting
  almost immediately after the slot array, not just within its duplicate.
- The remaining pairs (identical slot array, different match) differed by only 2-6 bytes, all
  clustered right at the very end of the tail (offsets ~1130-1153) — small, unidentified,
  match-specific values that do not obviously correlate with attendance (checked, no match).

**Working conclusion: the bulk of the tail is very likely DERIVED FROM the slot array** — plausibly
a pitch-diagram coordinate rendering keyed off the same band/column bytes — rather than
independent team-instruction data, since it tracks slot-array changes exactly and stays identical
when the slot array does. Not proven; nothing has been decoded to a specific meaning. The few
bytes that vary even with an identical slot array are a live open thread.

### A second interior-column ambiguity, found via this diff

The "different slot array" match above (2024-08-25, still `4-1-2-2-1` by formation string) decodes
its AM band as **`AMC AMC`** — both players get column values `0x04` and `0x01`, neither the
wide-right byte (`0x08`) nor the left flag. This is the *same* pattern already found for
Ellegaard/Tånnander in the M band ("Known limitation" below): a band with more than 2 members has
more than 2 real lateral positions, and the current decoder collapses every non-edge column value
to the centre letter. **This match is very likely actually `AMR`/`AML`, not `AMC`/`AMC`** — needs a
screenshot to confirm, not yet checked.

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
| slot array (duplicate) | 22 B | confirmed a verbatim repeat, not new data |
| tail → next anchor | ~1,120 B | derived-from-slots (probable), not decoded to a meaning |

Only one formation string and one slot array exist per match — confirmed no second occurrence
anywhere in a match's span (searched, one hit). No mid-match change record exists; see "Positions
are STARTING positions only" above.

## Status (2026-08-29): position decode SHIPPED. Two threads still open.

1. **Interior column ranks for 4+ member bands** — the DC/MC/AMC collapse above. Needs more
   ground truth (ideally a screenshot for a band with exactly the pattern seen at 2024-08-25) to
   derive the right rank → letter mapping.
2. **The tail past the slot array** — probably derived from the slots, not independently
   informative, but not proven and nothing in it is decoded. The small per-match diff at the very
   end of the tail (2-6 bytes, unidentified) is the most promising remaining thread if anyone
   wants to keep pulling it.

Already done: the bench-truncation bug is fixed, `position` is emitted through `staging` →
`mart` (`fmparser/mart.py`'s `unit` derivation replaces the old `pos_order IN (2,3) →
Fullbacks` bucketing, which was wrong for any back-3 shape), and `parse_events` still uses the
old backward-scan heuristic — the 988-byte goal-list table would be a cleaner replacement
whenever someone gets to it, but nothing is broken today.
