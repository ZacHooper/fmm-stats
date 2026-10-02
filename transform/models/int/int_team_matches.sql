-- Every played-or-scheduled match twice, once per side, so the team asked
-- about is always in team_tid: venue H or A, goals for and against (the final
-- score, after extra time where there was any), the shoot-out, result on the
-- final score (a shoot-out decides a tie, not the result) and points.
with sides as (
    select
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
    *,
    case
        when goals_for > goals_against then 'W'
        when goals_for = goals_against then 'D'
        when goals_for < goals_against then 'L'
    end as result,
    case
        when goals_for > goals_against then 3
        when goals_for = goals_against then 1
        when goals_for < goals_against then 0
    end as points
from sides
