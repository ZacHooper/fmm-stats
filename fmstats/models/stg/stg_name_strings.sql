-- The browse string table: every name string the save holds, by ordinal.
select
    cast(phase as date) as snapshot_date,
    ordinal,
    name
from {{ source('raw', 'name_strings') }}
