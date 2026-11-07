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
`scripts/fit_value_model.py` fits on that column.

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

- **`+34..+38`** — five bytes, still unnamed, but much better characterised now:
  - **Not formations**, which was the obvious reading. They draw from a 15-value subset of
    `[0,19]`, and the two commonest preferred shapes are *absent* from it — `4-2-3-1` is the
    preferred formation of 1,258 staff and **never** appears here, while `4-2-4` and `3-4-3`
    appear here and are nobody's preferred shape. A different index space.
  - **Static.** Byte-identical for all 4,082 staff present in both `frem-2024-11-10` and
    `frem-2026-07-02` — 20 months and a promotion apart. Database attributes, not state.
  - **Near-unique per person**: 4,131 distinct 5-tuples across 4,210 staff, five near-
    independent draws from one table with the same distribution in each slot.
  - **No demographic structure**: no clustering by nationality, club or age decade (mean
    within-group sd 6.60 against 6.73 overall).

  Static, near-unique, structureless and person-scoped is the signature of an **identity or
  appearance code** (FM-style face/hair/build parameters) far more than of a preference list —
  a preference would cluster somehow. Cheapest test: two managers with visibly different
  portraits, and see whether any slot tracks the difference. Note `+37` is not interchangeable
  with the other four (value 7 appears 161 times there against 2-9 elsewhere).
- **Job Status** — still unlocated, still out of scope.

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

## Follow-up review (PR 51 audit, 2026-09-16)

Re-verified against `frem-2024-11-10.fms`; everything above reproduces. The gaps, all fixed
on `claude/pr-51-review-audit-un6rcv`. Full argument in the review comment on PR 51.

1. **Stale claims this work disproved** were still asserted in `lookups.py`, `load_duckdb.py`
   and two docs — including "ranking history is 24 entries", the very assumption whose
   cross-career failure is listed under Traps below.
2. **No invariant was added for any of the 11 new staging tables or 9 new mart views**, so
   `validate_mart.py` passing meant nothing. `scripts/audit/audit_records.py` (STRIDE / COVERAGE /
   EXTENT) and density guards in `tests/test_staff_records.py` now cover this; the rules are
   in `AGENTS.md`.

**The hidden attributes are now carried, and the player nine are NAMED** — `jumping`,
`consistency`, `big_match`, `injury_prone`, `versatility`, `set_pieces`, `penalty`,
`work_rate`, `flair`, from fmm-editor's `Player.cs` order.

Two things make that order safe to assert. Every one of the seven offsets we had verified
independently against in-game values lands exactly where it predicts. And FMM22 stores **18 of
the 34** slots as a plain 1-20 value and the other 16 in a wrapped 0-255 encoding, split exactly
along fmm-editor's semantic line — the plain 18 ability-independent, the encoded 16 technical
and goalkeeping. A partition that clean cannot come from a mis-aligned order.

**The 0-255 slots are NOT computed at display time — they hold the attribute, entangled.**
`fmparser/model.py` has been predicting from those exact bytes all along, and a positional test
settles what they carry. At MATCHED ability (CA 95-105, n=3,596), each source byte ranks
positions exactly as its fmm-editor name says:

| byte | name | top | bottom |
|---|---|---|---|
| `P-34` | Crossing | AMR 263, MR 262, AML 260 | DC 219, GK 173 |
| `P-32` | Tackling | DC 272, DMC 268 | ST 211, GK 175 |
| `P-31` | Finishing | **ST 282**, AMC 251 | DC 213, GK 173 |
| `P-27` | Passing | MC 272, DMC 268 | ST 244, GK 241 |
| `P-11` | Movement | ST 270, AML 268 | DC 226, GK 181 |
| `P-10` | Positioning | DC 275, DMC 265 | ST 223 |
| `P-7…P-1` | the 5 GK attributes | **GK 244-279** | every outfield position flat at ~170-174 |

The goalkeeping five are decisive: GK ~80 points clear with all ten outfield positions
indistinguishable. `corr(byte, CA)` is only 0.02-0.25, and within a 10-point CA band the bytes
still have sd 20-35 — this is per-player information, not a re-encoding of ability.

So the ordering is confirmed **slot by slot**, not just at the seven anchors, and two
long-standing claims are retired: `fm-parser-project.md`'s "FMM stores a REDUCED set and
computes the full 23-attr screen on demand", and this PR's own earlier wording that FMM22
"computes those from CA at display time". Both wrong. **Follow-up worth having:** the frozen
model is ~63% exact / ~93% within 1, fitted on 28 players; bytes with signal this clean should
support a far better decode.



