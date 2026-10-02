-- Each European nation's country coefficients, oldest first (seq 0). The last
-- entry is the season in progress and reads 0.
select
    cast(phase as date) as snapshot_date,
    nation_id,
    seq,
    coefficient
from {{ source('raw', 'nation_coefficients') }}
