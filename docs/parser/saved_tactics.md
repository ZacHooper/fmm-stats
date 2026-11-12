# saved_tactics  ([`fmparser/tables/saved_tactics.py`](../../fmparser/tables/saved_tactics.py))

**The user's saved tactics**: each one's name and the role the user set for every position.
Straight after the [person stamps](person_stamps.md), in a block that belongs to the user's
club. Not every club's tactics: AI clubs' shapes are their managers' formations in
[staff](staff.md).

| | saved tactics |
|---|---|
| frem-2021-06-27, truro-2026-07-22 (first days) | 1 |
| frem-2023-07-02 | 11 |
| frem-2026-06-11 | 30 |
| bucaspor-2023-04-01 | 12 |
| truro-2026-08-08 | 15 |

## Layout

```
60 B                      unread; a money-sized number at +40 (3.8e10 Truro, 1.8e10 Frem)
[u32 n][n x 14 B]         n people, each [tid u32] + 10 bytes, unread (6 Frem, 3 Bucaspor, 0 Truro)
[u16 count][count x 59 B] the saved tactics
```

A tactic, 59 bytes:

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `gk_role` | u8 | 0, Goalkeeper, on every tactic measured |
| +1 | | u8 | `ff` |
| +2 | `roles` | 10 × `[role u8][u8][ff]` | the outfield roles in the formation's own position order; the middle byte is 0 or 1, unread |
| +32 | `name` | 26 B | the user's name for it, NUL-padded ("4-1-2-1-2", "uber tactic") |
| +58 | `flag` | u8 | 0 or 1, unread: 1 to 5 tactics a save carry it, and it is not the manager's preferred/attacking/defensive formation (the user's staff record stores none) |

The formation's positions are not in the record; only the name says them, and a user can
rename a tactic. The role codes are [seeds/roles.csv](../../seeds/roles.csv)'s on FMM22.
FMM27 keeps the codes up to Inside Forward and renumbers from there (two new roles, the
Wide Centre-Back and Inverted Full-Back: see [training](training.md)).

**How it is found.** From the person stamps' end, skip the 60-byte block and the counted
14-byte entries; the u16 there counts the tactics. The locator refuses it unless every tactic
reads: an `ff` after the goalkeeper's role and after every slot, a printable NUL-padded name,
a flag of 0 or 1.

## Evidence

`tests/test_saved_tactics_evidence.py`, eight saves of both games: every tactic reads, and a
career's first save holds one. On truro-2026-08-08 one tactic is named after the formation
all our match reports carry, 4-1-2-1-2, and its first four roles are 3, 3, 5, 5 (Full-Back,
Full-Back, Central Defender, Central Defender) for the DR, DL, DC, DC the reports list
first. On frem-2026-06-11 the "4-1-4-1" reads Full-Back ×2, Central Defender ×2, Defensive
Midfielder, Wide Midfielder, Winger, Roaming Playmaker, Box to Box Midfielder, Target
Forward. No screen yet.

## Quirks

> **Lead:** a screenshot of the Truro "4-1-2-1-2" tactic's role for each position would pin
> FMM27's role codes in one go: the open "FMM27 role codes" item in TODO, which training's
> `focus_role` is waiting on too.

> **Lead:** the 14-byte entries name people (Frem's six include tids 9328, 29576, 10404).
> Set-piece takers or captains are the first guess; a Set Pieces screen would tell.

## Output

`output/<label>/saved_tactics.json`: `[{name, gk_role, roles: [10 codes], flag}]` in stored
order. Not loaded yet.