Semantic checks agree where they can discriminate — `P-28` vs `height_cm` is **r = +0.79**
against +0.30 for Strength, which is Jumping and nothing else; `P-8` tracks Technique (+0.65)
not Stamina (+0.20); `P-13`/`P-14` correlate +0.57 with each other. **`consistency` and
`injury_prone` are unconfirmed** — 39 players have enough rated matches to measure rating
spread, and the 89 injury rows show the injured group up on *every* attribute, so that test is
confounded by minutes. Neither contradicts the order; both rest on the structural argument.

`P-29` stays **Aerial** (Player.cs says Heading; the FMM22 UI says Aerial) and Teamwork is
still derived from `P-25 + P-9`. Both kept deliberately, both ground-truth-backed for FMM22.

**The INFO record now has a declarative layout, and five more named fields.**
`staging.INFO_LAYOUT` is the single declaration of the record's fixed 68-byte head —
`_decode_info` reads from it, `audit_records.py` checks against it, and
`audit_records.py --map` prints it as the schema. Undecoded bytes went from **25 to 6**, and
the six that remain are `Unknown1`/`Unknown3`, unnamed in fmm-editor too.

What unlocked them: `People.cs`'s constructor gives read ORDER, and FMM22's head is **2 bytes
shorter** than FMM26's because caps/goals are `u8` here and `i16` there. Shift everything from
+40 on by two and it lands exactly on offsets we had already verified independently — club at
+42, personality at +52, PlayerId at +60, the staff link at +64. That is the check that the
alignment is right, not a guess. The new fields: **`joined_date`** (+46; 100% decode as a
plausible date, none after the save's own season), `u21_caps`/`u21_goals` (+40/+41),
`second_nationality_id` (+26), `ethnicity` (+28 — which retires BUGS #6's "declared national
team" guess, since that would hold nation ids in the 100s). One that did NOT survive contact:
`type_flag` (+33) agrees with our SID staff rule on only **82.4%** of records and has three
values, so BUGS #14's "agrees ~99%" was wrong and the SID rule still decides.

**There are no empty person slots.** The 77 records with `uid == 0` (and every nonsense joined
date: 1290, 1545, 2570) came from a sentinel sweep reading records out of alignment. Walked
from the table's count frame (`fmparser/tables/person_info.py`), every one of the 32,966
records is a real person and none needs blanking or a plausibility window.

**The personality block is parsed too, for the first time.** The 8 values
(`adaptability … temperament`) were verified byte-exact against the 7 managers' screenshots
back in BUGS #14 and then never wired into `_decode_info` — identified and discarded, the same
failure as the record tail. They are `staging.PERSON_FIELDS` now, on **both** players and
staff, along with international caps/goals at `+38`/`+39`. Two findings came with them: those
two are **u8 in FMM22**, not the u16 pair `People.cs` declares (Látal reads 47 caps / 1 goal as
bytes; a u16 would make it 303 caps), and **255 is a sentinel** — 77 records carry it in both
fields, always the same 77, with nothing between 200 and 254 — so it is stored NULL. The
licensed database checks out: Ronaldo 186 caps / 118 goals, Courtois 133 / 0.

**The staff six stay named by offset, and that is a finding now, not a gap: fmm-editor has no
`Staff.cs`.** Its `People.cs` reads the info record and stops at the `Unknown6b` u32 — which is
our `id2`, the link to the staff attribute record — and never follows it. No upstream order to
borrow, no ground truth of our own, so naming `hidden_s18 … hidden_s28` would be guessing.

### Still open
- **`hidden_s27` is the one to identify next** — 85% of staff read 1-4 against ~10 for the
  other five, the only one of the fifteen distinctive enough for a small ground-truth set.
- ~~The personality block's owner is unresolved~~ — **resolved.** It is on the INFO record at
  `info+52…59`: fmm-editor's `People.cs` declares the 8 bytes there, BUGS #14 verified them
  byte-exact against screenshots, and five of the eight bytes at `P-50 … P-43` are 1-20 for
  **0%** of records. `ATTRIBUTE_DECODING.md` is corrected. One discrepancy left as a note:
  slot 3 reads **Determination** on the FMM22 screens and **Controversy** in `People.cs`.
- **`mart.club_managers` isn't purely structural** — it keeps a `home_reputation` tiebreak and
  exposes no candidate count, so a sole hit and a fallback are indistinguishable.
- **Every test skips silently and exits 0 without a save**, so nothing runs on a clean clone.
