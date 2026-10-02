-- The used slots of the three name id-tables (first_names, surnames,
-- nicknames): a person's name id -> the ordinal of its browse string.
select
    cast(phase as date) as snapshot_date,
    name_table,
    id,
    ordinal
from {{ source('raw', 'name_ids') }}
