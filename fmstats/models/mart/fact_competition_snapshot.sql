-- Each competition on each snapshot: its reputation.
select
    cid,
    snapshot_date,
    reputation,
    is_current
from {{ ref('int_competition_snapshots') }}
