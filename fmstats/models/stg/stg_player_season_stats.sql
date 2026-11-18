-- The Player History screen's This Season panel, one row per player attribute
-- record (sid) and block that has an appearance. club_season is the history
-- list's current-season line (league, cup and continental, plus a club's B
-- team); league, cup (every domestic cup), continental, non_competitive
-- (friendlies and reserve matches) and international split it by kind.
-- goals_conceded is a goalkeeper's; 0 for the rest.
select
    cast(phase as date) as snapshot_date,
    sid,
    block,
    apps as appearances,
    goals,
    assists,
    conceded as goals_conceded,
    rating_total,
    yellows,
    reds,
    player_of_match as player_of_match_awards
from {{ source('raw', 'player_season_stats') }}
