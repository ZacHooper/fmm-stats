-- Each region's tier-weighted appearances by season (fact_region_season), the
-- split by tier included.
select
    season,
    home_region_id,
    is_live,
    appearances,
    weighted_appearances,
    appearances_by_tier,
    nation_share,
    nation_share_index
from {{ ref('fact_region_season') }}
