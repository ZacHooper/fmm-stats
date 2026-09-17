# The 143-byte record at ~36.36–36.94 MB is PLAYER MOVEMENT (transfer history)

Found 2026-09-17 while ruling this region OUT as a match table — it kept firing the fixture
signature because two club tids sit adjacent at its head. Zac suggested transfer history; the
ground truth is his in-game **Transfers** screen (Boldklubben Frem, 2025/26 Transfers In,
11 Jun 2026), which is the only independent check we have for it.

**Not parsed yet.** This is a decode note, not a shipped record. Nothing reads it.

## Extent

```
36.3556 M .. 36.9418 M     4,099 records, 143-byte stride
```

Located by walking the sequential counter at `+8` (6,411 → 10,509, step 1) out from a known
record until it breaks; a second counter at `+12` is always exactly **4,723** higher. The run
is contiguous and the counters bound it, so no plausibility window is involved.

## Fields identified

| off | field | evidence |
|---|---|---|
| `+0` | **from-club** (u16) | see the column-offset warning below |
| `+2` | **to-club** (u16) | filtering `+2 == 346` returns Frem's signings |
| `+8` | u32 counter, step 1 | bounds the table |
| `+12` | u32 counter, always `+8` + 4,723 | |
| `+46` | club (u16) | equals the player's current club on 19% — not yet understood |
| `+48` | **player tid** (u16) | resolves to a known person on **4,099/4,099 records (100%)**; 1,612 distinct people |
| `+61` | `[day u16][year u16]` — **not a transfer date**, see below | day takes only TWO values (0 and 179) across all 4,099 records |

Everything else is unread. **Fees are NOT located** — `+52`/`+53` vary with the transfer but not
linearly with the fee (£200K → 23, £120K → 9, £300K → 53), and searching for the exact amounts
finds nothing here. Money is displayed ROUNDED (CLAUDE.md §3), so any future search must use a
band, but a band search over ±25% did not find them either.

## `+61` is not a transfer date — correcting an earlier claim

An earlier version of this note said `+61` "decodes as a plausible `[day][year]` on 100% of
records". That was true and almost meaningless: **the day only ever takes two values**, so the
test was passing on a constant. Zac caught it by pointing out the Transfers screen shows no
dates at all. There are just **7 distinct pairs** in the whole table:

```
day=0    year=2021   3,037 records   (null)
day=179  year=2028     554
day=179  year=2027     427
day=179  year=2030      34
day=179  year=2029      29
day=179  year=2026      11
day=179  year=2031       7
```

Day 179 is the end of June — a season boundary, not an event. So the field is really a YEAR
with a fixed companion, and it cannot express a per-transfer date even in principle.

What it *does* correlate with is **contract expiry**, cross-checked against
`staging.scrape_contracts`, which decodes expiry from a different record entirely:

| relation to the player's CURRENT expiry year | records |
|---|---|
| equal | 664 (62.5%) |
| current is 1–4 years LATER | 381 |
| current is EARLIER | 17 (1.6%) |

**`+63` is ≤ the current expiry year on 98.4% of records.** A one-directional relationship that
strong is not chance, and it is what you would expect if `+63` is the expiry of the contract
signed **at the move**, with renewals since pushing the current one later. That is the leading
reading; 62.5% equality on its own would not have justified calling it contract expiry, and the
earlier draft should not have implied it did.

## The column-offset trap applies — read `+0` from the NEXT record

This is CLAUDE.md §5's trap, live: **a row's from-club belongs to the player on the PREVIOUS
row.** Graded against all 11 signings on the screenshot:

| read | matches |
|---|---|
| `+0` on the same record | **5/9** |
| `+0` on the next record | **8/9** |

```
player                  expected from   same-row +0        next-row +0
Johannes Tjørnelund     København       OK København       OK København
Marcelo Schöne          Brøndby         OK Brøndby         OK Brøndby
Mads-Emil Wass          Roskilde           Bournemouth     OK Roskilde
Gregers Dehn            Roskilde        OK Roskilde        OK Roskilde
Mounir Secka            Nordsjælland       Frem               Frem          <- the one miss
Anders Noer             Frem (Yth)      OK Frem            OK Frem
Mikkel Lejbowicz        København       OK København       OK København
Oliver Sørensen         Midtjylland        Brøndby         OK Midtjylland
Lauge Gülstorff         Brøndby            Frem            OK Brøndby
```

Anders Noer is a **Graduation** (Frem Yth → Frem) and reads Frem, which is right. The one miss,
Mounir Secka, was a **Bosman**; two more screenshot entries (Jakob Larsen, Bosman; Bertil Juel
Andersen, Loan from Granada) produce no record at all. So free transfers and loans may be
stored differently, or under a name the spine resolves differently — unresolved either way.

A player occupies **several consecutive records** (902 people have 1, but 179 have 2, 178 have
5, 134 have 4, 54 have 11), which is why the offset shows up as "the first record of a block
carries the previous player's club".

## Why it kept looking like a match table

`+0`/`+2` are two club tids side by side, and `+4..+7` is a constant `01 00 00 01`. The match
signature reads that constant as a **0-1 scoreline on day 256** — the same fake fixture on every
record, against whatever clubs happen to be in `+0`/`+2`. A constant score and a constant date
across many different opponents is the tell. See
[`light-results-record.md`](light-results-record.md) for the sweep that flagged it.

## Next steps

1. **Find the fee AND the transfer-type flag — they are probably two fields, not one.**
   Zac's reading of the screenshot, which the screenshot supports directly: the game's
   **Amount** column holds *either* a money value *or* a word — of his 11 signings, four show
   a fee (£300K, £200K, £130K, £120K) and seven show `Bosman` x2, `Loan` x4, `Graduation` x1.
   So expect a small **type** field (free / fee / loan / youth graduation) alongside a money
   field that is only meaningful when the type says so. This reframes the failed fee hunt: a
   band search across all records was looking for money in rows that have none, and it also
   explains the three screenshot entries that produced no usable record — two Bosmans and a
   loan. Search for the fee ONLY in rows whose type flag matches the four fee-paying signings,
   and look for a byte that partitions the table into groups of roughly the right shape.
2. Work out the block structure (why 1–11 records per player) before walking it — the offset is
   a symptom of not understanding it.
3. Test the "expiry at the time of the move" reading for `+61` directly — on a player who
   demonstrably renewed after signing, `+63` should hold the OLD expiry while
   `scrape_contracts` holds the new one. The 98.4% one-directional result is consistent with
   it but does not prove it.
