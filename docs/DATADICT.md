# The tagged data dictionary (~17.0–20.8 MB)

A hierarchical, self-describing database of everything competition-related: competitions,
stages, seasons, fixtures, dates, nations, prize money, division setup. Every field is
named on disk. This doc is the **curated** dictionary; the full auto-generated schema
(every entity + all ~990 tags with types/ranges/samples) is regenerated into
`output/<label>/datadict/_schema.md` on each dump.

Reader: `fmparser/datadict.py` (built on the wire-format primitives in `fmparser/tagged.py`).

## Materialize it locally

```bash
python3 dump_datadict.py 21-22-end.fms
```
writes `output/<label>/datadict/`:

| file | contents |
|------|----------|
| `<entity>.json` | one per entity type (159 of them): every id-headed record of that type at **any nesting depth**, fully nested & lossless |
| `_stream.json` | the complete ordered item stream (records inline + raw blobs) — the lossless master; reconstructs the region's data without re-reading the save |
| `_schema.json` / `_schema.md` | auto data dictionary: per-tag stats + per-entity field schemas + nesting graph |
| `_crossref.json` | automated decode hints: reverse index (known ID → tags) + per-tag candidates |
| `_coverage.json` | byte-accounting proof (see below) |
| `_index.json` | entity → file + record count |

**Losslessness (21-22-end):** every byte in [17.0M, 20.8M) is accounted for —
**83.65% tagged fields, 9.81% raw blobs, 6.54% zero padding, 0 unaccounted.** 25,818
id-headed records across 159 entity types. Round-trip verified: every dumped record
re-reads identically from its offset (`tests/test_datadict.py`).

## Wire format (fully decoded)

```
field  = [tag: 4 bytes, stored REVERSED][0x01 marker][type: 1 byte][value]
       | tagless positional: [0x01][type][value]                 (tag rendered "~")
record = an id-headed container; its tag names the entity. Records NEST.
```
Tags are the field name reversed on disk: `pmoc`→`comp`, `smtn`→`ntms`, `  di`→`id`.

### type → value
| type | value | meaning |
|------|-------|---------|
| `0x01` `0x13` | u32 (4) | unsigned int |
| `0x0b` | u32 (4) | unsigned int, **semantics unconfirmed** → dump keeps raw hex as a 3rd pair element |
| `0x02` | entity-ref (4) | value is a reversed 4-char tag (e.g. `comp`) |
| `0x03` `0x11` | u8 (1) | small int |
| `0x12` | u16 (2) | int |
| `0x14` | u64 (8) | long |
| `0x0a` | **container** | value = child count; the children follow. **Never a scalar.** |
| `0x1a` | **string** | value = u32 byte length, then that many bytes |

### Container forms (all three occur; the parser handles each)
1. **id-headed record** — `<tag> 01 0a <n>` then `id 01 02 <tag>` then `n` children.
   The `id` field (type 0x02, value == the opener tag) names the entity. This is a
   "record"; its tag is the entity type.
2. **headerless container** — `<tag> 01 0a <n>` then `n` children (no `id`).
3. **anonymous container** — tagless `01 0a <n>` then `n` children (rendered tag `~`).

Example (`stdt` record): `[["dyom",30],["mont",8],["year",2000],["endt",[["dyom",2],
["mont",5],["year",2001],["hidl",0]]]]` — a start date with a nested end date.

## Non-tagged regions (captured as raw blobs)
- **~17.0–17.5 MB preamble:** a fixed-width binary block (types `0x04`/`0x1d`, big
  `0xffff` arrays incl. one 5497-byte run at 17,473,391). Not the tagged format; stored
  verbatim in `_stream.json` for losslessness. Decoding it is a future task.
- Small `(u16, 2022)`-pair fragments after `ff ff ff ff 00 00` separators — also raw.

## Entity catalogue (by record count; * = decoded)

