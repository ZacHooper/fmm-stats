-- Each stadium: its city. Name and capacity change over a career, so they are
-- on fact_stadium_snapshot.
select
    stadium_id,
    uid,
    city_id,
    last_seen_date
from {{ ref('int_stadiums') }}
