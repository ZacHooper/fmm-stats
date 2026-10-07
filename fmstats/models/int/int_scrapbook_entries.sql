-- Each player's latest entry in our club's Scrapbook lists (var('club_lists'),
-- the Manager's Best Eleven) on each snapshot. The entry is a copy of his
-- profile as it was on entry_date; is_fresh marks one at most
-- var('scrapbook_max_age_days') old, recent enough to stand in for what his
-- own record does not state.
select
    entries.*,
    entries.snapshot_date - entries.entry_date
    <= {{ var('scrapbook_max_age_days') }} as is_fresh
from {{ ref('stg_scrapbook_entries') }} as entries
where
    entries.list between {{ var('club_lists')[0] }}
    and {{ var('club_lists')[1] }}
qualify row_number() over (
    partition by entries.snapshot_date, entries.player_tid
    order by entries.entry_date desc, entries.list desc
) = 1
