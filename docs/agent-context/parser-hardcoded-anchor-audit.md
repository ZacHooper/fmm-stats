---
name: parser-hardcoded-anchor-audit
description: "Audit of the whole parser for the PR #42 bug class (a gate that is only true for a SUBSET of records), measured across 6 saves and 2 careers. FOUR live losses — the light-results year gate, and the CONTRACT/TAGGED windows which are Bucaspor-tuned and front-clip every Frem save (100% of contract status on older saves, 12-16% of competitions on all of them) — plus a verbatim repeat of the nickname sentinel in info_offset (fixed), eight latent traps and eight gates cleared by measurement"
metadata:
  node_type: memory
  type: reference
---

Triggered by [[nickname-players-missing]] (PR #42): `scrape_players` anchored on the
`FFFFFFFF` "no nickname" sentinel, so every player WITH a nickname was invisible. The
question this audit answers: **where else does the parser do that?**

## The bug class

> A record is located or accepted using a condition that is only true for a SUBSET of
> real records, and the rest disappear with no error.

It has now bitten this project **four separate times** — the nickname sentinel, the
`condition` byte in `looks_like_block` (26 lost appearances, already fixed), the club uid
ceiling in `reference.py` (327 lost clubs, already fixed), and the two live losses below.
It never announces itself: the output is smaller, not wrong.

The tell is always the same shape — **an equality test against a sentinel, or a range
literal, standing where a structural check belongs.**

## Method

Every gate was measured against `frem-2026-03-22.fms`, not reasoned about. For each
candidate the test is: *relax the gate, then check the recovered records against an
INDEPENDENT source* — the info spine (built by a different scraper), or whether a cid/name
actually resolves. A recovered record that nothing else corroborates is byte noise, and
several candidates died exactly that way (see **Cleared** — those are as valuable as the
hits, they say where not to look again).

---

## LIVE LOSSES

### 1. `lightresults.YEARS` is (2020, 2021, 2022) — in a 2026 save

`fmparser/lightresults.py`. Every light-result record must pass
`_u16(mm, o + 12) in YEARS`, and `find_light_regions` locates the regions by searching for
those same three year markers. The field is a **real calendar year**, so three seasons of
world results are gated out. (The module docstring's "base years 2020/2021" is wrong —
2020-2025 are all present and the distribution is smooth.)

In the hardcoded LIGHT window, with the year gate removed: **4,036 candidates, 3,238
accepted (80.2%)**. Rejected: 2023 (274), 2024 (228), 2025 (228).

End to end through `lightresults.build()`:

| | current | year gate widened |
|---|---|---|
| fixtures | 1,789 | **2,324** (+535) |
| leagues | 43 | 90 |
| leagues that RESOLVE to a name | 31 | **42** (+11) |
| clubs mapped to a league | 421 | **485** (+64) |

The recovered named leagues are unambiguously real — Ligue 1 Uber Eats, Portuguese Second
League, Austrian Premier Division, Italian Serie D Grp. B. This is the source for
**club -> league membership** and computed standings, so the loss propagates into every
league table and any "who's in which division" question.

**Do not just widen the constant.** The year field is doing double duty as a cheap record
validator, and widening it to 2018-2040 takes unresolvable cids from 12 to 49. The fix
wants to be a window ANCHORED ON THE SAVE'S OWN DATE (the save knows it — `find_match_region`
already derives its region from content), keeping the gate tight but current. Measured:
2020-2026 and 2020-2040 give identical output, so there is nothing above the save's year to
catch — the window only needs to track forward, not open up.

### 2. `CONTRACT_LO/HI = 54M-58M` clips the contract-status section at both ends

`fmparser/regions.py`. These bounds are **Bucaspor-tuned** (CLAUDE.md already warns the
windows drift per career). Actual distribution of tid+uid-validated `0x8700` records in
`frem-2026-03-22`:

```
40-45 MB :     2
50-55 MB : 23800      <-- the bulk, and the window starts at 54M
55-60 MB :  1885
```

**25,687 validated records exist; the window catches 15,709. 9,977 tids (38.8%) are
missed** — the window opens ~4 MB after the section does.

Worst for our own squad: of **43** spine tids at the managed/reserve clubs, only **7** get
a status from inside the window, **25** have one only outside it, and 11 have none.

