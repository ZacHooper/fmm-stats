-- Each stadium, as its latest snapshot gives it.
select
    stadium_id,
    uid,
    name,
    city_id,
    capacity,
    expansion_capacity,
    last_seen_date
from {{ ref('int_stadiums') }}
