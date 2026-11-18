-- Each region (a nation's subdivision, the game's own: South-West, London,
-- Sikasso), as its latest snapshot gives it.
select
    region_id,
    uid,
    name,
    nation_id,
    weather_id,
    last_seen_date
from {{ ref('int_regions') }}
