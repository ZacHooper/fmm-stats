-- Each match rating restated for the position played, keyed (match_id,
-- player_tid): rating_adj is a starter's rating as a z-score within his role
-- (var('rating_roles') maps a position to one), put back on the scale of
-- every outfield role pooled. The baseline is the managed team's competitive
-- starts across all seasons (a friendly inflates, an unused substitute carries
-- a flat rating, reserve games carry anonymous fillers), so it moves slightly
-- with every import. NULL for a substitute and for a side the save records no
-- positions for.
with career as (
    select * from {{ ref('stg_career') }}
),

roles as (
    select
        position_roles.position,
        position_roles.role
    from (
        values
        {% for position, role in var('rating_roles').items() %}
        ('{{ position }}', '{{ role }}'){% if not loop.last %},{% endif %}
        {% endfor %}
    ) as position_roles (position, role)
),

rated as (
    select
        matches.match_id,
        matches.player_tid,
        matches.team_tid,
        matches.started,
        matches.rating,
        roles.role,
        competitions.type = 'friendly' as is_friendly
    from {{ ref('fact_player_match') }} as matches
    inner join {{ ref('dim_match') }} as match_dims
        on matches.match_id = match_dims.match_id
    left join {{ ref('dim_competition') }} as competitions
        on match_dims.cid = competitions.cid
    left join roles
        on matches.position = roles.position
),

base as (
    select
        rated.role,
        rated.rating
    from rated
    inner join career
        on rated.team_tid = career.managed_club_tid
    where
        rated.started
        and not coalesce(rated.is_friendly, false)
        and rated.role is not null
),

baseline as (
    select
        role,
        avg(rating) as role_mean,
        stddev_samp(rating) as role_sd
    from base
    group by role
),

pool as (
    select
        avg(rating) as pool_mean,
        stddev_samp(rating) as pool_sd
    from base
    where role <> 'GK'
)

select
    rated.match_id,
    rated.player_tid,
    rated.role,
    case
        when rated.started and rated.role is not null
            then
                pool.pool_mean
                + (rated.rating - baseline.role_mean)
                / nullif(baseline.role_sd, 0) * pool.pool_sd
    end as rating_adj
from rated
cross join pool
left join baseline
    on rated.role = baseline.role
