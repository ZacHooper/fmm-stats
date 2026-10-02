{{ config(materialized='view') }}
-- Each league or group stage's table after every matchday, with the date it
-- runs to (int_standings for the rules and their limits). A view, not stored.
select
    cid,
    competition_season,
    stage_index,
    stage_key,
    matchday,
    through_date,
    position,
    team_tid,
    played,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goal_difference,
    points,
    is_latest
from {{ ref('int_standings') }}
