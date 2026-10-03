# Site marts (data-layers step 17)

The web app's JSON rebuilt on the model: a small set of views in the dbt schema `site`
(`transform/models/site/`), one per thing a page shows, and a thin exporter
(`scripts/export_site.py`) that reads only `site.*` and shapes rows into the same JSON
`scripts/export_data.py` writes from the old marts. Nothing reads them until the switch-over
(step 19); until then `scripts/diff_exports.py OLD NEW` compares the two exports file by file.

## Design

- **One mart per thing a page shows**, a thin select over `dim_*` / `fact_*`. A rule two
  consumers share lives in int or the mart tables.
- **No rules in the exporter.** Squad status, the B-list, origin, the loan ranks and the levels
  are SQL; the exporter only shapes rows (positional arrays, dicts keyed by tid) and rounds
  for display.
- **The JSON keeps its shape**, so the JS does not change and the export diff is the
  regression test. Trimming fields no page reads is a separate change.
- **The model's meanings, not the old quirks.** Seasons turn on the career's rollover day, a
  free agent is NULL, a loanee is at the team his record names, our squad is who the squad
  arrays list. Each difference this makes is listed below.

| Mart | Grain | Feeds |
|---|---|---|
| `site.snapshots` | snapshot | every file's snapshot fields |
| `site.config`, `site.role_weights`, `site.position_roles` | key; method × role × attribute; position | `core.json` tactics and familiarity |
| `site.our_teams` | team of the club we manage | career block |
| `site.clubs` | snapshot × team | `core.clubs`, `clubs.json` |
| `site.leagues` | snapshot × league, with skill_idx and the comparison ladder | `core.leagues`, ladders |
| `site.players` | snapshot × person, with positions and Level %iles | `core.players`, `all.json`, the profile |
| `site.squad` | snapshot × person in our squad | `ours.*` |
| `site.player_spells`, `site.player_moves`, `site.player_career` | spell; move; career line | `squad.json` |

## Intended differences

Measured on Frem store B (2023-06-29 / 2027-06-29 / 2027-08-09) against the old export.

**Players and clubs** (`core.json`, `all.json`, `clubs.json`)
- A loanee is at the team his record names, his parent's: Tochi Chukwuani (on loan from
  Nordsjælland) is no longer a Frem player row, and the squad counts, league pools, Level
  %iles and skill_idx move by one around him.
- Origin is the club, an academy counting for its club: `ours.origin` reads "Boldklubben
  Frem" where it read "#65189", and `all.json`'s `origin_club_tid` is the club's tid.
- A club on a career line the save has since reclaimed is still listed (148 empty clubs in
  `clubs.json`): the model keeps every line it has seen.
- `ours.status`: a player another club's squad lists on loan is 'Loan' on the day the save
  shows it. The old export read Player Progress, whose last week (2027-08-04) was before the
  save (2027-08-09), so nine loans that had started read 'First team'.

**Squad history** (`squad.json`)
- A spell at a club starts the day the player's record says he joined (where that lies
  between the spell's first snapshot and the one before) and ends on its last snapshot; the
  old spells guessed 1 July on both sides.
- Transfers name clubs, not their reserve sides (Brøndby, not Brøndby Reserves), and come
  from `fact_transfer`: a loan is not a transfer (Chukwuani's loan read as a free move to us).
- Career history: a youth line reads its club's name; a fee reads "£53,000", not the save's
  code; "contract ended" for a contract run out; NULL for a code not understood; lines the
  save has reclaimed are kept.

**Matches** (`matches.json`)
- The team stats and the managed side's formation are on `fact_team_match` now (our matches
  with detail; NULL elsewhere), so `site.matches` reads one table for the score and the
  stats.
- `extra_time` is the fixture list's `decided_by` (ET or pens): two cup ties that stayed
  goalless through extra time read false before, because the old test compared scores.
- A forward's position reads `ST`, the code the player rows use, not the match table's `FC`.
- Minutes in a match that went to extra time run to 120 (`fact_player_match`), not 90.
- Squad value: a player with no value of his own is valued by `int_player_value`, which reads
  a reserve side's league reputation off its first team (data-layers step 15).

**Registration** (`registration.json`; `int_squad_training`, `site.registration`)
- A season on an academy side counts as time at its club (Frem's youth side 65189 is Frem):
  the old view never mapped the youth tid, so every academy product read about 12 months
  short (Johan Maarup 17.3 -> 29.3, his home-grown date 2029-02 -> 2028-02).
- A career season runs from one rollover day to the next, so three seasons are 36.0 months.
  The old 364-day season left a gap each year that only the observed spells filled, and a
  player could miss club-trained status by a day: 10404 reads 36.0 (was 35.9, not home
  grown), 10527 keeps 36.0.
- The season in progress is credited from its start, or the day he joined, to the club whose
  squad lists him, a loan to the borrowing club. The old spells guessed a 1 July arrival
  (5562, signed 2027-06-25, read a year with us he never spent: 13.3 -> 1.3) and credited
  loans to us (Ruben Minerba's two loan seasons: 27.0 -> 21.0).
- The window, the seasons and the B-list date turn on the career's rollover day.

**World** (`world.json`)
- Clubs in the Danish Lower Division and B teams in the senior pyramid are on the home map:
  `dim_competition` gives that league its nation, which the old view lacked. Reserve sides
  are left off, as before, now by their team type.

**Loan outlook** (`loans.json`; `site.loan_outlook`)
- Computed in SQL, from the ability inside the view; only ranks, slot counts and percentiles
  leave it, and the exporter no longer reads a raw table. The formation slot table is
  `var('formation_slots')`.
- Who is at a club is who its squads list (`squad_membership`), not the dated spells: a player
  on loan counts at the club he is on loan to on the day the save shows it. Frederik
  Lindgaard, on loan from AB at 2413, is that club's natural left winger (its line reads 42,
  not "walks in"), and our nine loanees out count at their host clubs and carry `loaned_to`.

**Forecast** (`forecast.json`): identical.
