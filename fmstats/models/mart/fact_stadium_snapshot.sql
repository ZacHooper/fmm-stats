-- Each stadium on each snapshot: its name, capacity and expansion capacity.
select
    stadium_id,
    snapshot_date,
    name,
    capacity,
    expansion_capacity,
    is_current
from {{ ref('int_stadium_snapshots') }}
order by stadium_id, snapshot_date
