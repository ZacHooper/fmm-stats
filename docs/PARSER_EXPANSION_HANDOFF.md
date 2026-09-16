# Parser expansion — handoff

**Started and finished 2026-09-16.** Six workstreams, all shipped — the manager STYLE field
(§F) last, as a derivation rather than a stored field. Read [`CLAUDE.md`](../CLAUDE.md) and
[`agent-context/fmm-editor-record-comparison.md`](agent-context/fmm-editor-record-comparison.md)
first — the latter is the field-by-field map this all came from.

> These are **workstreams A–F**, deliberately lettered. `docs/HANDOFF.md` already numbers
> project-level phases 1–4 and reusing numbers here would be confusing.

---

## Why this happened

Comparing our parsers against **`github.com/nyongrand/fmm-editor`** (a C# reader for the FMM26
pre-game `.dat` database) showed several of our records were **located correctly but read
short**. Separately, `data/rough-guide.md` — already in the repo — turned out to describe a
**staff attribute record** we had never found, which carries the manager formation field that
BUGS #14 spent four rounds failing to locate.

`.dat` vs `.fms` is not a platform split: `.dat` is the shipped pre-game database, `.fms` is a
save. The save embeds the same record layouts, which is why fmm-editor's field names transfer.
(`jal-co/FMMLoader-26` was also checked and is irrelevant — a mod installer for FM2026 desktop,
no binary parsing at all.)

---

## A — Player record tail. SHIPPED

The global attribute record runs `P-42 … P+35` — exactly the 78-byte grid we already walked —
but we stopped at `P+22`. Added `current_reputation`, `world_reputation`,
`international_retired`, `squad_number`, `preferred_squad_number`, `height_cm`, `weight_kg`
via `attributes.record_tail()`, shared by both record readers.

Proof it is real: **GK average 188.2 cm / 78.2 kg vs outfield 180.4 / 71.8** over 26,518
records. `reputation` (P+21) was always HOME reputation; left named as-is because
`value_model.py` is fitted on that column.

## B — Staff record + the manager formation triple. SHIPPED

`fmparser/staff.py`. The info record carries **two** link fields: `sid` (+60) → player
attribute record, and **`id2` (+64) → staff attribute record**. `+64` was carried in docs as an
"unexplained u32" for four rounds of BUGS #14; it is the whole answer.

`ID2+31/+32/+33` are the **preferred / attacking / defensive** formations, as catalog indices —
the same three fields FM2026's editor exposes. 7/7 ground-truth managers exact on formation,
reputation tier and all 10 coaching attributes; **100% of 4,210 staff records** carry a
catalog-valid triple against a 57% base rate.

`mart.club_managers` identifies the manager **exactly, not heuristically**: the club record's
11-slot staff array holds the coaches but *not* the manager, so the manager is the staff member
at the club who is absent from it. 7/7, one candidate each, and Frem correctly returns **no**
manager because we manage it.

## C — Club record. SHIPPED

