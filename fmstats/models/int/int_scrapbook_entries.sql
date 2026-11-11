-- Each player's latest entry in our club's Scrapbook lists on each snapshot:
-- var('club_lists'), the Manager's Best Eleven, and
-- var('club_all_time_list'), its All-Time pool, which holds a new career's
-- squad before the season's list is written; on the same day a season list's
-- entry wins. The entry is a copy of his
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
    or entries.list = {{ var('club_all_time_list') }}
qualify row_number() over (
    partition by entries.snapshot_date, entries.player_tid
    order by
        entries.entry_date desc,
        entries.list = {{ var('club_all_time_list') }},
        entries.list desc
) = 1
