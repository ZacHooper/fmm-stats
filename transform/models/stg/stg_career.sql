-- The career this store holds, one row: its key and the club it manages.
select
    max(case when key = 'career_key' then value end) as career_key,
    cast(
        max(case when key = 'career_managed_tid' then value end) as integer
    ) as managed_club_tid
from {{ source('raw', 'app_config') }}
