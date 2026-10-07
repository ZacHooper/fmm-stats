-- Every ranked nation on every snapshot, keyed (snapshot_date, nation_id):
-- its world ranking (1 the top), ranking points, its continental coefficient
-- (the sum of its coefficient history) and its rival.
--
-- coefficient_history: the per-season coefficients, oldest first, the last
-- entry the season in progress. The list moves along one place when a season
-- closes (European nations' in June), so
--
-- coefficient_season: the season (end year) of the newest COMPLETED entry, the
-- second to last: the year of the latest snapshot, up to this one, on which the
-- list had moved along. NULL before any such move is on record.
--
-- coefficient_is_live: whether the nation's history changes anywhere in the
-- store. Some never do (every African nation's reads the same on every
-- snapshot): those are the game's starting values, which it doesn't update.
with nations as (
    select
        *,
        lag(coefficient_history) over (
            partition by nation_id order by snapshot_date
        ) as previous_history
    from {{ ref('fact_nation_snapshot') }}
),

moved as (
    select
        *,
        max(
            case
                when
                    len(coefficient_history) > 1
                    and coefficient_history <> previous_history
                    and coefficient_history[1:-3] = previous_history[2:-2]
                    then year(snapshot_date)
            end
        ) over (
            partition by nation_id order by snapshot_date
            rows between unbounded preceding and current row
        ) as coefficient_season,
        count(distinct coefficient_history) over (
            partition by nation_id
        ) > 1 as coefficient_is_live
    from nations
)

select
    moved.snapshot_date,
    moved.nation_id,
    nation_names.name,
    moved.world_ranking + 1 as world_rank,
    moved.ranking_points,
    list_sum(moved.coefficient_history) as coefficient,
    moved.coefficient_history,
    moved.coefficient_season,
    moved.coefficient_is_live,
    rivals.name as rival
from moved
inner join {{ ref('dim_nation') }} as nation_names
    on moved.nation_id = nation_names.nation_id
left join {{ ref('dim_nation') }} as rivals
    on nation_names.rival_nation_id = rivals.nation_id
where moved.is_ranked
