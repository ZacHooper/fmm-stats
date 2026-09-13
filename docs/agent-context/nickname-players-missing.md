---
name: nickname-players-missing
description: "scrape_players anchored on the FFFFFFFF 'no nickname' sentinel, so every player WITH a nickname was invisible to the whole decode — 2,072 records, fixed with a second validated sweep"
metadata:
  node_type: memory
  type: reference
---

**The player info sweep used to find players by searching for `FFFFFFFF`, which is the
"no nickname" sentinel — so a player who HAS a nickname was invisible to the entire
decode.** No name, no attributes, no squad membership, no ratings, no Level percentile.
Found 2026-09 while scouting Brøndby; fixed the same session in `staging.scrape_players`.

## How it surfaced

Brøndby's team sheet named two men — **"Waldo" (AML)** and **"Peque Polo" (FC)** — who
appeared in **no** Brøndby snapshot in the store, in any season. They were not new
signings: the club's own squad screen gave them **11 and 22 apps** that season. And
`staging.match_player_stats` (a different scraper, keyed on tid, so it never depended on
the sentinel) had them under bare tids **19471** and **20905**, playing against us four
times since 2024. In the 1-2 defeat on 2026-03-22, tid 20905 **scored both goals rated
10** and tid 19471 assisted — the two players our scouting data could not see decided the
match.

Raw-byte lookup resolved them via `reference.resolve_name`:

| tid | Name in the save | Shown in-game as | nickname @ +16 |
|---|---|---|---|
| 20905 | **Carlos Polo** | Peque Polo | `a9050000` (id 1449) |
| 19471 | **Waldo Rubio** | Waldo | `a3040000` (id 1187) |
| 9894 *(control)* | Christian Tue | Christian Tue | `ffffffff` |

## The bug

```python
j = mm.find(b"\xff\xff\xff\xff", i)
base = j - 16          # the FFFFFFFF is the nickname field at +16
```

The comment was right about *what* the field is and wrong about what that implies.
`FFFFFFFF` there means "this player has no nickname". Anchoring the record search on it
means the sweep can only ever find players who don't have one. Nothing else about those
records is unusual — right club_tid, plausible DOB, resolvable name ids, real SIDs.

## The fix — a second, strictly validated sweep

`scrape_players` now runs two sweeps and `_scrape_nicknamed` handles the second. There is
no anchor byte to search for and **the records are variable length** (gaps of 91-107
bytes, no alignment — so no stride lattice to walk), so it sweeps the **58 possible DOB
year u16 values** instead, each a C-speed `mm.find`, and validates hard:

- tid in `(100, 70000)`, day-of-year ≤ 366, DOB year in `[1955, 2012]`;
- nickname at +16 **not** `FFFFFFFF` (sweep 1 already had its chance);
- `club_tid` is either `NO_CLUB` or **a club id sweep 1 already proved real** — the
  strongest cheap validator available, and non-circular because sweep 1 supplies it;
- name ids below `NAME_ID_MAX`, and the pair **must resolve to an actual name**. Sound
  as an invariant because **all 30,798 records sweep 1 finds resolve** (0% failure).

Sweep 1 is untouched and always wins a tid clash, so the change is **strictly additive**.

## Measured on `frem-2026-03-22`

| | Before | After |
|---|---|---|
| info spine records | 30,798 | **32,870** (+2,072) |
| of which real players / staff | — | +1,616 / +456 |
| extract `players` | 24,151 | **25,767** |
| Brøndby squad | 26 | **28** |
| runtime | 11.8s | 16.0s |

Regression-tested against a verbatim copy of the old function: **0 tids lost, 0 decoded
fields changed.**

The recovered names are overwhelmingly Spanish, Portuguese and Brazilian — the
nickname-using nations — which is the sanity check that the sweep is finding real people
and not byte noise. Waldo Rubio comes back at **94.7 Level %ile nationally at AML**, which
would have made him one of Brøndby's better players in any briefing.

## What this invalidates

- **"Absent from every club's squad in the snapshot ⇒ a post-snapshot signing"** was
  never safe, and `scout-opponent` used to say it. A regular starter could simply have a
  nickname. The opponent's `Club Squad → Selection` screen settles it — it lists season
  apps.
- **A `coverage.partial` check that only counts rated players will not catch this.**
  Brøndby's frame looked complete at 26.
- **Any pre-fix analysis of a Spanish/Portuguese/Brazilian squad is short some players**,
  including reserve-strength checks and squad-quality percentiles computed against a pool
  that was missing ~7% of its members.

## Still open

- **The nickname string itself is not decoded.** Nickname ids do not resolve through the
  first-name or surname tables (1449 → "Jonatan"/"Würtz", clearly wrong), so there is a
  third table somewhere. We store the full name, so the game shows "Peque Polo" where we
  show "Carlos Polo" — worth mapping if a briefing ever needs to match a team sheet by eye.
- **Sweep 1 has two junk records** with name ids of 82M and `0xFFFF0000` (of 61,596 ids).
  Pre-existing, harmless, not addressed here — but it is why `NAME_ID_MAX` is a constant
  rather than a max taken from the data.
