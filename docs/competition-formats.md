# Competition formats: how the save defines them, and the Champions Cup

How a competition's format (stages, rounds, groups, qualification, prize money) is stored, what
the parser reads of it today, the European Champions Cup's format decoded in full, and the
engine features that a modern "league phase" Champions Cup could be built from. Measured on
`frem-2028-09-20` and `frem-2029-04-25`. Print any competition's rules with
`scripts/audit/dump_comp_rules.py` (examples below).

## 1. What we pull about competitions today

| source in the save | parser | extract file → raw | what it gives |
|---|---|---|---|
| competition table (main save, after the clubs) | `tables/competitions.py` | `competitions.json` → `raw.competitions` | 1,372 slots: cid, uid, names, `type_id`, nation, reputation, level, parent; an entrant list (`refs`) on 24 competitions |
| round-name catalog (main save) | `tables/rounds.py` | `round_names.json` | 273 stage/round names: 17 Quarter Final, 21 Playoff, 73 Group Stage, 149–151 First–Third Qualifying Round, 164 First Knockout Round … |
| data dictionary: 667 rule files (main save, ~17–20 MB) | `tables/rule_files.py` | `competition_team_counts.json` only | every competition's and nation's rules. Only the team-count rules (`retm`) are extracted |
| archive `comp_<uid>.dat`, one per loaded competition (147) | `tables/comp_rules.py` | `competition_rounds.json` → `raw.competition_rounds` | the rules flattened to one row per (stage, round): code, type, teams, groups, round name, legs |
| archive `comp_man.dat` | `tables/comp_stages.py`, `comp_honours.py` | **not extracted** | the 78-byte stage grid (the `stage_key` fixtures point at) and the 55-byte roll of honour |
| archive `fix_man.dat` | `tables/fixtures.py` | `world_fixtures.json` | every fixture of the last two calendar years: clubs, score, date, `stage_key`, `stage_index`, `round_index` |
| our own matches | `tables/matches.py` | `matches.json` | `comp_id` per match, which is how a `stage_key` gets its competition |

dbt builds these into `mart.dim_competition`, `dim_stage`, `dim_round`, `fact_participation`,
`fact_competition_outcome`, `mart_standings` and `mart_tie_results`. Everything above `stgs` →
`rnds` (qualification routes, seeding, draw rules, prize money, dates) is read by the parser
only as far as `comp_rules.FILE` declares and is otherwise listed as `unread`.

## 2. Where a competition's format lives

A competition's format exists **twice**:

