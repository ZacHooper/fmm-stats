-- One row per loaded save: its in-game date, the season it falls in (the
-- campaign's end year) and the save it came from. Every other stg model is
-- keyed by snapshot_date; season is read from here.
select
    cast(phase as date) as snapshot_date,
    season,
    label,
    save_path,
    loaded_at
from {{ source('raw', 'extracts') }}