| entity | count | meaning |
|--------|-------|---------|
| `comp`* | 7042 | a competition reference/record. Almost always `comp`=competition **uid** (+ optional `type`, `ntms`, `levl`, `mnsn` in sub-containers). |
| `stnm`* | 1373 | competition **stage** (`stgn` stage-number, `ntms`, dates, `team`). |
| `Ttea` | 1158 | team-entry record (see IDs below — `Ttea` is an internal id-space, NOT a club TID). |
| `stdt`*/`endt`*/`nwdt`*/`drdt`*/`date`* | 1002/954/840/341/401 | **dates** (`dyow` day-of-week 0–6, `dyom` 1–31, `mont` 1–12, `year`, `hidl`, `time`). `endt` nests inside `stdt`; `nwdt` inside `fxds`. |
| `fxds`* | 996 | **fixture** (`id_1`/`id_2` = packed string tokens, `nwdt` date, `mnsn`/`sbsn` season). |
| `sdfd`*/`edfd`* | 928/782 | competition **season/stage records**: `comp` ref + date ranges + `id_1`/`id_2` tokens. |
| `nmsn`/`nssn`/`sbsn`/`mnsn` | 823/…/345/466 | **season** records (`stgn`, `stag`, `comp`, `ntms`, `levl`). |
| `nati`* | 442 | **nation** competition record (`Nnat` = nation id in this region's own space; `dvlv`, `mntm`/`mxtm`). |
| `team` | 492 | team record (`Ttea` id, `year`, `comp`). |
| `rgdv`/`lsdv`/`lwdv`/`updv` | 263/… | division setup / promotion-relegation (`comp`, `mxtm`, `nati`). |
| `przm`/`cash`/`wnpz` | — | **prize money** (`posn` finishing position, `cash`, `curr`). |

## Field dictionary (confirmed)
`comp`=competition uid · `levl`=tier/level (0–27) · `ntms`=number of teams (league sizes
+ power-of-2 cup rounds) · `mntm`/`mxtm`=min/max teams · `posn`=finishing position ·
`cash`/`curr`=prize money + currency · `dyow`/`dyom`/`mont`/`year`/`time`=date parts ·
`stgn`=stage number · `seed`=seeding. Full auto list: `_schema.md`.

## Key ID findings (important)
This region uses its **own id-spaces**, largely disjoint from the club-TID / nation-id
spaces used in player & match records:
- **`comp` = competition uid** (u32). Confirmed: uid **463485** ↔ our cid **228** (Turkish
  2. League White Group). Join to cid via `reference.comp_detail`.
- **No club TIDs anywhere.** A full scan for known clubs (Galatasaray 955, Bucaspor 6567,
  Liverpool 356, …) found **zero** hits. Clubs are not referenced by TID here.
- **`id_1`/`id_2` are packed 4-char string tokens**, not team ids. Read big-endian they
  spell descriptors: `wint`, `end `, `star`, `leag`, and pairs like `Grou`+`Draw` =
  "Group Draw". These label fixture/stage kinds, not clubs.
- **`Ttea` is an internal team-entry id-space** (values 1904, 1909, 72000160, 2000032491…)
  — neither club TID nor a packed code. Mapping it to real clubs is unsolved.
- **`Nnat` uses a region-local nation numbering** (e.g. 110), not the 173=Turkey id used
  elsewhere. No 173 hits in the region.

Consequence: **club→league membership can't be bridged from this region alone** — it has
no club TIDs. It would need a `Ttea`-id → club and/or comp-uid → club map found elsewhere.
This is why the earlier TID-based hunt failed; it's a genuine structural fact, not a bug.

## Open decode targets
- Map `Ttea` id-space → real clubs (needs an external anchor; ask for in-game squad/table
  screenshots).
- Decode the `id_1`/`id_2` token vocabulary fully (what each 4-char code means).
- `0x0b` type semantics (24,758 fields; raw hex preserved so it's reinterpretable).
- The 17.0–17.5 MB fixed-format preamble (raw-captured today).
- Season-graph entities (`nmsn`/`nssn`/`sbsn`/`mnsn`, `stnm`/`stag`) — how stages chain.
