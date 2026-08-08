# FMM22 save — TAGGED data-dictionary reference

A **living reference** of every key in the save's self-describing *tagged data dictionary*
(the "datadict"). Goal: know what each key references so we can pull structured competition
data directly instead of computing approximations from the partial light-results list (see
[`fmparser/lightresults.py`](../fmparser/lightresults.py) and the memory note
`denmark-region-drift`).

## What the datadict IS (key insight, 2026-08)
The datadict is the **season-build CONFIG engine** — the rules the game uses at the start of each
season to *build the fixtures*: competition format, number of teams, rounds/legs, seeding, draw
rules, TV/match-day scheduling, and **promotion / relegation / league splits**. Confirmed on
denmark-mid-22:
- `nssn` records carry split-groups: e.g. `topp=3 btpl=3 ntms=4 nrds=2` (top-3 up / bottom-3 down,
  4 teams, 2 rounds) **with an embedded rank snapshot** `team=0 crk=4 … team=3 crk=7` (slot→current
  rank). So current position (`crk`) IS persisted here, per stage/split-group, keyed by team **slot**.
- another `nssn` is a full fixture-scheduling block (`fxor` fixture order, `tvty/tvmt` TV, `ndow/ntim`
  day+time, `bkdw/stdw/endw` week windows) — literally how fixtures get laid out.
- `SCsn` (stage: `tems` team-count, `lgto`), `srnd` (seeded round: `drrl` draw-rule, `prio`, `rnds`).

Consequence for the **exact league table**: the *ordering* (`crk`) is here, but a full live
P-W-D-L-GF-GA-Pts scoreboard may be runtime-derived. The most tractable, high-value datadict wins
are **exact league membership + format + promotion/relegation/splits** — all gated on the id→club
**hop** (teams are referenced by internal slot / ~2e9 entity id, never a club tid). Crack the hop
(Phase 2) and R1/R4 both open up.

> **How to regenerate the tables below:** run `python3 scripts/dd_enum.py <save.fms>` (writes the
> JSON) then `python3 scripts/dd_doc.py` (rewrites everything under the AUTO-GENERATED marker).
> Edit the **meaning** columns freely — they are curated in `scripts/dd_doc.py`'s `KNOWN` dict so a
> re-gen preserves them. Add a decoded key to `KNOWN`, re-gen, commit.

## Format (from `fmparser/tagged.py`)
- **Field** = `[tag: 4 bytes, stored REVERSED][0x01 marker][type: 1 byte][value]`.
  Types: `0x01/0x0a/0x0b/0x13`=u32, `0x11`=u16, `0x03`=u8, `0x02`=**entity-type reference**
  (value is itself a reversed 4-char tag naming an entity type).
- **Record** = a container opener `<Tag> 0x0a <n>` immediately followed by `id 0x02 -><Tag>`,
  then that record's fields, until the next opener. Records are padded/separated by `00`.
- **Entity ids** (`id` type `0x01`) are large (~2×10⁹) **internal entity ids — NOT club/player
  tids.** Resolving an internal id → club tid is the **"hop"** every prior attempt tripped on
  ("ids disjoint from club tids"). Cracking that mapping is Phase 2 below.
- The region **drifts per save** (like every other region — see `denmark-region-drift`). The
  enumerator locates it by the `comp` tag cluster; do NOT hard-code the offsets.

## Relational schema (tables, PKs, FKs) — 2026-08
The save behaves like a relational DB. Even where a field's *contents* are unknown, its role as a
**key** is recoverable, which itself constrains meaning.

### Key system (how ids/PKs are encoded)
- A record's `id` (type `0x02`) is the **type tag** (self): the u32 decodes to 4 ASCII chars
  (`1668246896`=`comp`, `1937007732`=`stdt`, `1851880553`=`nati`, `1936023923`=`seas`). This is the
  record declaring its table, **not** an instance key.
- A record's **instance PK** is a UID with a **type-band prefix**:
  - **`2000000000 + serial`** = created datadict entities (e.g. comp *3.Division* UID `2000016262`).
  - **`200000000 + tid`** = added clubs (Dalum `200007289`).
  - **small** = legacy entities (Frem club UID `507`).
- **FKs are value-based:** a field carrying a value in another table's key-space is a foreign key.

### Datadict tables (PK = instance UID; → = FK)
| table | PK / id | foreign keys (field → target) | notes |
|---|---|---|---|
| `comp` | comp UID (2e9) | `levl`→tier, `curr`→currency, `nati`/`Nnat`→nation, `pare`→comp(parent), `type` | ntms/mntm/mxtm counts |
| `stnm`/`stag`/`SCsn`/`nssn` | stage UID | `comp`→comp, `drrl`→draw-rule, `seed`/`prio` | stages of a comp; `nssn` holds team-slot `crk` snapshot |
| `lrnk`/`wrnk` | — | `stnm`→stage, `team`→slot(0..ntms) | standings/rank atom; `crk`=position |
| `Ttea`/`team` | team UID / `Ttea`=**club tid** | `Ttea`→club(tid), `comp`→comp | team-in-competition |
| `przm`/`wnpz`/`lspz`/`apmn` | — | `comp`→comp, `posn`→finish position | prize money by position |
| `stdt`/`endt`/`drdt`/`nwdt`/`date`/`dat2` | date UID | — | y/m/d date records |
| `fxds` | fixtures UID | `comp`→comp | fixture scheduling |
| `nati` | nation id | — | nation table |
| `mnsn`/`nmsn`/`sbsn` | season UID | `comp`→comp | season records |

### External tables (NOT in the datadict — other regions — that bridge in)
These are the already-cracked structures the datadict joins to (incl. **players + names**, which live
here, not in the datadict):
| table | region | PK | foreign keys | source |
|---|---|---|---|---|
| **clubs** | club DB ~7M (multi-segment) | club **tid** | `[TID][UID]`; `league`(+158)→comp code; `country`→nation | `reference.club_record` ([[day1-league-membership]]) |
| **players** | info spine | player **tid** | `club_tid`→club, `first_name_id`/`last_name_id`→names, `nationality_id`→nation | `staging.scrape_players` |
| **names** | browse @0.3M + id-index @~37M | name_id → ordinal → string | 16-byte `[ordinal][name_id]` index; browse `[len][utf8]` | `reference.build_name_resolver` ([[name-resolution]]) |
| **packed comps** | comp records ~13M | **cid** (u16) | `[cid][UID]`; name/type/nation | `reference.comp_detail` |
| **player history** | ~40.6M | (tid via sid-order) | club-tid per row | [[player-history-table]] |

### Bridges (the cross-region joins that make it one schema)
- **comp UID ↔ cid**: datadict `comp` UID `2000016262` ↔ packed-comp `cid 1147` (via `comp_detail`).
  This is the join that lets datadict config attach to our competitions. (HANDOFF: cid 228↔uid 463485.)
- **club tid**: datadict `Ttea` = club tid → clubs table (tid) → names/league.
- **nation id**: `nati`/`Nnat` shared with players' `nationality_id` and clubs' `country`.
- **name ids**: players' `first_name_id`/`last_name_id` → names table (the existing 3-hop).

## Requirements → target entities (work these first)
Requirement-driven order, most-wanted first:

| # | Requirement | Likely entities to decode | Why |
|---|---|---|---|
| R1 | **League table / standings** (exact P-W-D-L-GF-GA-Pts, position) | `lrnk` (crk/team/stag/ntms/sed1), `wrnk` (crk/lwrk/hgrk), `stnm`, `SCsn`, `Ttea` | `lrnk`=league-rank, `crk`=current rank; `Ttea` links a team to a comp/stage |
| R2 | **Team ↔ internal-id hop** | `Ttea`, `team`, `RLtm` | every standings/fixture ref is an internal 2e9 id; need id→club-tid map |
| R3 | **Fixtures / schedule** | `fxds`, `ofxd`, `nfxd`, `stdt`/`endt`/`drdt` | `fxds`=fixtures; date entities give kickoff/draw dates |
| R4 | **Competition structure / format** | `comp`, `stnm`/`stag`/`nssn`/`sbsn`, `srnd`, `ncmp`, `pare` | stages, rounds, seeding, parent comp |
| R5 | **Prize money / finances** | `przm`, `wnpz`, `lspz`, `cash`, `apmn` | prize/finance by position |
| R6 | **Reputation / seeding** | `wrnk`, `lrnk`, `rats`, `seed`, `topp`/`btpl` | strength proxies |

## Phase 2 — the id→club hop: findings (2026-08)
The established datadict connection method (HANDOFF.md, `reference.comp_detail`) is **link by UID**:
`our cid → comp UID → datadict entities that reference that UID`. Confirmed pieces:
- **Hop 1 works:** `comp_detail(1147)` → 3.Division **comp UID `2000016262`** (the ~2e9 "created-entity"
  family, same band as datadict internal ids like `2000087895`).
- **UID schemes by entity (clue):** club records are `[TID u32][UID u32]`; UIDs come in bands —
  legacy clubs small (Frem 346→507, Næsby 369→541), some mid (FCR 2532→943835), and **added clubs
  `UID = 200000000 + tid`** (Dalum 7289→200007289, Herlev 7509→200007509). Comps/added entities live
  in the 2e8/2e9 bands.
- **Ruled out:** club-UID does *not* appear directly as a datadict `Ttea/team/DBID/id` value
  (0/10 overlap) — so it's **not** a one-step club-UID==team-id shortcut. The team ref in
  `lrnk`/`nssn` is a **slot index** into the comp's ordered team list.
- **Next probe (the actual hop):** from cid 1147's comp UID `2000016262`, find the stage/`nssn`
  records that reference it → its ordered team list (`Ttea` entities) → resolve each `Ttea` to a club
  (via its UID/`DBID` against the club `[TID][UID]` table, allowing for the UID-band scheme). Then
  slot→club, and the embedded `crk` snapshot becomes a named, ordered table. Validate on Frem.

## Phase 2 — empirical field scan (2026-08, the decisive test)
Rather than assume `Ttea`, we scanned EVERY datadict field value against known ids (club tids +
UIDs, comp UID, player tids). Results (field tag → id-type it carries):
- **`comp`, `DBID` → comp UID** (`2000016262` for 3.Division). Solid.
- **`Ttea` → club TID** (directly, in some contexts — NOT a 2e9 internal id as first assumed).
- `Bran` → player tid; `type`/`d2lA` → club tid (mostly coincidental small-value collisions).

