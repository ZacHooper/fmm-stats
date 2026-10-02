-- Each nation's world-ranking history, oldest first (seq 0). The list grows
-- with the career, so its length is not fixed.
select
    cast(phase as date) as snapshot_date,
    nation_id,
    seq,
    ranking
from {{ source('raw', 'nation_ranking_history') }}
