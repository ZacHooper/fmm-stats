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

Style is **derived, not stored**: a banding of `ID2+14`, one of the staff record's hidden
attributes, exposed as `attacking_intent` (raw 1-20) and `style` (the label).

**The full argument lives in `fmparser/staff.py`'s module docstring** — next to the code it
governs, so it cannot drift from it: the 39-byte stride that settled the extent and left
nowhere for a 3-valued enum, the out-of-sample test against the licensed manager database, the
rejected `+14 − +20` rival, and the band thirds. **The numbers live in
`tests/test_staff_records.py`** as executable data — the 7 ground-truth managers and the 7
whose Style was predicted in advance off `frem-2026-07-02.fms` and then read in game, 7/7
correct, Peter Pedersen at intent 8 reading Normal being the one that kills the cut-at-11
reading.

Recorded here because they appear nowhere else: `corr(+14, world reputation)` is only **+0.24**
(elite managers do average 13.3 against 10.7 overall, so quality is a confound but not the
signal), and `corr(+14, +20)` is **+0.01** — `+20` is not the opposite of `+14`, and stays
unnamed.

### Still undecoded in this record

- **`+34..+38`** — five more catalog-index bytes, and a real structure rather than padding:
  they draw from a 15-value subset of `[0,19]` that is **disjoint** from the formation triple's
  own 15-value subset, they are mutually independent (~9% pairwise agreement against a ~7%
  chance rate), and independent of the triple (~5%). Naming them needs ground truth we lack.
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

Re-verified against `frem-2024-11-10.fms`; everything above reproduces. Three gaps, all fixed
on `claude/pr-51-review-audit-un6rcv`. Full argument in the review comment on PR 51.

1. **The city walk had this document's own bug.** `_CITY_GAP_TOLERANCE = 40` decided where the
   table ended, so the row count was a function of the constant (40 → 10,928 rows; 200 →
   11,773; 5,000 → 13,840). It emitted 3 rows that aren't cities and dropped 31 that are —
   every one of the 31 referenced by a stadium. Now bounded by the table's own invariant
   (`id == slot index`, true for 10,925/10,925): 10,956 rows, contiguous, no knob. The
   ground-truth coordinates were exact throughout, which is the lesson.
2. **Stale claims this work disproved** were still asserted in `lookups.py`, `load_duckdb.py`
   and two docs — including "ranking history is 24 entries", the very assumption whose
   cross-career failure is listed under Traps below.
3. **No invariant was added for any of the 11 new staging tables or 9 new mart views**, so
   `validate_mart.py` passing meant nothing. `scripts/audit_records.py` (STRIDE / COVERAGE /
   EXTENT) and density guards in `tests/test_staff_records.py` now cover this; the rules are
   in `CLAUDE.md`.

**The hidden attributes are now carried** — 9 on the player record (`hidden_p28 … hidden_p08`),
6 on the staff record (`hidden_s18 … hidden_s28`), named by offset because we know *what* they
are and not *which*. See `attributes.HIDDEN_OFFSETS` / `staff.HIDDEN_OFFSETS`; that closes
"six of the seven hidden attributes" under *Still undecoded in this record* above.

### Still open
- **`hidden_s27` is the one to identify next** — 85% of staff read 1-4 against ~10 for the
  other five, the only one of the fifteen distinctive enough for a small ground-truth set.
- **The personality block's owner is unresolved** — `ATTRIBUTE_DECODING.md` puts it at
  `P-50 … P-43`, outside a record anchored at `P-42`; `staff.py` says it's on the INFO record.
- **`mart.club_managers` isn't purely structural** — it keeps a `home_reputation` tiebreak and
  exposes no candidate count, so a sole hit and a fallback are indistinguishable.
- **`_nation_candidates` breaks its `nat_len` loop unconditionally**, dropping a candidate
  whose `name_len` search then fails. Doesn't bite on these saves.
- **`parse_club_trailer` steps over 20 undecoded bytes** — width confirmed, content unread.
- **Every test skips silently and exits 0 without a save**, so nothing runs on a clean clone.
