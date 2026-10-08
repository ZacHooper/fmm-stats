-- fact_team_match holds every match from both sides, and the two rows mirror:
-- each side's opponent is the other row's team, goals and shoot-out kicks for
-- one side are against the other, and one side is home and the other away.
-- result follows the final score (W/D/L) and points the result (3/1/0). A
-- formation is the save's record of our own shape, so only a team of the
-- managed club carries one.
with career as (
    select * from {{ ref('stg_career') }}
),

sides as (
    select * from {{ ref('fact_team_match') }}
),

side_counts as (
    select
        match_id,
        count(*) as n_sides
    from sides
    group by match_id
)

select
    'a match without exactly two sides' as "check",
    side_counts.match_id,
    null as team_tid
from side_counts
where side_counts.n_sides <> 2
union all
select
    'the two sides do not mirror' as "check",
    sides.match_id,
    sides.team_tid
from sides
inner join sides as other
    on
        sides.match_id = other.match_id
        and sides.team_tid <> other.team_tid
where
    sides.opponent_tid is distinct from other.team_tid
    or sides.goals_for is distinct from other.goals_against
    or sides.pens_for is distinct from other.pens_against
    or sides.venue = other.venue
union all
select
    'result or points disagree with the score' as "check",
    sides.match_id,
    sides.team_tid
from sides
where
    sides.result is distinct from case
        when sides.goals_for > sides.goals_against then 'W'
        when sides.goals_for = sides.goals_against then 'D'
        when sides.goals_for < sides.goals_against then 'L'
    end
    or sides.points is distinct from case sides.result
        when 'W' then 3
        when 'D' then 1
        when 'L' then 0
    end
union all
select
    'a formation on a team the career does not manage' as "check",
    sides.match_id,
    sides.team_tid
from sides
cross join career
left join {{ ref('dim_team') }} as teams
    on sides.team_tid = teams.team_tid
where
    sides.formation is not null
    and teams.club_tid is distinct from career.managed_club_tid
