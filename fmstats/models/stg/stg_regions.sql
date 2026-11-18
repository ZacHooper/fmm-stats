-- The region table, one row per region per snapshot: what a city's region_id
-- names (South-West, London, ... for England). weather_id is NULL where the
-- record names none (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    id as region_id,
    uid,
    name,
    nation_id,
    nullif(weather_id, {{ var('no_id16') }}) as weather_id
from {{ source('raw', 'regions') }}
