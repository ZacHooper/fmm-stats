# tactic_history  ([`fmparser/tables/tactic_history.py`](../../fmparser/tables/tactic_history.py))

**Tactic setups the game has recorded for the user**: a name, and the role set for every
position. Not tactics the user saved: the Truro career has no saved tactic (its one saved
item is a selection, "starting xi", which is in no save measured). Straight after the
[person stamps](person_stamps.md), in a block that belongs to the user's club.

| | records |
|---|---|
| frem-2021-06-27, truro-2026-07-22 (first days) | 1 |
| truro-2026-07-25 | 5 |
| truro-2026-08-08 | 15 |
| frem-2023-07-02 | 11 |
| frem-2026-06-11, frem-2030-06-22 | 30 (a cap: the list stops growing) |
| bucaspor-2023-04-01 | 12 |

## Layout

```
60 B                      unread; a money-sized number at +40 (3.8e10 Truro, 1.8e10 Frem)
[u32 n][n x 14 B]         n people, each [tid u32] + 10 bytes, unread (6 Frem, 3 Bucaspor, 0 Truro)
[u16 count][count x 59 B] the records
```

A record, 59 bytes:

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `gk_role` | u8 | 0, Goalkeeper, on every record measured |
| +1 | | u8 | `ff` |
| +2 | `roles` | 10 × `[role u8][u8][ff]` | the outfield roles in the formation's own position order; the middle byte is 0 or 1, unread |
| +32 | `name` | 26 B | NUL-padded: a formation ("4-4-2 Diamond", "4-1-2-1-2") or "uber tactic" |
| +58 | `flag` | u8 | 0 or 1, unread |

**What the records are.** Most names are formations, one record each (Truro: 5-2-1-2,
4-4-2 Diamond, 5-1-2-2, 4-2-4, 4-1-2-1-2); the rest are "uber tactic", in both careers, so a
name the game gives rather than one a user typed. On truro-2026-08-08 the "uber tactic"
records carry the roles of the user's 4-1-2-1-2 with small changes between them, and the
last record is that 4-1-2-1-2. That reads as a history of setups: roughly one per formation
the user has picked, plus snapshots as roles change, capped at 30. On Frem, full at 30, the
last record is not the formation Frem's matches use. They are not opponents' tactics: the
formations Truro's opponents used (4-5-1, 5-3-2, 4-4-2) are not among them.

The formation's positions are not in the record. The role codes are
[seeds/roles.csv](../../seeds/roles.csv)'s on FMM22; FMM27 keeps the codes up to Inside
Forward and renumbers from there (see [training](training.md)).

**How it is found.** From the person stamps' end, skip the 60-byte block and the counted
14-byte entries; the u16 there counts the records. The locator refuses it unless every record
reads.

## Evidence

`tests/test_tactic_history_evidence.py`, eight saves of both games: every record reads, the
count grows 1, 5, 15 over Truro's first weeks and is 30 on both late Frem saves. On
truro-2026-08-08 the last record is named 4-1-2-1-2, the formation all our match reports
carry, and its first four roles are 3, 3, 5, 5 (Full-Back, Full-Back, Central Defender,
Central Defender) for the DR, DL, DC, DC the reports list first. On frem-2026-06-11 the
"4-1-4-1" reads Full-Back ×2, Central Defender ×2, Defensive Midfielder, Wide Midfielder,
Winger, Roaming Playmaker, Box to Box Midfielder, Target Forward. No screen yet.

## Quirks

> **Correction:** this was first read as the user's saved tactics. The user has none on
> Truro; the growth with play, the cap at 30 and the game-given "uber tactic" name say
> otherwise.

> **Lead:** a screenshot of Truro's current tactic with the role at each position would pin
> FMM27's role codes in one go (TODO, "FMM27 role codes").

> **Lead:** what adds a record. Two saves either side of a single change (a new formation
> picked, or one role changed) would say.

> **Lead:** the 14-byte entries name people (Frem's six include tids 9328, 29576, 10404).

## Output

`output/<label>/tactic_history.json`: `[{name, gk_role, roles: [10 codes], flag}]` in stored
order. Not loaded yet.
