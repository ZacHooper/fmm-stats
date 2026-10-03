-- Each match twice, once per side: venue, goals for and against (the final
-- score, from the world fixture list), the shoot-out, result and points. The
-- match's date and teams are on dim_match (match_id).
select
    match_id,
    team_tid,
    opponent_tid,
    venue,
    goals_for,
    goals_against,
    pens_for,
    pens_against,
    result,
    points
from {{ ref('int_team_matches') }}
