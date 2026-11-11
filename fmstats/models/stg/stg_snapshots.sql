-- One row per loaded save: its in-game date, the season it falls in (the
-- campaign's end year) and the save it came from. Every other stg model is
-- keyed by snapshot_date; season is read from here. save_format is the game
-- the save came from ('fmm22', 'fmm27').
select
    cast(phase as date) as snapshot_date,
    season,
    label,
    save_path,
    loaded_at,
    save_format
from {{ source('raw', 'extracts') }}
