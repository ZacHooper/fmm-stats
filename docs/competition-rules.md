# Competition rules: the tag register

What each tag of a competition rule file means. The rule files are tagged trees in the data
dictionary (`fmparser/tables/rule_files.py`, 667 files) and again, as a copy of the
dictionary file it names in `file`, in each loaded competition's archive member
(`comp_<uid>.dat`, `fmparser/tables/comp_rules.py`). The parser READS only the stage list's
structure (`comp_rules.FILE`/`STAGE`/`ROUND`); everything below is from this register's
decoding and is not yet in a schema or the store.

Case study: the English pyramid, Premier League to National League North/South, whose real
rules are public, checked against the store's fixtures and club league history.

## Tools

```bash
# every field of every rule file and archive member, one row each (path, tag, value, fourcc)
uv run python scripts/audit/rule_tags.py <save.fms> --out rule_tags.duckdb
```

`rule_tags.path` indexes list elements (`stgs[0].prmr.nrpl`), so one stage's rule is one
`LIKE` away. A u32 whose four bytes are printable is also given as `fourcc`: the `id` of a
rule container is its own tag stored as a number (`id = 1886547314` is `prmr`; `relr`'s is
`rlgr`; a stage's `id` is its code, `leag`, `poff`, `cup `).

## Confidence

- **VERIFIED**: the value matches an independent fact (real-world rule, the store's
  fixtures or club league history) across every case checked, and differs where the facts
  differ.
- **CONSISTENT**: fits every case looked at, but the cases do not discriminate it from
  another reading.
- **HYPOTHESIS**: one reading of too few cases.

## The archive copy

On frem-2030-09-14, 51 of the 73 configured archive members are field-for-field identical
to the dictionary file they name; the other 22 differ only in runtime values the game fills
(`itvm[k].chmy`, inflated money; `SpDs[k].sudt`; one `itvm.type`). Several members can name
one file: National League North (5123054) and South (5123055) both carry
`eng_national_north_south_region_2020`. A nation's dictionary holds variants of a file
(`_2019`, `_21_teams`, `_compatible`); the archive member names the live one.

## How a pyramid is linked

A rule names the competition it sends clubs to by **uid**, and the target can be a
**parent** competition that groups parallel leagues:

```
National League (109201, level 4)      relr: 4 -> 150990
National League North/South (150990, cid 167, level 5)   chdc: [5123054, 5123055]
    North / South (one rule file)      prmr: 1 auto + play-off -> 109201
                                       relr: 4 -> 158186
English Regional Premier Divisions (158186, cid 173, level 6)
```

Neither child names the other, and no rule above or below names a child. The store's club
league history (`stg.club_league_history`, seasons 2022-2028) shows what the parent does
with them: the National League's four relegated clubs split between North and South
differently every season (2/2, 3/1, 4/0, 1/3), and clubs move SIDEWAYS between North and
South with no promotion or relegation (South's 5th and 19th, North's 6th and 11th). So the
parent reallocates its children's members each season; by what rule (location is the
likely one) is open.

Level 6 is not loaded in the Frem career, so the eight clubs `LtfP` brings up and the eight
the children relegate to 158186 have no history to check.

## Stage tags (a `stgs[k]` element)

| tag | read | meaning | evidence | confidence |
|---|---|---|---|---|
| `id` | yes | stage code (`leag`, `poff`, `cup `, `fnls`, `prom`, `rele`, `cham` ...) | | VERIFIED (comp_rules) |
| `indx` | yes | stage index = `fix_man` +76 | | VERIFIED (comp_rules) |
| `type` | yes | 0 knockout, 1 league, 2 groups, 6 play-off feeder | | VERIFIED (comp_rules) |
| `ntms` | yes | teams in the stage | | VERIFIED (comp_rules) |
| `nrds` | | times each pair meets in a league stage | 2 in the English leagues; 4 in the Scottish Championship/L1/L2 (36 games, 10 clubs); 3 in the Scottish Premiership (33 then the split) | VERIFIED |
| `pwin` / `pdrw` | | points for a win / a draw | 3 / 1 on every league stage looked at | CONSISTENT |
| `pdad` | | points deducted for entering administration | Premier League 9, EFL 12, National League and N/S 10: the real deductions | VERIFIED |
| `prmr` | | promotion rule: container `{nrpl, mnpl, mxpl, comp, mnpc}` | see below | VERIFIED |
| `tppr` | | play-off places rule: `{nrpl, stag, nmsn}` | see below | VERIFIED |
| `relr` | | relegation rule: `{nrpl, mnpl, comp}`; its `id` reads `rlgr` | see below | VERIFIED |
| `sort` | | tie-breakers after points, in order: a list of codes | see below | VERIFIED for 0-3 |
| `tems` | | where the stage's clubs come from: list of `{id, comp, stag, indx, mxtm, nmsn, rvtm}` | see below | VERIFIED for the play-off order |
| `ptsd` | | points deductions: list of `{team, year, pots, reas}` | `eng_national` stage 0: team 647, 2021, 12 points, reason 8 | CONSISTENT |
| `ftac` | | per-round outcome of a play-off: list of `{type, stnm, team, comp, lfte, srcc, stag}` | see below | HYPOTHESIS |
| `strq` | | stage requirement: `[{stag, pref}]`, the stage this one waits for | the play-off stage carries `stag` = the league stage | CONSISTENT |
| `srnd` | | `{id 'srnd', subr, prio}` | N/S play-off `subr` 11 `prio` 5; Championship play-off `subr` 44 | open |
| `fxor` `ttac` `edtv` `hspp` `prio` `subr` `mtrl` `acod` `sche` | | | Premier League / Championship / EFL / non-league differ: `fxor` 6/8/8/9, `edtv` 0/0/1/1, `hspp` 0/0/1/1 | open |

