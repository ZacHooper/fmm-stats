-- Each club on each snapshot: what its teams share (ground, colours and kits,
-- academy, affiliates).
select
    club_tid,
    snapshot_date,
    stadium_id,
    academy,
    colours,
    kits,
    affiliates,
    is_current
from {{ ref('int_club_snapshots') }}