`reference.parse_club_trailer()` reads the whole trailer: colours and kits (a `Color` is u16
RGB555 — the `0x7FFF` flood BUGS #15 called sentinels is **white**), Status/Academy/Facilities,
attendances, `LeagueId` (which is what the old empirical `+158` always was), stadium id,
`LeaguePos`, reputation, affiliates (**21 bytes each**), the fixed **40-slot squad array**, the
11-slot staff array, and `main_club_tid`.

`main_club_tid` resolves exactly for all 352 reserve sides ("KAA Gent Reserves" → "KAA Gent",
Frem 7296 → 346) — the structural replacement for the hardcoded `reserve_tid` in `careers.py`,
**not yet wired**.

`mart.club_roster` + `mart.roster_vs_spells` land the squad array **alongside** the spell model,
not instead of it. They answer different questions: the array is *who is in this squad*
(includes loaned-in, excludes reserve-team players), `club_tid` is *who owns him*. On
frem-2024-11-10, 32 players carry `club_tid=346` while the first-team array holds 29 — the 8
missing are exactly the 8 in the reserves array. **Nothing has switched over.**

## D — Competition `Level` + reputation fix. SHIPPED

Reputation was read one byte early, straddling the background colour: Superliga read **34817**,
actually **136**. Now `u16 @ p+9`, plus `level` (0 = top flight) and `parent_cid`.

The acceptance gate deliberately still uses the **old** expression so exactly the same 602
competitions resolve — retuning what gets a name at all is a separate, riskier change.
`registration_rules` now derives tier from `level`, which also fixes parallel divisions:
Denmark's Series has four regional groups the save marks all level 4, where reputation-rank gave
them tiers 5/6/7/8. Verified a no-op for our position (tier 1, hg_min 8).

## E — Stadiums, cities, languages, currencies, nations. SHIPPED

`fmparser/places.py` and `fmparser/lookups.py`. All located **structurally** — by chaining, by a
fixed stride, or by a signature — never by a constant offset.

| table | rows | verified against |
|---|---|---|
| stadiums | 15,987 | Parken **38,065**, Aalborg Portland Park **13,800** — exact |
| cities | 10,928 | Copenhagen 55.6761/12.5683, Aalborg 57.0488/9.9217 |
| languages | 77 | ids match those inferred from managers' language lists |
| currencies | 94 | Danish Krone **8.699**, Czech Koruna **29.81** per GBP |
| nations | 227 | Denmark→Copenhagen→Parken, England→London→Wembley |

Plus the **national-team block**: world ranking, points, rival nation, ranking history, and
**UEFA country coefficients**. `mart.club_places` joins club → stadium → city.

**Coefficients are verified against three in-game screenshots across two careers** — the
in-game "Coef" column is `SUM(coefficients)`, matching 11/11 nations on a Frem 2026 screen and
11/11 on a Bucaspor 2022 screen. See the long ordering note in `lookups.py`: the array is
chronological and seeded with real UEFA history, and **FMM's own per-season columns read slots
2 and 3 while labelling them with the two most recent seasons** — a constant 6-slot display
offset in the game, confirmed on a day-one save. Use the total and the trend; do not map a
`seq` to the season the game prints beside it.

---

## F — Manager STYLE. **SOLVED 2026-09-16**, both band edges confirmed in-game

Style is **derived, not stored**: it is a banding of `ID2+14`, one of the seven hidden
attributes in the staff record. `fmparser/staff.py` exposes it as `attacking_intent` (the raw
1-20 value) and `style` (the derived label), the same shape as `reputation_tier`.

### What cracked it: the record is 39 bytes

Every earlier round searched a window around the record without knowing where the record
*ended*. Measuring the stride between consecutive real records settles it — **3,896 of 4,209
gaps are exactly 39**, and 4,657 of 5,097 on the Turkish save (the rest are 78/117/156, i.e.
skipped records). So:

```
+0   id2 u32          +4  ca u16      +6  pa u16
+8   home rep u16     +10 current u16 +12 world u16
+14 .. +30            SEVENTEEN attribute bytes (1-20)
+31 .. +38            EIGHT catalog-index bytes
```

Seventeen is the number the Manager Profile screen shows — but seven of those seventeen are the
personality block on the **info** record, so only 10 of these are displayed and **seven are
hidden**. And with the extent known there is nowhere left in the record for a 3-valued enum,
which is what turns "we cannot find Style" into "Style is not stored".

### Why `+14`, and not another n=7 false positive

`+14` is the only byte in the record that orders the 7 ground-truth managers Attacking >
Normal > Defensive. On its own that is worth nothing — BUGS #14's `-140` candidate did exactly
that and was noise — so it was tested **out of sample** against the licensed real-world manager
database the save carries:

- the four managers **Round 3 of BUGS #14 had already labelled attacking**, before this hunt
  existed, all land in the top 15% of the distribution: Klopp 18, Postecoglou 16, De Zerbi 16,
  Nagelsmann 16. By chance that is p < 1e-3.
- **Controlling for quality** (the obvious confound — `corr(+14, world reputation)` is only
  +0.24, but elite managers do average 13.3 vs 10.7): inside the top 20 by world reputation the
  order runs Klopp 18, Nagelsmann 16, Tuchel 15, Pochettino 15, Gallardo 15 … Nuno 11, Zidane
  10, Simeone 9, Mourinho 8. The two most famously defensive managers in world football are the
  two lowest of the twenty.
- **Cross-career**: on the Turkish save the same people read the same values (Klopp 18, Simeone
  9, Mourinho 8 — it is a static database attribute, not career state), and the names that fill
  the top were chosen by nobody: Sampaoli 18, Roger Schmidt 18, Kompany 18, Almeyda 19.

A rejected rival worth recording: `+14 - +20` also orders the 7 ground-truth managers, and
looks like "attacking coaching minus defending coaching". It loses badly out of sample — it
puts **Mourinho at +4, i.e. Attacking**. `+14` alone gets him right. `+20` is not the opposite
of `+14` (`corr = +0.01`) and remains unnamed.

### The bands, and how both edges were confirmed

`style()` bands in thirds — `<=7` Defensive, `8-13` Normal, `>=14` Attacking — giving 25% /
45% / 30% across 1,278 real club managers with Normal the plurality, which is the right shape
for a game label.

The 2024 ground truth could only pin the *Attacking* edge (13 Normal, 14 Attacking). Its one
Defensive manager reads 7 and its lowest Normal reads 12, so **any Defensive cut in 7..11
fitted it equally well** — and the rival cut at 11 was attractive, because it would have made
Mourinho (8) and Simeone (9) Defensive, which reads better footballistically.

So it was settled by prediction rather than by argument: seven managers spanning intent 6-14
were picked off `frem-2026-07-02.fms`, their Style written down in advance, and then read in
game. **All seven correct:**

| manager | club | intent | predicted & confirmed |
|---|---|---|---|
| Peter Sørensen | Vejle BK | 6 | Defensive |
| **Peter Pedersen** | **Odder IGF** | **8** | **Normal** ← the Defensive edge |
| Kenneth Kjærsgaard | Jammerbugt FC | 9 | Normal |
| Johnny Hansen | Vendsyssel FF | 10 | Normal |
| Kim Kristensen | Hobro IK | 11 | Normal |
| Brian Priske | Brøndby IF | 12 | Normal |
| **Jon Dahl Tomasson** | **AGF** | **14** | **Attacking** ← the Attacking edge |

Peter Pedersen at 8 is the one that mattered: it kills the cut-at-11 reading outright. The set
is guarded in `tests/test_staff_records.py`, which checks it against the 2026 save whenever
that save is present and skips cleanly when it is not.

### Still undecoded in this record

- **`+34..+38`** — five more catalog-index bytes, and a real structure rather than padding:
  they draw from a 15-value subset of `[0,19]` that is **disjoint** from the formation triple's
  own 15-value subset, they are mutually independent (~9% pairwise agreement against a ~7%
  chance rate), and independent of the triple (~5%). Five independent draws from a different
  index space than the formations. Naming them needs ground truth we do not have.
- **Six of the seven hidden attributes** (`+18, +20, +24, +26, +27, +28`). `+27` is the easiest
  next target: 85% of staff read 1-4 on it with a thin tail to 20, a shape none of the others
  have.
- **Job Status** — still unlocated, still out of scope.

## Outstanding, not part of F

- **A full rebuild has NOT been run.** The local store is mixed: 25 snapshots, but only a few
  carry the new tables. `uv run python scripts/rebuild.py --career frem` (~10 min) is the last
  step before trusting anything. `scripts/validate_mart.py` passed on the pre-E store.
- **`site/api/*.json` has not been regenerated.** `export_data.py` and `site/js/data.js` were
  changed together in workstream A to add shirt/height/weight, so the next
  `export_data.py --upload-all` will produce a real (expected) `git diff site/api`. The user has
  since said the site is not the priority — **the three reputation fields were deliberately NOT
  exported** (core.json loads on every page view and reputation is ability-adjacent).
- **Value-model refit.** `value_model.py` fits on `reputation` alone, which is its strongest
  single term. We now have `current_reputation` and `world_reputation` as well, plus height and
  weight. Re-run `scripts/fit_value_model.py` after a clean rebuild. The user specifically
  called reputation out as important for transfer value.
- `careers.py` still hardcodes `reserve_tid`; `main_club_tid` could replace it.
- `mart.squad_current` still uses the spell model; `roster_vs_spells` exists to judge the switch.
- Unparsed: the **Region** table, and the nation record's counted language list.

## Traps this work hit, all of which produced confidently wrong output first

- **`CREATE TABLE IF NOT EXISTS` does not add columns.** Bit three times. Every new column needs
  a `_MIGRATIONS` entry. Worst case: `history.player_snapshots` is built with
  `... AS SELECT p.*, a.*`, so its columns froze at 78 and a positional insert failed with
  "78 columns but 85 values" — which **failed two entire snapshot loads**. `_archive_snapshot`
  now names its columns explicitly.
- **A fixed-size assumption on a growing list.** The nation ranking history is 10 entries in a
  2022 save and 24 by 2026. Hard-coding 24 silently returned *nothing* for every earlier career
  — caught only because the user supplied an older save.
- **Multi-segment tables break stride walks.** Staff records share the 78-byte player stride but
  the table's phase resets; a `+= 78` sweep found 2 of 7 known managers. Key lookups instead.
- **Club, competition and nation records share a shape** (long name, short name, 3-letter code).
  A club claimed Belgium's id on a first-wins scan; "densest cluster" alone picked the
  competition table. Nations need a continent ceiling *and* a position filter.
- **A loose plausibility test is not a locator.** "Lots of valid lat/lon nearby" selected noise
  and truncated the city table to a tenth of its size; the real signature is a long run of
  records spaced *exactly* one record apart.
- **Run the cross-career check early, not at the end.** Every offset here came from one Danish
  save. Bucaspor (Turkey) is the only generalisation test the parser has, and it is what would
  have caught the ranking-history bug immediately.

## Guards

`tests/test_staff_records.py` covers all of A, B and E against ground truth, plus two structural
properties a mis-read field cannot fake: the formation triple must be catalog-valid across the
whole staff population, and world ranking must be near-unique across nations. Run it with a save
path; it skips cleanly without one.


---

## Follow-up review (PR 51 audit, 2026-09-16)

Reviewed on `claude/pr-51-review-audit-un6rcv`, against `frem-2024-11-10.fms`. Everything the
PR claims about the staff record, the formation triple, Style, the record tail and the
competition `level` reproduces from the bytes. Three things it did not catch:

**1. The city walk was bounded by a tolerance constant, and both ends were wrong.**
`_CITY_GAP_TOLERANCE = 40` decided where the table ended, so the row count was a function of
the constant (40 -> 10,928 rows; 200 -> 11,773; 5,000 -> 13,840). At 40 it emitted **3 rows
that are not cities** (ids 14338/14339/30976, bytes outside the table passing the loose
lat/lon test) and dropped **31 rows that are** — every one of the 31 referenced by a stadium,
so 32 of 10,943 distinct `stadium.city_id` values resolved to nothing in `mart.club_places`.

The table's real invariant is `id == slot index`, which held for 10,925/10,925 records inside
the seed run. Walking on that instead gives 10,956 rows, ids 0..10955 contiguous, 1 unresolved
`city_id` (the 0xFFFF sentinel), identical decode for every row both walks find, and no
tolerance knob. The ground-truth coordinates were exact throughout — which is the lesson.

**2. Stale claims the PR's own findings disprove.** The "nation ranking history is 24 entries"
assertion — the exact assumption whose cross-career failure the PR documents as a headline
trap — was still stated as fact in `lookups.py` (twice), `load_duckdb.py`'s DDL comment and
`fmm-editor-record-comparison.md` (twice). `docs/ATTRIBUTE_DECODING.md` §1 and
`fm-parser-project.md` still said the player record spans `P-55 … P+22`, the truncation
workstream A fixed. All corrected.

**3. No invariant was added for any of the 11 new staging tables or 9 new mart views.**
`scripts/validate_mart.py` is untouched by the PR, so "all checks passed" was true and empty.

### What is now in place
- **`scripts/audit_records.py`** — STRIDE / COVERAGE / EXTENT, described in `CLAUDE.md`. It
  independently re-derives the 39-byte staff stride (92.6% modal, 100% multiples) and the
  78-byte player stride (100%), and reports every byte in a record that no field claims.
- **Density + join guards in `tests/test_staff_records.py`** — verified to fail on an injected
  dropped row and an injected phantom row, while the ground-truth coordinate checks still pass.

### The hidden attributes are now carried

Both records hold 1-20 attribute bytes we can identify as attributes but cannot name, and both
were parsing them and throwing them away — the record-tail failure with a different excuse.
**Not being able to NAME a field is not a reason not to CARRY it.** Now in the store:

| record | bytes | columns |
|---|---|---|
| player attribute | `P-28, -20, -18, -17, -15, -14, -13, -9, -8` | `hidden_p28 … hidden_p08` on `staging.players`, `history.player_snapshots`, `mart.player_snapshots` |
| staff attribute | `+18, +20, +24, +26, +27, +28` | `hidden_s18 … hidden_s28` on `staging.staff_attributes`, `mart.staff` |

Named by offset, so the name asserts only where the byte is. The separation from non-attribute
bytes is clean and measured, not assumed: every attribute byte is 1-20 for >99.9% of records
with ~20-30 distinct values; every other byte in `P-38 … P-1` spans 0-255 with ~150 distinct
values. Verified end to end on `frem-2024-11-10` — all 15 columns land 1-20 with no nulls for
attributed players (25,282) and staff (4,210), and `hidden_s27`'s distribution through the mart
matches the raw bytes exactly.

`scripts/audit_records.py` now reports these as named rather than `UNKNOWN`: the player record
reads 60 named + 18 unknown (was 51 + 27) and the staff record 34 named + 5 (was 28 + 11, the
5 being the undecoded catalog indices at `+34..+38` — the attribute block is fully carried).

**`+27` is the one to identify next.** 85% of staff read 1-4, mean 3.0, against ~10 for the
other five — it is the only one of the fifteen with a shape distinctive enough that a small
ground-truth set would separate it.

### Still open after this pass
- **The personality block's owner is unresolved.** `ATTRIBUTE_DECODING.md` puts it at
  `P-50 … P-43`, which falls outside a record anchored at `P-42`; `staff.py` says it lives on
  the INFO record. One of those is wrong. Flagged in the doc, not settled.
- **`parse_club_trailer` steps over 20 undecoded bytes** after `reputation`. The width is right
  (the affiliate count lands correctly for 11,080 clubs) but the content is unread. Now named
  rather than a bare `q += 20`.
- **The hidden attributes are carried but unidentified.** Fifteen columns, no names. `+27`
  first (see above); the rest need ground truth we do not have.
- **`mart.club_managers` is not purely structural.** The comment says the manager is identified
  exactly by absence from the club's staff array, but the SQL keeps a
  `ROW_NUMBER() ... ORDER BY home_reputation DESC` tiebreak and no column says whether a row
  was a sole candidate or a tiebreak. Worth exposing the candidate count.
- **`_nation_candidates` breaks out of its `nat_len` loop unconditionally** once a nationality
  parses, so a candidate whose `name_len` search then fails is dropped rather than retried. It
  does not bite on this save (the 22 absent nation ids were never candidates) but it is fragile.
- **Every test in `tests/` skips silently without a save**, exiting 0. There is no check that
  runs on a clean clone, which is why a parser regression can merge green.
