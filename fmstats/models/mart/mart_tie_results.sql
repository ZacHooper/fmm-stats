{{ config(materialized='view') }}
-- Each knockout tie: its two teams (team_a the home side of the first leg),
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
    team_a_tid,
    team_b_tid,
    goals_a,
    goals_b,
    pens_a,
    pens_b,
    decided_by,
    is_decided,
    winner_tid
from {{ ref('int_ties') }}
