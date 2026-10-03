-- The store's settings the web app reads, one row per key: the default
-- weight-set and the familiarity curve.
select
    key,
    value
from {{ ref('stg_app_config') }}
