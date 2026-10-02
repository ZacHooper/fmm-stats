-- Every club-shaped record's name, one row per club per snapshot.
select
    cast(phase as date) as snapshot_date,
    tid,
    name
from {{ source('raw', 'clubs') }}