### `prmr`, `tppr`, `relr`: promotion, play-off places, relegation

| league | `prmr.nrpl` | `prmr.mnpl` | `prmr.mxpl` | `tppr.nrpl` | `relr.nrpl` | `relr.comp` | real rule |
|---|---|---|---|---|---|---|---|
| Premier League | | | | | 3 | 12 Championship | 3 down |
| Championship | 2 | 3 | | 4 | 3 | 13 | 2 up, play-off 3rd-6th, 3 down |
| League One | 2 | 3 | | 4 | 4 | 14 | 2 up, play-off 3rd-6th, 4 down |
| League Two | 3 | 4 | | 4 | 2 | 109201 | 3 up, play-off 4th-7th, 2 down |
| National League | 1 | 2 | 2 | 6 | 4 | 150990 (parent) | 1 up, play-off 2nd-7th, 4 down |
| N/S (each) | 1 | 1 | 2 | 6 | 4 | 158186 (parent) | 1 up, play-off 2nd-7th |

- `prmr.nrpl` = automatic promotion places (from the top); `prmr.comp` = the competition
  promoted into; `prmr.mnpl` = clubs promoted in all, play-off winners included (VERIFIED:
  League Two 3 + 1 = 4); `prmr.mxpl` = the most promoted. `prmr.mnpc` (4, N/S only) is
  probably a total across the parent's children (2 x 2); HYPOTHESIS.
- `tppr.nrpl` = the places after the automatic ones that go into the play-off; `tppr.stag` =
  the stage they go to (1, the `poff`/`cup `/`fnls` stage); `tppr.nmsn.stgn` = its name
  (21 Playoff, 238 Playoffs).
- `relr.nrpl` = relegation places (from the bottom); `relr.comp` = where they go;
  `relr.mnpl`, when present, equals `nrpl`.
- Club league history, 2022-2028 (VERIFIED every season): National League 21st-24th down to
  North/South; 1st and the play-off winner up from each of North and South and from the
  National League; League Two 23rd-24th down.

### `sort`: tie-breakers

Codes, applied after points in list order:

| code | meaning | evidence |
|---|---|---|
| 0 | goal difference | first after points in England, Germany, Denmark |
| 1 | goals scored | follows 0 in England |
| 2 | wins | FIRST in Belgium (`2,0,1,13,5`), which ranks on wins before goal difference |
| 3 | head to head | FIRST in Spain (`3,0,1`): the store's rebuilt Spanish tables disagree with the game only on clubs level on points, and head to head separates all 41 such pairs (TODO #13); Italy `3,18,0,1` |
| 5, 6, 13, 14, 18, 22, 29 ... | open | Denmark `0,1,5`; EFL `0,1,3,2,5,22`; Germany `0,14,1,3,5`; France `0,3,18,29,14,1`; Belgium's championship play-off opens with 6 (its halved-points rounding?) |

England: Premier League `0,1,3` (goal difference, goals scored, head to head); EFL
`0,1,3,2,5,22`; National League and N/S `0,1,2,3`.

### `tems` and the play-off bracket

A play-off stage's `tems` gives its clubs in pairing order, as indexes into the feeding
stage's play-off places (`tppr`), and a two-legged tie's first-listed club hosts the first
leg. The EFL play-offs carry `indx` 3,0,2,1: with places 3rd-6th indexed 0-3 that is 6th,
3rd, 5th, 4th, and the Championship's first legs in the store are 6th v 3rd and 5th v 4th
every season 2022-2030 (VERIFIED).

A single-legged bracket instead pairs per round in `rnds[k].ctmp`: one `{ctin, hcti, atin,
alct, alti}` entry per tie. The National League play-off (places 2nd-7th, indexed 0-5):

- Quarter-final: `{ctin 0, hcti 2, atin 1}`, `{ctin 1, hcti 3, atin 0}`. Fixtures, nine
  seasons: always 4th v 7th and 5th v 6th, the higher place at home. So `hcti` = the home
  club's index (2 = 4th, 3 = 5th); `atin` picks the away club from those left (1 = 7th,
  0 = 6th) -- the mechanism is HYPOTHESIS, the outcome VERIFIED.
