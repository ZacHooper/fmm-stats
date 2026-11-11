{# Competitions, their stages and rounds, tables, ties, and how a team's season in one ended. #}

{% docs type %}
The competition's type, decoded from `type_id`: `league`, `reserve_league`, `cup`, `friendly`,
or `type_<n>` for a code not yet named.
{% enddocs %}

{% docs type_id %}
The competition's type as the save codes it (0 and 1 league, 2 cup, 8 reserve league, 9
friendly; the rest unnamed).
{% enddocs %}

{% docs code %}
The short code the game shows for the row's subject: a competition's (`SL` for the 3F
Superliga), a nation's three letters.
{% enddocs %}

{% docs short_name %}
The competition's short name, as stored (often the same as its name).
{% enddocs %}

{% docs parent_cid %}
The competition this one is a part of (Spanish Second Division B1-B4 -> B); NULL for none.
{% enddocs %}

{% docs tier_index %}
The competition's division tier, from 0 (the top), as stored: parallel divisions share a tier.
100 on a non-league competition and on most reserve leagues, 255 on one; use `tier` for a
league's tier from 1.
Synonyms: `dim_competition.level`.
{% enddocs %}

{% docs tier %}
The league's division tier, from 1 (the top): the save's level + 1, parallel divisions sharing
a tier.
{% enddocs %}

{% docs reputation %}
The game's reputation score for the row's subject, as stored; higher is better. The scale
depends on the subject: a competition's runs 0-200, a team's 1-10,000 (the stars on its club
card), a player's 1-10,000 (`reputation` is his home reputation, beside `current_reputation`
and `world_reputation`).
{% enddocs %}

{% docs league_cid %}
The team's league on the snapshot: the newest league its record named on or before it
(int.team_leagues). A team moving division names none on the rollover day, so it stays in the
league it played last until it names its new one.
{% enddocs %}

{% docs other_division_cid %}
The record's other-division field, the division it names in place of its league; NULL where it
names none (every row in the stores measured).
{% enddocs %}

{% docs last_league_cid %}
The league the team played in last season.
{% enddocs %}

{% docs last_league_position %}
The team's finishing position last season, in `last_league_cid` (not the current standing).
Unverified: 0 is common, also on teams with a last league, and values from 247 to 255 occur;
what either means is not known.
{% enddocs %}

{% docs ladder_rank %}
The league's place on the managed team's comparison ladder: 0 is the managed team's league, then
each league of its nation with a lower reputation, highest first. NULL outside the ladder.
{% enddocs %}

{% docs skill_index %}
The league's average player ability, scaled 0-100 between the weakest and strongest league on
the snapshot; NULL with fewer than `var('site_skill_min_players')` rated players. An index, so no
ability number leaves the view.
{% enddocs %}

{% docs n_members %}
The teams whose league is this one on the snapshot (int.team_leagues).
Synonyms: `member_count`.
{% enddocs %}

{% docs n_rated %}
The league's players with an ability, the ones `skill_index` averages.
Synonyms: `rated`.
{% enddocs %}

{% docs n_teams %}
The teams with a match in the competition season (`fact_participation`).
{% enddocs %}

{% docs stage_format %}
The stage's format: `knockout`, `league` or `group` (`var('stage_formats')`).
{% enddocs %}

{% docs stage_type_code %}
The stage's type as its rules code it: 0 knockout, 1 league, 2 groups, 6 a play-off feeder.
{% enddocs %}

{% docs stage_code %}
The stage's four-letter tag in its rules (`leag`, `grpa`, `poff`, `fnls`, ...).
{% enddocs %}

{% docs stage_teams %}
The teams the stage's rules give it; NULL where the rules list the stage twice with different
counts.
{% enddocs %}

{% docs round_teams %}
The teams the round's rules give it; NULL where the rules list the round twice with different
counts.
{% enddocs %}

{% docs n_groups %}
The groups the stage is drawn into, from its rules; NULL for a stage with none.
{% enddocs %}

{% docs is_final_stage %}
The stage is its competition season's last, whose outcome decides the winner.
{% enddocs %}

{% docs stage_type %}
The kind of stage a match is in, for the match list: `League` or `Group`; for a knockout stage,
`Qualifying` where it comes before the group stage of a competition with no league stage, else
`Knockout`; NULL for a match in no stage (a friendly).
{% enddocs %}

{% docs stage %}
The game's own label for the match's stage: a league stage's name, `Group` and the group's
letter, or the stage and round names.
{% enddocs %}

{% docs stage_reached %}
The furthest stage (`stage_index`) the team has a match in that competition season.
{% enddocs %}

{% docs round_reached %}
The furthest round (`round_index`) the team has a match in within `stage_reached`, where it is a
knockout stage; NULL otherwise.
{% enddocs %}

{% docs final_position %}
The game's own final league position, from the club league history: set once the league season
is finished (the latest snapshot holding it), NULL until then.
{% enddocs %}

{% docs table_position %}
The team's place in a table: on a standings row, after that matchday (ranked on points, goal
difference, goals scored, then `team_tid`; the save's further tie-breakers are not read); on an
outcome, its place at its latest matchday in the stage it reached, NULL for a knockout stage.
Synonyms: `mart_standings.position`.
{% enddocs %}

{% docs is_winner %}
The team won the competition season: `final_position` 1, or, where the final stage is a
knockout, the last round's tie. NULL until the save decides it.
{% enddocs %}

{% docs played %}
Matches played. On a standings row, the team's matches through that matchday; on a
participation, its played matches in the competition season (scheduled ones not counted).
Synonyms: `matches_played`.
{% enddocs %}

{% docs won %}
Matches won on the final score, through that matchday.
{% enddocs %}

{% docs drawn %}
Matches drawn on the final score, through that matchday.
{% enddocs %}

{% docs lost %}
Matches lost on the final score, through that matchday.
{% enddocs %}

{% docs goal_difference %}
`goals_for` - `goals_against`.
{% enddocs %}

{% docs is_decided %}
The tie is decided: all its legs (by the round's rules) are played.
{% enddocs %}

{% docs winner_tid %}
The team that won the tie: on aggregate, then on the last leg's shoot-out (no away-goals rule);
NULL until it is decided.
{% enddocs %}

{% docs competition %}
A competition's name. On our matches it is the match table's own name for it (`Friendly` for a
friendly); on a scrapbook entry, the profile's.
{% enddocs %}
