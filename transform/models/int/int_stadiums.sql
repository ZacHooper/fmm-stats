-- Each stadium once: what does not change between snapshots (its uid and
-- city). Name and capacity change (Valby Stadion 4,400, then 9,400, then
-- 15,000) and are on int_stadium_snapshots.
select
    stadium_id,
    uid,
    city_id,
    last_seen_date
from ({{ latest(ref('stg_stadiums'), 'stadium_id') }})
