# matches  ([`fmparser/tables/matches.py`](../../fmparser/tables/matches.py))

Our clubs' matches this season, each one in full: the match report, the stats, every
player's line and our tactic. A table of variable-length rows framed by a bare `[count u8]`,
at ~55.7 MB, holding the managed club's and its reserve side's matches in the order they were
played. 70 rows on `frem-2030-06-22` (50 Frem, 20 reserves). The game empties it on the
career's rollover day. Every other club's results are in [fixtures](fixtures.md).

## Layout

```
header  [count u8]                      matches in the table
row     [head, 8 B]                     home, away, competition, day
        [n u8][n × event, 17 B]         the match's events
        [body, 5,093 B]                 everything else, fixed width
```

A row is `5,102 + 17 n` bytes, and the next row starts where it ends. The body:

| body offset | span | block |
|---|---|---|
| +0 | 78 | body head: our side, the match header again, attendance, Player of the Match |
| +78 | 50 × 17 | the event list again, in 50 preallocated slots; the first `n` equal the counted list |
| +928 | 2 × 1,363 | the team blocks, home then away: `[77 B team head][20 × 62 B player slot][46 B team tail]` |
| +3,654 | 1,439 | the tail: our side's kick-off formation and tactic |

**Head, 8 bytes**

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `home_tid` | u16 | |
| +2 | `away_tid` | u16 | |
| +4 | `comp_id` | u16 | the competition's cid |
| +6 | `day` | u16 | day of the year, 0-based; the year is in the body head |

**Event, 17 bytes**

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `b0` | u8 | unnamed, 1–17; carried into `raw.match_events` |
| +1 | `type_byte` | u8 | `01` goal, `02` own goal, `03` penalty, `04` missed penalty, `05` red card, `06` injury, `07`/`08` shoot-out kick scored/missed, `29` disallowed goal; `0e` unnamed (one, in a reserve fixture, on `frem-2030-06-22`) |
| +2 | `minute` | u8 | 0-based: the game shows `minute + 1` |
| +3 | `added` | u8 | added time: `89, 3` shows as 90+3 |
| +4 | `side` | u8 | 0 home, 1 away: the team of the event's player, own goals included |
| +5 | `tid` | u32 | the event's player, always one of the match's players |
| +9 | | 8 | two u32, `ffffffff` on most events; never a tid of the match |

**Body head, 78 bytes**

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `club_tid` | u16 | our side: the managed club or its reserves |
| +2 | `opponent_tid` | u16 | |
| +4 | `club_comp_id` | u16 | = head `comp_id` |
| +6 | `home_flag` | u8 | 1 when `club_tid` is at home |
| +7 | `header_home_tid`, `header_away_tid`, `header_day` | 3 × u16 | = the head |
| +13 | `year` | u16 | the match date is `day` in `year` |
| +15 | `attendance` | u32 | 0 on friendlies |
| +63 | `player_of_match` | u32 | the game's Player of the Match (Quirks) |

**Team head, 77 bytes**

| offset | field | type | meaning |
|---|---|---|---|
| +3 | `goals_against` | u8 | = the other block's `goals` |
| +6 | | 22 | a copy of `positions`, or `ff` throughout on friendlies and reserve fixtures |
| +30 | `positions` | 11 × 2 | the side's eleven positions at full time, in `posOrder` order (below) |
| +52 | `goals` | u8 | the side's score, own goals for it included |

**Player slot, 62 bytes.** Twenty per side, preallocated. An unused slot keeps its
`posOrder` and has `tid` `ffffffff`. Every byte is a u8 unless marked.

