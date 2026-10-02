-- Each nation on each snapshot: world ranking, and the ranking and coefficient
-- histories as lists, oldest first.
select
    nation_id,
    snapshot_date,
    is_ranked,
    world_ranking,
    ranking_points,
    ranking_history,
    coefficient_history,
    is_current
from {{ ref('int_nation_snapshots') }}
