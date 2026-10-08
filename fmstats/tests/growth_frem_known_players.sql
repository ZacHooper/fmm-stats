{{ config(tags=['known_answers']) }}
-- Two Frem players' development, totals over the 18 attributes an outfield
-- player uses (all but var('gk_only_attributes')):
--   * Andreas Garly's stored attributes (var('exact_single') and the two
--     plain-byte composites, Teamwork and Aerial) never fall across his 29
--     snapshots to 2027-07-02; the modelled ones are re-estimated each
--     snapshot and may move a point either way, and after that window a fall
--     can be real. His total reads at least 212 (the baseline confirmed at
--     2024-11-10) on the latest snapshot, grew +11 from 2023-07-02 to
--     2024-06-28, and has grown at least that much over his time in our
--     squad, both ends of it exact reads.
--   * Oliver Møller-Jensen grew +36 over his time in our squad, first team
--     and reserves as one stint, which ends at 2025-06-29 when he left.
-- One row per known answer the store does not give.
{% set stored = var('exact_single') + ['Teamwork', 'Aerial'] %}
with career as (
    select * from {{ ref('stg_career') }}
),

players as (
    select
        snapshots.person_id,
        people.name,
        snapshots.snapshot_date,
        snapshots.attributes_are_estimated,
        exists (
            select 1
            from {{ ref('mart_squad_membership') }} as squads
            where
                squads.person_id = snapshots.person_id
                and squads.snapshot_date = snapshots.snapshot_date
                and squads.is_managed_club
        ) as in_our_squad,
        {% for attribute in stored %}
        snapshots."{{ attribute }}"{% if not loop.last %} +{% endif %}
        {% endfor %} as stored_total,
        {% for attribute in var('attr_order')
            if attribute not in var('gk_only_attributes') %}
        snapshots."{{ attribute }}"{% if not loop.last %} +{% endif %}
        {% endfor %} as attr_total
    from {{ ref('fact_player_snapshot') }} as snapshots
    inner join {{ ref('dim_person') }} as people
        on snapshots.person_id = people.person_id
    where
        people.name in ('Andreas Garly', 'Oliver Møller-Jensen')
        and snapshots.has_attributes
),

garly_window as (
    select
        snapshot_date,
        stored_total
        - lag(stored_total) over (order by snapshot_date) as step
    from players
    where name = 'Andreas Garly' and snapshot_date <= '2027-07-02'
),

tenures as (
    select
        name,
        max(snapshot_date) as last_date,
        max_by(attr_total, snapshot_date)
        - min_by(attr_total, snapshot_date) as growth,
        min_by(attributes_are_estimated, snapshot_date)
        or max_by(attributes_are_estimated, snapshot_date) as end_estimated
    from players
    where in_our_squad
    group by name
),

answers as (
    select
        (select count(*) from garly_window) as garly_snapshots,
        (select count(*) from garly_window where step < 0) as garly_falls,
        (
            select max_by(players.attr_total, players.snapshot_date)
            from players
            where players.name = 'Andreas Garly'
        ) as garly_latest_total,
        (
            select
                max(players.attr_total) filter (
                    where players.snapshot_date = '2024-06-28'
                )
                - max(players.attr_total) filter (
                    where players.snapshot_date = '2023-07-02'
                )
            from players
            where players.name = 'Andreas Garly'
        ) as garly_2024_growth,
        (
            select tenures.growth from tenures
            where tenures.name = 'Andreas Garly'
        ) as garly_tenure_growth,
        (
            select tenures.end_estimated from tenures
            where tenures.name = 'Andreas Garly'
        ) as garly_tenure_estimated,
        (
            select tenures.growth from tenures
            where tenures.name = 'Oliver Møller-Jensen'
        ) as mj_tenure_growth,
        (
            select tenures.last_date from tenures
            where tenures.name = 'Oliver Møller-Jensen'
        ) as mj_last_date
),

checks as (
    select
        'Garly: 29 snapshots to 2027-07-02' as check_name,
        cast(garly_snapshots as varchar) as got
    from answers
    where garly_snapshots is distinct from 29
    union all
    select
        'Garly: stored attributes never fall to 2027-07-02' as check_name,
        cast(garly_falls as varchar) as got
    from answers
    where garly_falls > 0
    union all
    select
        'Garly: total at least 212' as check_name,
        cast(garly_latest_total as varchar) as got
    from answers
    where coalesce(garly_latest_total < 212, true)
    union all
    select
        'Garly: +11 from 2023-07-02 to 2024-06-28' as check_name,
        cast(garly_2024_growth as varchar) as got
    from answers
    where garly_2024_growth is distinct from 11
    union all
    select
        'Garly: tenure growth at least his 2024 growth' as check_name,
        cast(garly_tenure_growth as varchar) as got
    from answers
    where coalesce(garly_tenure_growth < 11, true)
    union all
    select
        'Garly: tenure ends are exact reads' as check_name,
        cast(garly_tenure_estimated as varchar) as got
    from answers
    where garly_tenure_estimated is distinct from false
    union all
    select
        'Møller-Jensen: tenure growth +36' as check_name,
        cast(mj_tenure_growth as varchar) as got
    from answers
    where mj_tenure_growth is distinct from 36
    union all
    select
        'Møller-Jensen: tenure ends 2025-06-29' as check_name,
        cast(mj_last_date as varchar) as got
    from answers
    where mj_last_date is distinct from '2025-06-29'
)

select checks.*
from checks
cross join career
where career.career_key = 'frem'
