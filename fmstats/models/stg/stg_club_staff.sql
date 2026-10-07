-- Each club's staff array, one row per member listed. The manager is not in
-- it.
select
    cast(phase as date) as snapshot_date,
    club_tid,
    staff_tid,
    slot
from {{ source('raw', 'club_staff') }}
