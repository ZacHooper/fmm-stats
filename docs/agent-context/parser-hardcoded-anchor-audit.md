---
name: parser-hardcoded-anchor-audit
description: "Audit of the whole parser for the PR #42 bug class (a gate that is only true for a SUBSET of records). Three live losses found — the light-results year gate, the contract-status window, and a verbatim repeat of the nickname sentinel in reference.info_offset — plus eight latent traps and four gates cleared by measurement"
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

## Fixed in this pass

Only **#3** (`reference.info_offset`), because it is a verbatim repeat of an
already-reviewed bug and is verifiable against PR #42's own ground truth.

**#1 and #2 are left open deliberately.** Both are real and measured, but each changes the
shape of extracted data for every snapshot, so each deserves what PR #42 got — its own
change, a full rebuild, and a store-level diff — rather than being bundled into an audit.
