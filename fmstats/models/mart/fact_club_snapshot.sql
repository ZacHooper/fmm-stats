-- Each club on each snapshot: what its teams share (ground and affiliates;
-- colours and kits live on dim_club).
select
    club_tid,
    snapshot_date,
    stadium_id,
    affiliates,
    is_current
from {{ ref('int_club_snapshots') }}
order by club_tid, snapshot_date

