-- The formation catalog the staff records index, by id.
select
    cast(phase as date) as snapshot_date,
    formation_id,
    name
from {{ source('raw', 'formations') }}
