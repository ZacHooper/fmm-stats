-- How many players each region has produced at each scored tier's level or
-- better, on each snapshot, all ages and under-21s, with the region's share of
-- the nation's and that share against day 1 (fact_region_level_snapshot).
select
    snapshot_date,
    home_region_id,
    level_tier,
    age_group,
    n_players,
    nation_share,
    nation_share_index
from {{ ref('fact_region_level_snapshot') }}
