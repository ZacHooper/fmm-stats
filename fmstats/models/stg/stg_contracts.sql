-- Every used slot of the contract grid as stored; lapsed contracts keep their
-- dates. A person's current contract is the slot with is_current: marker bit 0
-- (1, 3, 17, 21 are live, unexpired and waged; 0, 2, 16, 20 are lapsed).
select
    cast(phase as date) as snapshot_date,
    tid,
    marker,
    marker & 1 = 1 as is_current,
    wage_units,
    expiry,
    start_date
from {{ source('raw', 'contracts') }}
