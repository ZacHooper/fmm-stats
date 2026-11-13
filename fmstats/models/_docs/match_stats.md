{# Counts a player or a side makes in a match, as the save's match table stores them for our
   own matches (both sides), and their sums. A count on a season or competition row is the
   sum over the matches it covers. #}

{% docs appearances %}
Appearances: matches the player took the field in, as a starter or a substitute who came on.
On a career-history line, the game's own figure for the season, all competitions together (0 on
a loan year's parent-club line); elsewhere counted from our own matches.
Synonyms: `apps`.
{% enddocs %}

{% docs games_started %}
Matches the player started (a place in the XI).
{% enddocs %}

{% docs is_starter %}
The player started: a place in the XI (`pos_order` up to `var('starters')`).
Synonyms: `started`.
{% enddocs %}

{% docs has_appeared %}
The player took the field: he started or came on. An unused substitute has a line but didn't
appear; never infer it from `rating` or `condition`.
Synonyms: `appeared`.
{% enddocs %}

{% docs lineup_order %}
The player's place on the team sheet: 1-11 the starters, 12 and up the bench.
Synonyms: `pos_order`.
{% enddocs %}

{% docs minutes %}
Minutes played: from kick-off, or the minute he came on, to the minute he went off, was sent
off or the match ended (90, or 120 where it went to extra time). Stoppage time is not counted;
0 for a player who didn't appear.
{% enddocs %}

{% docs sub_on_minute %}
The minute he came on; NULL for a starter and an unused substitute.
{% enddocs %}

{% docs sub_off_minute %}
The minute he was taken off; NULL for a player not taken off.
{% enddocs %}

{% docs sent_off_minute %}
The minute of his sending-off event (a red card, `var('sending_off_events')`), which ends his
minutes; NULL if not sent off. A second-yellow dismissal raises no event, so it is missed here.
{% enddocs %}

{% docs sendings_off %}
How many times the player was sent off (matches with a `sent_off_minute`).
{% enddocs %}

{% docs rating %}
The game's match rating, a whole number 1-10 (the match table stores no decimals). 0 on the
line of a player who didn't appear (an unused substitute in a friendly or reserve match); an
unused substitute in a competitive match carries a flat 6.
{% enddocs %}

{% docs rating_adj %}
The starter's rating restated for the position he played (int.player_match_ratings): a z-score
within his rating role (`var('rating_roles')`), put back on the scale of every outfield role
pooled, over the managed team's competitive starts. Not bounded by 10. NULL for a substitute, a
side with no positions, and a role with fewer than `var('rating_adj_min_starts')` starts. It
moves slightly with every import.
{% enddocs %}

{% docs average_rating %}
The player's average match rating over the matches he appeared in, to two decimals. On a
career-history line it is the game's own figure (NULL with no appearances); on a scrapbook
entry, the profile's.
Synonyms: `avg_rating`, `fact_player_season.rating`, `site_player_career.rating`.
{% enddocs %}

{% docs is_player_of_match %}
The game's own Player of the Match (the match table's pick, one player per match, either
side), not the top rating.
{% enddocs %}

{% docs is_player_of_match_award %}
`is_player_of_match` counted as the club records count it: in competitive matches only (not
a friendly).
{% enddocs %}

{% docs goals %}
Goals scored. On a goalkeeper's career-history line the game stores goals conceded in this
field (checked on Frem's keepers: 24 in 28 apps, and 0 scored in our matches).
{% enddocs %}

{% docs assists %}
Assists.
{% enddocs %}

{% docs passes %}
Passes attempted.
Synonyms: `opp_passes` → `opponent_passes`.
{% enddocs %}

{% docs passes_completed %}
Passes completed.
Synonyms: `opp_passes_completed` → `opponent_passes_completed`.
{% enddocs %}

{% docs key_passes %}
Key passes.
{% enddocs %}

{% docs tackles %}
Tackles attempted.
Synonyms: `opp_tackles` → `opponent_tackles`.
{% enddocs %}

{% docs tackles_won %}
Tackles won.
Synonyms: `opp_tackles_won` → `opponent_tackles_won`.
{% enddocs %}

{% docs interceptions %}
Interceptions.
Synonyms: `opp_interceptions` → `opponent_interceptions`.
{% enddocs %}

{% docs headers %}
Headers attempted.
{% enddocs %}

{% docs headers_won %}
Headers won.
{% enddocs %}

{% docs crosses %}
Crosses attempted.
Synonyms: `opp_crosses` → `opponent_crosses`.
{% enddocs %}

{% docs crosses_completed %}
Crosses completed.
{% enddocs %}

{% docs dribbles %}
Dribbles.
{% enddocs %}

{% docs mistakes %}
Mistakes.
{% enddocs %}

{% docs mistakes_to_goal %}
Mistakes that led to a goal.
{% enddocs %}

{% docs clear_cut_chances %}
Clear-cut chances. A side's is the count the match row stores for it, on both game versions. A
player's is the clear-cut-chance events that name him, FMM27 only (NULL on an FMM22 match, whose
events carry none).
Synonyms: `opp_clear_cut_chances` → `opponent_clear_cut_chances`.
{% enddocs %}

{% docs clear_cut_scored %}
The player's clear-cut chances he scored from: a clear-cut-chance event followed by his own goal
in the same minute. FMM27 only: NULL on an FMM22 match.
{% enddocs %}

{% docs corners %}
Corners won, as the match row stores them.
Synonyms: `opp_corners` → `opponent_corners`.
{% enddocs %}

{% docs offsides %}
Times caught offside, as the match row stores them.
Synonyms: `opp_offsides` → `opponent_offsides`.
{% enddocs %}

{% docs fouls %}
Fouls committed, as the match row stores them. FMM27 only: NULL on an FMM22 match.
Synonyms: `opp_fouls` → `opponent_fouls`.
{% enddocs %}

{% docs assist_tid %}
The player who assisted the goal: the assist event FMM27 writes straight after a goal, for the
scorer's side. NULL for an unassisted goal, for every other event, and on an FMM22 match, which
writes no assist events.
{% enddocs %}

{% docs xg %}
Expected goals: the chances' worth in goals, as the match screen shows it (the player's
stored value, rounded to two decimals; a side's xG is its players' sum). FMM27 only: NULL on
an FMM22 match, which stores none.
Synonyms: `opp_xg` → `opponent_xg`.
{% enddocs %}

{% docs xa %}
Expected assists: the xG of the shots the player set up, as the game's Player Statistics
screen shows it (whose xDiff is assists − xA). A side's xA is at most its xG; the rest is
shots nobody set up. FMM27 only: NULL on an FMM22 match, which stores none.
{% enddocs %}

{% docs goals_conceded %}
The goals a goalkeeper let in while on the pitch, as his match line stores them (0 for an
outfield player). FMM27 only: NULL on an FMM22 match.
{% enddocs %}

{% docs shots %}
Shots.
Synonyms: `opp_shots` → `opponent_shots`.
{% enddocs %}

{% docs shots_on_target %}
Shots on target.
Synonyms: `opp_shots_on_target` → `opponent_shots_on_target`.
{% enddocs %}

{% docs yellows %}
Yellow cards.
{% enddocs %}

{% docs reds %}
Red cards in the season, the game's own career-history figure.
{% enddocs %}

{% docs condition %}
The player's condition on his match line, in percent (45-100 in the store). Unverified: which
moment of the match it is read at. NULL where the save stores none (an unused substitute in a
friendly or reserve match).
{% enddocs %}
