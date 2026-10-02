-- Each nation on each snapshot: its world ranking, and the two histories as
-- lists, oldest first. Only European nations have coefficients; the last is
-- the season in progress and reads 0.
with rankings as (
    select
        snapshot_date,
        nation_id,
        list(ranking order by seq) as ranking_history
    from {{ ref('stg_nation_ranking_history') }}
    group by snapshot_date, nation_id
),

coefficients as (
    select
        snapshot_date,
        nation_id,
        list(coefficient order by seq) as coefficient_history
    from {{ ref('stg_nation_coefficients') }}
    group by snapshot_date, nation_id
)

select
    nations.snapshot_date,
    nations.nation_id,
    nations.is_ranked,
    nations.world_ranking,
    nations.ranking_points,
    coalesce(rankings.ranking_history, []) as ranking_history,
    coalesce(coefficients.coefficient_history, []) as coefficient_history,
    nations.snapshot_date = max(nations.snapshot_date) over () as is_current
from {{ ref('stg_nations') }} as nations
left join rankings
    on
        nations.snapshot_date = rankings.snapshot_date
        and nations.nation_id = rankings.nation_id
left join coefficients
    on
        nations.snapshot_date = coefficients.snapshot_date
        and nations.nation_id = coefficients.nation_id
