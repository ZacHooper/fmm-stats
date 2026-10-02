-- Every used slot of the contract grid as stored; lapsed contracts keep their
-- dates. A person's current contract is the slot with is_current.
select
    season,
    phase,
    tid,
    marker,
    marker = 1 as is_current,
    wage_units,
    expiry,
    start_date
from {{ source('raw', 'contracts') }}
