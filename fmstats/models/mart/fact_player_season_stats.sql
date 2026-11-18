-- The This Season panel: each player's current-season appearances, goals and
-- ratings on each snapshot, by kind of competition (block). The career
-- history (fact_player_season) holds the seasons before this one.
select
    snapshot_date,
    person_id,
    tid,
    block,
    appearances,
    goals,
    assists,
    goals_conceded,
    rating_total,
    average_rating,
    yellows,
    reds,
    player_of_match_awards
from {{ ref('int_player_season_stats') }}
