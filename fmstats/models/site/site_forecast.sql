-- The attribute forecast the web app reads, keyed (attribute, age_now,
-- value_now, horizon_age): of the outfield players who had value_now of an
-- attribute at age_now, the values they reached at horizon_age (their
-- snapshot closest to it, within a year; the earlier on a tie), as quartiles
-- and mean, over every player in the store. A cell needs
-- var('forecast').min_players players.
--
-- bucket says whether to trust an attribute's cells: 'fixed' where it does
-- not move between two exact reads a year apart, 'unmodelled' where too few
-- exact pairs exist or the decoded reads grow at more than max_ratio times
-- (or less than 1/max_ratio of) the exact ones, else 'forecastable'.
{% set f = var('forecast') %}
with horizons as (
    select unnest({{ f.horizons }}) as horizon_age
),

snapshots as (
    select
        person_id,
        snapshot_date,
        tid,
        age,
        attributes_are_estimated as is_estimated,
        {% for attribute in var('attr_order') %}
        "{{ attribute }}"{% if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref('fact_player_snapshot') }}
    where not is_goalkeeper and has_attributes
),

now_pool as (
    select *
    from snapshots
    where age between {{ f.ages[0] }} and {{ f.ages[1] }}
    qualify row_number() over (
        partition by person_id, age order by snapshot_date, tid
    ) = 1
),

target_pool as (
    select
        snapshots.*,
        horizons.horizon_age
    from snapshots
    cross join horizons
    where abs(snapshots.age - horizons.horizon_age) <= 1
    qualify row_number() over (
        partition by snapshots.person_id, horizons.horizon_age
        order by
            abs(snapshots.age - horizons.horizon_age),
            snapshots.snapshot_date,
            snapshots.tid
    ) = 1
),

pairs as (
    {% for attribute in var('attr_order') %}
    select
        '{{ attribute }}' as attribute,  -- noqa: RF04
        now_pool.age as age_now,
        target_pool.horizon_age,
        now_pool."{{ attribute }}" as value_now,
        target_pool."{{ attribute }}" as value_later
    from now_pool
    inner join target_pool
        on
            now_pool.person_id = target_pool.person_id
            and now_pool.age < target_pool.horizon_age
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

cells as (
    select
        attribute,
        age_now,
        value_now,
        horizon_age,
        count(*) as n,
        quantile_cont(value_later, 0.25) as p25,
        median(value_later) as median,
        avg(value_later) as mean,
        quantile_cont(value_later, 0.75) as p75
    from pairs
    where value_now is not null and value_later is not null
    group by attribute, age_now, value_now, horizon_age
    having count(*) >= {{ f.min_players }}
),

yearly as (
    {% for attribute in var('attr_order') %}
    select
        '{{ attribute }}' as attribute,  -- noqa: RF04
        not earlier.is_estimated and not later.is_estimated as both_exact,
        later."{{ attribute }}" - earlier."{{ attribute }}" as delta
    from snapshots as earlier
    inner join snapshots as later
        on
            earlier.person_id = later.person_id
            and date_diff('day', earlier.snapshot_date, later.snapshot_date)
            between {{ f.gap_days[0] }} and {{ f.gap_days[1] }}
    where earlier.age between {{ f.growth_ages[0] }} and {{ f.growth_ages[1] }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

growth as (
    select
        attribute,
        avg(delta) filter (where both_exact) as exact_mean,
        count(*) filter (where both_exact) as exact_n,
        avg(delta) filter (where not both_exact) as decoded_mean
    from yearly
    group by attribute
),

buckets as (
    select
        attribute,
        case
            when exact_n < {{ f.min_players }} or exact_mean is null
                then 'unmodelled'
            when abs(exact_mean) < {{ f.fixed_below }} then 'fixed'
            when
                decoded_mean is null
                or abs(decoded_mean) < {{ f.decoded_floor }}
                then 'unmodelled'
            when
                abs(exact_mean) / abs(decoded_mean) > {{ f.max_ratio }}
                or abs(decoded_mean) / abs(exact_mean) > {{ f.max_ratio }}
                then 'unmodelled'
            else 'forecastable'
        end as bucket
    from growth
)

select
    cells.*,
    coalesce(buckets.bucket, 'unmodelled') as bucket
from cells
left join buckets
    on cells.attribute = buckets.attribute