- Semi-final: `{ctin 0, alct 0, alti 0, hcti 5}`, `{ctin 1, alct 1, alti 0, hcti 4}`.
  Fixtures: 3rd always hosts the winner of 4th v 7th, 2nd the winner of 5th v 6th -- a
  fixed bracket, no reseeding (7th beat 4th on penalties in 2021/22 and played 3rd).
  `alct` reads as the earlier tie whose winner is the away club; `hcti` 5/4 is not the
  index of 3rd/2nd, so its meaning here is open.
- Final: no `ctmp`; the side listed at home varies, so it is drawn (`drdt`).

Round tags: `nmmt` = matches in the round (2/2/1), `nmxt` = clubs going into the next round
(4 = two winners and two byes, 2, 0), `nmlg` = legs (1; the EFL semi-finals 2), `nmrp` =
replays (0), `ntms` = clubs in the round, `stnm` = round name (6 First Round, 18 Semi Final,
20 Final). All VERIFIED against the fixtures.

### `ftac`

The play-offs carry one entry per round: `{type 52, stnm <round>, team 0|1, comp, lfte,
srcc 0, stag}`. `team` 0 is the round's winner, 1 its loser; the final's winner has `lfte`
1, every loser `lfte` 6, in every English play-off whatever its size (4 or 6 clubs).
HYPOTHESIS: the outcome each club is recorded with (1 = promoted, 6 = play-off defeat).

## File tags (top level)

| tag | meaning | evidence | confidence |
|---|---|---|---|
| `comp` | the competition's uid (absent on a child file shared by several members) | | VERIFIED |
| `type` | 1 = league | | CONSISTENT |
| `levl` | division level, 0 = top | Premier 0 ... N/S 5; Denmark 0-4; = `raw.competitions.level` | VERIFIED |
| `year` / `bsyr` | base year, 2000 | | CONSISTENT |
| `ygap` | years between editions | 376 files 1; 14 two-yearly (Nations League, Gold Cup); 32 four-yearly (World Cup qualifying, Club World Cup) | VERIFIED |
| `dtrn` | season span: `{stmn, styo, enmn, enyo}` = start month and year offset, end month and year offset | Denmark/Spain 7/0 - 6/+1; England 7/0 - 5/+1; Germany/Turkey 8/0 - 6/+1; Sweden 3-11, Norway 3-12, MLS 2-12 same year; the Euros 6-7 | VERIFIED |
| `fxds` | key dates: `{strl, id_1, id_2, dyow, dyom, mont, year, time, mnsn}`; `id_1`/`id_2` are FourCCs (`leag`+`star`, `leag`+`end `, `Win1`+`star`: the winter break) | National League: league starts Sat 5 Aug, ends 29 Apr; play-off rounds dated after | CONSISTENT |
| `mnsc` / `mstc` | minimum stadium capacity / minimum seats | National League 4000/500, N/S 3000/250 (the FA's grading for steps 1 and 2); EFL 5000/2000; Premier League 12500/12500 | CONSISTENT |
| `chdc` | a parent's child competitions (uids) | N/S parent: [5123054, 5123055] | VERIFIED |
| `LtfP` | clubs promoted INTO this (parent) competition: list of `{ntms, comp}` | N/S parent: four level-6 leagues, 2 each = 8, balancing the 2 x 4 the children relegate | CONSISTENT |
| `vlys` | `[{comp, mntm, mxtm}]` | N/S parent: 109201 24/24, then 5123055 | open |
| `NoMd` | | 20 on the National League and N/S files | open |
| `ptsd` | points deductions (as on a stage) | `eng_national`: 2011, 10 points | CONSISTENT |
| `itvm`, `MtTv`, `fnrg`, `prcm`, `typz` | money: TV, prize (`przm`), `cash` | `itvm[k].chmy` is filled at runtime | open |
| `ycfm` / `yctf` | | 1 / 6 on every English league | open |
| `desc` | free-text description (`Default`, `24 teams`) | | VERIFIED |
| `file`, `SubF`, `Bran`, `XSvC`, `EdBr`, `EdDt`, `vers`, `ftye` | source name/folder and editor trailer | | VERIFIED (rule_files) |

## Open, in the order they matter for moving clubs between leagues

1. How a parent splits its incoming clubs between its children (location?), and whether
   `vlys` or `rgman.dat` is the rule. Check the clubs' cities/coordinates against the
   North/South split.
2. `sort` codes 5, 13, 14, 18, 22, 29: rebuild Germany's and Belgium's tables with each
   reading (`mart.standings` vs `raw.club_league_history`).
3. `ftac.lfte` and `srcc`; `prmr.mnpc`; `hcti` in a later round.
4. The scheduling block (`sche`, `fxor`, `mtrl`, `drrl`, `drdt`, `date`) and money.
