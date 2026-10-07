-- The store's snapshots, the newest flagged: the web app is exported from one
-- of them (scripts/export_site.py, the newest unless asked).
select
    snapshot_date,
    season,
    label,
    snapshot_date = max(snapshot_date) over () as is_latest
from {{ ref('stg_snapshots') }}
