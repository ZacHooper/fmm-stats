-- Where each region's players play, on each snapshot: per scored tier, all
-- ages and under-21s, with the region's share of the nation's and that share
-- against day 1 (fact_region_playing_snapshot).
select
    snapshot_date,
    home_region_id,
    tier,
    age_group,
    n_players,
    nation_share,
    nation_share_index
from {{ ref('fact_region_playing_snapshot') }}
