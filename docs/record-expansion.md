# Parser expansion — record layouts from the 2026-09 decode

> **STATUS: REFERENCE, not a work plan.** Everything here SHIPPED in PR #51 (2026-09-17),
> including the Style hunt. Kept for the record layouts it decoded and the traps it hit.
> Anything still open from it lives in [`TODO.md`](TODO.md). For the per-byte schema of a
> record we walk, prefer `uv run python scripts/audit/audit_records.py --map` — that is generated
> from the parser's own tables and cannot go stale.

**Started and finished 2026-09-16.** Six workstreams, all shipped — the manager STYLE field
(§F) last, as a derivation rather than a stored field. Read [`AGENTS.md`](../AGENTS.md) and
[`agent-context/fmm-editor-record-comparison.md`](agent-context/fmm-editor-record-comparison.md)
first — the latter is the field-by-field map this all came from.

> These are **workstreams A–F**, deliberately lettered, so they never collide with the numbered
> entries in [`TODO.md`](TODO.md).

---

## Why this happened

Comparing our parsers against **`github.com/nyongrand/fmm-editor`** (a C# reader for the FMM26
pre-game `.dat` database) showed several of our records were **located correctly but read
short**. Separately, `data/rough-guide.md` — already in the repo — turned out to describe a
**staff attribute record** we had never found, which carries the manager formation field that
an earlier search spent four rounds failing to locate ([`docs/parser/staff.md`](parser/staff.md)).

`.dat` vs `.fms` is not a platform split: `.dat` is the shipped pre-game database, `.fms` is a
save. The save embeds the same record layouts, which is why fmm-editor's field names transfer.
(`jal-co/FMMLoader-26` was also checked and is irrelevant — a mod installer for FM2026 desktop,
no binary parsing at all.)

---

## A — Player record tail. SHIPPED

Documented in [`docs/parser/player_attributes.md`](parser/player_attributes.md).

## B — Staff record + the manager formation triple. SHIPPED

Documented in [`docs/parser/staff.md`](parser/staff.md); the person record's `id2` link in
[`docs/parser/person_info.md`](parser/person_info.md).

## C — Club record. SHIPPED

Documented in [`docs/parser/clubs.md`](parser/clubs.md).

## D — Competition `Level` + reputation fix. SHIPPED

Reputation was read one byte early, straddling the background colour: Superliga read **34817**,
actually **136**. Now `u16 @ p+9`, plus `level` (0 = top flight) and `parent_cid`.

The acceptance gate deliberately still uses the **old** expression so exactly the same 602
competitions resolve — retuning what gets a name at all is a separate, riskier change.
`registration_rules` now derives tier from `level`, which also fixes parallel divisions:
Denmark's Series has four regional groups the save marks all level 4, where reputation-rank gave
them tiers 5/6/7/8. Verified a no-op for our position (tier 1, hg_min 8).

## E — Stadiums, cities, languages, currencies, nations. SHIPPED

Documented one table per doc: [stadiums](parser/stadiums.md), [cities](parser/cities.md),
[languages](parser/languages.md), [currencies](parser/currencies.md),
[nations](parser/nations.md) (including how the Coefficients screen reads the list).

---

## F — Manager STYLE. SOLVED

Documented in [`docs/parser/staff.md`](parser/staff.md): Style is a banding of
`attacking_intent`, both band edges confirmed in game.

## Outstanding, not part of F

- **A full rebuild has NOT been run.** The local store is mixed: 25 snapshots, but only a few
  carry the new tables. `uv run python scripts/rebuild.py --career frem` (~10 min) is the last
  step before trusting anything. `tests/validate_mart.py` passed on the pre-E store.
- **The three reputation fields are deliberately NOT exported to the site** (core.json loads on
  every page view and reputation is ability-adjacent).
- `careers.py` still hardcodes `reserve_tid`; `main_club_tid` could replace it.
- `mart.squad_current` still uses the spell model; `roster_vs_spells` exists to judge the switch.
- Unparsed: the **Region** table.

## Traps this work hit, all of which produced confidently wrong output first

- **`CREATE TABLE IF NOT EXISTS` does not add columns.** Bit three times. Every new column needs
  a `_MIGRATIONS` entry. Worst case: `history.player_snapshots` is built with
  `... AS SELECT p.*, a.*`, so its columns froze at 78 and a positional insert failed with
  "78 columns but 85 values" — which **failed two entire snapshot loads**. `_archive_snapshot`
  now names its columns explicitly.
- **Multi-segment tables break stride walks.** Staff records share the 78-byte player stride but
  the table's phase resets; a `+= 78` sweep found 2 of 7 known managers. Key lookups instead.
- **Run the cross-career check early, not at the end.** Every offset here came from one Danish
  save. Bucaspor (Turkey) is the only generalisation test the parser has, and it is what would
  have caught the ranking-history bug immediately.

## Guards

`tests/test_staff_records.py` covers all of A, B and E against ground truth, plus two structural
properties a mis-read field cannot fake: the formation triple must be catalog-valid across the
whole staff population, and world ranking must be near-unique across nations. Run it with a save
path; it skips cleanly without one.


---

## Follow-up review (PR 51 audit)

Its findings are in the table docs: the person record's head and personality block in
[`person_info`](parser/person_info.md), the nine hidden player attributes and the wrapped
attribute bytes in [`player_attributes`](parser/player_attributes.md), the staff record's
unnamed bytes in [`staff`](parser/staff.md).
