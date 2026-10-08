-- In each of our own matches, a side's goals (fact_team_match.goals_for) are
-- the goals its own players scored (fact_player_match) plus the own goals the
-- other side put past itself (fact_match_event, counted for this side), so no
-- side is credited more goals than its opponent conceded, and a team's score
-- and its scorers' total differ by exactly the own goals. Shoot-out kicks are
-- in neither.
with player_goals as (
    select
        match_id,
        team_tid,
        sum(goals) as goals
    from {{ ref('fact_player_match') }}
    group by match_id, team_tid
),

own_goals as (
    select
        match_id,
        team_tid,
        count(*) as goals
    from {{ ref('fact_match_event') }}
    where event_type = 'own_goal'
    group by match_id, team_tid
)

select
    sides.match_id,
    sides.team_tid,
    sides.goals_for,
    player_goals.goals as player_goals,
    coalesce(own_goals.goals, 0) as own_goals_for
from {{ ref('fact_team_match') }} as sides
inner join player_goals
    on
        sides.match_id = player_goals.match_id
        and sides.team_tid = player_goals.team_tid
left join own_goals
    on
        sides.match_id = own_goals.match_id
        and sides.team_tid = own_goals.team_tid
where
    sides.goals_for
    is distinct from player_goals.goals + coalesce(own_goals.goals, 0)
