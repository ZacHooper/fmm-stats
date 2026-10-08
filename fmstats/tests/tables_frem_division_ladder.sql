{{ config(tags=['known_answers']) }}
-- Frem's league as at each snapshot climbs the Danish ladder in order:
-- 3. Division (cid 1147), 2. Division (4), NordicBet Liga (3), 3F Superliga
-- (2), so the as-at resolution varies by season rather than giving every
-- snapshot the division the club ended in. One row per step that differs from
-- the expected ladder; none for another career.
with career as (
    select managed_club_tid from {{ ref('stg_career') }}
),

steps as (
    select
        leagues.league_cid,
        min(leagues.snapshot_date) as first_date
    from {{ ref('int_team_leagues') }} as leagues
    inner join career
        on leagues.team_tid = career.managed_club_tid
    where career.managed_club_tid = 346
    group by leagues.league_cid
),

actual as (
    select
        league_cid,
        row_number() over (order by first_date) as step
    from steps
),

expected as (
    select
        ladder.league_cid,
        ladder.step
    from (values (1147, 1), (4, 2), (3, 3), (2, 4)) as ladder (league_cid, step)
    cross join career
    where career.managed_club_tid = 346
)

select
    coalesce(expected.step, actual.step) as step,
    expected.league_cid as expected_league_cid,
    actual.league_cid as actual_league_cid
from expected
full outer join actual
    on expected.step = actual.step
where expected.league_cid is distinct from actual.league_cid
