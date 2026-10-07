-- The career this store holds, one row: its key, the club it manages and the
-- day its new season starts (career_rollover, 'MM-DD'; careers.py measures it
-- per career).
select
    max(case when key = 'career_key' then value end) as career_key,
    cast(
        max(case when key = 'career_managed_tid' then value end) as integer
    ) as managed_club_tid,
    cast(
        split_part(
            max(case when key = 'career_rollover' then value end), '-', 1
        ) as integer
    ) as rollover_month,
    cast(
        split_part(
            max(case when key = 'career_rollover' then value end), '-', 2
        ) as integer
    ) as rollover_day
from {{ source('raw', 'app_config') }}
