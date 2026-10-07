-- Each competition on each snapshot: its reputation then.
select
    snapshot_date,
    cid,
    reputation,
    snapshot_date = max(snapshot_date) over () as is_current
from {{ ref('stg_competitions') }}
