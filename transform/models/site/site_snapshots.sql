-- mart.snapshots on the new layers: one row per snapshot, its season and
-- phase (the in-game date as text), its order and whether it is its season's
-- latest. phase_ord equals phase: every phase is a date.
select
    season,
    strftime(snapshot_date, '%Y-%m-%d') as phase,
    label,
    strftime(snapshot_date, '%Y-%m-%d') as phase_ord,
    snapshot_date as phase_date,
    row_number() over (order by season, snapshot_date) as snap_ix,
    snapshot_date = max(snapshot_date) over (partition by season)
        as is_latest_in_season
from {{ ref('stg_snapshots') }}
