{{ config(tags=['known_answers']) }}
-- Frem's 2024 campaign (2023-06-30 to 2024-06-29), as the full rebuild of the
-- Frem store holds it: 73 league goals for in the NordicBet Liga, 70 of them
-- by our own players (the other 3 are opposition own goals); the competitive
-- golden boot is Adam Jakobsen's 30 (he scored 4 more in friendlies); the
-- first team played 39 matches (32 league, 1 cup, 6 friendlies) and the club's
-- two teams 59, the reserve side's 20 being the difference. The club's teams
-- are Boldklubben Frem (346, first team) and its reserves (7296). One row per
-- answer that differs; none for another career.
with career as (
    select * from {{ ref('stg_career') }}
    where career_key = 'frem'
),

club_teams as (
    select teams.*
    from {{ ref('dim_team') }} as teams
    inner join career
        on teams.club_tid = career.managed_club_tid
),

sides_2024 as (
    select
        sides.*,
        matches.cid
    from {{ ref('fact_team_match') }} as sides
    inner join {{ ref('dim_match') }} as matches
        on sides.match_id = matches.match_id
    cross join career
    where {{ season_of('matches.match_date') }} = 2024
),

league as (
    select cid from {{ ref('dim_competition') }}
    where name = 'NordicBet Liga'
),

scorers as (
    select
        persons.name,
        sum(seasons.goals) as goals
    from {{ ref('fact_player_competition_season') }} as seasons
    inner join {{ ref('dim_competition') }} as competitions
        on seasons.cid = competitions.cid
    inner join {{ ref('dim_person') }} as persons
        on seasons.person_id = persons.person_id
    where
        seasons.season = 2024
        and competitions.type <> 'friendly'
        and seasons.team_tid in (select club_teams.team_tid from club_teams)
    group by seasons.person_id, persons.name
),

answers as (
    select
        'league goals for' as "check",
        '73' as expected,
        cast(sum(sides_2024.goals_for) as varchar) as actual
    from sides_2024
    where
        sides_2024.team_tid = 346
        and sides_2024.cid in (select league.cid from league)
    union all
    select
        'league goals by our players' as "check",
        '70' as expected,
        cast(sum(seasons.goals) as varchar) as actual
    from {{ ref('fact_player_competition_season') }} as seasons
    where
        seasons.season = 2024
        and seasons.team_tid = 346
        and seasons.cid in (select league.cid from league)
    union all
    select
        'competitive golden boot' as "check",
        'Adam Jakobsen 30' as expected,
        string_agg(name || ' ' || goals, ', ' order by name) as actual
    from scorers
    where goals = (select max(leaders.goals) as goals from scorers as leaders)
    union all
    select
        'first-team matches' as "check",
        '39' as expected,
        cast(count(*) as varchar) as actual
    from sides_2024
    where team_tid = 346
    union all
    select
        'matches of the club''s two teams' as "check",
        '59' as expected,
        cast(count(distinct sides_2024.match_id) as varchar) as actual
    from sides_2024
    where sides_2024.team_tid in (select club_teams.team_tid from club_teams)
    union all
    select
        'the club''s teams' as "check",
        '346 first, 7296 reserve' as expected,
        string_agg(
            team_tid || ' ' || team_type, ', ' order by team_tid
        ) as actual
    from club_teams
)

select answers.*
from answers
cross join career
where answers.actual is distinct from answers.expected
