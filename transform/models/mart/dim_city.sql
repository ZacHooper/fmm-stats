-- Each city, as its latest snapshot gives it.
select
    city_id,
    uid,
    nation_id,
    latitude,
    longitude,
    attraction,
    region_id,
    last_seen_date
from {{ ref('int_cities') }}
