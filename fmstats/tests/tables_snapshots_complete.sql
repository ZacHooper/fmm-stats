-- Every snapshot holds the reference tables every save yields: a snapshot
-- with none was restored from a store published before the loader read
-- them (scripts/pull_store.py names the snapshots; --reload re-extracts
-- them), and every model built on them would leave it out.
--   no regions               raw.regions has no row for the snapshot
--   no season stats          raw.player_season_stats has no row for it
select
    snapshots.snapshot_date,
    'no regions' as "check"
from {{ ref('stg_snapshots') }} as snapshots
where
    snapshots.snapshot_date not in (
        select regions.snapshot_date from {{ ref('stg_regions') }} as regions
    )
union all
select
    snapshots.snapshot_date,
    'no season stats' as "check"
from {{ ref('stg_snapshots') }} as snapshots
where
    snapshots.snapshot_date not in (
        select stats.snapshot_date
        from {{ ref('stg_player_season_stats') }} as stats
    )
