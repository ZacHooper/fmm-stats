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

role_means as (
    select
        role,
        count(*) as baseline_starts,
        avg(rating_adj) as mean_adj
    from base
    group by role
)

select
    case
        when role_means.baseline_starts < 30
            then 'fewer than 30 baseline starts'
        else 'role mean differs from the pool mean'
    end as check_name,
    role_means.role,
    role_means.baseline_starts,
    role_means.mean_adj,
    pool.pool_mean
from role_means
cross join pool
where
    role_means.baseline_starts < 30
    or abs(role_means.mean_adj - pool.pool_mean) > 0.01
    or role_means.mean_adj is null
union all
select
    'empty baseline' as check_name,
    null as role,
    0 as baseline_starts,
    null as mean_adj,
    null as pool_mean
where not exists (select 1 as found from role_means)
