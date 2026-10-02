-- Each nation on each snapshot: world ranking, the ranking and coefficient
-- histories (oldest first) and the languages it speaks.
select
    nation_id,
    snapshot_date,
    is_ranked,
    world_ranking,
    ranking_points,
    ranking_history,
    coefficient_history,
    languages,
    is_current
from {{ ref('int_nation_snapshots') }}
