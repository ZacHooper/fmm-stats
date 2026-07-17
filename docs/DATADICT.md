# The tagged data dictionary (~17.0–20.8 MB)

A hierarchical, relational database of everything competition-related: competitions,
standings, fixtures, teams-in-comps, nations, prize money, dates. Self-describing —
every field is named. This is the **proper source for club→league membership and league
tables** (the light-results byte-guessing in BUGS #12c is the hard way; this is the spec).

Reader: `fmparser/tagged.py`.

## Wire format (fully decoded)
```
field  = [tag: 4 bytes, stored REVERSED]  [0x01 marker]  [type: 1 byte]  [value: size(type)]
record = an `id`(type 0x02) header naming the entity type, then its fields.
         RECORDS NEST — a standings table contains child rows, each with its own `id`.
records separated by `00 00` padding.
```
Tags are the field name reversed on disk: `pmoc`→`comp`, `smtn`→`ntms`, `  di`→`id`.

### type → value size
| type | size | meaning |
|------|------|---------|
| `0x01`,`0x0a`,`0x0b`,`0x13` | 4 | u32 |
| `0x02` | 4 | entity-type reference (value is itself a reversed 4-char tag, e.g. `comp`) |
| `0x03`,`0x11` | 1 | u8 |
| `0x12` | 2 | u16 |
| `0x14` | 8 | u64 |

Example (a comp record):
```
id  [01][02] comp        → this record is a `comp` entity
comp[01][01] 7d120700    → comp = 463485 (u32)
ntms[01][11] 12          → ntms = 18   (num teams)
```

## Section
~17.0–20.8 MB, ~340k fields, ~1171 distinct tags (some are misaligned artifacts).
Sparse tag hits at 9–14 MB are false positives; the real dense dict is 17–20.8 MB.

## Entity catalogue (id → X, by frequency)
| entity | count | key fields | likely meaning |
|--------|-------|-----------|----------------|
| `comp` | 7042 | comp, type, **levl**, **ntms**, year, dates | **competitions** (level/tier, num teams) |
| `stnm`/`stag`/`stgn` | 1373 | stgn, ntms, nmmt, strl, stag | competition **stages** |
| `Ttea`/`team` | 1236/492 | team, Ttea, comp, **levl**, przm | **teams entered in a comp** |
| `stdt`/`endt` | 1002/954 | dyom, mont, year, dyow | **start/end dates** |
| `fxds` | 996 | fxds, id_1, id_2, sbsn | **fixtures** |
| `sdfd` | 928 | comp, edfd, stdt/endt, rsvt | **competition season/stage records**: comp ref + stage date ranges (stdt→endt with full y/m/d) + stage number. NOT standings (that was a mis-read from flat enumeration). |
| `przm`/`wnpz` | — | posn, cash, curr | **prize money per finishing position** (posn=0→1st place cash, etc.) — NOT a team table |
| `nmsn`/`nssn`/`sbsn` | 823 | stgn, stag, team, comp, ntms | **season** records |
| `nati` | 442 | Nnat, comp, seed | **nations** |
| `przm`/`wnpz`/`lspz`/`cash` | — | cash, curr, levl | **prize money** (per level/position) |
| `rgdv`/`lsdv`/`lwdv`/`updv` | — | comp, mxtm, seed, nati | division setup / promotion-relegation |

Common field tags: `id`, `comp`, `type`, `levl`(level), `ntms`(num teams), `team`,
`posn`(position), `rank`, `year`/`mont`/`dyom`/`dyow`(date parts), `time`, `cash`,
`curr`, `przm`(prize), `nati`, `seed`, `strl`, `mnsn`, `nmmt`.

## Recursive parser (DONE — `fmparser/tagged.py`)
- `read_field(mm, p)` → one field `(tag, type, value, next)`.
- `parse_field(mm, p)` → one field, **recursively parsing containers**. A container is
  `<tag> t0a <n>` immediately followed by `id t02 <tag>`; `<n>` = child field count.
  Tagless positional fields `[01][type][value]` are parsed as name `'~'`.
- `iter_records(mm, entity)` → every top-level record of an entity type, fully parsed.

Example (`iter_records(mm, 'sdfd')`):
```
[('comp',[('comp',131234),('id_1',...)]), ('id_2',...),
 ('edfd',[('comp',[('comp',131234),('in_1',29)]), ('~',6),
          ('stdt',[('dyow',4),('dyom',30),('mont',8),('year',2000),
                   ('endt',[('dyow',4),('dyom',2),('mont',5),('year',2001),('hidl',1)])])]),
 ('lwdl',1)]
```
i.e. comp 131234's 2000-01 season stage, 30 Aug 2000 → 2 May 2001.

## Why this matters (the goal) + what's still open
- **`comp`** → league **level/tier** (`levl`) → cross-league comparison ("≈ England L2"). ✅ reachable.
- **club→league MEMBERSHIP is still NOT located here.** `sdfd`/`przm` don't carry club
  TIDs (the `team` fields here are nesting-count bytes, values 2/3 — not TIDs; checked
  677 `team` fields, 0 were real club TIDs). So the entity that lists *which clubs are in
  a comp* hasn't been found yet.
- **Next:** with the recursive parser in hand, walk the `comp` entities (get level/tier +
  name via the comp uid) and hunt the team↔comp link — candidate entities: `Ttea`/`team`
  (teams-in-comp), `nssn`/`nmsn` (season squads), `rgdv`/`lsdv` (division setup). Then
  build leagues (name+level) and, if membership is found, `club→league` per player.
