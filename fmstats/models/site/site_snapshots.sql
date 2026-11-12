-- The store's snapshots, the newest flagged: the web app is exported from one
-- of them (scripts/export_data.py, the newest unless asked). save_format
-- is the game version that wrote the save.
select
    snapshot_date,
    season,
    label,
    save_format,
    snapshot_date = max(snapshot_date) over () as is_latest
from {{ ref('stg_snapshots') }}
