-- The settings the web app reads, one row per key: the store's (the default
-- weight-set, the familiarity curve) and the loan outlook's (the familiarity
-- a position needs, the formation a club with none known plays).
select
    key,
    value
from {{ ref('stg_app_config') }}
union all
select
    'min_familiarity' as key,  -- noqa: RF04
    '{{ var("loan_outlook").min_familiarity }}' as value
union all
select
    'fallback_formation' as key,  -- noqa: RF04
    '{{ var("fallback_formation") }}' as value
