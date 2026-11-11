{# A match and its sides: venue, score, result, events. Player and team counts are in
   match_stats.md. #}

{% docs home_team_tid %}
The home side. A match is (match_date, home_team_tid, away_team_tid). On a tie, the home side of
its first leg.
Synonyms: `team_a_tid` → `home_team_tid`.
{% enddocs %}

{% docs away_team_tid %}
The away side. On a tie, the away side of its first leg.
Synonyms: `team_b_tid` → `away_team_tid`.
{% enddocs %}

{% docs opponent_tid %}
The other side in the match, relative to the row's `team_tid`.
{% enddocs %}

{% docs venue %}
Where the row's side played: `H` at home, `A` away (the fixture's home and away sides; a
neutral-ground final still has one of each).
{% enddocs %}

{% docs goals_for %}
Goals the row's side scored: in a match, the final score after extra time where there was any
(shoot-out goals are `pens_for`); in a standings row, the total over its matches so far; in a
tie, the aggregate of the final scores.
Synonyms: `goals_a` → `home_goals`.
{% enddocs %}

{% docs goals_against %}
Goals the row's side conceded, counted as `goals_for` is.
Synonyms: `goals_b` → `away_goals`.
{% enddocs %}

{% docs pens_for %}
The row's side's goals in the shoot-out (on a tie, the last leg's); NULL where there was none.
Synonyms: `pens_a` → `home_pens`.
{% enddocs %}

{% docs pens_against %}
The other side's goals in the shoot-out; NULL where there was none.
Synonyms: `pens_b` → `away_pens`.
{% enddocs %}

{% docs result %}
The row's side's result on the final score: `W`, `D` or `L`. A shoot-out decides a tie, not the
result: a match drawn after extra time is `D`. NULL for a match not yet played.
{% enddocs %}

{% docs points %}
League points: from a match, 3 for a win, 1 for a draw, 0 for a loss on the final score (NULL
before it is played); in a standings row, the total so far. No deduction is read.
{% enddocs %}

{% docs decided_by %}
How the match was decided: `'90'` in normal time, `'ET'` in extra time, `'pens'` on a
shoot-out; NULL for a match not yet played. On a tie, the last leg's.
{% enddocs %}

{% docs has_extra_time %}
The match went to extra time (`decided_by` `ET` or `pens`).
Synonyms: `extra_time`.
{% enddocs %}

{% docs score_display %}
The final score for reading only, home first: `2-1`, `2-1 aet`, `0-0 (3-5 pens)`. Compute from
`fact_team_match`, never from this.
{% enddocs %}

{% docs has_detail %}
The match is one of our own with its detail in the save's match table: events, player lines and
team stats. Only these have rows in `fact_player_match` and `fact_match_event`.
{% enddocs %}

{% docs attendance %}
The crowd, as the match table stores it: 0 on a friendly. Only our own matches with detail
have one; NULL elsewhere.
{% enddocs %}

{% docs competition_source %}
How the match's competition was found, the fixture list naming none
(int.stage_competitions): `our_match` from one of our own matches in the stage,
`league_structure` from the league rule (a stage whose clubs are one league's); NULL where
neither labels it (a cup abroad, a friendly with no competition season).
{% enddocs %}

{% docs matchday %}
The matchday in a league or group stage, from 1, as the game shows it.
{% enddocs %}

{% docs matchday_index %}
The fixture list's matchday in a league or group stage, from 0 (`matchday` is this + 1). A
postponed match keeps its matchday. NULL outside a stage.
Synonyms: `dim_match.matchday`, `mart_standings.matchday`.
{% enddocs %}

{% docs leg %}
Which leg of a two-legged tie the match is, 1 or 2 by date; NULL for a single-legged round and
outside a knockout stage.
{% enddocs %}

{% docs legs %}
The legs per tie in the round, from its rules: 1, or 2 for home and away.
{% enddocs %}

{% docs legs_played %}
How many of the tie's legs have been played.
{% enddocs %}

{% docs formation %}
A formation's name (`4-2-3-1`, `5-2-2-1`). On `fact_team_match`, the managed side's formation
in that match as the match table stores it (NULL for every other side and match); on the
formation lists, a formation an AI manager can prefer (`var('formation_slots')`).
Synonyms: `site_club_managers.formation_*` → `formation_*_name`.
{% enddocs %}

{% docs minute %}
The match minute the event happened in, from 1. Stoppage time stays in the minute it extends
(`added_minutes` holds the rest).
{% enddocs %}

{% docs added_minutes %}
Minutes into stoppage time, where the event happened in it; 0 otherwise.
{% enddocs %}

{% docs period %}
The part of the match: `first_half`, `second_half`, `extra_time_first_half`,
`extra_time_second_half` by the minute (`var('match_periods')`), or `shootout` for a shoot-out
kick, whatever minute the save gives it.
{% enddocs %}

{% docs period_order %}
The period's place in a match, from 1 (first half) to 5 (shoot-out).
{% enddocs %}

{% docs first_minute %}
The first minute the period holds; NULL for the shoot-out.
{% enddocs %}

{% docs last_minute %}
The last minute the period holds; NULL for the shoot-out.
{% enddocs %}

{% docs event_type %}
The event type's name from the loader's seed (`goal`, `own_goal`, `penalty`, `red_card`,
`shootout_goal`, ...); NULL for a code the seed doesn't name.
{% enddocs %}

{% docs is_appearance_ending %}
The event ends the player's match (a sending-off, `var('sending_off_events')`): his minutes stop
at it.
Synonyms: `ends_appearance`.
{% enddocs %}

{% docs is_shootout %}
The event is a shoot-out kick, never a goal (`var('shootout_events')`).
{% enddocs %}

{% docs scores_for %}
Which side a scoring event counts for: `for` the player's own (a goal, a penalty), `against`
the other (an own goal); NULL for an event that doesn't score.
{% enddocs %}

{% docs player_team_tid %}
The side of the player the event names. An own goal's `team_tid` is the other side; this is
still his own.
{% enddocs %}
