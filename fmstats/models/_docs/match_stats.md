{# Counts a player or a side makes in a match, as the save's match table stores them for our
   own matches (both sides), and their sums. A count on a season or competition row is the
   sum over the matches it covers. #}

{% docs appearances %}
Appearances: matches the player took the field in, as a starter or a substitute who came on.
On a career-history line, the game's own figure for the season, all competitions together (0 on
a loan year's parent-club line); elsewhere counted from our own matches.
{% enddocs %}

{% docs games_started %}
Matches the player started (a place in the XI).
{% enddocs %}

{% docs is_starter %}
The player started: a place in the XI (`lineup_order` up to `var('starters')`).
{% enddocs %}

{% docs has_appeared %}
The player took the field: he started or came on. An unused substitute has a line but didn't
appear; never infer it from `rating` or `condition`.
{% enddocs %}

{% docs lineup_order %}
The player's place on the team sheet: 1-11 the starters, 12 and up the bench.
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
{% enddocs %}

{% docs passes_completed %}
Passes completed.
{% enddocs %}

{% docs key_passes %}
Key passes.
{% enddocs %}

{% docs tackles %}
Tackles attempted.
{% enddocs %}

{% docs tackles_won %}
Tackles won.
{% enddocs %}

{% docs interceptions %}
Interceptions.
{% enddocs %}

{% docs headers %}
Headers attempted.
{% enddocs %}

{% docs headers_won %}
Headers won.
{% enddocs %}

{% docs crosses %}
Crosses attempted.
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

{% docs shots %}
Shots.
{% enddocs %}

{% docs shots_on_target %}
Shots on target.
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
