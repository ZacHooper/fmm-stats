-- The world fixture list with scores, every match the save's archive holds.
-- Teams are club-shaped tids, national sides included (tid 0 is one).
-- home_goals / away_goals are the score after 90 minutes, home_goals_aet /
-- away_goals_aet the score after extra time (NULL where there was none), and
-- home_pens / away_pens the shootout (NULL where there was none).
-- stage_index reads NULL where the fixture belongs to no stage
-- (var('no_id8')), and seq_id where it has no sequence number
-- (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    home_tid as home_team_tid,
    away_tid as away_team_tid,
    date as match_date,
    year,
    round,
    home_goals,
    away_goals,
    home_extra_goals as home_goals_aet,
    away_extra_goals as away_goals_aet,
    home_pens,
    away_pens,
    stage_key,
    nullif(seq_id, {{ var('no_id16') }}) as seq_id,
    season_year,
    nullif(stage_index, {{ var('no_id8') }}) as stage_index,
    round_index,
    subr
from {{ source('raw', 'world_fixtures') }}
