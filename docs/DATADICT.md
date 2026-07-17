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
| `sdfd` | 928 | **comp, team, posn, rank**, cash, stag | **STANDINGS (league table): comp + team + position** |
| `nmsn`/`nssn`/`sbsn` | 823 | stgn, stag, team, comp, ntms | **season** records |
| `nati` | 442 | Nnat, comp, seed | **nations** |
| `przm`/`wnpz`/`lspz`/`cash` | — | cash, curr, levl | **prize money** (per level/position) |
| `rgdv`/`lsdv`/`lwdv`/`updv` | — | comp, mxtm, seed, nati | division setup / promotion-relegation |

Common field tags: `id`, `comp`, `type`, `levl`(level), `ntms`(num teams), `team`,
`posn`(position), `rank`, `year`/`mont`/`dyom`/`dyow`(date parts), `time`, `cash`,
`curr`, `przm`(prize), `nati`, `seed`, `strl`, `mnsn`, `nmmt`.

## Why this matters (the goal)
- **`comp`** → league **level/tier** (`levl`) → cross-league comparison ("≈ England L2").
- **`sdfd`** → **standings**: `comp` + `team` + `posn` → club→league membership AND final
  table positions, for ALL loaded leagues (Super League included). This is the clean
  answer to the club→league problem that byte-level fixture parsing couldn't crack.

## Open / next steps
1. **Recursive record parser** — the format nests (`sdfd` holds child rows headed by
   their own `id`). `tagged.walk_fields()` currently yields the flat field stream;
   needs record-tree segmentation on `id`(0x02) headers.
2. **ID mapping** — `comp` and `team` values here are internal ids (e.g. `comp=2`,
   `comp=463485`=uid). Map: comp value ↔ our `cid`/`uid` (reference.comp_detail),
   `team` value ↔ club `TID`. Then `sdfd` → real league tables + membership.
3. Join into `extract.py`: leagues table (name + level + members from comp+sdfd) and
   `club→league` on every player — completing the cross-league baselines goal.