BUT following the `Ttea` runs: **no run is 3.Division's 12-club roster.** The Ttea "member lists"
resolve to other divisions (a Danish group `2437–2478`) and award pseudo-entities ("Team of the
Year", tids 108–146). The 3.Division comp record (`comp/DBID=2000016262`) carries `ntms=12`/`Bktm=12`
and `cmps=6` sub-comps but **does not enumerate its member tids inline** — teams are referenced by
internal slot/structure, which is why datadict-membership was abandoned historically.

**Conclusion / decision:** membership is NOT worth extracting from the datadict — it's already solved
reliably by club records (`reference.club_record` `+158` league code → the exact 12 clubs, see
[[day1-league-membership]]). The datadict's unique value is the **config/format** (promotion,
relegation, splits, rounds, scheduling) and the `crk` position snapshot — but turning `crk` into a
named ordered table needs the slot→club order, which has no clean lookup. **Open decision:** is the
exact ordered table worth that remaining slot-resolution effort, given we already have membership +
an (approximate, mirror-fixed) computed table? Config extraction (R4/R5) is the higher-ROI datadict win.

## Completion plan
- **Phase 0 — Inventory (DONE):** enumerate every key + entity, this doc. Tables below.
- **Phase 1 — Entity anatomy:** for each R1/R3/R4 entity, dump full records with all fields +
  the record's own internal `id`, and label every child field (fill the meaning column). Deliver a
  per-entity field map (like the snapshot byte-map in `docs/ATTRIBUTE_DECODING.md`).
- **Phase 2 — The id→club hop:** find the table mapping internal entity ids (`Ttea`/`team` 2e9 ids)
  to club tids. Candidate approaches: (a) a `Ttea` record likely carries BOTH its internal id and a
  club ref/`DBID`; (b) cross-reference a comp whose members we already know (3.Division = the 12
  club tids) against the internal ids appearing in that comp's stage. Validate on Frem (tid 346).
- **Phase 3 — Standings extraction:** once R1 entity + hop are known, read the ordered table for a
  comp (validate against ground truth: Næsby top 6-4-1, Frem 6-3-2) → load into `staging.standings`
  with `source='datadict'` (authoritative; supersedes the computed light-results table).
- **Phase 4 — Generalise + ship:** career-agnostic reader in a new `fmparser/datadict.py`, wire
  into extract/load, verify on Bucaspor too. Keep this doc's meaning columns current.

## Open questions / hypotheses to test
- Is `lrnk` the live league table, and is `crk` the current position? (test: does a comp's `lrnk`
  set have exactly `ntms` rows with distinct `crk` 1..ntms?)
- Do `Ttea` records contain a club tid or `DBID` alongside the internal id (the hop in one place)?
- `stnm team=0/1` looked like 2-team slots — is that knockout legs, and is the round-robin table a
  different entity (`lrnk`/`SCsn`)?

---

<!-- AUTO-GENERATED TABLES below (edit meanings in scripts/dd_doc.py KNOWN; re-gen replaces tables) -->

**Region (denmark-mid-22.fms):** 16.665M–20.294M &nbsp; **distinct field tags:** 1070 (listing 575 with ≥15 occurrences) &nbsp; **entity types:** 159

## Entity types (records)
Ordered by record count. 'Child fields' = tags most often seen inside that record type.

| entity | records | top child fields | meaning |
|---|--:|---|---|
| `comp` | 7042 | id, type, igmt, nxss, umox, dyow, year, mntm, dyom, mont | competition (ref/id or local index) |
| `stnm` | 1373 | id, stgn, type, ntms, nmmt, mnsn, time, year, strl, dyow | stage entity (ref) |
| `Ttea` | 1158 | year, id, info, strl, mnsn, time, in_2, dyom, mont, dyow | team-in-competition INTERNAL entity id (~2e9) — needs id->club hop (Phase 2) |
| `stdt` | 1002 | id, dyom, mont, year, dyow, comp, nmmt, tvty, ndow, ntim | start date |
| `fxds` | 996 | id, mnsn, in_2, id_2, id_1, in_1, sbsn, type, nmmt, ofsd | fixtures entity |
| `endt` | 954 | id, dyom, mont, year, dyow, hidl, lwdl, wnty, time, type | end date |
| `sdfd` | 928 | id, id_1, id_2, in_1, cash, posn, mnsn, dyow, in_2, comp | start-date field? |
| `nwdt` | 840 | year, dyow, dyom, mont, id, time, type, strl, in_1, nmmt | ?date |
| `nmsn` | 823 | id, stgn, stag, dyow, team, mnsn, crk, nmmt, in_2, type | season name/num? |
| `edfd` | 782 | id, nmmt, tvty, dyow, tvmt, ndow, ntim, team, crk, lsdi | end-date field? |
| `team` | 492 | id, Ttea, year, przm, igmt, umox, nxss, dyow, type, dyom | team SLOT index within a stage (0..ntms-1) |
| `mnsn` | 466 | id, type, levl, ntms, year, stgn, Ttea, dyow, dyom, mont | season? |
| `nati` | 442 | id, Nnat, mnsn, year, type, dyow, dyom, mont, time, strl | nation |
| `date` | 401 | id, mnsn, mtrl, nmlg, dyow, year, dyom, mont, nmxt, in_2 | date entity |
| `sbsn` | 345 | id, stgn, type, time, mnsn, strl, ntms, year, dyow, dyom | sub-season? |
| `drdt` | 341 | id, time, ddsd, mnsn, year, dyom, mont, dyow, in_2, type | draw date? |
| `rgdv` | 263 | id, comp, igmt, mxtm, semt, seed, GmTy, rats, DBID, rst1 | **TBD** |
| `jcom` | 244 | id, comp, dyow, year, dyom, mont, time, przm, nmmt, cash | **TBD** |
| `rsid` | 230 | id, type, comp, vers, rsvt, utic, dyom, mont, fxri, stdt | **TBD** |
| `pare` | 226 | id, comp, igmt, umox, nxss, mntm, DBID, ntms, mxtm, type | parent competition (comp ref) |
| `nssn` | 214 | id, stgn, stag, type, nmmt, mnsn, ntms, tvty, indx, DBID | season/stage STRUCTURE incl split-group + embedded team-slot rank snapshot |
| `pvrn` | 213 | id, dyof, time, stgn, nmmt, mnsn, mtrl, type, ofsd, date | **TBD** |
| `spst` | 208 | id, stad, przm, year, time, strl, dyow, dyom, mont, comp | **TBD** |
| `accm` | 204 | id, type, sequ, gmsb, gmbl, tyar, prsw, sswn | **TBD** |
| `srci` | 198 | id, bnsc, decd, sfsr, mnsn, in_2, year, strl, type, time | **TBD** |
| `rdci` | 190 | id, gmsb, rdcr, bnsc, type, cmty, valu, fxrl, usqn, tcpf | **TBD** |
| `wrnk` | 187 | id, crk, lwrk, hgrk | world/reputation rank (crk/lwrk/hgrk) |
| `lrnk` | 187 | id, crk, type, ftac, nmrp, nmxt, ntms, stag, team, sed1 | STANDINGS atom: one team's rank in a stage (crk + team-slot + stnm + ntms) |
| `dsbi` | 180 | id, stdt, bnsc, gmsb, accm, type, sequ, prsw, sswn, rdci | **TBD** |
| `wnpz` | 173 | id, cash, nmmt, tvty, curr, ndow, tvmt, ntim, crk, ofsd | winner prize |
| `przm` | 172 | year, strl, dyom, mont, id, dyow, levl, cash, type, id_1 | prize money (amount, by posn) |
| `lcrl` | 154 | id, lcrg, igmt, mxtm, WrWt, type, GmTy, igma, semt, seed | **TBD** |
| `snrp` | 154 | id, sndr, type, cmty, valu, sdtr, mxss, NinE, usqn, tcpf | **TBD** |
| `lsdv` | 150 | id, comp, cash, dyow, curr, dyom, mont, year, strl, semt | **TBD** |
| `sred` | 142 | type, cmty, valu, sqsr, id, dyom, mont, year, sdnf, usqn | **TBD** |
| `lspz` | 138 | id, cash, time, curr, mnsn, nmmt, stnm, type, ntms, ofsd | ?prize |
| `srsd` | 130 | id, dyom, mont, year, dyow | **TBD** |
| `fnlc` | 127 | id, comp, dyow, year, strl, dyom, mont, time, aldt, type | **TBD** |
| `dat2` | 124 | id, mnsn, mtrl, sbsn, type, time, team, ftac, stag, dyof | date entity 2 |
| `ncmp` | 124 | id, comp, semt, stag, seed, DBID, ntms, srnd, subr, type | nested/child competition |
| `cash` | 112 | id, curr, type, WrWt, WrDl, lcrl, cmty, valu, trwi, usqn | cash amount |
| `tfrd` | 112 | type, cmty, valu, id, comp, styr, enyr, tcpf, sqsr, usqn | **TBD** |
| `srnd` | 110 | id, rnds, subr, prio, drrl, ctll, ntms, nmmt, strl, tvty | seeded round (subr/prio/drrl draw-rule/rnds) |
| `mtdy` | 106 | id, dyow, time, vers, type, rsvt, subr, utic, brpd, fxri | match day |
| `apmn` | 98 | id, nmmt, cash, curr, tvty, tvmt, ndow, ntim, lgin, type | ?appearance money |
| `updy` | 94 | id, type, dyom, mont, cmty, valu, mnsn, time, in_2, year | **TBD** |
| `sqdt` | 86 | type, valu, cmty, id, sqsr, tcpf, dyom, mont, year, usqn | **TBD** |
| `relr` | 85 | id, nrpl | relegation-related |
| `ssnd` | 82 | id, snms | **TBD** |
| `wkpm` | 78 | type, dyow, year, dyom, mont, cmty, valu, strl, id, time | **TBD** |
| `dtrn` | 75 | id, stmn, styo, enmn, enyo, year, strl, dyom, mont, id_1 | **TBD** |
| `sudt` | 68 | mnsn, in_2, year, strl, dyom, mont, time, dyow, id, hidl | **TBD** |
| `agdt` | 64 | id, type, dyom, mont, year, plty, lpcr, lnrl, expd, sbty | **TBD** |
| `trrl` | 62 | id, natr, frtj, cnem, lpcr, type, lnrl, plty, fcmn, valu | **TBD** |
| `snda` | 60 | type, valu, cmty, id, mxss, tcpf, usqn, sqsr, sdnf, sqsv | **TBD** |
| `ofxd` | 60 | id, mnsn, in_2, sbsn, id_1, id_2, in_1 | **TBD** |
| `nfxd` | 59 | przm, id, levl, mnsn, in_2, cash, id_1, id_2, ACfl, sbsn | **TBD** |
| `RLtm` | 59 | Ttea, id, seed, aqtp, tems, stag, type, year, ntms, indx | **TBD** |
| `CfOD` | 59 | przm, levl, id, year, dyom, mont, strl, id_2, id_1, dyow | **TBD** |
| `CnRl` | 58 | type, cmty, valu, id, comp, styr, enyr, tcpf, Draf, sqsr | **TBD** |
| `SCsn` | 58 | id, type, ntms, stgn, stag, topp, btpl, seed, levl, time | stage config (stgn, tems, lgto, stnm) |
| `tppr` | 51 | id, nrpl, levl, przm, comp, stag, vsdp, indx, itvm, fnrg | **TBD** |
| `rfpr` | 51 | id, hgrk, comp, inac, type, tems, itvm, vsdp, fnrg, dyow | **TBD** |
| `city` | 50 | id, type, year, dyow, dyom, mont, strl, id_1, id_2, indx | **TBD** |
| `updv` | 48 | id, comp | **TBD** |
| `lwdv` | 48 | id, comp, tems, type, Bran, PrSt, vlys, mntm, mxtm, dyow | **TBD** |
| `OPpr` | 48 | id, ntms, type, levl, lwrk, strl, year, dyow, dyom, mont | **TBD** |
| `btpr` | 45 | id, nrpl | bottom places (relegation) variant |
| `PSfd` | 42 | id, mnsn, id_1, id_2 | **TBD** |
| `prmr` | 42 | id, nrpl | promotion-related |
| `TrSt` | 41 | stag, id, type, srcc, shsn, shnt, exlg, shpo, indx, Per% | **TBD** |
| `pspl` | 37 | id, cash, curr, posn, type, ckch, ckpr, ckcc, ckrl, plyf | split? |
| `COdf` | 36 | id, team, crk, hgrk, lwrk, comp, nrpl, id_1, id_2, rank | **TBD** |
| `Cmp2` | 34 | id, comp, type, time, ofsd, dyof, nmmt, strl, stag, HdRl | **TBD** |
| `in_1` | 32 | id, Ttea, comp, Nnat | ? |
| `in_2` | 32 | id, Ttea, time, dyof, type, id_2, mnsn, comp, id_1, drrl | ? |
| `trsd` | 30 | id, dyom, mont, wdft, mdft, type, ftye, vers, ifdr, TrCm | **TBD** |
| `lwtd` | 28 | id, comp, type, cmty, valu, enyr, styr | **TBD** |
| `hgtd` | 28 | type, cmty, valu, id, comp, styr, tcpf, sqsr, bsyi, usqn | **TBD** |
| `pfpr` | 28 | mnsn, in_2, strl, year, dyow, dyom, mont, id, time, type | **TBD** |
| `MgaV` | 28 | id, cash, curr, MlsY, MtaM | **TBD** |
| `MtaV` | 28 | id, cash, curr, MlsY, PciL | **TBD** |
| `PciV` | 28 | id, cash, curr, MlsY, SmSL | **TBD** |
| `SmSV` | 28 | id, cash, curr, MlsY, RmSL | **TBD** |
| `RmSV` | 28 | id, cash, curr, MlsY, MLsC | **TBD** |
| `MsCv` | 28 | id, cash, curr, MlsY, NtGB | **TBD** |
| `cnti` | 26 | id, in_2, cont, nmmt, in_1, seed, type, semt, mxtm, id_1 | **TBD** |
| `dsrl` | 22 | id | **TBD** |
| `fxrl` | 21 | mnsn, in_2, year, dyom, mont, strl, dyow, time, id, styr | **TBD** |
| `idms` | 17 | levl, id, przm, type, mnsn, ntms, stgn, id_1, id_2, year | **TBD** |
| `info` | 16 | id, cash, curr, year, tcpf, usqn, mont, dyom, dyow, trrl | generic info/count value |
| `wopm` | 16 | id, decd, type, info, wpdw | **TBD** |
| `wtpm` | 16 | id, decd, type, info | **TBD** |
| `ctrn` | 16 | comp, id, decd, type, info, wpdw, ftye, vers, XSvC, nati | **TBD** |
| `sthl` | 15 | id, city, ntms, nmxt | **TBD** |
| `nthl` | 15 | id, nmmt, tvty, ndow, tvmt, ntim, dyof, ofsd, ntms, city | **TBD** |
| `lwpz` | 15 | id, cash, curr | **TBD** |
| `drpz` | 15 | dyow, id, mnsn, in_2, cash, year, fxor, nmmt, tvty, tvmt | **TBD** |
| `btfo` | 14 | id, cash, przm, curr, type, tfxt, CcQR, CcEx, levl, hlps | **TBD** |
| `BsNt` | 14 | id, Nnat, igmt, MwSo, MwSs, DBID, SrTs, mxtm, rats, fsqt | **TBD** |
| `avpt` | 13 | type, id, topp, btpl, ind1, year, ftac, stag, srcc, lfte | **TBD** |
| `stWP` | 12 | id, year, type, sswn, trrl, lnrl, bcr1, bcr2, bcr3, cann | **TBD** |
| `sqrw` | 12 | id, apmn, type, tcpf, usqn, sqsr, cmty, valu | **TBD** |
| `Cexi` | 12 | id, comp, igmt, umox, nxss, type, gmsb, bnsc, cmty, year | **TBD** |
| `tfpr` | 12 | id, hgrk, lwrk, crk, stag, type, ntms, indx, stnm, strq | **TBD** |
| `prcm` | 11 | type, cash, curr, PrSt, winr, losr, drpz, id, year, hlps | **TBD** |
| `fycl` | 10 | year, strl, dyom, mont, time, dyow, mnsn, bsyo, in_2, id | **TBD** |
| `Ucdr` | 10 | mnsn, in_2, year, strl, time, spld, spdO, dyom, mont, id | **TBD** |
| `fsff` | 9 | id, ntms, id_2, id_1, indx, type, pref, stag, strq, ofsd | **TBD** |
| `atpm` | 9 | id, cash, curr, stnm, drdt, time, nmlg, strq, tems | **TBD** |
| `wkFT` | 8 | id | **TBD** |
| `appe` | 8 | id, decd, type, info, wpdw | **TBD** |
| `oldt` | 8 | id, dyow, dyom, mont, year | **TBD** |
| `vlaf` | 8 | dyom, mont, year, strl, dyow, mnsn, time, hidl, lwdl, in_2 | **TBD** |
| `Nxdv` | 8 | id, DBID, ngps, comp, type, team, lfte, srcc, stag | **TBD** |
| `vlbf` | 7 | dyom, mont, dyow, year, strl, id, time, type, mnsn, bsyr | **TBD** |
| `invm` | 6 | id, cash, curr | **TBD** |
| `li-e` | 6 | type, cmty, valu, id, cash, curr, styr, usqn, tcpf, sqsr | **TBD** |
| `excp` | 6 | type, cmty, valu, tcpf, sqsr, usqn, id, cash, curr, fpwi | **TBD** |
| `NtSr` | 6 | id | **TBD** |
| `sptm` | 6 | type, valu, cmty, id, Ttea, info | **TBD** |
| `DUNf` | 6 | id, comp, type | **TBD** |
| `wstl` | 6 | id, nmmt, time, dyof, city, tvty, ndow, tvmt, ntim, cash | **TBD** |
| `ldpz` | 5 | id, cash, curr, stgn, stnm, type, time, ofsd, vlgr, mtrl | **TBD** |

