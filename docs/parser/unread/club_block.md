# The user's club block (around the tactic history and club titles)

The tables [tactic history](../tactic_history.md), [club seasons](../club_seasons.md) and
[club titles](../club_titles.md) sit in a block that belongs to the user's club, after the
[person stamps](../person_stamps.md). Two parts of that block are unread.

## 1. In front of the tactic history

| | size |
|---|---|
| FMM22 | 148 B (60 + 4 + 6 × 14) |
| FMM27 | 64 B (60 + 4, no entries) |

- **60 bytes**: the first byte 0 or 1 (0 on frem-2021-06-27 and Bucaspor, 1 on every Truro
  save and later Frem ones); on Frem `03 01 01 01` at
  +9 where Truro has zeros; `ff` × 27–30; and at +40 a u64 that is money-sized
  (38,400,000,000 Truro, 18,240,000,003 Frem). A budget in some unit is the guess.
- **`[u32 n][n × 14 B]`**: 6 entries on Frem, 3 on Bucaspor, none on Truro. Each is a person's
  tid and 10 bytes; Frem's tids include 9328, 29576, 10404, with a small number each (3, 9, 0,
  12, 7, 5). The Tactics screen's **Set Pieces** and **Captain** tabs are the lead: takers and
  captains are people, set per tactic.

**Next:** screenshots of the Set Pieces and Captain tabs on a day a save is taken.

## 2. After the club titles

| | from | to | size |
|---|---|---|---|
| FMM22 | 56,316,108 | 61,253,092 | 4.94 MB |
| FMM27 | 61,806,283 | 67,009,361 | 5.20 MB |

- Opens `01 [club tid u16][first season year u16]`, then a long run of **empty slots**: 11 bytes
  on FMM22 (`ffff` + 9 zeros), 12 on FMM27. Nothing is filled on any save, including
  frem-2030-06-22 nine seasons in.
- On FMM22 a small player-list block sits at 56,336,372 (`Jeppe Corfitzen` / `FC København` /
  `Res Group 1`).
- The rest, to the player lists, is not looked at: 00 29% / ff 53–57%.

**Next:** count the empty slots (a capacity, as the season and title pools have), then
profile the rest by entropy.
