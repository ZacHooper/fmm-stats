{{ config(materialized='view') }}
-- Each knockout tie: its two teams (home and away: the first leg's sides),
-- the aggregate, the last leg's shoot-out, how it was decided and the winner,
-- once all its legs are played. A view over int_ties, not stored.
select
    tie_id,
    cid,
    competition_season,
    stage_index,
    round_index,
    legs,
    legs_played,
    first_match_date,
    last_match_date,
    team_a_tid as home_team_tid,
    team_b_tid as away_team_tid,
    goals_a as home_goals,
    goals_b as away_goals,
    pens_a as home_pens,
    pens_b as away_pens,
    decided_by,
    is_decided,
    winner_tid
from {{ ref('int_ties') }}