| offset | field | | offset | field |
|---|---|---|---|---|
| +0 | `assists` | | +26 | `passC`, passes completed |
| +3 | `condition` (Quirks) | | +27 | `keyPass` |
| +4 | `crossA` | | +28 | `sid`, 2 bytes (the person's sid is 4) |
| +5 | `crossC` | | +32 | `rating`, a whole number |
| +8 | `dribbles` | | +35 | `shotA`, shots |
| +10 | `goals` | | +36 | `shotO`, shots on target |
| +11 | `headA` | | +41 | `posOrder`: 1–11 the starters, 12+ the bench |
| +12 | `headW` | | +42 | `tid`, u32 |
| +16 | `intercept` | | +48 | `tackA` |
| +19 | `subOn`, the minute; `ff` = not | | +49 | `tackW` |
| +21 | `subOff`, the minute; `ff` = not | | +53 | `yellow`, 1 = booked |
| +22 | `mistakes` | | | |
| +23 | `mistGoal`, mistakes leading to a goal | | | |
| +25 | `passA`, passes | | | |

**Tail, 1,439 bytes**

| offset | field | meaning |
|---|---|---|
| +33 | | the formation marker `76 b9 f4 07` |
| +37 | `formation` | ASCII, zero-padded to 32: `4-1-2-2-1` |
| +69 | `kickoff_positions` | 11 × 2: the formation's slots at kick-off, in the formation's own order |
| +102 | | `kickoff_positions` again, byte for byte |
| +220 | | 963 bytes: the formation's template from the formation catalog (Quirks) |
| +1196 | | eleven 8-byte rows, one per kick-off slot: five bytes, then `00 00 00` (Quirks) |

**A position is a `(band, column)` byte pair** (`core.primitives.pitch_position`). Band
`& 0x7f`: `01` GK, `04` D, `08` DM, `10` M, `20` AM, `40` ST; bit `0x80` marks the wide-left
player of the band. Column `08` is the wide-right player, so `(04, 08)` is DR, `(84, 00)` DL,
and any other column is the centre letter: DC, DMC, MC, AMC. GK and ST are always GK and FC.

Every byte of the row is declared, named or `UNKNOWN`: `scripts/audit/audit_records.py --map`
prints them.

**How it is found.** The formation marker sits at a fixed offset in every body. A marker
hit is a row when the bytes before it frame a row whose body repeats its head (clubs,
competition, home flag, day). From that row the walk steps back row by row to row 0, and the
byte in front of row 0 is the count. `scrape_matches` then requires the walk to read exactly
the declared count, no row before row 0 and none after the last.

## Evidence

Screenshots pending.

## Quirks

> **Quirk:** the table is emptied on the career's rollover day (late June), so a save made
> after it holds no matches: `frem-2023-07-02` has 0. The season's matches survive only in a
> save taken before the rollover. The loader places each snapshot by the career's rollover
> day (`careers.py`).

> **Decision:** an empty table has no row to seed from, so it is not located, and
> `scrape_matches` returns `[]`. The loader then requires the table to hold exactly our
> clubs' matches in the [fixtures](fixtures.md) list since the last rollover
> (`check_against_fixtures`). The two agree match for match, friendlies included, on every
> save measured, so "no matches" while the fixture list shows games played is a locator
> failure, not an empty season.

> **Decision:** no year window and no delimiter scan. A row is recognised by its own
> head/body repeat and walked by the length it declares, so a match cannot be found twice
> or skipped. The season's first match has no row before it and is found like any other.

> **Quirk:** `player_of_match` is the game's own pick, not the top rating. It is a player of
> the match on every row and the highest-rated player on 68 of 70 on `frem-2030-06-22`. The
> loader's `star_home` / `star_away` are each side's top rating, a different thing.

> **Quirk:** a plain yellow card is not an event. It is the player slot's `yellow` byte. A
> red card is an event (`05`).

> **Quirk:** the screen's team stats are sums of the player slots, not stored figures:
> shots `Σ shotA`, on target `Σ shotO`, passes `Σ passA`. The team rating is the mean
> `rating` of the players who took the field. The loader computes them (`team_stats`).

> **Dead end:** possession and clear-cut chances are not stored. Possession was searched as
> u8 and u16 and as sum-to-100 pairs, across the whole row and the file around it. It is
> not the pass share either: in the match checked, the side with more passes had less of the
> ball.

> **Quirk:** `positions` (team head +30) is the full-time team sheet, the order the stats
> screen shows. The tail's `kickoff_positions` is our kick-off formation in its own slot
> order, and does not say which player took which slot. After an in-match change the two
> differ (13 of our 46 competitive matches on `frem-2030-06-22`), and reading a player's
> position as `kickoff_positions[posOrder - 1]` puts him in the wrong place. A player's
> position is his side's `positions`. Nothing records when or how the shape changed:
> there is no substitution or tactic event, and team head +6 is a copy of +30.

> **Quirk:** the column byte is a rank across the band, and the decoder keeps only the two
> edges. Two central midfielders read `01` and `04` (left and right of centre) and both
> decode as MC, which is also what the screen says. A band of four or more loses which
> interior player is which.

> **Quirk:** reserve fixtures carry one default array, `GK DR DL DC DC MR ML MC MC FC FC`,
> on all 20 of them: the AI-run side never sets a tactic. Don't read reserve positions as a
> lineup.

> **Quirk:** only our side's formation string is stored. The opponent's shape is its
> `positions`.

> **Dead end:** the tail's 963 bytes at +220 are the formation's template from the
> formation catalog at ~20.6 MB, byte for byte on the 20 4-4-2 matches and within a few
> bytes on the rest. A shape not in the catalog (4-1-3-2) has no copy. It is geometry, not
> match data: no possession, no roles.

> **Quirk:** the eleven rows at tail +1196 follow the kick-off slots. Bytes 0–1 look like a
> role family (`24 48` keeper, `01 23` / `41 22` full-backs, `81 42` inside forward) and
> bytes 2–4 change between matches in the same role. Unverified: no screen with the roles
> has been matched to them.

> **Quirk:** `condition` is `ff` for an unused substitute only in friendlies and reserve
> fixtures. In a competitive match an unused substitute has a condition and a `rating` of 6.
> A player appeared when `posOrder <= 11` or `subOn != ff`; never infer it from `condition`
> or `rating`.

> **Quirk:** sixteen player slots are used in reserve fixtures, eighteen in competitive
> matches and twenty in friendlies, for both sides.

> **Quirk:** tids 32,967–33,066 are not people. The person table ends at 32,965, and no
> squad in any snapshot holds them. They are anonymous filler the game fields when a side has
> too few real players: 179 lines for our reserves on `frem-2030-06-22`, and opponents short
> of players in cup, European and league matches (Hedensted, 18 lines in one cup tie). One
> such tid turns out for up to seven clubs in a season. There is no name to find;
> `scripts/export_data.py` drops match rows it cannot name.

> **Quirk:** name a match row's player by `person_id` (`mart.fact_player_match`), never by
> tid alone. A tid is a recycled slot ([person_info](person_info.md)): grouping names by tid
> across snapshots picks between two people, differently on each run.

> **Quirk:** the shoot-out codes `07` / `08` are read from one shoot-out (Frem v
> Midtjylland, Sydbank Pokalen, 25 Oct 2022): all ten kicks at minute 120, and the score
> only closes if `07` is scored and `08` missed. One shoot-out can't tell a shoot-out kick
> from a goal at 90+30; recheck on the next one.

## Output

`output/<label>/matches.json`: one object per match, in the order played (`offset, date,
comp_id, home_tid, away_tid, club_tid, home_flag, attendance, score, player_of_match,
formation, kickoff_positions, home_positions, away_positions, events, home_xi, away_xi`;
`home_xi`/`away_xi` hold the used player slots). The loader writes `raw.matches` (with the
summed team stats and the competition label: a two-legged play-off tie gets First/Second
Leg by date), `raw.match_events` and `raw.match_player_stats` (each starter's position from
his side's `positions`).
