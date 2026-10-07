-- Each stadium on each snapshot: its name and capacity then.
select
    snapshot_date,
    stadium_id,
    name,
    capacity,
    expansion_capacity,
    snapshot_date = max(snapshot_date) over () as is_current
from {{ ref('stg_stadiums') }}
