# rule_files  ([`fmparser/tables/rule_files.py`](../../fmparser/tables/rule_files.py))

The game's library of competition rules: 667 rule files, one per competition plus each
nation's competition list, reserve list and rules. They make up the **data dictionary**, a
3.3 MB region at ~16.7–20.0 MB in the reference half ([savefile map](savefile-map.md)), in the
same tagged format as the archive's [comp_rules](comp_rules.md) members but without their
54-byte header. Each file is a count-framed block, `[u32 n][n tagged fields]`. The files are
byte-identical in every save of a career (27 of 667 differ between the Frem and Bucaspor
careers); the bytes between them change.

## Layout

```
region    the densest cluster of the `comp` tag, padded 60 KB before and 300 KB after (find_region)
file      [u32 n][n tagged fields]      a rule file: its top level has `ftye` and `file`
per nation, in order:
          [dated record][u32 n][n fields]                    the nation's merged <nat>_rules (bare)
          [separator][u32 k] k × ([01 0a][u32 n][n fields])  a group of k containers:
                     <nat>_comps, <nat>_reserve_comps, <nat>_rules, then its competitions
```

A file names its source in `file` (`dan_prem_3_6_euro_teams`) and its folder in `SubF`
(`.\europe\dan\leagues\`), and closes with the trailer `XSvC EdBr EdDt SubF` the archive
members also end with. The tagged format is specified in `fmparser/core/types.py`
(`read_tree`).

Five schemas, chosen per file by `schema_for`:

| schema | files | carries |
|---|---|---|
| `comp_rules.FILE` | 453 | a competition's stage list (`stgs`): the same declaration the archive members read with |
| `NATION_COMPS` | 53 | `<nat>_comps`: division levels (`dvlv`), competitions (`cmps`), team-count rules (`retm`) |
| `NATION_RESERVE_COMPS` | 53 | `<nat>_reserve_comps`: reserve and youth competitions |
| `NATION_RULES` | 106 | `<nat>_rules`, twice per nation: in its group, and the merged bare copy that also carries its `_comps` and `_reserve_comps` tags |
| `STAGELESS_COMP` | 2 | `wal_cymru`, `wal_cymru_main`: a competition configured without a stage list |

| tag | field | meaning |
|---|---|---|
| `file` | `file` | the file's name |
| `SubF` | `source_path` | its folder |
| `ftye` | `file_type` | |
| `retm` | `team_rules` | a nation's team-count rules: `{comp, ntms, nxss}` |
| `retm[].comp` | `comp_uid` | the competition's **uid**, as a u32 or a `{id 'comp', comp <uid>}` container; absent on a rule about a team or a nation |
| `retm[].ntms` | `teams` | teams in the competition (on 18% of rules, every save) |
| `retm[].nxss` | `nxss` | 0 or 1, unnamed: 1 on 51 rules, the same 51 on all seven saves of both careers (Chile's 5250792 carries a 17-team rule at 0 and a 16-team rule at 1) |

`team_counts()` reads every `_comps` rule that names a competition and carries `ntms` with
`nxss` 0: **190 competitions**, written to `competition_team_counts.json`.

**How it is checked.** `tiling()` accounts for the span from the first file to the last: on
frem-2030-06-22 it is 3,269,072 bytes, 3,242,194 of them (99.18%) in the 667 files, no other
count-framed block (a file that failed to read would show up as fragments here; the test
requires zero), and 26,878 bytes unread. `framing_problems()` checks that each group's `k`
equals the containers that follow and that every bare file is a `_rules`: none on any save.

> **Quirk:** the unread 0.8% is the part that is state. Between frem-2026-03-28 and
> frem-2030-06-22 all 667 files are byte-identical while 227 of the 666 gaps between them
> differ (87 between frem-2026-03-28 and frem-2026-06-11). Neither the separator (`ffffffff`-led
> u16 entries ending `01`) nor the dated record before each merged `_rules` (u16 day-of-year,
> u16 year pairs) is decoded. TODO, "The data dictionary's state between the rule files".

> **Decision:** the region is found by the `comp` tag's densest cluster, padded, and bounded
> by the files themselves (count-framed blocks that read to their declared count), not by a
> fixed window. The pad is slack: the first file opens ~66 bytes before the cluster's first
> `comp`, the last closes ~170 bytes after its last.

## Layout: FMM27

782 rule files on both Truro saves, read with FMM27 variants of the same schemas
(`RULE_FILES_TABLE_FMM27`, `schema_for_fmm27`). Kept to what `team_counts()` needs; the rest
is carried unread, as on FMM22.

- **No `SubF` anywhere.** A nation's three files carry `PLgn` in its place: an unnamed int,
  0 on 246 files and 1 on 57, absent on one `_reserve_comps`.
- **Continents' rule files, men's and women's**: `afr`, `wmn_afr`, `asi`, `wmn_asi`,
  `wmn_eur`, `nam`, `wmn_nam`, `oce`, `wmn_oce`, `sam`, `wmn_sam`, stored bare like a merged
  `<nat>_rules` (`CONTINENT_RULES_FMM27`). A file with neither a nation suffix nor `PLgn`
  reads as a stageless competition (`STAGELESS_COMP_FMM27`).
- **New tags** on every schema (team rules: `FBkt`, `ReTT`, `DbSt`, `DbEd`, `ifmh`; the
  competition files' stage and round lists: `cdes`, `gtct`, `tmor`, …), listed unread.
- `team_counts()` gives 256 competitions. Like FMM22's 190 (70 resolve), most rules name a
  uid that is not in the competition table: 97 of the 256 resolve.

> **Lead:** two groups don't frame as FMM22's do: FMM27 puts small 2-field tagless containers
> (`ourc`, `inuc`) inside a group, ahead of its rule files, so `framing_problems` reads a
> wrong count (`declares 8,655,361 files`), and `tiling` counts their 587 bytes as unread
> blocks. The audit FAILs on both; not worth decoding while nothing uses the region.

## Evidence

`frem-2030-06-22`. Denmark's group is `dan_rules` (bare), then `dan_comps`, `dan_reserve_comps`,
`dan_rules`, `dan_prem`, `dan_prem_3_6_euro_teams`, `dan_first`, `dan_second`, `dan_cup`,
`dan_series`, `dan_third`. `dan_comps` runs from byte 16,971,525 to 16,972,641; its `retm`
(at 16,971,955) holds `{comp 6, ntms 12}`, `{comp 7, ntms 12}` and `{comp 8, ntms 12}`: the 3F
Superliga, NordicBet Liga and 2. Division, 12 clubs each, as their tables show.

The 3F Superliga's archive member `comp_6.dat` names `dan_prem_3_6_euro_teams`, and its stage
list is the file's ([comp_rules](comp_rules.md)); the same holds for all 73 configured members.

Pending: an in-game rules screen for the Superliga (teams, promotion and relegation places,
split rounds) to tie the unread tags to what the game shows.

## Output

`output/<label>/competition_team_counts.json`, `{uid: teams}` from `team_counts()`, loaded
into `raw.competition_team_counts`. The rule files' stage lists are not extracted: the
archive members carry the same for the loaded competitions ([comp_rules](comp_rules.md)).
