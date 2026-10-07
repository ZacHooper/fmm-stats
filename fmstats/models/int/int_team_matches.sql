-- Every played-or-scheduled match twice, once per side, so the team asked
-- about is always in team_tid: venue H or A, goals for and against (the final
-- score, after extra time where there was any), the shoot-out, result on the
-- final score (a shoot-out decides a tie, not the result) and points. For a
-- match of ours with detail (int.our_matches), the side's team stats and, on
-- the managed side, its formation; NULL for every other match.
with sides as (
    select
        match_id,
        match_date,
        home_team_tid,
        away_team_tid,
        home_team_tid as team_tid,
        away_team_tid as opponent_tid,
        'H' as venue,
        home_goals as goals_for,
        away_goals as goals_against,
        home_pens as pens_for,
        away_pens as pens_against
    from {{ ref('int_matches') }}
    union all
    select
        match_id,
        match_date,
        home_team_tid,
        away_team_tid,
        away_team_tid as team_tid,
        home_team_tid as opponent_tid,
        'A' as venue,
        away_goals as goals_for,
        home_goals as goals_against,
        away_pens as pens_for,
        home_pens as pens_against
    from {{ ref('int_matches') }}
)

select
    sides.*,
    case
        when sides.goals_for > sides.goals_against then 'W'
        when sides.goals_for = sides.goals_against then 'D'
        when sides.goals_for < sides.goals_against then 'L'
    end as result,
    case
        when sides.goals_for > sides.goals_against then 3
        when sides.goals_for = sides.goals_against then 1
        when sides.goals_for < sides.goals_against then 0
    end as points,
    case
        when (sides.venue = 'H') = ours.is_home then ours.formation
    end as formation,
    {% for stat in var('team_match_stats') %}
    case
        when sides.venue = 'H' then ours.home_{{ stat }}
        else ours.away_{{ stat }}
    end as {{ stat }}{% if not loop.last %},{% endif %}
    {% endfor %}
from sides
left join {{ ref('int_our_matches') }} as ours
    on sides.match_id = ours.match_id
