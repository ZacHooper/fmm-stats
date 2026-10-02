-- The stadium table, one row per stadium per snapshot. city_id is NULL where
-- the record names no city (var('no_id16')).
select
    cast(phase as date) as snapshot_date,
    id as stadium_id,
    uid,
    name,
    nullif(city_id, {{ var('no_id16') }}) as city_id,
    capacity,
    expansion_capacity
from {{ source('raw', 'stadiums') }}
