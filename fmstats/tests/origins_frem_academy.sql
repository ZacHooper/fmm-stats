{{ config(tags=['known_answers']) }}
-- Frem's academy and home: "Frem Yth" is tid 65189, the complement of Frem's
-- 346, a youth side of the club we manage with players who came out of it as
-- their origin; and the club's nation is Denmark, the nation whose league it
-- plays in. One row per known answer the store does not give.
with career as (
    select * from {{ ref('stg_career') }}
),

academy as (
    select
        count(*) filter (
            where
            team_clubs.team_tid = 65189
            and team_clubs.is_youth_side
            and team_clubs.club_tid = career.managed_club_tid
        ) as resolves,
        (
            select count(*) as alumni
            from {{ ref('dim_person') }} as people
            where
                people.origin_youth_team_tid = 65189
                and people.origin_club_tid = career.managed_club_tid
        ) as alumni
    from {{ ref('int_team_clubs') }} as team_clubs
    cross join career
    group by career.managed_club_tid
),

home as (
    select
        nations.name as nation,
        clubs.nation_id = clubs.league_nation_id as plays_at_home
    from {{ ref('dim_club') }} as clubs
    inner join career
        on clubs.club_tid = career.managed_club_tid
    left join {{ ref('dim_nation') }} as nations
        on clubs.nation_id = nations.nation_id
),

checks as (
    select
        'youth tid 65189 is not our academy' as check_name,
        cast(academy.resolves as varchar) as got
    from academy
    where academy.resolves <> 1
    union all
    select
        'our academy has no alumni' as check_name,
        cast(academy.alumni as varchar) as got
    from academy
    where academy.alumni = 0
    union all
    select
        'our club is not Danish in a Danish league' as check_name,
        home.nation as got
    from home
    where home.nation is distinct from 'Denmark' or not home.plays_at_home
    union all
    select
        'our club has no record' as check_name,
        null as got
    where not exists (select 1 as found from home)
)

select checks.*
from checks
cross join career
where career.career_key = 'frem'
