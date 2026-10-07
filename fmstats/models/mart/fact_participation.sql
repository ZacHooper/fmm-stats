-- Each team in each competition season it has a labelled match in: first and
-- last match dates, matches played, and the stage (and knockout round) it
-- reached.
select
    team_tid,
    cid,
    competition_season,
    first_match_date,
    last_match_date,
    matches_played,
    stage_reached,
    round_reached
from {{ ref('int_participations') }}
