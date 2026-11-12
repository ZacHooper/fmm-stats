# team_history  ([`fmparser/tables/team_history.py`](../../fmparser/tables/team_history.py))

**Every team-of-the-period the game has picked**: Team of the Week, Team of the Year, Squad
of the Season, Dream Team, Players' Select, Best XI, All-Star XI. Straight after the
[award history](award_history.md).

| | teams |
|---|---|
| frem-2021-06-27, truro-2026-07-22 (first days) | 0 |
| frem-2023-07-02 | 189 |
| frem-2026-06-11 | 845 |
| truro-2026-08-08 | 4 (William Hill Premiership Team of the Week …) |

## Layout

`[count u32]`, then 316-byte teams: `[award_id u32][day u16][year u16]` and 11 places of 28
bytes, `[person_tid][first_name_id][last_name_id][common_name_id][club_tid][rating f32][u32]`.
The rating is 6.0–10.0; the last u32 is 0 on every place measured. The same on both games.

## Evidence

`tests/test_award_history_evidence.py`, eight saves: every team names a team award, every
picked player and club resolves (club `ffffffff` for none), ratings 6.0–10.0. A player's name
ids are still his own on 9,268 of 9,295 places on frem-2026-06-11; the rest are retired
players whose slots were reused. No screen yet.

## Output

`output/<label>/team_history.json`: `[{award_id, date, players: [11 × {person_tid,
first_name_id, last_name_id, common_name_id, club_tid, rating}]}]`. Not loaded yet.
