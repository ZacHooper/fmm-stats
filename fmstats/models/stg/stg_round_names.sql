-- The game's catalog of stage, round and leg names.
select
    cast(phase as date) as snapshot_date,
    id as round_name_id,
    name
from {{ source('raw', 'round_names') }}