The records are consistent (0 tids disagree on status across copies), so widening adds
without any last-wins hazard. The status byte's meaning is separately validated — 65 =
out on loan is ground truth in `tests/test_ground_truth.py` — so this is a clipping bug,
not a decode bug. Note it plausibly explains part of [[loan-status-unreliable]]: that note
blamed "a stale copy / wrong code interpretation", but a player whose only record sits
outside the window simply gets `squad_status = NULL`.

### 3. `reference.info_offset` is a verbatim repeat of the PR #42 bug — **FIXED HERE**

```python
if mm[i + 16:i + 20] == b"\xff\xff\xff\xff":   # the "no nickname" sentinel
```

PR #42 fixed `staging.scrape_players` and left this second, independent copy of the same
anchor. It feeds `attributes.record_for()` and `reference.parse_info()`, so both were blind
to **~2,047 of 32,870 people (6.2%)**.

Confirmed on PR #42's own ground truth — `record_for` returned `None` for Carlos Polo
(20905) and Waldo Rubio (19471), the two men who decided the March 2026 defeat, while the
control Christian Tue (9894, no nickname) resolved fine.

Mitigating: `extract.py` does not call `record_for` — it uses `scrape_attributes` + a SID
join — so the **live extract was not losing players through this path**. It was live in
`tests/test_ground_truth.py` and in any ad-hoc lookup.

