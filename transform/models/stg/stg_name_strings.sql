-- The browse string table: every name string the save holds, by ordinal.
select
    season,
    phase,
    ordinal,
    name
from {{ source('raw', 'name_strings') }}
