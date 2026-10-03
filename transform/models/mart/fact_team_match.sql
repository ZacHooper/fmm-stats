-- Each match twice, once per side: venue, goals for and against (the final
-- score, from the world fixture list), the shoot-out, result and points. The
-- match's date and teams are on dim_match (match_id). For our own matches with
-- detail, the side's team stats and, on the managed side, its formation;
-- NULL for every other match.
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
    points,
    formation,
    {% for stat in var('team_match_stats') %}
    {{ stat }}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('int_team_matches') }}
