-- The used slots of the three name id-tables (first_names, surnames,
-- nicknames): a person's name id -> the ordinal of its browse string.
select
    season,
    phase,
    name_table,
    id,
    ordinal
from {{ source('raw', 'name_ids') }}
