-- The store's settings, one row per key: the career keys the loader records
-- (career_key, career_managed_tid, career_rating_method, career_rollover) and
-- the config bundle's (default_method, the familiarity curve).
select
    key,
    value
from {{ source('raw', 'app_config') }}
