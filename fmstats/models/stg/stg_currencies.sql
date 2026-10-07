-- The currency table, one row per currency per snapshot. Money in the save is
-- already in one currency; rate_per_gbp is how many units buy one pound
-- (Danish Krone 8.699).
select
    cast(phase as date) as snapshot_date,
    uid,
    name,
    exchange_rate as rate_per_gbp
from {{ source('raw', 'currencies') }}