Fixed by accepting the sentinel OR a plausible nickname id, keeping every other check.
Regression over 1,500 sampled spine tids: **0 lost, 0 offsets changed, +100 gained, and
all 100 resolve to real names** (Jonathan Viera, Felipe Rodrigues da Silva, Alejandro Gómez
Martín — the Spanish/Portuguese/Brazilian concentration PR #42 predicted).

---

## LATENT TRAPS — no loss measured today, will bite

| # | Where | The gate | Headroom |
|---|---|---|---|
| 4 | `matches.py` `parse_header` / `_valid_match_header` | `2018 <= year <= 2030` | **hard stop in 2031**, and this is also the region LOCATOR (`find_match_region`), so matches stop being findable at all |
| 5 | `attributes._NAME_LEN` | name length 3-32 **bytes** | longest real squad name is **31 bytes** (`Frederik Vestergaard Kristensen`) — **1 byte** |
| 6 | `attributes._name_before` | `" " in txt` | a MONONYM ("Hulk", "Fred", "Rodrygo") fails -> dropped from `own_squad_full` -> loses exact attrs, transfer value and loan flag, falling back to the ±1 estimate. 0 lost on Frem's current squad (all 171 first-team + 39 reserve marker hits named) |
| 7 | `staging.DOB_YEAR_HI` | `2012` | youngest cohorts are 2009 (711) and 2010 (4) — **~3 seasons**. `DOB_YEAR_LO=1955` is fine: smooth taper (1956:2, 1957:4, 1958:9), not a cliff |
| 8 | `matches.is_block_start` | `ff` at +17, +18 AND +20, plus `condition` 1..100 | `looks_like_block` was ALREADY relaxed for exactly this reason (its docstring: 26 lost appearances). +18 is non-`ff` in 13 of 1,404 blocks and +20 in 1 — so they are real fields, not constants. 0 runs lost today (all four relaxations give 80 runs / 1,404 blocks) only because a run always starts on a posOrder-1 starter |
| 9 | `staging.scrape_contracts` | `2018 <= yr <= 2035` | max seen 2031 — ~4 years |
| 10 | tid floors | spine `100 < tid`, but `own_squad_full` + `discover_career` use `1000 < tid` | 897 spine people sit in (100, 1000]. Given tid recycling ([[tid-recycling]]), a newgen can land there |
| 11 | `staging.scrape_contracts` | `mm[p + 4]` is unbounded | raises `IndexError` if `hi` is near EOF; safe only because the default `hi` is 40M |

---

## CLEARED — measured, no loss. Do not re-investigate without new evidence

- **`attributes._valid_positions`' `max(seg) == 20`** and **`scrape_attributes`' `0 < ca <= pa <= 200`**.
  36,505 candidate positions are rejected by these across the ATTR region (294 for `max<20`,
  18,066 `ca>pa`, 16,031 `pa>200`, 2,114 `ca==0`) — and **0 of them carry a SID present in the
  info spine**. They are byte noise. The gates are sound.
- **`ATTR_LO/HI` (3.8M-6.6M)** — 0 records in the 2 MB below or 3 MB above.
- **`CONTRACTREC_LO/HI` (16M-40M)** — 0 records outside.
- **`resolve_name`** — 0 resolved names have a blank first name or surname.
- **`matches.find_match_region`** — correctly derives its region from content. This is the
  pattern the other regions should follow.

## ROUND 2 — cross-save, and the modules round 1 had not opened

Round 1 measured one save. Measuring six (frem 2021-07-01, 2023-07-01, 2024-11-10,
2025-11-30, 2026-03-22 and bucaspor-2022-06-01) changes two of the conclusions and adds a
fourth live loss.

### THE PATTERN: every hand-tuned window is Bucaspor-shaped and front-clips Frem

This is the real finding, and it is architectural rather than a list of bugs. `regions.py`
already tells the story against itself, in the comment above `REFDATA_LO`:

> a first attempt set LO from sampled hits alone (3.0M) and **silently cut 2.4M+ off the
> FRONT of the real section**, which is exactly the kind of miss this project has been
> burned by before.

That was fixed for REFDATA (LO set to 0). **`CONTRACT_LO` and `TAGGED_LO` have the identical
defect and were not fixed.** Measured against Bucaspor, both windows are perfect — 0 records
missed. Measured against Frem, both open several hundred KB to several MB *after* the real
section starts, and everything before that point is gone.

`mapregions.sections()` already recovers the correct front boundary per save, which is what
`regions.py` itself recommends ("or better, derive it from `mapregions.sections()` at runtime
instead of hand-tuning a constant again"):

| save | tagged: section start | first real tagged record | `TAGGED_LO` |
|---|---|---|---|
| frem-2026-03-22 | 16.751M | 16.755M | 17.000M |
| frem-2021-07-01 | 16.636M | 16.639M | 17.000M |

The section start lands within ~4 KB of the first real record on both. At the default
`min_gap` the section END is far too generous (one span runs 16.7M-52.4M), but that costs
only scan time — every record is validated on read anyway. **The fix shape is: take LO from
the section, keep a generous HI.**

### 4. `TAGGED_LO = 17.0M` clips the data dictionary — NEW, live on every Frem save

`fmparser/tagged.py` (and `datadict.py`, which imports the same bounds). Frem's tagged region
begins at **16.64-16.79 MB**; the window opens at **17.00 MB**. The loss is entirely at the
front — nothing sits above `TAGGED_HI` on any save.

Because the data dictionary is static reference data, the true totals are known exactly
(6,926 `comp` and 889 `sdfd` records on every save), so the loss is unambiguous:

| save | `comp` found | missed | `sdfd` found | missed |
|---|---|---|---|---|
| frem-2021-07-01 | 5,303 / 6,926 | **1,623 (23%)** | 664 / 889 | 225 (25%) |
| frem-2023-07-01 | 5,776 / 6,926 | 1,150 (17%) | 717 / 889 | 172 (19%) |
| frem-2024-11-10 | 6,015 / 6,926 | 911 (13%) | 767 / 889 | 122 (14%) |
| frem-2025-11-30 | 6,040 / 6,926 | 886 (13%) | 767 / 889 | 122 (14%) |
| frem-2026-03-22 | 5,875 / 6,926 | 1,051 (15%) | 742 / 889 | 147 (17%) |
| bucaspor-2022-06-01 | **6,926 / 6,926** | **0** | **889 / 889** | **0** |

**Live downstream impact:** `extract.py:368` calls `tagged.league_team_counts(mm)` with the
default window to build `competitions.json`. It finds **81 of 93 competitions** on
frem-2026-03-22 and 78 of 93 on frem-2021-07-01 — **11-15 competitions (12-16%) missing from
every Frem snapshot ever built**. Bucaspor: 93 of 93.

### 2 revisited — the contract-status window is worse than one save showed

It is not a 39% loss. It is a **100% loss on the older Frem saves**, improving only because
the section is growing forward into the window as the file grows:

| save | status records found | of total | `squad_status` coverage |
|---|---|---|---|
| frem-2021-07-01 | 0 | 25,497 | **0 / 32,533** |
| frem-2023-07-01 | 0 | 25,719 | **0 / 32,757** |
| frem-2024-11-10 | 10,916 | 25,232 (56.7% missed) | 10,915 / 32,850 |
| frem-2025-11-30 | 11,464 | 25,794 (55.6% missed) | 11,463 / 32,887 |
| frem-2026-03-22 | 15,709 | 25,687 (38.8% missed) | 15,709 / 32,870 |
| bucaspor-2022-06-01 | 26,041 | 26,041 (**0% missed**) | 26,040 / 33,942 |

So `squad_status` and `loaned_out` are **entirely NULL for two Frem snapshots** in the store
and partial for the rest. Note this is a DIFFERENT failure from [[loan-status-unreliable]],
which was a Bucaspor observation (Seyhun reading `loaned_out=True` wrongly) — and Bucaspor
loses no records at all. Two distinct problems wearing the same symptom.

### 1 revisited — "widen the year gate" was WRONG; bound it by the save's own date

Round 1 recommended anchoring the window on the save date but measured only the naive
widening. Measuring the naive version across careers shows it would have been a bad change:

| save | current (2020-22) | `[saveyr-6, saveyr]` | naive 2018-2034 |
|---|---|---|---|
| bucaspor-2022-06-01 | 2,989 @ 87.6% resolvable | **3,003 @ 87.2%** | 4,171 @ **62.9%** |
| frem-2026-03-22 | 1,789 @ 97.7% | **2,324 @ 94.4%** | 2,326 @ 94.3% |
| frem-2025-11-30 | 1,724 @ 97.6% | **2,232 @ 94.9%** | 2,233 @ 94.8% |
| frem-2024-11-10 | 1,938 @ 94.4% | **2,315 @ 91.1%** | 2,326 @ 90.6% |

The naive widening floods Bucaspor with **1,182 junk fixtures** and craters resolvability to
62.9%. Those records are dated **2023-2027 in a save whose in-game date is June 2022** —
impossible as results, and only **6 of 1,182** carry a cid that resolves to a real
competition. The year field is genuinely load-bearing as a record validator, which is why
this gate has survived: it works, it is just frozen.

**Bounding above by the save's own in-game date is the right shape.** It rejects every one of
those impossible future-dated records while capturing 2,324 of the naive version's 2,326 real
gains on frem-2026 (+535 fixtures, +11 resolvable leagues, +64 clubs mapped). It is also
strictly better than the status quo on the day-1 save, where the current window admits 94
junk fixtures and the save-bounded one admits 27.

`tests/test_lightresults.py` passes under both the current and the widened gate (2,989 ->
4,171 fixtures, Super League membership and the known game/cup split all still correct), so
the ground truth does not discriminate here — the resolvability rate above is what does.

### Cleared in round 2

- **`history.locate`** — the model the rest should follow. No hardcoded offset or season
  range; finds the slab by a plausible row count, a supermajority of `next == k+1`, and all
  pointers in-slab, then `Table.sanity()` proves the forest.
- **`results.memberships`** — structural, no date gate, `valid_clubs` gated.
- **`injuries.weekly_series`** — `_CLUSTER_WIN` is a RELATIVE window (densest 256 KB cluster),
  so it self-locates. Not a hardcoded position.
- **`matches.find_match_region`** — derives its region from content. Returns `None` on the
  two 0-match saves, which is correct, not a failure.

## State: what is fixed, what is open

**Fixed:** only **#3** (`reference.info_offset`) — a verbatim repeat of an already-reviewed
bug, verifiable against PR #42's own ground truth.

**Open, all measured, none attempted:** #1 (light-results year gate), #2 (`CONTRACT_LO/HI`),
#4 (`TAGGED_LO`). Each changes the shape of extracted data for every snapshot, so each wants
what PR #42 got — its own change, a full rebuild, and a store-level diff.

Rough order by value: **#4 is the cheapest** (front boundary only, `sections()` lands within
4 KB, exact known totals to verify against). **#2 is the biggest** (two Frem snapshots have
no squad status at all). **#1 needs the most design** — it needs the save's in-game date
threaded into `lightresults`, which currently has no access to it.

If only one thing survives from this audit, make it this: **a hand-tuned byte window in this
codebase is a Bucaspor measurement.** Three of them have now been caught front-clipping Frem
(REFDATA, fixed; CONTRACT and TAGGED, open). Check any remaining one against
`mapregions.sections()` before trusting it on a new career.
