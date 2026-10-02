-- Each round of a knockout stage: name, team count and legs (2 for a tie
-- played home and away).
select
    cid,
    competition_season,
    stage_index,
    round_index,
    name,
    round_teams,
    legs
from {{ ref('int_rounds') }}
