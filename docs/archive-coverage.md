# Archive coverage: what the `sicomps` archive replaces, and what it does not

**2026-09-20.** [`save-archive.md`](save-archive.md) established the container and characterised
the members. This asks the different question that decides how much parser work is now
redundant: **for each member, do we already reconstruct this by hand, and is the archive's copy
better?**

Measured on `frem-2021-07-01` (day one), `frem-2023-07-02`, `frem-2026-06-11` and
`bucaspor-2023-03-25`. Member counts are **159 on every save of both careers** — 12 named
subsystems plus 147 `comp_<id>.dat`, stable across five in-game years. (The *frame* count is
not the member count: a member may span several frames, so a chain walk counts 168–184. Do not
use the frame count as an invariant.)

## The answer that conditions everything else: it is a two-year rolling window

`fix_man.dat` is **always exactly two segments, and they are always the current and the
previous calendar year**:

| save | segment 1 | segment 2 | records |
|---|---|---|---|
| frem-2021-07-01 | **2021**, doy 83–177 (209 recs) | **2020**, doy 86–322 (114) | 323 |
| frem-2023-07-02 | **2023**, doy 1–182 (7,934) | **2022**, doy 1–365 (18,704) | 26,638 |
| frem-2026-06-11 | **2026**, doy 1–161 (7,721) | **2025**, doy 1–365 (19,232) | 26,953 |
| bucaspor-2023-03-25 | **2023**, doy 1–90 (5,454) | **2022**, doy 1–365 (20,632) | 26,086 |

The year sits at `+55` and is constant within a segment. The current-year segment stops at the
save's own day-of-year (2026-06-11 is doy 162; the segment ends at 161), so these are **matches
already played**, not a forward fixture list.

**Consequence: the archive is a current-state store. It can never replace anything we depend on
for history** — a save from 2026 knows nothing about 2021. It can only enrich the snapshot it
came from. That single fact turns almost every verdict below from REPLACE into AUGMENT, and it
is why this survey ran before the parser refactor rather than after.

**The corollary is the opportunity.** We keep 27 snapshots. Each carries ~18 months of world
results, so unioning `fix_man` across the archive of saves would cover the whole career — and
the window is wide enough that consecutive snapshots overlap rather than leaving holes.

## Verdicts

| member | what we do today | verdict | evidence |
|---|---|---|---|
| **`fix_man`** | `matchslots.py` resolves **275** fixtures from a 3,975-slot table; `matches.py` parses only OUR club's games | **AUGMENT — the largest in the archive** | 26,954 matches, **1,751 distinct clubs**, home-first, with scores. Our club appears 52 times, our reserves 28 — the other ~26,900 are matches we have never had at all |
| `stadium` | `places.scrape_stadiums` → **15,987** records with names, ids 0..15,986 | **CONFIRM only** | declares **15,984** and runs 8.34 B/entry — an index, not the named records. Ours is bigger and richer; the archive copy is a cross-check, not a source |
| `comp_<id>.dat` ×147 | competition table; standings record decoded but unimplemented (TODO #3) | **BLOCKED** | the 147 ids are **not our `cid` space** and `reference.comp_refs` resolves **1 of 147**. Until that mapping exists the contents cannot be attributed to a competition |
| `discipline` | injuries/suspensions from the Player-Progress bitfield | **IGNORE** | 254 B and **byte-identical on every save of both careers** — a static enumeration, not career state |
| `fifa_rankings` | nation rankings via `lookups` → `mart.nation_ranking_history` | **IGNORE** | 14 B on every save. Despite the name it holds no ranking table |
| `squad_man` | squad snapshot via `CLUB_MARKER` | **IGNORE** | 225 B → 17 B over the career; a stub by 2026 |
| `reserves` | reserve side via `careers.py`'s hard-coded `reserve_tid` | **IGNORE** | 1,500 B, constant within a career |
| `comp_man`, `comp_hosts`, `national_teams`, `friend_man`, `rule_group`, `rgman` | various | **UNEXAMINED** | sizes and first bytes in `save-archive.md`; none is large enough to change the refactor's target |

## What this means for the refactor plan

**Proceed as planned.** The archive does not make any of it redundant: the framing primitive,
the seven declared-count fixes (nicknames, nations, languages, currencies, player attributes,
staff, id-table orientation), the club-table walk and the career-half scan bounds all touch
subsystems the archive does **not** carry. Nothing in the plan should be re-pointed at it.

Two items do move:

- **TODO #4 (complete results/fixtures) is substantially answered** — by a member of the
  archive, not by any of the four byte-level approaches that were tried. It should be rewritten
  around `fix_man` plus the union-across-snapshots idea, and the dead ends kept as recorded
  negatives.
- **`matchslots.py` should not be developed further.** `fix_man` strictly dominates it — 26,954
  matches against 275, home-first (the 25-byte table mis-orients one row of every repeated club
  pair), and with scores. It is also not wired into `extract.py` today; only
  `tests/test_match_slots.py` imports `locate`. Leave it as the decoded record it is.

## What is not established

- **No competition field is identified in `fix_man`**, so a match cannot yet be attributed to a
  competition — the same gap the 25-byte table has.
- **The goals reading is not a fixed field** (`save-archive.md` has the Frem row that breaks
  it), so a fixture's score is not safe to ship yet even though the clubs and date are.
- **Whether the two-year window ever leaves a gap between consecutive snapshots** is untested.
  It looks safe — our saves are far closer together than 18 months — but the union has not been
  built, so the claim is an expectation, not a measurement.
- The `comp_<id>` → `cid` mapping, which is what would unlock 3.5 MB of per-competition data
  and probably the standings record with it. **This is the highest-value unknown the archive
  leaves open.**
