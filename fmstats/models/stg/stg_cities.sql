-- The city table, one row per city per snapshot. region_id is NULL where the
-- record names no region (var('no_id16')). attraction is the game's 0-20
-- rating of the city.
select
    cast(phase as date) as snapshot_date,
    id as city_id,
    uid,
    nation_id,
    latitude,
    longitude,
    attraction,
    nullif(region_id, {{ var('no_id16') }}) as region_id
from {{ source('raw', 'cities') }}
