-- Each player's transfer valuation and reputation on each snapshot, keyed (person_id, snapshot_date).
-- Stored separately from player state to isolate frequent market valuation and reputation shifts
-- from slower-moving player attributes and contract history.
select
    info.person_id,
    info.snapshot_date,
    info.tid,
    coalesce(info.value, valuation.value_estimate) as value,
    info.value is null and valuation.value_estimate is not null
        as value_is_estimated,
    case when info.value is null then valuation.is_in_trusted_band end
        as value_in_trusted_band,
    info.reputation,
    info.current_reputation,
    info.world_reputation
from {{ ref('int_player_info') }} as info
left join {{ ref('int_player_value') }} as valuation
    on
        info.snapshot_date = valuation.snapshot_date
        and info.tid = valuation.tid
order by info.person_id, info.snapshot_date