## Field keys
`type` codes: 0x01/0x0a/0x0b/0x13=u32, 0x11=u16, 0x03=u8, 0x02=entity-ref (reversed tag).

| key | count | type(s) | int range / ent-refs | samples | meaning |
|---|--:|---|---|---|---|
| `id` | 39251 | 0x01,0x02,0x11 | refs: comp×7042, stnm×1373, Ttea×1236, stdt×1002 | 1851880553, 1668246896, 1885434469, 1836344441, ->sdfd | entity id (u32; ~2e9 = internal entity id, the 'hop' vs club tid) |
| `comp` | 18551 | 0x0a,0x01,0x11 | 1..2000094524 | 2, 131234, 131235, 5688090, 136517 | competition (ref/id or local index) |
| `year` | 12195 | 0x12,0x11,0x02 | refs:     ×1,   Ð×1 | 2000, 2001, 0, 2021, 2022 | year |
| `type` | 11415 | 0x11,0x12,0x01,0x02 | refs:    H×14,    ×12,    ×8,    ×6 | 2, 5, 21, 4, 122 | record/comp type code |
| `dyow` | 10311 | 0x11 | 1..7 | 2, 7, 4, 6, 3 | day of week (1..7) |
| `dyom` | 10199 | 0x11 | 1..31 | 10, 15, 1, 17, 31 | day of month (1..31) |
| `mont` | 10198 | 0x11 | 1..12 | 4, 5, 7, 11, 8 | month (1..12) |
| `mnsn` | 8263 | 0x11,0x12,0x0a | 0..240 | 76, 73, 6, 20, 145 | season? |
| `time` | 7188 | 0x12,0x11 | 0..2300 | 1900, 1200, 1000, 1800, 1400 | time of day (HHMM) |
| `strl` | 5910 | 0x11 | 1..38 | 3, 1, 2, 6, 16 | ?level/rung (1..16) |
| `in_2` | 5074 | 0x11,0x02,0x0a | refs:   ×4,   	 ×1 | 0, 5, 1, 9, 19 | ? |
| `ntms` | 4657 | 0x11,0x12 | 0..342 | 6, 13, 8, 11, 12 | number of teams |
| `nmmt` | 4365 | 0x11,0x12 | 0..146 | 1, 5, 2, 4, 3 | number of matches |
| `stgn` | 4083 | 0x11,0x12,0x01 | 6..2000016479 | 108, 172, 21, 20, 171 | stage number |
| `Ttea` | 3951 | 0x01,0x12,0x0a,0x11 | 2..2000087895 | 23071816, 5350051, 2000087895, 5628523, 5628524 | team-in-competition INTERNAL entity id (~2e9) — needs id->club hop (Phase 2) |
| `levl` | 3905 | 0x11,0x02 | refs:    ×252,     ×123,    ×114,    ×108 | 0, 1, 2, 3, 4 | league level/tier (0..27) |
| `team` | 3752 | 0x0a,0x11,0x12,0x01 | 0..72023746 | 2, 3, 0, 1, 4 | team SLOT index within a stage (0..ntms-1) |
| `id_1` | 3419 | 0x01,0x11,0x03 | 0..2003727410 | 1936023923, 1818583399, 2003398260, 1651208736, 2003398263 | secondary entity id/ref |
| `stag` | 3256 | 0x11,0x01,0x0b | 0..2003006832 | 1, 2, 3, 0, 4 | stage index/ref |
| `przm` | 3208 | 0x0a,0x0b,0x01,0x11,0x12 | 0..96809160 | 3, 5, 7, 2, 4737581 | prize money (amount, by posn) |
| `id_2` | 3167 | 0x01,0x11,0x03 | 0..2003398244 | 1937006962, 0, 3, 1701733408, 1936483188 | secondary entity id/ref |
| `crk` | 3040 | 0x11 | 0..27 | 0, 1, 2, 3, 4 | current rank / league position |
| `cash` | 2931 | 0x0a,0x01,0x12,0x11 | 0..4288967296 | 3, 96153, 57692, 5769, 28846 | cash amount |
| `igmt` | 2744 | 0x03 | 0..1 | 0, 1 | bool flag |
| `stnm` | 2579 | 0x11,0x12,0x0a | 2..255 | 108, 172, 2, 20, 3 | stage entity (ref) |
| `tvty` | 2491 | 0x11,0x03 | 0..4 | 2, 1, 0, 4, 3 | TV type |
| `nxss` | 2256 | 0x03 | 0..1 | 0, 1 | bool flag |
| `umox` | 2250 | 0x03 | 0..1 | 0, 1 | bool flag |
| `DBID` | 2226 | 0x01,0x12,0x11 | 1..2000152066 | 2000087895, 2000119680, 131126, 130931, 23501362 | database id (entity uid, 2e9 band for created) |
| `valu` | 2224 | 0x11,0x01 | 0..590500 | 5, 3, 0, 30, 6 | value |
| `tvmt` | 2215 | 0x11 | 0..36 | 17, 4, 0, 7, 30 | TV channel/match |
| `ndow` | 2166 | 0x11 | 1..7 | 1, 6, 7, 3, 4 | nominal day-of-week |
| `hidl` | 2100 | 0x11 | 0..255 | 0, 1, 2, 3, 6 | ? |
| `in_1` | 2043 | 0x11,0x02,0x0a,0x12 | refs:    ×4,    ×2,    ×1 | 0, 29, 1, 33, 5 | ? |
| `cmty` | 2033 | 0x11 | 1..255 | 255, 1 | ?commentary? |
| `ntim` | 2022 | 0x12,0x11 | 0..2215 | 1330, 1615, 1830, 2100, 2045 | nominal kickoff time (HHMM) |
| `mntm` | 1981 | 0x11,0x12 | 0..450 | 16, 3, 18, 9, 8 | max teams? (0..96) |
| `curr` | 1831 | 0x02,0x11 | refs:    ×525,    ×296,    ×130,    ×110 | ->   !, ->   , ->   , ->   , ->   ( | currency (ref) |
| `ofsd` | 1788 | 0x0b | 0..16 | 0, 1, 2, 6, 5 | ? |
| `seed` | 1718 | 0x11,0x0b | 0..255 | 0, 1, 10, 8, 6 | seeding |
| `lwdl` | 1708 | 0x11 | 0..255 | 1, 4, 0, 255, 2 | **TBD** |
| `mxtm` | 1684 | 0x11,0x12 | 0..185 | 16, 18, 9, 15, 13 | max teams |
| `indx` | 1587 | 0x11 | 0..25 | 0, 3, 5, 1, 2 | index |
| `sbsn` | 1547 | 0x11,0x0a,0x12 | 2..136 | 4, 3, 2, 18, 20 | sub-season? |
| `lwrk` | 1523 | 0x11 | 0..27 | 3, 7, 5, 11, 12 | season-lowest rank |
| `stdt` | 1520 | 0x11,0x0a | 0..7 | 0, 4, 5, 1, 7 | start date |
| `dyof` | 1510 | 0x11 | 0..255 | 1, 248, 2, 255, 0 | day offset |
| `hgrk` | 1505 | 0x11 | 0..27 | 0, 4, 6, 13, 17 | season-highest rank |
| `info` | 1494 | 0x11,0x0b,0x0a,0x03,0x12 | 0..750 | 40, 90, 75, 70, 3 | generic info/count value |
| `fxds` | 1494 | 0x0b,0x0a | 0..81 | 17, 3, 4, 21, 8 | fixtures entity |
| `mtrl` | 1422 | 0x02 | refs:    ×622,     ×294,    ×147,   ×78 | ->    , ->   , ->   , ->   , ->    | **TBD** |
| `tems` | 1373 | 0x0b,0x11 | 0..80 | 3, 1, 0, 4, 2 | team count (stage) |
| `subr` | 1288 | 0x11 | 0..69 | 55, 30, 0, 20, 6 | sub-round |
| `semt` | 1274 | 0x11 | 0..9 | 1, 0, 2, 8, 9 | ? |
| `date` | 1233 | 0x0a | 2..8 | 5, 4, 3, 2, 6 | date entity |
| `styr` | 1202 | 0x12 | 2000..2027 | 2021, 2020, 2022, 2024, 2017 | start year |
| `nmsn` | 1159 | 0x0a,0x11,0x12 | 2..167 | 2, 3, 21, 108, 109 | season name/num? |
| `endt` | 1151 | 0x0a | 3..7 | 3, 5, 4, 6, 7 | end date |
| `prio` | 1107 | 0x11 | 1..10 | 4, 2, 5, 6, 3 | priority (seeding) |
| `bsyo` | 1067 | 0x11 | 0..255 | 0, 1, 255, 2 | bool flag |
| `sdfd` | 1053 | 0x0a | 2..5 | 3, 4, 5, 2 | start-date field? |
| `vers` | 1017 | 0x11 | 0..6 | 1, 5, 4, 6, 3 | version |
| `lsdi` | 1017 | 0x11 | 0..44 | 10, 12, 20, 8, 0 | **TBD** |
| `drdt` | 1007 | 0x0a | 1..6 | 2, 3, 6, 4, 5 | draw date? |
| `nmlg` | 1004 | 0x11 | 1..2 | 2, 1 | num legs |
| `tvds` | 991 | 0x0b | 0..28 | 12, 9, 7, 1, 0 | **TBD** |
| `enyr` | 939 | 0x12 | 2000..2025 | 2020, 2000, 2019, 2023, 2021 | end year |
| `strq` | 937 | 0x0b,0x11 | 0..6 | 0, 1, 2, 3, 4 | ?stage-seq |
| `ftac` | 933 | 0x0b | 0..18 | 0, 1, 4, 2, 3 | ?(rank flag) |
| `edfd` | 883 | 0x0a | 2..5 | 3, 4, 5, 2 | end-date field? |
| `nwdt` | 842 | 0x0a | 5..5 | 5 | ?date |
| `bsyi` | 830 | 0x03,0x11,0x12 | 0..1000 | 1, 0, 2, 4, 100 | bool flag |
| `mtdy` | 825 | 0x0a,0x0b | 0..4 | 3, 2, 1, 4, 0 | match day |
| `nrpl` | 820 | 0x11 | 0..14 | 1, 0, 6, 2, 3 | ?num replays |
| `nmxt` | 820 | 0x11,0x12 | 0..292 | 2, 4, 0, 1, 6 | num next / matches-to-play |
| `sqsr` | 808 | 0x0b,0x12 | 0..350 | 1, 3, 2, 0, 10 | ?squad-season ref |
| `sche` | 804 | 0x0b | 0..2 | 1, 0, 2 | scheduled flag |
| `posn` | 795 | 0x11 | 0..19 | 0, 1, 2, 3, 4 | finishing position (for prize) |
| `vlgr` | 770 | 0x0b,0x03 | 0..11 | 0, 2, 1, 4, 6 | **TBD** |
| `srcc` | 724 | 0x03 | 0..1 | 0, 1 | bool flag |
| `stmn` | 690 | 0x11 | 1..12 | 7, 9, 11, 1, 3 | start month |
| `enmn` | 690 | 0x11 | 1..12 | 8, 6, 1, 2, 4 | end month |
| `bsyr` | 680 | 0x12 | 1998..2027 | 2000, 2017, 2021, 2015, 2016 | base/season year |
| `topp` | 675 | 0x11 | 0..60 | 0, 4, 3, 6, 2 | top places promoted / qualifying |
| `ftye` | 667 | 0x11 | 1..12 | 12, 10, 11, 1, 2 | ?fixture-type month? |
| `Bran` | 667 | 0x12,0x11,0x02 | refs:   «×16 | 1435, 1437, 1436, 1452, 0 | ?brand/entity ref (~1435) |
| `XSvC` | 667 | 0x11,0x12 | 1..172 | 2, 51, 13, 4, 3 | ? |
| `fsdi` | 667 | 0x11 | 0..255 | 21, 9, 0, 1, 2 | **TBD** |
| `lfte` | 664 | 0x11 | 1..255 | 255, 6, 4, 1, 2 | **TBD** |
| `drrl` | 664 | 0x02 | refs:    ×105,     ×87,    H×66,    ×53 | ->   , ->   H, ->  , ->    , ->    | draw rule |
| `bnsc` | 662 | 0x11 | 0..5 | 5, 2, 3, 1, 0 | **TBD** |
| `fxri` | 651 | 0x11 | 0..255 | 2, 8, 7, 1, 3 | ?fixture rule index |
| `pref` | 642 | 0x03 | 0..1 | 0, 1 | bool flag |
| `aldt` | 632 | 0x0b | 0..33 | 2, 0, 9, 8, 5 | ?date-related (0..8) |
| `sort` | 612 | 0x0b,0x11 | 0..10 | 2, 4, 3, 5, 6 | sort order |
| `ctmp` | 608 | 0x0b | 0..9 | 0, 3, 2, 4, 1 | **TBD** |
| `nmrp` | 603 | 0x11 | 0..1 | 0, 1 | bool flag |
| `tcpf` | 587 | 0x03 | 0..1 | 0, 1 | bool flag |
| `dats` | 584 | 0x0b | 0..34 | 5, 2, 21, 31, 28 | date value (day-of-month-ish) |
| `gmsb` | 582 | 0x11 | 1..2 | 2, 1 | ?(1/2) flag |
| `usqn` | 578 | 0x03 | 0..1 | 1, 0 | bool flag |
| `rank` | 578 | 0x0b,0x03 | 0..28 | 18, 4, 2, 0, 12 | rank/position? |
| `advs` | 577 | 0x0b | 0..3 | 1, 0, 3 | **TBD** |
| `inac` | 543 | 0x03 | 0..1 | 0, 1 | inactive flag |
| `btpl` | 535 | 0x11 | 0..255 | 3, 7, 0, 11, 2 | bottom places relegated |
| `nati` | 529 | 0x0a,0x12,0x01 | 2..918748 | 2, 3, 769, 917496, 918740 | nation |
| `nrds` | 511 | 0x11 | 0..5 | 4, 2, 3, 5, 1 | number of rounds |
| `rsvt` | 488 | 0x02,0x11 | refs:    ×20,    ×16,    !×6,    0×6 | ->   , 0, 1, 2, ->    | **TBD** |
| `ygap` | 487 | 0x11 | 1..100 | 4, 2, 100, 1 | ?year gap |
| `ind1` | 484 | 0x11 | 0..31 | 0, 5, 2, 1, 28 | index |
| `styo` | 482 | 0x11 | 0..255 | 1, 0, 255 | start-year flag? |
| `chcl` | 482 | 0x11,0x03 | 0..7 | 1, 2, 3, 0, 5 | ? |
| `bkdw` | 474 | 0x11 | 1..7 | 1, 4, 7, 3, 5 | block day-of-week |
| `stgs` | 466 | 0x0b | 0..18 | 5, 1, 7, 4, 3 | number of stages |
| `enyo` | 459 | 0x11 | 0..3 | 1, 0, 2, 3 | end-year flag? |
| `dtrn` | 456 | 0x0a | 5..5 | 5 | **TBD** |
| `ilgf` | 455 | 0x03 | 0..0 | 0 | bool flag |
| `spld` | 454 | 0x11 | 1..36 | 12, 13, 14, 3, 1 | split? |
| `Nnat` | 426 | 0x11,0x12,0x01 | 5..62002127 | 110, 111, 112, 113, 125 | nation id (110..141, nation-space) |
| `sed1` | 426 | 0x11 | 0..20 | 2, 1, 0, 12, 13 | seed 1 |
| `sed2` | 426 | 0x11 | 0..21 | 2, 3, 12, 10, 13 | seed 2 |
| `pvrn` | 420 | 0x11,0x0a,0x12 | 2..164 | 18, 6, 7, 2, 3 | **TBD** |
| `wrnk` | 413 | 0x0a | 2..4 | 4, 2, 3 | world/reputation rank (crk/lwrk/hgrk) |
| `lrnk` | 413 | 0x0a | 2..4 | 2, 4 | STANDINGS atom: one team's rank in a stage (crk + team-slot + stnm + ntms) |
| `spdO` | 410 | 0x11 | 0..255 | 0, 235, 245, 249, 1 | **TBD** |
| `dcin` | 405 | 0x11 | 0..255 | 1, 2, 0, 5, 255 | ? |
| `rnds` | 403 | 0x0b | 1..11 | 1, 2, 3, 4, 7 | rounds |
| `srnd` | 403 | 0x0a | 1..6 | 4, 2, 5, 6, 1 | seeded round (subr/prio/drrl draw-rule/rnds) |
| `decd` | 396 | 0x11 | 0..6 | 0, 1, 2, 5, 4 | ?decided flag/count |
| `rkli` | 395 | 0x0b | 0..28 | 18, 12, 0, 11, 4 | ?rank-list size? |
| `gpid` | 395 | 0x11 | 0..15 | 0, 1, 2, 3, 4 | group id |
| `ACfl` | 389 | 0x02 | refs:     ×266,    ×60,    ×19,    ×10 | ->   , ->    , ->  , ->   , -> @   | **TBD** |
| `dat2` | 384 | 0x0a | 3..7 | 4, 5, 3, 6, 7 | date entity 2 |
| `brpd` | 378 | 0x0b | 0..5 | 1, 0, 2, 5, 3 | **TBD** |
| `sequ` | 372 | 0x11 | 0..45 | 38, 2, 14, 30, 6 | sequence no. |
| `idwi` | 370 | 0x11 | 1..7 | 7, 1, 2, 3, 4 | index |
| `ctin` | 367 | 0x11 | 0..8 | 0, 1, 2, 3, 4 | ?counter/index |
| `plty` | 364 | 0x11 | 0..10 | 1, 0, 2, 7, 10 | ?playoff/penalty type |
| `natl` | 362 | 0x0b | 0..12 | 0, 12, 4 | ?nation level/flag |
| `ptsd` | 361 | 0x0b | 0..6 | 0, 2, 1, 3, 4 | ?points config (0..6) |
| `iEsT` | 359 | 0x03 | 0..1 | 0, 1 | bool flag |
| `Cdpc` | 358 | 0x0b | 0..8 | 0, 2, 1, 8, 3 | **TBD** |
| `ttac` | 349 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `pare` | 348 | 0x0a | 2..3 | 2, 3 | parent competition (comp ref) |
| `SrTs` | 346 | 0x11 | 0..21 | 10, 0, 12, 7, 11 | ? |
| `itvm` | 342 | 0x0b | 0..22 | 1, 8, 0, 22, 19 | **TBD** |
| `fnrg` | 338 | 0x0b | 0..20 | 15, 1, 0, 20, 18 | **TBD** |
| `FxSt` | 337 | 0x0b | 0..7 | 0, 1, 2, 6, 3 | **TBD** |
| `ddsd` | 325 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `accm` | 324 | 0x0a | 3..4 | 4, 3 | **TBD** |
| `vsdp` | 320 | 0x0b | 0..1 | 1, 0 | **TBD** |
| `MtTv` | 319 | 0x0b | 0..9 | 0, 1, 8, 2, 3 | **TBD** |
| `hlps` | 318 | 0x0b | 0..5 | 0, 1, 3, 2, 4 | **TBD** |
| `relr` | 315 | 0x0a,0x11 | 1..7 | 3, 5, 4, 7, 2 | relegation-related |
| `mnpl` | 315 | 0x11 | 0..25 | 1, 2, 3, 4, 0 | **TBD** |
| `stvd` | 314 | 0x0b | 0..12 | 5, 0, 9, 3, 12 | **TBD** |
| `lgto` | 314 | 0x0b | 0..1 | 0, 1 | ?league config flag |
| `crgt` | 314 | 0x0b | 0..68 | 0, 29, 28, 58, 55 | **TBD** |
| `srci` | 302 | 0x0a | 4..4 | 4 | **TBD** |
| `sfsr` | 302 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `ldos` | 302 | 0x11 | 1..255 | 1, 255, 2, 4 | **TBD** |
| `rdci` | 300 | 0x0a | 3..4 | 3, 4 | **TBD** |
| `rdcr` | 300 | 0x11 | 0..9 | 8, 0, 2, 3, 6 | **TBD** |
| `sbty` | 300 | 0x11 | 1..33 | 1, 2, 27, 26, 12 | ?subs type? |
| `ctll` | 299 | 0x0b | 0..32 | 0, 4, 8, 3, 16 | **TBD** |
| `lgfx` | 298 | 0x0b | 0..2 | 1, 0, 2 | **TBD** |
| `mxss` | 294 | 0x11 | 0..99 | 99, 30, 2, 1, 40 | **TBD** |
| `dsbi` | 294 | 0x0a | 3..3 | 3 | **TBD** |
| `cnic` | 289 | 0x03 | 0..1 | 0, 1 | bool flag |
| `mxpl` | 289 | 0x11 | 0..25 | 1, 2, 3, 4, 5 | **TBD** |
| `fxor` | 277 | 0x11 | 0..9 | 1, 0, 6, 8, 2 | fixture order |
| `rats` | 271 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `fate` | 268 | 0x11 | 0..255 | 2, 0, 255, 4, 1 | **TBD** |
| `GmTy` | 263 | 0x11 | 1..6 | 4, 5, 6, 1 | **TBD** |
| `rgdv` | 263 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `rmic` | 257 | 0x03 | 0..1 | 1, 0 | bool flag |
| `qtsd` | 256 | 0x11 | 0..100 | 0, 90, 91, 92, 93 | **TBD** |
| `typz` | 255 | 0x0b | 0..49 | 16, 8, 14, 12, 20 | **TBD** |
| `jcom` | 244 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `wnty` | 240 | 0x11 | 1..39 | 7, 1, 9, 6, 20 | **TBD** |
| `tfxt` | 235 | 0x0b | 0..30 | 0, 2, 3, 1, 15 | ?fixture text/type |
| `nssn` | 235 | 0x0a,0x11 | 2..18 | 2, 18, 3 | season/stage STRUCTURE incl split-group + embedded team-slot rank snapshot |
| `quty` | 235 | 0x11 | 1..9 | 3, 2, 4, 1, 9 | **TBD** |
| `stdm` | 234 | 0x11 | 1..31 | 1, 24, 31, 21, 4 | start day-of-month |
| `endm` | 234 | 0x11 | 1..31 | 31, 30, 29, 28, 20 | end day-of-month |
| `hcti` | 234 | 0x11 | 0..20 | 0, 5, 4, 3, 1 | **TBD** |
| `spst` | 231 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `rsid` | 230 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `sths` | 230 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `rst1` | 226 | 0x11 | 0..18 | 0, 1, 10, 3, 12 | **TBD** |
| `pots` | 224 | 0x11,0x0b | 1..30 | 6, 9, 5, 21, 10 | **TBD** |
| `iqum` | 224 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `uhtt` | 224 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `bktm` | 223 | 0x12,0x11 | 0..2100 | 1945, 1400, 1300, 1330, 2030 | **TBD** |
| `wnpz` | 221 | 0x0a,0x01 | 2..88000 | 3, 2, 88000 | winner prize |
| `stad` | 219 | 0x01,0x12 | 838..2000029204 | 2000029204, 68005347, 8826792, 980, 741569 | **TBD** |
| `qurl` | 219 | 0x0b,0x11 | 0..4 | 2, 1, 0, 3, 4 | qualification rule? |
| `sqsv` | 218 | 0x11 | 4..41 | 8, 28, 41, 25, 4 | **TBD** |
| `utic` | 218 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `Bktm` | 216 | 0x11 | 0..100 | 18, 20, 12, 28, 16 | bracket teams |
| `vlys` | 214 | 0x0b | 0..4 | 1, 2, 3, 4, 0 | **TBD** |
| `frty` | 211 | 0x03,0x11 | 0..1 | 0, 1 | **TBD** |
| `atin` | 210 | 0x11 | 0..17 | 1, 0, 2, 6, 3 | **TBD** |
| `stdw` | 210 | 0x11 | 1..7 | 7, 6, 1, 4 | start day-of-week |
| `endw` | 210 | 0x11 | 1..7 | 1, 7, 4 | end day-of-week |
| `sfar` | 208 | 0x11 | 1..10 | 2, 1, 3, 6, 10 | **TBD** |
| `edtv` | 205 | 0x11 | 0..4 | 2, 0, 1, 3, 4 | **TBD** |
| `mtdr` | 200 | 0x11 | 1..8 | 1, 8, 2 | **TBD** |
| `city` | 200 | 0x01,0x0a,0x12,0x11 | 2..74009628 | 100024, 102586, 102583, 74009628, 2 | **TBD** |
| `snrp` | 198 | 0x0a | 2..4 | 3, 2, 4 | **TBD** |
| `blpm` | 197 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `lspz` | 195 | 0x0a,0x12,0x01 | 2..52750 | 3, 2, 14000, 28000, 52750 | ?prize |
| `hdty` | 194 | 0x11 | 1..8 | 3, 4, 5, 8, 2 | **TBD** |
| `dtfl` | 188 | 0x02 | refs:    ×46,     ×31,    ×30,    ×23 | ->   , ->   , ->  , ->   A, ->     | **TBD** |
| `prmr` | 182 | 0x0a,0x11 | 2..6 | 5, 4, 3, 2, 6 | promotion-related |
| `lcrl` | 174 | 0x0a,0x01 | 2..156580 | 2, 156580, 3 | **TBD** |
| `apmn` | 174 | 0x0b,0x0a | 0..3 | 1, 0, 2, 3 | ?appearance money |
| `PrSt` | 173 | 0x0b,0x02 | refs:     ×100,    ×25,    ×3,    ×3 | 1, ->   , ->   , 2, ->     | **TBD** |
| `rmnn` | 173 | 0x03 | 1..1 | 1 | **TBD** |
| `RdPr` | 173 | 0x11 | 0..0 | 0 | **TBD** |
| `TiTu` | 171 | 0x12 | 1230..2100 | 1730, 2000, 1330, 1400, 1800 | TV kickoff time slot (HHMM) |
| `sdnf` | 168 | 0x02 | refs:    ×38,   ×18,   ×16,    ×12 | ->   , ->   , ->  , ->   , ->À  | **TBD** |
| `MlsY` | 168 | 0x12 | 2021..2027 | 2021, 2022, 2023, 2024, 2025 | **TBD** |
| `tmPL` | 167 | 0x0b | 1..30 | 1, 2, 3, 12, 4 | **TBD** |
| `ngps` | 164 | 0x11 | 1..16 | 2, 4, 6, 3, 8 | **TBD** |
| `lsdv` | 163 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `cmps` | 161 | 0x0b | 1..19 | 7, 6, 3, 4, 8 | **TBD** |
| `nmdt` | 160 | 0x11 | 2..46 | 20, 24, 22, 34, 18 | **TBD** |
| `srsd` | 160 | 0x0a | 4..6 | 5, 4, 6 | **TBD** |
| `sred` | 160 | 0x0a | 4..5 | 5, 4 | **TBD** |
| `sblt` | 156 | 0x0b | 0..1 | 0, 1 | **TBD** |
| `usfr` | 151 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `updy` | 149 | 0x0a | 3..3 | 3 | **TBD** |
| `alct` | 149 | 0x11 | 0..15 | 1, 2, 0, 3, 5 | **TBD** |
| `alti` | 149 | 0x11 | 0..0 | 0 | **TBD** |
| `snen` | 146 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `rvtm` | 146 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `mstc` | 145 | 0x12,0x11,0x01 | 0..70000 | 5000, 1500, 3000, 300, 12500 | **TBD** |
| `CcQR` | 143 | 0x0b | 0..7 | 7, 0, 5, 6, 1 | **TBD** |
| `lnrl` | 142 | 0x0b | 0..47 | 0, 3, 1, 8, 4 | **TBD** |
| `snst` | 142 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `mnsc` | 142 | 0x12,0x11,0x01 | 0..70000 | 8000, 4000, 10000, 1500, 12500 | **TBD** |
| `HdRl` | 142 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `ignt` | 141 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `lgrl` | 140 | 0x02 | refs:    ×54,    ×20,    ×17,    ×14 | ->   , ->   , ->   , ->   p, ->  P | **TBD** |
| `fnlc` | 134 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `exlg` | 133 | 0x0b | 0..2 | 1, 2, 0 | **TBD** |
| `Ufss` | 132 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `tppr` | 132 | 0x0a,0x11 | 0..10 | 6, 4, 5, 0, 7 | **TBD** |
| `grrl` | 131 | 0x02 | refs:    ×30,     ×30,   ×20,     ×8 | ->  , ->   , ->   , ->  , ->   | **TBD** |
| `gnty` | 131 | 0x11 | 0..7 | 7, 3, 1, 0, 5 | **TBD** |
| `gpdt` | 131 | 0x0b | 0..16 | 2, 4, 0, 10, 3 | **TBD** |
| `ngrt` | 131 | 0x11 | 1..20 | 12, 20, 14, 1, 13 | **TBD** |
| `snrd` | 130 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `reas` | 130 | 0x11 | 2..10 | 7, 6, 10, 2, 8 | **TBD** |
| `dsrl` | 128 | 0x0b,0x0a | 1..7 | 2, 3, 1, 7, 4 | **TBD** |
| `ncmp` | 128 | 0x0a | 2..3 | 2, 3 | nested/child competition |
| `fxrl` | 127 | 0x0b,0x0a | 1..14 | 5, 11, 4, 6, 2 | **TBD** |
| `RkIn` | 127 | 0x11 | 1..20 | 1, 20, 11, 7, 4 | **TBD** |
| `hlct` | 125 | 0x11 | 0..13 | 0, 2, 1, 4, 6 | **TBD** |
| `hlti` | 125 | 0x11 | 0..0 | 0 | **TBD** |
| `aqtp` | 124 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `Cfdf` | 124 | 0x11,0x12 | 16..512 | 16, 64, 512, 32, 256 | **TBD** |
| `scnc` | 123 | 0x03 | 1..1 | 1 | **TBD** |
| `stfl` | 121 | 0x02 | refs:    ×71,    ×26,    ×13,    ×4 | ->  , ->   , ->   , ->   , ->    | **TBD** |
| `sndr` | 118 | 0x11 | 0..3 | 0, 1, 2, 3 | **TBD** |
| `wkpm` | 118 | 0x0a | 1..5 | 5, 1, 4 | **TBD** |
| `sseg` | 114 | 0x02 | refs:    ×36,    ×18,    ×10,   ×6 | ->   , ->   , -> @  , ->   , ->     | **TBD** |
| `sudt` | 114 | 0x0a | 4..6 | 5, 4, 6 | **TBD** |
| `expd` | 114 | 0x12,0x02,0x01 | refs:    ×10,  P ×8,   P ×6,   ×6 | 4096, ->   , ->  À, -> ü, ->  P | **TBD** |
| `tfrd` | 112 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `ofdi` | 112 | 0x11 | 0..255 | 255, 1, 0, 2, 9 | **TBD** |
| `oldi` | 112 | 0x11 | 1..255 | 36, 31, 255, 1, 2 | **TBD** |
| `CcEx` | 110 | 0x0b | 0..0 | 0 | **TBD** |
| `Per%` | 109 | 0x11 | 10..100 | 50, 60, 40, 69, 100 | **TBD** |
| `lpcr` | 108 | 0x11 | 1..4 | 1, 4, 2, 3 | **TBD** |
| `shsn` | 107 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `lgin` | 107 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `dvlv` | 106 | 0x0b | 1..6 | 2, 1, 3, 4, 6 | **TBD** |
| `retm` | 106 | 0x0b | 2..90 | 11, 18, 6, 13, 4 | **TBD** |
| `rsvl` | 106 | 0x0b | 0..13 | 3, 5, 2, 6, 0 | **TBD** |
| `trwi` | 106 | 0x0b | 2..13 | 4, 2, 3, 5, 8 | **TBD** |
| `sswn` | 106 | 0x0b | 1..5 | 3, 2, 1, 5, 4 | **TBD** |
| `WdDa` | 106 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `dfdl` | 104 | 0x11 | 0..3 | 1, 0, 2, 3 | **TBD** |
| `rsno` | 104 | 0x0b | 0..1 | 0, 1 | **TBD** |
| `trrl` | 104 | 0x0a | 4..25 | 10, 13, 12, 5, 8 | **TBD** |
| `natr` | 104 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `stdr` | 104 | 0x0b | 1..13 | 4, 8, 1, 2, 5 | **TBD** |
| `wdft` | 102 | 0x12 | 1330..2100 | 1500, 1530, 1330, 2100, 1930 | **TBD** |
| `mdft` | 102 | 0x12 | 1500..2100 | 2000, 1930, 1800, 1530, 1900 | **TBD** |
| `exfp` | 102 | 0x0b | 0..2 | 0, 1, 2 | **TBD** |
| `mnmt` | 102 | 0x11 | 2..34 | 11, 22, 9, 10, 34 | **TBD** |
| `sfal` | 99 | 0x0b | 0..10 | 1, 6, 3, 7, 2 | **TBD** |
| `strs` | 99 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `cnti` | 99 | 0x0a | 2..2 | 2 | **TBD** |
| `CpTT` | 98 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `cont` | 97 | 0x03,0x11 | 1..6 | 1, 3, 4, 6, 2 | **TBD** |
| `TrCm` | 96 | 0x0b | 0..2 | 0, 2 | **TBD** |
| `CrTm` | 96 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `mcld` | 95 | 0x11 | 1..3 | 3, 2, 1 | **TBD** |
| `ssnd` | 94 | 0x0a | 3..6 | 5, 3, 4, 6 | **TBD** |
| `snms` | 94 | 0x11 | 23..99 | 30, 33, 99, 23, 40 | **TBD** |
| `sqdt` | 94 | 0x0a | 4..6 | 5, 4, 6 | **TBD** |
| `mdsw` | 92 | 0x0b | 0..4 | 2, 0, 1, 3, 4 | **TBD** |
| `prsw` | 92 | 0x0b | 0..0 | 0 | **TBD** |
| `agdt` | 91 | 0x0a | 4..4 | 4 | **TBD** |
| `wnCT` | 90 | 0x12 | 1700..2400 | 2400, 2300, 1700, 1800, 1900 | **TBD** |
| `mxmt` | 90 | 0x11 | 2..34 | 11, 22, 9, 10, 34 | **TBD** |
| `lcrg` | 90 | 0x01 | 14005139..67249095 | 54002973, 54002978, 54002977, 54002979, 54002980 | **TBD** |
| `btpr` | 89 | 0x0a,0x11 | 0..7 | 6, 0, 2, 4, 7 | bottom places (relegation) variant |
| `WrWt` | 88 | 0x11 | 1..7 | 1, 2, 4, 7 | **TBD** |
| `lsps` | 85 | 0x11 | 0..15 | 0, 1, 2, 3, 4 | **TBD** |
| `WbDl` | 84 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `btfo` | 83 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `pris` | 83 | 0x11,0x0b | 0..6 | 6, 3, 1, 2, 0 | **TBD** |
| `pOsT` | 83 | 0x11 | 0..4 | 1, 2, 3, 4, 0 | **TBD** |
| `VRrl` | 81 | 0x0b | 1..6 | 1, 2, 3, 4, 5 | **TBD** |
| `snda` | 80 | 0x0a | 2..4 | 3, 2, 4 | **TBD** |
| `sdtr` | 80 | 0x0b | 1..4 | 2, 1, 3, 4 | **TBD** |
| `hmtm` | 80 | 0x0b,0x11 | 0..100 | 2, 1, 3, 5, 82 | **TBD** |
| `nrdw` | 77 | 0x11 | 1..255 | 2, 255, 3, 5, 4 | ?wins-related (candidate W) |
| `SgSd` | 76 | 0x0b | 0..6 | 2, 3, 4, 0, 1 | **TBD** |
| `sfst` | 75 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `pspl` | 75 | 0x0a,0x03 | 1..12 | 11, 10, 12, 5, 6 | split? |
| `mxto` | 75 | 0x11,0x12 | 1..155 | 1, 2, 32, 104, 23 | **TBD** |
| `rndt` | 74 | 0x03,0x0b | 0..4 | 1, 0, 4 | **TBD** |
| `snrf` | 73 | 0x02 | refs:    ×51,    ×12,    @×10 | ->   , ->   @, ->    | **TBD** |
| `nelt` | 73 | 0x11 | 0..255 | 0, 254, 1, 2, 252 | **TBD** |
| `d2lA` | 72 | 0x11,0x12 | 10..365 | 83, 66, 73, 67, 74 | **TBD** |
| `ckch` | 71 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `ckpr` | 71 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `ckcc` | 71 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `ckrl` | 71 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `plyf` | 71 | 0x02 | refs:     ×71 | ->     | **TBD** |
| `nrdl` | 70 | 0x11 | 1..255 | 1, 255, 2, 4, 3 | ?losses-related (candidate L) |
| `cts1` | 70 | 0x11 | 0..5 | 0, 2, 5 | **TBD** |
| `pwin` | 69 | 0x11 | 3..4 | 3, 4 | **TBD** |
| `igma` | 69 | 0x03 | 1..1 | 1 | **TBD** |
| `awtm` | 67 | 0x0b,0x11 | 0..50 | 2, 18, 3, 0, 25 | **TBD** |
| `dahr` | 67 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `sr2c` | 67 | 0x11 | 0..5 | 3, 2, 5, 0, 1 | **TBD** |
| `hdst` | 67 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `osti` | 67 | 0x11 | 0..2 | 1, 0, 2 | **TBD** |
| `FAif` | 66 | 0x0b | 0..2 | 0, 1, 2 | **TBD** |
| `sch?` | 65 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `clyc` | 65 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `ofxd` | 65 | 0x0a | 2..3 | 3, 2 | **TBD** |
| `frtj` | 64 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `ddlf` | 64 | 0x02 | refs:    ×24,     ×18,   2×4,   ×4 | ->   , ->   , ->  gb, ->  v, ->  'v | **TBD** |
| `nfxd` | 64 | 0x0a | 2..3 | 3, 2 | **TBD** |
| `ScQt` | 64 | 0x0b | 0..9 | 9, 1, 6, 3, 4 | **TBD** |
| `nplt` | 63 | 0x11 | 1..6 | 1, 6, 3, 2 | **TBD** |
| `nprt` | 63 | 0x11 | 0..3 | 1, 2, 0, 3 | **TBD** |
| `AfxD` | 63 | 0x0b | 0..4 | 1, 0, 3, 2, 4 | **TBD** |
| `tppl` | 62 | 0x11 | 1..6 | 1, 6, 3, 2 | **TBD** |
| `pplc` | 62 | 0x11 | 0..3 | 1, 2, 0, 3 | **TBD** |
| `bppu` | 62 | 0x11 | 1..2 | 1, 2 | **TBD** |
| `nwpt` | 62 | 0x11 | 1..2 | 1, 2 | **TBD** |
| `pdrw` | 61 | 0x11 | 1..2 | 1, 2 | **TBD** |
| `RLtm` | 61 | 0x0a | 2..4 | 3, 4, 2 | **TBD** |
| `CfOD` | 59 | 0x0a | 3..5 | 4, 5, 3 | **TBD** |
| `CnRl` | 58 | 0x0a | 1..2 | 2, 1 | **TBD** |
| `SCsn` | 58 | 0x0a | 2..2 | 2 | stage config (stgn, tems, lgto, stnm) |
| `cnem` | 56 | 0x11 | 5..12 | 12, 6, 11, 10, 5 | **TBD** |
| `snfl` | 56 | 0x02 | refs:    ×8,   ×8,   ×8,   ×6 | ->   , ->  , ->   , ->  , ->   | **TBD** |
| `mage` | 56 | 0x03 | 1..1 | 1 | **TBD** |
| `TrSt` | 55 | 0x0a | 4..6 | 6, 4, 5 | **TBD** |
| `plfd` | 54 | 0x11 | 2..7 | 5, 2, 4, 7 | **TBD** |
| `pts1` | 54 | 0x11 | 0..33 | 5, 0, 4, 6, 20 | **TBD** |
| `pts2` | 54 | 0x11 | 0..30 | 11, 2, 5, 0, 8 | **TBD** |
| `pts3` | 54 | 0x11 | 0..25 | 5, 15, 21, 4, 0 | **TBD** |
| `pts4` | 54 | 0x11 | 0..27 | 7, 2, 3, 4, 27 | **TBD** |
| `pts5` | 54 | 0x11 | 0..24 | 3, 6, 10, 18, 2 | **TBD** |
| `crlm` | 53 | 0x0b | 0..18 | 2, 9, 6, 0, 4 | **TBD** |
| `pced` | 51 | 0x11 | 0..20 | 1, 18, 0, 7, 20 | **TBD** |
| `poed` | 51 | 0x11 | 0..1 | 1, 0 | **TBD** |
| `rfpr` | 51 | 0x0a | 2..4 | 2, 4 | **TBD** |
| `TtUl` | 50 | 0x0b | 2..5 | 2, 3, 4, 5 | **TBD** |
| `DOmf` | 50 | 0x0b | 0..4 | 2, 3, 4, 1, 0 | **TBD** |
| `gsyo` | 48 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `updv` | 48 | 0x0a | 2..2 | 2 | **TBD** |
| `lwdv` | 48 | 0x0a | 2..2 | 2 | **TBD** |
| `OPpr` | 48 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `StPl` | 47 | 0x0b | 1..15 | 1, 3, 4, 2, 10 | **TBD** |
| `chdc` | 47 | 0x0b | 0..21 | 2, 3, 4, 5, 9 | **TBD** |
| `usRU` | 46 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `usTP` | 46 | 0x03 | 0..0 | 0 | **TBD** |
| `LtfP` | 45 | 0x0b | 1..21 | 6, 2, 1, 8, 4 | **TBD** |
| `bcr1` | 44 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `bcr3` | 44 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `lpcp` | 44 | 0x11 | 1..4 | 1, 4, 2, 3 | **TBD** |
| `swtm` | 44 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `bupd` | 44 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `ByTm` | 44 | 0x0b | 0..5 | 0, 2, 3, 5, 1 | **TBD** |
| `pfpr` | 44 | 0x0a | 2..4 | 4, 2 | **TBD** |
| `shnt` | 43 | 0x11 | 12..18 | 18, 12, 14, 16 | **TBD** |
| `t001` | 43 | 0x11 | 2..254 | 240, 254, 3, 252, 5 | **TBD** |
| `t002` | 43 | 0x11 | 1..255 | 241, 1, 240, 253, 4 | **TBD** |
| `t003` | 43 | 0x11 | 1..255 | 242, 15, 255, 2, 240 | **TBD** |
| `t004` | 43 | 0x11 | 1..255 | 243, 14, 241, 1, 254 | **TBD** |
| `t005` | 43 | 0x11 | 1..255 | 244, 13, 242, 15, 255 | **TBD** |
| `t006` | 43 | 0x11 | 1..255 | 245, 12, 243, 14, 241 | **TBD** |
| `bcr2` | 42 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `bcr5` | 42 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `bcr4` | 42 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `PSfd` | 42 | 0x0a | 3..4 | 4, 3 | **TBD** |
| `btms` | 42 | 0x11,0x03 | 0..1 | 1, 0 | **TBD** |
| `mnpc` | 42 | 0x11 | 1..10 | 3, 4, 1, 10 | **TBD** |
| `dasn` | 41 | 0x03 | 1..1 | 1 | **TBD** |
| `cann` | 40 | 0x03 | 0..0 | 0 | **TBD** |
| `fcmn` | 40 | 0x11 | 1..17 | 16, 17, 1, 15 | **TBD** |
| `pspd` | 40 | 0x11 | 15..106 | 40, 35, 50, 15, 28 | **TBD** |
| `bcr6` | 40 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `wpdw` | 40 | 0x11 | 120..120 | 120 | **TBD** |
| `midp` | 40 | 0x11 | 2..100 | 2, 100, 12, 5, 4 | **TBD** |
| `MtGr` | 40 | 0x0b | 1..3 | 1, 3, 2 | **TBD** |
| `CmAc` | 39 | 0x03 | 1..1 | 1 | **TBD** |
| `ndCD` | 39 | 0x11 | 13..21 | 17, 19, 13, 21, 18 | **TBD** |
| `gmbl` | 38 | 0x0b | 2..6 | 6, 3, 4, 2 | **TBD** |
| `yccp` | 38 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `clty` | 38 | 0x11 | 0..3 | 1, 2, 0, 3 | **TBD** |
| `mgqm` | 38 | 0x11 | 0..10 | 5, 1, 0, 10 | **TBD** |
| `winr` | 38 | 0x11 | 0..63 | 0, 60, 63, 20 | **TBD** |
| `losr` | 38 | 0x11 | 37..100 | 100, 40, 37 | **TBD** |
| `spid` | 37 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `fsqt` | 37 | 0x0b | 1..8 | 4, 2, 1, 5, 8 | **TBD** |
| `trsd` | 36 | 0x0a | 3..3 | 3 | **TBD** |
| `pmdf` | 36 | 0x11 | 13..84 | 46, 45, 42, 26, 30 | **TBD** |
| `\seu` | 36 | 0x0a | 43..58 | 58, 53, 52, 54, 47 | **TBD** |
| `COdf` | 36 | 0x0a | 2..3 | 3, 2 | **TBD** |
| `MtFc` | 36 | 0x11 | 1..16 | 12, 16, 3, 1, 6 | **TBD** |
| `tvDd` | 35 | 0x0b | 1..16 | 1, 16, 3, 2, 10 | **TBD** |
| `btld` | 35 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `Cmp2` | 34 | 0x0a | 2..2 | 2 | **TBD** |
| `Draf` | 34 | 0x0b | 0..6 | 0, 6 | **TBD** |
| `NwTy` | 34 | 0x11 | 5..15 | 15, 5, 13, 14 | **TBD** |
| `ycmx` | 34 | 0x11 | 1..20 | 17, 1, 19, 18, 20 | **TBD** |
| `tmor` | 34 | 0x0b | 0..16 | 4, 0, 8, 16, 12 | **TBD** |
| `pdad` | 33 | 0x11 | 9..15 | 9, 12, 15, 10 | **TBD** |
| `srst` | 33 | 0x11 | 1..12 | 5, 1, 11, 7, 12 | **TBD** |
| `t007` | 33 | 0x11 | 1..255 | 246, 11, 244, 13, 242 | **TBD** |
| `t008` | 33 | 0x11 | 1..254 | 247, 10, 245, 12, 243 | **TBD** |
| `twbt` | 32 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `qsid` | 32 | 0x11 | 0..6 | 0, 4, 6 | **TBD** |
| `NoMd` | 32 | 0x11 | 18..50 | 22, 23, 20, 18, 50 | **TBD** |
| `litd` | 31 | 0x11 | 1..20 | 8, 9, 10, 20, 17 | **TBD** |
| `dyad` | 31 | 0x11 | 1..7 | 7, 6, 1 | **TBD** |
| `Bltp` | 31 | 0x0b | 0..1 | 0, 1 | **TBD** |
| `drpz` | 31 | 0x0a,0x01,0x11 | 2..62000 | 3, 62000, 2, 50 | **TBD** |
| `clyb` | 31 | 0x03 | 1..1 | 1 | **TBD** |
| `tyar` | 30 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `GtRc` | 29 | 0x0b | 1..9 | 1, 9, 2, 6 | **TBD** |
| `TlCh` | 29 | 0x0b | 1..10 | 6, 7, 1, 4, 3 | **TBD** |
| `cts2` | 29 | 0x11 | 1..6 | 1, 6 | **TBD** |
| `wopm` | 28 | 0x0a | 3..5 | 4, 5, 3 | **TBD** |
| `ctrn` | 28 | 0x0a | 4..5 | 4, 5 | **TBD** |
| `wtpm` | 28 | 0x0a | 4..4 | 4 | **TBD** |
| `usbs` | 28 | 0x03 | 1..1 | 1 | **TBD** |
| `scon` | 28 | 0x11 | 1..5 | 5, 2, 4, 1 | **TBD** |
| `lwtd` | 28 | 0x0a | 2..2 | 2 | **TBD** |
| `hgtd` | 28 | 0x0a | 2..2 | 2 | **TBD** |
| `MgaV` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `MtaV` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `PciV` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `SmSV` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `RmSV` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `MsCv` | 28 | 0x0a | 3..3 | 3 | **TBD** |
| `NmSt` | 28 | 0x11 | 1..30 | 30, 2, 1, 3, 4 | **TBD** |
| `stsi` | 28 | 0x11 | 0..3 | 3, 0, 2 | **TBD** |
| `amst` | 27 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `mdct` | 27 | 0x11,0x12 | 14..1000 | 14, 16, 1000, 21, 500 | **TBD** |
| `Igcp` | 27 | 0x0b | 1..7 | 7, 6, 5, 1, 4 | **TBD** |
| `WcSa` | 26 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `perd` | 26 | 0x11 | 1..7 | 2, 1, 4, 7 | **TBD** |
| `incm` | 26 | 0x02 | refs:   ?ÿ×20,   ï×4,     ×2 | ->  ?ÿ, ->    , ->  ï | **TBD** |
| `expt` | 26 | 0x02 | refs:  ºÿ×14,  ÿ×4,    ×4,    ×2 | -> ÿ, ->   , ->   , -> ºÿ, -> ÿ | **TBD** |
| `sanc` | 26 | 0x0b | 1..2 | 2, 1 | **TBD** |
| `mxex` | 26 | 0x11 | 1..99 | 2, 1, 30, 99, 15 | **TBD** |
| `CdSr` | 26 | 0x11 | 1..3 | 3, 1, 2 | **TBD** |
| `ind2` | 26 | 0x11 | 0..15 | 7, 15, 2, 0 | **TBD** |
| `\rut` | 25 | 0x0a | 12..58 | 12, 31, 52, 57, 58 | **TBD** |
| `shpo` | 25 | 0x11 | 0..10 | 0, 4, 6, 10, 8 | **TBD** |
| `SDty` | 25 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `WcSu` | 24 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `HgSq` | 24 | 0x11 | 22..99 | 40, 99, 24, 22 | **TBD** |
| `yrmn` | 24 | 0x11 | 15..17 | 15, 17, 16 | **TBD** |
| `trpr` | 24 | 0x11 | 50..121 | 50, 121, 120, 114, 100 | **TBD** |
| `trdl` | 24 | 0x11 | 0..0 | 0 | **TBD** |
| `ifdr` | 24 | 0x0b | 1..4 | 2, 1, 3, 4 | **TBD** |
| `WrDl` | 24 | 0x11 | 0..255 | 255, 0, 1, 2 | **TBD** |
| `hdlr` | 24 | 0x11 | 0..5 | 0, 1, 2, 3, 5 | **TBD** |
| `sqrw` | 24 | 0x0a,0x01 | 2..7860000 | 2, 7483354, 4, 7860000, 129558 | **TBD** |
| `nccc` | 24 | 0x11 | 2..10 | 2, 4, 3, 6, 10 | **TBD** |
| `SSEG` | 24 | 0x0b | 1..3 | 2, 1, 3 | **TBD** |
| `NinE` | 24 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `SefW` | 24 | 0x03 | 1..1 | 1 | **TBD** |
| `MtAc` | 24 | 0x0b | 2..2 | 2 | **TBD** |
| `UdFR` | 24 | 0x03 | 1..1 | 1 | **TBD** |
| `tfpr` | 24 | 0x0a | 2..4 | 2, 4, 3 | **TBD** |
| `AlOO` | 24 | 0x03 | 0..0 | 0 | **TBD** |
| `rnst` | 23 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `CnDr` | 22 | 0x0b | 0..2 | 1, 2, 0 | **TBD** |
| `trma` | 22 | 0x11 | 19..30 | 30, 19, 25 | **TBD** |
| `dist` | 22 | 0x11,0x12 | 60..2000 | 100, 60, 250, 500, 2000 | **TBD** |
| `smae` | 22 | 0x0a | 5..8 | 7, 6, 8, 5 | **TBD** |
| `rquh` | 21 | 0x03 | 1..1 | 1 | **TBD** |
| `nCcP` | 21 | 0x11 | 3..7 | 3, 5, 6, 7, 4 | **TBD** |
| `ettp` | 21 | 0x11 | 1..5 | 1, 3, 4, 5, 2 | **TBD** |
| `etbp` | 21 | 0x11 | 1..9 | 1, 3, 4, 7, 8 | **TBD** |
| `fycl` | 21 | 0x0a | 2..3 | 2, 3 | **TBD** |
| `mncc` | 21 | 0x11 | 10..25 | 12, 10, 25 | **TBD** |
| `nptp` | 21 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `cpmf` | 20 | 0x03 | 1..1 | 1 | **TBD** |
| `invm` | 20 | 0x0a,0x01 | 2..5000000 | 3, 2, 5000000 | **TBD** |
| `li-e` | 20 | 0x0a | 2..3 | 3, 2 | **TBD** |
| `cita` | 20 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `RnsP` | 20 | 0x03 | 1..1 | 1 | **TBD** |
| `avcp` | 19 | 0x0b | 0..8 | 1, 3, 8, 4, 0 | **TBD** |
| `yctf` | 19 | 0x11 | 1..6 | 6, 5, 1 | **TBD** |
| `IChf` | 19 | 0x11 | 1..4 | 1, 3, 2, 4 | **TBD** |
| `tplv` | 19 | 0x11 | 0..21 | 0, 6, 21, 5, 1 | **TBD** |
| `btlv` | 19 | 0x11 | 0..33 | 5, 12, 13, 14, 15 | **TBD** |
| `t009` | 19 | 0x11 | 2..255 | 8, 16, 246, 11, 244 | **TBD** |
| `t010` | 19 | 0x11 | 1..254 | 7, 248, 9, 16, 245 | **TBD** |
| `t011` | 19 | 0x11 | 2..255 | 6, 249, 8, 247, 10 | **TBD** |
| `t012` | 19 | 0x11 | 1..255 | 5, 250, 7, 248, 9 | **TBD** |
| `t013` | 19 | 0x11 | 2..255 | 4, 251, 6, 249, 8 | **TBD** |
| `t014` | 19 | 0x11 | 1..254 | 3, 252, 5, 250, 7 | **TBD** |
| `t015` | 19 | 0x11 | 2..255 | 2, 253, 4, 251, 6 | **TBD** |
| `t016` | 19 | 0x11 | 1..249 | 1, 247, 2, 246, 3 | **TBD** |
| `CnPe` | 18 | 0x11 | 0..5 | 0, 3, 1, 5, 4 | **TBD** |
| `rcfs` | 18 | 0x11 | 2..21 | 2, 21 | **TBD** |
| `BclT` | 18 | 0x11 | 1..4 | 1, 2, 4 | **TBD** |
| `pdef` | 18 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `ReTT` | 18 | 0x11 | 5..5 | 5 | **TBD** |
| `brex` | 18 | 0x03 | 1..1 | 1 | **TBD** |
| `nb23` | 18 | 0x03 | 1..1 | 1 | **TBD** |
| `\gra` | 18 | 0x0a | 12..45 | 12, 23, 44, 45, 43 | **TBD** |
| `tvDp` | 18 | 0x11,0x12 | 7..160 | 31, 18, 7, 160, 28 | **TBD** |
| `nmrg` | 18 | 0x11 | 2..23 | 2, 5, 23, 6, 4 | **TBD** |
| `derb` | 18 | 0x0b,0x01 | 1..72019020 | 1, 72019011, 72019010, 72019013, 72019014 | **TBD** |
| `idms` | 17 | 0x0a | 2..3 | 3, 2 | **TBD** |
| `1syr` | 17 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `ycfm` | 17 | 0x11,0x03 | 1..1 | 1 | **TBD** |
| `vwon` | 17 | 0x03 | 1..1 | 1 | **TBD** |
| `olpl` | 17 | 0x11 | 255..255 | 255 | **TBD** |
| `nwpl` | 17 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `DNSC` | 17 | 0x03 | 1..1 | 1 | **TBD** |
| `idts` | 17 | 0x03 | 1..1 | 1 | **TBD** |
| `iqtb` | 17 | 0x03 | 0..1 | 1, 0 | **TBD** |
| `masm` | 16 | 0x11 | 16..17 | 16, 17 | **TBD** |
| `WaRu` | 16 | 0x0b | 1..32 | 32, 1, 2, 3 | **TBD** |
| `sddt` | 16 | 0x0b | 1..6 | 1, 6, 2 | **TBD** |
| `dlrq` | 16 | 0x11 | 1..4 | 2, 4, 1 | **TBD** |
| `pwbt` | 16 | 0x03 | 1..1 | 1 | **TBD** |
| `fpyc` | 16 | 0x11 | 1..1 | 1 | **TBD** |
| `fprc` | 16 | 0x11 | 1..3 | 2, 3, 1 | **TBD** |
| `fppz` | 16 | 0x0b | 1..1 | 1 | **TBD** |
| `prcm` | 16 | 0x0a | 3..4 | 4, 3 | **TBD** |
| `acod` | 16 | 0x0a | 4..4 | 4 | **TBD** |
| `shrd` | 16 | 0x0a | 1..1 | 1 | **TBD** |
| `yafr` | 16 | 0x11 | 2..2 | 2 | **TBD** |
| `goid` | 16 | 0x11 | 0..1 | 0, 1 | **TBD** |
| `avpt` | 16 | 0x0a | 5..6 | 5, 6 | **TBD** |
| `sthl` | 16 | 0x0a | 2..2 | 2 | **TBD** |
| `nthl` | 16 | 0x0a | 2..2 | 2 | **TBD** |
| `lwpz` | 16 | 0x0a,0x01 | 2..100000 | 3, 100000, 2 | **TBD** |
| `cts3` | 16 | 0x11 | 2..7 | 2, 7 | **TBD** |
| `OPri` | 15 | 0x11 | 3..9 | 3, 5, 7, 6, 9 | **TBD** |
| `fifa` | 15 | 0x03 | 1..1 | 1 | **TBD** |
| `Uddr` | 15 | 0x03 | 1..1 | 1 | **TBD** |
| `lmhi` | 15 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `lmlo` | 15 | 0x03 | 0..1 | 0, 1 | **TBD** |
| `dpas` | 15 | 0x03 | 1..1 | 1 | **TBD** |
