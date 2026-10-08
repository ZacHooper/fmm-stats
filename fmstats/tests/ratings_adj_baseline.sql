-- rating_adj is standardised on its baseline, the managed team's competitive
-- (non-friendly) starts with a role: on those starts every role's mean
-- rating_adj equals the mean raw rating of the outfield roles pooled (within
-- 0.01), and every role rests on at least 30 starts. One row per role that
-- breaks either, plus one if the baseline is empty.
with career as (
    select managed_club_tid from {{ ref('stg_career') }}
),

base as (
    select
        facts.role,
        facts.rating,
        facts.rating_adj
    from {{ ref('fact_player_match') }} as facts
    inner join career
        on facts.team_tid = career.managed_club_tid
    inner join {{ ref('dim_match') }} as matches
        on facts.match_id = matches.match_id
    left join {{ ref('dim_competition') }} as competitions
        on matches.cid = competitions.cid
    where
        facts.started
        and facts.role is not null
        and competitions.type is distinct from 'friendly'
),

pool as (
    select avg(rating) as pool_mean
    from base
    where role <> 'GK'
),

roles as (
    select
        role,
        count(*) as starts,
        avg(rating_adj) as mean_adj
    from base
    group by role
)

select
    case
        when roles.starts < 30 then 'fewer than 30 baseline starts'
        else 'role mean differs from the pool mean'
    end as check_name,
    roles.role,
    roles.starts,
    roles.mean_adj,
    pool.pool_mean
from roles
cross join pool
where
    roles.starts < 30
    or abs(roles.mean_adj - pool.pool_mean) > 0.01
    or roles.mean_adj is null
union all
select
    'empty baseline' as check_name,
    null as role,
    0 as starts,
    null as mean_adj,
    null as pool_mean
where not exists (select 1 from roles)