1. **The rule file in the data dictionary** (main save, uncompressed). The Champions Cup's is
   `eur_champions_cup_2021` in `.\continental\eur\`, 19,490 bytes.
2. **The archive member `comp_<uid>.dat`** (zstd-compressed, in the save's tail archive) for
   each loaded competition. The Champions Cup is cid 256, uid 1301394, so `comp_1301394.dat`:

       [54-byte header][the rule file's tagged block][runtime state]
        54 B             19,490 B                     72,524 B (Sep 2028) → 76,970 B (Apr 2029)

   The tagged block is **byte-identical** to the dictionary's rule file on both saves (all 56
   top-level tags). The runtime state after it is not decoded: it contains further tagged-looking
   items (`stnm`, `comp`, `team`, `fxds`, dates) and our club's tid once, and it grows during
   the season. It is likely the draw, group and fixture state.

A rule file can have **dated versions**. Top-level `styr`/`enyr` give the year window a version
is active for, and SI uses this for format changes: `inter_concacaf_nations_league_qual` carries
`styr 2018, enyr 2018`, `nam_champions_league_2023` `2023, 2023`, and `wwclub_world_champ_cup_2018`
and `_2021` hand over in 2021. FMM22 ships **one** Champions Cup file, `eur_champions_cup_2021`,
with no year window. So the old format never ends.

The rules carry `updy = {11 June}`, which looks like the competition's annual update day. That
is a hypothesis to test: it may be the day the loaded rules are refreshed for the next season.

## 3. The Champions Cup's current format, decoded

`stgs` holds four stages. `type`: 0 = knockout, 1 = league, 2 = groups.

| indx | stage | type | rounds (`ntms` teams, `nmlg` legs) |
|---|---|---|---|
| 0 | Champions Path (`stnm` 2000016478) | 0 | 1st Prelim (4, 1) → 2nd Prelim (2, 1) → 1st Qual (34, 2) → 2nd Qual (20, 2) → 3rd Qual (12, 2) → Playoff (8, 2) |
| 1 | League Path (2000016479) | 0 | 2nd Qual (6, 2) → 3rd Qual (8, 2) → Playoff (4, 2) |
| 2 | Group Stage (73) | 2 | 32 teams, `ngps 8`, `ngrt 4` per group, `nrds 2` (home and away) |
| 3 | knockout | 0 | First Knockout Round (16, 2) → Quarter Final (8, 2) → Semi Final (4, 2) → Final (2, 1) |

The tags that make it work:

- **Entrants: `tems` and `fsqt`.** Each stage's `tems` lists its sources, `{id 6, qtsd k}` =
  "clubs holding qualification seed k". The group stage takes seed 0 directly. `fsqt` maps seeds
  to entry points: seed 0 → stage 2, seeds 1–3 → League Path Playoff / 3rd Qual / 2nd Qual,
  seeds 4–7 → Champions Path Playoff / 3rd Qual / 2nd Qual / 1st Qual (seed 8 enters at the 1st
  Prelim, per `ByTm`). `ByTm` says which seeds skip which rounds. **Which nation's clubs get which seed is
  not in this file.** Denmark's and England's league files do not name uid 1301394 as a qualification target either
  (118 references to it in 52 rule files are not yet all read).
  Nation→seed allocation is probably by coefficient rank. `rule_group.dat` logs it ("Promoted
  seeding for Denmark (13th) … EURO Cup old_seed=2 new_seed=1"), so that member is the place to look.
- **Routing between stages and competitions: `ftac` and `qurl`.** `ftac` entries route a round's
  winners (`team 0`) or losers (`team 1`) somewhere. `type 51` = "advance to stage `stag`, round
  `nmsn`", `type 54`/`58` = "drop to competition `comp`, seed / stage". Qualifying losers drop to
  the EURO Cup (1301396) or EURO Cup II (31051584), and `comp 255` means eliminated. The group
  stage's `qurl` sends the top 2 (`nrpl 2`) to round 164, and its `ftac`
  `{type 8, topp 2, btpl 2, comp 1301396, seed 6}` sends 3rd place to the EURO Cup. The Final's
  `type 55` entries qualify the winner for the Super Cup (1301397) and Club World Championship
  (121092).
- **Draw constraints: `vlgr`.** Group stage: `type 1` (reads as: no two clubs of one nation),
  `type 1` with `Nnat 791 / 800` (a pair of nations kept apart), and `type 13/14` over seed
  ranges 0–3 and 4–7 (the two halves of the matchday split in `gpdt`). In the R16 round,
  `type 5 sed1 20 sed2 21` reads as winners vs runners-up, with `type 3` and `type 8` as more
  pairing rules. These meanings are inferred from the structure, not verified.
- **Scheduling: `fxds`** (48 dated slots at top level), `gpdt` (per half of the groups: the
  matchday → date-slot order and TV kick-offs), `date`/`dat2`/`ofsd` per round.
- **Money:** `apmn` (appearance), `wnpz`/`lspz` (winner/loser), group `lwpz` 2.8M per win and
  `drpz` 930K per draw, R16 9.6M, QF 10.6M, SF 12.5M, Final 20M / 15.5M, all in currency 7.
  `rkli` + `typz` are the 13 finishing tiers (winner … 1st Prelim) with a value per tier,
  probably the coefficient or reputation award.

## 4. Engine features a league phase can be built from

The modern format is one 36-team table where each club plays 8 different opponents (2 per pot,
4 home and 4 away). Places 1–8 go to the Round of 16, 9–24 to a two-legged knockout playoff, and
25–36 are out. FMM22's own rule files show the engine already has every piece of that:

1. **A league that is not a round robin: `nrds 0` + `exlg {stag, mnmt, mxmt}`.** `exlg` caps
   the matches each team plays in a league stage. Uses include `inter_concacaf_nations_league_qual`
   (34 teams, 4 games each), `arg_superleague_cup` (28 teams, 13 each),
   `arg_primera_nacional_35_teams` (35 teams, 32–34 each), `aus_nsl_12_teams` and MLS (two
   conferences topped up to 34 games each, `gnty 7`).
2. **A hand-written fixture grid: `cftp`.** `inter_concacaf_nations_league_qual` (2018 only)
   is *exactly* a Swiss league phase in miniature. It is one `type 1` stage, 34 teams, `nrds 0`,
   `exlg 4/4`, and a `cftp` list of 4 matchdays × 34 slots. In slot `tNNN`, a value v < 128
   means a home match against slot v and v ≥ 128 means away at slot 256 − v.
   `dump_comp_rules.py --grid` checks it: 0 unmirrored pairings, every slot exactly 2 home and
   2 away, 4 different opponents each. `cze_first` and `ser_super` use `cftp` too, for their
   split rounds. Whether slots are filled in seed order (which would let a grid encode "2
   opponents per pot") is **not yet known**.
3. **Routing by finishing place: `qurl` / `ftac` with `topp`/`btpl` ranges**, which already
   route group places to rounds and other competitions.
4. **Teams entering a knockout stage at a later round: `ByTm`**, which the qualifying stages
   already use.

So a modern-format `stgs` can be written in tags the engine already parses. In outline:

| indx | stage | content |
|---|---|---|
| 0, 1 | Champions / League Path | as now, with the playoff winners feeding stage 2 |
| 2 | League Phase | `type 1`, `ntms 36` (or 32, see below), `nrds 0`, `exlg {stag 2, mnmt 8, mxmt 8}`, optionally a `cftp` 8 × 36 grid; `qurl`: places 1–8 → stage 3 at R16, 9–24 → stage 3 knockout playoff, 25–36 → `comp 255` |
| 3 | knockout | Knockout Playoff (16, 2 legs) → R16 (16, with 1–8 entering via `ByTm`) → QF → SF → Final |

**36 teams needs 4 more entrants than today**, and that depends on the nation→seed allocation,
which this file does not hold (§3). **A 32-team league phase with 8 games each** keeps today's
entry exactly as it is and changes only stages 2 and 3, so it is the sensible first target.

## 5. What a save mod has to do, and what is unknown

1. **Write tagged trees.** The parser only reads them (`core/types.read_tree`). Build the encoder,
   and prove it by re-encoding the current `comp_1301394.dat` byte-identically.
2. **Repack the archive.** Recompress the member and rewrite the directory (`offset`, `stored`,
   `unpacked` for every later entry), plus the directory's own header and frame. Unknown: the u32
   in the 13-byte header that opens the archive (17 more than the members' total on Frem, 495
   less on Bucaspor; `docs/save-archive.md`). It may be a checksum or a size the game checks.
3. **Decide which copy the game reads.** The dictionary copy is uncompressed in the main save.
   Making it longer shifts every byte after ~19 MB, and whether the save holds absolute offsets
   past that point is unknown. If the game refreshes a loaded competition from the dictionary
   each `updy`, an archive-only edit would be undone on 11 June.
4. **The runtime state** (72–77 KB after the rules) is undecoded and indexes the current stages.
   Edit only when the competition is idle (after the Final, before next season's draw), and
   expect the game may reject state that no longer matches the stages.
5. **`comp_man.dat` stage keys.** Every fixture's `stage_key` is a row in `comp_man`'s stage
   grid. Whether the game allocates rows for new stages itself is unknown.
6. **Save integrity.** It is not known whether FMM22 checks a hash over the save.

A ladder of experiments, each needing only the one before it:

1. **No-op repack:** decompress and recompress `comp_1301394.dat` unchanged (different zstd
   level), rebuild the directory, then load the save in game. This tests (2) and (6).
2. **Visible scalar edit:** e.g. the Final's `wnpz` prize, made in the close season. This tests
   that the game reads the member, and, by simming past 11 June, whether the edit survives `updy`.
3. **32-team league phase:** replace stages 2–3 as in §4, keeping entry as is. Then check the
   generated fixtures in `fix_man.dat` (`world_fixtures.json`): 8 per club, a single table.
4. **36 teams:** after finding the nation→seed allocation.

## Commands

```bash
S=~/fm-saves/frem/frem-2029-04-25.fms
uv run python scripts/audit/dump_comp_rules.py $S --uid 1301394                  # CL member, whole
uv run python scripts/audit/dump_comp_rules.py $S --uid 1301394 --tags stgs      # just the stages
uv run python scripts/audit/dump_comp_rules.py $S --file inter_concacaf_nations_league_qual --grid
uv run python scripts/audit/dump_comp_rules.py $S --find exlg                    # who uses a tag
```
