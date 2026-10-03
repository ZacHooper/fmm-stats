-- Every ranked nation on every snapshot, keyed (snapshot_date, nation_id):
-- its world ranking (1 the top), ranking points, its continental coefficient
-- (the sum of its coefficient history) and its rival.
select
    nations.snapshot_date,
    nations.nation_id,
    names.name,
    nations.world_ranking + 1 as world_rank,
    nations.ranking_points,
    list_sum(nations.coefficient_history) as coefficient,
    rivals.name as rival
from {{ ref('fact_nation_snapshot') }} as nations
inner join {{ ref('dim_nation') }} as names
    on nations.nation_id = names.nation_id
left join {{ ref('dim_nation') }} as rivals
    on names.rival_nation_id = rivals.nation_id
where nations.is_ranked
